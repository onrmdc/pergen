"""
Token-gate snapshot at boot (audit H-06).

Wave-3 Phase 5 landed the immutable-snapshot fix. ``_install_api_token_gate``
now resolves tokens once at ``create_app`` time and freezes the result
into ``app.extensions['pergen']['token_snapshot']`` (a ``MappingProxyType``).
Per-request handler reads only from the snapshot — no per-request env
read. Closes the timing-attack surface flagged by the audit.

This test is the contract pin: a runtime ``del os.environ[...]`` must
NOT downgrade the gate, AND the original token must still authenticate.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.security]


def test_token_gate_resolves_tokens_once_at_startup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    token = "t" * 64  # >= 32 chars
    monkeypatch.setenv("SECRET_KEY", "s" * 64)
    monkeypatch.setenv("PERGEN_API_TOKEN", token)
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))

    for mod in [
        "backend.app",
        "backend.app_factory",
        "backend.config",
        "backend.config.settings",
        "backend.config.app_config",
    ]:
        sys.modules.pop(mod, None)
    factory = importlib.import_module("backend.app_factory")
    app = factory.create_app("production")
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)

    # Now scrub the env — a startup-bound gate must still accept the
    # original token; a per-request gate will not.
    monkeypatch.delenv("PERGEN_API_TOKEN", raising=False)
    app.config.pop("PERGEN_API_TOKEN", None)
    assert "PERGEN_API_TOKEN" not in os.environ

    client = app.test_client()
    # Use a non-exempt /api/* route so the token gate is actually consulted.
    # If the gate snapshotted at startup it still requires the token →
    # request WITHOUT the token must be rejected (401/403). If the gate
    # re-reads env per request, scrubbing the env downgrades it to a
    # no-op and an unauthenticated request succeeds (200) — which is
    # exactly the audit gap.
    r_no_token = client.get("/api/inventory")
    assert r_no_token.status_code in (401, 403), (
        "token gate must reject unauthenticated requests even after the env "
        f"var is scrubbed (got {r_no_token.status_code}); this proves the "
        "gate uses a startup-time snapshot rather than a per-request env read."
    )
    # Sanity: the original token still works.
    r_ok = client.get("/api/inventory", headers={"X-API-Token": token})
    assert r_ok.status_code == 200, (
        f"original token must still be accepted (got {r_ok.status_code})"
    )
