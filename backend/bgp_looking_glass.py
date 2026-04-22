"""
BGP Looking Glass: RIPEStat (routing-status, routing-history, visibility, RPKI)
and PeeringDB. Used by /api/bgp/* routes. No credential required for public APIs.
"""
import re

import requests

RIPESTAT_BASE = "https://stat.ripe.net/data"
PEERINGDB_NET = "https://www.peeringdb.com/api/net"
DEFAULT_TIMEOUT = 12


def normalize_resource(raw: str) -> tuple[str, str]:
    """
    Parse user input into a RIPEStat resource string.
    Returns (resource, kind) where kind is "prefix" or "asn".
    - Bare IPv4 (e.g. 1.1.1.0) -> add /24, kind prefix
    - Prefix (e.g. 1.1.1.0/24) -> as-is, kind prefix
    - AS number (e.g. 13335 or AS13335) -> ensure AS prefix, kind asn
    """
    s = (raw or "").strip()
    if not s:
        return ("", "")

    # AS: digits only or AS12345
    as_match = re.match(r"^(?:AS)?\s*(\d+)$", s, re.IGNORECASE)
    if as_match:
        num = int(as_match.group(1))
        if 1 <= num < 4200000000 and (num < 64512 or num > 65534):
            return (f"AS{num}", "asn")
        return (f"AS{num}", "asn")  # still return, let API validate

    # IPv4 with optional /prefix
    prefix_match = re.match(
        r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?:/(\d{1,2}))?$", s
    )
    if prefix_match:
        a, b, c, d = int(prefix_match.group(1)), int(prefix_match.group(2)), int(prefix_match.group(3)), int(prefix_match.group(4))
        if 0 <= a <= 255 and 0 <= b <= 255 and 0 <= c <= 255 and 0 <= d <= 255:
            p = prefix_match.group(5)
            if p:
                plen = int(p)
                if 0 <= plen <= 32:
                    return (f"{a}.{b}.{c}.{d}/{plen}", "prefix")
            return (f"{a}.{b}.{c}.{d}/24", "prefix")
    return (s, "prefix")  # pass through, API may reject


