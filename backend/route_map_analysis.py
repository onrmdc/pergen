"""
Route-map / BGP analysis from Arista running-config (show running-config | json).
Parses: prefix-lists, route-maps (match ip address prefix-list), BGP neighbor peer group and route-map in/out.
Builds unified table: peer_group | route_map_in (prefix-lists + prefixes) | route_map_out | devices.
"""
import re
from collections import defaultdict


def _device_order_key(hostname: str) -> tuple:
    """Sort key: N01 before N02."""
    h = (hostname or "").strip()
    if "N01" in h:
        return (0, h)
    if "N02" in h:
        return (1, h)
    return (2, h)


def _get_cmds(data: dict) -> dict:
    if not data or not isinstance(data, dict):
        return {}
    if "cmds" in data:
        return data.get("cmds") or {}
    return data


def analyze_router_config(data: dict) -> dict:
    """
    data: Arista show running-config | json (root or with "cmds").
    Returns: prefix_lists, route_map_prefix_lists, bgp_neighbor_to_group, bgp_route_maps.
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


def _extract_prefix_lists(cmds: dict) -> dict:
    """ip prefix-list NAME -> seq X permit/deny Y."""
    out = {}
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
                entries.append({"seq": int(m.group(1)), "action": m.group(2).lower(), "prefix": m.group(3).strip()})
        entries.sort(key=lambda x: x["seq"])
        out[name] = entries
    return out


def _extract_route_map_prefix_lists(cmds: dict) -> dict:
    """route-map NAME ACTION SEQ -> match ip address prefix-list PL_NAME."""
    out = {}
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
    """neighbor X peer group G; neighbor G route-map M in/out. DCI: vrf VRF -> same."""
    bgp = _find_router_bgp_cmds(cmds)
    neighbor_to_group = {}
    route_maps = {}

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


def build_unified_bgp_full_table(router_parsed_list: list) -> list:
    """
    One table: peer_group | route_map_in (dropdown: prefix-lists -> prefixes) | route_map_out | devices.
    Returns: [ { peer_group, route_map_in, route_map_out, hierarchy_in, hierarchy_out, devices }, ... ]
    """
    if not router_parsed_list:
        return []

    def _norm_group(g):
        return (g or "").strip()

    by_group = defaultdict(lambda: defaultdict(dict))
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
        hierarchy_in_merged = defaultdict(set)
        hierarchy_out_merged = defaultdict(set)
        route_map_in_set = set()
        route_map_out_set = set()
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
        rows.append({
            "peer_group": group_norm,
            "route_map_in": route_map_in,
            "route_map_out": route_map_out,
            "hierarchy_in": hierarchy_in,
            "hierarchy_out": hierarchy_out,
            "devices": devices,
        })
    return rows
