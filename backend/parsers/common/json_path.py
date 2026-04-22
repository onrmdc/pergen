"""JSON-path walking and recursive-key search helpers.

Extracted verbatim from ``backend/parse_output.py`` (Phase 1 of the
parse_output refactor — see ``docs/refactor/parse_output_split.md``).

Behaviour is preserved byte-for-byte; the only change is the module
location. Existing callers continue to import from
``backend.parse_output`` via the back-compat shim.
"""

from __future__ import annotations

from typing import Any


def _get_path(data: Any, path: str) -> Any:
    """Get value from dict/list by dot path. Handles list: take first element."""
    if not path or data is None:
        return None
    parts = path.strip().split(".")
    for p in parts:
        if data is None:
            return None
        if isinstance(data, list):
            data = data[0] if data else None
        if isinstance(data, dict):
            data = data.get(p)
        else:
            return None
    return data


def _flatten_nested_list(
    data: Any, path: str, inner_path: str | list[str]
) -> list:
    """Get list at path; for each item get inner_path (dot-separated or list of paths) and flatten.
    If inner_path is a list (e.g. [TABLE_vrf.ROW_vrf, TABLE_process_adj.ROW_process_adj]), flatten through multiple levels."""
    val = _get_path(data, path)
    if not isinstance(val, list):
        return []
    if isinstance(inner_path, list):
        levels = inner_path
        if not levels:
            return val
        out = []
        for item in val:
            if not isinstance(item, dict):
                continue
            level_vals = [_get_path(item, levels[0])]
            for level in levels[1:]:
                next_vals = []
                for v in level_vals:
                    if isinstance(v, list):
                        for elem in v:
                            if isinstance(elem, dict):
                                next_vals.append(_get_path(elem, level))
                    elif isinstance(v, dict):
                        next_vals.append(_get_path(v, level))
                level_vals = [x for x in next_vals if x is not None]
            for v in level_vals:
                if isinstance(v, list):
                    out.extend(v)
                elif v is not None:
                    out.append(v)
        return out
    out = []
    for item in val:
        if not isinstance(item, dict):
            continue
        inner = _get_path(item, inner_path)
        if isinstance(inner, list):
            out.extend(inner)
        elif inner is not None:
            out.append(inner)
    return out


def _find_key(data: Any, key: str) -> Any:
    """Recursively find first value for key in nested dict."""
    if not isinstance(data, dict):
        return None
    if key in data:
        return data[key]
    for v in data.values():
        found = _find_key(v, key)
        if found is not None:
            return found
    return None


def _find_key_containing(data: Any, key_substr: str) -> Any:
    """Recursively find first value whose key contains key_substr (case-insensitive). Used for NX-API keys like smt_if_last_link_flapped."""
    if not isinstance(data, dict):
        return None
    sub = key_substr.lower()
    for k, v in data.items():
        if sub in str(k).lower():
            if v is not None and v != "" and (not isinstance(v, dict) or v):
                return v
        if isinstance(v, dict):
            found = _find_key_containing(v, key_substr)
            if found is not None:
                return found
        elif isinstance(v, list) and v:
            for item in v:
                if isinstance(item, dict):
                    found = _find_key_containing(item, key_substr)
                    if found is not None:
                        return found
    return None


def _find_list(data: Any, key_substr: str) -> list | None:
    """Find first list in nested dict whose key contains key_substr (e.g. 'ROW')."""
    if not isinstance(data, dict):
        return None
    for k, v in data.items():
        if key_substr.lower() in str(k).lower() and isinstance(v, list):
            return v
        found = _find_list(v, key_substr)
        if found is not None:
            return found
    return None


def _get_val(r: dict, *keys: str) -> str:
    """First matching key value from dict, stripped."""
    for k in keys:
        v = _find_key(r, k)
        if v is not None:
            return str(v).strip()
    return ""


__all__ = [
    "_get_path",
    "_flatten_nested_list",
    "_find_key",
    "_find_key_containing",
    "_find_list",
    "_get_val",
]
