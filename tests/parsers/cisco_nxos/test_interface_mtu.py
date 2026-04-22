"""Unit tests for ``backend.parsers.cisco_nxos.interface_mtu``."""

from __future__ import annotations

from backend.parsers.cisco_nxos.interface_mtu import _parse_cisco_interface_show_mtu


class TestParseCiscoInterfaceShowMtu:
    def test_two_interfaces(self) -> None:
        raw = {
            "TABLE_interface": {
                "ROW_interface": [
                    {"interface": "Ethernet1/1", "eth_mtu": "9216"},
                    {"interface": "Ethernet1/2", "eth_mtu": "1500"},
                ]
            }
        }
        out = _parse_cisco_interface_show_mtu(raw)
        assert out == {"interface_mtu_map": {"Ethernet1/1": "9216", "Ethernet1/2": "1500"}}

    def test_dict_row_promoted_to_list(self) -> None:
        raw = {"TABLE_interface": {"ROW_interface": {"interface": "Eth1", "eth_mtu": "1500"}}}
        out = _parse_cisco_interface_show_mtu(raw)
        assert out == {"interface_mtu_map": {"Eth1": "1500"}}

    def test_missing_eth_mtu_becomes_dash(self) -> None:
        raw = {"TABLE_interface": {"ROW_interface": [{"interface": "Eth1"}]}}
        out = _parse_cisco_interface_show_mtu(raw)
        assert out == {"interface_mtu_map": {"Eth1": "-"}}

    def test_empty_returns_empty_map(self) -> None:
        assert _parse_cisco_interface_show_mtu({}) == {"interface_mtu_map": {}}
        assert _parse_cisco_interface_show_mtu(None) == {"interface_mtu_map": {}}

    def test_skips_rows_with_no_interface(self) -> None:
        raw = {"TABLE_interface": {"ROW_interface": [{"eth_mtu": "1500"}]}}
        out = _parse_cisco_interface_show_mtu(raw)
        assert out == {"interface_mtu_map": {}}

    def test_body_string_unwrap(self) -> None:
        import json
        body = json.dumps({"TABLE_interface": {"ROW_interface": [{"interface": "Eth1", "eth_mtu": "9216"}]}})
        raw = {"body": body}
        out = _parse_cisco_interface_show_mtu(raw)
        assert out == {"interface_mtu_map": {"Eth1": "9216"}}
