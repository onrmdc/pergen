"""Wave-6 Phase F: cookie-auth login flow happy path + error cases.

Validates the new ``auth_bp`` blueprint:
* ``POST /api/auth/login`` with valid (username, password=token)
  → 200 + ``Set-Cookie: pergen_session=...; HttpOnly`` + JSON body
  with a CSRF token.
* ``GET /api/auth/whoami`` after login returns the actor + CSRF.
* ``POST /api/auth/logout`` clears the session — subsequent whoami
  returns ``{actor: null}``.
* Bad credentials → 401.
* Missing fields → 400.

The cookie path is exercised under ``PERGEN_AUTH_COOKIE_ENABLED=1``
so the auth blueprint endpoints are reachable via the dual-path gate.
"""
from __future__ import annotations

import importlib
import sys

import pytest

pytestmark = [pytest.mark.security]

_ALICE_TOK = "a" * 64
_BOB_TOK = "b" * 64


def _gated_app(monkeypatch, tmp_path, *, cookie_enabled: bool = True):
    """Build a fresh app with the cookie auth path enabled."""
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    monkeypatch.setenv(
        "PERGEN_API_TOKENS",
        f"alice:{_ALICE_TOK},bob:{_BOB_TOK}",
    )
    monkeypatch.delenv("PERGEN_DEV_OPEN_API", raising=False)
    monkeypatch.delenv("PERGEN_API_TOKEN", raising=False)
    if cookie_enabled:
        monkeypatch.setenv("PERGEN_AUTH_COOKIE_ENABLED", "1")
    else:
        monkeypatch.delenv("PERGEN_AUTH_COOKIE_ENABLED", raising=False)
    for mod in [
        "backend.app",
        "backend.app_factory",
        "backend.blueprints",
        "backend.blueprints.auth_bp",
        "backend.config",
        "backend.config.app_config",
        "backend.config.settings",
    ]:
        sys.modules.pop(mod, None)
    factory = importlib.import_module("backend.app_factory")
    # Clear throttle between tests.
    auth_mod = importlib.import_module("backend.blueprints.auth_bp")
    auth_mod._reset_throttle_for_tests()
    app = factory.create_app("development")
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    return app


def test_login_happy_path_sets_session_cookie(monkeypatch, tmp_path) -> None:
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    res = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": _ALICE_TOK},
    )
    assert res.status_code == 200, res.get_data(as_text=True)
    body = res.get_json()
    assert body.get("ok") is True
    assert body.get("csrf"), "login response must carry a CSRF token"

    # Check cookie attributes.
    set_cookie = res.headers.get("Set-Cookie", "")
    assert "pergen_session=" in set_cookie, set_cookie
    assert "HttpOnly" in set_cookie, "session cookie must be HttpOnly"
    assert "SameSite=Lax" in set_cookie, "session cookie must be SameSite=Lax"
    # Secure is config-driven (False in dev) so we only assert when set.


def test_login_bad_credentials_401(monkeypatch, tmp_path) -> None:
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    res = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong"},
    )
    assert res.status_code == 401
    body = res.get_json()
    assert "error" in body
    # No Set-Cookie should be issued for failed login.
    assert "pergen_session" not in res.headers.get("Set-Cookie", "")


def test_login_unknown_user_401(monkeypatch, tmp_path) -> None:
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    res = client.post(
        "/api/auth/login",
        json={"username": "mallory", "password": _ALICE_TOK},
    )
    assert res.status_code == 401


def test_login_missing_fields_400(monkeypatch, tmp_path) -> None:
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    res = client.post("/api/auth/login", json={})
    assert res.status_code == 400


def test_whoami_anonymous_returns_null(monkeypatch, tmp_path) -> None:
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    res = client.get("/api/auth/whoami")
    assert res.status_code == 200
    assert res.get_json() == {"actor": None}


def test_whoami_after_login_returns_actor_and_csrf(monkeypatch, tmp_path) -> None:
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    rlogin = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": _ALICE_TOK},
    )
    csrf = rlogin.get_json()["csrf"]

    rwho = client.get("/api/auth/whoami")
    assert rwho.status_code == 200
    body = rwho.get_json()
    assert body["actor"] == "alice"
    assert body["csrf"] == csrf


