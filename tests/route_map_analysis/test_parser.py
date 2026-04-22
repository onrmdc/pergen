"""Unit tests for ``backend.route_map_analysis.parser``.

Covers the helpers extracted from the legacy god-module in wave-3 phase 8:

* ``_get_cmds`` — unwrap the optional ``cmds`` envelope
* ``_extract_prefix_lists`` — ``ip prefix-list NAME`` → entries
* ``_extract_route_map_prefix_lists`` — route-map NAME → referenced prefix-lists
* ``_find_router_bgp_cmds`` — find the router bgp block
* ``_extract_bgp`` — neighbor → peer-group + route-map mapping (incl. VRF)
* ``analyze_router_config`` — top-level orchestrator

All inputs are shaped like Arista ``show running-config | json`` payloads.
"""

from __future__ import annotations

from backend.route_map_analysis.parser import (
    _extract_bgp,
    _extract_prefix_lists,
    _extract_route_map_prefix_lists,
    _find_router_bgp_cmds,
    _get_cmds,
    analyze_router_config,
)


# --------------------------------------------------------------------------- #
# _get_cmds                                                                    #
# --------------------------------------------------------------------------- #


class TestGetCmds:
    def test_returns_inner_cmds(self) -> None:
        assert _get_cmds({"cmds": {"key": "value"}}) == {"key": "value"}

    def test_passthrough_when_no_cmds_key(self) -> None:
        assert _get_cmds({"router bgp 1": {}}) == {"router bgp 1": {}}

    def test_returns_empty_for_falsy(self) -> None:
        assert _get_cmds(None) == {}
        assert _get_cmds({}) == {}

    def test_returns_empty_for_non_dict(self) -> None:
        assert _get_cmds("string") == {}
        assert _get_cmds([1, 2]) == {}


# --------------------------------------------------------------------------- #
# _extract_prefix_lists                                                        #
# --------------------------------------------------------------------------- #


class TestExtractPrefixLists:
    def test_parses_seq_action_prefix(self) -> None:
        cmds = {
            "ip prefix-list PL-A": {
                "cmds": {
                    "seq 10 permit 10.0.0.0/8": {},
                    "seq 20 deny 192.168.0.0/16": {},
                }
            }
        }
        out = _extract_prefix_lists(cmds)
        assert "PL-A" in out
        # Sorted by seq.
        assert out["PL-A"] == [
            {"seq": 10, "action": "permit", "prefix": "10.0.0.0/8"},
            {"seq": 20, "action": "deny", "prefix": "192.168.0.0/16"},
        ]

    def test_skips_non_prefix_list_keys(self) -> None:
        cmds = {
            "router bgp 1": {"cmds": {}},
            "ip prefix-list X": {"cmds": {"seq 5 permit 1.1.1.1/32": {}}},
        }
        out = _extract_prefix_lists(cmds)
        assert list(out.keys()) == ["X"]

    def test_handles_empty_cmds(self) -> None:
        assert _extract_prefix_lists({}) == {}
        assert _extract_prefix_lists(None) == {}

    def test_skips_lines_that_do_not_match_format(self) -> None:
        cmds = {
            "ip prefix-list PL": {
                "cmds": {
                    "garbage line": {},
                    "seq 10 permit 10.0.0.0/8": {},
                }
            }
        }
        out = _extract_prefix_lists(cmds)
        assert out["PL"] == [
            {"seq": 10, "action": "permit", "prefix": "10.0.0.0/8"},
        ]


# --------------------------------------------------------------------------- #
# _extract_route_map_prefix_lists                                              #
# --------------------------------------------------------------------------- #


class TestExtractRouteMapPrefixLists:
    def test_extracts_single_reference(self) -> None:
        cmds = {
            "route-map RM-A permit 10": {
                "cmds": {"match ip address prefix-list PL-A": {}}
            }
        }
        out = _extract_route_map_prefix_lists(cmds)
        assert out == {"RM-A": ["PL-A"]}

    def test_dedups_and_sorts_references(self) -> None:
        cmds = {
            "route-map RM permit 10": {
                "cmds": {"match ip address prefix-list PL-Z": {}}
            },
            "route-map RM permit 20": {
                "cmds": {"match ip address prefix-list PL-A": {}}
            },
            "route-map RM permit 30": {
                "cmds": {"match ip address prefix-list PL-Z": {}}  # duplicate
            },
        }
        out = _extract_route_map_prefix_lists(cmds)
        assert out["RM"] == ["PL-A", "PL-Z"]

    def test_skips_non_route_map_keys(self) -> None:
        cmds = {
            "ip prefix-list PL": {"cmds": {}},
            "route-map RM permit 10": {
                "cmds": {"match ip address prefix-list PL": {}}
            },
        }
        out = _extract_route_map_prefix_lists(cmds)
        assert "RM" in out
        assert "PL" not in out

    def test_skips_route_maps_with_no_prefix_list_match(self) -> None:
        cmds = {
            "route-map RM permit 10": {
                "cmds": {"set local-preference 200": {}}
            }
        }
        assert _extract_route_map_prefix_lists(cmds) == {}

    def test_skips_route_map_without_three_tokens(self) -> None:
        # "route-map JUSTNAME" — too few tokens after stripping the prefix.
        cmds = {
            "route-map JUSTNAME": {"cmds": {"match ip address prefix-list PL": {}}}
        }
        assert _extract_route_map_prefix_lists(cmds) == {}


