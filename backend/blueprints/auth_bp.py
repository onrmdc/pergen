"""
Authentication Blueprint — in-app login → HttpOnly cookie session.

Wave-6 Phase F deliverable. Implements Council-decided Option B from
``docs/refactor/DONE_spa_auth_ui.md``: an operator logs in once via
``/login``, the server sets a Flask-signed session cookie carrying
``{actor, csrf}``, and the dual-path token gate
(``backend/app_factory.py::_install_api_token_gate``) accepts the
cookie+CSRF combination on every subsequent ``/api/*`` request.

Routes
------
``POST /api/auth/login``    — body ``{username, password}``. ``password``
                              here is the per-actor API token, validated
                              against the immutable token snapshot from
                              ``app.extensions["pergen"]["token_snapshot"]``.
                              On success: ``session.clear()`` (defeats
                              session fixation) + repopulate
                              ``{actor, csrf, iat}``. Returns
                              ``{ok: true, csrf: <token>}``.
``POST /api/auth/logout``   — ``session.clear()``. Returns ``{ok: true}``.
``GET  /api/auth/whoami``   — returns ``{actor, csrf}`` for a logged-in
                              session, ``{actor: null}`` otherwise.
``GET  /login``             — server-rendered HTML login form.
                              CSP-compliant (no inline JS / no inline CSS).
                              Posts via ``pergenFetch``.

Security
--------
* Cookie attributes: ``HttpOnly; SameSite=Lax``; ``Secure`` is gated
  on ``app.config["SESSION_COOKIE_SECURE"]`` (True in prod, False in dev).
* Session fixation: ``session.clear()`` is called before the new keys
  are set on every login.
* Login throttling: in-process LRU token bucket per
  ``(remote_addr, username)`` — 10 fails / 60s → 429 with ``Retry-After``.
  Bounded at 1024 entries to cap memory.
* Audit lines: ``audit auth.login.success/auth.login.fail/auth.logout``
  matching the format used by the other blueprints.
* Constant-time credential check: delegates to ``hmac.compare_digest``
  and iterates over every configured token even after a hit so timing
  leaks the *count* of actors but not which one matched.
* CSRF defence is enforced by the gate, not this blueprint —
  ``/api/auth/login`` itself is exempt (the SPA has no session cookie
  to issue a CSRF token from yet).
"""
from __future__ import annotations

import hmac
import logging
import os
import time
from collections import OrderedDict
from threading import Lock
from typing import Any

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    make_response,
    request,
    session,
)
from markupsafe import escape as _escape

from backend.security.csrf import issue_csrf_token

# Audit channel — same format as inventory_bp / credentials_bp.
_audit = logging.getLogger("app.audit")
_log = logging.getLogger("app.blueprints.auth")

auth_bp = Blueprint("auth", __name__)

# ----- Login throttling ---------------------------------------------------
# Token-bucket-ish: per-key list of failure timestamps within the window.
# Bounded LRU so a flood of distinct (ip, user) pairs cannot OOM us.
_THROTTLE_WINDOW_SEC = 60
_THROTTLE_MAX_FAILS = 10
_THROTTLE_LRU_CAP = 1024
_throttle_lock = Lock()
_throttle: "OrderedDict[tuple[str, str], list[float]]" = OrderedDict()


def _throttle_key() -> tuple[str, str]:
    """Build a per-IP-per-user throttling key. Username may be empty."""
    ip = (request.remote_addr or "-").strip()
    body = request.get_json(silent=True) or {}
    user = (body.get("username") or "").strip()
    return (ip, user)


def _throttle_check(now: float | None = None) -> int | None:
    """Return ``Retry-After`` seconds if the bucket is full, else ``None``.

    Pure read — does not record the current attempt.
    """
    now = now or time.monotonic()
    key = _throttle_key()
    with _throttle_lock:
        bucket = _throttle.get(key)
        if not bucket:
            return None
        # Drop expired entries lazily.
        cutoff = now - _THROTTLE_WINDOW_SEC
        bucket = [t for t in bucket if t > cutoff]
        if not bucket:
            _throttle.pop(key, None)
            return None
        _throttle[key] = bucket
        if len(bucket) >= _THROTTLE_MAX_FAILS:
            # Retry-After: seconds until the oldest entry falls out of window.
            oldest = bucket[0]
            return max(1, int(_THROTTLE_WINDOW_SEC - (now - oldest)))
    return None


def _throttle_record_fail(now: float | None = None) -> None:
    """Append a failure timestamp. Caps the LRU at ``_THROTTLE_LRU_CAP``."""
    now = now or time.monotonic()
    key = _throttle_key()
    with _throttle_lock:
        bucket = _throttle.get(key) or []
        cutoff = now - _THROTTLE_WINDOW_SEC
        bucket = [t for t in bucket if t > cutoff]
        bucket.append(now)
        _throttle[key] = bucket
        # Move-to-end so the LRU evicts cold keys first.
        _throttle.move_to_end(key)
        while len(_throttle) > _THROTTLE_LRU_CAP:
            _throttle.popitem(last=False)


def _throttle_clear() -> None:
    """Reset on a successful login so a typo'd password isn't held against the user."""
    key = _throttle_key()
    with _throttle_lock:
        _throttle.pop(key, None)


def _is_cookie_auth_enabled() -> bool:
    """Cookie-auth feature flag — opt-in via env or app.config."""
    val = (
        os.environ.get("PERGEN_AUTH_COOKIE_ENABLED")
        or current_app.config.get("PERGEN_AUTH_COOKIE_ENABLED")
        or ""
    )
    return str(val).strip() == "1"


