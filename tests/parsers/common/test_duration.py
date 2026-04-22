"""Unit tests for ``backend.parsers.common.duration``.

Pin the legacy parsing of relative durations like ``"1d02h"``,
``"14week(s) 2day(s)"``, ``"never"``, and ``"00:41:55"``.
"""

from __future__ import annotations

import pytest

from backend.parsers.common.duration import (
    _parse_hhmmss_to_seconds,
    _parse_relative_seconds_ago,
)


class TestParseRelativeSecondsAgo:
    @pytest.mark.parametrize("val", [None, "", "never", "-", 42, "  ", "NEVER"])
    def test_returns_none_for_sentinels(self, val) -> None:
        assert _parse_relative_seconds_ago(val) is None

    def test_compact_dh_format(self) -> None:
        # 1d02h = 1*86400 + 2*3600 = 93600
        assert _parse_relative_seconds_ago("1d02h") == 93600.0

    def test_compact_h(self) -> None:
        assert _parse_relative_seconds_ago("23h") == 23 * 3600

    def test_compact_m(self) -> None:
        assert _parse_relative_seconds_ago("30m") == 30 * 60

    def test_compact_s(self) -> None:
        assert _parse_relative_seconds_ago("45s") == 45

    def test_word_form_weeks_and_days(self) -> None:
        # 14week(s) + 2day(s) = 14*7*86400 + 2*86400
        expected = 14 * 7 * 86400 + 2 * 86400
        assert _parse_relative_seconds_ago("14week(s) 2day(s)") == expected

    def test_word_form_does_not_double_count_compact(self) -> None:
        # "2day(s)" must NOT also match as "2d" (regression: word form is stripped before compact)
        # 2 days only = 172800
        assert _parse_relative_seconds_ago("2day(s)") == 2 * 86400

    def test_word_form_hours_and_minutes(self) -> None:
        assert _parse_relative_seconds_ago("3hour(s) 15minute(s)") == 3 * 3600 + 15 * 60

    def test_zero_total_returns_none(self) -> None:
        # No recognised tokens → total 0 → None
        assert _parse_relative_seconds_ago("xyz") is None

    def test_case_insensitive(self) -> None:
        assert _parse_relative_seconds_ago("1D02H") == 93600.0


class TestParseHhmmssToSeconds:
    @pytest.mark.parametrize("val", [None, "", "  ", "never", "NEVER", "-", "n/a", 42])
    def test_returns_none_for_sentinels(self, val) -> None:
        assert _parse_hhmmss_to_seconds(val) is None

    def test_basic_hhmmss(self) -> None:
        # 00:41:55 = 41*60 + 55 = 2515
        assert _parse_hhmmss_to_seconds("00:41:55") == 2515

    def test_single_digit_hour(self) -> None:
        # 5:00:00 = 5*3600 = 18000
        assert _parse_hhmmss_to_seconds("5:00:00") == 18000

    def test_large_hour_count(self) -> None:
        assert _parse_hhmmss_to_seconds("100:00:00") == 100 * 3600

    def test_strips_surrounding_whitespace(self) -> None:
        assert _parse_hhmmss_to_seconds("  01:00:00  ") == 3600

    def test_invalid_format_returns_none(self) -> None:
        assert _parse_hhmmss_to_seconds("1:00") is None
        assert _parse_hhmmss_to_seconds("01:00:99:00") is None
        assert _parse_hhmmss_to_seconds("ab:cd:ef") is None
