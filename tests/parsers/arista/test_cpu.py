"""Unit tests for ``backend.parsers.arista.cpu``."""

from __future__ import annotations

from backend.parsers.arista.cpu import _parse_arista_cpu


class TestParseAristaCpu:
    def test_non_dict_returns_blank(self) -> None:
        assert _parse_arista_cpu(None) == {"CPU usage": ""}
        assert _parse_arista_cpu("scalar") == {"CPU usage": ""}

    def test_missing_cpu_info_returns_blank(self) -> None:
        assert _parse_arista_cpu({}) == {"CPU usage": ""}

    def test_cpu_info_not_dict_returns_blank(self) -> None:
        assert _parse_arista_cpu({"cpuInfo": "scalar"}) == {"CPU usage": ""}

    def test_idle_25_percent_means_75_used(self) -> None:
        raw = {"cpuInfo": {"%Cpu(s)": {"idle": 25.0}}}
        assert _parse_arista_cpu(raw) == {"CPU usage": "75.0 %"}

    def test_idle_zero_means_full_load(self) -> None:
        raw = {"cpuInfo": {"%Cpu(s)": {"idle": 0}}}
        assert _parse_arista_cpu(raw) == {"CPU usage": "100.0 %"}

    def test_invalid_idle_returns_blank(self) -> None:
        raw = {"cpuInfo": {"%Cpu(s)": {"idle": "not-a-number"}}}
        assert _parse_arista_cpu(raw) == {"CPU usage": ""}

    def test_missing_pct_dict_returns_blank(self) -> None:
        raw = {"cpuInfo": {"%Cpu(s)": "scalar"}}
        assert _parse_arista_cpu(raw) == {"CPU usage": ""}

    def test_list_wrapped_input(self) -> None:
        # Arista eAPI returns a list; envelope helper takes [0]
        raw = [{"cpuInfo": {"%Cpu(s)": {"idle": 90}}}]
        assert _parse_arista_cpu(raw) == {"CPU usage": "10.0 %"}
