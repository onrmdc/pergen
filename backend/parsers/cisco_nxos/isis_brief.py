"""Cisco NX-OS 'show isis interface brief' parser.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

import json
from typing import Any


def _find_isis_interface_brief_rows(data: Any) -> list:
    """Find list of row dicts from NX-API 'show isis interface brief' JSON."""
    if not data or not isinstance(data, dict):
        return []
    for key, val in data.items():
        if isinstance(val, list) and val and isinstance(val[0], dict):
            keys0 = list((val[0] or {}).keys())
            if any("intfb-name-out" in str(k) for k in keys0):
                return val
        if isinstance(val, dict):
            out = _find_isis_interface_brief_rows(val)
            if out:
                return out
        if isinstance(val, list) and val and isinstance(val[0], dict):
            keys0 = list((val[0] or {}).keys())
            if any("intfb-ready-state-out" in str(k) for k in keys0):
                return val
    return []


def _parse_cisco_isis_interface_brief(raw_output: Any) -> dict[str, Any]:
    """Parse 'show isis interface brief' NX-API JSON. Returns isis_ready_count, isis_up_count, isis_interface_rows."""
    data = raw_output
    if isinstance(raw_output, str) and raw_output.strip().startswith("{"):
        try:
            data = json.loads(raw_output)
        except Exception:
            data = {}
    rows = _find_isis_interface_brief_rows(data)
    ready_count = 0
    up_count = 0
    isis_interface_rows: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        name_key = next(
            (k for k in r if "intfb-name-out" in str(k).lower() or "intfb_name_out" in str(k).lower()),
            None,
        )
        state_key = next(
            (k for k in r if "intfb-state-out" in str(k).lower() or "intfb_state_out" in str(k).lower()),
            None,
        )
        ready_key = next(
            (k for k in r if "intfb-ready-state-out" in str(k).lower() or "intfb_ready_state_out" in str(k).lower()),
            None,
        )
        if not name_key or not ready_key:
            continue
        ready_val = (r.get(ready_key) or "").strip()
        intf_name = (r.get(name_key) or "").strip()
        if not intf_name.startswith("Ethernet") or "loopback" in intf_name.lower():
            continue
        state_out = (r.get(state_key) or "").strip() if state_key else "Down"
        isis_interface_rows.append({"interface": intf_name, "state": "Up" if state_out.lower() == "up" else "Down"})
        if ready_val != "Ready":
            continue
        ready_count += 1
        if state_out.lower() == "up":
            up_count += 1
    return {"ISIS": f"{up_count}/{ready_count}", "isis_interface_rows": isis_interface_rows}


__all__ = [
    "_parse_cisco_isis_interface_brief",
    "_find_isis_interface_brief_rows",
]
