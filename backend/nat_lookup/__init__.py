"""
``backend.nat_lookup`` — back-compat shim for the legacy god-module.

The original 341-line ``backend/nat_lookup.py`` has been split into a cohesive
package (Phase 8 of the wave-3 refactor — see
``docs/refactor/wave3_roadmap.md``):

* ``backend.nat_lookup.ip_helpers``      — IPv4 validator (``_is_valid_ip``)
* ``backend.nat_lookup.xml_helpers``     — defusedxml parse + format helpers
* ``backend.nat_lookup.palo_alto.api``   — Panorama / firewall API call helpers
* ``backend.nat_lookup.service``         — orchestration (``nat_lookup``)

Every public + private symbol that callers and tests previously imported from
``backend.nat_lookup`` is re-exported here verbatim so existing import paths
and ``unittest.mock.patch("backend.nat_lookup.<symbol>", ...)`` targets keep
working unchanged. The ``service`` module deliberately looks up
``find_leaf_module``, ``load_inventory``, ``get_devices_by_tag`` and
``requests`` through this shim at call time so test patches land on the live
call sites.

Audit H-1 — defusedxml is a HARD requirement
============================================

``defusedxml`` is declared in ``requirements.txt`` and the import below is
intentionally direct (no try/except fallback). The previous fallback to
``xml.etree.ElementTree`` was removed because it silently downgraded the
parser to one that is vulnerable to billion-laughs / XXE attacks. A missing
dependency now raises ``ImportError`` at module-load time — which is the
correct, fail-loud behaviour for a security-relevant import.

This literal import line is asserted by
``tests/test_security_audit_batch4.py::test_nat_lookup_imports_defusedxml_unconditionally``
via ``inspect.getsource(backend.nat_lookup)``; do not remove it from this
file even though the actual XML parsing now lives in
:mod:`backend.nat_lookup.xml_helpers`.
"""

from __future__ import annotations

# Audit H-1: ``defusedxml`` is a HARD requirement (declared in
# requirements.txt). Previously this import was wrapped in try/except and
# silently fell back to the stdlib xml.etree parser, which is vulnerable
# to billion-laughs / XXE attacks. The fallback was removed so a missing
# dependency raises ImportError at module-load time instead of degrading
# the security posture at runtime.
from defusedxml import ElementTree as ET  # type: ignore[import-not-found]  # noqa: F401
from defusedxml.common import DefusedXmlException as _DefusedXmlError  # noqa: F401
from defusedxml.ElementTree import ParseError as _ETParseError  # noqa: F401

# ``requests`` is re-exported as a module attribute so that tests can do
# ``patch.object(backend.nat_lookup.requests, "get", ...)`` and have the
# patch reach :mod:`backend.nat_lookup.service` at call time.
import requests  # noqa: E402  # noqa: F401

# Late-bound module references — the orchestrator looks these up via this
# shim at call time, so test patches on these names propagate to the
# service layer unchanged.
from backend import find_leaf as find_leaf_module  # noqa: E402  # noqa: F401
from backend.inventory.loader import (  # noqa: E402  # noqa: F401
    get_devices_by_tag,
    load_inventory,
)
from backend.runners._http import DEVICE_TLS_VERIFY  # noqa: E402  # noqa: F401
from backend.runners.runner import _get_credentials  # noqa: E402  # noqa: F401

# Backwards-compat alias — kept only for any external imports of the old name.
_DefusedXmlException = _DefusedXmlError

# IP helpers (legacy private API)
from backend.nat_lookup.ip_helpers import (  # noqa: E402
    _IPV4_RE,
    _is_valid_ip,
)

# XML parse + format helpers (legacy private API)
from backend.nat_lookup.xml_helpers import (  # noqa: E402
    _find_nat_rule_name_in_response,
    _find_translated_ips_in_rule_config,
    _format_first_nat_rule_response,
    _format_translated_address_response,
)

# Public orchestration API — imported AFTER the helpers above so that
# ``service`` can look them up via this shim at call time (preserving
# ``patch("backend.nat_lookup.<symbol>", ...)`` semantics).
from backend.nat_lookup.service import nat_lookup  # noqa: E402

__all__ = [
    # Re-exported modules / constants for late binding + identity asserts
    "requests",
    "find_leaf_module",
    "load_inventory",
    "get_devices_by_tag",
    "DEVICE_TLS_VERIFY",
    "_get_credentials",
    # defusedxml symbols (H-1)
    "ET",
    "_DefusedXmlError",
    "_DefusedXmlException",
    "_ETParseError",
    # IP helpers
    "_IPV4_RE",
    "_is_valid_ip",
    # XML helpers (legacy private API)
    "_format_first_nat_rule_response",
    "_find_nat_rule_name_in_response",
    "_format_translated_address_response",
    "_find_translated_ips_in_rule_config",
    # Public entrypoint
    "nat_lookup",
]
