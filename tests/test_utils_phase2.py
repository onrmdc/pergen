"""
Phase-2 tests — pure helper extraction from ``backend/app.py``.

RED before GREEN: these tests import from the *new* destination modules
(``backend.utils.*``) which do not yet exist. Once the helpers are
moved, the tests must pass without touching this file again.

Behaviour verified here is the *contract* the helpers had as private
``_*`` functions in ``backend/app.py``. They are now public utilities,
so they get real unit tests for the first time.
"""
from __future__ import annotations


# --------------------------------------------------------------------------- #
# backend.utils.transceiver_display                                            #
# --------------------------------------------------------------------------- #


def test_transceiver_errors_display_zero_when_missing():
    from backend.utils.transceiver_display import transceiver_errors_display

    assert transceiver_errors_display({}) == "0/0"


def test_transceiver_errors_display_handles_dash_and_blank():
    from backend.utils.transceiver_display import transceiver_errors_display

    assert transceiver_errors_display({"crc_count": "-", "in_errors": ""}) == "0/0"


def test_transceiver_errors_display_parses_integers_and_floats():
    from backend.utils.transceiver_display import transceiver_errors_display

    assert transceiver_errors_display({"crc_count": "12", "in_errors": "3.7"}) == "12/3"


def test_transceiver_errors_display_extracts_leading_int_from_garbage():
    from backend.utils.transceiver_display import transceiver_errors_display

    assert transceiver_errors_display({"crc_count": "42 errors", "in_errors": "abc"}) == "42/0"


def test_transceiver_last_flap_display_returns_dash_when_unknown():
    from backend.utils.transceiver_display import transceiver_last_flap_display

    assert transceiver_last_flap_display({}) == "-"


def test_transceiver_last_flap_display_formats_epoch():
    from backend.utils.transceiver_display import transceiver_last_flap_display

    # 2024-01-15 03:04:05 UTC = 1705287845
    out = transceiver_last_flap_display({"last_status_change_epoch": 1705287845})
    # Format is local-time DDMMYYYY-HHMM; just assert pattern + 13 chars
    import re

    assert re.match(r"^\d{8}-\d{4}$", out)


def test_transceiver_last_flap_display_passes_through_already_formatted_string():
    from backend.utils.transceiver_display import transceiver_last_flap_display

    assert transceiver_last_flap_display({"last_link_flapped": "01012024-1230"}) == "01012024-1230"


def test_transceiver_last_flap_display_ignores_malformed_string():
    from backend.utils.transceiver_display import transceiver_last_flap_display

    assert transceiver_last_flap_display({"last_link_flapped": "yesterday"}) == "-"


# --------------------------------------------------------------------------- #
# backend.utils.interface_status                                               #
# --------------------------------------------------------------------------- #


def test_iface_status_lookup_direct_hit():
    from backend.utils.interface_status import iface_status_lookup

    src = {"Ethernet1": {"oper": "up"}}
    assert iface_status_lookup(src, "Ethernet1") == {"oper": "up"}


def test_iface_status_lookup_case_insensitive_match():
    from backend.utils.interface_status import iface_status_lookup

    src = {"Ethernet1": {"oper": "up"}}
    assert iface_status_lookup(src, "ethernet1") == {"oper": "up"}


def test_iface_status_lookup_strips_internal_whitespace():
    from backend.utils.interface_status import iface_status_lookup

    src = {"Ether net1": {"oper": "up"}}
    assert iface_status_lookup(src, "Ethernet1") == {"oper": "up"}


def test_iface_status_lookup_returns_empty_dict_when_missing():
    from backend.utils.interface_status import iface_status_lookup

    assert iface_status_lookup({}, "Ethernet1") == {}


