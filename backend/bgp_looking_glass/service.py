"""
Top-level BGP Looking Glass orchestration.

The seven public ``get_bgp_*`` functions below are re-exported from
:mod:`backend.bgp_looking_glass` and preserve the original behaviour from
``backend/bgp_looking_glass.py`` byte-for-byte.

All RIPEStat / PeeringDB I/O is delegated to
:mod:`backend.bgp_looking_glass.ripestat` and
:mod:`backend.bgp_looking_glass.peeringdb`, which in turn resolve
``_get_json`` via the package shim at call time so existing
``unittest.mock.patch("backend.bgp_looking_glass._get_json", ...)`` targets
keep landing on the live network boundary.
"""

from __future__ import annotations

from backend.bgp_looking_glass.normalize import normalize_resource
from backend.bgp_looking_glass.peeringdb import lookup_as_name
from backend.bgp_looking_glass.ripestat import (
    fetch_announced_prefixes,
    fetch_as_overview,
    fetch_bgplay,
    fetch_looking_glass,
    fetch_routing_history,
    fetch_routing_status,
    fetch_rpki_validation,
    fetch_visibility,
    parse_routing_status,
)

__all__ = [
    "get_bgp_status",
    "get_bgp_history",
    "get_bgp_visibility",
    "get_bgp_looking_glass",
    "get_bgp_play",
    "get_bgp_as_info",
    "get_bgp_announced_prefixes",
]


def get_bgp_status(resource: str) -> dict:
    """
    Combined status: routing-status + RPKI (when prefix) + PeeringDB AS name.
    resource: normalized prefix or AS (e.g. 1.1.1.0/24 or AS13335).
    Returns dict with: announced, withdrawn, origin_as, rpki_status, as_name,
    visibility_summary, error (if any).
    """
    resource, kind = normalize_resource(resource)
    out: dict = {
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

    data = fetch_routing_status(resource)
    if data and "_error" in data:
        out["error"] = data["_error"]
        return out
    if not data or "data" not in data:
        out["error"] = "No routing-status data"
        return out

    parsed = parse_routing_status(data)
    out["announced"] = parsed["announced"]
    out["withdrawn"] = parsed["withdrawn"]
    out["origin_as"] = parsed["origin_as"]
    out["visibility_summary"] = parsed["visibility_summary"]

    # RPKI: for prefix we need prefix + origin AS
    if kind == "prefix" and resource and out.get("origin_as"):
        out["rpki_status"] = fetch_rpki_validation(out["origin_as"], resource)

    # PeeringDB AS name when we have an AS
    asn = out.get("origin_as") or (resource if kind == "asn" else None)
    if asn:
        out["as_name"] = lookup_as_name(asn)

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
    return fetch_routing_history(resource)


def get_bgp_visibility(resource: str) -> dict:
    """
    Visibility API: probes/peers seeing the resource. Returns dict with
    probes_seeing, total_probes, percentage, error.
    """
    resource, _ = normalize_resource(resource)
    out: dict = {
        "probes_seeing": None,
        "total_probes": None,
        "percentage": None,
        "error": None,
    }
    if not resource:
        out["error"] = "Empty or invalid resource"
        return out
    return fetch_visibility(resource)


def get_bgp_looking_glass(resource: str) -> dict:
    """
    Looking Glass: which RIS RRCs and peers see the resource.
    Returns dict with peers: [ { rrc, location, peer_id, ip, as_number, ... } ], error.
    """
    resource, _ = normalize_resource(resource)
    out: dict = {"peers": [], "rrcs": [], "error": None}
    if not resource:
        out["error"] = "Empty or invalid resource"
        return out
    return fetch_looking_glass(resource)


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
    resource, _ = normalize_resource(resource)
    out: dict = {
        "query_starttime": None,
        "query_endtime": None,
        "path_changes": [],
        "error": None,
    }
    if not resource:
        out["error"] = "Empty or invalid resource"
        return out
    return fetch_bgplay(resource, starttime=starttime, endtime=endtime)


def get_bgp_as_info(asn: str) -> dict:
    """
    AS holder/name from RIPEStat as-overview. asn: e.g. 9121 or AS9121.
    Returns { asn, name } or { asn, name, error }.
    """
    return fetch_as_overview(asn)


def get_bgp_announced_prefixes(asn: str) -> dict:
    """
    Prefixes announced by an AS (RIPEStat announced-prefixes). asn: e.g. 9121 or AS9121.
    Returns { prefixes: ["1.2.3.0/24", ...], error? }.
    """
    return fetch_announced_prefixes(asn)
