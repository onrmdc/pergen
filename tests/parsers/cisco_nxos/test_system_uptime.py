"""Unit tests for ``backend.parsers.cisco_nxos.system_uptime``."""

from __future__ import annotations

from backend.parsers.cisco_nxos.system_uptime import _parse_cisco_system_uptime


class TestParseCiscoSystemUptime:
    def test_basic(self) -> None:
        raw = {"sys_up_days": 1, "sys_up_hrs": 2, "sys_up_mins": 3, "sys_up_secs": 4}
        assert _parse_cisco_system_uptime(raw) == {"Uptime": "1d 2h 3m 4s"}

    def test_missing_fields_default_to_zero(self) -> None:
        assert _parse_cisco_system_uptime({}) == {"Uptime": "0d 0h 0m 0s"}

    def test_string_values(self) -> None:
        raw = {
            "sys_up_days": "5",
            "sys_up_hrs": "0",
            "sys_up_mins": "30",
            "sys_up_secs": "15",
        }
        assert _parse_cisco_system_uptime(raw) == {"Uptime": "5d 0h 30m 15s"}

    def test_strips_whitespace(self) -> None:
        raw = {"sys_up_days": "  7  ", "sys_up_hrs": " 1 "}
        assert _parse_cisco_system_uptime(raw) == {"Uptime": "7d 1h 0m 0s"}

    def test_non_dict_returns_blank(self) -> None:
        assert _parse_cisco_system_uptime(None) == {"Uptime": ""}
        assert _parse_cisco_system_uptime("scalar") == {"Uptime": ""}

    def test_string_with_brace_parsed_as_json(self) -> None:
        raw = '{"sys_up_days":"3"}'
        assert _parse_cisco_system_uptime(raw) == {"Uptime": "3d 0h 0m 0s"}

    def test_invalid_json_string_returns_empty_uptime(self) -> None:
        # Not parseable JSON → empty dict from inner parse → all zeros
        raw = '{not json'
        assert _parse_cisco_system_uptime(raw) == {"Uptime": "0d 0h 0m 0s"}
