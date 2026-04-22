"""
Device Commands Blueprint — custom CLI / Arista runCmds / route-map.

Phase-10 deliverable. Replaces four legacy routes from
``backend/app.py``:

* POST ``/api/arista/run-cmds``  — run arbitrary eAPI runCmds with
                                    CommandValidator gating.
* GET  ``/api/router-devices``   — DCI / WAN router scope filter.
* POST ``/api/route-map/run``    — Arista route-map analysis pipeline.
* POST ``/api/custom-command``   — single-command SSH (show / dir).

The CommandValidator gate (Phase 13 hardening) is applied verbatim.
Inventory access goes through the registered ``InventoryService``.
"""
from __future__ import annotations

import logging

from flask import Blueprint, current_app, jsonify, request

from backend import credential_store as creds
from backend import route_map_analysis as route_map_analysis_module
from backend.runners.runner import _get_credentials
from backend.security.validator import CommandValidator

_log_err = logging.getLogger("app.blueprints.device_commands")

device_commands_bp = Blueprint("device_commands", __name__)


def _resolve_inventory_device(req_device: dict) -> dict | None:
    """Audit H-2: bind a request device to its canonical inventory row.

    The request body's ``credential``, ``vendor`` and ``model`` are NOT
    trusted — they're sourced from the inventory CSV. Match by hostname
    first, then by ip. Returns ``None`` when not found so the caller
    refuses to act.
    """
    inv_svc = current_app.extensions.get("inventory_service")
    if inv_svc is None or not isinstance(req_device, dict):
        return None
    devs = inv_svc.all()
    host = (req_device.get("hostname") or "").strip()
    ip = (req_device.get("ip") or "").strip()
    for d in devs:
        if host and (d.get("hostname") or "").strip() == host:
            return d
    for d in devs:
        if ip and (d.get("ip") or "").strip() == ip:
            return d
    return None


# --------------------------------------------------------------------------- #
# /api/arista/run-cmds                                                         #
# --------------------------------------------------------------------------- #


@device_commands_bp.route("/api/arista/run-cmds", methods=["POST"])
def api_arista_run_cmds():
    """Run arbitrary eAPI runCmds on one Arista device.

    Audit H-2: the request device is bound to the inventory. The
    inventory's ``credential`` and ``ip`` win over the request body's
    values, so a caller cannot bind an arbitrary IP to a privileged
    credential.
    """
    data = request.get_json(silent=True) or {}
    device = data.get("device")
    cmds = data.get("cmds")
    if not device or not isinstance(device, dict):
        return jsonify({"result": None, "error": "device object required"}), 400
    if not cmds or not isinstance(cmds, list):
        return jsonify({"result": None, "error": "cmds array required"}), 400
    canonical = _resolve_inventory_device(device)
    if canonical is None:
        return jsonify({"result": None, "error": "device not in inventory"}), 404
    ip = (canonical.get("ip") or "").strip()
    if not ip:
        return jsonify({"result": None, "error": "inventory device missing ip"}), 400

    cred_name = (canonical.get("credential") or "").strip()
    username, password = _get_credentials(
        cred_name, current_app.config["SECRET_KEY"], creds
    )
    if not username and not password:
        return (
            jsonify({"result": None, "error": f"no credential for '{cred_name}'"}),
            400,
        )

    # Audit M11: dict-form cmds must only contain ``cmd`` (and ``input``
    # for the special-case ``enable`` step). Any other key is a possible
    # injection vector — we strip them rather than forwarding.
    cmds_out: list = []
    for c in cmds:
        if isinstance(c, dict) and (c.get("cmd") or "").strip().lower() == "enable":
            cmds_out.append({"cmd": "enable", "input": password or ""})
        elif isinstance(c, dict):
            cmd_str = (c.get("cmd") or "").strip()
            ok, reason = CommandValidator.validate(cmd_str)
            if not ok:
                return jsonify({"result": None, "error": f"rejected command: {reason}"}), 400
            # Whitelist: only ``cmd`` is forwarded for non-enable dicts.
            cmds_out.append({"cmd": cmd_str})
        else:
            cmd_str = str(c).strip() if c is not None else ""
            ok, reason = CommandValidator.validate(cmd_str)
            if not ok:
                return jsonify({"result": None, "error": f"rejected command: {reason}"}), 400
            cmds_out.append(cmd_str)

    from backend.runners import arista_eapi

    results, err = arista_eapi.run_cmds(ip, username, password, cmds_out, timeout=60)
    if err:
        return jsonify({"result": None, "error": err}), 200
    return jsonify({"result": results, "error": None})


# --------------------------------------------------------------------------- #
# /api/router-devices                                                          #
# --------------------------------------------------------------------------- #


