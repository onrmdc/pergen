"""Wave-6 Phase F: session-fixation defence.

A pre-login session cookie value MUST NOT carry over into the
post-login session — otherwise an attacker who can plant a cookie
on a victim's browser before login can hijack the session
afterwards.

The test pre-populates a session by hitting an endpoint that may
issue a cookie (e.g. login attempt that lands in a session via
side effects), then logs in, then asserts the cookie value
issued by login is different from any pre-login value AND that
``session.clear()`` was called (so leftover keys are gone).
"""
from __future__ import annotations

import importlib
import sys

import pytest

pytestmark = [pytest.mark.security]

_TOK = "z" * 64


def _gated_app(monkeypatch, tmp_path):
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    monkeypatch.setenv("PERGEN_API_TOKENS", f"alice:{_TOK}")
    monkeypatch.delenv("PERGEN_DEV_OPEN_API", raising=False)
    monkeypatch.delenv("PERGEN_API_TOKEN", raising=False)
    monkeypatch.setenv("PERGEN_AUTH_COOKIE_ENABLED", "1")
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


def test_session_clear_called_on_login(monkeypatch, tmp_path) -> None:
    """A session pre-populated with junk before login must NOT survive into
    the post-login session.
    """
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    # Plant a session value pre-login (simulates an attacker who
    # convinced the victim's browser to accept a cookie they crafted).
    with client.session_transaction() as sess:
        sess["adversary_planted"] = "should_not_survive"
        sess["actor"] = "mallory"  # try to pre-claim an actor
        sess["csrf"] = "attacker-csrf"

    rlogin = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": _TOK},
    )
    assert rlogin.status_code == 200

    # After a successful login the session MUST contain only the keys
    # the auth blueprint set — no leftover attacker-planted keys.
    with client.session_transaction() as sess:
        assert sess.get("actor") == "alice", "post-login actor must be the legit one"
        assert sess.get("csrf") and sess["csrf"] != "attacker-csrf", (
            "post-login CSRF must be freshly issued, not the planted value"
        )
        assert "adversary_planted" not in sess, (
            "session.clear() was not called: adversary-planted key survived login"
        )


def test_csrf_token_rotates_on_relogin(monkeypatch, tmp_path) -> None:
    """Two consecutive logins must produce two distinct CSRF tokens."""
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    r1 = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": _TOK},
    )
    csrf1 = r1.get_json()["csrf"]

    r2 = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": _TOK},
    )
    csrf2 = r2.get_json()["csrf"]

    assert csrf1 != csrf2, "CSRF token must rotate on every fresh login"
    assert len(csrf1) >= 32 and len(csrf2) >= 32
