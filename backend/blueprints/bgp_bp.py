"""
BGP Looking-Glass Blueprint.

Phase-7 deliverable. Replaces the eight ``/api/bgp/*`` routes from
``backend/app.py``.

Seven of the routes are pure pass-throughs to the
``backend.bgp_looking_glass`` helper module — they live here only to
keep ``app.py`` lean and to give the BGP domain a single ownership
boundary.

The eighth route, ``/api/bgp/wan-rtr-match``, has real orchestration:
walk the inventory, dispatch a per-vendor runner, and check whether
the device's running-config declares ``router bgp <ASN>``. We delegate
that orchestration to ``InventoryService`` and the per-vendor runners
already imported by the legacy code; the matching itself uses the
extracted ``backend.utils.bgp_helpers.wan_rtr_has_bgp_as`` helper.
"""
from __future__ import annotations

import logging

from flask import Blueprint, current_app, jsonify, request

from backend import bgp_looking_glass as bgp_lg
from backend import credential_store as creds
from backend.runners.runner import _get_credentials
from backend.utils.bgp_helpers import wan_rtr_has_bgp_as

_log = logging.getLogger("app.blueprints.bgp")

bgp_bp = Blueprint("bgp", __name__)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _bgp_resource() -> str | None:
    """Return ``prefix`` if supplied, else ``ASNNNN`` from the ``asn`` arg."""
    prefix = (request.args.get("prefix") or "").strip()
    asn = (request.args.get("asn") or "").strip()
    if prefix:
        return prefix
    if asn:
        return f"AS{asn}" if not asn.upper().startswith("AS") else asn
    return None


def _normalised_asn() -> str:
    raw = (request.args.get("asn") or "").strip()
    return raw.replace("AS", "").replace("as", "").strip()


# --------------------------------------------------------------------------- #
# Pass-through routes                                                         #
# --------------------------------------------------------------------------- #


@bgp_bp.route("/api/bgp/status", methods=["GET"])
def api_bgp_status():
    """BGP status: routing-status + RPKI + PeeringDB AS name."""
    resource = _bgp_resource()
    if not resource:
        return jsonify({"error": "prefix or asn required"}), 400
    return jsonify(bgp_lg.get_bgp_status(resource))


@bgp_bp.route("/api/bgp/history", methods=["GET"])
def api_bgp_history():
    """BGP routing history for diff."""
    resource = _bgp_resource()
    if not resource:
        return jsonify({"error": "prefix or asn required"}), 400
    return jsonify(bgp_lg.get_bgp_history(resource))


@bgp_bp.route("/api/bgp/visibility", methods=["GET"])
def api_bgp_visibility():
    """BGP visibility (RIS probes)."""
    resource = _bgp_resource()
    if not resource:
        return jsonify({"error": "prefix or asn required"}), 400
    return jsonify(bgp_lg.get_bgp_visibility(resource))


@bgp_bp.route("/api/bgp/looking-glass", methods=["GET"])
def api_bgp_looking_glass():
    """RRCs and peers seeing the resource."""
    resource = _bgp_resource()
    if not resource:
        return jsonify({"error": "prefix or asn required"}), 400
    return jsonify(bgp_lg.get_bgp_looking_glass(resource))


@bgp_bp.route("/api/bgp/bgplay", methods=["GET"])
def api_bgp_bgplay():
    """Path changes in time window. Optional ``starttime`` / ``endtime``."""
    resource = _bgp_resource()
    if not resource:
        return jsonify({"error": "prefix or asn required"}), 400
    starttime = (request.args.get("starttime") or "").strip() or None
    endtime = (request.args.get("endtime") or "").strip() or None
    return jsonify(bgp_lg.get_bgp_play(resource, starttime=starttime, endtime=endtime))


@bgp_bp.route("/api/bgp/as-info", methods=["GET"])
def api_bgp_as_info():
    """AS holder/company name from RIPEStat."""
    asn = (request.args.get("asn") or "").strip()
    if not asn:
        return jsonify({"error": "asn required"}), 400
    return jsonify(bgp_lg.get_bgp_as_info(asn))


@bgp_bp.route("/api/bgp/announced-prefixes", methods=["GET"])
def api_bgp_announced_prefixes():
    """Prefixes announced by an AS (RIPEStat)."""
    asn = (request.args.get("asn") or "").strip()
    if not asn:
        return jsonify({"error": "asn required"}), 400
    return jsonify(bgp_lg.get_bgp_announced_prefixes(asn))


# --------------------------------------------------------------------------- #
# Orchestration: WAN-router BGP-AS match                                      #
# --------------------------------------------------------------------------- #


@bgp_bp.route("/api/bgp/wan-rtr-match", methods=["GET"])
def api_bgp_wan_rtr_match():
    """Find WAN-Router devices whose running-config declares ``router bgp <ASN>``.

    Inventory-driven: iterate WAN routers, dispatch per-vendor runner,
    grep for ``router bgp <asn>`` in the returned config (text or JSON).
    Soft-failure on any device error — the route always returns 200 with
    the matches it found.
    """
    asn_raw = _normalised_asn()
    if not asn_raw or not asn_raw.isdigit():
        return jsonify({"matches": [], "error": "asn required (digits only)"}), 400

    inv_svc = current_app.extensions.get("inventory_service")
    if inv_svc is None:
        return jsonify({"matches": [], "error": "inventory_service not registered"}), 500
    devs = inv_svc.all()

    secret_key = current_app.config["SECRET_KEY"]
    wan = [
        d
        for d in devs
        if (d.get("role") or "").strip().lower().replace(" ", "-") == "wan-router"
    ]
    matches: list[dict] = []
    for d in wan:
        hostname = (d.get("hostname") or "").strip() or (d.get("ip") or "?")
        ip = (d.get("ip") or "").strip()
        cred_name = (d.get("credential") or "").strip()
        vendor = (d.get("vendor") or "").strip()
        model = (d.get("model") or "").strip()
        if not ip:
            continue
        username, password = _get_credentials(cred_name, secret_key, creds)
        if not username and not password:
            continue
        found = False
        try:
            if vendor.lower() in ("arista",) or model.lower() in ("eos",):
                from backend.runners import arista_eapi

                results, err = arista_eapi.run_commands(
                    ip,
                    username,
                    password,
                    ["show running-config | json"],
                    timeout=90,
                )
                if not err and results:
                    cfg = results[0] if isinstance(results[0], dict) else None
                    if cfg:
                        found = wan_rtr_has_bgp_as(cfg, asn_raw, is_json=True)
            else:
                from backend.runners import ssh_runner

                out, err = ssh_runner.run_command(
                    ip,
                    username,
                    password,
                    "show running-config",
                    timeout=60,
                )
                if not err and out:
                    found = wan_rtr_has_bgp_as(out, asn_raw, is_json=False)
        except Exception as exc:  # noqa: BLE001 - soft-failure per device
            _log.debug("wan-rtr-match runner failed for %s: %s", hostname, exc)
        if found:
            matches.append(
                {
                    "hostname": hostname,
                    "fabric": (d.get("fabric") or "").strip() or "—",
                    "site": (d.get("site") or "").strip() or "—",
                }
            )
    return jsonify({"matches": matches})
