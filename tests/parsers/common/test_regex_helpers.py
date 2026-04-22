"""Unit tests for ``backend.parsers.common.regex_helpers``."""

from __future__ import annotations

from backend.parsers.common.regex_helpers import _count_regex_lines, _extract_regex


class TestExtractRegex:
    def test_returns_first_capture_group(self) -> None:
        assert _extract_regex("name: alice", r"name:\s+(\w+)") == "alice"

    def test_strips_capture_whitespace(self) -> None:
        assert _extract_regex("v =   42  ", r"v =\s*(.+)") == "42"

    def test_returns_none_when_no_match(self) -> None:
        assert _extract_regex("abc", r"xyz=(\d+)") is None

    def test_returns_none_when_pattern_has_no_group(self) -> None:
        # m.lastindex is None when there are no groups
        assert _extract_regex("abc", r"abc") is None

    def test_returns_none_for_empty_text(self) -> None:
        assert _extract_regex("", r"(\w+)") is None

    def test_returns_none_for_empty_pattern(self) -> None:
        assert _extract_regex("abc", "") is None

    def test_invalid_regex_returns_none(self) -> None:
        # malformed regex; helper swallows exceptions
        assert _extract_regex("abc", r"(unclosed") is None

    def test_multiline_dotall_flags_active(self) -> None:
        # MULTILINE + DOTALL means . matches newline; here we use ^ across lines
        text = "first\nfoo: bar"
        assert _extract_regex(text, r"^foo:\s+(\w+)") == "bar"


class TestCountRegexLines:
    def test_counts_each_match(self) -> None:
        text = "a\nb\nc"
        assert _count_regex_lines(text, r"^[a-z]$") == 3

    def test_returns_zero_for_no_match(self) -> None:
        assert _count_regex_lines("abc", r"\d+") == 0

    def test_returns_zero_for_empty_text(self) -> None:
        assert _count_regex_lines("", r".") == 0

    def test_returns_zero_for_empty_pattern(self) -> None:
        assert _count_regex_lines("abc", "") == 0

    def test_invalid_regex_returns_zero(self) -> None:
        assert _count_regex_lines("abc", r"(unclosed") == 0

    def test_findall_counts_overlapping_matches_once_each(self) -> None:
        # findall is non-overlapping by default
        assert _count_regex_lines("aaaa", r"aa") == 2
