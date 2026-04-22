"""
Audit-log coverage gaps.

The transceiver and credential blueprints already emit ``app.audit``
log lines for destructive operations (see ``test_security_audit_findings``).
The audit found four routes that *should* also emit audit lines but
don't yet: inventory add, notepad save, run/pre, and report delete.

Each test below documents the expected behaviour. They are marked
``xfail`` so they pass as xfail today and act as a tracker — once the
audit lines are added in their respective blueprints, the xfail flips
to a real pass.
"""
from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.security]


def _audit_records(caplog) -> list[logging.LogRecord]:
    return [
        r
        for r in caplog.records
        if "audit" in r.name.lower() or "audit" in (r.message or "").lower()
    ]


def test_inventory_add_emits_audit_log(client, caplog) -> None:
    caplog.set_level(logging.INFO)
    r = client.post(
        "/api/inventory/device",
        json={
            "hostname": "leaf-99",
            "ip": "10.0.99.1",
            "fabric": "FAB1",
            "site": "Mars",
            "hall": "Hall-1",
            "vendor": "Arista",
            "model": "EOS",
            "role": "Leaf",
            "credential": "test-cred",
        },
    )
    assert r.status_code in (200, 400, 409)
    assert _audit_records(caplog), (
        "POST /api/inventory/device must emit an app.audit line "
        "(actor + inventory.add)"
    )


def test_notepad_save_emits_audit_log(client, caplog) -> None:
    caplog.set_level(logging.INFO)
    r = client.put(
        "/api/notepad",
        json={"content": "audit-coverage probe", "user": "alice"},
    )
    assert r.status_code in (200, 500)
    assert _audit_records(caplog), (
        "PUT /api/notepad must emit an app.audit line (actor + notepad.save)"
    )


def test_run_pre_emits_audit_log(client, caplog) -> None:
    caplog.set_level(logging.INFO)
    # Stub the inline runner so we don't actually try to SSH to the device.
    with patch(
        "backend.blueprints.runs_bp._run_devices_inline",
        return_value=[{"hostname": "leaf-01", "ok": True, "outputs": []}],
    ):
        r = client.post(
            "/api/run/pre",
            json={
                "devices": [
                    {
                        "hostname": "leaf-01",
                        "ip": "10.0.0.1",
                        "vendor": "Arista",
                        "role": "Leaf",
                        "credential": "test-cred",
                    }
                ]
            },
        )
    assert r.status_code in (200, 400, 404, 500)
    assert _audit_records(caplog), (
        "POST /api/run/pre must emit an app.audit line (actor + run.pre)"
    )


def test_report_delete_emits_audit_log(client, caplog) -> None:
    caplog.set_level(logging.INFO)
    r = client.delete("/api/reports/probe-run-id-does-not-exist")
    # 200 (deleted) or 500 (not found / ignored) — both acceptable; the
    # audit line is what matters.
    assert r.status_code in (200, 404, 500)
    assert _audit_records(caplog), (
        "DELETE /api/reports/<id> must emit an app.audit line "
        "(actor + report.delete)"
    )
