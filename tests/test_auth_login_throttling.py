"""Wave-6 Phase F.9: login throttling.

10 failed login attempts from the same (IP, username) within 60 seconds
must trigger a 429 with a ``Retry-After`` header. The throttling state
is an in-process LRU bounded at 1024 entries so a flood of distinct
(IP, username) pairs cannot OOM the worker.
"""
from __future__ import annotations

import importlib
import sys

import pytest

pytestmark = [pytest.mark.security]

_TOK = "t" * 64


def _gated_app(monkeypatch, tmp_path):
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    monkeypatch.setenv("PERGEN_API_TOKENS", f"alice:{_TOK}")
    monkeypatch.delenv("PERGEN_DEV_OPEN_API", raising=False)
    monkeypatch.delenv("PERGEN_API_TOKEN", raising=False)
    monkeypatch.setenv("PERGEN_AUTH_COOKIE_ENABLED", "1")
    for mod in [
        "backend.app",
        "backend.app_factory",
        "backend.blueprints",
        "backend.blueprints.auth_bp",
        "backend.config",
        "backend.config.app_config",
        "backend.config.settings",
    ]:
        sys.modules.pop(mod, None)
    factory = importlib.import_module("backend.app_factory")
    auth_mod = importlib.import_module("backend.blueprints.auth_bp")
    auth_mod._reset_throttle_for_tests()
    app = factory.create_app("development")
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    return app, auth_mod


def test_throttle_kicks_in_after_10_fails(monkeypatch, tmp_path) -> None:
    app, _ = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    # 10 failed attempts: each returns 401.
    for i in range(10):
        r = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": f"wrong-{i}"},
        )
        assert r.status_code == 401, f"attempt {i} returned {r.status_code}"

    # 11th attempt → 429 + Retry-After.
    r = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "still-wrong"},
    )
    assert r.status_code == 429
    ra = r.headers.get("Retry-After")
    assert ra is not None and ra.isdigit() and int(ra) >= 1


def test_successful_login_clears_throttle(monkeypatch, tmp_path) -> None:
    """A correct login mid-stream must reset the bucket so a typo'd password
    isn't held against the user forever.
    """
    app, _ = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    # 5 fails then a success.
    for i in range(5):
        r = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": f"wrong-{i}"},
        )
        assert r.status_code == 401

    rok = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": _TOK},
    )
    assert rok.status_code == 200

    # Must be able to fail again without hitting the throttle on attempt 1.
    r = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong-again"},
    )
    assert r.status_code == 401, f"throttle was not cleared (got {r.status_code})"


def test_throttle_lru_caps_memory_at_1024(monkeypatch, tmp_path) -> None:
    """Distinct (IP, username) pairs above the cap must evict cold entries."""
    app, auth_mod = _gated_app(monkeypatch, tmp_path)

    cap = auth_mod._THROTTLE_LRU_CAP
    # Populate cap+200 entries with one fail timestamp each.
    with auth_mod._throttle_lock:
        auth_mod._throttle.clear()
        for i in range(cap + 200):
            key = (f"10.0.0.{i % 256}", f"user-{i}")
            auth_mod._throttle[key] = [0.0]
            auth_mod._throttle.move_to_end(key)
            while len(auth_mod._throttle) > cap:
                auth_mod._throttle.popitem(last=False)

    assert len(auth_mod._throttle) == cap, (
        f"throttle LRU cap not enforced (size={len(auth_mod._throttle)}, cap={cap})"
    )
