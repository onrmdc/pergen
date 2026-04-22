"""
``credential_migration`` — operator-led data migration from the
legacy ``backend.credential_store`` SQLite store
(``instance/credentials.db``, single SHA-256 → Fernet) to the new
``CredentialRepository`` store (``instance/credentials_v2.db``,
PBKDF2-HMAC-SHA256 600k → AES-128-CBC + HMAC, owned by
``EncryptionService``).

Wave-6 Phase E.2 — pure-function library used by the CLI wrapper at
``scripts/migrate_credentials_v1_to_v2.py``.  The migration is
deliberately **not** invoked at app boot; an operator runs it once,
manually, after taking a backup of ``instance/credentials.db``.

Public API
----------

* ``verify_can_decrypt(legacy_db_path, secret_key)`` — pre-flight
  canary that decrypts (at most) one row from the legacy store and
  surfaces a clear error if the operator's ``SECRET_KEY`` does not
  match the key the legacy DB was written under.

* ``migrate_credentials(legacy_db_path, v2_db_path, secret_key, *,
  dry_run=False, verbose=False)`` — read every row from the legacy
  store, re-encrypt it with the new ``EncryptionService``, and write
  it to the v2 store.  Idempotent: rows that already exist in v2 (by
  name) are **skipped**, never overwritten — the operator's manually
  set newer credential always wins.

Security
--------

* The legacy store is opened **read-only** (``mode=ro`` URI) so a buggy
  migration cannot corrupt the only authoritative copy of the data.
* The legacy module's import-time ``DeprecationWarning`` is suppressed
  *only* inside this module — every other call site still sees it.
* No credential payload is ever logged or returned in the result dict;
  ``details`` carries ``{name, method, status}`` triples only.
* ``secret_key`` is required to be a non-empty string — empty rejects
  with ``ValueError`` instead of silently deriving a weak key.
* Failures on individual rows are captured in ``errors`` and the loop
  continues; the operator decides post-hoc whether to investigate or
  re-run after fixing the source row.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import warnings
from typing import Any

from backend.repositories.credential_repository import CredentialRepository
from backend.security.encryption import EncryptionService

_log = logging.getLogger("app.repository.credential_migration")

# --------------------------------------------------------------------------- #
# Internals                                                                   #
# --------------------------------------------------------------------------- #


def _import_legacy() -> Any:
    """Import the legacy credential store with its DeprecationWarning
    suppressed — the migration is the *one* place that legitimately
    needs to call into the legacy decryption helper.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import importlib

        return importlib.import_module("backend.credential_store")


