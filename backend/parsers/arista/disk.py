"""Arista disk usage parser.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

from typing import Any

from backend.parsers.common.arista_envelope import _arista_result_obj


def _parse_arista_disk(raw_output: Any) -> dict[str, Any]:
    """Parse Arista 'show file systems | json'. flash: (size-free)/size*100."""
    obj = _arista_result_obj(raw_output)
    if obj is None:
        return {"Disk": ""}
    try:
        for fs in obj.get("fileSystems") or []:
            if not isinstance(fs, dict):
                continue
            if (fs.get("prefix") or "").strip().lower() == "flash:":
                try:
                    size = int(fs.get("size") or 0)
                    free = int(fs.get("free") or 0)
                    if size > 0:
                        pct = round(((size - free) / size) * 100, 1)
                        return {"Disk": f"{pct} %"}
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    return {"Disk": ""}


__all__ = ["_parse_arista_disk"]
