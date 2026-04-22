"""W4-M-01 — `POST /api/reports/<id>/restore` actor-scoping bypass.

Wave-4 audit (docs/security/audit_2026-04-22-wave4.md §3.2 W4-M-01).
The wave-3 fix correctly moved restore from GET ?restore=1 to POST,
but did not add actor scoping at the report-load step. Bob can
restore any saved report and re-bind its in-memory state ownership
to himself.

Properly fixing this requires recording ``created_by_actor`` in the
report-on-disk format AND projecting the index-listing to filter by
actor. That's a paired ReportRepository + ReportService change with
a data-migration concern (existing reports have no creator field).

This test pins the contract for when the fix lands: Bob attempting
to restore Alice's saved report must be refused. Marked xfail until
the report-on-disk owner field lands.
"""

from __future__ import annotations

import importlib
import sys

import pytest

pytestmark = [pytest.mark.security]


def _gated_client(monkeypatch, tmp_path):
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "test-w4-m01")
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


def test_report_restore_rejects_cross_actor(monkeypatch, tmp_path) -> None:
    """W4-M-01 — Bob must NOT be able to restore Alice's saved report."""
    client = _gated_client(monkeypatch, tmp_path)

    # Alice creates a PRE run, which auto-saves a report to disk.
    devices = [{"hostname": "h", "ip": "1.2.3.4"}]
    pre_results = [{"hostname": "h", "parsed_flat": {"secret": "x"}}]
    rcreate = client.post(
        "/api/run/pre/create",
        json={"devices": devices, "device_results": pre_results, "name": "alice-report"},
        headers={"X-API-Token": "a" * 32},
    )
    assert rcreate.status_code in (200, 201), rcreate.get_data(as_text=True)
    rid = rcreate.get_json().get("run_id")

    # Bob attempts to restore Alice's saved report.
    r = client.post(
        f"/api/reports/{rid}/restore",
        headers={"X-API-Token": "b" * 32},
    )
    assert r.status_code in (403, 404), (
        f"cross-actor restore succeeded (status={r.status_code}); "
        f"see W4-M-01"
    )