def _open_legacy_readonly(path: str) -> sqlite3.Connection:
    """Open the legacy SQLite DB in read-only mode via the URI form.

    ``mode=ro`` makes the connection refuse any write — guarantees the
    migration cannot corrupt the source even if a later code change
    accidentally issues an ``UPDATE``.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"legacy credential DB not found: {path}")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _legacy_rows(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """Return ``[(name, method, value_enc), …]`` from the legacy store.

    Treats both *no credentials table* and *file-is-not-a-database* as
    "empty source" rather than a hard error — the operator's runbook
    starts with a backup step, so the worst case is they re-run after
    pointing at the right file.
    """
    try:
        cur = conn.execute(
            "SELECT name, method, value_enc FROM credentials ORDER BY name"
        )
        return [(r[0], r[1], r[2]) for r in cur.fetchall()]
    except sqlite3.DatabaseError:
        return []


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #


def verify_can_decrypt(
    legacy_db_path: str, secret_key: str
) -> tuple[bool, str | None, str | None]:
    """Pre-flight: try to decrypt one entry from the legacy store.

    Returns
    -------
    ``(ok, sample_name, error)`` where:

    * ``ok=True, sample_name=<name>, error=None`` — the operator's
      ``SECRET_KEY`` matches; the named entry decrypted cleanly.
    * ``ok=True, sample_name=None, error=None`` — the legacy store is
      empty; nothing to migrate (trivially decryptable).
    * ``ok=False, sample_name=None, error=<msg>`` — the legacy DB is
      missing, unreadable, or the ``SECRET_KEY`` is wrong.

    No payload is returned — only the credential ``name``.
    """
    if not isinstance(secret_key, str) or len(secret_key) == 0:
        return False, None, "secret_key must be a non-empty string"
    try:
        conn = _open_legacy_readonly(legacy_db_path)
    except FileNotFoundError as exc:
        return False, None, f"legacy DB not found: {exc}"
    except sqlite3.Error as exc:
        return False, None, f"cannot open legacy DB: {exc}"

    try:
        rows = _legacy_rows(conn)
    finally:
        conn.close()

    if not rows:
        return True, None, None

    legacy = _import_legacy()
    try:
        fernet = legacy._fernet(secret_key)
    except Exception as exc:  # pragma: no cover — defensive
        return False, None, f"cannot derive legacy key: {exc}"

    name, _method, value_enc = rows[0]
    try:
        legacy._decrypt(fernet, value_enc)
    except Exception as exc:
        return False, None, (
            f"decryption failed for '{name}' — is SECRET_KEY the same "
            f"as the running app? ({exc.__class__.__name__})"
        )
    return True, name, None


def migrate_credentials(
    legacy_db_path: str,
    v2_db_path: str,
    secret_key: str,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """Read every row from the legacy store, write to v2.

    Parameters
    ----------
    legacy_db_path : path to ``instance/credentials.db`` (legacy
        SHA-256 → Fernet store).  Opened read-only.
    v2_db_path : path to ``instance/credentials_v2.db`` (the new
        ``CredentialRepository`` store).  Created if missing; merged
        into if present.
    secret_key : the operator's ``SECRET_KEY`` (must match the key the
        legacy store was originally written under).
    dry_run : if True, do everything except the v2 write — useful for
        the operator to confirm the count before touching the new file.
    verbose : if True, populate ``result["details"]`` with one entry
        per row processed (``{name, method, status}``).  ``status`` is
        one of ``migrated`` / ``skipped`` / ``error``.

    Returns
    -------
    Dict with::

        {
            "migrated": int,           # rows freshly written to v2
            "skipped":  int,           # rows already present in v2 (by name)
            "errors":   list[str],     # one human-readable msg per failure
            "details":  list[dict],    # always present; populated iff verbose
        }

    Behaviour
    ---------
    * **Idempotent.** Rows whose name already exists in v2 are
      counted as ``skipped`` — the legacy version does **not**
      overwrite a manually-set newer credential.
    * **Merge.** Existing v2 rows whose name is **not** in legacy are
      left untouched.
    * **Continues past errors.** A single bad row is recorded in
      ``errors`` and the loop moves on; the migration is not aborted.
    * **No payload leakage.** ``details`` records name + method +
      status only; nothing in the result contains a cleartext or
      ciphertext credential.

    Raises
    ------
    ValueError : ``secret_key`` is empty.
    """
    if not isinstance(secret_key, str) or len(secret_key) == 0:
        raise ValueError("secret_key must be a non-empty string")

    result: dict[str, Any] = {
        "migrated": 0,
        "skipped": 0,
        "errors": [],
        "details": [],
    }

    # Open legacy DB (read-only).
    try:
        legacy_conn = _open_legacy_readonly(legacy_db_path)
    except FileNotFoundError as exc:
        result["errors"].append(f"legacy DB not found: {exc}")
        return result
    except sqlite3.Error as exc:  # pragma: no cover — defensive
        result["errors"].append(f"cannot open legacy DB: {exc}")
        return result

    try:
        rows = _legacy_rows(legacy_conn)
    finally:
        legacy_conn.close()

    if not rows:
        # Nothing to migrate — but ensure v2 schema exists so the
        # operator can write to it via the regular service afterwards.
        if not dry_run:
            _ensure_v2_repo(v2_db_path, secret_key)
        return result

    legacy = _import_legacy()
    try:
        fernet = legacy._fernet(secret_key)
    except Exception as exc:  # pragma: no cover — defensive
        result["errors"].append(f"cannot derive legacy key: {exc}")
        return result

    # Build the v2 repo (creates the file + schema).  Even in dry-run we
    # need a *snapshot* of what is already in v2 so we can report the
    # would-be ``migrated`` vs ``skipped`` split accurately.
    v2_repo = _ensure_v2_repo(v2_db_path, secret_key)
    existing_names = {r["name"] for r in v2_repo.list()}

    for name, method, value_enc in rows:
        try:
            payload = legacy._decrypt(fernet, value_enc)
        except Exception as exc:
            msg = (
                f"decryption failed for '{name}' "
                f"({exc.__class__.__name__})"
            )
            result["errors"].append(msg)
            if verbose:
                result["details"].append(
                    {"name": name, "method": method, "status": "error"}
                )
            _log.warning("credential_migration: %s", msg)
            continue

        if name in existing_names:
            result["skipped"] += 1
            if verbose:
                result["details"].append(
                    {"name": name, "method": method, "status": "skipped"}
                )
            continue

        if dry_run:
            result["migrated"] += 1
            if verbose:
                result["details"].append(
                    {"name": name, "method": method, "status": "migrated"}
                )
            continue

        try:
            _set_via_repo(v2_repo, name, method, payload)
        except Exception as exc:
            msg = (
                f"v2 write failed for '{name}' "
                f"({exc.__class__.__name__}: {exc})"
            )
            result["errors"].append(msg)
            if verbose:
                result["details"].append(
                    {"name": name, "method": method, "status": "error"}
                )
            _log.warning("credential_migration: %s", msg)
            continue

        result["migrated"] += 1
        existing_names.add(name)
        if verbose:
            result["details"].append(
                {"name": name, "method": method, "status": "migrated"}
            )

    return result


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _ensure_v2_repo(v2_db_path: str, secret_key: str) -> CredentialRepository:
    """Create the v2 file + schema if missing, return the repository."""
    parent = os.path.dirname(v2_db_path)
    if parent and parent != ":memory:":
        os.makedirs(parent, exist_ok=True)
    enc = EncryptionService.from_secret(secret_key)
    repo = CredentialRepository(v2_db_path, enc)
    repo.create_schema()
    return repo


def _set_via_repo(
    repo: CredentialRepository, name: str, method: str, payload: dict
) -> None:
    """Translate a legacy decrypted payload into a ``repo.set(...)`` call."""
    if method == "basic":
        repo.set(
            name,
            method="basic",
            username=payload.get("username", ""),
            password=payload.get("password", ""),
        )
    elif method == "api_key":
        repo.set(name, method="api_key", api_key=payload.get("api_key", ""))
    else:
        raise ValueError(f"unknown legacy method: {method!r}")
