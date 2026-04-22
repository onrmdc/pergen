"""Cisco NX-OS interface MTU parser.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

import json
from typing import Any

from backend.parsers.common.json_path import _find_key, _find_list


def _parse_cisco_interface_show_mtu(raw_output: Any) -> dict[str, Any]:
    """
    Parse Cisco NX-API 'show interface' JSON: TABLE_interface.ROW_interface[].eth_mtu per interface.
    """
    mtu_map: dict[str, str] = {}
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
        return {"interface_mtu_map": {}}
    tbl = data.get("TABLE_interface") or data.get("table_interface")
    rows = None
    if isinstance(tbl, dict):
        rows = tbl.get("ROW_interface") or tbl.get("row_interface")
    if not rows:
        rows = _find_list(data, "ROW_interface") or _find_list(data, "ROW_inter")
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return {"interface_mtu_map": {}}
    for r in rows:
        if not isinstance(r, dict):
            continue
        intf = r.get("interface") or _find_key(r, "interface")
        if not intf:
            continue
        eth_mtu = r.get("eth_mtu") or _find_key(r, "eth_mtu")
        mtu_map[str(intf).strip()] = str(eth_mtu).strip() if eth_mtu is not None else "-"
    return {"interface_mtu_map": mtu_map}


__all__ = ["_parse_cisco_interface_show_mtu"]
