"""Unit tests for ``backend.parsers.arista.isis``."""

from __future__ import annotations

from backend.parsers.arista.isis import (
    _find_arista_isis_adjacency_list,
    _parse_arista_isis_adjacency,
)


class TestFindAristaIsisAdjacencyList:
    def test_returns_adjacencyTable(self) -> None:
        data = {"adjacencyTable": [{"interface": "Eth1"}]}
        assert _find_arista_isis_adjacency_list(data) == [{"interface": "Eth1"}]

    def test_returns_adjacencies_alt_key(self) -> None:
        data = {"adjacencies": [{"interface": "Eth2"}]}
        assert _find_arista_isis_adjacency_list(data) == [{"interface": "Eth2"}]

    def test_recurses_into_nested_dicts(self) -> None:
        data = {"outer": {"adjacencyTable": [{"interface": "Eth3"}]}}
        assert _find_arista_isis_adjacency_list(data) == [{"interface": "Eth3"}]

    def test_falls_back_to_inferred_list(self) -> None:
        data = {"unknown_key": [{"interface": "Eth4", "state": "Up"}]}
        assert _find_arista_isis_adjacency_list(data) == [{"interface": "Eth4", "state": "Up"}]

    def test_empty_dict_returns_empty(self) -> None:
        assert _find_arista_isis_adjacency_list({}) == []

    def test_non_dict_returns_empty(self) -> None:
        assert _find_arista_isis_adjacency_list(None) == []
        assert _find_arista_isis_adjacency_list("scalar") == []


class TestParseAristaIsisAdjacency:
    def test_two_neighbors(self) -> None:
        raw = {
            "adjacencyTable": [
                {"interface": "Ethernet1/1", "state": "Up"},
                {"interface": "Ethernet1/2", "state": "Down"},
            ]
        }
        out = _parse_arista_isis_adjacency(raw)
        assert out["ISIS"] == "2"
        assert len(out["isis_adjacency_rows"]) == 2
        assert out["isis_adjacency_rows"][0]["interface"] == "Ethernet1/1"

    def test_empty_response_returns_zero(self) -> None:
        out = _parse_arista_isis_adjacency({})
        assert out["ISIS"] == "0"
        assert out["isis_adjacency_rows"] == []

    def test_non_dict_returns_default(self) -> None:
        out = _parse_arista_isis_adjacency(None)
        assert out == {"isis_adjacency_count": 0, "isis_adjacency_rows": [], "ISIS": "0"}

    def test_picks_alt_field_names(self) -> None:
        # adjacencyState used instead of state; interfaceName instead of interface
        raw = {
            "adjacencyTable": [
                {"interfaceName": "Eth1/1", "adjacencyState": "Up"},
            ]
        }
        out = _parse_arista_isis_adjacency(raw)
        assert out["isis_adjacency_rows"] == [{"interface": "Eth1/1", "state": "Up"}]

    def test_skips_blank_interface(self) -> None:
        raw = {"adjacencyTable": [{"state": "Up"}, {"interface": "Eth1", "state": "Up"}]}
        out = _parse_arista_isis_adjacency(raw)
        assert out["isis_adjacency_rows"] == [{"interface": "Eth1", "state": "Up"}]

    def test_blank_state_defaults_to_unknown(self) -> None:
        raw = {"adjacencyTable": [{"interface": "Eth1"}]}
        out = _parse_arista_isis_adjacency(raw)
        # interface present but no state → "Unknown"
        assert out["isis_adjacency_rows"][0]["state"] == "Unknown"
