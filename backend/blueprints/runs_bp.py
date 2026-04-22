"""
Runs Blueprint — pre/post device runs + diff utility.

Phase-11 deliverable. Replaces eight legacy routes from
``backend/app.py``:

* POST /api/run/device              — single device exec
* POST /api/run/pre                 — full PRE pipeline (server-side run)
* POST /api/run/pre/create          — register PRE results from frontend
* POST /api/run/pre/restore         — replay a saved PRE into run state
* POST /api/run/post                — POST run + per-key diff
* POST /api/run/post/complete       — register POST results from frontend
* POST /api/diff                    — text unified diff utility
* GET  /api/run/result/<run_id>     — fetch stored run state

The in-memory ``_run_state`` dict is now a ``RunStateStore`` instance
on ``app.extensions["run_state_store"]``. Per-device diff computation
is delegated to ``ReportService.compare_runs`` so both ``api_run_post``
and ``api_run_post_complete`` share one implementation.
"""
from __future__ import annotations

import contextlib
import difflib
import uuid
from datetime import UTC, datetime

from flask import Blueprint, current_app, jsonify, request

from backend import credential_store as creds
from backend.runners.runner import run_device_commands

runs_bp = Blueprint("runs", __name__)


def _state_store():
    store = current_app.extensions.get("run_state_store")
    if store is None:
        raise RuntimeError("run_state_store not registered; call create_app first")
    return store


def _resolve_inventory_device(req_device: dict) -> dict | None:
    """Audit H-2: bind the request device to an inventory row.

    The request body's ``credential``, ``vendor``, ``model`` and ``role``
    are NOT trusted. We match by ``hostname`` first, then by ``ip``, and
    return the canonical inventory copy so any privileged fields (like
    ``credential``) come from the server-controlled CSV. Returns ``None``
    when the device is not in inventory — caller refuses to act.
    """
    inv_svc = current_app.extensions.get("inventory_service")
    if inv_svc is None:
        return None
    if not isinstance(req_device, dict):
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


def _bind_devices_to_inventory(devices: list) -> tuple[list[dict], list[dict]]:
    """Resolve every entry against inventory. Returns (resolved, rejected)."""
    resolved: list[dict] = []
    rejected: list[dict] = []
    for d in devices or []:
        canonical = _resolve_inventory_device(d) if isinstance(d, dict) else None
        if canonical is None:
            rejected.append(d if isinstance(d, dict) else {"raw": str(d)})
        else:
            resolved.append(canonical)
    return resolved, rejected


def _report_service():
    svc = current_app.extensions.get("report_service")
    if svc is None:
        raise RuntimeError("report_service not registered; call create_app first")
    return svc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _run_devices_inline(devices: list[dict]) -> list[dict]:
    """Run commands sequentially for each device using the legacy runner."""
    secret_key = current_app.config["SECRET_KEY"]
    return [run_device_commands(d, secret_key, creds) for d in devices]


# --------------------------------------------------------------------------- #
# Single-device exec                                                          #
# --------------------------------------------------------------------------- #


@runs_bp.route("/api/run/device", methods=["POST"])
def api_run_device():
    """Single-device exec.

    Audit H-2: the request body's device dict is bound to the inventory.
    The server uses the inventory-stored ``credential``, ``vendor`` and
    ``model`` — caller-supplied values for those fields are ignored.
    """
    data = request.get_json(silent=True) or {}
    device = data.get("device")
    if not device or not isinstance(device, dict):
        return jsonify({"error": "device object required"}), 400
    canonical = _resolve_inventory_device(device)
    if canonical is None:
        return jsonify({"error": "device not in inventory"}), 404
    result = run_device_commands(canonical, current_app.config["SECRET_KEY"], creds)
    return jsonify({"device_result": result})


# --------------------------------------------------------------------------- #
# PRE flows                                                                   #
# --------------------------------------------------------------------------- #


@runs_bp.route("/api/run/pre", methods=["POST"])
def api_run_pre():
    """Server-driven PRE: run commands here, store, return.

    Audit H-2: every device in the request is bound to the inventory.
    Devices not in inventory are rejected outright (not silently skipped).
    """
    data = request.get_json(silent=True) or {}
    devices = data.get("devices") or []
    if not isinstance(devices, list) or not devices:
        return jsonify({"error": "devices list required"}), 400
    bound, rejected = _bind_devices_to_inventory(devices)
    if rejected:
        return (
            jsonify(
                {
                    "error": "one or more devices not in inventory",
                    "rejected_count": len(rejected),
                }
            ),
            404,
        )
    run_id = str(uuid.uuid4())
    device_results = _run_devices_inline(bound)
    created_at = _now_iso()
    _state_store().set(
        run_id,
        {
            "phase": "PRE",
            "devices": bound,
            "device_results": device_results,
            "created_at": created_at,
        },
    )
    return jsonify(
        {
            "run_id": run_id,
            "phase": "PRE",
            "device_results": device_results,
            "run_created_at": created_at,
        }
    )


@runs_bp.route("/api/run/pre/create", methods=["POST"])
def api_run_pre_create():
    """Frontend-driven PRE: caller already ran the devices, just register."""
    data = request.get_json(silent=True) or {}
    devices = data.get("devices") or []
    device_results = data.get("device_results") or []
    name = (data.get("name") or "").strip() or None
    if not isinstance(devices, list) or not devices:
        return jsonify({"error": "devices list required"}), 400
    if not isinstance(device_results, list) or len(device_results) != len(devices):
        return jsonify({"error": "device_results length must match devices"}), 400
    run_id = str(uuid.uuid4())
    created_at = _now_iso()
    _state_store().set(
        run_id,
        {
            "phase": "PRE",
            "devices": devices,
            "device_results": device_results,
            "created_at": created_at,
        },
    )
    with contextlib.suppress(Exception):  # persistence is best-effort
        _report_service().save(
            run_id=run_id,
            name=name or "pre_report",
            created_at=created_at,
            devices=devices,
            device_results=device_results,
        )
    return jsonify({"run_id": run_id, "run_created_at": created_at})


