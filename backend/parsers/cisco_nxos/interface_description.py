"""Cisco NX-OS interface description parser.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

import json
from typing import Any

from backend.parsers.common.json_path import _find_key, _find_list


def _parse_cisco_interface_description(raw_output: Any) -> dict[str, Any]:
    """Parse Cisco NX-API 'show interface description'. Returns interface_descriptions: dict interface -> description."""
    data = raw_output
    if isinstance(raw_output, dict) and "result" in raw_output:
        r = raw_output["result"]
        data = r[0] if isinstance(r, list) and r else r
    if isinstance(raw_output, list) and raw_output and isinstance(raw_output[0], dict):
        data = raw_output[0]
    body = data.get("body") if isinstance(data, dict) else None
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            body = None
    if body is not None and isinstance(body, dict):
        data = body
    if not isinstance(data, dict):
        return {"interface_descriptions": {}}
    out: dict[str, str] = {}
    rows = _find_list(data, "ROW_inter")
    if not rows:
        tbl = data.get("TABLE_interface") or data.get("table_interface")
        if isinstance(tbl, dict):
            rows = tbl.get("ROW_interface") or tbl.get("row_interface")
    if isinstance(rows, dict):
        rows = [rows]
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        intf = _find_key(r, "interface")
        desc = _find_key(r, "description") or _find_key(r, "desc") or _find_key(r, "port_desc")
        if intf:
            out[str(intf).strip()] = str(desc).strip() if desc else ""
    return {"interface_descriptions": out}


__all__ = ["_parse_cisco_interface_description"]
