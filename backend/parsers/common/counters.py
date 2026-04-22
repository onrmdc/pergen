"""Count helpers derived from JSON structures.

Extracted verbatim from ``backend/parse_output.py`` (Phase 1 of the
parse_output refactor — see ``docs/refactor/parse_output_split.md``).
"""

from __future__ import annotations

from typing import Any

from backend.parsers.common.json_path import _flatten_nested_list, _get_path


def _count_from_json(data: Any, path: str, flatten_inner_path: str | None = None) -> int:
    """Get list/dict at path and return length or count of items.
    If flatten_inner_path is set, path must be a list; each item's inner_path is flattened and counted."""
    if flatten_inner_path:
        val = _flatten_nested_list(data, path, flatten_inner_path)
        return len(val)
    val = _get_path(data, path)
    if isinstance(val, list):
        return len(val)
    if isinstance(val, dict):
        return len(val)
    if isinstance(val, (int, float)):
        return int(val)
    return 0


def _count_where(
    data: Any,
    path: str,
    where: dict,
    key_prefix: str | None = None,
    key_prefix_exclude: str | None = None,
    flatten_inner_path: str | None = None,
) -> int:
    """Get list or dict at path; count items where each key in where matches item.get(key).
    If value is a dict (e.g. Arista interface name -> props), iterate over .values().
    key_prefix: only count entries whose key starts with this.
    key_prefix_exclude: exclude entries whose key starts with this (e.g. exclude Management from total).
    flatten_inner_path: if set, path is list of dicts; flatten each item's inner_path to one list, then count_where."""
    if flatten_inner_path:
        val = _flatten_nested_list(data, path, flatten_inner_path)
    else:
        val = _get_path(data, path)
    if isinstance(val, dict):
        if key_prefix:
            val = [v for k, v in val.items() if isinstance(k, str) and k.startswith(key_prefix)]
        elif key_prefix_exclude:
            val = [v for k, v in val.items() if not (isinstance(k, str) and k.startswith(key_prefix_exclude))]
        else:
            val = list(val.values())
    if not isinstance(val, list):
        return 0
    n = 0
    for item in val:
        if not isinstance(item, dict):
            continue
        match = all(str(item.get(k)) == str(v) for k, v in where.items())
        if match:
            n += 1
    return n


def _get_from_dict_by_key_prefix(
    data: Any, path: str, key_prefix: str, value_key: str, divisor: float = 1
) -> Any:
    """Get dict at path, find first key that startswith key_prefix, return item[value_key] / divisor."""
    val = _get_path(data, path)
    if not isinstance(val, dict) or not key_prefix:
        return None
    for k, item in val.items():
        if isinstance(k, str) and k.startswith(key_prefix) and isinstance(item, dict):
            v = item.get(value_key)
            if v is not None and divisor and divisor != 0:
                try:
                    return float(v) / float(divisor)
                except (TypeError, ValueError):
                    return v
            return v
    return None


__all__ = [
    "_count_from_json",
    "_count_where",
    "_get_from_dict_by_key_prefix",
]