def test_logout_clears_session(monkeypatch, tmp_path) -> None:
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    client.post(
        "/api/auth/login",
        json={"username": "alice", "password": _ALICE_TOK},
    )
    res = client.post("/api/auth/logout")
    assert res.status_code == 200
    assert res.get_json() == {"ok": True}

    rwho = client.get("/api/auth/whoami")
    assert rwho.get_json() == {"actor": None}


def test_login_page_renders_csp_compliant_html(monkeypatch, tmp_path) -> None:
    """GET /login must serve HTML with no inline <script> or <style>."""
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    res = client.get("/login")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "<form" in html
    # CSP compliance: no inline script / style tags.
    # (External <link rel="stylesheet"> and <script src="..."> are fine.)
    import re as _re
    assert not _re.search(r"<script(?![^>]*\bsrc=)", html), (
        "login page must not contain inline <script> tags (CSP script-src 'self')"
    )
    assert not _re.search(r"<style\b", html), (
        "login page must not contain inline <style> tags (CSP style-src 'self')"
    )
    # The hidden next-input must be present so the form can round-trip ?next=.
    assert 'id="loginNext"' in html


def test_login_page_escapes_next_param(monkeypatch, tmp_path) -> None:
    """A malicious ?next= must be HTML-escaped, not reflected verbatim.

    The hazard is the attacker breaking out of the ``value="..."``
    attribute on the hidden input. markupsafe.escape converts ``"`` to
    ``&#34;`` so the breakout is impossible — the literal text
    ``onfocus=alert(1)`` survives but only as inert attribute data.
    We assert the breakout chars are escaped, not the literal payload.
    """
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    res = client.get('/login?next="><script>alert(1)</script>')
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    # The breakout characters MUST be escaped.
    assert "<script>alert(1)</script>" not in html, (
        "raw script tag in next param must not be reflected unescaped"
    )
    # Specifically, the closing-quote / angle bracket pair must not appear
    # adjacent in the rendered HTML (they would close the value attribute).
    assert '"><script>' not in html
    # The escaped form should be present.
    assert "&lt;script&gt;" in html or "&#34;&gt;" in html or "&#34;" in html


def test_cookie_path_grants_access_with_csrf(monkeypatch, tmp_path) -> None:
    """After login, GET works (cookie alone) and POST works (cookie + CSRF)."""
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    rlogin = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": _ALICE_TOK},
    )
    csrf = rlogin.get_json()["csrf"]

    # Safe method: cookie alone is sufficient.
    rget = client.get("/api/inventory")
    assert rget.status_code == 200, rget.get_data(as_text=True)

    # Unsafe method without CSRF → 403.
    rpost_bad = client.post(
        "/api/inventory/device",
        json={"hostname": "newdev", "ip": "10.99.0.1"},
    )
    assert rpost_bad.status_code == 403

    # Unsafe method with CSRF → succeeds (or domain-level error, but not 401/403).
    rpost = client.post(
        "/api/inventory/device",
        json={"hostname": "newdev", "ip": "10.99.0.1"},
        headers={"X-CSRF-Token": csrf},
    )
    assert rpost.status_code not in (401, 403), rpost.get_data(as_text=True)


def test_legacy_token_header_path_still_works(monkeypatch, tmp_path) -> None:
    """X-API-Token must still authenticate even when cookie path is enabled."""
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    rget = client.get("/api/inventory", headers={"X-API-Token": _ALICE_TOK})
    assert rget.status_code == 200, rget.get_data(as_text=True)

    # State-changing call also works without CSRF when using the token header
    # (CSRF is only required on the cookie path).
    rpost = client.post(
        "/api/inventory/device",
        json={"hostname": "tok-dev", "ip": "10.99.0.2"},
        headers={"X-API-Token": _ALICE_TOK},
    )
    assert rpost.status_code not in (401, 403), rpost.get_data(as_text=True)
