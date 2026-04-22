"""Unit tests for ``backend.parsers.arista.interface_description``."""

from __future__ import annotations

from backend.parsers.arista.interface_description import (
    _parse_arista_interface_description,
)


class TestParseAristaInterfaceDescription:
    def test_two_interfaces(self) -> None:
        raw = {
            "interfaceDescriptions": {
                "Ethernet1/1": {"description": "uplink-spine-1"},
                "Ethernet1/2": {"description": "downlink-server-3"},
            }
        }
        out = _parse_arista_interface_description(raw)
        assert out == {
            "interface_descriptions": {
                "Ethernet1/1": "uplink-spine-1",
                "Ethernet1/2": "downlink-server-3",
            }
        }

    def test_string_description_value(self) -> None:
        raw = {"interfaceDescriptions": {"Eth1": "raw-string"}}
        out = _parse_arista_interface_description(raw)
        assert out == {"interface_descriptions": {"Eth1": "raw-string"}}

    def test_none_description_value_becomes_empty(self) -> None:
        raw = {"interfaceDescriptions": {"Eth1": None}}
        out = _parse_arista_interface_description(raw)
        assert out == {"interface_descriptions": {"Eth1": ""}}

    def test_missing_interface_descriptions_returns_empty(self) -> None:
        assert _parse_arista_interface_description({}) == {"interface_descriptions": {}}

    def test_non_dict_returns_empty(self) -> None:
        assert _parse_arista_interface_description(None) == {"interface_descriptions": {}}

    def test_descriptions_not_dict_returns_empty(self) -> None:
        assert _parse_arista_interface_description(
            {"interfaceDescriptions": "scalar"}
        ) == {"interface_descriptions": {}}

    def test_strips_whitespace(self) -> None:
        raw = {"interfaceDescriptions": {"Eth1": {"description": "  hello  "}}}
        out = _parse_arista_interface_description(raw)
        assert out["interface_descriptions"]["Eth1"] == "hello"
