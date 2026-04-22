"""
Health-check Blueprint.

Exposes a richer ``/api/v2/health`` endpoint that complements the legacy
``/api/health`` route in ``backend/app.py``.  The legacy endpoint is left
in place so existing clients keep working; the v2 endpoint is the path
forward — it's discoverable, versioned, and reports more than a constant
``"ok"``.

Security
--------
The endpoint is intentionally read-only and exposes no secrets or
internal paths.  It returns Pergen's symbolic name, ``status="ok"``, the
current UTC timestamp, the registered config name (when set on
``app.config['CONFIG_NAME']``), and the request id.
"""
from __future__ import annotations

from datetime import UTC, datetime

from flask import Blueprint, current_app, g, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/api/v2/health", methods=["GET"])
def api_v2_health():
    """
    Lightweight liveness probe.

    Inputs
    ------
    None.

    Outputs
    -------
    200 JSON ``{"service": "pergen", "status": "ok",
    "timestamp": "<ISO-8601 UTC>", "config": "<config-name>",
    "request_id": "<uuid4>"}``.

    Security
    --------
    Returns no environment variables, no version strings beyond a
    constant, no stack info.  Safe for unauthenticated probing.
    """
    # Audit (wave-3 Phase 11): the ``config`` field used to echo
    # ``app.config["CONFIG_NAME"]`` back to anonymous callers. That
    # disclosed environment posture (production vs testing) to anyone
    # who could probe /api/v2/health and was deemed unnecessary.
    # Internal posture checks should read app.config directly.
    return jsonify(
        {
            "service": "pergen",
            "status": "ok",
            "timestamp": datetime.now(UTC).isoformat(),
            "request_id": getattr(g, "request_id", ""),
        }
    )


@health_bp.route("/api/health", methods=["GET"])
def api_health():
    """Legacy v1 liveness probe — preserved for backwards compatibility.

    Phase-12: moved here from ``backend/app.py`` so the legacy module
    can shrink to <80 lines. Returns the same simple
    ``{"status": "ok"}`` contract operators have always relied on.
    """
    return jsonify({"status": "ok"})
