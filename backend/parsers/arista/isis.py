"""Arista IS-IS adjacency parser.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

from typing import Any

from backend.parsers.common.arista_envelope import (
    _arista_result_obj,
    _arista_result_to_dict,
)


def _find_arista_isis_adjacency_list(data: Any) -> list:
    """Find list of adjacency entries from Arista 'show isis adjacency | json'."""
    if not data or not isinstance(data, dict):
        return []
    for key in ("adjacencyTable", "adjacencies", "adjacency"):
        val = data.get(key)
        if isinstance(val, list):
            return val
    for v in data.values():
        if isinstance(v, dict):
            out = _find_arista_isis_adjacency_list(v)
            if out:
                return out
        if isinstance(v, list) and v and isinstance(v[0], dict):
            if any("interface" in str(k).lower() or "intf" in str(k).lower() for k in (v[0] or {})):
                return v
    return []


def _parse_arista_isis_adjacency(raw_output: Any) -> dict[str, Any]:
    """Parse Arista 'show isis adjacency | json'. Returns isis_adjacency_count, isis_adjacency_rows (interface, state)."""
    obj = _arista_result_obj(raw_output, 0)
    inner = _arista_result_to_dict(obj) if isinstance(obj, dict) else None
    if not isinstance(inner, dict):
        return {"isis_adjacency_count": 0, "isis_adjacency_rows": [], "ISIS": "0"}
    rows: list[dict[str, Any]] = []
    adj_list = _find_arista_isis_adjacency_list(inner)
    for r in adj_list or []:
        if not isinstance(r, dict):
            continue
        intf = (
            r.get("interface") or r.get("interfaceName") or r.get("intf") or r.get("port")
            or next((r.get(k) for k in r if "interface" in str(k).lower() or "intf" in str(k).lower()), "")
        )
        state = (
            r.get("state") or r.get("adjacencyState") or r.get("status")
            or next((r.get(k) for k in r if "state" in str(k).lower() or "status" in str(k).lower()), "Unknown")
        )
        intf = str(intf).strip() if intf else ""
        if intf:
            rows.append({"interface": intf, "state": str(state).strip() or "Unknown"})
    count = len(rows)
    return {"ISIS": str(count), "isis_adjacency_rows": rows}


__all__ = ["_parse_arista_isis_adjacency", "_find_arista_isis_adjacency_list"]
