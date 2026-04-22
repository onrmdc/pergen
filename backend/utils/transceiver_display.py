"""
Display formatters for transceiver / interface UI cells.

Phase-2 deliverable — extracted verbatim from ``backend/app.py`` so
the route layer can import a tiny pure helper module instead of
co-locating presentation logic with route handlers.

These functions are intentionally side-effect free and have no Flask
dependency.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime


def transceiver_errors_display(st: Mapping) -> str:
    """Return CRC / input-error counts as ``"<crc>/<in>"``.

    Accepts whatever the parsers emit (``int``, ``float``, decorated
    string like ``"42 errors"``, or the canonical ``"-"`` placeholder
    for "no value").
    """

    def _n(key: str) -> int:
        v = str(st.get(key) or "").strip()
        if v in ("", "-"):
            return 0
        try:
            return int(float(v))
        except (ValueError, TypeError):
            m = re.search(r"-?\d+", v)
            return int(m.group(0)) if m else 0

    return f"{_n('crc_count')}/{_n('in_errors')}"


def transceiver_last_flap_display(st: Mapping) -> str:
    """Return the last flap timestamp as ``DDMMYYYY-HHMM`` (24h, local).

    Resolution order:
      1. ``last_status_change_epoch`` if it is a positive int/float;
      2. an already-formatted ``last_link_flapped`` string matching
         ``\\d{8}-\\d{4}``;
      3. ``"-"`` otherwise.
    """
    ep = st.get("last_status_change_epoch")
    if isinstance(ep, (int, float)) and ep > 0:
        try:
            return datetime.fromtimestamp(float(ep)).strftime("%d%m%Y-%H%M")
        except (ValueError, OSError, OverflowError):
            pass
    raw = str(st.get("last_link_flapped") or "").strip()
    if raw and re.match(r"^\d{8}-\d{4}$", raw):
        return raw
    return "-"
