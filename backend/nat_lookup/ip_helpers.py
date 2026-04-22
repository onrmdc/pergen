"""
IPv4 validation helpers for the NAT-lookup package.

Extracted verbatim from the legacy ``backend/nat_lookup.py`` so that the
regex object identity (``_IPV4_RE``) and validator semantics
(``_is_valid_ip``) remain stable for any caller or test that imports
them via the ``backend.nat_lookup`` package shim.
"""

from __future__ import annotations

import re

_IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.){3}"
    r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])$"
)


def _is_valid_ip(ip: str) -> bool:
    """Return ``True`` iff ``ip`` is a non-empty, well-formed dotted-quad IPv4."""
    return bool((ip or "").strip() and _IPV4_RE.match((ip or "").strip()))


__all__ = ["_IPV4_RE", "_is_valid_ip"]
