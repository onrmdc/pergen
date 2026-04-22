"""
TDD tests for ``backend.repositories.credential_repository.CredentialRepository``.

The repository owns Pergen's encrypted credential SQLite store and is the
OOD replacement for the module-level helpers in ``backend/credential_store.py``.

Contract
--------
* ``CredentialRepository(db_path, encryption)`` — explicit injection of
  the SQLite path and an ``EncryptionService`` instance (or compatible).
* ``repo.create_schema()`` is idempotent (safe to call repeatedly).
* ``repo.set("name", method="basic", username=..., password=...)``
* ``repo.set("name", method="api_key", api_key=...)``
* ``repo.list()`` returns ``[{"name", "method", "updated_at"}]`` — never
  the secret payload.
* ``repo.get("name")`` returns ``{"name", "method", **payload}`` or None.
* ``repo.delete("name")`` returns True/False.
* Method values other than ``"basic"`` / ``"api_key"`` raise ``ValueError``.
* Empty / whitespace name raises ``ValueError``.
* Stored payload is encrypted on disk (raw bytes never contain the
  cleartext password).
"""
from __future__ import annotations

import sqlite3

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture()
def repo(tmp_path):
    from backend.repositories.credential_repository import CredentialRepository
    from backend.security.encryption import EncryptionService

    enc = EncryptionService.from_secret("test-secret-key")
    r = CredentialRepository(db_path=str(tmp_path / "creds.db"), encryption=enc)
    r.create_schema()
    return r


def test_create_schema_is_idempotent(repo):
    repo.create_schema()
    repo.create_schema()


def test_set_and_get_basic_credential(repo):
    repo.set("device-leaf-1", method="basic", username="admin", password="hunter2")
    got = repo.get("device-leaf-1")
    assert got["name"] == "device-leaf-1"
    assert got["method"] == "basic"
    assert got["username"] == "admin"
    assert got["password"] == "hunter2"


def test_set_and_get_api_key_credential(repo):
    repo.set("snmp-token", method="api_key", api_key="super-secret-token")
    got = repo.get("snmp-token")
    assert got["method"] == "api_key"
    assert got["api_key"] == "super-secret-token"


def test_get_returns_none_for_missing(repo):
    assert repo.get("does-not-exist") is None


def test_list_excludes_secret_payload(repo):
    repo.set("a", method="basic", username="u", password="p")
    repo.set("b", method="api_key", api_key="t")
    rows = repo.list()
    names = sorted(r["name"] for r in rows)
    assert names == ["a", "b"]
    for r in rows:
        assert "password" not in r
        assert "api_key" not in r
        assert "username" not in r
        assert r["updated_at"]


def test_set_overwrites_existing(repo):
    repo.set("dup", method="basic", username="u1", password="p1")
    repo.set("dup", method="basic", username="u2", password="p2")
    got = repo.get("dup")
    assert got["username"] == "u2"
    assert got["password"] == "p2"


def test_delete_returns_true_when_existed(repo):
    repo.set("kill-me", method="basic", username="u", password="p")
    assert repo.delete("kill-me") is True
    assert repo.get("kill-me") is None


def test_delete_returns_false_when_missing(repo):
    assert repo.delete("ghost") is False


def test_set_rejects_unknown_method(repo):
    with pytest.raises(ValueError):
        repo.set("x", method="bogus", username="u", password="p")


def test_set_rejects_empty_name(repo):
    with pytest.raises(ValueError):
        repo.set("", method="basic", username="u", password="p")
    with pytest.raises(ValueError):
        repo.set("   ", method="basic", username="u", password="p")


def test_payload_is_encrypted_on_disk(tmp_path):
    """Open the underlying SQLite file directly and verify the cleartext
    password is not present in any row's ``value_enc`` column."""
    from backend.repositories.credential_repository import CredentialRepository
    from backend.security.encryption import EncryptionService

    db_path = str(tmp_path / "encrypted.db")
    enc = EncryptionService.from_secret("disk-secret")
    repo = CredentialRepository(db_path=db_path, encryption=enc)
    repo.create_schema()
    repo.set("d1", method="basic", username="root", password="VERY-SECRET-PW-XYZ")

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT value_enc FROM credentials").fetchall()
    conn.close()
    assert rows
    for (enc_blob,) in rows:
        assert "VERY-SECRET-PW-XYZ" not in enc_blob
        assert "root" not in enc_blob


def test_name_is_stripped(repo):
    repo.set("  spaced  ", method="basic", username="u", password="p")
    assert repo.get("spaced") is not None
    assert repo.get("  spaced  ") is not None  # get also strips
