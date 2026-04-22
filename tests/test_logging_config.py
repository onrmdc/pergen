"""
TDD tests for ``backend.logging_config`` (RED phase).

LoggingConfig must:
* Configure a stream handler always (and a RotatingFileHandler when LOG_FILE set).
* Use ``JsonFormatter`` for production (one JSON object per line).
* Use ``ColourFormatter`` for development.
* Redact known-sensitive keys (``password``, ``token``, ``api_key`` …).
* Expose a separate audit logger (``app.audit``).
"""
from __future__ import annotations

import io
import json
import logging
from unittest import mock

import pytest

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# JsonFormatter                                                               #
# --------------------------------------------------------------------------- #


def test_json_formatter_emits_one_object_per_line():
    from backend.logging_config import JsonFormatter

    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    out = JsonFormatter().format(record)
    payload = json.loads(out)
    assert payload["msg"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "x"
    assert "ts" in payload


def test_json_formatter_redacts_sensitive_extra_fields():
    from backend.logging_config import JsonFormatter

    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname=__file__, lineno=1,
        msg="login", args=(), exc_info=None,
    )
    record.__dict__["password"] = "shh"
    record.__dict__["token"] = "secret"
    record.__dict__["safe_field"] = "ok"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["password"] == "***REDACTED***"
    assert payload["token"] == "***REDACTED***"
    assert payload["safe_field"] == "ok"


def test_json_formatter_includes_exception_info():
    from backend.logging_config import JsonFormatter

    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="x", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="oops", args=(), exc_info=sys.exc_info(),
        )
    payload = json.loads(JsonFormatter().format(record))
    assert "boom" in payload["exception"]


# --------------------------------------------------------------------------- #
# ColourFormatter                                                             #
# --------------------------------------------------------------------------- #


def test_colour_formatter_includes_level_name():
    from backend.logging_config import ColourFormatter

    record = logging.LogRecord(
        name="x", level=logging.WARNING, pathname=__file__, lineno=1,
        msg="hi", args=(), exc_info=None,
    )
    out = ColourFormatter().format(record)
    assert "WARNING" in out
    assert "hi" in out


# --------------------------------------------------------------------------- #
# Sensitive key redaction (shared helper)                                     #
# --------------------------------------------------------------------------- #


def test_redact_sensitive_recursively():
    from backend.logging_config import redact_sensitive

    payload = {
        "username": "alice",
        "password": "secret",
        "nested": {"api_key": "tok", "ok": 1},
        "list": [{"token": "x"}, "ok"],
    }
    out = redact_sensitive(payload)
    assert out["username"] == "alice"
    assert out["password"] == "***REDACTED***"
    assert out["nested"]["api_key"] == "***REDACTED***"
    assert out["nested"]["ok"] == 1
    assert out["list"][0]["token"] == "***REDACTED***"
    assert out["list"][1] == "ok"


# --------------------------------------------------------------------------- #
# LoggingConfig.configure                                                     #
# --------------------------------------------------------------------------- #


def test_logging_config_attaches_stream_handler_with_correct_level():
    from backend.logging_config import LoggingConfig

    fake_app = mock.MagicMock()
    fake_app.config = {"LOG_LEVEL": "INFO", "LOG_FORMAT": "json"}
    LoggingConfig.configure(fake_app)
    root = logging.getLogger()
    assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    assert root.level == logging.INFO


def test_logging_config_creates_audit_logger():
    from backend.logging_config import LoggingConfig

    fake_app = mock.MagicMock()
    fake_app.config = {"LOG_LEVEL": "INFO", "LOG_FORMAT": "json"}
    LoggingConfig.configure(fake_app)
    audit = logging.getLogger("app.audit")
    assert audit.handlers or audit.parent  # has handler or inherits from root
    assert audit.level <= logging.INFO


def test_logging_config_writes_json_lines_to_buffer():
    """End-to-end smoke: a handler writing JSON should produce parseable output."""
    from backend.logging_config import JsonFormatter

    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("smoke-json")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.info("hi", extra={"request_id": "abc-123"})
    line = buf.getvalue().strip()
    payload = json.loads(line)
    assert payload["msg"] == "hi"
    assert payload["request_id"] == "abc-123"
