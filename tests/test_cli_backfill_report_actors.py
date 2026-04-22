"""Unit tests for the W4-M-01 backfill CLI.

Exercises the operator tool that stamps legacy reports with
``created_by_actor``. Tests run against a temporary reports directory
seeded with a mix of pre- and post-W4-M-01 payloads to verify:

1. Reports without ``created_by_actor`` get stamped with the supplied owner.
2. Reports already carrying the field are skipped (idempotent).
3. ``--dry-run`` prints planned changes without touching files on disk.
4. Index entries are stamped in lockstep with the gzipped payloads.
5. Missing reports directory exits with a non-zero status.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from backend.cli.backfill_report_actors import _backfill, main


def _seed_legacy_report(reports_dir: Path, run_id: str) -> Path:
    path = reports_dir / f"{run_id}.json.gz"
    payload = {
        "run_id": run_id,
        "name": "legacy-report",
        "created_at": "2026-01-01T00:00:00Z",
        "devices": [{"hostname": f"leaf-{run_id}", "ip": "10.0.0.1"}],
        "device_results": [
            {"hostname": f"leaf-{run_id}", "parsed_flat": {"v": "x"}}
        ],
    }
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(payload, f)
    return path


def _seed_index(reports_dir: Path, entries: list[dict]) -> None:
    with (reports_dir / "index.json").open("w", encoding="utf-8") as f:
        json.dump(entries, f)


def _read_payload(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture()
def reports_dir(tmp_path: Path) -> Path:
    d = tmp_path / "reports"
    d.mkdir()
    return d


class TestBackfill:
    def test_stamps_legacy_payloads(self, reports_dir: Path) -> None:
        p1 = _seed_legacy_report(reports_dir, "old-1")
        p2 = _seed_legacy_report(reports_dir, "old-2")
        _seed_index(
            reports_dir,
            [
                {"run_id": "old-1", "name": "legacy-report", "created_at": "2026-01-01"},
                {"run_id": "old-2", "name": "legacy-report", "created_at": "2026-01-02"},
            ],
        )

        stamped, skipped, errors = _backfill(reports_dir, owner="legacy", dry_run=False)
        assert (stamped, skipped, errors) == (2, 0, 0)

        # Both gzipped payloads now carry the field.
        assert _read_payload(p1)["created_by_actor"] == "legacy"
        assert _read_payload(p2)["created_by_actor"] == "legacy"
        # The index entries too.
        with (reports_dir / "index.json").open() as f:
            entries = json.load(f)
        assert all(e["created_by_actor"] == "legacy" for e in entries)

    def test_idempotent_skips_already_stamped(self, reports_dir: Path) -> None:
        p1 = _seed_legacy_report(reports_dir, "old-1")
        # Stamp once.
        _backfill(reports_dir, owner="legacy", dry_run=False)
        # Stamp again.
        stamped, skipped, errors = _backfill(reports_dir, owner="legacy", dry_run=False)
        assert stamped == 0
        assert skipped == 1
        assert errors == 0
        assert _read_payload(p1)["created_by_actor"] == "legacy"

    def test_dry_run_does_not_modify_files(self, reports_dir: Path) -> None:
        p1 = _seed_legacy_report(reports_dir, "old-1")
        original = _read_payload(p1)
        assert "created_by_actor" not in original

        stamped, skipped, errors = _backfill(reports_dir, owner="legacy", dry_run=True)
        assert stamped == 1
        assert errors == 0

        # Disk untouched.
        on_disk = _read_payload(p1)
        assert "created_by_actor" not in on_disk

    def test_missing_directory_returns_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist"
        stamped, skipped, errors = _backfill(missing, owner="legacy", dry_run=False)
        assert stamped == 0
        assert skipped == 0
        assert errors == 1

    def test_handles_corrupt_gzip_gracefully(self, reports_dir: Path) -> None:
        # A malformed file should be reported as error but not crash.
        bad = reports_dir / "broken.json.gz"
        bad.write_bytes(b"not really gzip")
        stamped, skipped, errors = _backfill(reports_dir, owner="legacy", dry_run=False)
        assert stamped == 0
        assert errors == 1


class TestMainEntrypoint:
    def test_exit_zero_on_success(self, reports_dir: Path) -> None:
        _seed_legacy_report(reports_dir, "old-1")
        rc = main(["--reports-dir", str(reports_dir), "--owner", "netops"])
        assert rc == 0

    def test_exit_nonzero_on_missing_dir(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope"
        rc = main(["--reports-dir", str(missing)])
        assert rc != 0

    def test_dry_run_flag(self, reports_dir: Path) -> None:
        p1 = _seed_legacy_report(reports_dir, "old-1")
        rc = main(["--reports-dir", str(reports_dir), "--dry-run"])
        assert rc == 0
        # Disk untouched.
        assert "created_by_actor" not in _read_payload(p1)
