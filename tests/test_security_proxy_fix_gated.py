"""H-1 — ProxyFix middleware must be opt-in via ``PERGEN_TRUST_PROXY``.

Audit (Security review H-1): naively trusting ``X-Forwarded-For`` from an
un-proxied deployment lets the login throttle (per-IP) and any audit-log
IP be bypassed by an attacker who rotates the header value. Mounting
``werkzeug.middleware.proxy_fix.ProxyFix`` unconditionally would
regress that defence.

The fix wires ``ProxyFix`` only when ``PERGEN_TRUST_PROXY=1`` is set —
operators behind a trusted reverse proxy (nginx, Caddy, cloud LB) opt
in explicitly.

This module pins:
  * env unset → ``app.wsgi_app`` is the bare Flask ``wsgi_app`` (no
    ProxyFix wrapping).
  * ``PERGEN_TRUST_PROXY=1`` → ``app.wsgi_app`` IS a ``ProxyFix``
    instance.
  * Any non-``"1"`` value (``"0"``, ``"true"``, ``""``) is treated as
    "not opted in" — defensive parsing.

Audit reference: ``backend/app_factory.py`` lines 123-136.
"""
from __future__ import annotations

import importlib
import sys

import pytest
from werkzeug.middleware.proxy_fix import ProxyFix

pytestmark = [pytest.mark.security]


def _build_app_with_env(monkeypatch, tmp_path, *, trust_proxy: str | None):
    """Build a fresh app honouring ``trust_proxy`` env value (or unset)."""
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    monkeypatch.setenv("PERGEN_API_TOKEN", "z" * 64)
    monkeypatch.delenv("PERGEN_DEV_OPEN_API", raising=False)
    if trust_proxy is None:
        monkeypatch.delenv("PERGEN_TRUST_PROXY", raising=False)
    else:
        monkeypatch.setenv("PERGEN_TRUST_PROXY", trust_proxy)
    for mod in [
        "backend.app",
        "backend.app_factory",
        "backend.blueprints",
        "backend.config",
        "backend.config.app_config",
        "backend.config.settings",
    ]:
        sys.modules.pop(mod, None)
    factory = importlib.import_module("backend.app_factory")
    app = factory.create_app("development")
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    return app


def test_proxy_fix_not_mounted_when_env_unset(monkeypatch, tmp_path) -> None:
    """Default posture: ``app.wsgi_app`` must NOT be a ProxyFix instance."""
    app = _build_app_with_env(monkeypatch, tmp_path, trust_proxy=None)
    assert not isinstance(app.wsgi_app, ProxyFix), (
        "ProxyFix must not be mounted by default — it lets X-Forwarded-For "
        "spoof remote_addr and bypass per-IP defences (audit H-1)"
    )


def test_proxy_fix_mounted_when_env_set_to_one(monkeypatch, tmp_path) -> None:
    """``PERGEN_TRUST_PROXY=1`` → ``app.wsgi_app`` IS a ProxyFix instance."""
    app = _build_app_with_env(monkeypatch, tmp_path, trust_proxy="1")
    assert isinstance(app.wsgi_app, ProxyFix), (
        "PERGEN_TRUST_PROXY=1 must mount werkzeug ProxyFix so "
        "request.remote_addr reflects the original client IP behind a "
        "trusted reverse proxy (audit H-1)"
    )


@pytest.mark.parametrize("falsy", ["0", "true", "TRUE", "yes", "on", "", " "])
def test_proxy_fix_not_mounted_for_truthy_but_not_one(
    monkeypatch, tmp_path, falsy: str
) -> None:
    """Defensive parsing: only the literal ``"1"`` opts in.

    Operators commonly write ``true`` / ``yes`` / ``on`` for boolean envs.
    The audit's intent is an explicit, deliberate opt-in — anything other
    than ``"1"`` must be treated as "not opted in" so a typo cannot
    silently widen trust.
    """
    app = _build_app_with_env(monkeypatch, tmp_path, trust_proxy=falsy)
    assert not isinstance(app.wsgi_app, ProxyFix), (
        f"PERGEN_TRUST_PROXY={falsy!r} must NOT mount ProxyFix — only "
        f"the literal string '1' is the documented opt-in (audit H-1)"
    )


def test_proxy_fix_wrapped_app_still_serves_requests(monkeypatch, tmp_path) -> None:
    """Smoke: with ProxyFix mounted, requests still flow end-to-end."""
    app = _build_app_with_env(monkeypatch, tmp_path, trust_proxy="1")
    client = app.test_client()
    # /api/health is gate-exempt and always returns 200.
    r = client.get("/api/health")
    assert r.status_code == 200, r.get_data(as_text=True)
