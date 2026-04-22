"""Helpers for unwrapping the Arista eAPI result envelope.

Arista's eAPI returns either a single response object or a list of
response objects, optionally wrapped under ``output`` or ``result``.
These two helpers normalize the envelope so vendor-specific parsers
can work with the inner data dict directly.

Extracted verbatim from ``backend/parse_output.py`` (Phase 1 of the
parse_output refactor — see ``docs/refactor/parse_output_split.md``).
"""

from __future__ import annotations

from typing import Any


def _arista_result_obj(raw_output: Any, index: int = 0) -> dict | None:
    """Get dict from Arista eAPI result (single object or list of results)."""
    if isinstance(raw_output, list) and raw_output:
        raw_output = raw_output[index] if index < len(raw_output) else raw_output[0]
    if isinstance(raw_output, dict):
        return raw_output
    return None


def _arista_result_to_dict(obj: Any) -> dict | None:
    """Unwrap Arista result to the actual data dict (e.g. output or result key)."""
    if not isinstance(obj, dict):
        return None
    if "output" in obj and isinstance(obj["output"], dict):
        return obj["output"]
    if "result" in obj:
        r = obj["result"]
        if isinstance(r, dict):
            return r
        if isinstance(r, list) and r and isinstance(r[0], dict):
            return r[0]
    return obj


__all__ = ["_arista_result_obj", "_arista_result_to_dict"]
