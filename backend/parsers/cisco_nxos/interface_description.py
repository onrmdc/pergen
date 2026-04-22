"""Cisco NX-OS interface description parser.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

from typing import Any

from backend.parsers.common.json_path import _find_key, _find_list
from backend.parsers.common.cisco_envelope import cisco_unwrap_body


def _parse_cisco_interface_description(raw_output: Any) -> dict[str, Any]:
    """Parse Cisco NX-API 'show interface description'. Returns interface_descriptions: dict interface -> description."""
    data = cisco_unwrap_body(raw_output)
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