@device_commands_bp.route("/api/router-devices", methods=["GET"])
def api_router_devices():
    """Return DCI and/or WAN routers for route-map compare."""
    scope = (request.args.get("scope") or "all").strip().lower()
    inv_svc = current_app.extensions.get("inventory_service")
    if inv_svc is None:
        return jsonify({"devices": []})
    devs = inv_svc.all()

    def _role_lower(d: dict) -> str:
        return (d.get("role") or "").strip().lower()

    if scope == "dci":
        devices = [d for d in devs if _role_lower(d) == "dci-router"]
    elif scope == "wan":
        devices = [d for d in devs if _role_lower(d) == "wan-router"]
    else:
        devices = [d for d in devs if _role_lower(d) in ("dci-router", "wan-router")]
    return jsonify({"devices": devices})


# --------------------------------------------------------------------------- #
# /api/route-map/run                                                           #
# --------------------------------------------------------------------------- #


@device_commands_bp.route("/api/route-map/run", methods=["POST"])
def api_route_map_run():
    """Run route-map compare on selected (Arista EOS) devices."""
    data = request.get_json(silent=True) or {}
    devices = data.get("devices") or []
    if not isinstance(devices, list) or not devices:
        return (
            jsonify(
                {
                    "ok": False,
                    "rows": [],
                    "errors": [{"error": "devices list required"}],
                }
            ),
            400,
        )

    from backend.runners import arista_eapi

    parsed_list: list[dict] = []
    errors: list[dict] = []
    secret_key = current_app.config["SECRET_KEY"]

    for d in devices:
        hostname = (d.get("hostname") or "").strip()
        ip = (d.get("ip") or "").strip()
        vendor = (d.get("vendor") or "").strip()
        model = (d.get("model") or "").strip()
        cred_name = (d.get("credential") or "").strip()
        if not ip:
            errors.append({"hostname": hostname, "error": "missing ip"})
            continue
        username, password = _get_credentials(cred_name, secret_key, creds)
        if not username and not password:
            errors.append(
                {"hostname": hostname, "error": f"no credential for '{cred_name}'"}
            )
            continue
        is_arista = vendor.lower() in ("arista",) or model.lower() in ("eos",)
        if not is_arista:
            errors.append({"hostname": hostname, "error": "only Arista EOS supported"})
            continue
        results, err = arista_eapi.run_commands(
            ip, username, password, ["show running-config | json"], timeout=120
        )
        if err:
            errors.append({"hostname": hostname, "error": err})
            continue
        config = results[0] if results else None
        if not isinstance(config, dict):
            errors.append({"hostname": hostname, "error": "no JSON config"})
            continue
        try:
            parsed = route_map_analysis_module.analyze_router_config(config)
            parsed_list.append(
                {
                    "hostname": hostname,
                    "vendor": vendor,
                    "model": model,
                    "parsed": parsed,
                }
            )
        except Exception:  # noqa: BLE001 - per-device soft fail
            # Audit L-1: log full detail server-side; envelope stays generic.
            _log_err.exception("route-map analysis failed for host=%s", hostname)
            errors.append(
                {"hostname": hostname, "error": "analysis failed (see server logs)"}
            )

    rows = route_map_analysis_module.build_unified_bgp_full_table(parsed_list)
    return jsonify({"ok": True, "rows": rows, "errors": errors})


# --------------------------------------------------------------------------- #
# /api/custom-command                                                          #
# --------------------------------------------------------------------------- #


@device_commands_bp.route("/api/custom-command", methods=["POST"])
def api_custom_command():
    """Single SSH command (show / dir only — CommandValidator enforced).

    Audit H-2: device must exist in inventory; credential resolved from
    inventory, never from the request body.
    """
    data = request.get_json(silent=True) or {}
    device = data.get("device")
    command = (data.get("command") or "").strip()
    if not device or not isinstance(device, dict):
        return jsonify({"error": "device object required"}), 400
    if not command:
        return jsonify({"error": "command is required"}), 400
    ok, reason = CommandValidator.validate(command)
    if not ok:
        return jsonify({"error": f"rejected command: {reason}"}), 400
    canonical = _resolve_inventory_device(device)
    if canonical is None:
        return jsonify({"error": "device not in inventory"}), 404
    ip = (canonical.get("ip") or "").strip()
    if not ip:
        return jsonify({"error": "inventory device missing ip"}), 400
    cred_name = (canonical.get("credential") or "").strip()
    username, password = _get_credentials(
        cred_name, current_app.config["SECRET_KEY"], creds
    )
    if not username and not password:
        return jsonify({"output": None, "error": f"no credential for '{cred_name}'"})
    from backend.runners import ssh_runner

    output, err = ssh_runner.run_command(ip, username, password, command)
    if err:
        return jsonify({"output": None, "error": err})
    return jsonify({"output": output or "", "error": None})
