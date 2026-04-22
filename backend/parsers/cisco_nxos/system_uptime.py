"""Cisco NX-OS system-uptime parser.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

import json
from typing import Any


def _parse_cisco_system_uptime(raw_output: Any) -> dict[str, Any]:
    """Parse 'show system uptime' NX-API JSON. Returns Uptime as 'Xd Xh Xm Xs'."""
    data = raw_output
    if isinstance(raw_output, str) and raw_output.strip().startswith("{"):
        try:
            data = json.loads(raw_output)
        except Exception:
            data = {}
    if not isinstance(data, dict):
        return {"Uptime": ""}
    d = str(data.get("sys_up_days") or "0").strip()
    h = str(data.get("sys_up_hrs") or "0").strip()
    m = str(data.get("sys_up_mins") or "0").strip()
    s = str(data.get("sys_up_secs") or "0").strip()
    return {"Uptime": f"{d}d {h}h {m}m {s}s"}


__all__ = ["_parse_cisco_system_uptime"]
