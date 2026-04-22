"""Unit tests for ``backend.parsers.cisco_nxos.interface_description``."""

from __future__ import annotations

from backend.parsers.cisco_nxos.interface_description import (
    _parse_cisco_interface_description,
)


class TestParseCiscoInterfaceDescription:
    def test_two_interfaces(self) -> None:
        raw = {
            "TABLE_interface": {
                "ROW_interface": [
                    {"interface": "Ethernet1/1", "desc": "uplink"},
                    {"interface": "Ethernet1/2", "description": "downlink"},
                ]
            }
        }
        out = _parse_cisco_interface_description(raw)
        assert out == {
            "interface_descriptions": {
                "Ethernet1/1": "uplink",
                "Ethernet1/2": "downlink",
            }
        }

    def test_alternate_port_desc_key(self) -> None:
        raw = {"TABLE_interface": {"ROW_interface": [{"interface": "Eth1", "port_desc": "test"}]}}
        out = _parse_cisco_interface_description(raw)
        assert out == {"interface_descriptions": {"Eth1": "test"}}

    def test_empty_description(self) -> None:
        raw = {"TABLE_interface": {"ROW_interface": [{"interface": "Eth1"}]}}
        out = _parse_cisco_interface_description(raw)
        assert out == {"interface_descriptions": {"Eth1": ""}}

    def test_empty_returns_empty(self) -> None:
        assert _parse_cisco_interface_description({}) == {"interface_descriptions": {}}
        assert _parse_cisco_interface_description(None) == {"interface_descriptions": {}}

    def test_skips_rows_without_interface(self) -> None:
        raw = {"TABLE_interface": {"ROW_interface": [{"desc": "lonely"}]}}
        out = _parse_cisco_interface_description(raw)
        assert out == {"interface_descriptions": {}}

    def test_dict_row_promoted_to_list(self) -> None:
        raw = {"TABLE_interface": {"ROW_interface": {"interface": "Eth1", "desc": "x"}}}
        out = _parse_cisco_interface_description(raw)
        assert out == {"interface_descriptions": {"Eth1": "x"}}
