"""Wave-6 Phase F: state-changing endpoints under cookie auth require CSRF.

When ``PERGEN_AUTH_COOKIE_ENABLED=1`` and a request authenticates via
the cookie path (no ``X-API-Token`` header), every POST/PUT/DELETE/PATCH
MUST carry a matching ``X-CSRF-Token`` header. Missing or bad CSRF →
403. This is the centerpiece of the new dual-path gate's defence
against cross-site form submissions.

Note: the legacy ``X-API-Token`` header path is intentionally CSRF-free
because machine clients (CI / curl) do not have an ambient cookie a
malicious page could ride.
"""
from __future__ import annotations

import importlib
import sys

import pytest

pytestmark = [pytest.mark.security]

_TOK = "c" * 64

# Routes whose POST/PUT/DELETE shape accepts JSON bodies — same set
# as test_security_csrf_unsafe_methods.py.
CSRF_TARGETS = [
    ("POST", "/api/inventory/device", {"hostname": "x", "ip": "1.2.3.4"}),
    ("POST", "/api/credentials", {"name": "x", "method": "basic", "username": "u", "password": "p"}),
    ("PUT", "/api/notepad", {"content": "abc"}),
]


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
    return app


def _login(client) -> str:
    r = client.post("/api/auth/login", json={"username": "alice", "password": _TOK})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["csrf"]


@pytest.mark.parametrize("method,path,payload", CSRF_TARGETS)
def test_cookie_path_rejects_unsafe_method_without_csrf(
    monkeypatch, tmp_path, method: str, path: str, payload: dict
) -> None:
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()
    _login(client)

    r = client.open(path, method=method, json=payload)
    assert r.status_code == 403, (
        f"{method} {path} accepted state-changing request without "
        f"X-CSRF-Token (status={r.status_code})"
    )


@pytest.mark.parametrize("method,path,payload", CSRF_TARGETS)
def test_cookie_path_rejects_bad_csrf(
    monkeypatch, tmp_path, method: str, path: str, payload: dict
) -> None:
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()
    _login(client)

    r = client.open(
        path,
        method=method,
        json=payload,
        headers={"X-CSRF-Token": "wrong-token-value"},
    )
    assert r.status_code == 403, (
        f"{method} {path} accepted state-changing request with "
        f"forged CSRF token (status={r.status_code})"
    )


@pytest.mark.parametrize("method,path,payload", CSRF_TARGETS)
def test_cookie_path_accepts_valid_csrf(
    monkeypatch, tmp_path, method: str, path: str, payload: dict
) -> None:
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()
    csrf = _login(client)

    r = client.open(path, method=method, json=payload, headers={"X-CSRF-Token": csrf})
    # Domain-level outcomes are fine; we just must NOT see auth/csrf rejection.
    assert r.status_code not in (401, 403), (
        f"{method} {path} rejected legitimate CSRF token (status={r.status_code})"
    )


def test_token_header_path_does_not_require_csrf(monkeypatch, tmp_path) -> None:
    """Machine clients using X-API-Token must not be forced to send CSRF."""
    app = _gated_app(monkeypatch, tmp_path)
    client = app.test_client()

    r = client.post(
        "/api/inventory/device",
        json={"hostname": "machine-dev", "ip": "10.99.0.50"},
        headers={"X-API-Token": _TOK},
    )
    assert r.status_code not in (401, 403), r.get_data(as_text=True)


def test_csrf_uses_constant_time_comparison() -> None:
    """Defence-in-depth: verify_csrf_token uses hmac.compare_digest, not ==.

    A naïve == compare leaks the prefix length of the expected token via
    timing. We can't measure that reliably here, but we can verify the
    helper is wired through hmac.compare_digest by inspecting source +
    behaviour with mismatched-length inputs.
    """
    from backend.security import csrf as _csrf_mod

    src = (_csrf_mod.__file__,)
    import inspect
    source = inspect.getsource(_csrf_mod)
    assert "hmac.compare_digest" in source, (
        "verify_csrf_token must use hmac.compare_digest"
    )
    # Mismatched-length inputs must return False without raising.
    assert _csrf_mod.verify_csrf_token("short", "much-longer-expected-token") is False
    # Empty / None inputs return False.
    assert _csrf_mod.verify_csrf_token("", "x") is False
    assert _csrf_mod.verify_csrf_token("x", "") is False
    assert _csrf_mod.verify_csrf_token(None, "x") is False
    assert _csrf_mod.verify_csrf_token("x", None) is False
    # Equal inputs return True.
    tok = _csrf_mod.issue_csrf_token()
    assert _csrf_mod.verify_csrf_token(tok, tok) is True
