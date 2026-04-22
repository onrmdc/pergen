"""
Resource-string normalization for the BGP Looking Glass.

Behaviour preserved verbatim from the original
``backend/bgp_looking_glass.py::normalize_resource``.
"""

from __future__ import annotations

import re

__all__ = ["normalize_resource"]


def normalize_resource(raw: str) -> tuple[str, str]:
    """
    Parse user input into a RIPEStat resource string.
    Returns (resource, kind) where kind is "prefix" or "asn".
    - Bare IPv4 (e.g. 1.1.1.0) -> add /24, kind prefix
    - Prefix (e.g. 1.1.1.0/24) -> as-is, kind prefix
    - AS number (e.g. 13335 or AS13335) -> ensure AS prefix, kind asn
    """
    s = (raw or "").strip()
    if not s:
        return ("", "")

    # AS: digits only or AS12345
    as_match = re.match(r"^(?:AS)?\s*(\d+)$", s, re.IGNORECASE)
    if as_match:
        num = int(as_match.group(1))
        if 1 <= num < 4200000000 and (num < 64512 or num > 65534):
            return (f"AS{num}", "asn")
        return (f"AS{num}", "asn")  # still return, let API validate

    # IPv4 with optional /prefix
    prefix_match = re.match(
        r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?:/(\d{1,2}))?$", s
    )
    if prefix_match:
        a, b, c, d = (
            int(prefix_match.group(1)),
            int(prefix_match.group(2)),
            int(prefix_match.group(3)),
            int(prefix_match.group(4)),
        )
        if 0 <= a <= 255 and 0 <= b <= 255 and 0 <= c <= 255 and 0 <= d <= 255:
            p = prefix_match.group(5)
            if p:
                plen = int(p)
                if 0 <= plen <= 32:
                    return (f"{a}.{b}.{c}.{d}/{plen}", "prefix")
            return (f"{a}.{b}.{c}.{d}/24", "prefix")
    return (s, "prefix")  # pass through, API may reject
