"""
Phase-6 tests — credential routes move from ``backend/app.py`` to
``backend/blueprints/credentials_bp.py``.

The blueprint preserves the legacy contract verbatim (keyed off the
``backend.credential_store`` module which the rest of the codebase
already uses for round-tripping). Migration to the new
``CredentialService`` is out of scope for this phase — that's a
separate, riskier swap deferred until after the decomposition is done.
"""
from __future__ import annotations

import pytest as _pytest_for_marker  # noqa: F401

pytestmark = [_pytest_for_marker.mark.integration]


def test_credentials_list_returns_array(client):
    r = client.get("/api/credentials")
    assert r.status_code == 200
    body = r.get_json()
    assert isinstance(body.get("credentials"), list)


def test_credentials_create_requires_name(client):
    r = client.post("/api/credentials", json={"method": "api_key", "api_key": "x"})
    assert r.status_code == 400
    assert "name" in r.get_json()["error"].lower()


def test_credentials_create_validates_method(client):
    r = client.post("/api/credentials", json={"name": "test", "method": "wrong"})
    assert r.status_code == 400
    assert "method" in r.get_json()["error"].lower()


def test_credentials_create_api_key_round_trip(client):
    r = client.post(
        "/api/credentials",
        json={"name": "phase6-cred", "method": "api_key", "api_key": "secret-token"},
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    listing = client.get("/api/credentials").get_json()["credentials"]
    assert any((c.get("name") or c) == "phase6-cred" for c in listing)


def test_credentials_create_basic_round_trip(client):
    r = client.post(
        "/api/credentials",
        json={
            "name": "phase6-basic",
            "method": "basic",
            "username": "u",
            "password": "p",
        },
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_credentials_delete_returns_404_for_unknown(client):
    r = client.delete("/api/credentials/__no_such_credential__")
    assert r.status_code == 404


def test_credentials_delete_succeeds(client):
    client.post(
        "/api/credentials",
        json={"name": "phase6-del", "method": "api_key", "api_key": "x"},
    )
    r = client.delete("/api/credentials/phase6-del")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_credentials_validate_returns_404_for_unknown(client):
    r = client.post("/api/credentials/__no_such__/validate")
    assert r.status_code == 404
    assert r.get_json()["ok"] is False


def test_credentials_validate_returns_no_device_when_unused(client):
    # Create a cred no inventory device uses
    client.post(
        "/api/credentials",
        json={"name": "orphan-cred", "method": "api_key", "api_key": "x"},
    )
    r = client.post("/api/credentials/orphan-cred/validate")
    # Expected: 200 ok=False device=None reason=no inventory device uses it
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is False
    assert "no device" in body["error"].lower()


def test_credentials_routes_owned_by_credentials_blueprint(flask_app):
    expected = {
        ("GET", "/api/credentials"),
        ("POST", "/api/credentials"),
        ("DELETE", "/api/credentials/<name>"),
        ("POST", "/api/credentials/<name>/validate"),
    }
    seen = set()
    for rule in flask_app.url_map.iter_rules():
        for method in rule.methods or ():
            if (method, rule.rule) in expected:
                view = flask_app.view_functions[rule.endpoint]
                assert view.__module__ == "backend.blueprints.credentials_bp", (
                    f"{method} {rule.rule} dispatches to {view.__module__}"
                )
                seen.add((method, rule.rule))
    assert seen == expected, f"missing: {expected - seen}"
