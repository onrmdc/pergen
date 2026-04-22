"""
Phase-9 blueprint extraction tests.

Locks the wiring promise of phase 9:
* The factory registers ``inventory_service``, ``notepad_service``,
  ``report_service``, ``credential_service`` and ``device_service``
  into ``app.extensions``.
* The new ``inventory_bp`` and ``notepad_bp`` Blueprints are mounted
  with the legacy URL contract preserved.
* The legacy ``backend/app.py`` module no longer owns those routes
  (preventing accidental re-registration).
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


# --------------------------------------------------------------------------- #
# Service registration                                                        #
# --------------------------------------------------------------------------- #


def test_factory_registers_all_services(flask_app):
    ext = flask_app.extensions
    for key in (
        "inventory_service",
        "notepad_service",
        "report_service",
        "credential_service",
        "device_service",
    ):
        assert key in ext, f"missing service: {key}"


def test_inventory_blueprint_mounted(flask_app):
    assert "inventory" in flask_app.blueprints
    rules = {r.rule for r in flask_app.url_map.iter_rules()}
    for path in (
        "/api/fabrics",
        "/api/sites",
        "/api/halls",
        "/api/roles",
        "/api/devices",
        "/api/devices-arista",
        "/api/devices-by-tag",
        "/api/inventory",
    ):
        assert path in rules, f"route {path} not registered"


def test_notepad_blueprint_mounted(flask_app):
    assert "notepad" in flask_app.blueprints
    rules = {r.rule for r in flask_app.url_map.iter_rules()}
    assert "/api/notepad" in rules


def test_legacy_module_no_longer_owns_inventory_routes(flask_app):
    """The view function for /api/fabrics must come from the blueprint,
    not from the legacy ``backend.app`` module.
    """
    view = flask_app.view_functions["inventory.api_fabrics"]
    assert view.__module__ == "backend.blueprints.inventory_bp"


def test_legacy_module_no_longer_owns_notepad_routes(flask_app):
    view = flask_app.view_functions["notepad.api_notepad_get"]
    assert view.__module__ == "backend.blueprints.notepad_bp"


# --------------------------------------------------------------------------- #
# Blueprint behaviour parity                                                  #
# --------------------------------------------------------------------------- #


def test_inventory_bp_fabrics(client):
    body = client.get("/api/fabrics").get_json()
    assert body == {"fabrics": ["FAB1"]}


def test_inventory_bp_devices_arista(client):
    body = client.get("/api/devices-arista?fabric=FAB1&site=Mars").get_json()
    hostnames = {d["hostname"] for d in body["devices"]}
    assert "leaf-01" in hostnames


def test_notepad_bp_round_trip(client):
    initial = client.get("/api/notepad").get_json()
    assert "content" in initial and "line_editors" in initial

    payload = {"content": "first line\nsecond line", "user": "tester"}
    put = client.put("/api/notepad", json=payload)
    assert put.status_code == 200
    body = put.get_json()
    assert body["content"] == "first line\nsecond line"
    assert len(body["line_editors"]) == 2
    assert all(e == "tester" for e in body["line_editors"])

    fresh = client.get("/api/notepad").get_json()
    assert fresh == body


def test_notepad_bp_requires_content(client):
    r = client.put("/api/notepad", json={"user": "tester"})
    assert r.status_code == 400
    assert "content" in r.get_json()["error"].lower()
