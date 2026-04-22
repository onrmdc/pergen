"""Unit tests for ``backend.parsers.arista.disk``."""

from __future__ import annotations

from backend.parsers.arista.disk import _parse_arista_disk


class TestParseAristaDisk:
    def test_non_dict_returns_blank(self) -> None:
        assert _parse_arista_disk(None) == {"Disk": ""}

    def test_missing_filesystems_returns_blank(self) -> None:
        assert _parse_arista_disk({}) == {"Disk": ""}

    def test_flash_25pct_used(self) -> None:
        raw = {"fileSystems": [{"prefix": "flash:", "size": 100, "free": 75}]}
        assert _parse_arista_disk(raw) == {"Disk": "25.0 %"}

    def test_flash_full(self) -> None:
        raw = {"fileSystems": [{"prefix": "flash:", "size": 1000, "free": 0}]}
        assert _parse_arista_disk(raw) == {"Disk": "100.0 %"}

    def test_skips_non_flash_filesystems(self) -> None:
        # Only "flash:" prefix matters
        raw = {
            "fileSystems": [
                {"prefix": "tmp:", "size": 100, "free": 50},
                {"prefix": "flash:", "size": 200, "free": 100},
            ]
        }
        assert _parse_arista_disk(raw) == {"Disk": "50.0 %"}

    def test_zero_size_returns_blank(self) -> None:
        raw = {"fileSystems": [{"prefix": "flash:", "size": 0, "free": 0}]}
        assert _parse_arista_disk(raw) == {"Disk": ""}

    def test_invalid_size_returns_blank(self) -> None:
        raw = {"fileSystems": [{"prefix": "flash:", "size": "abc", "free": 0}]}
        assert _parse_arista_disk(raw) == {"Disk": ""}

    def test_no_flash_present_returns_blank(self) -> None:
        raw = {"fileSystems": [{"prefix": "tmp:", "size": 100, "free": 50}]}
        assert _parse_arista_disk(raw) == {"Disk": ""}

    def test_non_dict_filesystem_entry_skipped(self) -> None:
        raw = {"fileSystems": ["scalar", {"prefix": "flash:", "size": 100, "free": 90}]}
        assert _parse_arista_disk(raw) == {"Disk": "10.0 %"}
