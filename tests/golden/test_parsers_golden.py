"""
Golden snapshot suite for every ``backend.parse_output._parse_*`` parser.

Each test feeds a representative raw payload (modelled after real device JSON
shapes: Arista eAPI ``| json`` and Cisco NX-API JSON-RPC bodies) and snapshots
the parser's output.  The goal is to lock current behaviour byte-for-byte
before the refactor moves these functions into a ``ParserEngine`` class.

When a test runs for the first time, the snapshot file is created under
``tests/fixtures/golden/parsers/<name>.json`` and committed.  Subsequent runs
fail on any drift — re-run with ``PERGEN_REGEN_GOLDEN=1`` to deliberately
re-baseline.

These tests deliberately use ``time.time()`` patching (or check fields that
do not depend on wall-clock time) so they are deterministic.
"""
from __future__ import annotations

from unittest import mock

import pytest

from tests.golden._snapshot import assert_matches_snapshot

pytestmark = pytest.mark.golden


# --------------------------------------------------------------------------- #
# Arista parsers                                                              #
# --------------------------------------------------------------------------- #


def test_arista_uptime_seconds_to_dhms():
    from backend.parse_output import _parse_arista_uptime

    out = _parse_arista_uptime({"upTime": 90061})  # 1d 1h 1m 1s
    assert_matches_snapshot("parsers/arista_uptime_basic", out)


def test_arista_uptime_invalid_input():
    from backend.parse_output import _parse_arista_uptime

    assert_matches_snapshot("parsers/arista_uptime_empty", _parse_arista_uptime({}))
    assert_matches_snapshot(
        "parsers/arista_uptime_non_dict", _parse_arista_uptime("not a dict")
    )


def test_arista_cpu_idle_to_usage():
    from backend.parse_output import _parse_arista_cpu

    raw = {"cpuInfo": {"%Cpu(s)": {"idle": 87.5}}}
    assert_matches_snapshot("parsers/arista_cpu_basic", _parse_arista_cpu(raw))
    assert_matches_snapshot("parsers/arista_cpu_empty", _parse_arista_cpu({}))


def test_arista_disk_flash_percentage():
    from backend.parse_output import _parse_arista_disk

    raw = {
        "fileSystems": [
            {"prefix": "flash:", "size": 1000, "free": 250},
            {"prefix": "/dev/something", "size": 500, "free": 100},
        ]
    }
    assert_matches_snapshot("parsers/arista_disk_basic", _parse_arista_disk(raw))
    assert_matches_snapshot("parsers/arista_disk_empty", _parse_arista_disk({}))


def test_arista_power_counts_ok_supplies():
    from backend.parse_output import _parse_arista_power

    raw = {
        "powerSupplies": {
            "1": {"state": "ok"},
            "2": {"state": "ok"},
            "3": {"state": "failed"},
        }
    }
    assert_matches_snapshot("parsers/arista_power_basic", _parse_arista_power(raw))
    assert_matches_snapshot("parsers/arista_power_empty", _parse_arista_power({}))


