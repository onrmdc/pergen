"""Unit tests for ``backend.parsers.arista.bgp``."""

from __future__ import annotations

from backend.parsers.arista.bgp import parse_arista_bgp_evpn_next_hop


class TestParseAristaBgpEvpnNextHop:
    def test_returns_first_next_hop(self) -> None:
        raw = {
            "evpnRoutes": {
                "route1": {"evpnRoutePaths": [{"nextHop": "10.0.0.5"}]},
            }
        }
        assert parse_arista_bgp_evpn_next_hop(raw) == "10.0.0.5"

    def test_returns_first_non_blank_next_hop(self) -> None:
        raw = {
            "evpnRoutes": {
                "r1": {"evpnRoutePaths": [{"nextHop": ""}]},
                "r2": {"evpnRoutePaths": [{"nextHop": "1.2.3.4"}]},
            }
        }
        assert parse_arista_bgp_evpn_next_hop(raw) == "1.2.3.4"

    def test_returns_none_when_no_routes(self) -> None:
        assert parse_arista_bgp_evpn_next_hop({"evpnRoutes": {}}) is None

    def test_non_dict_returns_none(self) -> None:
        assert parse_arista_bgp_evpn_next_hop(None) is None
        assert parse_arista_bgp_evpn_next_hop("scalar") is None

    def test_skips_path_entries_that_arent_dicts(self) -> None:
        raw = {
            "evpnRoutes": {
                "r1": {"evpnRoutePaths": ["scalar", {"nextHop": "5.5.5.5"}]},
            }
        }
        assert parse_arista_bgp_evpn_next_hop(raw) == "5.5.5.5"

    def test_skips_route_entries_that_arent_dicts(self) -> None:
        raw = {"evpnRoutes": {"junk": "scalar", "good": {"evpnRoutePaths": [{"nextHop": "9.9.9.9"}]}}}
        assert parse_arista_bgp_evpn_next_hop(raw) == "9.9.9.9"

    def test_strips_whitespace_in_next_hop(self) -> None:
        raw = {"evpnRoutes": {"r": {"evpnRoutePaths": [{"nextHop": "  10.0.0.1  "}]}}}
        assert parse_arista_bgp_evpn_next_hop(raw) == "10.0.0.1"

    def test_list_wrapped_response(self) -> None:
        raw = [{"evpnRoutes": {"r": {"evpnRoutePaths": [{"nextHop": "1.1.1.1"}]}}}]
        assert parse_arista_bgp_evpn_next_hop(raw) == "1.1.1.1"

    def test_no_evpn_routes_returns_none(self) -> None:
        assert parse_arista_bgp_evpn_next_hop({}) is None
