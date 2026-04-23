"""C-1 / H-4 — ``backend.credential_store.get_credential`` v2 fall-through.

Audit (Python review C-1 / Security audit H-4): writes through the new
``CredentialService`` land in ``credentials_v2.db``, but legacy
consumers (5 blueprints + ``backend/runners/runner.py`` +
``find_leaf`` + ``nat_lookup``) still resolve credentials via
``backend.credential_store.get_credential``. Without a fall-through,
a credential created via the API is unreadable by every device-exec
route on a fresh install — silent breakage that surfaces only when an
operator tries to push config.

The fix wires ``get_credential`` to consult the v2 store
(``CredentialRepository`` + ``EncryptionService``) when the legacy
table has no row. Failures are swallowed (returns ``None``) so the
legacy path stays best-effort and a corrupt v2 DB cannot crash the
device-exec routes.

This module pins:
  * basic credentials roundtrip via the fall-through
  * api_key credentials roundtrip via the fall-through
  * unknown names return ``None`` (never raise)
  * a corrupt v2 DB returns ``None`` (best-effort, never raise)
"""
from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.security]

# Anything ≥ 32 bytes works for the EncryptionService key derivation.
_SECRET = "credential-v2-fallthrough-test-secret-x" * 2


def _build_v2_repo(db_path: str):
    """Construct a CredentialRepository + EncryptionService against ``db_path``."""
    from backend.repositories.credential_repository import CredentialRepository
    from backend.security.encryption import EncryptionService

    enc = EncryptionService.from_secret(_SECRET)
    repo = CredentialRepository(db_path, enc)
    repo.create_schema()
    return repo


def _patch_v2_path(monkeypatch, db_path: str) -> None:
    """Force ``credential_store._v2_db_path`` to return our temp DB."""
    import backend.credential_store as cs

    monkeypatch.setattr(cs, "_v2_db_path", lambda: db_path)


def _isolate_legacy_db(monkeypatch, tmp_path) -> str:
    """Point the *legacy* DB at an empty temp file so the fall-through fires."""
    import backend.credential_store as cs

    legacy_db = str(tmp_path / "credentials_legacy.db")
    monkeypatch.setattr(cs, "_db_path", lambda: legacy_db)
    cs.init_db(_SECRET)  # creates an empty schema
    return legacy_db


def test_get_credential_falls_through_to_v2_for_basic(
    monkeypatch, tmp_path
) -> None:
    """A basic credential written to v2 only must be readable via the legacy API."""
    v2_db = str(tmp_path / "credentials_v2.db")
    repo = _build_v2_repo(v2_db)
    repo.set("device-cred", method="basic", username="alice", password="hunter2")

    _isolate_legacy_db(monkeypatch, tmp_path)
    _patch_v2_path(monkeypatch, v2_db)

    import backend.credential_store as cs

    payload = cs.get_credential("device-cred", _SECRET)
    assert payload is not None, (
        "credential created via CredentialRepository must be reachable "
        "through credential_store.get_credential's v2 fall-through"
    )
    assert payload.get("name") == "device-cred"
    assert payload.get("method") == "basic"
    assert payload.get("username") == "alice"
    assert payload.get("password") == "hunter2"


def test_get_credential_falls_through_to_v2_for_api_key(
    monkeypatch, tmp_path
) -> None:
    """An api_key credential written to v2 only must be readable too."""
    v2_db = str(tmp_path / "credentials_v2.db")
    repo = _build_v2_repo(v2_db)
    repo.set("api-only-cred", method="api_key", api_key="ABCDEF1234567890")

    _isolate_legacy_db(monkeypatch, tmp_path)
    _patch_v2_path(monkeypatch, v2_db)

    import backend.credential_store as cs

    payload = cs.get_credential("api-only-cred", _SECRET)
    assert payload is not None
    assert payload.get("method") == "api_key"
    assert payload.get("api_key") == "ABCDEF1234567890"


def test_get_credential_unknown_name_returns_none(monkeypatch, tmp_path) -> None:
    """Names absent from BOTH stores must return ``None`` (never raise)."""
    v2_db = str(tmp_path / "credentials_v2.db")
    _build_v2_repo(v2_db)  # empty v2

    _isolate_legacy_db(monkeypatch, tmp_path)
    _patch_v2_path(monkeypatch, v2_db)

    import backend.credential_store as cs

    assert cs.get_credential("does-not-exist", _SECRET) is None


def test_get_credential_corrupt_v2_db_returns_none(monkeypatch, tmp_path) -> None:
    """A garbage v2 DB must NOT crash device-exec routes — silent ``None``.

    Replaces the v2 DB with random bytes (not a valid SQLite file).
    The fall-through swallows the exception and returns ``None`` so
    the calling route still produces a clean "no credential" error
    instead of a 500.
    """
    v2_db = str(tmp_path / "credentials_v2.db")
    # Write garbage that isn't a SQLite file. The file MUST exist (the
    # fall-through short-circuits when the path is missing) but be
    # corrupt enough that opening it raises.
    with open(v2_db, "wb") as fh:
        fh.write(b"\x00\x01\x02not a sqlite file at all" * 32)

    _isolate_legacy_db(monkeypatch, tmp_path)
    _patch_v2_path(monkeypatch, v2_db)

    import backend.credential_store as cs

    # Must not raise; must return None.
    result = cs.get_credential("anything", _SECRET)
    assert result is None, (
        "corrupt v2 DB must produce a silent None (best-effort), "
        f"got {result!r}"
    )


def test_get_credential_missing_v2_db_returns_none(monkeypatch, tmp_path) -> None:
    """When the v2 DB file does not exist, fall-through is a no-op."""
    missing_path = str(tmp_path / "never-created-credentials_v2.db")
    assert not os.path.exists(missing_path)

    _isolate_legacy_db(monkeypatch, tmp_path)
    _patch_v2_path(monkeypatch, missing_path)

    import backend.credential_store as cs

    assert cs.get_credential("anything", _SECRET) is None


def test_legacy_db_takes_precedence_over_v2(monkeypatch, tmp_path) -> None:
    """If the legacy DB has the row, the v2 store must NOT be consulted.

    Pins the contract that the fall-through is a *fall-through*, not a
    blind override — operators with credentials still in the legacy
    store keep using them until a migration sweep runs.
    """
    # 1. Seed the legacy DB with a basic credential.
    _isolate_legacy_db(monkeypatch, tmp_path)
    import backend.credential_store as cs

    cs.set_credential(
        "shared-name",
        "basic",
        _SECRET,
        username="legacy-user",
        password="legacy-pass",
    )

    # 2. Seed the v2 DB with a different credential under the same name.
    v2_db = str(tmp_path / "credentials_v2.db")
    repo = _build_v2_repo(v2_db)
    repo.set("shared-name", method="basic", username="v2-user", password="v2-pass")
    _patch_v2_path(monkeypatch, v2_db)

    payload = cs.get_credential("shared-name", _SECRET)
    assert payload is not None
    assert payload["username"] == "legacy-user", (
        "legacy DB must win when the row exists in both stores; "
        f"got {payload!r}"
    )