def test_arista_isis_adjacency():
    from backend.parse_output import _parse_arista_isis_adjacency

    raw = {
        "vrfs": {
            "default": {
                "isisInstances": {
                    "1": {
                        "interfaces": {
                            "Ethernet1": {
                                "intfLevels": {
                                    "2": {
                                        "neighborInfo": [
                                            {"interfaceName": "Ethernet1", "state": "Up"}
                                        ]
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    assert_matches_snapshot(
        "parsers/arista_isis_adjacency_basic", _parse_arista_isis_adjacency(raw)
    )
    assert_matches_snapshot(
        "parsers/arista_isis_adjacency_empty", _parse_arista_isis_adjacency({})
    )


def test_arista_transceiver_basic():
    from backend.parse_output import _parse_arista_transceiver

    raw = {
        "interfaces": {
            "Ethernet1": {
                "txPower": -1.234,
                "rxPower": -2.5,
                "serialNumber": "SN1234",
                "vendorSn": "SN1234",
            },
            "Ethernet2": {
                "txPower": "-",
                "rxPower": None,
                "serialNumber": "",
            },
        }
    }
    assert_matches_snapshot("parsers/arista_transceiver_basic", _parse_arista_transceiver(raw))


def test_arista_interface_status_table_form():
    from backend.parse_output import _parse_arista_interface_status

    raw = {
        "TABLE_interface": {
            "ROW_interface": [
                {
                    "interface": "Ethernet1/15",
                    "state": "down",
                    "state_rsn_desc": "linkFlapErrDisabled",
                    "eth_link_flapped": "14week(s) 2day(s)",
                    "eth_reset_cntr": "25",
                    "eth_mtu": "9216",
                    "eth_inerr": "12",
                    "eth_crc": "3",
                }
            ]
        }
    }
    out = _parse_arista_interface_status(raw)
    out_no_epoch = _strip_epoch_keys(out, "interface_status_rows")
    assert_matches_snapshot("parsers/arista_interface_status_table", out_no_epoch)


def test_arista_interface_status_native_dict():
    from backend.parse_output import _parse_arista_interface_status

    raw = {
        "interfaces": {
            "Ethernet1/1": {
                "interfaceStatus": "connected",
                "interfaceCounters": {
                    "inErrors": 7,
                    "fcsErrors": 2,
                    "linkStatusChanges": 4,
                },
                "mtu": 9216,
                "lastStatusChangeTimestamp": 1700000000.0,
            }
        }
    }
    out = _parse_arista_interface_status(raw)
    out_no_epoch = _strip_epoch_keys(out, "interface_status_rows")
    assert_matches_snapshot("parsers/arista_interface_status_native", out_no_epoch)


def test_arista_interface_description():
    from backend.parse_output import _parse_arista_interface_description

    raw = {
        "interfaceDescriptions": {
            "Ethernet1": {"description": "uplink-to-spine-01"},
            "Ethernet2": {"description": ""},
            "Management1": "mgmt-net",
        }
    }
    assert_matches_snapshot(
        "parsers/arista_interface_description", _parse_arista_interface_description(raw)
    )


# --------------------------------------------------------------------------- #
# Cisco NX-OS parsers                                                         #
# --------------------------------------------------------------------------- #


def test_cisco_system_uptime():
    from backend.parse_output import _parse_cisco_system_uptime

    raw = {"sys_up_days": "1", "sys_up_hrs": "2", "sys_up_mins": "3", "sys_up_secs": "4"}
    assert_matches_snapshot("parsers/cisco_system_uptime_basic", _parse_cisco_system_uptime(raw))
    assert_matches_snapshot("parsers/cisco_system_uptime_empty", _parse_cisco_system_uptime({}))


def test_cisco_isis_interface_brief():
    from backend.parse_output import _parse_cisco_isis_interface_brief

    raw = {
        "TABLE_process_tag": {
            "ROW_process_tag": {
                "TABLE_intf": {
                    "ROW_intf": [
                        {
                            "intfb-name-out": "Ethernet1/1",
                            "intfb-state-out": "Up",
                            "intfb-ready-state-out": "Ready",
                        },
                        {
                            "intfb-name-out": "Ethernet1/2",
                            "intfb-state-out": "Down",
                            "intfb-ready-state-out": "Ready",
                        },
                        {
                            "intfb-name-out": "loopback0",
                            "intfb-state-out": "Up",
                            "intfb-ready-state-out": "Ready",
                        },
                    ]
                }
            }
        }
    }
    assert_matches_snapshot(
        "parsers/cisco_isis_interface_brief_basic",
        _parse_cisco_isis_interface_brief(raw),
    )


def test_cisco_power_basic():
    from backend.parse_output import _parse_cisco_power

    raw = {
        "TABLE_psinfo": {
            "ROW_psinfo": [
                {"psnum": "1", "ps_status": "ok"},
                {"psnum": "2", "ps_status": "shutdown"},
            ]
        }
    }
    assert_matches_snapshot("parsers/cisco_power_basic", _parse_cisco_power(raw))


def test_cisco_nxos_transceiver_basic():
    from backend.parse_output import _parse_cisco_nxos_transceiver

    raw = {
        "TABLE_interface": {
            "ROW_interface": [
                {
                    "interface": "Ethernet1/1",
                    "sfp": "present",
                    "type": "QSFP-100G-SR4",
                    "name": "CISCO",
                    "partnum": "QSFP-100G-SR4",
                    "serialnum": "ABC1234",
                    "tx_pwr": "-1.50",
                    "rx_pwr": "-2.00",
                }
            ]
        }
    }
    assert_matches_snapshot(
        "parsers/cisco_nxos_transceiver_basic", _parse_cisco_nxos_transceiver(raw)
    )


def test_cisco_interface_status_table():
    from backend.parse_output import _parse_cisco_interface_status

    raw = {
        "TABLE_interface": {
            "ROW_interface": [
                {
                    "interface": "Ethernet1/1",
                    "state": "up",
                    "name": "uplink",
                    "duplex": "full",
                    "speed": "100G",
                }
            ]
        }
    }
    out = _parse_cisco_interface_status(raw)
    assert_matches_snapshot(
        "parsers/cisco_interface_status_table",
        _strip_epoch_keys(out, "interface_status_rows"),
    )


def test_cisco_interface_show_mtu():
    from backend.parse_output import _parse_cisco_interface_show_mtu

    raw = {
        "TABLE_interface": {
            "ROW_interface": [
                {"interface": "Ethernet1/1", "eth_mtu": "9216"},
                {"interface": "Ethernet1/2", "eth_mtu": "1500"},
            ]
        }
    }
    assert_matches_snapshot("parsers/cisco_interface_show_mtu", _parse_cisco_interface_show_mtu(raw))


def test_cisco_interface_detailed_basic():
    from backend.parse_output import _parse_cisco_interface_detailed

    raw = {
        "TABLE_interface": {
            "ROW_interface": [
                {
                    "interface": "Ethernet1/1",
                    "state": "eth-up",
                    "eth_crc": "3",
                    "eth_inerr": "12",
                    "eth_link_flapped": "00:01:00",
                    "eth_reset_cntr": "5",
                }
            ]
        }
    }
    with mock.patch("backend.parse_output.time.time", return_value=1_700_000_000.0):
        out = _parse_cisco_interface_detailed(raw)
    assert_matches_snapshot("parsers/cisco_interface_detailed_basic", out)


def test_cisco_interface_description():
    from backend.parse_output import _parse_cisco_interface_description

    raw = {
        "TABLE_interface": {
            "ROW_interface": [
                {"interface": "Ethernet1/1", "desc": "uplink"},
                {"interface": "Ethernet1/2", "description": "downlink"},
                {"interface": "Ethernet1/3"},  # no description key
            ]
        }
    }
    assert_matches_snapshot(
        "parsers/cisco_interface_description", _parse_cisco_interface_description(raw)
    )


# --------------------------------------------------------------------------- #
# Public dispatcher                                                           #
# --------------------------------------------------------------------------- #


def test_parse_output_with_custom_parser_routes_to_arista_uptime():
    from backend.parse_output import parse_output

    out = parse_output(
        "arista_uptime",
        {"upTime": 3600},
        {"custom_parser": "arista_uptime", "fields": []},
    )
    assert_matches_snapshot("parsers/dispatch_arista_uptime", out)


def test_parse_output_with_yaml_field_only():
    from backend.parse_output import parse_output

    out = parse_output(
        "ad-hoc",
        {"version": "4.30"},
        {
            "fields": [
                {"name": "Version", "json_path": "version"},
            ]
        },
    )
    assert_matches_snapshot("parsers/dispatch_yaml_only", out)


def test_parse_output_format_template():
    from backend.parse_output import parse_output

    out = parse_output(
        "ad-hoc-fmt",
        {"a": 5, "b": 7},
        {
            "fields": [
                {"name": "A", "json_path": "a"},
                {"name": "B", "json_path": "b"},
                {
                    "name": "Combined",
                    "format_template": "{A}/{B}",
                    "format_fields": ["A", "B"],
                },
            ]
        },
    )
    assert_matches_snapshot("parsers/dispatch_format_template", out)


def test_parse_output_no_config_returns_empty():
    from backend.parse_output import parse_output

    assert_matches_snapshot(
        "parsers/dispatch_no_config", parse_output("x", {"a": 1}, None)  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _strip_epoch_keys(payload: dict, list_key: str) -> dict:
    """Remove ``last_status_change_epoch`` keys (wall-clock derived) from row lists.

    The parsers compute ``time.time() - seconds_ago``; we patch ``time.time``
    where possible, but for the multi-row Arista parsers we strip the field
    so snapshots remain deterministic without monkey-patching the module."""
    cleaned = dict(payload)
    rows = list(cleaned.get(list_key) or [])
    cleaned[list_key] = [
        {k: v for k, v in row.items() if k != "last_status_change_epoch"}
        for row in rows
    ]
    return cleaned
