"""Arista CPU usage parser.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

from typing import Any

from backend.parsers.common.arista_envelope import _arista_result_obj


def _parse_arista_cpu(raw_output: Any) -> dict[str, Any]:
    """Parse Arista 'show processes top once | json'. cpuInfo['%Cpu(s)'].idle -> CPU usage = 100 - idle."""
    obj = _arista_result_obj(raw_output)
    if obj is None:
        return {"CPU usage": ""}
    try:
        cpu_info = obj.get("cpuInfo") or {}
        if not isinstance(cpu_info, dict):
            return {"CPU usage": ""}
        pct = cpu_info.get("%Cpu(s)")
        if isinstance(pct, dict):
            idle = pct.get("idle")
            if idle is not None:
                try:
                    used = round(100.0 - float(idle), 1)
                    return {"CPU usage": f"{used} %"}
                except (TypeError, ValueError):
                    pass
    except (TypeError, ValueError, KeyError, AttributeError):  # narrow audit HIGH-1
        pass
    return {"CPU usage": ""}


__all__ = ["_parse_arista_cpu"]
