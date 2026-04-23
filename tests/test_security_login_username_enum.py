"""H-6 — login audit log must not echo unknown usernames verbatim.

Audit (Security review H-6): ``backend/blueprints/auth_bp.py`` line ~213
now substitutes ``<unknown>`` for the actor field in the audit log when
the supplied username is not in the configured token snapshot. Without
this scrub, an attacker who can read the audit log (or correlate the
*volume* of audit lines per username) confirms which usernames are
valid → halves the work of credential stuffing / spraying.

This module pins the contract:

  * unknown username → ``actor=<unknown>``
  * known username + wrong password → ``actor=<username>``
  * both paths still return HTTP 401 (no functional change for the
    remote caller — only the server-side audit line differs).

Audit reference: ``backend/blueprints/auth_bp.py`` lines 208-220.
"""
from __future__ import annotations

import importlib
import logging
import sys

import pytest

pytestmark = [pytest.mark.security]

_TOK = "k" * 64


def _gated_app(monkeypatch, tmp_path):
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    monkeypatch.setenv("PERGEN_API_TOKENS", f"alice:{_TOK}")
    monkeypatch.setenv("PERGEN_AUTH_COOKIE_ENABLED", "1")
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
    # Ensure the audit logger emits at WARNING (auth.login.fail uses .warning).
    logging.getLogger("app.audit").setLevel(logging.DEBUG)
    return app


def _attach_caplog(caplog) -> None:
    """Re-attach pytest's caplog handler to root.

    ``LoggingConfig.configure`` strips every handler off the root logger
    when the app is built (so successive ``create_app`` calls don't
    duplicate output). pytest's ``caplog`` fixture installs its handler
    on root *before* the test body runs, so it gets evicted along with
    the others. Re-attach it explicitly so we can capture audit lines.
    """
    root = logging.getLogger()
    if caplog.handler not in root.handlers:
        root.addHandler(caplog.handler)


def test_unknown_username_logs_actor_unknown(monkeypatch, tmp_path, caplog) -> None:
    """An unknown username must NOT appear verbatim in the audit log."""
    app = _gated_app(monkeypatch, tmp_path)
    _attach_caplog(caplog)
    client = app.test_client()

    caplog.set_level(logging.DEBUG, logger="app.audit")
    r = client.post(
        "/api/auth/login", json={"username": "bob", "password": "wrong"}
    )
    assert r.status_code == 401, r.get_data(as_text=True)

    fail_records = [
        rec for rec in caplog.records
        if rec.name == "app.audit" and "auth.login.fail" in rec.getMessage()
    ]
    assert fail_records, (
        "expected one app.audit auth.login.fail record; got none. "
        f"All records: {[(r.name, r.getMessage()) for r in caplog.records]!r}"
    )
    msg = fail_records[-1].getMessage()
    assert "actor=<unknown>" in msg, (
        f"unknown username must be redacted to <unknown> in audit line; "
        f"got {msg!r}"
    )
    assert "actor=bob" not in msg, (
        f"unknown username must NOT appear verbatim in audit line; "
        f"got {msg!r}"
    )


def test_known_username_wrong_password_logs_real_actor(
    monkeypatch, tmp_path, caplog
) -> None:
    """A known username with wrong password is still logged verbatim."""
    app = _gated_app(monkeypatch, tmp_path)
    _attach_caplog(caplog)
    client = app.test_client()

    caplog.set_level(logging.DEBUG, logger="app.audit")
    r = client.post(
        "/api/auth/login", json={"username": "alice", "password": "wrong"}
    )
    assert r.status_code == 401, r.get_data(as_text=True)

    fail_records = [
        rec for rec in caplog.records
        if rec.name == "app.audit" and "auth.login.fail" in rec.getMessage()
    ]
    assert fail_records, (
        "expected an app.audit auth.login.fail record; got none"
    )
    msg = fail_records[-1].getMessage()
    assert "actor=alice" in msg, (
        f"known actor must appear in audit line so forensic correlation "
        f"works; got {msg!r}"
    )
    assert "<unknown>" not in msg, (
        f"known actor must not be incorrectly redacted to <unknown>; "
        f"got {msg!r}"
    )


def test_unknown_username_returns_401_same_status_as_known(
    monkeypatch, tmp_path
) -> None:
    """Status code parity: both unknown and known-but-wrong return 401.

    Defence in depth — the audit-line redaction is one layer; the HTTP
    response shape is the other. If the caller could distinguish 401 vs
    404 (or any other variant) by username, the audit redaction would
    be useless against an unauthenticated attacker.
    """
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    r_unknown = client.post(
        "/api/auth/login", json={"username": "ghost", "password": "wrong"}
    )
    r_known = client.post(
        "/api/auth/login", json={"username": "alice", "password": "wrong"}
    )
    assert r_unknown.status_code == 401
    assert r_known.status_code == 401
    # Body shape parity too — both should return {"error": "invalid credentials"}.
    assert r_unknown.get_json() == r_known.get_json()
