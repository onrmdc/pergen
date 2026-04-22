"""W4-H-01 — `/api/run/post/complete` actor-scoping bypass.

Wave-4 audit (docs/security/audit_2026-04-22-wave4.md §3.1) found that
``api_run_post_complete`` calls ``store.get(run_id)`` *without* the
``actor=_current_actor()`` argument that every other state-store read
in ``runs_bp.py`` passes. This means Bob can complete Alice's PRE run
and write tampered POST results into her run-state slot AND persist
them to disk under her run_id.

The wave-3 Phase 4 fix to /api/run/result, /api/run/post, and
/api/reports/<id>/restore was correct; this one route was simply
forgotten in the same commit (mechanical oversight, not a design flaw).

This is the contract pin: Bob must NOT be able to complete Alice's run.
"""

from __future__ import annotations

import importlib
import sys

import pytest

pytestmark = [pytest.mark.security]


def _gated_client(monkeypatch, tmp_path):
    """Build a fresh app with a multi-actor token gate enabled.

    Mirrors the helper in test_security_run_result_actor_scoping.py so
    both tests use the same fixture pattern.
    """
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "test-actor-scoping-w4")
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


def test_run_post_complete_rejects_actor_mismatch(monkeypatch, tmp_path) -> None:
    """W4-H-01 — Bob must NOT be able to complete Alice's PRE run."""
    client = _gated_client(monkeypatch, tmp_path)
    devices = [{"hostname": "h", "ip": "1.2.3.4"}]
    pre_results = [{"hostname": "h", "parsed_flat": {}}]

    # Alice creates a PRE run.
    rcreate = client.post(
        "/api/run/pre/create",
        json={"devices": devices, "device_results": pre_results, "name": "alice-run"},
        headers={"X-API-Token": "a" * 32},
    )
    assert rcreate.status_code in (200, 201), rcreate.get_data(as_text=True)
    rid = rcreate.get_json().get("run_id")
    assert rid

    # Bob attempts to complete Alice's PRE — must be refused (404 or 403,
    # mirroring the actor-scoping contract used elsewhere).
    bob_post_results = [{"hostname": "h", "parsed_flat": {"tampered": True}}]
    r = client.post(
        "/api/run/post/complete",
        json={"run_id": rid, "device_results": bob_post_results},
        headers={"X-API-Token": "b" * 32},
    )
    assert r.status_code in (403, 404), (
        f"actor scoping missing on /api/run/post/complete: bob completed "
        f"alice's run (status={r.status_code})"
    )

    # Sanity: alice CAN complete her own run.
    r_self = client.post(
        "/api/run/post/complete",
        json={"run_id": rid, "device_results": pre_results},
        headers={"X-API-Token": "a" * 32},
    )
    assert r_self.status_code == 200, (
        f"alice could not complete her own run (status={r_self.status_code})"
    )
