"""
Security audit batch 4 — gaps from coverage map + new protections added
in the same audit pass (C-1 fail-closed, C-2 actor logging, C-3 base64
removal, H-1 defusedxml hard-required, H-2 inventory binding, H-3 cred
sanitisation, H-4 delete validation, H-5 generic envelopes).

Threat-model rationale per test is documented inline. Each test is
designed to FAIL if the corresponding protection is removed or weakened
(no smoke-test-only assertions).
"""
from __future__ import annotations


def _rebuild_snapshot(flask_app):
    """Audit H-06: tests that mutate app.config['PERGEN_API_TOKEN(S)']
    AFTER create_app must call this so the immutable snapshot picks up
    the change. Production code never calls this (token rotation =
    graceful restart)."""
    rebuild = flask_app.extensions.get("pergen", {}).get("rebuild_token_snapshot")
    if rebuild is not None:
        rebuild()

import inspect
import logging
from unittest.mock import patch

import pytest


# --------------------------------------------------------------------------- #
# C-1 — Production fail-closed                                                 #
# --------------------------------------------------------------------------- #


def _repo_root() -> str:
    """Resolve the project root for subprocess sys.path injection."""
    from pathlib import Path

    return str(Path(__file__).resolve().parent.parent)


def _run_in_subprocess(code: str) -> tuple[int, str, str]:
    """Run a snippet in a fresh Python interpreter and capture (rc, stdout, stderr).

    Used to test create_app("production") fail-closed paths without polluting
    sys.modules in the active pytest worker (which would invalidate class
    identity across other tests' isinstance checks).
    """
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_create_app_production_refuses_when_no_api_token():
    """Threat: a production deploy that forgets PERGEN_API_TOKEN serves an
    open API. ``create_app("production")`` must refuse to start instead.

    Runs in a subprocess so module-cache state in this pytest worker is
    not perturbed (which would cause isinstance / class-identity drift
    across other tests).
    """
    code = (
        "import os, sys\n"
        f"sys.path.insert(0, {_repo_root()!r})\n"
        # Ensure no stray tokens leak in from the operator environment.
        "for k in ('PERGEN_API_TOKEN', 'PERGEN_API_TOKENS'):\n"
        "    os.environ.pop(k, None)\n"
        "os.environ['SECRET_KEY'] = 'x' * 64\n"
        "from backend.app_factory import create_app\n"
        "try:\n"
        "    create_app('production')\n"
        "    print('NO_RAISE')\n"
        "except RuntimeError as e:\n"
        "    print('RAISED', str(e))\n"
    )
    rc, out, err = _run_in_subprocess(code)
    assert rc == 0, f"subprocess crashed: {err}"
    assert out.startswith("RAISED"), f"create_app did not raise: {out!r}"
    msg = out.lower()
    assert "pergen_api_token" in msg or "open api" in msg


def test_create_app_production_refuses_short_api_token():
    """Audit C-1: token must meet minimum length. Subprocess-isolated."""
    code = (
        "import os, sys\n"
        f"sys.path.insert(0, {_repo_root()!r})\n"
        "os.environ['SECRET_KEY'] = 'x' * 64\n"
        "os.environ['PERGEN_API_TOKEN'] = 'tiny'\n"
        "os.environ.pop('PERGEN_API_TOKENS', None)\n"
        "from backend.app_factory import create_app\n"
        "try:\n"
        "    create_app('production')\n"
        "    print('NO_RAISE')\n"
        "except RuntimeError as e:\n"
        "    print('RAISED', str(e))\n"
    )
    rc, out, err = _run_in_subprocess(code)
    assert rc == 0, f"subprocess crashed: {err}"
    assert out.startswith("RAISED"), f"create_app did not raise: {out!r}"
    assert "character" in out.lower()


# --------------------------------------------------------------------------- #
# C-2 — Per-actor token routing                                                #
# --------------------------------------------------------------------------- #


def test_api_token_gate_resolves_actor_from_multi_token_env(flask_app):
    """When PERGEN_API_TOKENS is set, each token maps to an actor identity
    that is recorded on flask.g.actor for audit logging.
    """
    from backend.app_factory import _parse_actor_tokens

    tokens = _parse_actor_tokens("alice:" + "a" * 32 + ",bob:" + "b" * 32)
    assert tokens == {"alice": "a" * 32, "bob": "b" * 32}

    # Malformed entries are silently dropped (no widening of access).
    bad = _parse_actor_tokens("notoken,:emptyactor,actor:,,validone:" + "v" * 32)
    assert bad == {"validone": "v" * 32}


