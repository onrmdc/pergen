"""
RIPEStat-specific helpers for the BGP Looking Glass.

Each function below mirrors a public ``get_bgp_*`` helper from the original
``backend/bgp_looking_glass.py``. The orchestration / public entry-points live
in :mod:`backend.bgp_looking_glass.service`; this module owns only the
RIPEStat-specific request-shaping and response-parsing.

``_get_json`` is resolved via the ``backend.bgp_looking_glass`` package shim
at call time so test patches like
``unittest.mock.patch("backend.bgp_looking_glass._get_json", ...)`` continue to
reach this code unchanged after the god-module split.
"""

from __future__ import annotations

from backend.bgp_looking_glass.http_client import RIPESTAT_BASE
from backend.bgp_looking_glass.normalize import normalize_resource

__all__ = [
    "fetch_routing_status",
    "fetch_rpki_validation",
    "fetch_routing_history",
    "fetch_visibility",
    "fetch_looking_glass",
    "fetch_bgplay",
    "fetch_as_overview",
    "fetch_announced_prefixes",
]


def _shim_get_json(url, params=None, timeout=None):
    """Late-bound proxy onto :func:`backend.bgp_looking_glass._get_json`.

    Resolved at call time so that
    ``patch("backend.bgp_looking_glass._get_json", ...)`` reaches every
    network call originated from this module.
    """
    from backend import bgp_looking_glass as _shim

    if timeout is None:
        return _shim._get_json(url, params)
    return _shim._get_json(url, params, timeout=timeout)


# ---------------------------------------------------------------------------
# routing-status
# ---------------------------------------------------------------------------


def fetch_routing_status(resource: str) -> dict:
    """Return parsed routing-status data for an already-normalized resource."""
    url = f"{RIPESTAT_BASE}/routing-status/data.json"
    return _shim_get_json(url, {"resource": resource}) or {}


def parse_routing_status(data: dict) -> dict:
    """Extract origin/visibility/announced flags from a routing-status payload.

    Mirrors the inline parsing block from the original
    ``get_bgp_status`` implementation exactly.
    """
    out = {
        "announced": False,
        "withdrawn": True,
        "origin_as": None,
        "visibility_summary": None,
    }
    d = data.get("data", {}) or {}
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
                    out["visibility_summary"] = {
                        "peers_seeing": seeing,
                        "total_peers": total,
                    }
                    break
    if not out["visibility_summary"] and isinstance(d.get("visibility"), dict):
        v4 = d["visibility"].get("v4") or d["visibility"]
        out["visibility_summary"] = {
            "peers_seeing": (v4 or {}).get("ris_peers_seeing")
            or (v4 or {}).get("peers_seeing")
            or 0,
            "total_peers": (v4 or {}).get("total_ris_peers")
            or (v4 or {}).get("total_peers")
            or 0,
        }
    return out


# ---------------------------------------------------------------------------
# rpki-validation
# ---------------------------------------------------------------------------


def fetch_rpki_validation(origin_as: str, prefix: str) -> str:
    """Return RPKI status string for ``(origin_as, prefix)``.

    Returns ``"Unknown"`` on any error / missing payload — mirroring the
    original behaviour which never raised on an RPKI lookup failure.
    """
    rpki_url = f"{RIPESTAT_BASE}/rpki-validation/data.json"
    rpki_data = _shim_get_json(rpki_url, {"resource": origin_as, "prefix": prefix})
    if rpki_data and "_error" not in rpki_data and "data" in rpki_data:
        status = (rpki_data.get("data") or {}).get("status") or "unknown"
        return str(status).capitalize()
    return "Unknown"


# ---------------------------------------------------------------------------
# routing-history
# ---------------------------------------------------------------------------


def _entry_to_text(e: dict) -> str:
    """Serialize one routing-history entry to a stable, sortable text block."""
    lines = []
    if isinstance(e, dict):
        for k, v in sorted(e.items()):
            if v is not None and str(v).strip():
                lines.append(f"{k}: {v}")
    return "\n".join(lines) if lines else ""


def fetch_routing_history(resource: str) -> dict:
    """Return parsed routing-history payload, including current/previous diff text."""
    out = {"entries": [], "current": "", "previous": "", "error": None}
    url = f"{RIPESTAT_BASE}/routing-history/data.json"
    data = _shim_get_json(url, {"resource": resource})
    if data and "_error" in data:
        out["error"] = data["_error"]
        return out
    if not data or "data" not in data:
        return out

    entries = (data.get("data") or {}).get("entries") or []
    if not isinstance(entries, list):
        entries = []
    out["entries"] = entries

    if len(entries) >= 1:
        out["current"] = _entry_to_text(
            entries[0] if isinstance(entries[0], dict) else {"raw": str(entries[0])}
        )
    if len(entries) >= 2:
        out["previous"] = _entry_to_text(
            entries[1] if isinstance(entries[1], dict) else {"raw": str(entries[1])}
        )
    return out