def _get_json(url: str, params: dict | None = None, timeout: int = DEFAULT_TIMEOUT) -> dict | None:
    try:
        r = requests.get(url, params=params or {}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as e:
        return {"_error": str(e)[:200]}


def get_bgp_status(resource: str) -> dict:
    """
    Combined status: routing-status + RPKI (when prefix) + PeeringDB AS name.
    resource: normalized prefix or AS (e.g. 1.1.1.0/24 or AS13335).
    Returns dict with: announced, withdrawn, origin_as, rpki_status, as_name,
    visibility_summary, error (if any).
    """
    resource, kind = normalize_resource(resource)
    out = {
        "announced": None,
        "withdrawn": None,
        "origin_as": None,
        "rpki_status": "Unknown",
        "as_name": None,
        "visibility_summary": None,
        "error": None,
    }
    if not resource:
        out["error"] = "Empty or invalid resource"
        return out

    # Routing status
    url = f"{RIPESTAT_BASE}/routing-status/data.json"
    data = _get_json(url, {"resource": resource})
    if data and "_error" in data:
        out["error"] = data["_error"]
        return out
    if not data or "data" not in data:
        out["error"] = "No routing-status data"
        return out

    d = data.get("data", {})
    # routing-status: origins (prefix) or announced space (AS); first_seen/last_seen for visibility
    origins = d.get("origins") or []
    if not origins and "announcements" in d:
        origins = d.get("announcements") or []
    out["announced"] = len(origins) > 0
    out["withdrawn"] = not out["announced"]
    origin_as = None
    if origins:
        first = origins[0]
        if isinstance(first, dict):
            origin_as = first.get("origin") or first.get("origin_asn")
        elif isinstance(first, (int, str)):
            origin_as = first
    if origin_as is not None:
        out["origin_as"] = str(origin_as).replace("AS", "").strip()

    # Visibility from first_seen/last_seen or top-level visibility
    for key in ("last_seen", "first_seen"):
        node = d.get(key)
        if isinstance(node, dict):
            vis = node.get("visibility") or {}
            if isinstance(vis, dict):
                v4 = vis.get("v4") or vis
                seeing = v4.get("ris_peers_seeing") or v4.get("peers_seeing") or 0
                total = v4.get("total_ris_peers") or v4.get("total_peers") or 0
                if seeing or total:
                    out["visibility_summary"] = {"peers_seeing": seeing, "total_peers": total}
                    break
    if not out["visibility_summary"] and isinstance(d.get("visibility"), dict):
        v4 = d["visibility"].get("v4") or d["visibility"]
        out["visibility_summary"] = {
            "peers_seeing": (v4 or {}).get("ris_peers_seeing") or (v4 or {}).get("peers_seeing") or 0,
            "total_peers": (v4 or {}).get("total_ris_peers") or (v4 or {}).get("total_peers") or 0,
        }

    # RPKI: for prefix we need prefix + origin AS
    if kind == "prefix" and resource and out.get("origin_as"):
        rpki_url = f"{RIPESTAT_BASE}/rpki-validation/data.json"
        rpki_data = _get_json(rpki_url, {"resource": out["origin_as"], "prefix": resource})
        if rpki_data and "_error" not in rpki_data and "data" in rpki_data:
            status = (rpki_data.get("data") or {}).get("status") or "unknown"
            out["rpki_status"] = str(status).capitalize()
        elif rpki_data and "_error" in rpki_data:
            out["rpki_status"] = "Unknown"

    # PeeringDB AS name when we have an AS
    asn = out.get("origin_as") or (resource if kind == "asn" else None)
    if asn:
        asn_clean = str(asn).replace("AS", "").strip()
        pdb = _get_json(PEERINGDB_NET, {"asn": asn_clean})
        if pdb and "_error" not in pdb and "data" in pdb:
            data_list = pdb.get("data") or []
            if data_list and isinstance(data_list[0], dict):
                out["as_name"] = (data_list[0].get("name") or "").strip() or None

    return out


def get_bgp_history(resource: str) -> dict:
    """
    Routing history for diff (current vs previous). Returns dict with
    entries (list), current, previous (text for diff), error.
    """
    resource, _ = normalize_resource(resource)
    out = {"entries": [], "current": "", "previous": "", "error": None}
    if not resource:
        out["error"] = "Empty or invalid resource"
        return out

    url = f"{RIPESTAT_BASE}/routing-history/data.json"
    data = _get_json(url, {"resource": resource})
    if data and "_error" in data:
        out["error"] = data["_error"]
        return out
    if not data or "data" not in data:
        return out

    entries = (data.get("data") or {}).get("entries") or []
    if not isinstance(entries, list):
        entries = []
    out["entries"] = entries

    def _entry_to_text(e: dict) -> str:
        lines = []
        if isinstance(e, dict):
            for k, v in sorted(e.items()):
                if v is not None and str(v).strip():
                    lines.append(f"{k}: {v}")
        return "\n".join(lines) if lines else ""

    if len(entries) >= 1:
        out["current"] = _entry_to_text(entries[0] if isinstance(entries[0], dict) else {"raw": str(entries[0])})
    if len(entries) >= 2:
        out["previous"] = _entry_to_text(entries[1] if isinstance(entries[1], dict) else {"raw": str(entries[1])})

    return out


def get_bgp_visibility(resource: str) -> dict:
    """
    Visibility API: probes/peers seeing the resource. Returns dict with
    probes_seeing, total_probes, percentage, error.
    """
    resource, _ = normalize_resource(resource)
    out = {"probes_seeing": None, "total_probes": None, "percentage": None, "error": None}
    if not resource:
        out["error"] = "Empty or invalid resource"
        return out

    url = f"{RIPESTAT_BASE}/visibility/data.json"
    data = _get_json(url, {"resource": resource})
    if data and "_error" in data:
        out["error"] = data["_error"]
        return out
    if not data or "data" not in data:
        out["error"] = "No visibility data"
        return out

    d = data.get("data", {})
    seeing = d.get("peers_seeing") or d.get("visibility", {}).get("peers_seeing") if isinstance(d.get("visibility"), dict) else None
    total = d.get("total_peers") or (d.get("visibility") or {}).get("total_peers") if isinstance(d.get("visibility"), dict) else None
    if seeing is not None:
        out["probes_seeing"] = int(seeing)
    if total is not None:
        out["total_probes"] = int(total)
    if out["probes_seeing"] is not None and out["total_probes"] and out["total_probes"] > 0:
        out["percentage"] = round(100.0 * out["probes_seeing"] / out["total_probes"], 1)
    return out


def get_bgp_looking_glass(resource: str) -> dict:
    """
    Looking Glass: which RIS RRCs and peers see the resource.
    Returns dict with peers: [ { rrc, location, peer_id, ip, as_number, ... } ], error.
    """
    resource, _ = normalize_resource(resource)
    out = {"peers": [], "rrcs": [], "error": None}
    if not resource:
        out["error"] = "Empty or invalid resource"
        return out

    url = f"{RIPESTAT_BASE}/looking-glass/data.json"
    data = _get_json(url, {"resource": resource})
    if data and "_error" in data:
        out["error"] = data["_error"]
        return out
    if not data or "data" not in data:
        return out

    d = data.get("data", {})
    rrcs_list = d.get("rrcs") or []
    if not isinstance(rrcs_list, list):
        rrcs_list = []

    for rrc_entry in rrcs_list:
        if not isinstance(rrc_entry, dict):
            continue
        rrc_id = rrc_entry.get("rrc") or rrc_entry.get("id") or ""
        location = (rrc_entry.get("location") or "").strip() or str(rrc_id)
        peers_list = rrc_entry.get("peers") or []
        if not isinstance(peers_list, list):
            peers_list = []
        out["rrcs"].append({"rrc_id": rrc_id, "location": location, "peer_count": len(peers_list)})
        for p in peers_list:
            if not isinstance(p, dict):
                continue
            peer_ip = p.get("peer") or p.get("ip") or ""
            asn = p.get("as_number") or p.get("asn_origin") or p.get("asn") or ""
            raw_path = p.get("as_path")
            if isinstance(raw_path, str):
                as_path = [x.strip() for x in raw_path.split() if x.strip()]
            elif isinstance(raw_path, list):
                as_path = [str(x).strip() for x in raw_path if str(x).strip()]
            else:
                as_path = []
            out["peers"].append({
                "rrc": rrc_id,
                "location": location,
                "peer_id": p.get("id") or peer_ip,
                "ip": peer_ip,
                "as_number": str(asn) if asn else "",
                "prefix": (p.get("prefix") or "").strip(),
                "as_path": as_path,
            })
    return out


def get_bgp_play(
    resource: str,
    starttime: str | None = None,
    endtime: str | None = None,
) -> dict:
    """
    BGP play: path changes over a time window. Uses initial_state and events.
    starttime/endtime: ISO8601 or Unix. If omitted, last 24h (or RIPEStat default).
    Returns dict with query_starttime, query_endtime, path_changes: [ ... ], error.
    """
    import time as _time
    resource, _ = normalize_resource(resource)
    out = {"query_starttime": None, "query_endtime": None, "path_changes": [], "error": None}
    if not resource:
        out["error"] = "Empty or invalid resource"
        return out

    params = {"resource": resource}
    if endtime:
        params["endtime"] = endtime
    if starttime:
        params["starttime"] = starttime
    else:
        # Default: last 24h. RIPEStat often uses endtime - 8h if only endtime given.
        if not endtime:
            end_ts = int(_time.time())
            params["endtime"] = end_ts
            params["starttime"] = end_ts - 86400  # 24h back

    url = f"{RIPESTAT_BASE}/bgplay/data.json"
    data = _get_json(url, params, timeout=20)
    if data and "_error" in data:
        out["error"] = data["_error"]
        return out
    if not data or "data" not in data:
        out["error"] = "No bgplay data"
        return out

    d = data.get("data", {})
    out["query_starttime"] = d.get("query_starttime")
    out["query_endtime"] = d.get("query_endtime")
    initial_state = d.get("initial_state") or []
    events = d.get("events") or []
    sources = d.get("sources") or []
    nodes = d.get("nodes") or []
    if not isinstance(initial_state, list):
        initial_state = []
    if not isinstance(events, list):
        events = []
    if not isinstance(sources, list):
        sources = []
    if not isinstance(nodes, list):
        nodes = []

    def _source_info(sid):
        for s in sources:
            if isinstance(s, dict) and str(s.get("id")) == str(sid):
                return s.get("ip"), s.get("as_number"), s.get("rrc")
        return None, None, None

    def _owner(asn):
        for n in nodes:
            if isinstance(n, dict) and str(n.get("as_number")) == str(asn):
                return (n.get("owner") or "").strip()
        return ""

    # initial_state: list of { source_id, target_prefix, path? }
    prev_path = {}
    for ist in initial_state:
        if not isinstance(ist, dict):
            continue
        sid = ist.get("source_id")
        tprefix = ist.get("target_prefix") or ist.get("attrs", {}).get("target_prefix")
        path = ist.get("path") or (ist.get("attrs") or {}).get("path") or []
        if sid is not None and tprefix is not None:
            prev_path[(sid, tprefix)] = path if isinstance(path, list) else []

    path_changes = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        attrs = ev.get("attrs") or ev
        sid = attrs.get("source_id") or ev.get("source_id")
        tprefix = attrs.get("target_prefix") or ev.get("target_prefix")
        new_path = attrs.get("path") or ev.get("path") or []
        if not isinstance(new_path, list):
            new_path = []
        key = (sid, tprefix)
        previous = prev_path.get(key) or []
        ts = ev.get("timestamp") or ev.get("time") or ""
        ip, as_num, rrc = _source_info(sid) if sid is not None else (None, None, None)
        owner = _owner(as_num) if as_num is not None else ""
        path_changes.append({
            "timestamp": ts,
            "source_id": sid,
            "source_ip": ip,
            "source_as": as_num,
            "source_owner": owner,
            "rrc": rrc,
            "target_prefix": tprefix,
            "previous_path": previous,
            "new_path": new_path,
        })
        prev_path[key] = new_path

    out["path_changes"] = path_changes
    return out


def get_bgp_as_info(asn: str) -> dict:
    """
    AS holder/name from RIPEStat as-overview. asn: e.g. 9121 or AS9121.
    Returns { asn, name } or { asn, name, error }.
    """
    asn_clean = (asn or "").strip().replace("AS", "").replace("as", "").strip()
    if not asn_clean or not asn_clean.isdigit():
        return {"asn": asn_clean or asn, "name": None, "error": "Invalid ASN"}
    resource = f"AS{asn_clean}"
    url = f"{RIPESTAT_BASE}/as-overview/data.json"
    data = _get_json(url, {"resource": resource})
    if data and "_error" in data:
        return {"asn": resource, "name": None, "error": data["_error"]}
    if not data or "data" not in data:
        return {"asn": resource, "name": None}
    holder = (data.get("data") or {}).get("holder")
    name = (holder or "").strip() or None
    return {"asn": resource, "name": name}


def get_bgp_announced_prefixes(asn: str) -> dict:
    """
    Prefixes announced by an AS (RIPEStat announced-prefixes). asn: e.g. 9121 or AS9121.
    Returns { prefixes: ["1.2.3.0/24", ...], error? }.
    """
    asn_clean = (asn or "").strip().replace("AS", "").replace("as", "").strip()
    if not asn_clean or not asn_clean.isdigit():
        return {"prefixes": [], "error": "Invalid ASN"}
    resource = f"AS{asn_clean}"
    url = f"{RIPESTAT_BASE}/announced-prefixes/data.json"
    data = _get_json(url, {"resource": resource})
    if data and "_error" in data:
        return {"prefixes": [], "error": data["_error"]}
    if not data or "data" not in data:
        return {"prefixes": []}
    raw = data.get("data") or {}
    prefix_list = raw.get("prefixes") if isinstance(raw.get("prefixes"), list) else []
    out = []
    for p in prefix_list:
        if isinstance(p, dict) and p.get("prefix"):
            out.append(str(p["prefix"]).strip())
        elif isinstance(p, str) and p.strip():
            out.append(p.strip())
    return {"prefixes": out}