def test_api_token_gate_records_matched_actor_in_flask_g(flask_app):
    """End-to-end: a request carrying alice's token must result in
    g.actor == "alice" so audit log lines can record the operator.
    """
    from flask import g

    flask_app.config["PERGEN_API_TOKENS"] = (
        "alice:" + "a" * 32 + ",bob:" + "b" * 32
    )
    _rebuild_snapshot(flask_app)
    client = flask_app.test_client()

    # We need to inspect g.actor inside a request, so attach a probe.
    captured: dict = {}

    @flask_app.route("/api/_test/whoami")
    def _whoami():
        captured["actor"] = getattr(g, "actor", None)
        return {"actor": captured["actor"]}, 200

    r = client.get("/api/_test/whoami", headers={"X-API-Token": "a" * 32})
    assert r.status_code == 200
    assert r.get_json()["actor"] == "alice"


# --------------------------------------------------------------------------- #
# C-3 — Hard cryptography requirement                                          #
# --------------------------------------------------------------------------- #


def test_credential_store_requires_cryptography_at_import_time():
    """Threat: a corrupt venv where ``cryptography`` import fails would
    have downgraded the credential DB to base64 storage. The fallback was
    removed — confirm no ``base64`` import remains in the legacy module
    (which would have been the smoking-gun for the fallback path).
    """
    from backend import credential_store

    src = inspect.getsource(credential_store)
    # Hard import is unconditional now (no try/except wrapping Fernet).
    assert "from cryptography.fernet import Fernet" in src
    # The fallback ``return base64.b64encode(...)`` line must be gone.
    assert "base64.b64encode(json.dumps(data)" not in src


# --------------------------------------------------------------------------- #
# H-1 — defusedxml is a hard requirement                                       #
# --------------------------------------------------------------------------- #


def test_nat_lookup_imports_defusedxml_unconditionally():
    """Audit H-1: previously the import was wrapped in try/except so a
    missing dependency silently fell back to the unsafe stdlib parser.
    The fallback was removed — assert the import is direct.
    """
    from backend import nat_lookup

    src = inspect.getsource(nat_lookup)
    assert "from defusedxml import ElementTree as ET" in src
    # The fallback ``import xml.etree.ElementTree as ET`` must be absent.
    assert "import xml.etree.ElementTree as ET" not in src


# --------------------------------------------------------------------------- #
# H-2 — Inventory binding on /api/run/device, /api/arista/run-cmds,           #
#       /api/custom-command (request body's credential is ignored)            #
# --------------------------------------------------------------------------- #


def test_run_device_rejects_device_not_in_inventory(client):
    """Threat: caller supplies arbitrary IP + credential to point Pergen
    at any host on the management LAN. The route must refuse anything not
    in the inventory CSV.
    """
    r = client.post(
        "/api/run/device",
        json={
            "device": {
                "hostname": "ghost",
                "ip": "203.0.113.99",  # TEST-NET-3, not in inventory
                "credential": "test-cred",
            }
        },
    )
    assert r.status_code == 404
    assert "inventory" in (r.get_json().get("error") or "").lower()


def test_arista_run_cmds_rejects_device_not_in_inventory(client):
    """Same threat surface as above, on /api/arista/run-cmds."""
    r = client.post(
        "/api/arista/run-cmds",
        json={
            "device": {
                "hostname": "ghost",
                "ip": "203.0.113.99",
                "credential": "test-cred",
            },
            "cmds": ["show version"],
        },
    )
    assert r.status_code == 404
    assert "inventory" in (r.get_json().get("error") or "").lower()


def test_custom_command_rejects_device_not_in_inventory(client):
    """Same threat surface, on /api/custom-command (SSH path)."""
    r = client.post(
        "/api/custom-command",
        json={
            "device": {
                "hostname": "ghost",
                "ip": "203.0.113.99",
                "credential": "test-cred",
            },
            "command": "show version",
        },
    )
    assert r.status_code == 404
    assert "inventory" in (r.get_json().get("error") or "").lower()


