"""
Transceiver Blueprint — inventory + recover + clear-counters.

Phase-9 deliverable. Replaces the three legacy ``api_transceiver*``
routes from ``backend/app.py``.

The heavyweight ``/api/transceiver`` orchestration is delegated to
``TransceiverService.collect_rows()`` so this blueprint is < 30 lines
per route. Recover and clear-counters stay co-located here because
they are stateless and their per-vendor branching is small.

Recovery + clear-counters share a strict gate:

* Audit C4: only Leaf devices on host ports ``Ethernet1/1``–``Ethernet1/48``
  may be touched.
* Audit H7: the destination device + credential are RESOLVED FROM THE
  INVENTORY by hostname/ip, not trusted from the request body. An
  attacker who can call the API cannot rebind a device to a privileged
  credential by passing ``credential="tech"`` in the body.
* The attached credential must be ``method=basic`` (no API-key overrides).
* Audit A09: every successful recover / clear emits an audit log line.
* Audit M2: error envelopes do not echo Python exception detail.
"""
from __future__ import annotations

import json
import logging

from flask import Blueprint, current_app, g, jsonify, request

from backend import credential_store as creds
from backend.services.transceiver_service import TransceiverService
from backend.transceiver_recovery_policy import is_transceiver_recovery_allowed

_log = logging.getLogger("app.audit")
_log_err = logging.getLogger("app.blueprints.transceiver")

transceiver_bp = Blueprint("transceiver", __name__)


def _actor() -> str:
    """Audit C-2: resolved actor for the current request, or ``anonymous``."""
    return getattr(g, "actor", "anonymous")


def _service() -> TransceiverService:
    return TransceiverService(
        secret_key=current_app.config["SECRET_KEY"],
        credential_store=creds,
    )


def _resolve_inventory_device(req_device: dict) -> dict | None:
    """Look up the request device in the inventory; return canonical row.

    Audit H7: the request body's ``credential``, ``vendor``, and ``role``
    fields are NOT trusted. We match by ``hostname`` (preferred) then by
    ``ip``, and return the inventory-stored copy. If no match, return
    ``None`` so the caller can refuse to act.
    """
    inv_svc = current_app.extensions.get("inventory_service")
    if inv_svc is None:
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
# /api/transceiver — multi-device inventory                                    #
# --------------------------------------------------------------------------- #


@transceiver_bp.route("/api/transceiver", methods=["POST"])
def api_transceiver():
    """Run transceiver + status + descriptions across many devices."""
    data = request.get_json(silent=True) or {}
    devices = data.get("devices") or []
    if not isinstance(devices, list):
        return jsonify({"error": "devices array required"}), 400
    rows, errors, trace = _service().collect_rows(devices)
    return jsonify(
        {"rows": rows, "errors": errors, "interface_status_trace": trace}
    )


# --------------------------------------------------------------------------- #
# /api/transceiver/recover — bounce one or more interfaces                     #
# --------------------------------------------------------------------------- #


def _require_destructive_confirm() -> tuple[dict, int] | None:
    """Audit C4 + C-1 fail-closed: gate destructive routes behind the
    ``X-Confirm-Destructive: yes`` header.

    Activation:
    * Always **on** in production (``CONFIG_NAME == "production"``).
    * Otherwise opt-in via ``PERGEN_REQUIRE_DESTRUCTIVE_CONFIRM=1`` so dev
      and test environments stay frictionless.

    Returns the 403 response when the gate trips, else None to continue.
    """
    import os as _os

    from flask import current_app

    enabled = (
        _os.environ.get("PERGEN_REQUIRE_DESTRUCTIVE_CONFIRM") == "1"
        or current_app.config.get("CONFIG_NAME") == "production"
    )
    if not enabled:
        return None
    if (request.headers.get("X-Confirm-Destructive") or "").strip().lower() != "yes":
        return (
            {"error": "destructive operation requires X-Confirm-Destructive: yes header"},
            403,
        )
    return None


