"""
Credentials Blueprint.

Audit C3/R1/R2 fix (post-Phase-13): the four credential routes now
delegate to ``CredentialService`` (via ``app.extensions``) instead of
the legacy ``backend.credential_store`` module. The new service uses
``EncryptionService`` (AES-128-CBC + HMAC, with tamper detection)
and enforces ``InputSanitizer.sanitize_credential_name`` on every
write.

Routes:
* ``GET    /api/credentials``                      — list
* ``POST   /api/credentials``                      — create (api_key | basic)
* ``DELETE /api/credentials/<name>``               — delete
* ``POST   /api/credentials/<name>/validate``      — login probe via inventory

The ``/validate`` endpoint still uses ``backend.runners.runner.run_device_commands``
because the runner contract is independent of the credential storage
backend; see ``DeviceService`` for the OOD alternative.
"""
from __future__ import annotations

import logging

from flask import Blueprint, current_app, g, jsonify, request

from backend.runners.runner import run_device_commands

_log = logging.getLogger("app.audit")  # audit-channel logger
_log_err = logging.getLogger("app.blueprints.credentials")

credentials_bp = Blueprint("credentials", __name__)


def _actor() -> str:
    """Return the resolved actor for the current request (audit C-2).

    ``flask.g.actor`` is populated by ``_install_api_token_gate``. Falls
    back to ``"anonymous"`` for any request that bypassed the gate
    (dev/test with no token configured).
    """
    return getattr(g, "actor", "anonymous")


def _credential_service():
    """Return the registered ``CredentialService`` or raise."""
    svc = current_app.extensions.get("credential_service")
    if svc is None:
        raise RuntimeError(
            "credential_service not registered; call create_app first"
        )
    return svc


def _inventory_service():
    svc = current_app.extensions.get("inventory_service")
    if svc is None:
        raise RuntimeError(
            "inventory_service not registered; call create_app first"
        )
    return svc


# --------------------------------------------------------------------------- #
# CRUD                                                                        #
# --------------------------------------------------------------------------- #


@credentials_bp.route("/api/credentials", methods=["GET"])
def api_credentials_list():
    """List credentials (names + methods + updated_at — no secrets)."""
    return jsonify({"credentials": _credential_service().list()})


@credentials_bp.route("/api/credentials", methods=["POST"])
def api_credentials_create():
    """Create or replace a credential. Validated by ``CredentialService.set``."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    method = (data.get("method") or "").strip().lower()
    if not name:
        return jsonify({"error": "name is required"}), 400
    if method not in ("api_key", "basic"):
        return jsonify({"error": "method must be api_key or basic"}), 400
    try:
        _credential_service().set(
            name,
            method=method,
            api_key=data.get("api_key"),
            username=data.get("username"),
            password=data.get("password"),
        )
        _log.info("audit credential.set actor=%s name=%s method=%s", _actor(), name, method)
        return jsonify({"ok": True})
    except ValueError as e:
        # InputSanitizer / repository-level validation failure (safe to surface)
        return jsonify({"error": str(e)}), 400
    except Exception as e:  # noqa: BLE001 - storage error must not 500 the client
        _log_err.exception("credential.set failed for name=%s", name)
        # Generic envelope (audit M2): never leak exception detail.
        _ = e
        return jsonify({"error": "credential storage error"}), 500


@credentials_bp.route("/api/credentials/<name>", methods=["DELETE"])
def api_credentials_delete(name: str):
    """Remove a credential. 404 when unknown."""
    if _credential_service().delete(name):
        _log.info("audit credential.delete actor=%s name=%s", _actor(), name)
        return jsonify({"ok": True})
    return jsonify({"error": "not found"}), 404


# --------------------------------------------------------------------------- #
# /validate — login probe                                                     #
# --------------------------------------------------------------------------- #


@credentials_bp.route("/api/credentials/<name>/validate", methods=["POST"])
def api_credentials_validate(name: str):
    """Validate by attempting login to the first inventory device using this credential.

    The /validate endpoint still depends on the *legacy* credential
    runner because ``runner.run_device_commands`` accepts a "creds module"
    object, not a service. The CredentialService is consulted first
    (cheap existence check); the runner then re-resolves the secret via
    its own (legacy-compatible) lookup. A future migration can move
    this to ``DeviceService.run_for_device``.
    """
    cred_svc = _credential_service()
    payload = cred_svc.get((name or "").strip())
    if not payload:
        return jsonify({"ok": False, "error": "Credential not found"}), 404

    devs = _inventory_service().all()
    cred_lower = (name or "").strip().lower()
    candidates = [
        d for d in devs if (d.get("credential") or "").strip().lower() == cred_lower
    ]
    if not candidates:
        return jsonify(
            {
                "ok": False,
                "device": None,
                "error": "No device in inventory uses this credential",
            }
        )
    device = candidates[0]
    hostname = (device.get("hostname") or device.get("ip") or "unknown").strip()

    # We still call the legacy runner — it expects a creds-module-shaped
    # adapter. Wrap the new service to look like one.
    from backend import credential_store as legacy_creds

    result = run_device_commands(device, current_app.config["SECRET_KEY"], legacy_creds)
    if result.get("error"):
        return jsonify({"ok": False, "device": hostname, "error": result["error"]})

    ran = [
        c
        for c in (result.get("commands") or [])
        if not c.get("error") and c.get("raw") is not None
    ]
    if not ran:
        return jsonify(
            {
                "ok": False,
                "device": hostname,
                "error": "No applicable commands for this device; cannot validate login.",
            }
        )

    parsed = result.get("parsed_flat") or {}
    uptime = (parsed.get("Uptime") or "").strip()
    out_payload: dict = {
        "ok": True,
        "device": result.get("hostname") or hostname,
        "message": "Logged in to {}.".format(result.get("hostname") or hostname),
    }
    if uptime:
        out_payload["uptime"] = uptime
    return jsonify(out_payload)
