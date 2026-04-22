"""Unit tests for ``backend.parsers.cisco_nxos.isis_brief``."""

from __future__ import annotations

from backend.parsers.cisco_nxos.isis_brief import (
    _find_isis_interface_brief_rows,
    _parse_cisco_isis_interface_brief,
)


class TestFindIsisInterfaceBriefRows:
    def test_finds_rows_with_intfb_name_out(self) -> None:
        data = {"key": [{"intfb-name-out": "Ethernet1/1", "intfb-state-out": "up"}]}
        rows = _find_isis_interface_brief_rows(data)
        assert len(rows) == 1

    def test_recurses_nested(self) -> None:
        data = {"outer": {"inner": [{"intfb-name-out": "Eth1"}]}}
        rows = _find_isis_interface_brief_rows(data)
        assert len(rows) == 1

    def test_empty_returns_empty(self) -> None:
        assert _find_isis_interface_brief_rows({}) == []
        assert _find_isis_interface_brief_rows(None) == []


class TestParseCiscoIsisInterfaceBrief:
    def test_two_up_interfaces(self) -> None:
        raw = {
            "TABLE_x": {
                "ROW_x": [
                    {
                        "intfb-name-out": "Ethernet1/1",
                        "intfb-state-out": "up",
                        "intfb-ready-state-out": "Ready",
                    },
                    {
                        "intfb-name-out": "Ethernet1/2",
                        "intfb-state-out": "down",
                        "intfb-ready-state-out": "Ready",
                    },
                ]
            }
        }
        out = _parse_cisco_isis_interface_brief(raw)
        # 1 up out of 2 ready
        assert out["ISIS"] == "1/2"
        assert len(out["isis_interface_rows"]) == 2

    def test_skips_loopback(self) -> None:
        raw = {
            "TABLE_x": {
                "ROW_x": [
                    {
                        "intfb-name-out": "Ethernet-loopback0",
                        "intfb-state-out": "up",
                        "intfb-ready-state-out": "Ready",
                    },
                ]
            }
        }
        out = _parse_cisco_isis_interface_brief(raw)
        # The loopback row is skipped (name contains "loopback")
        assert out["isis_interface_rows"] == []

    def test_skips_non_ethernet(self) -> None:
        raw = {
            "TABLE_x": {
                "ROW_x": [
                    {
                        "intfb-name-out": "mgmt0",
                        "intfb-state-out": "up",
                        "intfb-ready-state-out": "Ready",
                    },
                ]
            }
        }
        out = _parse_cisco_isis_interface_brief(raw)
        assert out["isis_interface_rows"] == []

    def test_only_ready_counted(self) -> None:
        raw = {
            "TABLE_x": {
                "ROW_x": [
                    {
                        "intfb-name-out": "Ethernet1/1",
                        "intfb-state-out": "up",
                        "intfb-ready-state-out": "NotReady",
                    }
                ]
            }
        }
        out = _parse_cisco_isis_interface_brief(raw)
        assert out["ISIS"] == "0/0"
        # The interface still appears in the row list (state is captured) — that's the existing contract
        assert len(out["isis_interface_rows"]) == 1

    def test_string_with_brace_parsed_as_json(self) -> None:
        raw = '{"TABLE_x":{"ROW_x":[{"intfb-name-out":"Ethernet1/1","intfb-state-out":"up","intfb-ready-state-out":"Ready"}]}}'
        out = _parse_cisco_isis_interface_brief(raw)
        assert out["ISIS"] == "1/1"

    def test_empty_returns_zero_zero(self) -> None:
        assert _parse_cisco_isis_interface_brief({}) == {"ISIS": "0/0", "isis_interface_rows": []}
