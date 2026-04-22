"""Duration / relative-time parsing helpers.

Extracted verbatim from ``backend/parse_output.py`` (Phase 1 of the
parse_output refactor — see ``docs/refactor/parse_output_split.md``).
"""

from __future__ import annotations

import re


def _parse_relative_seconds_ago(s: str) -> float | None:
    """Parse Cisco-style relative time like '1d02h', '23h', '30m', '14week(s) 2day(s)', 'never'. Returns seconds ago or None."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip().lower()
    if s in {"never", "-", ""}:
        return None
    total = 0.0
    for m in re.finditer(r"(\d+)\s*week\(s\)", s):
        try:
            total += float(m.group(1)) * 7 * 86400
        except (ValueError, TypeError):
            pass
    for m in re.finditer(r"(\d+)\s*day\(s\)", s):
        try:
            total += float(m.group(1)) * 86400
        except (ValueError, TypeError):
            pass
    for m in re.finditer(r"(\d+)\s*hour\(s\)", s):
        try:
            total += float(m.group(1)) * 3600
        except (ValueError, TypeError):
            pass
    for m in re.finditer(r"(\d+)\s*minute\(s\)", s):
        try:
            total += float(m.group(1)) * 60
        except (ValueError, TypeError):
            pass
    # Strip word forms so "2day(s)" does not also match as compact "2d"
    s_rest = s
    for token in (
        r"\d+\s*week\(s\)",
        r"\d+\s*day\(s\)",
        r"\d+\s*hour\(s\)",
        r"\d+\s*minute\(s\)",
    ):
        s_rest = re.sub(token, " ", s_rest, flags=re.IGNORECASE)
    s_rest = re.sub(r"\s+", " ", s_rest).strip()
    # Compact Cisco-style: 1d02h, 23h, 30m (remaining after word forms removed)
    for part in re.findall(r"(\d+)\s*([dhms])", s_rest):
        try:
            n = float(part[0])
        except (TypeError, ValueError):
            continue
        unit = part[1]
        if unit == "d":
            total += n * 86400
        elif unit == "h":
            total += n * 3600
        elif unit == "m":
            total += n * 60
        elif unit == "s":
            total += n
    if total <= 0:
        return None
    return total


def _parse_hhmmss_to_seconds(s: str) -> float | None:
    """Parse duration HH:MM:SS (e.g. '00:41:55' = 41 min 55 sec ago). Returns seconds or None."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s or s.lower() in ("never", "-", "n/a"):
        return None
    # HH:MM:SS or H:MM:SS
    m = re.match(r"^(\d+):(\d{1,2}):(\d{1,2})$", s)
    if m:
        try:
            h, mn, sec = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return h * 3600 + mn * 60 + sec
        except (ValueError, TypeError):
            return None
    return None


__all__ = ["_parse_relative_seconds_ago", "_parse_hhmmss_to_seconds"]
