"""
``backend.find_leaf`` — back-compat shim for the legacy god-module.

The original 325-line ``backend/find_leaf.py`` has been split into a cohesive
package (Phase 8 of the wave-3 refactor — see
``docs/refactor/wave3_roadmap.md``):

* ``backend.find_leaf.ip_helpers``           — IPv4 validator + leaf-IP combinator
* ``backend.find_leaf.strategies.arista``    — Arista BGP-EVPN search & completion
* ``backend.find_leaf.strategies.cisco``     — Cisco ARP-suppression search & completion
* ``backend.find_leaf.service``              — orchestration (parallel search + per-device entrypoint)

Every public + private symbol that callers and tests previously imported from
``backend.find_leaf`` is re-exported here verbatim so existing import paths and
``unittest.mock.patch("backend.find_leaf.<symbol>", ...)`` targets keep
working unchanged. The ``service`` module deliberately looks up
``_query_one_leaf_search`` / ``_complete_find_leaf_from_hit`` through this
shim at call time so test patches land on both call sites.
"""

from __future__ import annotations

from backend.find_leaf.ip_helpers import (
    _IPV4_RE,
    _is_valid_ip,
    _leaf_ip_from_remote,
)
from backend.find_leaf.strategies.arista import (
    _complete_arista_hit,
    _query_arista_leaf_search,
)
from backend.find_leaf.strategies.cisco import (
    _complete_cisco_hit,
    _query_cisco_leaf_search,
)


def _query_one_leaf_search(dev, search_ip, secret_key, cred_store_module):
    """
    Dispatch a single leaf-search query to the vendor strategy.

    Returns ``None`` when the credential lookup fails, the vendor is unsupported,
    or the IP is not present on the device. The exact return shape of a hit is
    vendor-specific and consumed by :func:`_complete_find_leaf_from_hit`.
    """
    vendor = (dev.get("vendor") or "").strip().lower()
    if vendor == "arista":
        return _query_arista_leaf_search(dev, search_ip, secret_key, cred_store_module)
    if vendor == "cisco":
        return _query_cisco_leaf_search(dev, search_ip, secret_key, cred_store_module)
    return None


def _complete_find_leaf_from_hit(hit, search_ip, devices, secret_key, cred_store_module):
    """Given a hit from :func:`_query_one_leaf_search`, complete the result (connect to leaf, get port)."""
    vendor = hit.get("vendor")
    if vendor == "arista":
        return _complete_arista_hit(hit, search_ip, devices, secret_key, cred_store_module)
    if vendor == "cisco":
        return _complete_cisco_hit(hit, search_ip, devices, secret_key, cred_store_module)
    # Unknown vendor — return the same empty envelope the legacy code returned.
    return {
        "found": True,
        "error": None,
        "leaf_hostname": "",
        "leaf_ip": "",
        "interface": "",
        "vendor": "",
        "fabric": "",
        "hall": "",
        "site": "",
        "remote_vtep_addr": "",
        "physical_iod": "",
    }


# Public orchestration API — imported AFTER the private helpers above so that
# ``service`` can look them up via this shim at call time (preserving
# ``patch("backend.find_leaf._query_one_leaf_search", ...)`` semantics).
from backend.find_leaf.service import find_leaf, find_leaf_check_device  # noqa: E402

__all__ = [
    # IP helpers
    "_IPV4_RE",
    "_is_valid_ip",
    "_leaf_ip_from_remote",
    # Strategy dispatch (legacy private API)
    "_query_one_leaf_search",
    "_complete_find_leaf_from_hit",
    # Public entrypoints
    "find_leaf",
    "find_leaf_check_device",
]
