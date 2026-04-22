"""
``backend.bgp_looking_glass`` — back-compat shim for the legacy god-module.

The original 447-line ``backend/bgp_looking_glass.py`` has been split into a
cohesive package (Phase 8 of the wave-3 refactor — see
``docs/refactor/wave3_roadmap.md``):

* ``backend.bgp_looking_glass.normalize``    — ``normalize_resource``
* ``backend.bgp_looking_glass.http_client``  — SSRF-hardened ``_get_json``
                                               (audit M-01: ``allow_redirects=False``)
* ``backend.bgp_looking_glass.ripestat``     — RIPEStat-specific request/parse
* ``backend.bgp_looking_glass.peeringdb``    — PeeringDB AS-name lookup
* ``backend.bgp_looking_glass.service``      — orchestrating ``get_bgp_*`` API

Every public + private symbol that callers and tests previously imported from
``backend.bgp_looking_glass`` is re-exported here verbatim so existing import
paths and ``unittest.mock.patch("backend.bgp_looking_glass.<symbol>", ...)``
targets keep working unchanged. The submodules deliberately resolve
``_get_json`` through this shim at call time so test patches land on the live
network call sites.

Audit M-01 — SSRF-via-redirect defence is preserved verbatim
============================================================

The ``_get_json`` helper in :mod:`backend.bgp_looking_glass.http_client` keeps
``allow_redirects=False`` and explicitly converts any 3xx into an error
envelope. This contract is asserted by
``tests/test_security_ripestat_redirect_guard.py`` and must not regress.
See ``docs/security/audit_2026-04-22.md`` §3.2 M-01.
"""

from __future__ import annotations

# ``requests`` is re-exported as a module attribute so that tests can do
# ``patch.object(backend.bgp_looking_glass.requests, "get", ...)`` and
# ``patch("backend.bgp_looking_glass.requests.get", ...)``. Because Python
# caches imported modules, every submodule that does ``import requests``
# resolves to the same module object, so a patch here reaches every call
# site.
import requests  # noqa: F401

# HTTP boundary — constants + the single SSRF-hardened fetcher.
from backend.bgp_looking_glass.http_client import (  # noqa: E402
    DEFAULT_TIMEOUT,
    PEERINGDB_NET,
    RIPESTAT_BASE,
    _get_json,
)

# Pure parsing helper (no I/O).
from backend.bgp_looking_glass.normalize import normalize_resource  # noqa: E402

# Public orchestration API — imported AFTER ``_get_json`` so the
# ripestat / peeringdb modules can resolve it via this shim at call time.
from backend.bgp_looking_glass.service import (  # noqa: E402
    get_bgp_announced_prefixes,
    get_bgp_as_info,
    get_bgp_history,
    get_bgp_looking_glass,
    get_bgp_play,
    get_bgp_status,
    get_bgp_visibility,
)

__all__ = [
    # Re-exported modules / constants
    "requests",
    "RIPESTAT_BASE",
    "PEERINGDB_NET",
    "DEFAULT_TIMEOUT",
    # Network boundary helper (legacy private API kept for tests)
    "_get_json",
    # Pure helper
    "normalize_resource",
    # Public entry-points
    "get_bgp_status",
    "get_bgp_history",
    "get_bgp_visibility",
    "get_bgp_looking_glass",
    "get_bgp_play",
    "get_bgp_as_info",
    "get_bgp_announced_prefixes",
]
