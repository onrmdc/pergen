"""
Network operations blueprint — ICMP probes + SPA fallback.

Phase-5 deliverable. Replaces the legacy ``api_ping`` and ``index``
routes from ``backend/app.py``.

The ``/api/ping`` endpoint preserves the Phase-13 hardening AND adds
the audit-H3 SSRF guard:

* ``InputSanitizer.sanitize_ip`` short-circuits invalid IPs *before*
  any process exec, so a malicious IP literal cannot reach the system
  ``ping`` binary.
* The request ``devices`` list is capped at ``MAX_PING_DEVICES`` (64)
  to bound worst-case execution time and stop SSRF-style internal
  scans from a single request.
* **Audit H3**: loopback / link-local / multicast / reserved /
  private addresses are rejected unless the operator explicitly
  enables internal pinging via ``PERGEN_ALLOW_INTERNAL_PING=1``.
  The default-deny posture stops unauthenticated callers from using
  the endpoint as a network scanner against the host's internal
  segments.
* Each device gets up to 5 attempts; first success wins.

The ``/`` endpoint serves the built SPA when present (``index.html``
under ``app.static_folder``), falling back to a JSON sentinel for
operators hitting the API directly.
"""
from __future__ import annotations

import ipaddress
import logging
import os

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from backend.security.sanitizer import InputSanitizer
from backend.utils import ping as ping_module

_log = logging.getLogger("app.blueprints.network_ops")

network_ops_bp = Blueprint("network_ops", __name__)


def _is_internal_address(ip: str) -> bool:
    """Return True for addresses that should never be probed by an
    unauthenticated /api/ping caller.

    Conservative — flag *anything* that is not globally routable: private
    (RFC1918), loopback, link-local, multicast, reserved, unspecified.
    The carve-out is ``PERGEN_ALLOW_INTERNAL_PING=1`` for operators who
    legitimately use this endpoint against management subnets.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        # Will be caught by sanitize_ip; treat as "not internal" so the
        # validation path is taken, not the SSRF path.
        return False
    return (
        addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_private
        or addr.is_reserved
        or addr.is_unspecified
    )


@network_ops_bp.route("/api/ping", methods=["POST"])
def api_ping():
    """ICMP-probe up to 64 devices; first reply within 5 attempts wins."""
    data = request.get_json(silent=True) or {}
    devices = data.get("devices") or []
    if not isinstance(devices, list):
        return jsonify({"error": "devices must be a list"}), 400
    if len(devices) > ping_module.MAX_PING_DEVICES:
        return (
            jsonify({"error": f"devices list capped at {ping_module.MAX_PING_DEVICES}"}),
            400,
        )

    allow_internal = os.environ.get("PERGEN_ALLOW_INTERNAL_PING") == "1"

    max_attempts = 5
    results: list[dict] = []
    for d in devices:
        hostname = (d.get("hostname") or "").strip()
        ip = (d.get("ip") or "").strip()
        ok, _reason = InputSanitizer.sanitize_ip(ip)
        if not ok:
            results.append({"hostname": hostname, "ip": ip, "reachable": False})
            continue
        # Audit H3: SSRF guard — reject internal targets by default.
        if not allow_internal and _is_internal_address(ip):
            _log.warning("ping rejected internal address ip=%s", ip)
            results.append({"hostname": hostname, "ip": ip, "reachable": False})
            continue
        reachable = False
        for _ in range(max_attempts):
            if ping_module.single_ping(ip):
                reachable = True
                break
        results.append({"hostname": hostname, "ip": ip, "reachable": reachable})
    return jsonify({"results": results})


@network_ops_bp.route("/")
def index():
    """SPA fallback — serves ``index.html`` if present, else JSON sentinel."""
    static_folder = current_app.static_folder
    if static_folder and os.path.isfile(os.path.join(static_folder, "index.html")):
        return send_from_directory(static_folder, "index.html")
    return jsonify({"message": "Pergen API. Use /api/* routes."})
