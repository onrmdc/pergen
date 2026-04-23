"""
Network operations blueprint — ICMP probes + SPA fallback.

Phase-5 deliverable. Replaces the legacy ``api_ping`` and ``index``
routes from ``backend/app.py``.

The ``/api/ping`` endpoint preserves the Phase-13 hardening:

* ``InputSanitizer.sanitize_ip`` short-circuits invalid IPs *before*
  any process exec, so a malicious IP literal cannot reach the system
  ``ping`` binary.
* The request ``devices`` list is capped at ``MAX_PING_DEVICES`` (64)
  to bound worst-case execution time and stop SSRF-style internal
  scans from a single request.
* Each device gets up to 5 attempts; first success wins.

Audit H3 — SSRF guard (wave-7 follow-up posture change)
-------------------------------------------------------

Pergen is operated against the operator's own internal management
network. RFC1918, loopback, and link-local addresses are the
EXPECTED targets of ``/api/ping`` (e.g. ``10.59.1.1`` leaf, ``10.59.65.x``
spine), not exotic edge cases.

* **Default**: internal addresses are ALLOWED to reach the underlying
  ``single_ping`` call. This is the deliberate posture for an
  internal-only deployment, recorded in
  ``docs/security/DONE_audit_2026-04-23-wave7.md``.
* **Opt-in lock-down**: set ``PERGEN_BLOCK_INTERNAL_PING=1`` to
  re-enable the original audit-H3 default-deny — useful for
  internet-exposed deployments or shared multi-tenant hosts where
  ``/api/ping`` could otherwise be abused as a metadata-service
  oracle (e.g. ``169.254.169.254``).
* **Backward compat**: the legacy ``PERGEN_ALLOW_INTERNAL_PING=1``
  env var is honoured as a no-op (allow is now the default). If both
  ``ALLOW`` and ``BLOCK`` are set, ``BLOCK`` wins — explicit lock-down
  beats default-allow.

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
    """Return True for addresses that the SSRF guard considers internal.

    Conservative — flags *anything* that is not globally routable: private
    (RFC1918), loopback, link-local, multicast, reserved, unspecified.
    Whether to BLOCK these or let them through is decided by
    ``_ssrf_guard_enabled()`` based on the env-var posture.
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


def _ssrf_guard_enabled() -> bool:
    """Resolve the wave-7 posture for the /api/ping SSRF guard.

    Default: False (allow internal targets — the operator's actual
    fleet is on RFC1918, so the original default-deny was making the
    tool unusable for its intended internal-deployment use case).

    Opt-in lock-down: ``PERGEN_BLOCK_INTERNAL_PING=1`` re-enables the
    audit-H3 default-deny posture. This wins over the legacy
    ``PERGEN_ALLOW_INTERNAL_PING`` env var (explicit lock-down beats
    backward-compat allow).
    """
    return os.environ.get("PERGEN_BLOCK_INTERNAL_PING") == "1"


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

    block_internal = _ssrf_guard_enabled()

    max_attempts = 5
    results: list[dict] = []
    for d in devices:
        hostname = (d.get("hostname") or "").strip()
        ip = (d.get("ip") or "").strip()
        ok, _reason = InputSanitizer.sanitize_ip(ip)
        if not ok:
            results.append({"hostname": hostname, "ip": ip, "reachable": False})
            continue
        # Audit H3 (wave-7 follow-up): the SSRF guard is opt-in via
        # ``PERGEN_BLOCK_INTERNAL_PING=1``. Default posture allows
        # internal targets because the operator's fleet is internal.
        if block_internal and _is_internal_address(ip):
            _log.info("ping ssrf-guard rejected internal address ip=%s", ip)
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
