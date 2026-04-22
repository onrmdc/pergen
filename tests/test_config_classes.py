"""
TDD tests for ``backend.config.app_config`` (RED phase).

These tests document the contract of the upcoming config hierarchy:

* ``BaseConfig`` — shared defaults, env-var resolution.
* ``DevelopmentConfig`` — DEBUG=True, verbose logging.
* ``TestingConfig`` — TESTING=True, in-memory SQLite, terse logs.
* ``ProductionConfig`` — DEBUG=False, JSON logs, ``validate()`` raises
  ``RuntimeError`` if ``SECRET_KEY`` is still the default placeholder.
* ``CONFIG_MAP`` — maps env strings to config classes.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit


def test_config_map_exposes_all_envs():
    from backend.config.app_config import CONFIG_MAP

    assert set(CONFIG_MAP.keys()) >= {"development", "testing", "production", "default"}
    # default must point to development for safety
    assert CONFIG_MAP["default"] is CONFIG_MAP["development"]


def test_base_config_resolves_secret_key_from_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "from-env-12345")
    from backend.config import app_config

    cfg = app_config.BaseConfig()
    assert cfg.SECRET_KEY == "from-env-12345"


def test_base_config_falls_back_to_placeholder(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    # Force a fresh import so the env state is re-read.
    import importlib

    from backend.config import app_config

    importlib.reload(app_config)
    cfg = app_config.BaseConfig()
    assert cfg.SECRET_KEY == app_config.DEFAULT_SECRET_KEY
    # Restore SECRET_KEY for the rest of the session
    os.environ["SECRET_KEY"] = "pergen-test-secret-key-deterministic"
    importlib.reload(app_config)


def test_testing_config_uses_in_memory_sqlite_and_disables_scheduler():
    from backend.config.app_config import TestingConfig

    cfg = TestingConfig()
    assert cfg.TESTING is True
    assert cfg.DEBUG is False
    assert cfg.CREDENTIAL_DB_PATH == ":memory:"
    assert cfg.START_SCHEDULER is False


def test_development_config_enables_debug_and_verbose_logs():
    from backend.config.app_config import DevelopmentConfig

    cfg = DevelopmentConfig()
    assert cfg.DEBUG is True
    assert cfg.LOG_LEVEL == "DEBUG"
    assert cfg.LOG_FORMAT == "colour"


def test_production_config_disables_debug_and_uses_json_logs():
    from backend.config.app_config import ProductionConfig

    cfg = ProductionConfig()
    assert cfg.DEBUG is False
    assert cfg.LOG_LEVEL in {"INFO", "WARNING"}
    assert cfg.LOG_FORMAT == "json"


def test_production_config_validate_rejects_default_secret(monkeypatch):
    """ProductionConfig.validate() must reject the placeholder SECRET_KEY."""
    from backend.config.app_config import DEFAULT_SECRET_KEY, ProductionConfig

    cfg = ProductionConfig()
    cfg.SECRET_KEY = DEFAULT_SECRET_KEY
    with pytest.raises(RuntimeError):
        cfg.validate()


def test_production_config_validate_accepts_strong_secret():
    from backend.config.app_config import ProductionConfig

    cfg = ProductionConfig()
    cfg.SECRET_KEY = "a-strong-deployment-secret-with-32-chars"
    cfg.validate()  # must not raise
