"""Value formatting helpers used by parsers.

Extracted verbatim from ``backend/parse_output.py`` (Phase 1 of the
parse_output refactor — see ``docs/refactor/parse_output_split.md``).
"""

from __future__ import annotations

from typing import Any


def _apply_value_subtract_and_suffix(f: dict, val: Any, result: dict, name: str) -> None:
    """Set result[name] from val; apply value_subtract_from (e.g. 100 - idle) and value_suffix (e.g. ' %')."""
    if val is None:
        result[name] = None
        return
    num = None
    if isinstance(val, (int, float)):
        num = val
    else:
        try:
            num = float(val)
        except (TypeError, ValueError):
            result[name] = str(val)
            return
    subtract = f.get("value_subtract_from")
    if subtract is not None:
        try:
            num = float(subtract) - num
        except (TypeError, ValueError):
            pass
    suffix = f.get("value_suffix")
    if suffix:
        result[name] = (str(int(num)) if num == int(num) else str(round(num, 2))) + suffix
    else:
        result[name] = num if isinstance(num, (int, float)) else str(num)


def _format_power_two_decimals(val: Any) -> str:
    """Format TX/RX power value to at most 2 decimal places. Non-numeric values returned as-is or '-'."""
    if val is None:
        return "-"
    s = str(val).strip()
    if not s or s == "-":
        return "-"
    try:
        f = float(s.replace(",", "."))
        return f"{f:.2f}"
    except ValueError:
        return s


__all__ = ["_apply_value_subtract_and_suffix", "_format_power_two_decimals"]
