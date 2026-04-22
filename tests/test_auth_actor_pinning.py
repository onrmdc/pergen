"""Wave-6 Phase F: ``g.actor`` must be populated identically under
both auth paths.

Existing wave-3 actor-scoping code (RunStateStore, ReportService)
relies on ``flask.g.actor`` being set to the operator's name. The
dual-path gate added in Phase F MUST honour that contract on the
cookie path too — otherwise per-actor isolation silently regresses.

This test inserts a tiny inspection blueprint that echoes
``g.actor`` so we can verify both paths surface the same value.
"""
from __future__ import annotations

import importlib
import sys

import pytest
from flask import Blueprint, g, jsonify

pytestmark = [pytest.mark.security]

_ALICE_TOK = "a" * 64
_BOB_TOK = "b" * 64

# Inspector blueprint — defined once at module load so the import order
# in `_gated_app` doesn't recreate it.
_actor_probe = Blueprint("_actor_probe", __name__)


@_actor_probe.route("/api/_actor_probe", methods=["GET"])
def _actor_probe_get():
    return jsonify({"actor": getattr(g, "actor", None)})


def _gated_app(monkeypatch, tmp_path):
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    monkeypatch.setenv(
        "PERGEN_API_TOKENS",
        f"alice:{_ALICE_TOK},bob:{_BOB_TOK}",
    )
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
    if "_actor_probe" not in app.blueprints:
        app.register_blueprint(_actor_probe)
    return app


def test_actor_pinned_under_token_header_path(monkeypatch, tmp_path) -> None:
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    r = client.get("/api/_actor_probe", headers={"X-API-Token": _BOB_TOK})
    assert r.status_code == 200
    assert r.get_json()["actor"] == "bob"


def test_actor_pinned_under_cookie_path(monkeypatch, tmp_path) -> None:
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    rlogin = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": _ALICE_TOK},
    )
    assert rlogin.status_code == 200

    r = client.get("/api/_actor_probe")
    assert r.status_code == 200
    assert r.get_json()["actor"] == "alice", (
        "cookie-path auth must pin g.actor identically to the token-header path "
        "(otherwise wave-3 actor scoping silently regresses)"
    )


def test_token_header_takes_precedence_over_session(monkeypatch, tmp_path) -> None:
    """If a request carries BOTH a session cookie (alice) AND a token
    header (bob), the token header wins — it's the explicit machine
    credential and must not be silently overridden by an idle browser
    session that happens to share the cookie jar.
    """
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    # Establish alice's cookie session.
    client.post(
        "/api/auth/login",
        json={"username": "alice", "password": _ALICE_TOK},
    )
    # Now hit the probe with bob's token header — the token header is
    # checked first, so g.actor must be 'bob'.
    r = client.get("/api/_actor_probe", headers={"X-API-Token": _BOB_TOK})
    assert r.status_code == 200
    assert r.get_json()["actor"] == "bob"
