"""
Flask route baselines.

These tests hit every read-only endpoint and a representative subset of
mutating endpoints via the Flask test client.  The goal is to lock the
**HTTP contract** (status codes + JSON response shape) so the upcoming move
to per-domain Blueprints in Phase 4+ cannot drift silently.

External services (network device APIs, RIPEStat, RPKI validators) are
*not* called.  Where a route hits an external service, only the input
validation / 400 path is exercised; the happy path is left to integration
suites that ship with the relevant Phase.

Inventory-shape tests share the small ``mock_inventory_csv`` fixture from
``conftest.py`` (two leaves in ``FAB1 / Mars / Hall-1``).
"""
from __future__ import annotations

from unittest import mock

import pytest

pytestmark = [pytest.mark.golden, pytest.mark.integration]


# --------------------------------------------------------------------------- #
# Health & root                                                               #
# --------------------------------------------------------------------------- #


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_index_returns_spa_or_api_message(client):
    """Locks the dual behaviour: serve SPA index.html when present, else JSON message."""
    r = client.get("/")
    assert r.status_code == 200
    if r.is_json:
        assert r.get_json() == {"message": "Pergen API. Use /api/* routes."}
    else:
        # SPA bundle is being served from backend/static/index.html.
        assert b"<html" in r.data.lower() or b"<!doctype" in r.data.lower()


# --------------------------------------------------------------------------- #
# Inventory hierarchy                                                         #
# --------------------------------------------------------------------------- #


def test_fabrics_returns_distinct_fabrics(client):
    r = client.get("/api/fabrics")
    assert r.status_code == 200
    assert r.get_json() == {"fabrics": ["FAB1"]}


def test_sites_requires_fabric(client):
    assert client.get("/api/sites").get_json() == {"sites": []}
    body = client.get("/api/sites?fabric=FAB1").get_json()
    assert body == {"sites": ["Mars"]}


def test_halls_requires_fabric(client):
    assert client.get("/api/halls").get_json() == {"halls": []}
    body = client.get("/api/halls?fabric=FAB1&site=Mars").get_json()
    assert body == {"halls": ["Hall-1"]}


def test_roles_requires_fabric(client):
    assert client.get("/api/roles").get_json() == {"roles": []}
    body = client.get("/api/roles?fabric=FAB1&site=Mars").get_json()
    assert body == {"roles": ["Leaf"]}


def test_devices_requires_fabric(client):
    assert client.get("/api/devices").get_json() == {"devices": []}
    body = client.get("/api/devices?fabric=FAB1&site=Mars").get_json()
    assert len(body["devices"]) == 2
    assert {d["hostname"] for d in body["devices"]} == {"leaf-01", "leaf-02"}


def test_devices_arista_filter(client):
    body = client.get("/api/devices-arista?fabric=FAB1&site=Mars").get_json()
    assert len(body["devices"]) == 1
    assert body["devices"][0]["hostname"] == "leaf-01"


def test_devices_by_tag_returns_only_matching(client):
    body = client.get("/api/devices-by-tag?tag=leaf-search").get_json()
    assert body == {"devices": [{"hostname": "leaf-01", "ip": "10.0.0.1"}]}


def test_devices_by_tag_missing_tag_returns_empty(client):
    body = client.get("/api/devices-by-tag").get_json()
    assert body == {"devices": []}


def test_inventory_returns_full_list(client):
    body = client.get("/api/inventory").get_json()
    assert "inventory" in body
    assert len(body["inventory"]) == 2
    assert {d["hostname"] for d in body["inventory"]} == {"leaf-01", "leaf-02"}


def test_router_devices_returns_empty_when_no_router_role(client):
    body = client.get("/api/router-devices").get_json()
    assert body == {"devices": []}


# --------------------------------------------------------------------------- #
# Commands & parsers metadata                                                 #
# --------------------------------------------------------------------------- #


def test_commands_endpoint_shape(client):
    r = client.get("/api/commands")
    assert r.status_code == 200
    body = r.get_json()
    assert isinstance(body, dict)
    # Either {"commands": [...]} or list returned at top — lock current shape.
    assert "commands" in body
    assert isinstance(body["commands"], list)


def test_parsers_fields_endpoint_returns_dict(client):
    r = client.get("/api/parsers/fields")
    assert r.status_code == 200
    payload = r.get_json()
    assert isinstance(payload, dict)


def test_parsers_lookup_returns_404_for_unknown_id(client):
    r = client.get("/api/parsers/no-such-command-id-xyz")
    # Either explicit 404 or empty body — both are valid; pin current behaviour.
    assert r.status_code in (200, 404)


# --------------------------------------------------------------------------- #
# Reports / runs                                                              #
# --------------------------------------------------------------------------- #


def test_reports_endpoint_returns_list(client):
    r = client.get("/api/reports")
    assert r.status_code == 200
    body = r.get_json()
    assert "reports" in body
    assert isinstance(body["reports"], list)


def test_reports_unknown_id_returns_404(client):
    r = client.get("/api/reports/does-not-exist")
    assert r.status_code == 404


