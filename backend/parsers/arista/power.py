"""Arista power-supply parser.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

from typing import Any

from backend.parsers.common.arista_envelope import _arista_result_obj


def _parse_arista_power(raw_output: Any) -> dict[str, Any]:
    """Parse Arista 'show environment power | json'. Count powerSupplies with state == 'ok'."""
    obj = _arista_result_obj(raw_output)
    if obj is None:
        return {"Power supplies": ""}
    try:
        supplies = obj.get("powerSupplies")
        if not isinstance(supplies, dict):
            return {"Power supplies": ""}
        count = sum(1 for v in supplies.values() if isinstance(v, dict) and (str(v.get("state") or "").strip().lower() == "ok"))
        return {"Power supplies": count}
    except (TypeError, ValueError, KeyError, AttributeError):  # narrow audit HIGH-1
        return {"Power supplies": ""}


__all__ = ["_parse_arista_power"]
