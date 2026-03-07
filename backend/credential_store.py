"""
Credential store: name -> method (api_key | basic) + encrypted payload.
No remote vault; all credentials stored locally (encrypted SQLite).
"""
import os
import json
import sqlite3
import hashlib
import base64
from typing import Optional

try:
    from cryptography.fernet import Fernet
    _HAS_FERNET = True
except ImportError:
    _HAS_FERNET = False


def _db_path():
    base = os.path.dirname(os.path.abspath(__file__))
    instance = os.path.join(base, "instance")
    os.makedirs(instance, exist_ok=True)
    return os.path.join(instance, "credentials.db")


def _fernet(secret_key: str):
    if not _HAS_FERNET:
        return None
    key = base64.urlsafe_b64encode(
        hashlib.sha256(secret_key.encode() if isinstance(secret_key, str) else secret_key).digest()
    )
    return Fernet(key)


def init_db(secret_key: str) -> None:
    conn = sqlite3.connect(_db_path())
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


def _encrypt(fernet_obj, data: dict) -> str:
    if not fernet_obj:
        return base64.b64encode(json.dumps(data).encode()).decode()
    return fernet_obj.encrypt(json.dumps(data).encode()).decode()


def _decrypt(fernet_obj, enc: str) -> dict:
    if not fernet_obj:
        return json.loads(base64.b64decode(enc.encode()).decode())
    return json.loads(fernet_obj.decrypt(enc.encode()).decode())


def list_credentials(secret_key: str) -> list[dict]:
    """Return list of {name, method} (no secrets)."""
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT name, method, updated_at FROM credentials ORDER BY name").fetchall()
    conn.close()
    return [{"name": r["name"], "method": r["method"], "updated_at": r["updated_at"]} for r in rows]


def get_credential(name: str, secret_key: str) -> Optional[dict]:
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
    api_key: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
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