@transceiver_bp.route("/api/transceiver/recover", methods=["POST"])
def api_transceiver_recover():
    """Shutdown / no-shutdown a list of interfaces. Requires basic creds."""
    from backend.runners import interface_recovery

    confirm = _require_destructive_confirm()
    if confirm is not None:
        body, status = confirm
        return jsonify(body), status

    data = request.get_json(silent=True) or {}
    req_device = data.get("device")
    interfaces = data.get("interfaces")
    if not isinstance(req_device, dict):
        return jsonify({"error": "device object required", "commands": []}), 400
    if not (req_device.get("ip") or "").strip() and not (req_device.get("hostname") or "").strip():
        return jsonify({"error": "device ip or hostname required", "commands": []}), 400
    if not isinstance(interfaces, list):
        return jsonify({"error": "interfaces array required", "commands": []}), 400

    # Audit H7: resolve from inventory; never trust caller-supplied credential.
    device = _resolve_inventory_device(req_device)
    if device is None:
        return (
            jsonify({"error": "device not found in inventory", "commands": []}),
            404,
        )
    ip = (device.get("ip") or "").strip()
    if not ip:
        return jsonify({"error": "device ip required", "commands": []}), 400

    cred_name = (device.get("credential") or "").strip()
    payload = creds.get_credential(cred_name, current_app.config["SECRET_KEY"])
    if not payload or payload.get("method") != "basic":
        return (
            jsonify(
                {
                    "error": "recovery requires a username/password (basic) credential, not API key only",
                    "commands": [],
                }
            ),
            400,
        )
    username = payload.get("username") or ""
    password = payload.get("password") or ""
    if not username:
        return jsonify({"error": "credential username required", "commands": []}), 400

    ok_names, verr = interface_recovery.validate_interface_names(interfaces)
    if verr:
        return jsonify({"error": verr, "commands": []}), 400
    denied = [n for n in ok_names if not is_transceiver_recovery_allowed(device, n)]
    if denied:
        return (
            jsonify(
                {
                    "error": (
                        "Recovery is only allowed for Leaf devices on host ports Ethernet1/1 through Ethernet1/48. "
                        f"Not allowed: {denied!r}"
                    ),
                    "commands": [],
                }
            ),
            400,
        )

    vendor_l = (device.get("vendor") or "").strip().lower()
    if "cisco" in vendor_l:
        cmd_list = interface_recovery.build_cisco_nxos_recovery_lines(ok_names)
    elif "arista" in vendor_l:
        cmd_list = interface_recovery.build_arista_recovery_commands(ok_names)
    else:
        cmd_list = []

    try:
        if "cisco" in vendor_l:
            out, err = interface_recovery.recover_interfaces_cisco_nxos(
                ip, username, password, ok_names
            )
            if err:
                return (
                    jsonify({"ok": False, "error": err, "output": out, "commands": cmd_list}),
                    500,
                )
            status_text, st_err = (
                interface_recovery.fetch_interface_status_summary_cisco_nxos(
                    ip, username, password, ok_names
                )
            )
            payload = {
                "ok": True,
                "commands": cmd_list,
                "interface_status_output": status_text or "",
            }
            if st_err:
                payload["interface_status_warning"] = st_err
            _log.info(
                "audit transceiver.recover ok actor=%s host=%s ip=%s vendor=cisco interfaces=%s bounce_delay_s=%d",
                _actor(),
                (device.get("hostname") or "").strip(),
                ip,
                ok_names,
                interface_recovery._resolve_bounce_delay_sec(),
            )
            return jsonify(payload)
        if "arista" in vendor_l:
            results, err = interface_recovery.recover_interfaces_arista_eos(
                ip, username, password, ok_names
            )
            if err:
                return (
                    jsonify(
                        {"ok": False, "error": err, "results": results, "commands": cmd_list}
                    ),
                    500,
                )
            status_text, st_err = (
                interface_recovery.fetch_interface_status_summary_arista_eos(
                    ip, username, password, ok_names
                )
            )
            payload = {
                "ok": True,
                "commands": cmd_list,
                "interface_status_output": status_text or "",
            }
            if st_err:
                payload["interface_status_warning"] = st_err
            _log.info(
                "audit transceiver.recover ok actor=%s host=%s ip=%s vendor=arista interfaces=%s bounce_delay_s=%d",
                _actor(),
                (device.get("hostname") or "").strip(),
                ip,
                ok_names,
                interface_recovery._resolve_bounce_delay_sec(),
            )
            return jsonify(payload)
        return (
            jsonify({"error": "unsupported vendor (use Arista or Cisco)", "commands": cmd_list}),
            400,
        )
    except Exception:  # noqa: BLE001 - audit M2: never echo str(e) to caller
        _log_err.exception("transceiver.recover failed for host=%s", ip)
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "device runner failed (see server logs)",
                    "commands": cmd_list,
                }
            ),
            500,
        )


