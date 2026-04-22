"""
Network-lookup Blueprint — find-leaf + NAT lookup.

Phase-8 deliverable. Replaces the three legacy ``api_find_leaf``,
``api_find_leaf_check_device``, and ``api_nat_lookup`` routes from
``backend/app.py``.

Both backing modules (``backend.find_leaf``, ``backend.nat_lookup``)
are already self-contained adapters around the underlying network
runners — the route layer is purely transport translation plus the
soft-failure exception envelopes the SPA expects.

Inventory CSV path resolution mirrors the legacy ``_inventory_path()``
helper: prefer the configured CSV, fall back to the example shipped
with the repo. We resolve it through the registered
``InventoryRepository`` instead of duplicating the logic so the test
fixtures (``mock_inventory_csv``) keep working.
"""
from __future__ import annotations

import logging

from flask import Blueprint, current_app, jsonify, request

from backend import credential_store as creds
from backend import find_leaf as find_leaf_module
from backend import nat_lookup as nat_lookup_module

_log_err = logging.getLogger("app.blueprints.network_lookup")

network_lookup_bp = Blueprint("network_lookup", __name__)


def _inventory_csv_path() -> str:
    """Look up the active inventory CSV path from the registered service.

    Audit H1: uses the public ``InventoryService.csv_path`` property
    (was reaching into ``svc._repo._csv_path``).
    """
    inv_svc = current_app.extensions.get("inventory_service")
    if inv_svc is None:
        # Defensive: should never happen because create_app registers
        # the service before the blueprint is reachable.
        from backend.config import settings

        return settings.INVENTORY_PATH
    return inv_svc.csv_path


@network_lookup_bp.route("/api/find-leaf", methods=["POST"])
def api_find_leaf():
    """Find leaf and interface for an IP. Body: ``{"ip": "1.2.3.4"}``."""
    data = request.get_json(silent=True) or {}
    search_ip = (data.get("ip") or "").strip()
    if not search_ip:
        return jsonify({"error": "ip is required"}), 400
    try:
        result = find_leaf_module.find_leaf(
            search_ip,
            current_app.config["SECRET_KEY"],
            creds,
            inventory_path=_inventory_csv_path(),
        )
        return jsonify(result)
    except Exception:  # noqa: BLE001 - soft-failure envelope
        # Audit H-5: log full detail server-side; return generic envelope.
        _log_err.exception("find-leaf failed for ip=%s", search_ip)
        return jsonify(
            {
                "found": False,
                "error": "find-leaf failed (see server logs)",
                "leaf_hostname": "",
                "leaf_ip": "",
                "interface": "",
                "vendor": "",
                "remote_vtep_addr": "",
                "physical_iod": "",
                "checked_devices": [],
            }
        )


@network_lookup_bp.route("/api/find-leaf-check-device", methods=["POST"])
def api_find_leaf_check_device():
    """Probe a single device. Body: ``{"ip", "hostname" | "device_ip"}``."""
    data = request.get_json(silent=True) or {}
    search_ip = (data.get("ip") or "").strip()
    hostname = (data.get("hostname") or "").strip()
    device_ip = (data.get("device_ip") or "").strip()
    identifier = hostname or device_ip
    if not search_ip:
        return (
            jsonify(
                {
                    "found": False,
                    "error": "ip is required",
                    "checked_hostname": identifier,
                }
            ),
            400,
        )
    if not identifier:
        return (
            jsonify(
                {
                    "found": False,
                    "error": "hostname or device_ip is required",
                    "checked_hostname": "",
                }
            ),
            400,
        )
    try:
        result = find_leaf_module.find_leaf_check_device(
            search_ip,
            identifier,
            current_app.config["SECRET_KEY"],
            creds,
            inventory_path=_inventory_csv_path(),
        )
        return jsonify(result)
    except Exception:  # noqa: BLE001 - soft-failure envelope
        # Audit H-5: log server-side, return generic envelope.
        _log_err.exception(
            "find-leaf-check-device failed for ip=%s identifier=%s",
            search_ip,
            identifier,
        )
        return jsonify(
            {
                "found": False,
                "error": "find-leaf check-device failed (see server logs)",
                "checked_hostname": identifier,
                "leaf_hostname": "",
                "leaf_ip": "",
                "interface": "",
                "vendor": "",
                "fabric": "",
                "hall": "",
                "site": "",
            }
        )


@network_lookup_bp.route("/api/nat-lookup", methods=["POST"])
def api_nat_lookup():
    """NAT lookup. Body: ``{"src_ip", "dest_ip", "fabric"?, "site"?, "debug"?}``.

    Audit M1: the ``debug`` flag is suppressed unless the operator
    explicitly opts in via ``PERGEN_ALLOW_DEBUG_RESPONSES=1``. The
    underlying helper would otherwise echo full Palo Alto API response
    bodies into the JSON payload (information disclosure).
    """
    import os as _os

    data = request.get_json(silent=True) or {}
    src_ip = (data.get("src_ip") or "").strip()
    dest_ip = (data.get("dest_ip") or "").strip() or "8.8.8.8"
    debug = bool(data.get("debug")) and (
        _os.environ.get("PERGEN_ALLOW_DEBUG_RESPONSES") == "1"
    )
    fabric = (data.get("fabric") or "").strip() or None
    site = (data.get("site") or "").strip() or None
    leaf_checked_devices = (
        data.get("leaf_checked_devices")
        if isinstance(data.get("leaf_checked_devices"), list)
        else None
    )
    if not src_ip:
        return jsonify({"ok": False, "error": "src_ip is required"}), 400
    try:
        result = nat_lookup_module.nat_lookup(
            src_ip,
            dest_ip,
            current_app.config["SECRET_KEY"],
            creds,
            inventory_path=_inventory_csv_path(),
            debug=debug,
            fabric=fabric,
            site=site,
            leaf_checked_devices=leaf_checked_devices,
        )
        return jsonify(result)
    except Exception:  # noqa: BLE001 - soft-failure envelope
        # Audit H-5: log server-side, return generic envelope.
        _log_err.exception(
            "nat-lookup failed for src=%s dest=%s", src_ip, dest_ip
        )
        return jsonify(
            {
                "ok": False,
                "error": "nat-lookup failed (see server logs)",
                "fabric": "",
                "site": "",
                "rule_name": "",
                "translated_ips": [],
                "firewall_hostname": "",
                "firewall_ip": "",
                "leaf_checked_devices": [],
                "debug": None,
            }
        )
