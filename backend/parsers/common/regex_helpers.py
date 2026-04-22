"""Regex-based extraction and counting helpers.

Extracted verbatim from ``backend/parse_output.py`` (Phase 1 of the
parse_output refactor — see ``docs/refactor/parse_output_split.md``).
"""

from __future__ import annotations

import re


def _extract_regex(text: str, pattern: str) -> str | None:
    """First capture group from regex, or None."""
    if not text or not pattern:
        return None
    try:
        m = re.search(pattern, text, re.MULTILINE | re.DOTALL)
        return m.group(1).strip() if m and m.lastindex else None
    except Exception:
        return None


def _count_regex_lines(text: str, pattern: str) -> int:
    """Count lines matching regex (no capture needed)."""
    if not text or not pattern:
        return 0
    try:
        return len(re.findall(pattern, text, re.MULTILINE))
    except Exception:
        return 0


__all__ = ["_extract_regex", "_count_regex_lines"]