# --------------------------------------------------------------------------- #
# _find_router_bgp_cmds                                                        #
# --------------------------------------------------------------------------- #


class TestFindRouterBgpCmds:
    def test_finds_router_bgp_block(self) -> None:
        cmds = {
            "ip prefix-list X": {},
            "router bgp 65001": {"cmds": {"neighbor 1.1.1.1 peer group P": {}}},
        }
        out = _find_router_bgp_cmds(cmds)
        assert "neighbor 1.1.1.1 peer group P" in out

    def test_returns_empty_when_absent(self) -> None:
        assert _find_router_bgp_cmds({"foo": {}}) == {}
        assert _find_router_bgp_cmds({}) == {}


# --------------------------------------------------------------------------- #
# _extract_bgp                                                                 #
# --------------------------------------------------------------------------- #


class TestExtractBgp:
    def test_neighbor_peer_group_assignment(self) -> None:
        cmds = {
            "router bgp 65001": {
                "cmds": {
                    "neighbor 1.1.1.1 peer group P-A": {},
                    "neighbor 2.2.2.2 peer group P-B": {},
                }
            }
        }
        n2g, rm = _extract_bgp(cmds)
        assert n2g == {"1.1.1.1": "P-A", "2.2.2.2": "P-B"}
        assert rm == {}

    def test_route_map_in_and_out(self) -> None:
        cmds = {
            "router bgp 65001": {
                "cmds": {
                    "neighbor P-A peer group P-A": {},  # group definition (skipped)
                    "neighbor P-A route-map RM-IN in": {},
                    "neighbor P-A route-map RM-OUT out": {},
                }
            }
        }
        n2g, rm = _extract_bgp(cmds)
        # The "neighbor P-A peer group P-A" line registers P-A as both ip and group.
        assert n2g.get("P-A") == "P-A"
        assert rm["P-A"] == {"in": "RM-IN", "out": "RM-OUT"}

    def test_neighbor_inherits_route_map_from_group(self) -> None:
        cmds = {
            "router bgp 65001": {
                "cmds": {
                    "neighbor 1.1.1.1 peer group P-A": {},
                    "neighbor P-A route-map RM-IN in": {},
                }
            }
        }
        n2g, rm = _extract_bgp(cmds)
        assert n2g["1.1.1.1"] == "P-A"
        # Inheritance: 1.1.1.1 picks up RM-IN from its group P-A.
        assert "1.1.1.1" in rm
        assert rm["1.1.1.1"]["in"] == "RM-IN"

    def test_vrf_block_uses_vrf_name_as_group_override(self) -> None:
        cmds = {
            "router bgp 65001": {
                "cmds": {
                    "vrf TENANT-A": {
                        "cmds": {
                            "neighbor 10.1.1.1 peer group PG-VRF": {},
                            "neighbor PG-VRF route-map RM-VRF in": {},
                        }
                    }
                }
            }
        }
        n2g, rm = _extract_bgp(cmds)
        # group_override = vrf name → 10.1.1.1 maps to TENANT-A, not PG-VRF.
        assert n2g["10.1.1.1"] == "TENANT-A"
        assert rm["PG-VRF"]["in"] == "RM-VRF"

    def test_handles_no_router_bgp_section(self) -> None:
        n2g, rm = _extract_bgp({"ip prefix-list X": {}})
        assert n2g == {}
        assert rm == {}

    def test_skips_blank_keys(self) -> None:
        cmds = {
            "router bgp 1": {
                "cmds": {
                    "": {},
                    "   ": {},
                    "neighbor 1.1.1.1 peer group P": {},
                }
            }
        }
        n2g, _ = _extract_bgp(cmds)
        assert n2g == {"1.1.1.1": "P"}


# --------------------------------------------------------------------------- #
# analyze_router_config                                                        #
# --------------------------------------------------------------------------- #


class TestAnalyzeRouterConfig:
    def test_full_pipeline(self) -> None:
        data = {
            "cmds": {
                "ip prefix-list PL-A": {
                    "cmds": {"seq 10 permit 10.0.0.0/8": {}}
                },
                "route-map RM-IN permit 10": {
                    "cmds": {"match ip address prefix-list PL-A": {}}
                },
                "router bgp 65001": {
                    "cmds": {
                        "neighbor 1.1.1.1 peer group P-A": {},
                        "neighbor P-A route-map RM-IN in": {},
                    }
                },
            }
        }
        out = analyze_router_config(data)
        assert "PL-A" in out["prefix_lists"]
        assert out["route_map_prefix_lists"] == {"RM-IN": ["PL-A"]}
        assert out["bgp_neighbor_to_group"]["1.1.1.1"] == "P-A"
        assert out["bgp_route_maps"]["P-A"]["in"] == "RM-IN"

    def test_empty_data(self) -> None:
        out = analyze_router_config({})
        assert out == {
            "prefix_lists": {},
            "route_map_prefix_lists": {},
            "bgp_neighbor_to_group": {},
            "bgp_route_maps": {},
        }
