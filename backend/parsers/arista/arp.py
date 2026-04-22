"""Arista ARP table interface lookup.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

from typing import Any

from backend.parsers.common.arista_envelope import (
    _arista_result_obj,
    _arista_result_to_dict,
)


def parse_arista_arp_interface_for_ip(response: Any, search_ip: str, index: int = 0) -> str | None:
    """Parse Arista 'show ip arp vrf all | json'. Return interface for search_ip (skip Vxlan), or None."""
    search_ip = (search_ip or "").strip()
    if not search_ip:
        return None
    obj = _arista_result_obj(response, index)
    if obj is None:
        return None
    try:
        data = _arista_result_to_dict(obj)
        if not data or not isinstance(data, dict):
            return None
        vrfs = data.get("vrfs") or {}
        for vrf_data in vrfs.values():
            if not isinstance(vrf_data, dict):
                continue
            for n in vrf_data.get("ipV4Neighbors") or []:
                if not isinstance(n, dict):
                    continue
                addr = (n.get("address") or "").strip()
                if addr != search_ip:
                    continue
                iface = (n.get("interface") or "").strip()
                if not iface or "Vxlan" in iface or "Vxlan1" in iface:
                    continue
                return iface
    except Exception:
        pass
    return None


__all__ = ["parse_arista_arp_interface_for_ip"]
