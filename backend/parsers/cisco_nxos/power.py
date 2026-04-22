"""Cisco NX-OS power-supply parser.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

import json
from typing import Any

from backend.parsers.common.json_path import _find_key


def _parse_cisco_power(raw_output: Any) -> dict[str, Any]:
    """Parse Cisco 'show environment power'. powersup.TABLE_psinfo.ROW_psinfo, count ps_status == 'Ok'."""
    data = raw_output
    if isinstance(raw_output, str) and raw_output.strip().startswith("{"):
        try:
            data = json.loads(raw_output)
        except Exception:
            data = {}
    if not data:
        return {"Power supplies": ""}
    try:
        powersup = _find_key(data, "powersup")
        if not isinstance(powersup, dict):
            body = _find_key(data, "body")
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except Exception:
                    return {"Power supplies": ""}
            data = body if isinstance(body, dict) else data
            powersup = data.get("powersup") if isinstance(data, dict) else None
        if not isinstance(powersup, dict):
            return {"Power supplies": ""}
        table = powersup.get("TABLE_psinfo") or powersup.get("table_psinfo")
        if not isinstance(table, dict):
            return {"Power supplies": ""}
        rows = table.get("ROW_psinfo") or table.get("row_psinfo")
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            return {"Power supplies": ""}
        count = sum(1 for r in rows if isinstance(r, dict) and (str(r.get("ps_status") or "").strip() == "Ok"))
        return {"Power supplies": count}
    except Exception:
        return {"Power supplies": ""}


__all__ = ["_parse_cisco_power"]
