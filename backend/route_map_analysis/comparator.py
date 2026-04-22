"""
Cross-device unified BGP route-map comparator.

Consumes the per-router parser output produced by
:func:`backend.route_map_analysis.parser.analyze_router_config` and merges
them into one table keyed by peer-group:

    peer_group | route_map_in | route_map_out |
    hierarchy_in (prefix-list -> prefixes) | hierarchy_out | devices
"""

from __future__ import annotations

from collections import defaultdict


def _device_order_key(hostname: str) -> tuple:
    """Sort key — N01 before N02 to keep paired leaves grouped predictably."""
    h = (hostname or "").strip()
    if "N01" in h:
        return (0, h)
    if "N02" in h:
        return (1, h)
    return (2, h)


def build_unified_bgp_full_table(router_parsed_list: list) -> list:
    """
    Build the unified BGP table for the route-map analysis UI.

    ``router_parsed_list`` is a list of ``{hostname, vendor, model, parsed}``
    dicts where ``parsed`` is an :func:`analyze_router_config` return value.
    Returns a list of rows, one per peer-group, with merged route-map
    references and prefix-list hierarchies across all devices that use that
    peer-group.
    """
    if not router_parsed_list:
        return []

    def _norm_group(g):
        return (g or "").strip()

    by_group: dict = defaultdict(lambda: defaultdict(dict))
    for item in router_parsed_list:
        hostname = item.get("hostname") or ""
        p = item.get("parsed") or {}
        n2g = p.get("bgp_neighbor_to_group") or {}
        brm = p.get("bgp_route_maps") or {}
        rmp = p.get("route_map_prefix_lists") or {}
        pl = p.get("prefix_lists") or {}
        groups = set(_norm_group(g) for g in n2g.values())
        for group_norm in groups:
            if not group_norm:
                continue
            rm = brm.get(group_norm) or {}
            if not rm:
                for ip, g in n2g.items():
                    if _norm_group(g) == group_norm:
                        rm = brm.get(ip) or {}
                        break
            rm_in = (rm.get("in") or "").strip() or None
            rm_out = (rm.get("out") or "").strip() or None
            hierarchy_in = []
            if rm_in:
                for pl_name in rmp.get(rm_in) or []:
                    entries = pl.get(pl_name) or []
                    prefixes = sorted(set(e.get("prefix") or "" for e in entries if e.get("prefix")))
                    if pl_name or prefixes:
                        hierarchy_in.append({"prefix_list": pl_name, "prefixes": prefixes})
            hierarchy_out = []
            if rm_out:
                for pl_name in rmp.get(rm_out) or []:
                    entries = pl.get(pl_name) or []
                    prefixes = sorted(set(e.get("prefix") or "" for e in entries if e.get("prefix")))
                    if pl_name or prefixes:
                        hierarchy_out.append({"prefix_list": pl_name, "prefixes": prefixes})
            by_group[group_norm][hostname] = {
                "route_map_in": rm_in,
                "route_map_out": rm_out,
                "hierarchy_in": hierarchy_in,
                "hierarchy_out": hierarchy_out,
            }

    rows = []
    for group_norm in sorted(by_group.keys()):
        dev_data = by_group[group_norm]
        devices = sorted(dev_data.keys(), key=_device_order_key)
        hierarchy_in_merged: dict = defaultdict(set)
        hierarchy_out_merged: dict = defaultdict(set)
        route_map_in_set: set = set()
        route_map_out_set: set = set()
        for d in devices:
            r = dev_data[d]
            if r["route_map_in"]:
                route_map_in_set.add(r["route_map_in"])
            if r["route_map_out"]:
                route_map_out_set.add(r["route_map_out"])
            for h in r["hierarchy_in"]:
                hierarchy_in_merged[h["prefix_list"]].update(h["prefixes"])
            for h in r["hierarchy_out"]:
                hierarchy_out_merged[h["prefix_list"]].update(h["prefixes"])
        route_map_in = ", ".join(sorted(route_map_in_set)) if route_map_in_set else "—"
        route_map_out = ", ".join(sorted(route_map_out_set)) if route_map_out_set else "—"
        hierarchy_in = [{"prefix_list": k, "prefixes": sorted(v)} for k, v in sorted(hierarchy_in_merged.items())]
        hierarchy_out = [{"prefix_list": k, "prefixes": sorted(v)} for k, v in sorted(hierarchy_out_merged.items())]
        rows.append(
            {
                "peer_group": group_norm,
                "route_map_in": route_map_in,
                "route_map_out": route_map_out,
                "hierarchy_in": hierarchy_in,
                "hierarchy_out": hierarchy_out,
                "devices": devices,
            }
        )
    return rows


__all__ = [
    "_device_order_key",
    "build_unified_bgp_full_table",
]