def test_iface_status_lookup_skips_non_dict_values():
    from backend.utils.interface_status import iface_status_lookup

    src = {"Ethernet1": "not-a-dict"}
    # exact key match still returns whatever is there (legacy behaviour)
    assert iface_status_lookup(src, "Ethernet1") == "not-a-dict"
    # case-fold match coerces non-dicts to {}
    assert iface_status_lookup(src, "ethernet1") == {}


def test_merge_cisco_detailed_flap_creates_canonical_entry():
    from backend.utils.interface_status import merge_cisco_detailed_flap

    status: dict = {}
    flap_rows = [
        {
            "interface": "Ethernet1/1",
            "last_link_flapped": "01012024-1230",
            "flap_counter": "5",
            "crc_count": "2",
            "in_errors": "1",
            "last_status_change_epoch": 1700000000,
        }
    ]
    merge_cisco_detailed_flap(status, flap_rows)
    assert status["Ethernet1/1"]["flap_count"] == "5"
    assert status["Ethernet1/1"]["last_link_flapped"] == "01012024-1230"
    assert status["Ethernet1/1"]["crc_count"] == "2"
    assert status["Ethernet1/1"]["in_errors"] == "1"
    assert status["Ethernet1/1"]["last_status_change_epoch"] == 1700000000


def test_merge_cisco_detailed_flap_ignores_blank_and_dash_values():
    from backend.utils.interface_status import merge_cisco_detailed_flap

    status: dict = {"Ethernet1": {"flap_count": "9", "crc_count": "3"}}
    merge_cisco_detailed_flap(
        status,
        [{"interface": "Ethernet1", "flap_counter": "-", "crc_count": ""}],
    )
    # untouched
    assert status["Ethernet1"]["flap_count"] == "9"
    assert status["Ethernet1"]["crc_count"] == "3"


def test_merge_cisco_detailed_flap_skips_non_dict_rows_and_empty_iface():
    from backend.utils.interface_status import merge_cisco_detailed_flap

    status: dict = {}
    merge_cisco_detailed_flap(status, ["garbage", {"interface": ""}])
    assert status == {}


def test_merge_cisco_detailed_flap_matches_existing_key_case_insensitively():
    from backend.utils.interface_status import merge_cisco_detailed_flap

    status: dict = {"Ethernet1": {}}
    merge_cisco_detailed_flap(
        status,
        [{"interface": "ethernet1", "flap_counter": "7"}],
    )
    assert status["Ethernet1"]["flap_count"] == "7"
    assert "ethernet1" not in status


def test_interface_status_trace_filters_to_status_commands_only():
    from backend.utils.interface_status import interface_status_trace

    payload = {
        "commands": [
            {
                "command_id": "arista_show_interface_status",
                "parsed": {"interface_status_rows": [{"interface": "Et1", "flap_count": 0}]},
                "raw": {"k": 1},
            },
            {"command_id": "unrelated", "parsed": {}, "raw": {}},
        ]
    }
    out = interface_status_trace(payload)
    assert len(out) == 1
    assert out[0]["command_id"] == "arista_show_interface_status"
    assert out[0]["parsed_row_count"] == 1
    assert out[0]["sample_interfaces"] == ["Et1"]


def test_cisco_interface_detailed_trace_filters_exact_command_id():
    from backend.utils.interface_status import cisco_interface_detailed_trace

    payload = {
        "commands": [
            {
                "command_id": "cisco_nxos_show_interface",
                "parsed": {"interface_flapped_rows": [{"interface": "Eth1/1"}]},
                "raw": [{"x": 1}],
            },
            {"command_id": "cisco_nxos_show_other", "parsed": {}, "raw": {}},
        ]
    }
    out = cisco_interface_detailed_trace(payload)
    assert len(out) == 1
    assert out[0]["parsed_flap_row_count"] == 1


# --------------------------------------------------------------------------- #
# backend.utils.bgp_helpers                                                    #
# --------------------------------------------------------------------------- #


