"""
Phase-9 tests — transceiver routes move from ``backend/app.py`` to
``backend/blueprints/transceiver_bp.py`` + ``TransceiverService``.

This is the highest-risk single phase (the original ``api_transceiver``
function is a 110-line orchestration that runs four command groups per
device and merges the results). The contract is preserved verbatim and
the merge logic now sits behind a single
``TransceiverService.collect_rows()`` entry point that is unit-testable
without spinning up a real Flask app.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest as _pytest_for_marker  # noqa: F401

pytestmark = [_pytest_for_marker.mark.integration]


# --------------------------------------------------------------------------- #
# Validation paths (no real device traffic)                                    #
# --------------------------------------------------------------------------- #


def test_transceiver_rejects_non_list_devices(client):
    r = client.post("/api/transceiver", json={"devices": "x"})
    assert r.status_code == 400


def test_transceiver_returns_empty_when_no_devices(client):
    r = client.post("/api/transceiver", json={"devices": []})
    assert r.status_code == 200
    body = r.get_json()
    assert body["rows"] == []
    assert body["errors"] == []
    assert body["interface_status_trace"] == []


def test_transceiver_recover_requires_device(client):
    r = client.post("/api/transceiver/recover", json={})
    assert r.status_code == 400
    assert "device" in r.get_json()["error"].lower()


def test_transceiver_recover_requires_interfaces_array(client):
    r = client.post(
        "/api/transceiver/recover",
        json={"device": {"ip": "1.1.1.1"}, "interfaces": "Ethernet1"},
    )
    assert r.status_code == 400


def test_transceiver_clear_counters_requires_device_object(client):
    r = client.post("/api/transceiver/clear-counters", json={"device": "not-a-dict"})
    assert r.status_code == 400


def test_transceiver_clear_counters_requires_interface_string(client):
    r = client.post(
        "/api/transceiver/clear-counters",
        json={"device": {"ip": "1.1.1.1"}, "interface": []},
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Service-layer unit tests for the collect_rows orchestration                  #
# --------------------------------------------------------------------------- #


def test_transceiver_service_collect_rows_returns_empty_for_no_devices():
    from backend.services.transceiver_service import TransceiverService

    svc = TransceiverService(secret_key="x", credential_store=None)
    rows, errors, trace = svc.collect_rows([])
    assert rows == []
    assert errors == []
    assert trace == []


def test_transceiver_service_collect_rows_propagates_run_errors():
    """When the transceiver run errors, the device shows up in errors[]."""
    from backend.services.transceiver_service import TransceiverService

    svc = TransceiverService(secret_key="x", credential_store=None)

    def boom(*_a, **_k):
        return {"error": "credential missing", "hostname": "leaf-1"}

    with patch(
        "backend.services.transceiver_service.run_device_commands",
        side_effect=boom,
    ):
        rows, errors, _trace = svc.collect_rows(
            [{"hostname": "leaf-1", "ip": "10.0.0.1"}]
        )
    assert rows == []
    assert errors == [{"hostname": "leaf-1", "error": "credential missing"}]


def test_transceiver_service_collect_rows_emits_no_data_message_when_empty():
    """A successful run with no transceiver_rows yields the 'no transceiver data' note."""
    from backend.services.transceiver_service import TransceiverService

    svc = TransceiverService(secret_key="x", credential_store=None)

    def stub(*_a, **k):
        cf = k.get("command_id_filter")
        # transceiver run: empty
        if cf == "transceiver":
            return {"hostname": "leaf-1", "parsed_flat": {"transceiver_rows": []}}
        # status / desc / mtu: empty
        return {"hostname": "leaf-1", "parsed_flat": {}}

    with patch(
        "backend.services.transceiver_service.run_device_commands",
        side_effect=stub,
    ):
        rows, errors, trace = svc.collect_rows(
            [{"hostname": "leaf-1", "ip": "10.0.0.1"}]
        )
    assert rows == []
    assert errors == [
        {"hostname": "leaf-1", "error": "no transceiver data (unsupported or no optics)"}
    ]
    assert len(trace) == 1


def test_transceiver_service_collect_rows_merges_status_into_row():
    """Happy path: transceiver row + status entry → merged output row."""
    from backend.services.transceiver_service import TransceiverService

    svc = TransceiverService(secret_key="x", credential_store=None)

    def stub(*_a, **k):
        cf = k.get("command_id_filter")
        if cf == "transceiver":
            return {
                "hostname": "leaf-1",
                "ip": "10.0.0.1",
                "parsed_flat": {
                    "transceiver_rows": [
                        {
                            "interface": "Ethernet1",
                            "serial": "SN1",
                            "type": "10G",
                            "manufacturer": "ACME",
                            "temp": "30",
                            "tx_power": "-2",
                            "rx_power": "-3",
                        }
                    ]
                },
            }
        if cf == "interface_status":
            return {
                "parsed_flat": {
                    "interface_status_rows": [
                        {
                            "interface": "Ethernet1",
                            "state": "up",
                            "last_link_flapped": "01012024-1230",
                            "in_errors": "0",
                            "crc_count": "0",
                            "mtu": "9216",
                            "flap_count": "1",
                        }
                    ]
                }
            }
        if cf == "interface_description":
            return {"parsed_flat": {"interface_descriptions": {"Ethernet1": "uplink"}}}
        return {"parsed_flat": {}}

    with patch(
        "backend.services.transceiver_service.run_device_commands",
        side_effect=stub,
    ):
        rows, errors, _trace = svc.collect_rows(
            [
                {
                    "hostname": "leaf-1",
                    "ip": "10.0.0.1",
                    "vendor": "Arista",
                    "role": "Leaf",
                }
            ]
        )
    assert errors == []
    assert len(rows) == 1
    row = rows[0]
    assert row["hostname"] == "leaf-1"
    assert row["interface"] == "Ethernet1"
    assert row["status"] == "up"
    assert row["serial"] == "SN1"
    assert row["description"] == "uplink"
    assert row["mtu"] == "9216"
    assert row["last_flap"] == "01012024-1230"
    assert row["errors"] == "0/0"


# --------------------------------------------------------------------------- #
# Migration assertion                                                          #
# --------------------------------------------------------------------------- #


def test_transceiver_routes_owned_by_blueprint(flask_app):
    expected = {
        ("POST", "/api/transceiver"),
        ("POST", "/api/transceiver/recover"),
        ("POST", "/api/transceiver/clear-counters"),
    }
    seen = set()
    for rule in flask_app.url_map.iter_rules():
        for method in rule.methods or ():
            if (method, rule.rule) in expected:
                view = flask_app.view_functions[rule.endpoint]
                assert view.__module__ == "backend.blueprints.transceiver_bp", (
                    f"{method} {rule.rule} dispatches to {view.__module__}"
                )
                seen.add((method, rule.rule))
    assert seen == expected, f"missing: {expected - seen}"
