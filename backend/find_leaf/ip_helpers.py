"""
IP helpers for the leaf-search workflow.

Houses the IPv4 validator and the "rebuild leaf IP from current device + remote
VTEP" combinator used by both the Arista and Cisco strategies. Behaviour is
preserved verbatim from the original ``backend/find_leaf.py`` god-module so
that the legacy coverage tests in
``tests/test_legacy_coverage_find_leaf_nat.py`` continue to pass byte-for-byte.
"""

from __future__ import annotations

import re

__all__ = ["_IPV4_RE", "_is_valid_ip", "_leaf_ip_from_remote"]

# Simple IPv4 validation
_IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.){3}"
    r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])$"
)


def _is_valid_ip(ip: str) -> bool:
    return bool((ip or "").strip() and _IPV4_RE.match((ip or "").strip()))


def _leaf_ip_from_remote(current_ip: str, remote_vtep: str) -> str | None:
    """
    Build leaf IP: first 3 octets from current device (leaf-search), last octet from remote_vtep.
    Returns None if either IP is invalid.
    """
    current_ip = (current_ip or "").strip()
    remote_vtep = (remote_vtep or "").strip()
    if not _is_valid_ip(current_ip) or not _is_valid_ip(remote_vtep):
        return None
    parts_cur = current_ip.split(".")
    parts_rem = remote_vtep.split(".")
    if len(parts_cur) != 4 or len(parts_rem) != 4:
        return None
    return f"{parts_cur[0]}.{parts_cur[1]}.{parts_cur[2]}.{parts_rem[3]}"
