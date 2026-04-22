"""
Phase-3 tests — inventory write routes (POST/PUT/DELETE/import) move
from ``backend/app.py`` into ``inventory_bp`` + ``InventoryService``.

Contract preserved verbatim from the legacy implementation:

* POST   /api/inventory/device   — add (uniqueness on hostname / ip)
* PUT    /api/inventory/device   — update via ``current_hostname``
* DELETE /api/inventory/device   — by hostname or ip query arg
* POST   /api/inventory/import   — bulk append, deduped, returns
                                    ``{ok, added, skipped[]}``

The blueprint test suite already exercises round-tripping; this file
adds the negative paths, validation paths, and the import contract,
then asserts that the *blueprint* (not the legacy ``backend.app``
module) owns the route — i.e. the migration actually happened.
"""
from __future__ import annotations

import json


# --------------------------------------------------------------------------- #
# Add (POST)                                                                   #
# --------------------------------------------------------------------------- #


def test_add_device_rejects_missing_body(client):
    r = client.post("/api/inventory/device", data="not-json", content_type="text/plain")
    assert r.status_code == 400


def test_add_device_rejects_empty_hostname(client):
    r = client.post("/api/inventory/device", json={"hostname": "  ", "ip": "10.0.0.99"})
    assert r.status_code == 400
    assert "hostname" in r.get_json()["error"].lower()


def test_add_device_rejects_duplicate_hostname(client):
    r = client.post(
        "/api/inventory/device",
        json={"hostname": "leaf-01", "ip": "10.99.99.99"},
    )
    assert r.status_code == 400
    assert "hostname already exists" in r.get_json()["error"].lower()


def test_add_device_rejects_duplicate_ip(client):
    r = client.post(
        "/api/inventory/device",
        json={"hostname": "newleaf", "ip": "10.0.0.1"},  # collides with leaf-01
    )
    assert r.status_code == 400
    assert "ip" in r.get_json()["error"].lower()


