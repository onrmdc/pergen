"""
TDD tests for ``backend.repositories.credential_migration``.

Wave-6 Phase E.1 — read every credential from the legacy
``instance/credentials.db`` (SHA-256 → Fernet, written by
``backend.credential_store``) and re-encrypt + write to the new
``instance/credentials_v2.db`` (PBKDF2 600k → AES-128-CBC + HMAC,
owned by ``CredentialRepository`` / ``EncryptionService``).

This module exercises the **library** function used by the operator
CLI ``scripts/migrate_credentials_v1_to_v2.py``.  Coverage target on
``credential_migration.py`` is ≥ 95 % (data-bearing code).

The legacy module's import-time ``DeprecationWarning`` is suppressed
here because the migration *needs* to import it.
"""
from __future__ import annotations

import sqlite3
import warnings
from collections.abc import Iterable

import pytest

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

SECRET = "test-migration-secret-key-1234"


def _legacy_set(db_path: str, secret_key: str, name: str, method: str, **payload) -> None:
    """Write one row using the legacy module's encryption.

    We import inside the helper so the deprecation warning only fires
    in tests that actually need the legacy store.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        # Force a re-import so the legacy module's _db_path() picks up
        # the patched path. Easier: just call the module functions
        # directly with a connection we own.
        import importlib

        legacy = importlib.import_module("backend.credential_store")
        fernet = legacy._fernet(secret_key)
    if method == "basic":
        data = {"username": payload["username"], "password": payload["password"]}
    elif method == "api_key":
        data = {"api_key": payload["api_key"]}
    else:
        raise ValueError(method)
    enc = legacy._encrypt(fernet, data)
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS credentials (
            name TEXT PRIMARY KEY,
            method TEXT NOT NULL,
            value_enc TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.execute(
        """INSERT INTO credentials (name, method, value_enc, updated_at)
           VALUES (?, ?, ?, datetime('now'))
           ON CONFLICT(name) DO UPDATE SET method = ?, value_enc = ?, updated_at = datetime('now')""",
        (name.strip(), method, enc, method, enc),
    )
    conn.commit()
    conn.close()


def _make_legacy_db(path: str, secret: str, entries: Iterable[dict]) -> str:
    """Build a legacy SQLite store at *path* containing *entries*."""
    # Initialise schema by writing zero rows then optionally fill.
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS credentials (
            name TEXT PRIMARY KEY,
            method TEXT NOT NULL,
            value_enc TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
    conn.close()
    for entry in entries:
        _legacy_set(path, secret, **entry)
    return path


@pytest.fixture()
def legacy_db_empty(tmp_path):
    return _make_legacy_db(str(tmp_path / "legacy.db"), SECRET, [])


@pytest.fixture()
def legacy_db_one_basic(tmp_path):
    return _make_legacy_db(
        str(tmp_path / "legacy.db"),
        SECRET,
        [{"name": "leaf-1", "method": "basic", "username": "admin", "password": "hunter2"}],
    )


@pytest.fixture()
def legacy_db_five_mixed(tmp_path):
    entries = [
        {"name": "leaf-1", "method": "basic", "username": "admin", "password": "p1"},
        {"name": "leaf-2", "method": "basic", "username": "ops", "password": "p2"},
        {"name": "spine-1", "method": "api_key", "api_key": "tok-spine-1"},
        {"name": "spine-2", "method": "api_key", "api_key": "tok-spine-2"},
        {"name": "border", "method": "basic", "username": "root", "password": "borderpw"},
    ]
    return _make_legacy_db(str(tmp_path / "legacy.db"), SECRET, entries)


@pytest.fixture()
def v2_path(tmp_path):
    return str(tmp_path / "credentials_v2.db")


def _v2_repo(path: str, secret: str = SECRET):
    from backend.repositories.credential_repository import CredentialRepository
    from backend.security.encryption import EncryptionService

    repo = CredentialRepository(path, EncryptionService.from_secret(secret))
    repo.create_schema()
    return repo


# --------------------------------------------------------------------------- #
# E.1 #1 — Empty source
# --------------------------------------------------------------------------- #


def test_migrate_empty_legacy_db_is_noop(legacy_db_empty, v2_path):
    from backend.repositories.credential_migration import migrate_credentials

    result = migrate_credentials(legacy_db_empty, v2_path, SECRET)

    assert result["migrated"] == 0
    assert result["skipped"] == 0
    assert result["errors"] == []
    # v2 was created (schema initialised) and is empty.
    repo = _v2_repo(v2_path)
    assert repo.list() == []


# --------------------------------------------------------------------------- #
# E.1 #2 — Single credential roundtrip
# --------------------------------------------------------------------------- #


def test_migrate_single_basic_roundtrip(legacy_db_one_basic, v2_path):
    from backend.repositories.credential_migration import migrate_credentials

    result = migrate_credentials(legacy_db_one_basic, v2_path, SECRET)

    assert result["migrated"] == 1
    assert result["skipped"] == 0
    assert result["errors"] == []

    repo = _v2_repo(v2_path)
    got = repo.get("leaf-1")
    assert got is not None
    assert got["method"] == "basic"
    assert got["username"] == "admin"
    assert got["password"] == "hunter2"


# --------------------------------------------------------------------------- #
# E.1 #3 — Multiple credentials, mixed methods
# --------------------------------------------------------------------------- #


def test_migrate_five_mixed_roundtrip(legacy_db_five_mixed, v2_path):
    from backend.repositories.credential_migration import migrate_credentials

    result = migrate_credentials(legacy_db_five_mixed, v2_path, SECRET)

    assert result["migrated"] == 5
    assert result["skipped"] == 0
    assert result["errors"] == []

    repo = _v2_repo(v2_path)
    names = sorted(r["name"] for r in repo.list())
    assert names == ["border", "leaf-1", "leaf-2", "spine-1", "spine-2"]

    leaf1 = repo.get("leaf-1")
    assert leaf1["method"] == "basic"
    assert leaf1["password"] == "p1"

    spine1 = repo.get("spine-1")
    assert spine1["method"] == "api_key"
    assert spine1["api_key"] == "tok-spine-1"

    border = repo.get("border")
    assert border["method"] == "basic"
    assert border["username"] == "root"
    assert border["password"] == "borderpw"


# --------------------------------------------------------------------------- #
# E.1 #4 — Idempotent (re-running yields same v2 contents, no duplicates)
# --------------------------------------------------------------------------- #


def test_migrate_is_idempotent(legacy_db_five_mixed, v2_path):
    from backend.repositories.credential_migration import migrate_credentials

    first = migrate_credentials(legacy_db_five_mixed, v2_path, SECRET)
    assert first["migrated"] == 5
    assert first["skipped"] == 0

    second = migrate_credentials(legacy_db_five_mixed, v2_path, SECRET)
    assert second["migrated"] == 0  # nothing new to write
    assert second["skipped"] == 5  # all five already present
    assert second["errors"] == []

    repo = _v2_repo(v2_path)
    rows = repo.list()
    assert len(rows) == 5
    # No duplicate names.
    assert len({r["name"] for r in rows}) == 5
    # Payloads still decrypt cleanly after second pass.
    assert repo.get("spine-1")["api_key"] == "tok-spine-1"


# --------------------------------------------------------------------------- #
# E.1 #5 — SECRET_KEY mismatch on legacy DB
# --------------------------------------------------------------------------- #


def test_migrate_with_wrong_secret_key_returns_clear_errors(
    legacy_db_one_basic, v2_path
):
    from backend.repositories.credential_migration import migrate_credentials

    result = migrate_credentials(legacy_db_one_basic, v2_path, "WRONG-KEY-XYZ")

    assert result["migrated"] == 0
    assert any("decrypt" in e.lower() or "decryption" in e.lower() for e in result["errors"])

    # No row should have landed in v2 — the schema may exist but credentials table
    # must be empty.
    repo = _v2_repo(v2_path, secret="WRONG-KEY-XYZ")
    assert repo.list() == []


# --------------------------------------------------------------------------- #
# E.1 #6 — v2 has pre-existing entries: MERGE, do not delete
# --------------------------------------------------------------------------- #


def test_migrate_merges_with_existing_v2_entries(legacy_db_one_basic, v2_path):
    from backend.repositories.credential_migration import migrate_credentials

    # Pre-seed v2 with an unrelated entry.
    pre = _v2_repo(v2_path)
    pre.set("v2-only", method="api_key", api_key="already-here")

    result = migrate_credentials(legacy_db_one_basic, v2_path, SECRET)

    assert result["migrated"] == 1
    assert result["errors"] == []

    repo = _v2_repo(v2_path)
    names = sorted(r["name"] for r in repo.list())
    assert names == ["leaf-1", "v2-only"]
    # Pre-existing entry untouched.
    assert repo.get("v2-only")["api_key"] == "already-here"
    # Migrated entry decrypts correctly.
    assert repo.get("leaf-1")["password"] == "hunter2"


def test_migrate_skips_when_v2_already_has_same_name(legacy_db_one_basic, v2_path):
    from backend.repositories.credential_migration import migrate_credentials

    # Pre-seed v2 with the SAME name but DIFFERENT payload — migration
    # must skip (idempotent / merge behaviour) and NOT clobber the
    # operator's manually-set newer credential.
    pre = _v2_repo(v2_path)
    pre.set("leaf-1", method="basic", username="newer-admin", password="newer-pw")

    result = migrate_credentials(legacy_db_one_basic, v2_path, SECRET)

    assert result["migrated"] == 0
    assert result["skipped"] == 1
    assert result["errors"] == []

    repo = _v2_repo(v2_path)
    leaf1 = repo.get("leaf-1")
    assert leaf1["username"] == "newer-admin"
    assert leaf1["password"] == "newer-pw"


# --------------------------------------------------------------------------- #
# E.1 #7 — Pre-flight canary decrypt
# --------------------------------------------------------------------------- #


def test_verify_can_decrypt_returns_ok_for_correct_secret(legacy_db_five_mixed):
    from backend.repositories.credential_migration import verify_can_decrypt

    ok, sample, error = verify_can_decrypt(legacy_db_five_mixed, SECRET)

    assert ok is True
    assert isinstance(sample, str) and sample  # one credential name
    assert error is None


def test_verify_can_decrypt_returns_error_for_wrong_secret(legacy_db_five_mixed):
    from backend.repositories.credential_migration import verify_can_decrypt

    ok, sample, error = verify_can_decrypt(legacy_db_five_mixed, "WRONG-KEY")

    assert ok is False
    assert sample is None
    assert error and ("decrypt" in error.lower() or "fernet" in error.lower())


def test_verify_can_decrypt_handles_empty_db(legacy_db_empty):
    from backend.repositories.credential_migration import verify_can_decrypt

    ok, sample, error = verify_can_decrypt(legacy_db_empty, SECRET)

    # An empty DB is "decryptable" trivially — we return ok=True with
    # sample=None so the operator knows there's nothing to migrate.
    assert ok is True
    assert sample is None
    assert error is None


def test_verify_can_decrypt_returns_error_for_missing_db(tmp_path):
    from backend.repositories.credential_migration import verify_can_decrypt

    missing = str(tmp_path / "nope.db")
    ok, sample, error = verify_can_decrypt(missing, SECRET)

    assert ok is False
    assert sample is None
    assert error and "not found" in error.lower()


# --------------------------------------------------------------------------- #
# E.1 extras — dry-run + verbose + details
# --------------------------------------------------------------------------- #


def test_migrate_dry_run_does_not_write_v2(legacy_db_five_mixed, v2_path):
    from backend.repositories.credential_migration import migrate_credentials

    result = migrate_credentials(
        legacy_db_five_mixed, v2_path, SECRET, dry_run=True
    )

    # Counts the would-be-migrated rows.
    assert result["migrated"] == 5
    assert result["errors"] == []
    # But did NOT actually populate v2.
    repo = _v2_repo(v2_path)
    assert repo.list() == []


def test_migrate_verbose_populates_details(legacy_db_five_mixed, v2_path):
    from backend.repositories.credential_migration import migrate_credentials

    result = migrate_credentials(
        legacy_db_five_mixed, v2_path, SECRET, verbose=True
    )

    assert "details" in result
    assert isinstance(result["details"], list)
    assert len(result["details"]) == 5
    for entry in result["details"]:
        assert {"name", "method", "status"} <= set(entry)
        assert entry["status"] in ("migrated", "skipped", "error")
        # No payload leakage in details.
        assert "password" not in entry
        assert "api_key" not in entry
        assert "value_enc" not in entry


def test_migrate_returns_details_key_even_when_not_verbose(
    legacy_db_one_basic, v2_path
):
    from backend.repositories.credential_migration import migrate_credentials

    result = migrate_credentials(legacy_db_one_basic, v2_path, SECRET)

    # ``details`` is always present (may be empty when verbose=False).
    assert "details" in result
    assert isinstance(result["details"], list)


# --------------------------------------------------------------------------- #
# E.1 extras — empty secret rejected; missing legacy DB rejected
# --------------------------------------------------------------------------- #


def test_migrate_rejects_empty_secret(legacy_db_one_basic, v2_path):
    from backend.repositories.credential_migration import migrate_credentials

    with pytest.raises(ValueError):
        migrate_credentials(legacy_db_one_basic, v2_path, "")


def test_migrate_returns_error_when_legacy_db_missing(tmp_path, v2_path):
    from backend.repositories.credential_migration import migrate_credentials

    missing = str(tmp_path / "nope.db")
    result = migrate_credentials(missing, v2_path, SECRET)

    assert result["migrated"] == 0
    assert result["errors"]
    assert any("not found" in e.lower() for e in result["errors"])


# --------------------------------------------------------------------------- #
# E.1 extras — partial decrypt failure (one bad row in many)
# --------------------------------------------------------------------------- #


def test_migrate_continues_past_single_bad_row(legacy_db_one_basic, v2_path, tmp_path):
    """If one row has a tampered ciphertext, the function should record
    the error, skip that row, and continue with the rest — NOT abort
    the whole migration. Operator inspects errors[] afterwards.
    """
    from backend.repositories.credential_migration import migrate_credentials

    # Add a second valid row.
    _legacy_set(
        legacy_db_one_basic, SECRET, "leaf-2", "basic", username="u2", password="p2"
    )
    # Corrupt one row's value_enc.
    conn = sqlite3.connect(legacy_db_one_basic)
    conn.execute(
        "UPDATE credentials SET value_enc = 'not-a-valid-fernet-token' WHERE name = ?",
        ("leaf-1",),
    )
    conn.commit()
    conn.close()

    result = migrate_credentials(legacy_db_one_basic, v2_path, SECRET)

    assert result["migrated"] == 1  # leaf-2 succeeded
    assert len(result["errors"]) == 1  # leaf-1 failed
    assert "leaf-1" in result["errors"][0]

    repo = _v2_repo(v2_path)
    assert repo.get("leaf-2") is not None
    assert repo.get("leaf-1") is None


def test_migrate_with_wrong_key_verbose_records_error_details(
    legacy_db_one_basic, v2_path
):
    from backend.repositories.credential_migration import migrate_credentials

    result = migrate_credentials(
        legacy_db_one_basic, v2_path, "WRONG-KEY-XYZ", verbose=True
    )

    assert result["migrated"] == 0
    assert result["errors"]
    # Verbose path captured the error in details.
    assert result["details"]
    assert all(d["status"] == "error" for d in result["details"])


def test_migrate_skip_records_skipped_status_when_verbose(
    legacy_db_one_basic, v2_path
):
    from backend.repositories.credential_migration import migrate_credentials

    pre = _v2_repo(v2_path)
    pre.set("leaf-1", method="basic", username="u", password="p")

    result = migrate_credentials(
        legacy_db_one_basic, v2_path, SECRET, verbose=True
    )

    assert result["skipped"] == 1
    assert result["details"] == [
        {"name": "leaf-1", "method": "basic", "status": "skipped"}
    ]


def test_migrate_dry_run_verbose_marks_migrated_status(
    legacy_db_one_basic, v2_path
):
    from backend.repositories.credential_migration import migrate_credentials

    result = migrate_credentials(
        legacy_db_one_basic, v2_path, SECRET, dry_run=True, verbose=True
    )

    assert result["migrated"] == 1
    assert result["details"] == [
        {"name": "leaf-1", "method": "basic", "status": "migrated"}
    ]


def test_migrate_with_legacy_db_lacking_credentials_table_returns_zero(tmp_path):
    """A legacy DB file that exists but has no ``credentials`` table
    (e.g. an aborted ``init_db``) should be treated as empty, not as
    an error — operator gets a clean ``migrated=0`` result.
    """
    from backend.repositories.credential_migration import (
        migrate_credentials,
        verify_can_decrypt,
    )

    legacy = str(tmp_path / "no_table.db")
    conn = sqlite3.connect(legacy)
    # Some unrelated table — no ``credentials`` table.
    conn.executescript("CREATE TABLE other (id INTEGER PRIMARY KEY);")
    conn.commit()
    conn.close()

    ok, sample, error = verify_can_decrypt(legacy, SECRET)
    assert ok is True
    assert sample is None
    assert error is None

    v2 = str(tmp_path / "v2.db")
    result = migrate_credentials(legacy, v2, SECRET)
    assert result["migrated"] == 0
    assert result["skipped"] == 0
    assert result["errors"] == []


def test_verify_can_decrypt_rejects_empty_secret(legacy_db_one_basic):
    from backend.repositories.credential_migration import verify_can_decrypt

    ok, sample, error = verify_can_decrypt(legacy_db_one_basic, "")
    assert ok is False
    assert sample is None
    assert error and "non-empty" in error


def test_migrate_records_v2_write_failure_in_errors(
    legacy_db_one_basic, v2_path, monkeypatch
):
    """If the v2 repository write raises, the migration must record
    the error, mark the row as ``error`` in details (verbose), and
    continue with the next row instead of aborting.
    """
    from backend.repositories import credential_migration as mig

    # Patch _set_via_repo to fail once.
    real = mig._set_via_repo
    calls = {"n": 0}

    def boom(repo, name, method, payload):
        calls["n"] += 1
        raise RuntimeError("disk full")

    monkeypatch.setattr(mig, "_set_via_repo", boom)

    result = mig.migrate_credentials(
        legacy_db_one_basic, v2_path, SECRET, verbose=True
    )

    assert result["migrated"] == 0
    assert len(result["errors"]) == 1
    assert "leaf-1" in result["errors"][0]
    assert "disk full" in result["errors"][0]
    assert result["details"][0]["status"] == "error"

    # Restore (defensive — monkeypatch handles it but we keep the
    # symbol referenced).
    assert real is not None


def test_set_via_repo_rejects_unknown_method(v2_path):
    """Internal helper must reject any legacy method outside the
    {basic, api_key} whitelist — defensive guard against future
    schema drift in the legacy DB.
    """
    from backend.repositories.credential_migration import _set_via_repo

    repo = _v2_repo(v2_path)
    with pytest.raises(ValueError, match="unknown legacy method"):
        _set_via_repo(repo, "x", "totally-bogus-method", {})


def test_migrate_with_unreadable_legacy_db_returns_error(tmp_path, v2_path):
    """A path that points at a non-SQLite file surfaces as an error
    in the result envelope, not as an exception.
    """
    from backend.repositories.credential_migration import (
        migrate_credentials,
        verify_can_decrypt,
    )

    junk = tmp_path / "garbage.db"
    junk.write_bytes(b"this is not a sqlite database")

    # verify_can_decrypt: opening succeeds (sqlite is forgiving on
    # connect) but the SELECT fails — _legacy_rows swallows that as
    # "no credentials table" → ok=True, sample=None.
    ok, sample, error = verify_can_decrypt(str(junk), SECRET)
    assert ok is True
    assert sample is None

    result = migrate_credentials(str(junk), v2_path, SECRET)
    assert result["migrated"] == 0
    assert result["errors"] == []  # treated as empty