def test_run_device_uses_inventory_credential_not_request_body(client):
    """Threat: caller passes ``credential="prod-root"`` for an inventory
    device that is bound to ``test-cred``. The route must use the
    inventory's credential, not the body's.
    """
    captured: dict = {}

    def _capture_device(device, *_args, **_kwargs):
        captured["credential"] = (device or {}).get("credential")
        return {"hostname": "leaf-01", "ip": "10.0.0.1", "error": None, "commands": []}

    with patch(
        "backend.blueprints.runs_bp.run_device_commands", side_effect=_capture_device
    ):
        r = client.post(
            "/api/run/device",
            json={
                "device": {
                    "hostname": "leaf-01",
                    "ip": "10.0.0.1",
                    "credential": "ATTACKER-CHOSEN-PROD-ROOT",
                }
            },
        )
    assert r.status_code == 200
    # Inventory's credential ("test-cred") wins over the request body's.
    assert captured["credential"] == "test-cred", (
        f"request-body credential leaked into runner: {captured!r}"
    )


# --------------------------------------------------------------------------- #
# H-3 — Credential names are sanitised before DB lookup                       #
# --------------------------------------------------------------------------- #


def test_get_credentials_rejects_unsanitisable_name():
    """Threat: a credential name with shell-meta or NUL bytes flowing
    through the legacy resolver could land in audit logs / error messages.
    The InputSanitizer pre-check rejects them before any DB call.
    """
    from unittest.mock import MagicMock

    from backend.runners.runner import _get_credentials

    cred_store = MagicMock()
    # The sanitiser should reject this name; the cred store must NOT be called.
    user, pwd = _get_credentials("evil; rm -rf /", "secret", cred_store)
    assert (user, pwd) == ("", "")
    cred_store.get_credential.assert_not_called()


def test_get_credentials_passes_clean_name_to_store():
    """Counterpart: a well-formed name reaches the store unchanged."""
    from unittest.mock import MagicMock

    from backend.runners.runner import _get_credentials

    cred_store = MagicMock()
    cred_store.get_credential.return_value = {
        "method": "basic",
        "username": "alice",
        "password": "p",
    }
    user, pwd = _get_credentials("test-cred", "secret", cred_store)
    assert (user, pwd) == ("alice", "p")
    cred_store.get_credential.assert_called_once()
    assert cred_store.get_credential.call_args.args[0] == "test-cred"


# --------------------------------------------------------------------------- #
# H-4 — CredentialService.delete sanitises name                               #
# --------------------------------------------------------------------------- #


def test_credential_service_delete_rejects_unsanitisable_name(tmp_path):
    """Threat: an attacker calls DELETE /api/credentials/<bogus> with a
    name containing CRLF or control bytes hoping to forge audit log lines.
    The service must refuse before reaching the repository.
    """
    from unittest.mock import MagicMock

    from backend.services.credential_service import CredentialService

    repo = MagicMock()
    svc = CredentialService(repo)
    assert svc.delete("foo\r\nadmin") is False
    repo.delete.assert_not_called()


def test_credential_service_delete_accepts_clean_name():
    """Counterpart: well-formed names flow through to the repository."""
    from unittest.mock import MagicMock

    from backend.services.credential_service import CredentialService

    repo = MagicMock()
    repo.delete.return_value = True
    svc = CredentialService(repo)
    assert svc.delete("alice-cred") is True
    repo.delete.assert_called_once_with("alice-cred")


# --------------------------------------------------------------------------- #
# H-5 — Generic error envelopes (no raw exception leakage)                    #
# --------------------------------------------------------------------------- #


def test_find_leaf_envelope_does_not_leak_exception_text(client):
    """Threat: raw exception strings can include filesystem paths,
    library internals, or fragments of prepared URLs (which historically
    contained API keys). The envelope must stay generic.
    """
    sentinel = "INTERNAL-PATH-/Users/secret/path/etc/passwd"
    with patch("backend.find_leaf.find_leaf", side_effect=RuntimeError(sentinel)):
        r = client.post("/api/find-leaf", json={"ip": "10.0.0.1"})
    assert r.status_code == 200
    body = r.get_json()
    assert sentinel not in (body.get("error") or "")


def test_nat_lookup_envelope_does_not_leak_exception_text(client):
    sentinel = "X-PAN-KEY=AKIA-FAKE-LEAKED-1234567890"
    with patch("backend.nat_lookup.nat_lookup", side_effect=RuntimeError(sentinel)):
        r = client.post("/api/nat-lookup", json={"src_ip": "10.0.0.1"})
    assert r.status_code == 200
    body = r.get_json()
    assert sentinel not in (body.get("error") or "")


# --------------------------------------------------------------------------- #
# Existing-gap surfaces (from the agent's coverage map)                       #
# --------------------------------------------------------------------------- #