def test_add_device_succeeds_and_persists(client):
    payload = {
        "hostname": "leaf-77",
        "ip": "10.0.0.77",
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
    body = r.get_json()
    assert body["ok"] is True
    assert body["device"]["hostname"] == "leaf-77"
    inventory = client.get("/api/inventory").get_json()["inventory"]
    assert any(d["hostname"] == "leaf-77" for d in inventory)


# --------------------------------------------------------------------------- #
# Update (PUT)                                                                 #
# --------------------------------------------------------------------------- #


def test_update_device_requires_current_hostname(client):
    r = client.put("/api/inventory/device", json={"hostname": "x"})
    assert r.status_code == 400
    assert "current_hostname" in r.get_json()["error"]


def test_update_device_returns_404_when_not_found(client):
    r = client.put(
        "/api/inventory/device",
        json={"current_hostname": "does-not-exist", "hostname": "x", "ip": "1.1.1.1"},
    )
    assert r.status_code == 404


def test_update_device_rejects_rename_to_existing(client):
    # rename leaf-01 → leaf-02 (taken)
    r = client.put(
        "/api/inventory/device",
        json={
            "current_hostname": "leaf-01",
            "hostname": "leaf-02",
            "ip": "10.0.0.1",
        },
    )
    assert r.status_code == 400
    assert "hostname already exists" in r.get_json()["error"].lower()


def test_update_device_succeeds(client):
    r = client.put(
        "/api/inventory/device",
        json={
            "current_hostname": "leaf-01",
            "hostname": "leaf-01-renamed",
            "ip": "10.0.0.1",
            "fabric": "FAB1",
            "site": "Mars",
            "hall": "Hall-1",
            "vendor": "Arista",
            "model": "EOS",
            "role": "Leaf",
            "tag": "",
            "credential": "test-cred",
        },
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["device"]["hostname"] == "leaf-01-renamed"


# --------------------------------------------------------------------------- #
# Delete (DELETE)                                                              #
# --------------------------------------------------------------------------- #


def test_delete_device_requires_hostname_or_ip(client):
    r = client.delete("/api/inventory/device")
    assert r.status_code == 400


def test_delete_device_by_hostname(client):
    r = client.delete("/api/inventory/device?hostname=leaf-01")
    assert r.status_code == 200
    inv = client.get("/api/inventory").get_json()["inventory"]
    assert all(d["hostname"] != "leaf-01" for d in inv)


def test_delete_device_by_ip(client):
    r = client.delete("/api/inventory/device?ip=10.0.0.2")
    assert r.status_code == 200
    inv = client.get("/api/inventory").get_json()["inventory"]
    assert all(d["ip"] != "10.0.0.2" for d in inv)


def test_delete_device_returns_404_when_unknown(client):
    r = client.delete("/api/inventory/device?hostname=does-not-exist")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Import (POST /api/inventory/import)                                          #
# --------------------------------------------------------------------------- #


def test_import_requires_rows_array(client):
    r = client.post("/api/inventory/import", json={"rows": "not a list"})
    assert r.status_code == 400


def test_import_appends_new_skips_dupes(client):
    payload = {
        "rows": [
            {"hostname": "leaf-100", "ip": "10.0.0.100", "fabric": "FAB1", "site": "Mars"},
            {"hostname": "leaf-01", "ip": "10.10.10.10"},  # dup hostname
            {"hostname": "leaf-101", "ip": "10.0.0.1"},     # dup ip
            {"ip": "10.0.0.102"},                            # missing hostname
            {"hostname": "leaf-103", "ip": "10.0.0.103", "fabric": "FAB1", "site": "Mars"},
        ]
    }
    r = client.post("/api/inventory/import", json=payload)
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["added"] == 2
    assert len(body["skipped"]) == 3
    reasons = [s["reason"] for s in body["skipped"]]
    assert any("hostname already exists" in r for r in reasons)
    assert any("IP already exists" in r for r in reasons)
    assert any("missing hostname" in r for r in reasons)


# --------------------------------------------------------------------------- #
# Migration assertion — routes must live in the blueprint, not in app.py       #
# --------------------------------------------------------------------------- #


def test_inventory_write_routes_owned_by_inventory_blueprint(flask_app):
    """The four write routes must dispatch to functions defined in
    ``backend.blueprints.inventory_bp`` — not in ``backend.app``.
    """
    expected = {
        ("POST", "/api/inventory/device"),
        ("PUT", "/api/inventory/device"),
        ("DELETE", "/api/inventory/device"),
        ("POST", "/api/inventory/import"),
    }
    seen = set()
    for rule in flask_app.url_map.iter_rules():
        for method in rule.methods or ():
            if (method, rule.rule) in expected:
                view = flask_app.view_functions[rule.endpoint]
                assert view.__module__ == "backend.blueprints.inventory_bp", (
                    f"{method} {rule.rule} dispatches to {view.__module__} "
                    f"(expected backend.blueprints.inventory_bp)"
                )
                seen.add((method, rule.rule))
    assert seen == expected, f"missing routes: {expected - seen}"


def test_inventory_service_normalises_device_row():
    """The legacy ``_device_row`` helper now lives on InventoryService."""
    from backend.services.inventory_service import InventoryService

    norm = InventoryService.normalise_device_row(
        {"hostname": " leaf-x ", "ip": " 1.1.1.1 ", "credential": None}
    )
    assert norm is not None
    assert norm["hostname"] == "leaf-x"
    assert norm["ip"] == "1.1.1.1"
    assert norm["credential"] == ""
    # Every header column present
    from backend.inventory.loader import INVENTORY_HEADER

    assert set(norm.keys()) == set(INVENTORY_HEADER)


def test_inventory_service_normalise_returns_none_on_garbage():
    from backend.services.inventory_service import InventoryService

    assert InventoryService.normalise_device_row(None) is None
    assert InventoryService.normalise_device_row("not a dict") is None
    assert InventoryService.normalise_device_row([]) is None


def test_inventory_service_add_device_persists(tmp_path):
    """End-to-end service-level add against a real CSV."""
    from backend.repositories import InventoryRepository
    from backend.services.inventory_service import InventoryService

    csv = tmp_path / "inv.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n",
        encoding="utf-8",
    )
    svc = InventoryService(InventoryRepository(str(csv)))
    ok, payload = svc.add_device({"hostname": "leaf-1", "ip": "10.0.0.1"})
    assert ok is True
    assert payload["device"]["hostname"] == "leaf-1"
    # Persisted
    assert "leaf-1" in csv.read_text(encoding="utf-8")
    # Duplicate add returns ok=False
    ok2, err = svc.add_device({"hostname": "leaf-1", "ip": "10.0.0.2"})
    assert ok2 is False
    assert "exists" in err["error"].lower()
