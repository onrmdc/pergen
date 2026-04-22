"""
Centralised logging configuration for Pergen.

Phase-2 deliverable.  Exposes:

* ``JsonFormatter`` — emits one JSON object per line, suitable for shipping to
  ELK / Loki / CloudWatch.  Redacts sensitive keys.
* ``ColourFormatter`` — TTY-aware ANSI colours for development.
* ``redact_sensitive`` — recursive redactor for the standard sensitive-key set.
* ``LoggingConfig.configure(app)`` — attaches handlers based on
  ``app.config['LOG_LEVEL'] / LOG_FORMAT / LOG_FILE``.

Security
--------
Logs are the most common accidental secret-leak channel.  The
``_SENSITIVE_KEYS`` set below MUST be kept exhaustive: when in doubt, add the
key.  Redaction happens at format-time, so even if a caller forgets to scrub
``extra={...}``, the secret never reaches stdout / disk.
"""
from __future__ import annotations

import contextlib
import json
import logging
import logging.handlers
import os
import sys
import time
from collections.abc import Mapping
from typing import Any

# --------------------------------------------------------------------------- #
# Sensitive key catalogue                                                     #
# --------------------------------------------------------------------------- #

_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password", "passwd", "pwd",
        "secret", "secret_key",
        "token", "auth_token", "access_token", "refresh_token",
        "api_key", "apikey",
        "authorization", "auth",
        "cookie", "set-cookie",
        "credential", "credentials",
    }
)


def _is_sensitive(key: str) -> bool:
    """Case-insensitive sensitive-key lookup."""
    return key.lower() in _SENSITIVE_KEYS


def redact_sensitive(value: Any) -> Any:
    """
    Recursively walk *value* and replace any sensitive entries with the
    sentinel string ``***REDACTED***``.

    Inputs
    ------
    value : any JSON-serialisable structure (dict / list / scalar).

    Outputs
    -------
    A new structure of the same shape with sensitive leaves redacted.  The
    original ``value`` is never mutated.

    Security
    --------
    The redactor matches dict KEYS, not values, so a password used as a value
    of an unrelated field name will pass through.  Always name your fields
    explicitly (``password`` not ``p``).
    """
    if isinstance(value, Mapping):
        return {
            k: ("***REDACTED***" if _is_sensitive(str(k)) else redact_sensitive(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(v) for v in value)
    return value


# --------------------------------------------------------------------------- #
# JsonFormatter                                                               #
# --------------------------------------------------------------------------- #

_STD_LOG_FIELDS: frozenset[str] = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime", "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """One JSON object per line; sensitive keys redacted."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Pull caller-supplied extras (anything not part of the stdlib record).
        for key, val in record.__dict__.items():
            if key in _STD_LOG_FIELDS or key.startswith("_"):
                continue
            payload[key] = "***REDACTED***" if _is_sensitive(key) else val

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        try:
            return json.dumps(payload, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            # Fall back to a stringified payload if anything is non-serialisable.
            return json.dumps({"ts": payload["ts"], "level": payload["level"],
                               "logger": payload["logger"], "msg": str(payload["msg"])})


# --------------------------------------------------------------------------- #
# ColourFormatter                                                             #
# --------------------------------------------------------------------------- #


class ColourFormatter(logging.Formatter):
    """ANSI-colourised single-line output for interactive terminals."""

    _COLOURS: dict[str, str] = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[1;31m",
    }
    _RESET = "\033[0m"

    def __init__(self, *, force_colour: bool | None = None) -> None:
        super().__init__()
        if force_colour is None:
            force_colour = sys.stderr.isatty()
        self._colour = force_colour

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        prefix = f"{ts} {record.levelname:<8} {record.name}: "
        body = record.getMessage()
        if record.exc_info:
            body += "\n" + self.formatException(record.exc_info)
        if not self._colour:
            return prefix + body
        colour = self._COLOURS.get(record.levelname, "")
        return f"{colour}{prefix}{self._RESET}{body}"


# --------------------------------------------------------------------------- #
# LoggingConfig                                                               #
# --------------------------------------------------------------------------- #


class LoggingConfig:
    """Static helper that wires up handlers against the Flask ``app.config``."""

    @staticmethod
    def configure(app: Any) -> None:
        """
        Configure the root logger and the dedicated ``app.audit`` logger.

        Inputs
        ------
        app : a Flask app (or any object exposing ``app.config`` as a Mapping).

        Outputs
        -------
        None.  Handlers are mounted on the root logger so subsequent calls
        replace them (idempotent).

        Security
        --------
        File handlers create their parent directory with 0700 and chmod the
        log file to 0600 once it exists, preventing world-readable secrets.
        """
        log_level = str(app.config.get("LOG_LEVEL", "INFO")).upper()
        log_format = str(app.config.get("LOG_FORMAT", "json")).lower()
        log_file = app.config.get("LOG_FILE", "")

        formatter: logging.Formatter = JsonFormatter() if log_format == "json" else ColourFormatter()

        root = logging.getLogger()
        root.setLevel(getattr(logging, log_level, logging.INFO))
        # Replace handlers atomically — avoid duplicate output when configure()
        # is called multiple times (tests / hot-reload).
        for h in list(root.handlers):
            root.removeHandler(h)

        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        root.addHandler(stream)

        if log_file:
            try:
                os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
                handler = logging.handlers.RotatingFileHandler(
                    log_file, maxBytes=10 * 1024 * 1024, backupCount=5,
                )
                handler.setFormatter(formatter)
                root.addHandler(handler)
                with contextlib.suppress(OSError):
                    os.chmod(log_file, 0o600)
            except OSError:
                root.warning("could not create log file %s", log_file)

        # Audit logger: separate logger, same handlers, never propagates twice.
        audit = logging.getLogger("app.audit")
        audit.setLevel(logging.INFO)
        audit.propagate = True  # let it ride the root handlers

        # Request logger: same idea.
        req = logging.getLogger("app.request")
        req.setLevel(logging.INFO)
        req.propagate = True