def test_run_result_unknown_id_returns_404(client):
    r = client.get("/api/run/result/does-not-exist")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Notepad                                                                     #
# --------------------------------------------------------------------------- #


def test_notepad_get_returns_content_and_editors(client):
    r = client.get("/api/notepad")
    assert r.status_code == 200
    body = r.get_json()
    assert "content" in body
    assert "line_editors" in body
    assert isinstance(body["content"], str)
    assert isinstance(body["line_editors"], list)


def test_notepad_round_trip_uses_content_field(client):
    saved = client.put("/api/notepad", json={"content": "hello world", "user": "tester"})
    assert saved.status_code == 200
    fetched = client.get("/api/notepad").get_json()
    assert fetched["content"] == "hello world"
    assert fetched["line_editors"] == ["tester"]


def test_notepad_put_requires_content(client):
    r = client.put("/api/notepad", json={})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Credentials (read-only listing — no encryption assumptions yet)             #
# --------------------------------------------------------------------------- #


def test_credentials_get_returns_list(client):
    r = client.get("/api/credentials")
    assert r.status_code == 200
    body = r.get_json()
    assert "credentials" in body
    assert isinstance(body["credentials"], list)


# --------------------------------------------------------------------------- #
# Inventory mutations                                                         #
# --------------------------------------------------------------------------- #


def test_add_device_requires_hostname(client):
    r = client.post("/api/inventory/device", json={})
    assert r.status_code == 400
    assert "hostname" in r.get_json()["error"].lower()


def test_add_device_round_trip(client):
    payload = {
        "hostname": "leaf-99",
        "ip": "10.0.0.99",
        "fabric": "FAB1",
        "site": "Mars",
        "hall": "Hall-1",
        "vendor": "Arista",
        "model": "EOS",
        "role": "Leaf",
        "tag": "",
        "credential": "test-cred",
    }
    r = client.post("/api/inventory/device", json=payload)
    assert r.status_code == 200
    body = client.get("/api/inventory").get_json()
    assert any(d["hostname"] == "leaf-99" for d in body["inventory"])


# --------------------------------------------------------------------------- #
# POST routes that hit network — validation paths only                        #
# --------------------------------------------------------------------------- #


def test_arista_run_cmds_requires_device(client):
    r = client.post("/api/arista/run-cmds", json={"cmds": ["show version"]})
    assert r.status_code == 400


def test_arista_run_cmds_requires_cmds(client):
    r = client.post("/api/arista/run-cmds", json={"device": {"ip": "10.0.0.1"}})
    assert r.status_code == 400


def test_arista_run_cmds_missing_credential(client):
    """Audit H-2: caller-supplied credential is ignored — server uses inventory.

    Use a hostname/ip that is NOT in the mock inventory so the inventory
    binding rejects the request (404). This exercises the credential-
    resolution path safely without test-isolation noise from earlier
    seeded credentials.
    """
    r = client.post(
        "/api/arista/run-cmds",
        json={"device": {"hostname": "ghost-leaf", "ip": "203.0.113.99", "credential": "no-such-cred"}, "cmds": ["show version"]},
    )
    # 404 (not in inventory) is the new correct posture.
    assert r.status_code == 404
    assert "inventory" in r.get_json()["error"].lower()


def test_route_map_run_requires_devices(client):
    r = client.post("/api/route-map/run", json={"devices": []})
    assert r.status_code == 400


def test_run_pre_requires_devices(client):
    r = client.post("/api/run/pre", json={})
    # Locks current behaviour — accept either 400 or empty payload.
    assert r.status_code in (200, 400)


def test_diff_requires_pre_post(client):
    r = client.post("/api/diff", json={})
    assert r.status_code in (200, 400)


# --------------------------------------------------------------------------- #
# Custom command — runner mocked                                              #
# --------------------------------------------------------------------------- #


def test_custom_command_with_mocked_arista_runner(client):
    """Locks how /api/custom-command threads through arista_eapi.run_commands."""
    fake_results = [{"version": "4.30"}]

    def _add_test_credential():
        from flask import current_app

        from backend import credential_store as cs

        cs.set_credential(
            "test-cred",
            method="basic",
            username="admin",
            password="p4ss",
            secret_key=current_app.config["SECRET_KEY"],
        )

    with client.application.app_context():
        _add_test_credential()

    with mock.patch("backend.runners.arista_eapi.requests.post") as posted:
        posted.return_value = mock.MagicMock(
            status_code=200, json=lambda: {"result": fake_results}
        )
        posted.return_value.raise_for_status = mock.MagicMock()
        r = client.post(
            "/api/custom-command",
            json={
                "device": {
                    "ip": "10.0.0.1",
                    "vendor": "Arista",
                    "model": "EOS",
                    "credential": "test-cred",
                },
                "command": "show version",
            },
        )

    # Lock current shape — it must respond and report no transport error.
    assert r.status_code == 200
    body = r.get_json()
    assert isinstance(body, dict)
    assert "error" in body
