"""
``backend.route_map_analysis`` — back-compat shim for the legacy god-module.

The original 232-line ``backend/route_map_analysis.py`` has been split into
a cohesive package (Phase 8 of the wave-3 refactor — see
``docs/refactor/wave3_roadmap.md``):

* ``backend.route_map_analysis.parser``     — Arista ``show running-config | json``
  parser: prefix-lists, route-map ↔ prefix-list mappings, BGP neighbor /
  peer-group / route-map in/out (including DCI ``vrf`` blocks).
* ``backend.route_map_analysis.comparator`` — cross-device unified BGP table
  builder (peer-group → merged route-maps + prefix-list hierarchies +
  device list, sorted N01-before-N02).

Every public + private symbol that callers and tests previously imported
from ``backend.route_map_analysis`` is re-exported here verbatim so existing
import paths and ``unittest.mock.patch("backend.route_map_analysis.<symbol>", ...)``
targets keep working unchanged.
"""

from __future__ import annotations

from backend.route_map_analysis.comparator import (
    _device_order_key,
    build_unified_bgp_full_table,
)
from backend.route_map_analysis.parser import (
    _extract_bgp,
    _extract_prefix_lists,
    _extract_route_map_prefix_lists,
    _find_router_bgp_cmds,
    _get_cmds,
    analyze_router_config,
)

__all__ = [
    # Parser internals (legacy private API)
    "_get_cmds",
    "_extract_prefix_lists",
    "_extract_route_map_prefix_lists",
    "_find_router_bgp_cmds",
    "_extract_bgp",
    # Comparator internals (legacy private API)
    "_device_order_key",
    # Public entrypoints
    "analyze_router_config",
    "build_unified_bgp_full_table",
]