# --------------------------------------------------------------------------- #
# /api/transceiver/clear-counters                                              #
# --------------------------------------------------------------------------- #


@transceiver_bp.route("/api/transceiver/clear-counters", methods=["POST"])
def api_transceiver_clear_counters():
    """Clear counters on a single interface (privileged exec, not configure)."""
    from backend.runners import interface_recovery

    confirm = _require_destructive_confirm()
    if confirm is not None:
        body, status = confirm
        return jsonify(body), status

    data = request.get_json(silent=True) or {}
    req_device = data.get("device")
    interface = data.get("interface")
    if not isinstance(req_device, dict):
        return jsonify({"error": "device object required", "commands": []}), 400
    if not (req_device.get("ip") or "").strip() and not (req_device.get("hostname") or "").strip():
        return jsonify({"error": "device ip or hostname required", "commands": []}), 400
    if not interface or not isinstance(interface, str):
        return jsonify({"error": "interface string required", "commands": []}), 400

    # Audit H7: resolve device from inventory.
    device = _resolve_inventory_device(req_device)
    if device is None:
        return (
            jsonify({"error": "device not found in inventory", "commands": []}),
            404,
        )
    ip = (device.get("ip") or "").strip()
    if not ip:
        return jsonify({"error": "device ip required", "commands": []}), 400

    ok_names, verr = interface_recovery.validate_interface_names([interface])
    if verr or not ok_names:
        return jsonify({"error": verr or "invalid interface", "commands": []}), 400
    iface_clean = ok_names[0]
    if not is_transceiver_recovery_allowed(device, iface_clean):
        return (
            jsonify(
                {
                    "error": (
                        "Clear counters is only allowed for Leaf devices on host ports "
                        "Ethernet1/1 through Ethernet1/48."
                    ),
                    "commands": [],
                }
            ),
            400,
        )

    cred_name = (device.get("credential") or "").strip()
    payload = creds.get_credential(cred_name, current_app.config["SECRET_KEY"])
    if not payload or payload.get("method") != "basic":
        return (
            jsonify(
                {
                    "error": "clear counters requires a username/password (basic) credential",
                    "commands": [],
                }
            ),
            400,
        )
    username = payload.get("username") or ""
    password = payload.get("password") or ""
    if not username:
        return jsonify({"error": "credential username required", "commands": []}), 400

    vendor_l = (device.get("vendor") or "").strip().lower()
    cmd_list = [interface_recovery.build_clear_counters_command(iface_clean)]
    try:
        if "cisco" in vendor_l:
            out, err = interface_recovery.clear_counters_cisco_nxos(
                ip, username, password, iface_clean
            )
            if err:
                return (
                    jsonify({"ok": False, "error": err, "commands": cmd_list, "output": out}),
                    500,
                )
            _log.info(
                "audit transceiver.clear_counters ok actor=%s host=%s ip=%s vendor=cisco interface=%s",
                _actor(),
                (device.get("hostname") or "").strip(),
                ip,
                iface_clean,
            )
            return jsonify({"ok": True, "commands": cmd_list, "output": out or ""})
        if "arista" in vendor_l:
            results, err = interface_recovery.clear_counters_arista_eos(
                ip, username, password, iface_clean
            )
            if err:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": err,
                            "results": results,
                            "commands": cmd_list,
                        }
                    ),
                    500,
                )
            lines_out: list[str] = []
            if results:
                for r in results:
                    if isinstance(r, dict) and not r:
                        lines_out.append("(ok — no output from eAPI)")
                    elif isinstance(r, dict):
                        lines_out.append(json.dumps(r, indent=2))
                    else:
                        lines_out.append(str(r))
            else:
                lines_out.append("(no output)")
            _log.info(
                "audit transceiver.clear_counters ok actor=%s host=%s ip=%s vendor=arista interface=%s",
                _actor(),
                (device.get("hostname") or "").strip(),
                ip,
                iface_clean,
            )
            return jsonify(
                {"ok": True, "commands": cmd_list, "output": "\n".join(lines_out)}
            )
        return (
            jsonify({"error": "unsupported vendor (use Arista or Cisco)", "commands": cmd_list}),
            400,
        )
    except Exception:  # noqa: BLE001 - audit M2: never echo str(e) to caller
        _log_err.exception("transceiver.clear_counters failed for host=%s", ip)
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "device runner failed (see server logs)",
                    "commands": cmd_list,
                }
            ),
            500,
        )
