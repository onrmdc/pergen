"""
Phase-8 tests — find-leaf + NAT-lookup routes move from
``backend/app.py`` to ``backend/blueprints/network_lookup_bp.py``.

These are thin pass-throughs to the existing ``find_leaf`` and
``nat_lookup`` modules — the contract is preserved verbatim including
the soft-failure exception envelope each route returns on error.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest as _pytest_for_marker  # noqa: F401

pytestmark = [_pytest_for_marker.mark.integration]


def test_find_leaf_requires_ip(client):
    r = client.post("/api/find-leaf", json={})
    assert r.status_code == 400
    assert "ip" in r.get_json()["error"].lower()


def test_find_leaf_returns_envelope_on_exception(client):
    """Any underlying exception is caught and returned as a 200 envelope.

    Audit H-5: the error message must NOT echo the raw exception
    (information disclosure). Server-side logs hold the detail.
    """
    sentinel = "internal-detail-must-not-leak-12345"
    with patch(
        "backend.find_leaf.find_leaf", side_effect=RuntimeError(sentinel)
    ):
        r = client.post("/api/find-leaf", json={"ip": "10.0.0.1"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["found"] is False
    err = body["error"]
    assert sentinel not in err, "raw exception leaked into error envelope"
    assert "find-leaf" in err.lower()
    assert body["checked_devices"] == []


def test_find_leaf_forwards_args(client):
    with patch(
        "backend.find_leaf.find_leaf", return_value={"found": True, "leaf_ip": "1.2.3.4"}
    ) as m:
        r = client.post("/api/find-leaf", json={"ip": "10.0.0.99"})
    assert r.status_code == 200
    assert r.get_json()["found"] is True
    args, kwargs = m.call_args
    assert args[0] == "10.0.0.99"
    assert "inventory_path" in kwargs


def test_find_leaf_check_device_requires_ip(client):
    r = client.post("/api/find-leaf-check-device", json={"hostname": "SW1"})
    assert r.status_code == 400


def test_find_leaf_check_device_requires_identifier(client):
    r = client.post("/api/find-leaf-check-device", json={"ip": "10.0.0.1"})
    assert r.status_code == 400


def test_find_leaf_check_device_accepts_device_ip_alias(client):
    with patch(
        "backend.find_leaf.find_leaf_check_device",
        return_value={"found": True, "leaf_hostname": "leaf-1"},
    ) as m:
        r = client.post(
            "/api/find-leaf-check-device",
            json={"ip": "10.0.0.99", "device_ip": "192.168.0.1"},
        )
    assert r.status_code == 200
    args, _ = m.call_args
    assert args[1] == "192.168.0.1"  # identifier falls back to device_ip


def test_nat_lookup_requires_src_ip(client):
    r = client.post("/api/nat-lookup", json={})
    assert r.status_code == 400


def test_nat_lookup_defaults_dest_to_google_dns(client):
    with patch(
        "backend.nat_lookup.nat_lookup",
        return_value={"ok": True, "rule_name": "any"},
    ) as m:
        client.post("/api/nat-lookup", json={"src_ip": "10.0.0.99"})
    args, _ = m.call_args
    assert args[1] == "8.8.8.8"


def test_nat_lookup_returns_envelope_on_exception(client):
    """Audit H-5: error envelope is generic; raw exception stays server-side."""
    sentinel = "api-down-sentinel-abcdef"
    with patch(
        "backend.nat_lookup.nat_lookup", side_effect=RuntimeError(sentinel)
    ):
        r = client.post("/api/nat-lookup", json={"src_ip": "10.0.0.1"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is False
    assert sentinel not in body["error"], "raw exception leaked into envelope"
    assert "nat-lookup" in body["error"].lower()


def test_network_lookup_routes_owned_by_blueprint(flask_app):
    expected = {
        ("POST", "/api/find-leaf"),
        ("POST", "/api/find-leaf-check-device"),
        ("POST", "/api/nat-lookup"),
    }
    seen = set()
    for rule in flask_app.url_map.iter_rules():
        for method in rule.methods or ():
            if (method, rule.rule) in expected:
                view = flask_app.view_functions[rule.endpoint]
                assert view.__module__ == "backend.blueprints.network_lookup_bp", (
                    f"{method} {rule.rule} dispatches to {view.__module__}"
                )
                seen.add((method, rule.rule))
    assert seen == expected, f"missing: {expected - seen}"
