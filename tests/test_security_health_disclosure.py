"""
``/api/v2/health`` must not leak the internal config name.

Currently the v2 health route echoes ``CONFIG_NAME`` back to the
caller, which discloses environment posture (``production`` vs
``testing``) to any unauthenticated probe. This test pins the
*expected* shape: either the field is absent/empty, or it is not
the literal ``"production"`` string. Marked ``xfail`` until the
endpoint is hardened so it tracks the gap without breaking CI.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.security]


def _boot(config_name: str, secret_key: str | None = None):
    # Evict cached modules so create_app re-reads env-driven config.
    for mod in [
        "backend.app",
        "backend.app_factory",
        "backend.config",
        "backend.config.settings",
        "backend.config.app_config",
    ]:
        sys.modules.pop(mod, None)
    factory = importlib.import_module("backend.app_factory")
    app = factory.create_app(config_name)
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    return app


@pytest.mark.parametrize("config_name", ["testing", "production"])
def test_v2_health_does_not_leak_config_name(
    config_name: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Production config requires a strong SECRET_KEY + token gate.
    if config_name == "production":
        monkeypatch.setenv("SECRET_KEY", "x" * 64)
        monkeypatch.setenv("PERGEN_API_TOKEN", "p" * 64)
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))

    app = _boot(config_name)
    client = app.test_client()
    r = client.get("/api/v2/health")
    assert r.status_code == 200
    body = r.get_json() or {}
    text = r.get_data(as_text=True)
    assert "production" not in text, (
        "v2 health response must not contain the literal 'production'"
    )
    assert not body.get("config"), (
        f"v2 health 'config' field must be absent/empty, got {body.get('config')!r}"
    )
