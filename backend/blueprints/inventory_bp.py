"""
Inventory Blueprint — read-only listing endpoints.

Phase-9 deliverable.  Replaces the legacy ``api_fabrics``,
``api_sites``, ``api_halls``, ``api_roles``, ``api_devices``,
``api_devices_arista``, ``api_devices_by_tag``, ``api_inventory``
routes from ``backend/app.py``.

The Blueprint depends *only* on ``InventoryService`` (registered into
``app.extensions["inventory_service"]`` by the factory).  This is the
template every other domain Blueprint will follow in subsequent
phases — service in, ``jsonify`` out, no transport / parsing logic in
the route layer.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Blueprint, current_app, jsonify, request

if TYPE_CHECKING:  # pragma: no cover
    from backend.services.inventory_service import InventoryService

inventory_bp = Blueprint("inventory", __name__)


def _svc() -> InventoryService:
    """Lazy lookup of the registered ``InventoryService``.

    Phase 13: explicit ``RuntimeError`` rather than a raw ``KeyError`` so a
    request that hits this blueprint without going through ``create_app``
    (e.g. a unit test that builds its own Flask app) gets a meaningful
    diagnostic instead of a 500 with an opaque ``KeyError``.
    """
    svc = current_app.extensions.get("inventory_service")
    if svc is None:
        raise RuntimeError("inventory_service not registered; call create_app first")
    return svc


# --------------------------------------------------------------------------- #
# Hierarchy filters                                                           #
# --------------------------------------------------------------------------- #


@inventory_bp.route("/api/fabrics", methods=["GET"])
def api_fabrics():
    return jsonify({"fabrics": _svc().fabrics()})


@inventory_bp.route("/api/sites", methods=["GET"])
def api_sites():
    fabric = (request.args.get("fabric") or "").strip()
    if not fabric:
        return jsonify({"sites": []})
    return jsonify({"sites": _svc().sites(fabric)})


@inventory_bp.route("/api/halls", methods=["GET"])
def api_halls():
    fabric = (request.args.get("fabric") or "").strip()
    site = (request.args.get("site") or "").strip()
    if not fabric:
        return jsonify({"halls": []})
    return jsonify({"halls": _svc().halls(fabric, site)})


@inventory_bp.route("/api/roles", methods=["GET"])
def api_roles():
    fabric = (request.args.get("fabric") or "").strip()
    site = (request.args.get("site") or "").strip()
    hall = (request.args.get("hall") or "").strip() or None
    if not fabric:
        return jsonify({"roles": []})
    return jsonify({"roles": _svc().roles(fabric, site, hall)})


@inventory_bp.route("/api/devices", methods=["GET"])
def api_devices():
    fabric = (request.args.get("fabric") or "").strip()
    site = (request.args.get("site") or "").strip()
    role = (request.args.get("role") or "").strip() or None
    hall = (request.args.get("hall") or "").strip() or None
    if not fabric:
        return jsonify({"devices": []})
    devs = _svc().devices(fabric=fabric, site=site, role=role, hall=hall)
    return jsonify({"devices": devs})


@inventory_bp.route("/api/devices-arista", methods=["GET"])
def api_devices_arista():
    """Same query params as /api/devices but vendor-locked to Arista EOS."""
    fabric = (request.args.get("fabric") or "").strip()
    site = (request.args.get("site") or "").strip()
    role = (request.args.get("role") or "").strip() or None
    hall = (request.args.get("hall") or "").strip() or None
    if not fabric:
        return jsonify({"devices": []})
    devs = _svc().devices(fabric=fabric, site=site, role=role, hall=hall)
    # NOTE: legacy filter is intentionally inclusive — vendor=arista
    # OR model=eos.  Preserved verbatim to keep the golden test green.
    arista = [
        d for d in devs
        if (d.get("vendor") or "").strip().lower() == "arista"
        or (d.get("model") or "").strip().lower() == "eos"
    ]
    return jsonify({"devices": arista})


@inventory_bp.route("/api/devices-by-tag", methods=["GET"])
def api_devices_by_tag():
    """Lookup by tag with optional ``fabric=`` / ``site=`` post-filters."""
    tag = (request.args.get("tag") or "").strip()
    if not tag:
        return jsonify({"devices": []})
    fabric = (request.args.get("fabric") or "").strip()
    site = (request.args.get("site") or "").strip()
    matched = _svc().devices_by_tag(tag)
    if fabric:
        matched = [d for d in matched if (d.get("fabric") or "").strip() == fabric]
    if site:
        matched = [d for d in matched if (d.get("site") or "").strip() == site]
    devices = [
        {
            "hostname": (d.get("hostname") or "").strip(),
            "ip": (d.get("ip") or "").strip(),
        }
        for d in matched
    ]
    return jsonify({"devices": devices})


# --------------------------------------------------------------------------- #
# Full inventory dump (read-only)                                             #
# --------------------------------------------------------------------------- #


@inventory_bp.route("/api/inventory", methods=["GET"])
def api_inventory():
    """Full inventory as list (for the Inventory page).

    Returns ``{"inventory": [...]}`` to match the legacy contract that
    the SPA depends on (note: the *key* is ``inventory``, not
    ``devices`` — the latter is reserved for the hierarchy endpoints).
    """
    return jsonify({"inventory": _svc().all()})


# --------------------------------------------------------------------------- #
# Write routes (Phase 3 — moved from backend/app.py)                          #
# --------------------------------------------------------------------------- #


@inventory_bp.route("/api/inventory/device", methods=["POST"])
def api_inventory_device_add():
    """Add one device. Hostname and IP must be unique."""
    data = request.get_json(silent=True) or {}
    ok, body = _svc().add_device(data)
    return (jsonify(body), 200) if ok else (jsonify(body), 400)


@inventory_bp.route("/api/inventory/device", methods=["PUT"])
def api_inventory_device_update():
    """Update one device by ``current_hostname``. New hostname / IP must be unique."""
    data = request.get_json(silent=True) or {}
    ok, body, status = _svc().update_device(data)
    _ = ok  # status carries success/error semantics
    return jsonify(body), status


@inventory_bp.route("/api/inventory/device", methods=["DELETE"])
def api_inventory_device_delete():
    """Delete one device by hostname or IP query arg."""
    hostname = (request.args.get("hostname") or "").strip()
    ip = (request.args.get("ip") or "").strip()
    ok, body, status = _svc().delete_device(hostname=hostname, ip=ip)
    _ = ok
    return jsonify(body), status


@inventory_bp.route("/api/inventory/import", methods=["POST"])
def api_inventory_import():
    """Append rows from body. Body: ``{rows: [{hostname, ip, ...}, ...]}``.

    Unique hostname and IP enforced; duplicates and rows missing
    ``hostname`` are reported in the ``skipped`` array.
    """
    data = request.get_json(silent=True) or {}
    ok, body, status = _svc().import_devices(data.get("rows"))
    _ = ok
    return jsonify(body), status
