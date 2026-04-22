"""
TDD tests for ``backend.request_logging`` (RED phase).

RequestLogger must:
* Generate a UUID4 ``g.request_id`` per request.
* Log ``→ METHOD /path`` on entry.
* Log ``← STATUS duration_ms`` on exit and add ``X-Request-ID`` response header.
* Emit a WARNING when duration > LOG_SLOW_MS (default 500).
"""
from __future__ import annotations

import logging
import re
import uuid

import pytest
from flask import Flask, jsonify

pytestmark = pytest.mark.unit


def _build_app(log_slow_ms: int = 500) -> Flask:
    from backend.request_logging import RequestLogger

    app = Flask(__name__)
    app.config["LOG_SLOW_MS"] = log_slow_ms
    RequestLogger.init_app(app)

    @app.route("/ping")
    def ping():
        return jsonify({"ok": True})

    @app.route("/slow")
    def slow():
        import time

        time.sleep(0.05)
        return jsonify({"ok": True})

    return app


def test_request_id_header_added_to_response():
    app = _build_app()
    client = app.test_client()
    r = client.get("/ping")
    assert r.status_code == 200
    rid = r.headers.get("X-Request-ID")
    assert rid
    uuid.UUID(rid)  # must be a valid UUID4


def test_request_id_is_unique_per_request():
    app = _build_app()
    client = app.test_client()
    r1 = client.get("/ping")
    r2 = client.get("/ping")
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


def test_request_logger_emits_entry_and_exit_logs(caplog):
    app = _build_app()
    client = app.test_client()
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/ping")
    messages = [rec.getMessage() for rec in caplog.records if rec.name == "app.request"]
    assert any(re.search(r"→\s*GET\s+/ping", m) for m in messages)
    assert any(re.search(r"←\s*200", m) for m in messages)


def test_request_logger_warns_when_slow(caplog):
    """A request slower than LOG_SLOW_MS should produce at least one WARNING."""
    app = _build_app(log_slow_ms=1)  # everything is "slow"
    client = app.test_client()
    with caplog.at_level(logging.WARNING, logger="app.request"):
        client.get("/slow")
    warnings = [rec for rec in caplog.records if rec.levelno >= logging.WARNING]
    assert warnings, "expected a WARNING for slow request"


def test_audit_log_writes_event(caplog):
    """audit_log() must record an entry with the expected event/actor pair."""
    from backend.request_logging import audit_log

    with caplog.at_level(logging.INFO, logger="app.audit"):
        audit_log("LOGIN_SUCCESS", actor="alice", detail="from 127.0.0.1")
    audits = [rec for rec in caplog.records if rec.name == "app.audit"]
    assert audits
    assert any("LOGIN_SUCCESS" in r.getMessage() and "alice" in r.getMessage() for r in audits)
