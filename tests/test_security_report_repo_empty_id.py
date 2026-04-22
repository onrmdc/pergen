"""M-05 — `ReportRepository._safe_id("")` returns the literal `default`.

Two distinct callers passing an empty `run_id` will silently overwrite the
same `default.json.gz` file. An attacker with `/api/run/pre/create` access
can flush a victim's "default" report.

Audit reference: ``docs/security/audit_2026-04-22.md`` §3.2 M-05.

Desired contract: `save(run_id="")` raises `ValueError`. XFAIL until the
guard lands.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.security]


def test_report_save_rejects_empty_run_id(tmp_path: Path) -> None:
    from backend.repositories.report_repository import ReportRepository

    repo = ReportRepository(str(tmp_path))
    with pytest.raises(ValueError):
        repo.save(
            run_id="",
            name="x",
            created_at="2026-04-22T00:00:00Z",
            devices=[],
            device_results=[],
        )


def test_report_save_rejects_whitespace_run_id(tmp_path: Path) -> None:
    from backend.repositories.report_repository import ReportRepository

    repo = ReportRepository(str(tmp_path))
    with pytest.raises(ValueError):
        repo.save(
            run_id="   ",
            name="x",
            created_at="2026-04-22T00:00:00Z",
            devices=[],
            device_results=[],
        )
