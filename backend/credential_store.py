"""
Credential store: name -> method (api_key | basic) + encrypted payload.
No remote vault; all credentials stored locally (encrypted SQLite).

Audit C-3 hardening: ``cryptography`` is a hard requirement. Previously the
module fell back to base64 (i.e. plaintext-equivalent) storage when the
``cryptography`` import failed, which meant a corrupt venv silently
downgraded the credential DB to no-encryption. The import is now
unconditional and ``ImportError`` propagates at module import time.

DEPRECATED (wave-3 Phase 6) — see ``docs/refactor/credential_store_migration.md``.
This module's per-call SHA-256-derived Fernet key is being replaced by
``backend.security.encryption.EncryptionService`` (PBKDF2 ≥ 600k +
AES-128-CBC + HMAC) wired via ``backend.services.credential_service.CredentialService``
and ``backend.repositories.credential_repository.CredentialRepository``.
The new store lives in ``instance/credentials_v2.db``.

The legacy SHA-256 path remains importable for one release cycle so that
existing callers (5 blueprint sites + ``backend/runners/runner.py`` +
``backend/find_leaf.py`` + ``backend/nat_lookup.py``) keep working while
the migration sweep lands one PR at a time.
"""
import base64
import contextlib
import hashlib
import json
import os
import sqlite3
import warnings

from cryptography.fernet import Fernet

# Audit deprecation marker — pinned by tests/test_security_legacy_credstore_deprecation.py.
__deprecated__ = True

warnings.warn(
    "backend.credential_store is deprecated; use "
    "backend.services.credential_service.CredentialService "
    "(PBKDF2 + AES-CBC+HMAC, instance/credentials_v2.db) instead. "
    "See docs/refactor/credential_store_migration.md.",
    DeprecationWarning,
    stacklevel=2,
)


def _db_path():
    base = os.path.dirname(os.path.abspath(__file__))
    instance = os.path.join(base, "instance")
    os.makedirs(instance, exist_ok=True)
    db = os.path.join(instance, "credentials.db")
    # Audit M-6: enforce 0o600 on the DB file as soon as we touch it so a
    # default-umask install can't leave the credential blob world-readable.
    if os.name == "posix" and os.path.exists(db):
        # chmod failures are non-fatal (e.g. read-only FS in CI sandbox).
        with contextlib.suppress(OSError):  # pragma: no cover
            os.chmod(db, 0o600)
    return db


def _fernet(secret_key: str) -> Fernet:
    """Derive a Fernet key from the application secret.

    Note: this still uses a single SHA-256 (no PBKDF2) for backwards
    compatibility with credentials encrypted by earlier Pergen versions.
    The new ``backend.security.encryption.EncryptionService`` (used by
    ``CredentialService``) uses PBKDF2 600k. The legacy module is
    retained only for the read paths during the migration window.
    """
    key = base64.urlsafe_b64encode(
        hashlib.sha256(secret_key.encode() if isinstance(secret_key, str) else secret_key).digest()
    )
    return Fernet(key)


def init_db(secret_key: str) -> None:
    db = _db_path()
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS credentials (
            name TEXT PRIMARY KEY,
            method TEXT NOT NULL,
            value_enc TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()
    # Audit M-6: lock down file mode after schema creation as well.
    if os.name == "posix":
        with contextlib.suppress(OSError):  # pragma: no cover
            os.chmod(db, 0o600)


def _encrypt(fernet_obj: Fernet, data: dict) -> str:
    return fernet_obj.encrypt(json.dumps(data).encode()).decode()


def _decrypt(fernet_obj: Fernet, enc: str) -> dict:
    return json.loads(fernet_obj.decrypt(enc.encode()).decode())


def list_credentials(secret_key: str) -> list[dict]:
    """Return list of {name, method} (no secrets)."""
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT name, method, updated_at FROM credentials ORDER BY name").fetchall()
    conn.close()
    return [{"name": r["name"], "method": r["method"], "updated_at": r["updated_at"]} for r in rows]


def get_credential(name: str, secret_key: str) -> dict | None:
    """
    Return credential payload: for basic -> {username, password}, for api_key -> {api_key}.
    Returns None if not found.
    """
    conn = sqlite3.connect(_db_path())
    row = conn.execute(
        "SELECT name, method, value_enc FROM credentials WHERE name = ?", (name.strip(),)
    ).fetchone()
    conn.close()
    if not row:
        return None
    fernet = _fernet(secret_key)
    payload = _decrypt(fernet, row[2])
    return {"name": row[0], "method": row[1], **payload}


def set_credential(
    name: str,
    method: str,
    secret_key: str,
    *,
    api_key: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> None:
    """Save credential. method is 'api_key' or 'basic'. For api_key pass api_key=; for basic pass username= and password=."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Credential name is required")
    if method == "api_key":
        data = {"api_key": (api_key or "").strip()}
    elif method == "basic":
        data = {"username": (username or "").strip(), "password": (password or "").strip()}
    else:
        raise ValueError("method must be 'api_key' or 'basic'")
    fernet = _fernet(secret_key)
    enc = _encrypt(fernet, data)
    conn = sqlite3.connect(_db_path())
    conn.execute(
        """INSERT INTO credentials (name, method, value_enc, updated_at)
           VALUES (?, ?, ?, datetime('now'))
           ON CONFLICT(name) DO UPDATE SET method = ?, value_enc = ?, updated_at = datetime('now')""",
        (name, method, enc, method, enc),
    )
    conn.commit()
    conn.close()


def delete_credential(name: str) -> bool:
    """Remove credential by name. Returns True if deleted."""
    conn = sqlite3.connect(_db_path())
    cur = conn.execute("DELETE FROM credentials WHERE name = ?", (name.strip(),))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted
