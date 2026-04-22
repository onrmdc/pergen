"""
TDD tests for ``backend.app_factory.create_app``.

Contract:
* ``create_app("testing")`` returns a Flask app with TestingConfig values.
* ``create_app("production")`` raises if SECRET_KEY is the placeholder.
* All existing routes (golden baseline) remain reachable through the factory.
* RequestLogger middleware is mounted (X-Request-ID header on responses).
* LoggingConfig.configure was invoked (root logger has at least one handler).
"""
from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.unit


def _fresh_factory():
    """Re-import the factory after env tweaks so config picks up new env.

    We pop every module that holds a cached reference to the legacy
    ``backend.app`` instance.  Otherwise a re-import of ``backend.app``
    creates a *new* Flask object but downstream modules still point at the
    *old* one (which has already handled requests in earlier tests and
    refuses ``before_request`` registration).
    """
    import importlib
    import sys

    for m in [
        "backend.app",
        "backend.app_factory",
        "backend.config.app_config",
        "backend.config.settings",
        "backend.config.commands_loader",
        "backend.inventory.loader",
        "backend.credential_store",
    ]:
        sys.modules.pop(m, None)
    return importlib.import_module("backend.app_factory")


def test_create_app_testing_returns_flask_app(tmp_path, monkeypatch):
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "test-key-for-factory")
    factory = _fresh_factory()
    app = factory.create_app("testing")
    assert app.config["TESTING"] is True
    assert app.config["DEBUG"] is False
    assert app.config["SECRET_KEY"] == "test-key-for-factory"


def test_create_app_default_returns_development_config(tmp_path, monkeypatch):
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "dev-key")
    factory = _fresh_factory()
    app = factory.create_app("default")
    assert app.config["DEBUG"] is True


def test_create_app_production_rejects_default_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    from backend.config.app_config import DEFAULT_SECRET_KEY

    monkeypatch.setenv("SECRET_KEY", DEFAULT_SECRET_KEY)
    factory = _fresh_factory()
    with pytest.raises(RuntimeError):
        factory.create_app("production")


def test_create_app_mounts_request_id_header(tmp_path, monkeypatch):
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "k1")
    factory = _fresh_factory()
    app = factory.create_app("testing")
    client = app.test_client()
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID")


def test_create_app_configures_root_logger(tmp_path, monkeypatch):
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "k1")
    factory = _fresh_factory()
    factory.create_app("testing")
    root = logging.getLogger()
    assert root.handlers, "expected at least one handler on the root logger"


def test_create_app_registers_health_blueprint(tmp_path, monkeypatch):
    """The new ``health`` Blueprint must be wired in by the factory."""
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "k1")
    factory = _fresh_factory()
    app = factory.create_app("testing")
    assert "health" in app.blueprints
    client = app.test_client()
    r = client.get("/api/v2/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["service"] == "pergen"
    assert body["status"] == "ok"
    assert body["config"] == "testing"
    assert body["request_id"]
    assert "T" in body["timestamp"]  # ISO-8601


def test_create_app_blueprint_registration_is_idempotent(tmp_path, monkeypatch):
    """Calling create_app twice must not raise on duplicate Blueprint."""
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "k1")
    factory = _fresh_factory()
    app1 = factory.create_app("testing")
    app2 = factory.create_app("testing")
    assert "health" in app1.blueprints
    assert "health" in app2.blueprints


def test_create_app_preserves_existing_routes(tmp_path, monkeypatch):
    """The factory must not delete or shadow legacy routes."""
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "k1")
    factory = _fresh_factory()
    app = factory.create_app("testing")
    client = app.test_client()
    # Sanity: a known route from the golden suite.
    r = client.get("/api/fabrics")
    assert r.status_code == 200
    body = r.get_json()
    assert "fabrics" in body
