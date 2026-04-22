"""
``CredentialRepository`` — encrypted SQLite store for device credentials.

Responsibilities
----------------
* Owns a single SQLite file (``credentials.db``) and a single
  ``EncryptionService`` instance.
* Persists credentials as encrypted blobs — the cleartext password /
  api key never lands in the DB column.
* Exposes a tight ``list / get / set / delete`` interface that matches
  the legacy ``backend.credential_store`` module so phase-9 routes can
  swap module-level helpers for ``CredentialRepository`` calls without
  any signature changes.

Security
--------
* Every payload is encrypted with the injected ``EncryptionService``
  (authenticated; tampering raises ``EncryptionError`` on read).
* Names are stripped and validated (non-empty after strip).
* ``method`` is restricted to the ``{"basic", "api_key"}`` whitelist —
  unknown values raise ``ValueError`` rather than being persisted.
* No credential value ever appears in the ``list()`` result.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from typing import Any

from backend.security.encryption import EncryptionService

_log = logging.getLogger("app.repository.credential")


class CredentialRepository:
    """Persistence façade for the encrypted credential SQLite store."""

    _ALLOWED_METHODS = ("basic", "api_key")

    def __init__(self, db_path: str, encryption: EncryptionService) -> None:
        """
        Inputs
        ------
        db_path : filesystem path to the SQLite file.  Parent dir is
            created lazily on first write.
        encryption : authenticated symmetric encryption service used
            to wrap the credential payload.

        Outputs
        -------
        ``CredentialRepository`` instance.  ``create_schema`` must be
        invoked once before reads/writes (idempotent).

        Security
        --------
        ``encryption`` is held by reference; callers are responsible for
        deriving it from a non-default ``SECRET_KEY``.
        """
        self._db_path = db_path
        self._enc = encryption
        self._lock = threading.Lock()
        # Phase 13: persistent in-memory connection.  ``sqlite3.connect(":memory:")``
        # creates a brand-new database per call, so without this guard
        # ``create_schema()`` would write a table to a connection that is
        # immediately closed and every subsequent ``get/set/list`` would hit
        # a fresh empty database.  Tests with ``CREDENTIAL_DB_PATH=":memory:"``
        # (TestingConfig default) used to silently break the credential
        # service; now they share a single connection for the lifetime of
        # the repository instance.
        self._mem_conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------ #
    # schema
    # ------------------------------------------------------------------ #
    def create_schema(self) -> None:
        """Create the ``credentials`` table if it does not exist.

        Audit H8: also tightens filesystem permissions on the DB file
        and enables ``PRAGMA secure_delete`` so deleted credentials
        do not leave plaintext-encrypted-blob fragments on disk.
        """
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA secure_delete = ON;
                CREATE TABLE IF NOT EXISTS credentials (
                    name TEXT PRIMARY KEY,
                    method TEXT NOT NULL,
                    value_enc TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()
        # Enforce 0o600 on the DB file (POSIX only — Windows ignores chmod).
        if self._db_path != ":memory:" and os.name == "posix":
            try:
                os.chmod(self._db_path, 0o600)
            except OSError as exc:  # pragma: no cover — best effort
                _log.warning(
                    "credential DB chmod 0o600 failed for %s: %s",
                    self._db_path,
                    exc,
                )

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    def list(self) -> list[dict[str, Any]]:
        """Return ``[{name, method, updated_at}, …]`` — no payloads."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT name, method, updated_at FROM credentials ORDER BY name"
            ).fetchall()
        return [
            {"name": r["name"], "method": r["method"], "updated_at": r["updated_at"]}
            for r in rows
        ]

    def get(self, name: str) -> dict[str, Any] | None:
        """Return ``{name, method, **payload}`` or None if not found."""
        key = (name or "").strip()
        if not key:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name, method, value_enc FROM credentials WHERE name = ?",
                (key,),
            ).fetchone()
        if not row:
            return None
        payload = self._decrypt(row[2])
        return {"name": row[0], "method": row[1], **payload}

    def set(
        self,
        name: str,
        *,
        method: str,
        api_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """
        Insert or replace a credential.

        Security
        --------
        * ``method`` must be ``"basic"`` or ``"api_key"`` (else
          ``ValueError``).
        * ``name`` must be non-empty after strip (else ``ValueError``).
        * Payload is JSON-serialised then encrypted with the injected
          service before being persisted.
        """
        key = (name or "").strip()
        if not key:
            raise ValueError("Credential name is required")
        if method not in self._ALLOWED_METHODS:
            raise ValueError("method must be 'api_key' or 'basic'")

        if method == "api_key":
            data = {"api_key": (api_key or "").strip()}
        else:
            data = {
                "username": (username or "").strip(),
                "password": (password or "").strip(),
            }

        enc_blob = self._encrypt(data)
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO credentials (name, method, value_enc, updated_at)
                       VALUES (?, ?, ?, datetime('now'))
                       ON CONFLICT(name) DO UPDATE SET
                            method = excluded.method,
                            value_enc = excluded.value_enc,
                            updated_at = datetime('now')""",
                (key, method, enc_blob),
            )
            conn.commit()

    def delete(self, name: str) -> bool:
        """Remove credential by name.  Returns True iff a row was deleted."""
        key = (name or "").strip()
        if not key:
            return False
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM credentials WHERE name = ?", (key,))
            conn.commit()
            return cur.rowcount > 0

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _connect(self) -> sqlite3.Connection:
        """Return a SQLite connection.

        For file-backed databases the call returns a fresh connection per
        invocation (cheap, no file locking issues since SQLite uses
        process-local file locks).

        For ``:memory:`` (TestingConfig default) a single connection is
        cached on the instance and re-used for the lifetime of the
        repository — without this, every call would land on a brand-new
        empty in-memory database and ``create_schema()`` would have no
        effect on subsequent reads / writes.
        """
        if self._db_path == ":memory:":
            if self._mem_conn is None:
                self._mem_conn = sqlite3.connect(
                    ":memory:", check_same_thread=False
                )
            return self._mem_conn
        return sqlite3.connect(self._db_path)

    def _encrypt(self, data: dict[str, Any]) -> str:
        return self._enc.encrypt(json.dumps(data))

    def _decrypt(self, blob: str) -> dict[str, Any]:
        try:
            raw = self._enc.decrypt(blob)
        except Exception:
            _log.warning("credential decryption failed (tampered or wrong key)")
            raise
        return json.loads(raw)
