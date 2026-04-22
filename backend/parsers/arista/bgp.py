"""Arista BGP EVPN next-hop lookup.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

from typing import Any

from backend.parsers.common.arista_envelope import (
    _arista_result_obj,
    _arista_result_to_dict,
)


def parse_arista_bgp_evpn_next_hop(response: Any, index: int = 0) -> str | None:
    """Parse Arista 'show bgp evpn route-type mac-ip <ip> | json'. Returns nextHop IP or None."""
    obj = _arista_result_obj(response, index)
    if obj is None:
        return None
    try:
        data = _arista_result_to_dict(obj)
        if not data or not isinstance(data, dict):
            return None
        evpn_routes = data.get("evpnRoutes") or {}
        for route_data in evpn_routes.values():
            if not isinstance(route_data, dict):
                continue
            for p in route_data.get("evpnRoutePaths") or []:
                if isinstance(p, dict):
                    nh = (p.get("nextHop") or "").strip()
                    if nh:
                        return nh
    except Exception:
        pass
    return None


__all__ = ["parse_arista_bgp_evpn_next_hop"]
