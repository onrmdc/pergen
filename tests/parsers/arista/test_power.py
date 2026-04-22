"""Unit tests for ``backend.parsers.arista.power``."""

from __future__ import annotations

from backend.parsers.arista.power import _parse_arista_power


class TestParseAristaPower:
    def test_non_dict_returns_blank(self) -> None:
        assert _parse_arista_power(None) == {"Power supplies": ""}

    def test_missing_supplies_returns_blank(self) -> None:
        assert _parse_arista_power({}) == {"Power supplies": ""}

    def test_supplies_not_dict_returns_blank(self) -> None:
        assert _parse_arista_power({"powerSupplies": []}) == {"Power supplies": ""}

    def test_counts_only_ok_state(self) -> None:
        raw = {
            "powerSupplies": {
                "1": {"state": "ok"},
                "2": {"state": "ok"},
                "3": {"state": "failed"},
                "4": {"state": "OK"},  # case-insensitive match
            }
        }
        assert _parse_arista_power(raw) == {"Power supplies": 3}

    def test_no_ok_supplies_returns_zero(self) -> None:
        raw = {"powerSupplies": {"1": {"state": "failed"}, "2": {"state": "off"}}}
        assert _parse_arista_power(raw) == {"Power supplies": 0}

    def test_skips_non_dict_supply_entries(self) -> None:
        raw = {"powerSupplies": {"1": "scalar", "2": {"state": "ok"}}}
        assert _parse_arista_power(raw) == {"Power supplies": 1}

    def test_missing_state_treated_as_not_ok(self) -> None:
        raw = {"powerSupplies": {"1": {}, "2": {"state": "ok"}}}
        assert _parse_arista_power(raw) == {"Power supplies": 1}
