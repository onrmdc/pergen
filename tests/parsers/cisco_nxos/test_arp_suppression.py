"""Unit tests for ``backend.parsers.cisco_nxos.arp_suppression``."""

from __future__ import annotations

import pytest

from backend.parsers.cisco_nxos.arp_suppression import (
    _get_arp_suppression_entries_list,
    parse_arp_suppression_asci,
    parse_arp_suppression_for_ip,
)


class TestGetArpSuppressionEntriesList:
    def test_returns_list_with_ip_addr_keys(self) -> None:
        rows = [{"ip-addr": "1.1.1.1"}, {"ip-addr": "2.2.2.2"}]
        assert _get_arp_suppression_entries_list(rows) is rows

    def test_underscore_variant(self) -> None:
        rows = [{"ip_addr": "1.1.1.1"}]
        assert _get_arp_suppression_entries_list(rows) is rows

    def test_finds_in_dict_with_entries_key(self) -> None:
        data = {"some_entries": [{"ip-addr": "1.1.1.1"}]}
        assert _get_arp_suppression_entries_list(data) == [{"ip-addr": "1.1.1.1"}]

    def test_recurses_into_nested(self) -> None:
        data = {"outer": [{"deeper_entries": [{"ip-addr": "1.1.1.1"}]}]}
        assert _get_arp_suppression_entries_list(data) == [{"ip-addr": "1.1.1.1"}]

    def test_returns_none_for_no_match(self) -> None:
        assert _get_arp_suppression_entries_list({}) is None
        assert _get_arp_suppression_entries_list(None) is None
        assert _get_arp_suppression_entries_list([]) is None


class TestParseArpSuppressionForIp:
    def test_finds_local_entry(self) -> None:
        raw = {
            "entries": [
                {"ip-addr": "10.0.0.1", "flag": "L", "physical-iod": "Eth1/1", "remote-vtep-addr": ""}
            ]
        }
        out = parse_arp_suppression_for_ip(raw, "10.0.0.1")
        assert out == {"flag": "L", "physical_iod": "Eth1/1", "remote_vtep_addr": ""}

    def test_finds_remote_entry(self) -> None:
        raw = {
            "entries": [
                {"ip-addr": "10.0.0.2", "flag": "R", "physical-iod": "", "remote-vtep-addr": "10.99.99.99"}
            ]
        }
        out = parse_arp_suppression_for_ip(raw, "10.0.0.2")
        assert out["flag"] == "R"
        assert out["remote_vtep_addr"] == "10.99.99.99"

    def test_returns_none_for_no_match(self) -> None:
        raw = {"entries": [{"ip-addr": "1.1.1.1"}]}
        assert parse_arp_suppression_for_ip(raw, "9.9.9.9") is None

    def test_returns_none_for_empty_search_ip(self) -> None:
        assert parse_arp_suppression_for_ip({"entries": []}, "") is None
        assert parse_arp_suppression_for_ip({"entries": []}, None) is None

    def test_returns_none_for_unsupported_input(self) -> None:
        assert parse_arp_suppression_for_ip(42, "1.1.1.1") is None

    def test_string_input_falls_back_to_ascii(self) -> None:
        text = '"ip-addr":"10.0.0.1" "flag":"R" "physical-iod":"Eth1/1" "remote-vtep-addr":"10.99.99.99"'
        out = parse_arp_suppression_for_ip(text, "10.0.0.1")
        assert out is not None
        assert out["flag"] == "R"

    def test_blank_flag_defaults_to_L(self) -> None:
        raw = {"entries": [{"ip-addr": "1.1.1.1", "flag": "", "physical-iod": "Eth1"}]}
        out = parse_arp_suppression_for_ip(raw, "1.1.1.1")
        assert out["flag"] == "L"

    def test_dict_without_entries_falls_back_to_row_search(self) -> None:
        raw = {"some_ROW_key": [{"ip-addr": "1.1.1.1", "flag": "L", "physical-iod": "Eth9/9"}]}
        out = parse_arp_suppression_for_ip(raw, "1.1.1.1")
        assert out is not None
        assert out["physical_iod"] == "Eth9/9"


class TestParseArpSuppressionAsci:
    def test_returns_none_for_no_match(self) -> None:
        assert parse_arp_suppression_asci("nothing here", "10.0.0.1") is None

    def test_returns_none_for_empty_inputs(self) -> None:
        assert parse_arp_suppression_asci("", "1.1.1.1") is None
        assert parse_arp_suppression_asci("text", "") is None

    def test_extracts_flag_phys_remote(self) -> None:
        text = '10.0.0.1 "flag":"R" "physical-iod":"Ethernet1/1" "remote-vtep-addr":"10.99.99.99"'
        out = parse_arp_suppression_asci(text, "10.0.0.1")
        assert out["flag"] == "R"
        assert out["physical_iod"] == "Ethernet1/1"
        assert out["remote_vtep_addr"] == "10.99.99.99"

    def test_default_flag_when_missing(self) -> None:
        text = '10.0.0.1 some text'
        out = parse_arp_suppression_asci(text, "10.0.0.1")
        assert out is not None
        assert out["flag"] == "L"

    @pytest.mark.parametrize("ip", [None, ""])
    def test_blank_ip(self, ip) -> None:
        assert parse_arp_suppression_asci("text", ip) is None
