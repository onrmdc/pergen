"""Wave-4 W4-M-01 backfill — stamp legacy reports with ``created_by_actor``.

Reports written before the W4-M-01 fix landed have no
``created_by_actor`` field. This is operationally fine — the loader
treats the absent field as the literal ``"legacy"`` and grants every
actor read access for back-compat. But operators who want to lock down
old reports retroactively can run this CLI to assign an explicit owner.

Usage
-----
::

    # Default: stamp every report missing the field with "legacy".
    python -m backend.cli.backfill_report_actors

    # Stamp with an explicit owner (e.g. the original ops team alias).
    python -m backend.cli.backfill_report_actors --owner=netops-2026

    # Dry-run (print planned changes; do not write).
    python -m backend.cli.backfill_report_actors --dry-run

    # Override the reports directory (defaults to PERGEN_INSTANCE_DIR/reports).
    python -m backend.cli.backfill_report_actors --reports-dir=/path/to/reports

Idempotent
----------
Reports that already have a ``created_by_actor`` field are skipped.
Re-running this command on a partially-stamped dataset is harmless.

Why no Flask app
----------------
This is a one-shot operator tool, not a route. We touch only the
``ReportRepository`` API + the gzipped JSON files on disk. No Flask
context, no token gate, no extensions.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from pathlib import Path


def _default_reports_dir() -> Path:
    base = os.environ.get("PERGEN_INSTANCE_DIR")
    if base:
        return Path(base) / "reports"
    # Fall back to the in-repo default.
    return Path(__file__).resolve().parent.parent / "instance" / "reports"


def _stamp_payload(payload: dict, owner: str) -> bool:
    """Return True iff the payload was modified."""
    if "created_by_actor" in payload and payload["created_by_actor"]:
        return False
    payload["created_by_actor"] = owner
    return True


def _stamp_index_entry(entry: dict, owner: str) -> bool:
    if "created_by_actor" in entry and entry["created_by_actor"]:
        return False
    entry["created_by_actor"] = owner
    return True


def _backfill(reports_dir: Path, owner: str, dry_run: bool) -> tuple[int, int, int]:
    """Backfill the directory.

    Returns ``(stamped, skipped, errors)``.
    """
    if not reports_dir.is_dir():
        print(f"reports dir not found: {reports_dir}", file=sys.stderr)
        return (0, 0, 1)

    stamped = 0
    skipped = 0
    errors = 0

    # Stamp each gzipped payload.
    for path in sorted(reports_dir.glob("*.json.gz")):
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  ERROR reading {path.name}: {exc}", file=sys.stderr)
            errors += 1
            continue

        if not _stamp_payload(payload, owner):
            skipped += 1
            continue

        if dry_run:
            print(f"  WOULD STAMP {path.name} -> created_by_actor={owner!r}")
        else:
            try:
                with gzip.open(path, "wt", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False)
                print(f"  stamped {path.name} -> created_by_actor={owner!r}")
            except OSError as exc:
                print(f"  ERROR writing {path.name}: {exc}", file=sys.stderr)
                errors += 1
                continue
        stamped += 1

    # Stamp the index.
    index_path = reports_dir / "index.json"
    if index_path.is_file():
        try:
            with index_path.open(encoding="utf-8") as f:
                entries = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  ERROR reading index.json: {exc}", file=sys.stderr)
            errors += 1
        else:
            if isinstance(entries, list):
                changed = False
                for entry in entries:
                    if isinstance(entry, dict) and _stamp_index_entry(entry, owner):
                        changed = True
                if changed:
                    if dry_run:
                        print("  WOULD UPDATE index.json")
                    else:
                        with index_path.open("w", encoding="utf-8") as f:
                            json.dump(entries, f, ensure_ascii=False)
                        print("  updated index.json")
                else:
                    print("  index.json: nothing to stamp")

    return (stamped, skipped, errors)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.cli.backfill_report_actors",
        description=(
            "Stamp legacy reports under instance/reports/ with the "
            "wave-4 W4-M-01 ``created_by_actor`` field."
        ),
    )
    parser.add_argument(
        "--owner",
        default="legacy",
        help='Owner string to stamp on un-tagged reports (default: "legacy").',
    )
    parser.add_argument(
        "--reports-dir",
        default=None,
        help=(
            "Path to the reports directory. Defaults to "
            "$PERGEN_INSTANCE_DIR/reports or backend/instance/reports."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes; do not write.",
    )
    args = parser.parse_args(argv)

    reports_dir = Path(args.reports_dir) if args.reports_dir else _default_reports_dir()
    print(f"Backfilling: {reports_dir}")
    print(f"  Owner:     {args.owner!r}")
    print(f"  Dry-run:   {args.dry_run}")
    print()

    stamped, skipped, errors = _backfill(reports_dir, args.owner, args.dry_run)

    print()
    print(f"Summary: stamped={stamped} skipped={skipped} errors={errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
