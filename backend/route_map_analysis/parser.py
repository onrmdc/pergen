"""
Arista ``show running-config | json`` parser for route-map / BGP analysis.

Extracts:

* ``ip prefix-list`` definitions (``_extract_prefix_lists``)
* ``route-map`` ↔ ``prefix-list`` mappings (``_extract_route_map_prefix_lists``)
* BGP neighbor → peer-group + per-neighbor inbound/outbound route-maps,
  including DCI ``vrf`` blocks (``_extract_bgp``)

The public entrypoint :func:`analyze_router_config` returns the unified
parsed dict that downstream comparator code consumes.
"""

from __future__ import annotations

import re


def _get_cmds(data: dict) -> dict:
    if not data or not isinstance(data, dict):
        return {}
    if "cmds" in data:
        return data.get("cmds") or {}
    return data


def _extract_prefix_lists(cmds: dict) -> dict:
    """``ip prefix-list NAME`` -> list of ``{seq, action, prefix}`` entries."""
    out: dict = {}
    prefix = "ip prefix-list "
    for key, node in (cmds or {}).items():
        if not isinstance(key, str) or not key.startswith(prefix) or not isinstance(node, dict):
            continue
        name = key[len(prefix) :].strip()
        sub = node.get("cmds") or {}
        entries = []
        for cmd_key in sub:
            m = re.match(r"seq\s+(\d+)\s+(permit|deny)\s+(.+)", str(cmd_key).strip(), re.I)
            if m:
                entries.append(
                    {
                        "seq": int(m.group(1)),
                        "action": m.group(2).lower(),
                        "prefix": m.group(3).strip(),
                    }
                )
        entries.sort(key=lambda x: x["seq"])
        out[name] = entries
    return out


def _extract_route_map_prefix_lists(cmds: dict) -> dict:
    """``route-map NAME ACTION SEQ`` -> list of referenced prefix-list names."""
    out: dict = {}
    prefix = "route-map "
    for key, node in (cmds or {}).items():
        if not isinstance(key, str) or not key.startswith(prefix) or not isinstance(node, dict):
            continue
        rest = key[len(prefix) :].strip().split()
        if len(rest) < 3:
            continue
        map_name = rest[0]
        sub = node.get("cmds") or {}
        for cmd_key in sub:
            c = str(cmd_key).strip()
            if "match ip address prefix-list" not in c:
                continue
            m = re.search(r"prefix-list\s+(\S+)", c, re.I)
            if m:
                pl_name = m.group(1)
                out.setdefault(map_name, [])
                if pl_name not in out[map_name]:
                    out[map_name].append(pl_name)
    for k in out:
        out[k] = sorted(out[k])
    return out


def _find_router_bgp_cmds(cmds: dict) -> dict:
    for key, node in (cmds or {}).items():
        if isinstance(key, str) and key.strip().startswith("router bgp ") and isinstance(node, dict):
            return node.get("cmds") or {}
    return {}


def _extract_bgp(cmds: dict) -> tuple:
    """
    Parse ``router bgp`` block (and any nested ``vrf VRF`` sub-blocks) for:

    * ``neighbor X peer group G``
    * ``neighbor (G|X) route-map M in|out``

    Returns ``(neighbor_to_group, route_maps)``.
    """
    bgp = _find_router_bgp_cmds(cmds)
    neighbor_to_group: dict = {}
    route_maps: dict = {}

    def _process_bgp_cmd_list(bgp_cmds, group_override=None):
        for key in bgp_cmds or {}:
            k = (key or "").strip()
            if not k:
                continue
            m = re.match(r"neighbor\s+(\S+)\s+peer\s+group\s+(\S+)", k, re.I)
            if m:
                ip, group = m.group(1), m.group(2)
                neighbor_to_group[ip] = group_override or group
                continue
            m = re.match(r"neighbor\s+(\S+)\s+route-map\s+(\S+)\s+in\s*$", k, re.I)
            if m:
                target, map_name = m.group(1), m.group(2)
                route_maps.setdefault(target, {}).update({"in": map_name})
                if group_override:
                    neighbor_to_group[target] = group_override
                continue
            m = re.match(r"neighbor\s+(\S+)\s+route-map\s+(\S+)\s+out\s*$", k, re.I)
            if m:
                target, map_name = m.group(1), m.group(2)
                route_maps.setdefault(target, {}).update({"out": map_name})
                if group_override:
                    neighbor_to_group[target] = group_override
                continue
            if group_override and re.match(r"neighbor\s+(\S+)\s+", k, re.I):
                m = re.match(r"neighbor\s+(\S+)\s+", k, re.I)
                if m:
                    neighbor_to_group[m.group(1)] = group_override

    _process_bgp_cmd_list(bgp)
    for key, node in (bgp or {}).items():
        if not isinstance(key, str) or not key.strip().lower().startswith("vrf "):
            continue
        vrf_cmds = node.get("cmds") if isinstance(node, dict) else {}
        if not vrf_cmds:
            continue
        vrf_name = key.strip()[4:].strip()
        _process_bgp_cmd_list(vrf_cmds, group_override=vrf_name)

    for ip, group in list(neighbor_to_group.items()):
        if ip not in route_maps and group in route_maps:
            route_maps[ip] = dict(route_maps[group])

    return neighbor_to_group, route_maps


def analyze_router_config(data: dict) -> dict:
    """
    Top-level parser entrypoint.

    ``data`` is the raw Arista ``show running-config | json`` response (either
    the root object or one already containing the ``cmds`` key). Returns a
    flat dict with the four parsed sections used by
    :func:`backend.route_map_analysis.comparator.build_unified_bgp_full_table`.
    """
    cmds = _get_cmds(data)
    prefix_lists = _extract_prefix_lists(cmds)
    route_map_prefix_lists = _extract_route_map_prefix_lists(cmds)
    neighbor_to_group, route_maps = _extract_bgp(cmds)
    return {
        "prefix_lists": prefix_lists,
        "route_map_prefix_lists": route_map_prefix_lists,
        "bgp_neighbor_to_group": neighbor_to_group,
        "bgp_route_maps": route_maps,
    }


__all__ = [
    "_get_cmds",
    "_extract_prefix_lists",
    "_extract_route_map_prefix_lists",
    "_find_router_bgp_cmds",
    "_extract_bgp",
    "analyze_router_config",
]
