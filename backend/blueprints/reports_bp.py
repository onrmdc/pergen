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

import logging

from flask import Blueprint, current_app, g, jsonify, request

# Audit M-07: dedicated audit channel.
_audit = logging.getLogger("app.audit")


def _actor() -> str:
    return getattr(g, "actor", None) or "anonymous"


def _scoping_actor() -> str | None:
    """Return the named actor for repo scoping, or None when anonymous.

    Wave-4 W4-M-01: thread-through to ReportRepository.list/load/delete
    so cross-actor reads are refused. Mirrors runs_bp._current_actor()
    semantics: anonymous → permissive (legacy back-compat).
    """
    actor = getattr(g, "actor", None)
    if not actor or actor == "anonymous":
        return None
    return str(actor)


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
    """List saved reports (from disk index).

    Wave-4 W4-M-01: projects out cross-actor entries when a named actor
    is on the request. Anonymous callers see every entry (back-compat).
    """
    try:
        return jsonify({"reports": _service().list(actor=_scoping_actor())})
    except Exception:  # noqa: BLE001 - degrade gracefully
        return jsonify({"reports": []})


@reports_bp.route("/api/reports/<run_id>", methods=["GET"])
def api_report_get(run_id: str):
    """Fetch saved report.

    Audit M-03: ``?restore=1`` previously triggered a side-effect (write
    to the run-state store) via a GET request — semantically incorrect
    and would dodge any future POST-only CSRF guard. The restore branch
    is now served by ``POST /api/reports/<run_id>/restore``; this GET
    route only reads.

    Wave-4 W4-M-01: cross-actor reads return 404 (treats IDOR mismatch
    identically to "not found" so the response cannot disclose run-id
    existence).
    """
    run_id = (run_id or "").strip()
    if not run_id:
        return jsonify({"error": "run_id required"}), 400
    if request.args.get("restore") == "1":
        # Refuse the legacy GET-side-effect form. Operators must use the
        # explicit POST /restore endpoint.
        return (
            jsonify(
                {
                    "error": (
                        "restore via GET is no longer supported — use "
                        "POST /api/reports/<run_id>/restore"
                    )
                }
            ),
            405,
        )
    try:
        report = _service().load(run_id, actor=_scoping_actor())
    except Exception:  # noqa: BLE001
        return jsonify({"error": "failed to load report"}), 500
    if report is None:
        return jsonify({"error": "report not found"}), 404
    return jsonify(report)


@reports_bp.route("/api/reports/<run_id>/restore", methods=["POST"])
def api_report_restore(run_id: str):
    """Restore a saved report into the run-state store (audit M-03 + W4-M-01)."""
    run_id = (run_id or "").strip()
    if not run_id:
        return jsonify({"error": "run_id required"}), 400
    actor = _scoping_actor()
    try:
        # Wave-4 W4-M-01: cross-actor restore returns 404 (no disclosure).
        report = _service().load(run_id, actor=actor)
    except Exception:  # noqa: BLE001
        return jsonify({"error": "failed to load report"}), 500
    if report is None:
        return jsonify({"error": "report not found"}), 404
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
        actor=actor,
    )
    return jsonify({"ok": True, "run_id": run_id})


@reports_bp.route("/api/reports/<run_id>", methods=["DELETE"])
def api_report_delete(run_id: str):
    """Remove a saved report from disk + index.

    Wave-4 W4-M-01: cross-actor delete is a silent no-op (no
    disclosure). Returns 200 in both cases (deleted-mine vs
    not-found-as-yours) for the same reason.
    """
    run_id = (run_id or "").strip()
    if not run_id:
        return jsonify({"error": "run_id required"}), 400
    try:
        _service().delete(run_id, actor=_scoping_actor())
        # Audit M-07: log the run id + actor.
        _audit.info("audit report.delete actor=%s run_id=%s", _actor(), run_id)
        return jsonify({"ok": True})
    except Exception:  # noqa: BLE001
        return jsonify({"error": "failed to delete"}), 500
