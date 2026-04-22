"""Unit tests for ``backend.parsers.cisco_nxos.arp``."""

from __future__ import annotations

import pytest

from backend.parsers.cisco_nxos.arp import (
    _get_cisco_arp_rows,
    _parse_cisco_arp_ascii_for_ip,
    parse_cisco_arp_interface_for_ip,
)


class TestGetCiscoArpRows:
    def test_finds_rows_in_table_adj(self) -> None:
        data = {
            "TABLE_vrf": {"TABLE_adj": {"ROW_adj": [{"ip-addr-out": "1.1.1.1"}]}}
        }
        rows = _get_cisco_arp_rows(data)
        assert len(rows) == 1

    def test_returns_empty_for_non_dict(self) -> None:
        assert _get_cisco_arp_rows(None) == []
        assert _get_cisco_arp_rows("scalar") == []

    def test_returns_empty_when_no_arp_data(self) -> None:
        assert _get_cisco_arp_rows({}) == []

    def test_dict_row_is_promoted_to_list(self) -> None:
        data = {"TABLE_vrf": {"TABLE_adj": {"ROW_adj": {"ip-addr-out": "1.1.1.1"}}}}
        rows = _get_cisco_arp_rows(data)
        assert rows == [{"ip-addr-out": "1.1.1.1"}]


class TestParseCiscoArpAsciiForIp:
    def test_finds_interface_for_ip(self) -> None:
        text = "10.0.0.1   00:11:22:33:44:55   Ethernet1/1"
        assert _parse_cisco_arp_ascii_for_ip(text, "10.0.0.1") == "Ethernet1/1"

    def test_returns_none_for_no_match(self) -> None:
        text = "10.0.0.2   00:11:22:33:44:55   Ethernet1/1"
        assert _parse_cisco_arp_ascii_for_ip(text, "10.0.0.99") is None

    @pytest.mark.parametrize("text,ip", [("", "1.1.1.1"), (None, "1.1.1.1"), ("text", "")])
    def test_empty_inputs_return_none(self, text, ip) -> None:
        assert _parse_cisco_arp_ascii_for_ip(text, ip) is None

    def test_handles_eth_prefix(self) -> None:
        text = "10.0.0.1 00:11:22:33:44:55 Eth1/2"
        assert _parse_cisco_arp_ascii_for_ip(text, "10.0.0.1") == "Eth1/2"

    def test_handles_port_channel(self) -> None:
        text = "10.0.0.1 00:11:22:33:44:55 Po10"
        assert _parse_cisco_arp_ascii_for_ip(text, "10.0.0.1") == "Po10"

    def test_falls_back_to_last_column(self) -> None:
        # Last column is interface-like, no Ethernet/Eth/Po prefix
        text = "10.0.0.1 00:11:22:33:44:55 mgmt0"
        assert _parse_cisco_arp_ascii_for_ip(text, "10.0.0.1") == "mgmt0"


class TestParseCiscoArpInterfaceForIp:
    def test_finds_via_table_vrf_table_adj(self) -> None:
        raw = {
            "TABLE_vrf": [
                {"TABLE_adj": {"ROW_adj": [{"ip-addr-out": "10.0.0.1", "intf-out": "Ethernet1/1"}]}}
            ]
        }
        assert parse_cisco_arp_interface_for_ip(raw, "10.0.0.1") == "Ethernet1/1"

    def test_finds_via_underscore_keys(self) -> None:
        raw = {
            "TABLE_vrf": [
                {"TABLE_adj": {"ROW_adj": [{"ip_addr_out": "10.0.0.1", "intf_out": "Ethernet1/2"}]}}
            ]
        }
        assert parse_cisco_arp_interface_for_ip(raw, "10.0.0.1") == "Ethernet1/2"

    def test_dict_table_vrf_promoted(self) -> None:
        raw = {
            "TABLE_vrf": {"TABLE_adj": {"ROW_adj": {"ip-addr-out": "1.1.1.1", "intf-out": "Eth9/9"}}}
        }
        assert parse_cisco_arp_interface_for_ip(raw, "1.1.1.1") == "Eth9/9"

    @pytest.mark.parametrize("ip", [None, "", "   "])
    def test_blank_ip_returns_none(self, ip) -> None:
        assert parse_cisco_arp_interface_for_ip({}, ip) is None

    def test_no_match_returns_none(self) -> None:
        raw = {"TABLE_vrf": [{"TABLE_adj": {"ROW_adj": []}}]}
        assert parse_cisco_arp_interface_for_ip(raw, "1.1.1.1") is None

    def test_falls_back_to_ascii_for_string_input(self) -> None:
        raw = "10.0.0.1   aaaa.bbbb.cccc   Ethernet1/1"
        assert parse_cisco_arp_interface_for_ip(raw, "10.0.0.1") == "Ethernet1/1"

    def test_body_string_input(self) -> None:
        raw = {"body": "10.0.0.1 aaaa.bbbb.cccc Ethernet1/1"}
        assert parse_cisco_arp_interface_for_ip(raw, "10.0.0.1") == "Ethernet1/1"

    def test_list_response_with_index(self) -> None:
        raw = [
            {},  # index 0 — empty
            {"TABLE_vrf": {"TABLE_adj": {"ROW_adj": [{"ip-addr-out": "9.9.9.9", "intf-out": "Po1"}]}}},
        ]
        assert parse_cisco_arp_interface_for_ip(raw, "9.9.9.9", index=1) == "Po1"

    def test_falls_back_to_flat_rows(self) -> None:
        # No TABLE_vrf wrapper — use _get_cisco_arp_rows fallback
        raw = {"any_key": [{"ip-addr-out": "1.1.1.1", "intf-out": "Ethernet5/5"}]}
        assert parse_cisco_arp_interface_for_ip(raw, "1.1.1.1") == "Ethernet5/5"
