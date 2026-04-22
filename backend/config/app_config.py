"""
Configuration hierarchy for the Pergen Flask application.

Phase-2 deliverable.  These classes intentionally do **not** mutate any
existing module-level globals (``backend.config.settings`` keeps its current
import-time semantics).  They will be wired into the app via the App Factory
in Phase 4.

Hierarchy
---------
``BaseConfig``
    Shared defaults; resolves ``SECRET_KEY`` from the environment and falls
    back to a deterministic placeholder so the import never explodes.
``DevelopmentConfig``
    ``DEBUG=True``, verbose colour logging, scheduler enabled.
``TestingConfig``
    ``TESTING=True``, in-memory SQLite, scheduler disabled.
``ProductionConfig``
    ``DEBUG=False``, JSON logs, ``validate()`` rejects the placeholder
    ``SECRET_KEY``.

Security
--------
``ProductionConfig.validate()`` MUST be invoked by the App Factory before
``app.run()``.  It refuses to start with the default secret in production.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #

DEFAULT_SECRET_KEY = "pergen-default-secret-CHANGE-ME"  # noqa: S105 — sentinel placeholder, never used in production
"""Sentinel placeholder.  ProductionConfig.validate() rejects this exact
string so a misconfigured deployment fails fast instead of silently shipping
with a known SECRET_KEY."""

# Audit C2/R7: also reject the historic ``backend/app.py`` placeholder
# that was used pre-Phase-12, so any operator who copied the value forward
# also fails fast.
_HISTORIC_PLACEHOLDERS = frozenset(
    {
        DEFAULT_SECRET_KEY,
        "dev-secret-change-in-prod",  # noqa: S105 — historic backend/app.py default
    }
)
_MIN_SECRET_KEY_LENGTH = 16
"""Minimum SECRET_KEY length enforced by ``ProductionConfig.validate()``."""


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _env_str(name: str, default: str) -> str:
    """Return the env var ``name`` or ``default`` if it's missing/empty."""
    val = os.environ.get(name)
    return val if val else default


def _env_int(name: str, default: int) -> int:
    """Coerce env var to int with a safe fallback."""
    try:
        return int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    """Truthy values: 1, true, yes, on (case-insensitive)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# --------------------------------------------------------------------------- #
# Config classes                                                              #
# --------------------------------------------------------------------------- #


@dataclass
class BaseConfig:
    """
    Shared application defaults.

    Inputs
    ------
    None.  All values resolve from the environment at instantiation time, so
    each ``BaseConfig()`` call reflects the current ``os.environ`` (important
    for tests using ``monkeypatch.setenv``).

    Outputs
    -------
    A dataclass instance with the following attributes:

    * ``SECRET_KEY``         – Flask session signing key.
    * ``DEBUG`` / ``TESTING`` – standard Flask flags.
    * ``CREDENTIAL_DB_PATH`` – sqlite path used by ``credential_store``.
    * ``LOG_LEVEL`` / ``LOG_FORMAT`` / ``LOG_FILE`` / ``LOG_SLOW_MS``
                              – consumed by ``LoggingConfig`` in Phase 2.
    * ``START_SCHEDULER``    – set to False in tests so APScheduler is silent.

    Security
    --------
    Never log a ``BaseConfig`` instance directly — its ``SECRET_KEY`` would
    leak.  Use ``backend.logging_config.redact_sensitive`` if you must.
    """

    SECRET_KEY: str = field(default_factory=lambda: _env_str("SECRET_KEY", DEFAULT_SECRET_KEY))
    DEBUG: bool = False
    TESTING: bool = False
    CREDENTIAL_DB_PATH: str = field(
        default_factory=lambda: _env_str("PERGEN_CREDENTIAL_DB", "")
    )
    LOG_LEVEL: str = field(default_factory=lambda: _env_str("LOG_LEVEL", "INFO"))
    LOG_FORMAT: str = field(default_factory=lambda: _env_str("LOG_FORMAT", "json"))
    LOG_FILE: str = field(default_factory=lambda: _env_str("LOG_FILE", ""))
    LOG_SLOW_MS: int = field(default_factory=lambda: _env_int("LOG_SLOW_MS", 500))
    START_SCHEDULER: bool = field(default_factory=lambda: _env_bool("PERGEN_START_SCHEDULER", True))
    # Phase 13: cap any single request body at 10 MB.  Without this Flask
    # silently buffers the entire body before invoking the handler, so a
    # gigabyte-sized POST can OOM the worker.  Set via env so an operator
    # who knows they need bigger requests can opt in.
    MAX_CONTENT_LENGTH: int = field(
        default_factory=lambda: _env_int("MAX_CONTENT_LENGTH", 10 * 1024 * 1024)
    )

    def validate(self) -> None:
        """
        Hook for environment-specific validation.

        Inputs/Outputs: none.

        Security
        --------
        Subclasses MUST override and refuse to start when running with weak
        defaults (placeholder secrets, debug mode in production, etc.).
        """
        return None


@dataclass
class DevelopmentConfig(BaseConfig):
    """Verbose, colourised, scheduler-on."""

    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    LOG_FORMAT: str = "colour"


@dataclass
class TestingConfig(BaseConfig):
    """In-memory SQLite, scheduler off, terse logs."""

    TESTING: bool = True
    DEBUG: bool = False
    CREDENTIAL_DB_PATH: str = ":memory:"
    START_SCHEDULER: bool = False
    LOG_LEVEL: str = "WARNING"
    LOG_FORMAT: str = "json"


@dataclass
class ProductionConfig(BaseConfig):
    """Hardened defaults: JSON logs, no debug, ``validate()`` enforced."""

    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    def validate(self) -> None:
        """Refuse to start with any historic placeholder SECRET_KEY.

        Audit C2/R7: rejects both ``pergen-default-secret-CHANGE-ME``
        and the legacy ``dev-secret-change-in-prod`` from
        pre-Phase-12 ``backend/app.py``. Also enforces a minimum key
        length so a one-character SECRET_KEY can't sneak past the
        placeholder check.

        Raises ``RuntimeError`` (preserved for compatibility with
        legacy callers expecting the old exception type) — message
        wording is tightened to mention all three failure modes.
        """
        if not self.SECRET_KEY:
            raise RuntimeError(
                "ProductionConfig refuses to start with an empty SECRET_KEY."
            )
        if self.SECRET_KEY in _HISTORIC_PLACEHOLDERS:
            raise RuntimeError(
                "ProductionConfig refuses to start with a historic placeholder "
                f"SECRET_KEY ({self.SECRET_KEY!r}). "
                "Set the SECRET_KEY environment variable to a strong random value "
                f"of at least {_MIN_SECRET_KEY_LENGTH} characters."
            )
        if len(self.SECRET_KEY) < _MIN_SECRET_KEY_LENGTH:
            raise RuntimeError(
                f"ProductionConfig SECRET_KEY must be at least {_MIN_SECRET_KEY_LENGTH} characters."
            )
        if self.DEBUG:
            raise RuntimeError("ProductionConfig must not run with DEBUG=True.")


# --------------------------------------------------------------------------- #
# Selector                                                                    #
# --------------------------------------------------------------------------- #


CONFIG_MAP: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
"""Map config-name strings (typically ``FLASK_ENV``) to config classes."""