# ---------------------------------------------------------------------------
# visibility
# ---------------------------------------------------------------------------


def fetch_visibility(resource: str) -> dict:
    """Return probes_seeing / total_probes / percentage / error."""
    out = {
        "probes_seeing": None,
        "total_probes": None,
        "percentage": None,
        "error": None,
    }
    url = f"{RIPESTAT_BASE}/visibility/data.json"
    data = _shim_get_json(url, {"resource": resource})
    if data and "_error" in data:
        out["error"] = data["_error"]
        return out
    if not data or "data" not in data:
        out["error"] = "No visibility data"
        return out

    d = data.get("data", {})
    seeing = (
        d.get("peers_seeing") or d.get("visibility", {}).get("peers_seeing")
        if isinstance(d.get("visibility"), dict)
        else None
    )
    total = (
        d.get("total_peers") or (d.get("visibility") or {}).get("total_peers")
        if isinstance(d.get("visibility"), dict)
        else None
    )
    if seeing is not None:
        out["probes_seeing"] = int(seeing)
    if total is not None:
        out["total_probes"] = int(total)
    if (
        out["probes_seeing"] is not None
        and out["total_probes"]
        and out["total_probes"] > 0
    ):
        out["percentage"] = round(100.0 * out["probes_seeing"] / out["total_probes"], 1)
    return out


# ---------------------------------------------------------------------------
# looking-glass
# ---------------------------------------------------------------------------


def fetch_looking_glass(resource: str) -> dict:
    """Return RRC + peer-list view from RIPEStat looking-glass endpoint."""
    out: dict = {"peers": [], "rrcs": [], "error": None}
    url = f"{RIPESTAT_BASE}/looking-glass/data.json"
    data = _shim_get_json(url, {"resource": resource})
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
        out["rrcs"].append(
            {"rrc_id": rrc_id, "location": location, "peer_count": len(peers_list)}
        )
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
            out["peers"].append(
                {
                    "rrc": rrc_id,
                    "location": location,
                    "peer_id": p.get("id") or peer_ip,
                    "ip": peer_ip,
                    "as_number": str(asn) if asn else "",
                    "prefix": (p.get("prefix") or "").strip(),
                    "as_path": as_path,
                }
            )
    return out


# ---------------------------------------------------------------------------
# bgplay
# ---------------------------------------------------------------------------


def fetch_bgplay(
    resource: str,
    starttime: str | None = None,
    endtime: str | None = None,
) -> dict:
    """Return parsed bgplay path-changes window. Mirrors original get_bgp_play."""
    import time as _time

    out: dict = {
        "query_starttime": None,
        "query_endtime": None,
        "path_changes": [],
        "error": None,
    }
    params: dict = {"resource": resource}
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
    data = _shim_get_json(url, params, timeout=20)
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
    prev_path: dict = {}
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
        ip, as_num, rrc = (
            _source_info(sid) if sid is not None else (None, None, None)
        )
        owner = _owner(as_num) if as_num is not None else ""
        path_changes.append(
            {
                "timestamp": ts,
                "source_id": sid,
                "source_ip": ip,
                "source_as": as_num,
                "source_owner": owner,
                "rrc": rrc,
                "target_prefix": tprefix,
                "previous_path": previous,
                "new_path": new_path,
            }
        )
        prev_path[key] = new_path

    out["path_changes"] = path_changes
    return out


# ---------------------------------------------------------------------------
# as-overview / announced-prefixes
# ---------------------------------------------------------------------------


def _clean_asn(asn: str | None) -> str:
    return (asn or "").strip().replace("AS", "").replace("as", "").strip()


def fetch_as_overview(asn: str) -> dict:
    """RIPEStat as-overview holder/name lookup. Mirrors original get_bgp_as_info."""
    asn_clean = _clean_asn(asn)
    if not asn_clean or not asn_clean.isdigit():
        return {"asn": asn_clean or asn, "name": None, "error": "Invalid ASN"}
    resource = f"AS{asn_clean}"
    url = f"{RIPESTAT_BASE}/as-overview/data.json"
    data = _shim_get_json(url, {"resource": resource})
    if data and "_error" in data:
        return {"asn": resource, "name": None, "error": data["_error"]}
    if not data or "data" not in data:
        return {"asn": resource, "name": None}
    holder = (data.get("data") or {}).get("holder")
    name = (holder or "").strip() or None
    return {"asn": resource, "name": name}


def fetch_announced_prefixes(asn: str) -> dict:
    """RIPEStat announced-prefixes for an AS. Mirrors original get_bgp_announced_prefixes."""
    asn_clean = _clean_asn(asn)
    if not asn_clean or not asn_clean.isdigit():
        return {"prefixes": [], "error": "Invalid ASN"}
    resource = f"AS{asn_clean}"
    url = f"{RIPESTAT_BASE}/announced-prefixes/data.json"
    data = _shim_get_json(url, {"resource": resource})
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
