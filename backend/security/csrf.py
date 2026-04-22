"""
CSRF token issuance and constant-time verification.

Wave-6 Phase F deliverable. Pure helpers — no Flask coupling — so the
module can be unit-tested without an app context. The auth blueprint
issues a fresh token on login and stores it in ``flask.session["csrf"]``
(signed by ``SECRET_KEY``). The token gate (``_install_api_token_gate``)
verifies the supplied ``X-CSRF-Token`` header against that session-bound
token on every state-changing request when the cookie auth path is
enabled.

Security
--------
* Tokens are 256 bits of cryptographic randomness (``secrets.token_urlsafe(32)``).
* Verification uses ``hmac.compare_digest`` to neutralise timing oracles.
* No fallback to ``==`` — if either side is missing/empty, verify returns
  ``False``.

Reference: ``docs/refactor/DONE_spa_auth_ui.md`` Phase 2.
"""
from __future__ import annotations

import hmac
import secrets

# 32 bytes → ~43 chars URL-safe base64. Matches the entropy budget of the
# per-actor API tokens themselves.
_CSRF_TOKEN_BYTES = 32


def issue_csrf_token() -> str:
    """Return a fresh, cryptographically random CSRF token (URL-safe).

    Outputs
    -------
    str — 43-character URL-safe base64 string (256 bits of entropy).

    Security
    --------
    Generated via ``secrets.token_urlsafe`` which uses the OS CSPRNG
    (``/dev/urandom`` on Unix). Never log this value — it would defeat
    the CSRF protection it's meant to provide.
    """
    return secrets.token_urlsafe(_CSRF_TOKEN_BYTES)


def verify_csrf_token(supplied: str | None, expected: str | None) -> bool:
    """Constant-time CSRF token comparison.

    Inputs
    ------
    supplied : token from the inbound request header ``X-CSRF-Token``.
    expected : token previously stored in ``flask.session["csrf"]``.

    Outputs
    -------
    ``True`` iff both values are non-empty strings AND equal under
    ``hmac.compare_digest``. Any falsy value on either side returns
    ``False`` immediately (defence-in-depth: a missing session token
    must never grant access regardless of what the client sends).

    Security
    --------
    Uses ``hmac.compare_digest`` to avoid leaking the token byte-by-byte
    via timing differences. The early ``not supplied or not expected``
    short-circuit is intentionally on the *combined* falsy check —
    not equivalent strings, just a guard so ``compare_digest`` always
    sees two non-empty bytes-of-the-same-length comparable values.
    """
    if not supplied or not expected:
        return False
    # ``compare_digest`` requires both args be the same type (both str
    # or both bytes). Coerce to ``str`` defensively.
    return hmac.compare_digest(str(supplied), str(expected))
