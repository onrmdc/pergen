#!/usr/bin/env python3
"""
Operator CLI — migrate Pergen credentials from the legacy SQLite store
(``instance/credentials.db``, single SHA-256 → Fernet) to the new
authenticated store (``instance/credentials_v2.db``, PBKDF2-HMAC-SHA256
600 000 → AES-128-CBC + HMAC-SHA256).

Wave-6 Phase E.3 — wraps ``backend.repositories.credential_migration``.

Usage
-----

::

    # Dry-run (no v2 writes; print what would happen).
    python scripts/migrate_credentials_v1_to_v2.py --dry-run

    # Real migration — operator must have stopped Pergen first.
    python scripts/migrate_credentials_v1_to_v2.py

    # Verbose per-row report (no payloads — names + methods + status).
    python scripts/migrate_credentials_v1_to_v2.py --verbose

    # Override paths (defaults: $PERGEN_INSTANCE_DIR/credentials{.db,_v2.db}
    # or backend/instance/<...>).
    python scripts/migrate_credentials_v1_to_v2.py \\
        --legacy-db /custom/credentials.db \\
        --v2-db /custom/credentials_v2.db

Pre-flight
----------
Before any v2 write the script performs a *canary decrypt* against the
legacy store; if ``SECRET_KEY`` is wrong the migration **refuses to
proceed** (exit code 2).  This prevents an operator with a stale env
var from silently producing zero migrated rows.

Exit codes
----------
* ``0`` — success (or successful dry-run).
* ``1`` — at least one row failed to migrate.
* ``2`` — pre-flight refused (missing SECRET_KEY, missing legacy DB,
  wrong key).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Make the repo importable when the script is invoked directly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.repositories.credential_migration import (  # noqa: E402
    migrate_credentials,
    verify_can_decrypt,
)


def _default_instance_dir() -> Path:
    base = os.environ.get("PERGEN_INSTANCE_DIR")
    if base:
        return Path(base)
    return _REPO_ROOT / "backend" / "instance"


def _resolve_secret_key() -> str | None:
    val = os.environ.get("SECRET_KEY")
    if not val:
        return None
    return val.strip() or None


def _print_summary(result: dict, *, dry_run: bool) -> None:
    print()
    print("Summary")
    print("-------")
    label = "would migrate" if dry_run else "migrated"
    print(f"  {label}: {result['migrated']}")
    print(f"  skipped (already in v2): {result['skipped']}")
    print(f"  errors: {len(result['errors'])}")
    if result["errors"]:
        print()
        print("Errors:")
        for err in result["errors"]:
            print(f"  - {err}")
    if result.get("details"):
        print()
        print("Per-row detail (name, method, status):")
        for d in result["details"]:
            print(f"  {d['name']!r:30s} {d['method']:8s} {d['status']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate_credentials_v1_to_v2.py",
        description=(
            "Migrate Pergen credentials from the legacy SHA-256 → Fernet "
            "store (instance/credentials.db) to the new PBKDF2 600k → "
            "AES-128-CBC+HMAC store (instance/credentials_v2.db)."
        ),
    )
    instance = _default_instance_dir()
    parser.add_argument(
        "--legacy-db",
        default=str(instance / "credentials.db"),
        help=(
            "Path to the legacy SQLite store. "
            "Default: $PERGEN_INSTANCE_DIR/credentials.db."
        ),
    )
    parser.add_argument(
        "--v2-db",
        default=str(instance / "credentials_v2.db"),
        help=(
            "Path to the new SQLite store (created if missing). "
            "Default: $PERGEN_INSTANCE_DIR/credentials_v2.db."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Decrypt legacy rows but do NOT write to the v2 store.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "Emit a per-row {name, method, status} line in the summary. "
            "No payloads are ever printed."
        ),
    )
    args = parser.parse_args(argv)

    secret_key = _resolve_secret_key()
    if not secret_key:
        print(
            "ERROR: SECRET_KEY env var is required (must match the running app).",
            file=sys.stderr,
        )
        return 2

    legacy = args.legacy_db
    v2 = args.v2_db

    print("Pergen credential migration")
    print("---------------------------")
    print(f"  legacy DB: {legacy}")
    print(f"  v2 DB:     {v2}")
    print(f"  dry-run:   {args.dry_run}")
    print(f"  verbose:   {args.verbose}")
    print()

    if not os.path.exists(legacy):
        print(
            f"ERROR: legacy DB not found at {legacy}. "
            "Set --legacy-db or PERGEN_INSTANCE_DIR.",
            file=sys.stderr,
        )
        return 2

    print("Pre-flight: canary decrypt against legacy store...")
    ok, sample, error = verify_can_decrypt(legacy, secret_key)
    if not ok:
        print(f"ERROR: pre-flight failed — {error}", file=sys.stderr)
        return 2
    if sample is None:
        print("  legacy store is empty — nothing to migrate.")
    else:
        print(f"  decrypted canary entry: {sample!r}")
    print()

    print("Running migration...")
    result = migrate_credentials(
        legacy,
        v2,
        secret_key,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    _print_summary(result, dry_run=args.dry_run)

    if result["errors"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
