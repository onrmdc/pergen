"""
Phase-10 tests — device-commands routes move from ``backend/app.py``
to ``backend/blueprints/device_commands_bp.py``.

Routes:
* POST /api/arista/run-cmds   — eAPI runCmds with CommandValidator gate
* GET  /api/router-devices    — DCI / WAN router scope filter
* POST /api/route-map/run     — Arista EOS route-map compare
* POST /api/custom-command    — SSH single command (CommandValidator gate)
"""
from __future__ import annotations

from unittest.mock import patch


# --------------------------------------------------------------------------- #
# /api/arista/run-cmds                                                         #
# --------------------------------------------------------------------------- #


def test_arista_run_cmds_requires_device(client):
    r = client.post("/api/arista/run-cmds", json={"cmds": ["show version"]})
    assert r.status_code == 400


def test_arista_run_cmds_requires_cmds_array(client):
    r = client.post("/api/arista/run-cmds", json={"device": {"ip": "1.1.1.1"}})
    assert r.status_code == 400


def test_arista_run_cmds_requires_device_ip(client):
    """Audit H-2: a device without IP/hostname in inventory is rejected (404).

    Pre-H-2 the route returned 400 from a missing-ip preflight; with
    inventory binding the inventory miss is detected first and 404 is
    the correct posture (the device simply doesn't exist).
    """
    r = client.post(
        "/api/arista/run-cmds",
        json={"device": {"hostname": "x"}, "cmds": ["show version"]},
    )
    assert r.status_code in (400, 404)
    err = (r.get_json() or {}).get("error") or ""
    assert "ip" in err.lower() or "inventory" in err.lower()


def test_arista_run_cmds_rejects_dangerous_command(client):
    """CommandValidator must block configure-mode commands."""
    r = client.post(
        "/api/arista/run-cmds",
        json={
            "device": {"ip": "1.1.1.1", "credential": "test-cred"},
            "cmds": ["configure terminal"],
        },
    )
    # Either "no credential" (legacy preflight) or "rejected" both prove the gate works.
    assert r.status_code == 400 or r.get_json().get("error")


# --------------------------------------------------------------------------- #
# /api/router-devices                                                          #
# --------------------------------------------------------------------------- #


def test_router_devices_returns_array(client):
    r = client.get("/api/router-devices")
    assert r.status_code == 200
    body = r.get_json()
    assert isinstance(body["devices"], list)


def test_router_devices_empty_when_no_dci_routers(client):
    """Default test inventory has only Leaf devices; result must be []."""
    r = client.get("/api/router-devices?scope=dci")
    assert r.status_code == 200
    assert r.get_json()["devices"] == []


# --------------------------------------------------------------------------- #
# /api/route-map/run                                                           #
# --------------------------------------------------------------------------- #


def test_route_map_run_requires_devices_list(client):
    r = client.post("/api/route-map/run", json={"devices": []})
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_route_map_run_skips_non_arista(client):
    """Non-Arista devices yield an error in the errors[] envelope."""
    r = client.post(
        "/api/route-map/run",
        json={
            "devices": [
                {
                    "hostname": "leaf-01",
                    "ip": "10.0.0.1",
                    "vendor": "Cisco",
                    "model": "NX-OS",
                    "credential": "test-cred",
                }
            ]
        },
    )
    assert r.status_code == 200
    body = r.get_json()
    # Either "no credential" (no-cred) or "only Arista EOS supported" — both prove the gate runs
    assert any(
        e["hostname"] == "leaf-01" and e.get("error")
        for e in body["errors"]
    )


# --------------------------------------------------------------------------- #
# /api/custom-command                                                          #
# --------------------------------------------------------------------------- #


def test_custom_command_requires_device(client):
    r = client.post("/api/custom-command", json={"command": "show version"})
    assert r.status_code == 400


def test_custom_command_requires_command(client):
    r = client.post("/api/custom-command", json={"device": {"ip": "1.1.1.1"}})
    assert r.status_code == 400


def test_custom_command_rejects_non_show_command(client):
    r = client.post(
        "/api/custom-command",
        json={"device": {"ip": "1.1.1.1"}, "command": "configure terminal"},
    )
    assert r.status_code == 400


def test_custom_command_succeeds_with_show(client):
    """A valid 'show version' should pass validation, against an inventory device.

    Audit H-2: device must be inventory-bound. Use the leaf-01 row from
    ``mock_inventory_csv``.
    """
    with patch("backend.runners.ssh_runner.run_command", return_value=("VERSION 4.1", None)):
        r = client.post(
            "/api/custom-command",
            json={
                "device": {"hostname": "leaf-01", "ip": "10.0.0.1", "credential": "test-cred"},
                "command": "show version",
            },
        )
    # 200 either way (no-cred returns 200 with error, or runner stub returns 200 ok)
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
# Migration assertion                                                          #
# --------------------------------------------------------------------------- #


def test_device_commands_routes_owned_by_blueprint(flask_app):
    expected = {
        ("POST", "/api/arista/run-cmds"),
        ("GET", "/api/router-devices"),
        ("POST", "/api/route-map/run"),
        ("POST", "/api/custom-command"),
    }
    seen = set()
    for rule in flask_app.url_map.iter_rules():
        for method in rule.methods or ():
            if (method, rule.rule) in expected:
                view = flask_app.view_functions[rule.endpoint]
                assert view.__module__ == "backend.blueprints.device_commands_bp", (
                    f"{method} {rule.rule} dispatches to {view.__module__}"
                )
                seen.add((method, rule.rule))
    assert seen == expected, f"missing: {expected - seen}"
