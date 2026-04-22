"""Unit tests for ``backend.parsers.arista.uptime``."""

from __future__ import annotations

import pytest

from backend.parsers.arista.uptime import _parse_arista_uptime


class TestParseAristaUptime:
    @pytest.mark.parametrize(
        "raw",
        [None, "", 42, [], "not-json"],
    )
    def test_non_dict_input_returns_blank(self, raw) -> None:
        assert _parse_arista_uptime(raw) == {"Uptime": ""}

    def test_string_with_brace_parsed_as_json(self) -> None:
        assert _parse_arista_uptime('{"upTime": 3600}') == {"Uptime": "0d 1h 0m 0s"}

    def test_invalid_json_string_falls_through_to_zero(self) -> None:
        # malformed JSON inside a brace-prefixed string → empty dict → all zeros
        assert _parse_arista_uptime('{not-json}') == {"Uptime": "0d 0h 0m 0s"}

    def test_one_day(self) -> None:
        assert _parse_arista_uptime({"upTime": 86400}) == {"Uptime": "1d 0h 0m 0s"}

    def test_compound_duration(self) -> None:
        # 1d 2h 3m 4s = 86400 + 7200 + 180 + 4 = 93784
        assert _parse_arista_uptime({"upTime": 93784}) == {"Uptime": "1d 2h 3m 4s"}

    def test_float_uptime_truncates(self) -> None:
        assert _parse_arista_uptime({"upTime": 3661.5}) == {"Uptime": "0d 1h 1m 1s"}

    def test_string_uptime_coerced(self) -> None:
        assert _parse_arista_uptime({"upTime": "60"}) == {"Uptime": "0d 0h 1m 0s"}

    def test_invalid_uptime_returns_blank(self) -> None:
        assert _parse_arista_uptime({"upTime": "abc"}) == {"Uptime": ""}

    def test_missing_uptime_treated_as_zero(self) -> None:
        assert _parse_arista_uptime({"other": 1}) == {"Uptime": "0d 0h 0m 0s"}
