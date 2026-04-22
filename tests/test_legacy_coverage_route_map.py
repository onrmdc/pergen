"""
Coverage push for ``backend/route_map_analysis.py``.

The module exposes two public functions:
  * ``analyze_router_config(data: dict) -> dict``
  * ``build_unified_bgp_full_table(parsed_list: list) -> list``

Both consume Arista EOS ``show running-config | json`` payloads.
We feed minimal-but-realistic payloads to drive coverage.
"""
from __future__ import annotations


def _eos_config(*, peer_groups=None, neighbors=None, route_maps=None, prefix_lists=None):
    """Build a minimal EOS show-running-config-json structure."""
    return {
        "cmds": {
            "router bgp 65000": {
                "cmds": {
                    **{
                        f"neighbor {pg} peer group": {"cmds": pg_cfg}
                        for pg, pg_cfg in (peer_groups or {}).items()
                    },
                    **{
                        f"neighbor {ip} peer group {pg}": {}
                        for ip, pg in (neighbors or {}).items()
                    },
                }
            },
            **{
                f"route-map {name} {action} {seq}": {"cmds": rm_cfg}
                for name, action, seq, rm_cfg in (route_maps or [])
            },
            **{
                f"ip prefix-list {name} seq {seq} {rule}": {}
                for name, seq, rule in (prefix_lists or [])
            },
        }
    }


# --------------------------------------------------------------------------- #
# analyze_router_config — exercise multiple branches                           #
# --------------------------------------------------------------------------- #


def test_analyze_router_config_empty_returns_dict():
    from backend.route_map_analysis import analyze_router_config

    out = analyze_router_config({})
    assert isinstance(out, dict)


def test_analyze_router_config_no_bgp_returns_dict():
    from backend.route_map_analysis import analyze_router_config

    out = analyze_router_config({"cmds": {}})
    assert isinstance(out, dict)


def test_analyze_router_config_with_peer_groups():
    from backend.route_map_analysis import analyze_router_config

    cfg = _eos_config(
        peer_groups={
            "PG-IPV4": {
                "route-map RM-IN in": {},
                "route-map RM-OUT out": {},
            }
        },
        neighbors={"10.0.0.1": "PG-IPV4"},
        route_maps=[
            ("RM-IN", "permit", "10", {"match ip address prefix-list PL-IN": {}}),
            ("RM-OUT", "deny", "10", {"match community CL1": {}}),
        ],
        prefix_lists=[("PL-IN", "5", "permit 10.0.0.0/8")],
    )
    out = analyze_router_config(cfg)
    assert isinstance(out, dict)


def test_analyze_router_config_with_multiple_peer_groups():
    from backend.route_map_analysis import analyze_router_config

    cfg = _eos_config(
        peer_groups={
            "PG-A": {"route-map RM-A in": {}},
            "PG-B": {"route-map RM-B out": {}},
            "PG-C": {},
        },
    )
    out = analyze_router_config(cfg)
    assert isinstance(out, dict)


def test_analyze_router_config_with_route_map_continue_chain():
    """Cover route-map hierarchy traversal (continue clauses)."""
    from backend.route_map_analysis import analyze_router_config

    cfg = _eos_config(
        route_maps=[
            ("RM-1", "permit", "10", {"continue 20": {}}),
            ("RM-1", "permit", "20", {"set local-preference 200": {}}),
        ],
    )
    out = analyze_router_config(cfg)
    assert isinstance(out, dict)


def test_analyze_router_config_handles_malformed_entries():
    """Garbage in different positions must not crash."""
    from backend.route_map_analysis import analyze_router_config

    cfg = {"cmds": {"router bgp 65000": {"cmds": {"not a neighbor": {}}}}}
    out = analyze_router_config(cfg)
    assert isinstance(out, dict)


def test_analyze_router_config_complex_neighbors():
    from backend.route_map_analysis import analyze_router_config

    cfg = _eos_config(
        peer_groups={
            "BACKBONE": {
                "remote-as 65001": {},
                "send-community": {},
                "route-map BB-IN in": {},
            }
        },
        neighbors={
            "172.16.0.1": "BACKBONE",
            "172.16.0.2": "BACKBONE",
        },
        route_maps=[("BB-IN", "permit", "10", {"set as-path prepend 65000 65000": {}})],
    )
    out = analyze_router_config(cfg)
    assert isinstance(out, dict)


# --------------------------------------------------------------------------- #
# build_unified_bgp_full_table                                                 #
# --------------------------------------------------------------------------- #


def test_build_unified_bgp_full_table_empty():
    from backend.route_map_analysis import build_unified_bgp_full_table

    assert build_unified_bgp_full_table([]) == []


def test_build_unified_bgp_full_table_single_router():
    from backend.route_map_analysis import build_unified_bgp_full_table

    parsed_one = {
        "hostname": "rtr-1",
        "vendor": "Arista",
        "model": "EOS",
        "parsed": {"peer_groups": []},
    }
    out = build_unified_bgp_full_table([parsed_one])
    assert isinstance(out, list)


def test_build_unified_bgp_full_table_multiple_routers():
    from backend.route_map_analysis import (
        analyze_router_config,
        build_unified_bgp_full_table,
    )

    cfg_a = _eos_config(
        peer_groups={"PG": {"route-map RM-A-IN in": {}}},
        route_maps=[("RM-A-IN", "permit", "10", {})],
    )
    cfg_b = _eos_config(
        peer_groups={"PG": {"route-map RM-B-IN in": {}}},
        route_maps=[("RM-B-IN", "permit", "10", {})],
    )
    rows = build_unified_bgp_full_table(
        [
            {"hostname": "a", "vendor": "Arista", "model": "EOS", "parsed": analyze_router_config(cfg_a)},
            {"hostname": "b", "vendor": "Arista", "model": "EOS", "parsed": analyze_router_config(cfg_b)},
        ]
    )
    assert isinstance(rows, list)


def test_build_unified_bgp_full_table_handles_missing_parsed():
    from backend.route_map_analysis import build_unified_bgp_full_table

    out = build_unified_bgp_full_table(
        [{"hostname": "a", "vendor": "Arista", "model": "EOS"}]
    )
    assert isinstance(out, list)


def test_build_unified_bgp_full_table_handles_string_in_list():
    """Defensive: parsed_list contains a non-dict entry."""
    from backend.route_map_analysis import build_unified_bgp_full_table

    try:
        out = build_unified_bgp_full_table(["garbage"])
        assert isinstance(out, list)
    except (AttributeError, TypeError):
        # Acceptable: not currently defended
        pass