@runs_bp.route("/api/run/pre/restore", methods=["POST"])
def api_run_pre_restore():
    """Replay a saved PRE back into run-state so POST can diff against it."""
    data = request.get_json(silent=True) or {}
    run_id = (data.get("run_id") or "").strip()
    devices = data.get("devices") or []
    device_results = data.get("device_results") or []
    created_at = data.get("created_at") or _now_iso()
    if not run_id:
        return jsonify({"error": "run_id required"}), 400
    if not isinstance(devices, list) or not devices:
        return jsonify({"error": "devices list required"}), 400
    if not isinstance(device_results, list) or len(device_results) != len(devices):
        return jsonify({"error": "device_results length must match devices"}), 400
    _state_store().set(
        run_id,
        {
            "phase": "PRE",
            "devices": devices,
            "device_results": device_results,
            "created_at": created_at,
        },
    )
    return jsonify({"ok": True})


# --------------------------------------------------------------------------- #
# POST flows                                                                  #
# --------------------------------------------------------------------------- #


@runs_bp.route("/api/run/post", methods=["POST"])
def api_run_post():
    """Server-driven POST: run same devices as PRE, diff, return."""
    data = request.get_json(silent=True) or {}
    run_id = (data.get("run_id") or "").strip()
    store = _state_store()
    pre_run = store.get(run_id)
    if not run_id or pre_run is None:
        return jsonify({"error": "run_id not found or expired"}), 404
    if pre_run.get("phase") != "PRE":
        return jsonify({"error": "run_id is not a PRE run"}), 400

    devices = pre_run["devices"]
    device_results = _run_devices_inline(devices)
    comparison = _report_service().compare_runs(pre_run["device_results"], device_results)
    post_created_at = _now_iso()
    store.update(
        run_id,
        post_device_results=device_results,
        comparison=comparison,
        post_created_at=post_created_at,
    )
    return jsonify(
        {
            "run_id": run_id,
            "phase": "POST",
            "device_results": device_results,
            "pre_device_results": pre_run.get("device_results"),
            "comparison": comparison,
            "run_created_at": pre_run.get("created_at"),
            "post_created_at": post_created_at,
        }
    )


@runs_bp.route("/api/run/post/complete", methods=["POST"])
def api_run_post_complete():
    """Frontend-driven POST: caller supplies device_results, we diff."""
    data = request.get_json(silent=True) or {}
    run_id = (data.get("run_id") or "").strip()
    device_results = data.get("device_results") or []
    store = _state_store()
    pre_run = store.get(run_id)
    if not run_id or pre_run is None:
        return jsonify({"error": "run_id not found or expired"}), 404
    if pre_run.get("phase") != "PRE":
        return jsonify({"error": "run_id is not a PRE run"}), 400
    devices = pre_run["devices"]
    if len(device_results) != len(devices):
        return jsonify({"error": "device_results length must match PRE devices"}), 400

    rs = _report_service()
    comparison = rs.compare_runs(pre_run["device_results"], device_results)
    post_created_at = _now_iso()
    store.update(
        run_id,
        post_device_results=device_results,
        comparison=comparison,
        post_created_at=post_created_at,
    )
    with contextlib.suppress(Exception):  # persistence is best-effort
        loaded = rs.load(run_id)
        name = (
            loaded.get("name") or "pre_report"
            if isinstance(loaded, dict)
            else "pre_report"
        )
        rs.save(
            run_id=run_id,
            name=name,
            created_at=pre_run.get("created_at"),
            devices=pre_run.get("devices") or [],
            device_results=pre_run.get("device_results") or [],
            post_created_at=post_created_at,
            post_device_results=device_results,
            comparison=comparison,
        )
    return jsonify(
        {
            "run_id": run_id,
            "phase": "POST",
            "device_results": device_results,
            "pre_device_results": pre_run.get("device_results"),
            "comparison": comparison,
            "run_created_at": pre_run.get("created_at"),
            "post_created_at": post_created_at,
        }
    )


# --------------------------------------------------------------------------- #
# Misc                                                                        #
# --------------------------------------------------------------------------- #


# Audit M4: cap inputs at 256 KB per side. ``difflib.unified_diff`` is
# O(n*m) so a 1 MB × 1 MB call ties up a worker for tens of seconds.
_DIFF_MAX_BYTES = 256 * 1024


@runs_bp.route("/api/diff", methods=["POST"])
def api_diff():
    """Unified text diff utility (git-style). Inputs capped at 256 KB each."""
    data = request.get_json(silent=True) or {}
    pre_text = (data.get("pre") or "").strip()
    post_text = (data.get("post") or "").strip()
    if len(pre_text) > _DIFF_MAX_BYTES or len(post_text) > _DIFF_MAX_BYTES:
        return (
            jsonify(
                {
                    "error": (
                        f"diff inputs capped at {_DIFF_MAX_BYTES} bytes per side "
                        f"(pre={len(pre_text)}, post={len(post_text)})"
                    )
                }
            ),
            400,
        )
    diff = difflib.unified_diff(
        pre_text.splitlines(keepends=True),
        post_text.splitlines(keepends=True),
        fromfile="PRE",
        tofile="POST",
        lineterm="",
    )
    return jsonify({"diff": "".join(diff)})


@runs_bp.route("/api/run/result/<run_id>", methods=["GET"])
def api_run_result(run_id: str):
    state = _state_store().get(run_id)
    if state is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(state)
