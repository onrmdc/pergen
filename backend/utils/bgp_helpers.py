"""
BGP-related helper utilities (no Flask dependency).

Phase-2 deliverable — extracted verbatim from ``backend/app.py``.
"""
from __future__ import annotations

import re
from typing import Any


def wan_rtr_has_bgp_as(config_output: Any, asn_str: str, is_json: bool) -> bool:
    """Return ``True`` if ``config_output`` declares ``router bgp <asn>``.

    Inputs
    ------
    config_output : either a string blob (CLI ``show running-config``) or
        a dict from a JSON-mode runner (``{"cmds": {...}}``).
    asn_str : digit-only AS number string. Non-digit input → ``False``.
    is_json : selects the matcher; ``True`` walks dict keys, ``False``
        does a regex search across the text.
    """
    asn_str = (asn_str or "").strip()
    if not asn_str or not asn_str.isdigit():
        return False
    pattern = re.compile(
        r"router\s+bgp\s+" + re.escape(asn_str) + r"(?:\s|$)",
        re.I,
    )
    if is_json:
        data = config_output if isinstance(config_output, dict) else None
        if not data:
            return False
        cmds = data.get("cmds") or data
        if not isinstance(cmds, dict):
            return False
        return any(isinstance(key, str) and pattern.search(key) for key in cmds)
    text = config_output if isinstance(config_output, str) else ""
    return bool(pattern.search(text))
