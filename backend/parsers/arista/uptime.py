"""Arista uptime parser.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

import json
from typing import Any


def _parse_arista_uptime(raw_output: Any) -> dict[str, Any]:
    """Parse Arista 'show uptime | json'. upTime is in seconds; convert to Xd Xh Xm Xs like Cisco."""
    data = raw_output
    if isinstance(raw_output, str) and raw_output.strip().startswith("{"):
        try:
            data = json.loads(raw_output)
        except (json.JSONDecodeError, ValueError, TypeError):  # narrow audit HIGH-1
            data = {}
    if not isinstance(data, dict):
        return {"Uptime": ""}
    try:
        total_secs = float(data.get("upTime") or 0)
    except (TypeError, ValueError):
        return {"Uptime": ""}
    total_secs = int(total_secs)
    days = total_secs // 86400
    rest = total_secs % 86400
    hours = rest // 3600
    rest = rest % 3600
    mins = rest // 60
    secs = rest % 60
    return {"Uptime": f"{days}d {hours}h {mins}m {secs}s"}


__all__ = ["_parse_arista_uptime"]