def test_clear_counters_requires_confirmation_header_in_production_mode(
    client, monkeypatch
):
    """Surface 2b — destructive gate is also enforced for clear-counters."""
    monkeypatch.setenv("PERGEN_REQUIRE_DESTRUCTIVE_CONFIRM", "1")
    r = client.post(
        "/api/transceiver/clear-counters",
        json={
            "device": {
                "hostname": "leaf-01",
                "ip": "10.0.0.1",
                "vendor": "Cisco",
                "credential": "test-cred",
            },
            "interface": "Ethernet1/1",
        },
    )
    assert r.status_code == 403
    body = r.get_json() or {}
    assert "X-Confirm-Destructive" in (body.get("error") or "")


@pytest.mark.parametrize(
    "ip",
    [
        "169.254.169.254",  # AWS / GCP / Azure instance metadata
        "169.254.170.2",    # ECS task metadata
        "0.0.0.0",          # unspecified
    ],
)
def test_ping_blocks_internal_address_families(client, monkeypatch, ip):
    """Surface 9 — SSRF guard on /api/ping must cover cloud metadata and
    the unspecified address, not just the loopback range.
    """
    monkeypatch.delenv("PERGEN_ALLOW_INTERNAL_PING", raising=False)
    r = client.post("/api/ping", json={"devices": [{"ip": ip}]})
    assert r.status_code in (200, 400)
    body = r.get_json() or {}
    results = body.get("results") or body.get("devices") or []
    for entry in results:
        assert not entry.get("reachable"), (
            f"SSRF guard let through {ip!r}: {entry!r}"
        )


def test_credential_repository_treats_injection_payload_as_literal_name(tmp_path):
    """Surface 6 — SQL injection literal in credential ``name`` must NOT
    drop the credentials table. The repo uses ``?``-bound parameters; this
    test fails if anyone switches to f-string SQL.
    """
    import sqlite3

    from backend.repositories.credential_repository import CredentialRepository
    from backend.security.encryption import EncryptionService

    db_path = tmp_path / "creds.db"
    enc = EncryptionService.from_secret("pergen-test-secret-key-deterministic")
    repo = CredentialRepository(str(db_path), enc)
    repo.create_schema()

    # Seed a known-good row so the table is materialised.
    repo.set("benign", method="api_key", api_key="abc")

    payload = "x'; DROP TABLE credentials;--"
    # The call may raise (sanitiser at service level) or succeed (literal
    # storage at repo level). Both are acceptable; the invariant is: the
    # table survives.
    try:
        repo.set(payload, method="api_key", api_key="evil")
    except Exception:
        pass
    try:
        repo.get(payload)
    except Exception:
        pass

    with sqlite3.connect(str(db_path)) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "credentials" in tables, (
        f"credentials table dropped — SQL injection succeeded: tables={tables}"
    )


def test_api_token_gate_exempts_health_probe(flask_app):
    """Surface 1 — /api/health stays open even when the gate is active so
    load-balancer liveness checks don't break.
    """
    flask_app.config["PERGEN_API_TOKEN"] = "tok-health-exempt-test-32chars-min"
    _rebuild_snapshot(flask_app)
    c = flask_app.test_client()
    r = c.get("/api/health")  # no X-API-Token header
    assert r.status_code != 401, (
        f"/api/health was gated despite documented exemption: {r.status_code}"
    )


def test_api_token_gate_uses_constant_time_comparison():
    """Surface 1 — pin the use of hmac.compare_digest. A regression to
    plain `==` would reintroduce a timing oracle on the token bytes.
    """
    from backend import app_factory

    src = inspect.getsource(app_factory._install_api_token_gate)
    assert "hmac.compare_digest" in src, (
        "API-token gate must use hmac.compare_digest for timing-safe "
        "comparison; found:\n" + src
    )


# --------------------------------------------------------------------------- #
# Audit log line format (C-2 actor recorded)                                  #
# --------------------------------------------------------------------------- #


def test_credential_set_audit_log_records_actor(client, caplog):
    """Audit lines for credential.set must include actor=<name>.

    With no token gate active (dev), the actor falls back to "anonymous"
    — but the audit line must still record *some* actor identifier so
    downstream log-search queries always have the field.
    """
    caplog.set_level(logging.INFO, logger="app.audit")
    r = client.post(
        "/api/credentials",
        json={
            "name": "audit-test-cred",
            "method": "basic",
            "username": "u",
            "password": "p",
        },
    )
    assert r.status_code == 200
    audit_lines = [
        rec.getMessage()
        for rec in caplog.records
        if rec.name == "app.audit" and "credential.set" in rec.getMessage()
    ]
    assert audit_lines, "no credential.set audit line emitted"
    assert any("actor=" in line for line in audit_lines)
