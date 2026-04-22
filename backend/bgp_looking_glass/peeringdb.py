"""
PeeringDB AS-name lookup.

Behaviour preserved verbatim from the original
``backend/bgp_looking_glass.py``. The lookup is delegated through the package
shim so test patches on ``backend.bgp_looking_glass._get_json`` still reach
this code path at call time.
"""

from __future__ import annotations

from backend.bgp_looking_glass.http_client import PEERINGDB_NET

__all__ = ["lookup_as_name"]


def lookup_as_name(asn: str | int | None) -> str | None:
    """Return the PeeringDB ``name`` for a given AS, or ``None``.

    The ``_get_json`` helper is resolved via the ``backend.bgp_looking_glass``
    shim at call time so tests that do
    ``patch("backend.bgp_looking_glass._get_json", ...)`` still reach the
    network boundary after the god-module split.
    """
    if asn is None:
        return None
    asn_clean = str(asn).replace("AS", "").strip()
    if not asn_clean:
        return None

    # Late binding via the shim so unittest.mock.patch() reaches us.
    from backend import bgp_looking_glass as _shim

    pdb = _shim._get_json(PEERINGDB_NET, {"asn": asn_clean})
    if not pdb or "_error" in pdb or "data" not in pdb:
        return None
    data_list = pdb.get("data") or []
    if data_list and isinstance(data_list[0], dict):
        return (data_list[0].get("name") or "").strip() or None
    return None
