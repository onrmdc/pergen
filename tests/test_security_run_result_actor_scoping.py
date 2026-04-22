"""M-02 — `/api/run/result/<run_id>` per-actor scoping.

Audit M-02 (docs/security/audit_2026-04-22.md §3.2). With multi-actor
token gating, an actor must only see runs they created — Bob trying to
read Alice's run must get the same response as a non-existent id (404)
so the response cannot disclose existence.

Wave-3 Phase 4 added ``actor`` parameter to RunStateStore.set/get; the
runs_bp routes now thread the gate's ``g.actor`` through.
"""

from __future__ import annotations

import importlib
import sys

import pytest

pytestmark = [pytest.mark.security]


def _gated_client(monkeypatch, tmp_path):
    """Build a fresh app with a multi-actor token gate enabled."""
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "test-actor-scoping")
    monkeypatch.setenv(
        "PERGEN_API_TOKENS",
        "alice:" + "a" * 32 + ",bob:" + "b" * 32,
    )
    monkeypatch.delenv("PERGEN_DEV_OPEN_API", raising=False)
    monkeypatch.delenv("PERGEN_API_TOKEN", raising=False)
    for mod in [
        "backend.app",
        "backend.app_factory",
        "backend.config",
        "backend.config.app_config",
        "backend.config.settings",
    ]:
        sys.modules.pop(mod, None)
    factory = importlib.import_module("backend.app_factory")
    app = factory.create_app("development")
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    return app.test_client()


def test_run_result_rejects_actor_mismatch(monkeypatch, tmp_path) -> None:
    """Bob must not be able to read Alice's run state via /api/run/result/<id>."""
    client = _gated_client(monkeypatch, tmp_path)
    # Alice creates a pre-run via /api/run/pre/create (requires matching
    # device_results length).
    devices = [{"hostname": "h", "ip": "1.2.3.4"}]
    device_results = [{"hostname": "h", "parsed_flat": {}}]
    rcreate = client.post(
        "/api/run/pre/create",
        json={"devices": devices, "device_results": device_results, "name": "alice-run"},
        headers={"X-API-Token": "a" * 32},
    )
    assert rcreate.status_code in (200, 201), rcreate.get_data(as_text=True)
    rid = rcreate.get_json().get("run_id")
    assert rid

    # Alice can read her own run.
    rself = client.get(f"/api/run/result/{rid}", headers={"X-API-Token": "a" * 32})
    assert rself.status_code == 200

    # Bob attempts to read Alice's run — must be refused.
    r = client.get(
        f"/api/run/result/{rid}",
        headers={"X-API-Token": "b" * 32},
    )
    assert r.status_code in (403, 404), (
        f"actor scoping missing: bob reached alice's run state ({r.status_code})"
    )