def test_wan_rtr_has_bgp_as_text_match():
    from backend.utils.bgp_helpers import wan_rtr_has_bgp_as

    assert wan_rtr_has_bgp_as("router bgp 65000\n neighbor x", "65000", is_json=False) is True


def test_wan_rtr_has_bgp_as_text_no_match():
    from backend.utils.bgp_helpers import wan_rtr_has_bgp_as

    assert wan_rtr_has_bgp_as("router bgp 65000", "65001", is_json=False) is False


def test_wan_rtr_has_bgp_as_text_requires_word_boundary():
    from backend.utils.bgp_helpers import wan_rtr_has_bgp_as

    # 65000 should NOT match 650001
    assert wan_rtr_has_bgp_as("router bgp 650001\n", "65000", is_json=False) is False


def test_wan_rtr_has_bgp_as_json_match():
    from backend.utils.bgp_helpers import wan_rtr_has_bgp_as

    payload = {"cmds": {"router bgp 65000": {}}}
    assert wan_rtr_has_bgp_as(payload, "65000", is_json=True) is True


def test_wan_rtr_has_bgp_as_json_no_match_when_payload_missing():
    from backend.utils.bgp_helpers import wan_rtr_has_bgp_as

    assert wan_rtr_has_bgp_as(None, "65000", is_json=True) is False
    assert wan_rtr_has_bgp_as("not a dict", "65000", is_json=True) is False


def test_wan_rtr_has_bgp_as_rejects_non_digit_asn():
    from backend.utils.bgp_helpers import wan_rtr_has_bgp_as

    assert wan_rtr_has_bgp_as("router bgp 65000", "abc", is_json=False) is False
    assert wan_rtr_has_bgp_as("router bgp 65000", "", is_json=False) is False


# --------------------------------------------------------------------------- #
# backend.utils.ping                                                           #
# --------------------------------------------------------------------------- #


def test_ping_module_exposes_max_ping_devices_constant():
    from backend.utils.ping import MAX_PING_DEVICES

    assert MAX_PING_DEVICES == 64


def test_single_ping_returns_false_on_subprocess_failure(monkeypatch):
    from backend.utils import ping as ping_mod

    def boom(*_a, **_k):
        raise OSError("ping not found")

    monkeypatch.setattr(ping_mod.subprocess, "run", boom)
    assert ping_mod.single_ping("10.0.0.1", timeout_sec=1) is False


def test_single_ping_returns_true_on_zero_returncode(monkeypatch):
    from backend.utils import ping as ping_mod

    class _Result:
        returncode = 0

    monkeypatch.setattr(ping_mod.subprocess, "run", lambda *a, **k: _Result())
    assert ping_mod.single_ping("10.0.0.1", timeout_sec=1) is True


def test_single_ping_returns_false_on_nonzero_returncode(monkeypatch):
    from backend.utils import ping as ping_mod

    class _Result:
        returncode = 1

    monkeypatch.setattr(ping_mod.subprocess, "run", lambda *a, **k: _Result())
    assert ping_mod.single_ping("10.0.0.1", timeout_sec=1) is False


# --------------------------------------------------------------------------- #
# Backwards-compat shim — the original names must still resolve from app.py    #
# (existing code/tests may import them).                                       #
# --------------------------------------------------------------------------- #


def test_legacy_names_still_resolvable_from_backend_app():
    """`backend.app` re-exports the helpers under their old underscore names so
    any in-tree caller (or shadow test) keeps working until phase 12."""
    import backend.app as legacy

    assert callable(legacy._transceiver_errors_display)
    assert callable(legacy._transceiver_last_flap_display)
    assert callable(legacy._iface_status_lookup)
    assert callable(legacy._merge_cisco_detailed_flap)
    assert callable(legacy._interface_status_trace)
    assert callable(legacy._cisco_interface_detailed_trace)
    assert callable(legacy._wan_rtr_has_bgp_as)
    assert callable(legacy._single_ping)
    assert legacy._MAX_PING_DEVICES == 64
