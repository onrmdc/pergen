"""Unit tests for ``backend.parsers.common.formatting``."""

from __future__ import annotations

from backend.parsers.common.formatting import (
    _apply_value_subtract_and_suffix,
    _format_power_two_decimals,
)


class TestApplyValueSubtractAndSuffix:
    def test_none_value_sets_none(self) -> None:
        result: dict = {}
        _apply_value_subtract_and_suffix({}, None, result, "k")
        assert result == {"k": None}

    def test_int_passthrough_no_modifiers(self) -> None:
        result: dict = {}
        _apply_value_subtract_and_suffix({}, 5, result, "k")
        assert result == {"k": 5}

    def test_float_passthrough_no_modifiers(self) -> None:
        result: dict = {}
        _apply_value_subtract_and_suffix({}, 3.14, result, "k")
        assert result == {"k": 3.14}

    def test_string_numeric_coerced_then_passthrough(self) -> None:
        result: dict = {}
        _apply_value_subtract_and_suffix({}, "5", result, "k")
        assert result == {"k": 5.0}

    def test_string_non_numeric_returned_as_string(self) -> None:
        result: dict = {}
        _apply_value_subtract_and_suffix({}, "abc", result, "k")
        assert result == {"k": "abc"}

    def test_value_subtract_from(self) -> None:
        # 100 - 25 = 75
        result: dict = {}
        _apply_value_subtract_and_suffix({"value_subtract_from": 100}, 25, result, "k")
        assert result == {"k": 75.0}

    def test_value_suffix_with_int(self) -> None:
        result: dict = {}
        _apply_value_subtract_and_suffix({"value_suffix": " %"}, 42, result, "k")
        assert result == {"k": "42 %"}

    def test_value_suffix_with_float_rounds_to_2(self) -> None:
        result: dict = {}
        _apply_value_subtract_and_suffix({"value_suffix": " %"}, 42.567, result, "k")
        assert result == {"k": "42.57 %"}

    def test_subtract_then_suffix(self) -> None:
        # 100 - 25.5 = 74.5 → "74.5 %"
        result: dict = {}
        _apply_value_subtract_and_suffix(
            {"value_subtract_from": 100, "value_suffix": " %"}, 25.5, result, "k"
        )
        assert result == {"k": "74.5 %"}

    def test_subtract_with_invalid_subtract_value_keeps_original(self) -> None:
        # Helper swallows TypeError on subtract; result keeps the (already converted) num
        result: dict = {}
        _apply_value_subtract_and_suffix(
            {"value_subtract_from": "not-a-number"}, 25, result, "k"
        )
        assert result == {"k": 25}


class TestFormatPowerTwoDecimals:
    def test_none_returns_dash(self) -> None:
        assert _format_power_two_decimals(None) == "-"

    def test_dash_returns_dash(self) -> None:
        assert _format_power_two_decimals("-") == "-"

    def test_empty_string_returns_dash(self) -> None:
        assert _format_power_two_decimals("") == "-"
        assert _format_power_two_decimals("   ") == "-"

    def test_int_formats_two_decimals(self) -> None:
        assert _format_power_two_decimals(5) == "5.00"

    def test_float_formats_two_decimals(self) -> None:
        assert _format_power_two_decimals(-3.14159) == "-3.14"

    def test_string_numeric(self) -> None:
        assert _format_power_two_decimals("3.14") == "3.14"

    def test_european_decimal_separator(self) -> None:
        assert _format_power_two_decimals("3,14") == "3.14"

    def test_non_numeric_string_returned_unchanged(self) -> None:
        assert _format_power_two_decimals("N/A") == "N/A"
