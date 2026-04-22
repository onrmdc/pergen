"""
Reports Blueprint — saved pre/post report listing + retrieval + delete.

Phase-11 deliverable. Replaces three legacy routes from
``backend/app.py``:

* GET    /api/reports                — list saved reports (newest first)
* GET    /api/reports/<run_id>       — fetch one (optional ``?restore=1``
                                       to also push back into run state)
* DELETE /api/reports/<run_id>       — remove from disk + index

All persistence goes through ``ReportService`` / ``ReportRepository``,
which already enforce the path-traversal guard and gzip storage.
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

reports_bp = Blueprint("reports", __name__)


def _service():
    svc = current_app.extensions.get("report_service")
    if svc is None:
        raise RuntimeError("report_service not registered; call create_app first")
    return svc


def _state_store():
    store = current_app.extensions.get("run_state_store")
    if store is None:
        raise RuntimeError("run_state_store not registered; call create_app first")
    return store


@reports_bp.route("/api/reports", methods=["GET"])
def api_reports_list():
    """List saved reports (from disk index)."""
    try:
        return jsonify({"reports": _service().list()})
    except Exception:  # noqa: BLE001 - degrade gracefully
        return jsonify({"reports": []})


@reports_bp.route("/api/reports/<run_id>", methods=["GET"])
def api_report_get(run_id: str):
    """Fetch saved report. ``?restore=1`` also pushes it back to run state."""
    run_id = (run_id or "").strip()
    if not run_id:
        return jsonify({"error": "run_id required"}), 400
    try:
        report = _service().load(run_id)
    except Exception:  # noqa: BLE001
        return jsonify({"error": "failed to load report"}), 500
    if report is None:
        return jsonify({"error": "report not found"}), 404
    if request.args.get("restore") == "1":
        _state_store().set(
            run_id,
            {
                "phase": "POST" if report.get("post_created_at") else "PRE",
                "devices": report.get("devices") or [],
                "device_results": report.get("device_results") or [],
                "created_at": report.get("created_at"),
                "post_device_results": report.get("post_device_results"),
                "post_created_at": report.get("post_created_at"),
                "comparison": report.get("comparison"),
            },
        )
    return jsonify(report)


@reports_bp.route("/api/reports/<run_id>", methods=["DELETE"])
def api_report_delete(run_id: str):
    """Remove a saved report from disk + index."""
    run_id = (run_id or "").strip()
    if not run_id:
        return jsonify({"error": "run_id required"}), 400
    try:
        _service().delete(run_id)
        return jsonify({"ok": True})
    except Exception:  # noqa: BLE001
        return jsonify({"error": "failed to delete"}), 500