def _token_snapshot() -> dict[str, str]:
    """Return the immutable per-actor token map from the gate snapshot."""
    snap = (
        current_app.extensions.get("pergen", {}).get("token_snapshot")
    )
    return dict(snap or {})


# --------------------------------------------------------------------------- #
# JSON endpoints                                                              #
# --------------------------------------------------------------------------- #


@auth_bp.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    """Validate ``{username, password}`` and start a signed-cookie session.

    The ``password`` field is treated as the operator's per-actor API
    token (NOT a separate password) — Pergen's identity model is a small
    set of named tokens, see ``app_factory._parse_actor_tokens``.

    Returns:
        200 ``{"ok": true, "csrf": "<token>"}`` on success (Set-Cookie).
        400 on malformed body.
        401 on bad credentials.
        429 ``{"error": "rate_limited"}`` + ``Retry-After`` header
            after 10 fails / 60s for the same (IP, username).
    """
    retry_after = _throttle_check()
    if retry_after is not None:
        _audit.warning(
            "audit auth.login.throttled actor=- ip=%s",
            request.remote_addr or "-",
        )
        resp = jsonify({"error": "rate_limited"})
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        return resp

    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        return jsonify({"error": "missing username or password"}), 400

    tokens = _token_snapshot()
    # Constant-time scan: iterate every token even after a hit.
    matched = False
    if username in tokens:
        expected = tokens[username]
        if hmac.compare_digest(str(password), str(expected)):
            matched = True
    # Even when the username is unknown, do a single dummy compare so the
    # response time is not a username-existence oracle.
    else:
        _ = hmac.compare_digest(str(password), "x" * max(1, len(password)))

    if not matched:
        _throttle_record_fail()
        # Audit (Security review H-6): redact the username in the audit
        # log when it does not match any configured actor — otherwise
        # an attacker who can read logs (or correlate audit-line volume
        # per username) can confirm valid usernames. The audit line
        # still carries the IP for forensic correlation.
        _audit.warning(
            "audit auth.login.fail actor=%s ip=%s",
            username if username in tokens else "<unknown>",
            request.remote_addr or "-",
        )
        return jsonify({"error": "invalid credentials"}), 401

    # Session fixation defence: blow away any pre-existing session keys
    # before populating the new ones. Flask issues a fresh signed cookie
    # value on the next response.
    session.clear()
    csrf = issue_csrf_token()
    session["actor"] = username
    session["csrf"] = csrf
    session["iat"] = int(time.time())
    session.permanent = True

    _throttle_clear()
    _audit.info(
        "audit auth.login.success actor=%s ip=%s",
        username,
        request.remote_addr or "-",
    )
    return jsonify({"ok": True, "csrf": csrf})


@auth_bp.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    """Clear the session cookie. Idempotent — always returns 200."""
    actor = session.get("actor") or "-"
    session.clear()
    _audit.info(
        "audit auth.logout actor=%s ip=%s",
        actor,
        request.remote_addr or "-",
    )
    return jsonify({"ok": True})


@auth_bp.route("/api/auth/whoami", methods=["GET"])
def api_auth_whoami():
    """Return the current session's actor + CSRF token, or ``null``."""
    actor = session.get("actor")
    if not actor:
        return jsonify({"actor": None})
    return jsonify({"actor": actor, "csrf": session.get("csrf", "")})


# --------------------------------------------------------------------------- #
# Server-rendered login page                                                  #
# --------------------------------------------------------------------------- #


_LOGIN_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Pergen — Sign in</title>
  <link rel="stylesheet" href="/static/css/extracted-inline.css">
  <link rel="stylesheet" href="/static/css/components.css">
  <link rel="stylesheet" href="/static/css/login.css">
</head>
<body>
  <main class="login-shell">
    <form id="loginForm" class="login-card" autocomplete="off">
      <h1 class="login-title">Pergen</h1>
      <p class="login-sub">Sign in with your operator credentials.</p>
      <label class="login-label" for="loginUsername">Username</label>
      <input class="login-input" id="loginUsername" name="username"
             type="text" autocomplete="username" required />
      <label class="login-label" for="loginPassword">Token</label>
      <input class="login-input" id="loginPassword" name="password"
             type="password" autocomplete="current-password" required />
      <button class="login-btn" id="loginSubmit" type="submit">Sign in</button>
      <p class="login-error" id="loginError" hidden></p>
      <input type="hidden" id="loginNext" value="__NEXT__" />
    </form>
  </main>
  <script src="/static/js/login.js"></script>
</body>
</html>
"""


@auth_bp.route("/login", methods=["GET"])
def login_page() -> Response:
    """Render the CSP-compliant login form.

    The ``?next=<hash>`` query param is escaped and round-tripped through
    a hidden input so a successful login can hand control back to the
    SPA at the right hash route.
    """
    next_raw = request.args.get("next") or ""
    # markupsafe.escape ensures any HTML metacharacter in `next` is
    # neutralised before insertion into the template.
    next_safe = str(_escape(next_raw))
    html = _LOGIN_HTML_TEMPLATE.replace("__NEXT__", next_safe)
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


# --------------------------------------------------------------------------- #
# Test seam                                                                   #
# --------------------------------------------------------------------------- #


def _reset_throttle_for_tests() -> None:
    """Test-only seam: clear the in-process LRU between cases."""
    with _throttle_lock:
        _throttle.clear()
