"""H-2 — session idle-timeout regression test.

Audit (Security review H-2): the auth gate now stamps ``session["iat"]``
at login and clears the session on every request whose ``iat`` is older
than ``PERGEN_SESSION_IDLE_HOURS * 3600`` seconds. Default Flask cookie
lifetime (31 days) was far too long for an operator tool with SSH
credential authority.

This module pins three contracts:

1. ``PERMANENT_SESSION_LIFETIME`` is a ``datetime.timedelta`` on
   ``app.config`` (NOT a raw int); the env var
   ``PERGEN_SESSION_LIFETIME_HOURS`` controls its magnitude.
2. ``PERGEN_SESSION_IDLE_HOURS`` defaults to the same value.
3. A logged-in cookie session whose ``iat`` is in the past beyond the
   idle window is rejected with 401 on the next /api/* request, and the
   session is cleared so the SPA must re-authenticate.

Audit reference: ``backend/app_factory.py`` lines 137-150 and 432-450.
"""
from __future__ import annotations

import datetime as _dt
import importlib
import sys
import time

import pytest

pytestmark = [pytest.mark.security]

_TOK = "z" * 64


def _gated_app(monkeypatch, tmp_path, *, idle_hours: int = 8):
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    monkeypatch.setenv("PERGEN_API_TOKENS", f"alice:{_TOK}")
    monkeypatch.setenv("PERGEN_AUTH_COOKIE_ENABLED", "1")
    monkeypatch.setenv("PERGEN_SESSION_LIFETIME_HOURS", str(idle_hours))
    monkeypatch.setenv("PERGEN_SESSION_IDLE_HOURS", str(idle_hours))
    monkeypatch.delenv("PERGEN_DEV_OPEN_API", raising=False)
    monkeypatch.delenv("PERGEN_API_TOKEN", raising=False)
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
    auth_mod = importlib.import_module("backend.blueprints.auth_bp")
    auth_mod._reset_throttle_for_tests()
    app = factory.create_app("development")
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    return app


def _login(client) -> str:
    r = client.post("/api/auth/login", json={"username": "alice", "password": _TOK})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["csrf"]


def test_permanent_session_lifetime_is_timedelta(monkeypatch, tmp_path) -> None:
    """Contract: PERMANENT_SESSION_LIFETIME is a ``timedelta`` (not int)."""
    app = _gated_app(monkeypatch, tmp_path, idle_hours=8)
    lifetime = app.config.get("PERMANENT_SESSION_LIFETIME")
    assert isinstance(lifetime, _dt.timedelta), (
        f"PERMANENT_SESSION_LIFETIME must be a datetime.timedelta, "
        f"got {type(lifetime).__name__}"
    )
    assert lifetime.total_seconds() == 8 * 3600


def test_session_lifetime_env_override_propagates(monkeypatch, tmp_path) -> None:
    """``PERGEN_SESSION_LIFETIME_HOURS=1`` shrinks the timedelta."""
    app = _gated_app(monkeypatch, tmp_path, idle_hours=1)
    assert app.config["PERMANENT_SESSION_LIFETIME"] == _dt.timedelta(hours=1)
    assert app.config["PERGEN_SESSION_IDLE_HOURS"] == 1


def test_whoami_returns_actor_after_login(monkeypatch, tmp_path) -> None:
    """Sanity: a fresh login → whoami sees the actor (proves cookie path)."""
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()
    _login(client)
    r = client.get("/api/auth/whoami")
    assert r.status_code == 200
    assert r.get_json()["actor"] == "alice"


def test_idle_session_is_rejected_and_cleared(monkeypatch, tmp_path) -> None:
    """Patching ``session["iat"]`` to the distant past → 401 + cleared session."""
    app = _gated_app(monkeypatch, tmp_path, idle_hours=1)
    client = app.test_client()
    _login(client)

    # Confirm authenticated GET works first.
    r = client.get("/api/inventory")
    assert r.status_code == 200, r.get_data(as_text=True)

    # Force the session to look ancient (well beyond the 1h idle window).
    with client.session_transaction() as sess:
        sess["iat"] = int(time.time()) - (2 * 3600)

    # Next request on a gated /api/* endpoint must be rejected.
    r = client.get("/api/inventory")
    assert r.status_code == 401, (
        f"expired session should yield 401, got {r.status_code}: "
        f"{r.get_data(as_text=True)!r}"
    )

    # Session must be cleared — whoami should now return actor=null.
    r = client.get("/api/auth/whoami")
    assert r.status_code == 200
    assert r.get_json().get("actor") is None, (
        "session.clear() should have wiped the actor key on idle expiry"
    )


def test_fresh_session_is_not_rejected(monkeypatch, tmp_path) -> None:
    """Counter-test: a session whose iat is *within* the window is accepted."""
    app = _gated_app(monkeypatch, tmp_path, idle_hours=8)
    client = app.test_client()
    _login(client)
    # iat should be effectively "now" — bump it to a few seconds ago.
    with client.session_transaction() as sess:
        sess["iat"] = int(time.time()) - 30
    r = client.get("/api/inventory")
    assert r.status_code == 200, r.get_data(as_text=True)
