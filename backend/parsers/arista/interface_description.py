"""Arista 'show interfaces description' parser.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

from typing import Any

from backend.parsers.common.arista_envelope import (
    _arista_result_obj,
    _arista_result_to_dict,
)


def _parse_arista_interface_description(raw_output: Any) -> dict[str, Any]:
    """Parse Arista 'show interfaces description | json'. Returns interface_descriptions: dict interface -> description."""
    obj = _arista_result_obj(raw_output, 0)
    inner = _arista_result_to_dict(obj) if isinstance(obj, dict) else None
    if not isinstance(inner, dict):
        return {"interface_descriptions": {}}
    descs = inner.get("interfaceDescriptions")
    if not isinstance(descs, dict):
        return {"interface_descriptions": {}}
    out_desc: dict[str, str] = {}
    for k, v in descs.items():
        key = str(k).strip()
        if isinstance(v, dict) and v.get("description") is not None:
            out_desc[key] = str(v["description"]).strip()
        elif v is not None:
            out_desc[key] = str(v).strip()
        else:
            out_desc[key] = ""
    return {"interface_descriptions": out_desc}


__all__ = ["_parse_arista_interface_description"]
