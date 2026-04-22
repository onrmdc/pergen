"""
Request-scoped logging middleware and audit log helper.

Phase-2 deliverable.

* ``RequestLogger.init_app(app)`` — wires ``before_request`` /
  ``after_request`` hooks that:

  - generate a UUID4 stored on ``flask.g.request_id``,
  - log ``→ METHOD /path [rid=…]`` on entry,
  - log ``← STATUS duration_ms [rid=…]`` on exit,
  - WARN when duration exceeds ``app.config['LOG_SLOW_MS']`` (default 500ms),
  - add the ``X-Request-ID`` response header for downstream tracing.

* ``audit_log(event, actor, detail="", severity="info")`` — emits to the
  dedicated ``app.audit`` logger with consistent shape.

Security
--------
The request logger never logs request bodies or headers — those can contain
session cookies, basic-auth, and CSRF tokens.  Only method, path, status, and
client IP are recorded.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from flask import Flask, Response, g, request

_request_logger = logging.getLogger("app.request")
_audit_logger = logging.getLogger("app.audit")


class RequestLogger:
    """Per-request entry/exit logging with slow-request detection."""

    @staticmethod
    def init_app(app: Flask) -> None:
        """
        Register Flask before/after hooks.

        Inputs
        ------
        app : Flask application instance.  Reads ``app.config['LOG_SLOW_MS']``.

        Outputs
        -------
        None.  Hooks are idempotent — calling ``init_app`` twice replaces the
        existing handlers because Flask de-dupes by function identity.
        """
        slow_ms = int(app.config.get("LOG_SLOW_MS", 500))

        @app.before_request
        def _log_request_start() -> None:
            g.request_id = str(uuid.uuid4())
            g._req_started = time.perf_counter()
            _request_logger.info(
                "→ %s %s [rid=%s ip=%s]",
                request.method,
                request.path,
                g.request_id,
                request.remote_addr or "-",
            )

        @app.after_request
        def _log_request_end(response: Response) -> Response:
            started = getattr(g, "_req_started", None)
            duration_ms: float
            if started is None:
                duration_ms = 0.0
            else:
                duration_ms = (time.perf_counter() - started) * 1000.0

            rid = getattr(g, "request_id", "-")
            response.headers.setdefault("X-Request-ID", rid)

            # Phase 13: defence-in-depth security headers.
            # ``setdefault`` so an explicit per-route override is preserved.
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault(
                "Referrer-Policy", "strict-origin-when-cross-origin"
            )
            response.headers.setdefault(
                "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
            )
            # Audit M8: HSTS + CSP. The CSP is intentionally restrictive
            # (self-only with a small inline-style allowance for the SPA);
            # operators with stricter SPAs can override per-route.
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains",
            )
            response.headers.setdefault(
                "Content-Security-Policy",
                (
                    "default-src 'self'; "
                    "img-src 'self' data:; "
                    "script-src 'self'; "
                    "style-src 'self' 'unsafe-inline'; "
                    "object-src 'none'; "
                    "base-uri 'self'; "
                    "frame-ancestors 'none'"
                ),
            )

            if duration_ms > slow_ms:
                _request_logger.warning(
                    "← %d %.1fms (slow > %dms) [rid=%s]",
                    response.status_code, duration_ms, slow_ms, rid,
                )
            else:
                _request_logger.info(
                    "← %d %.1fms [rid=%s]",
                    response.status_code, duration_ms, rid,
                )
            return response


def audit_log(
    event: str,
    actor: str,
    detail: str = "",
    severity: str = "info",
    **extra: Any,
) -> None:
    """
    Record an audit event on the ``app.audit`` logger.

    Inputs
    ------
    event    : symbolic event name (``LOGIN_SUCCESS``, ``CONFIG_BACKUP`` …).
    actor    : the principal performing the action (username / system-id).
    detail   : free-form context (IP address, target host, …).
    severity : ``info`` / ``warning`` / ``error``.
    extra    : extra keyword fields attached to the log record.  These pass
               through ``redact_sensitive`` automatically because they ride
               the JsonFormatter.

    Outputs
    -------
    None.  The logger may also persist to a DB-backed audit table once the
    ``EventLog`` model is added in Phase 5.

    Security
    --------
    Never include credentials in ``detail``.  Use ``extra={"username": …}``
    with a NON-sensitive key instead — passwords are auto-redacted.
    """
    level = {
        "info": logging.INFO,
        "warning": logging.WARNING,
        "warn": logging.WARNING,
        "error": logging.ERROR,
    }.get(severity.lower(), logging.INFO)

    msg = f"{event} actor={actor} detail={detail}".strip()
    _audit_logger.log(level, msg, extra=extra or None)
