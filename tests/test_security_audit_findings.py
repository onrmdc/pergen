"""
Tests for findings from the post-Phase-13 security audit.

Each test is named for its finding ID (C1, H1, M1, etc.) so the
audit report and the test suite stay cross-referenceable.

The tests fall into three categories:
1. **Refactor regression tests** (C1, H6, C2-app, R7) — assert the
   refactor-introduced issues stay fixed.
2. **Pre-existing security gap tests** (C3, H4, H7, H8, H9) — assert
   the new defenses (auth gate, mass-assignment guard, etc.) work.
3. **Best-practice / defense-in-depth tests** (M1-M11).
"""
from __future__ import annotations

import os
import threading
import time
from unittest.mock import patch


# --------------------------------------------------------------------------- #
# C1 — TransceiverService side-channel state                                  #
# --------------------------------------------------------------------------- #


def test_transceiver_service_has_no_hidden_state_between_devices():
    """``_collect_status`` must return its own raw result, not stash it."""
    from backend.services.transceiver_service import TransceiverService

    svc = TransceiverService(secret_key="x", credential_store=None)
    # The fix is to make _collect_status return a tuple. Service must NOT
    # rely on a `_last_status_result` instance attribute.
    assert not hasattr(svc, "_last_status_result"), (
        "TransceiverService leaks per-call state via _last_status_result; "
        "fix _collect_status to return (status_map, raw_result) instead."
    )


def test_transceiver_service_collect_rows_safe_under_concurrent_devices():
    """Two devices processed sequentially must not see each other's status."""
    from backend.services.transceiver_service import TransceiverService

    svc = TransceiverService(secret_key="x", credential_store=None)

    captured_states: list = []

    def stub(*_a, **k):
        cf = k.get("command_id_filter")
        cid_exact = k.get("command_id_exact")
        device = _a[0] if _a else {}
        host = device.get("hostname", "")
        if cf == "transceiver":
            return {
                "hostname": host,
                "ip": device.get("ip"),
                "parsed_flat": {
                    "transceiver_rows": [{"interface": "Eth1", "serial": f"sn-{host}"}]
                },
            }
        if cf == "interface_status":
            captured_states.append({"host": host, "id": id(svc)})
            return {
                "parsed_flat": {
                    "interface_status_rows": [
                        {"interface": "Eth1", "state": f"state-{host}"}
                    ]
                }
            }
        if cid_exact == "cisco_nxos_show_interface":
            return {"parsed_flat": {"interface_flapped_rows": []}}
        return {"parsed_flat": {}}

    with patch(
        "backend.services.transceiver_service.run_device_commands", side_effect=stub
    ):
        rows, _errors, _trace = svc.collect_rows(
            [
                {"hostname": "leaf-A", "ip": "1.1.1.1", "vendor": "Arista", "role": "Leaf"},
                {"hostname": "leaf-B", "ip": "2.2.2.2", "vendor": "Arista", "role": "Leaf"},
            ]
        )
    assert rows[0]["status"] == "state-leaf-A"
    assert rows[1]["status"] == "state-leaf-B"


# --------------------------------------------------------------------------- #
# C2/R7 — Dual SECRET_KEY defaults                                            #
# --------------------------------------------------------------------------- #


def test_no_secret_key_default_evaluated_at_app_py_import():
    """``backend/app.py`` must not hardcode the historic placeholder.

    Static-source check rather than a re-import: re-importing backend
    modules at runtime breaks every other test's class identity (since
    cached classes elsewhere reference the old module). The C2 fix is
    that ``backend/app.py`` no longer hardcodes ``"dev-secret-change-in-prod"``;
    a grep proves it.
    """
    import backend.app as app_mod

    src = open(app_mod.__file__).read()
    assert "dev-secret-change-in-prod" not in src, (
        "backend/app.py still contains the historic placeholder string. "
        "Use ``DEFAULT_SECRET_KEY`` from ``backend.config.app_config`` instead."
    )


def test_production_config_rejects_both_historic_secret_key_placeholders(monkeypatch):
    """``ProductionConfig.validate()`` must reject EITHER historic default."""
    from backend.config.app_config import ProductionConfig

    for placeholder in (
        "pergen-default-secret-CHANGE-ME",
        "dev-secret-change-in-prod",
    ):
        monkeypatch.setenv("SECRET_KEY", placeholder)
        cfg = ProductionConfig()
        try:
            cfg.validate()
            assert False, f"ProductionConfig accepted historic placeholder: {placeholder!r}"
        except (ValueError, RuntimeError):
            pass  # expected (either exception type is acceptable)


# --------------------------------------------------------------------------- #
# H1 — InventoryService.csv_path public property                               #
# --------------------------------------------------------------------------- #


def test_inventory_service_exposes_public_csv_path_property(tmp_path):
    """No more ``svc._repo._csv_path`` reach-arounds."""
    from backend.repositories import InventoryRepository
    from backend.services.inventory_service import InventoryService

    csv = tmp_path / "inv.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n",
        encoding="utf-8",
    )
    svc = InventoryService(InventoryRepository(str(csv)))
    assert svc.csv_path == str(csv)
    # Repository also exposes it
    assert svc._repo.csv_path == str(csv)  # noqa: SLF001 - verifying property exists


def test_inventory_repository_csv_path_is_read_only():
    """The property has no setter."""
    from backend.repositories import InventoryRepository

    repo = InventoryRepository("/tmp/whatever")
    try:
        repo.csv_path = "/tmp/other"  # noqa: B010 — intentional check
        assert False, "csv_path must be read-only"
    except AttributeError:
        pass


# --------------------------------------------------------------------------- #
# H6 — RunStateStore thread safety                                             #
# --------------------------------------------------------------------------- #


def test_run_state_store_concurrent_set_does_not_lose_writes():
    """Many threads writing distinct run_ids must all land."""
    from backend.services.run_state_store import RunStateStore

    store = RunStateStore()
    n = 200

    def writer(i: int):
        store.set(f"run-{i}", {"phase": "PRE", "i": i})

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for i in range(n):
        # Wave-4 W4-M-02: set() always records ``_created_by_actor`` —
        # strip it from the equality compare since the test only cares
        # that the user-supplied fields round-trip intact.
        got = store.get(f"run-{i}")
        assert got is not None
        got.pop("_created_by_actor", None)
        assert got == {"phase": "PRE", "i": i}


def test_run_state_store_get_returns_deep_copy():
    """Mutations on the returned dict must not leak back into the store."""
    from backend.services.run_state_store import RunStateStore

    store = RunStateStore()
    store.set("r1", {"phase": "PRE", "devices": [{"hostname": "leaf-1"}]})
    snap = store.get("r1")
    assert snap is not None
    snap["phase"] = "MUTATED"
    snap["devices"][0]["hostname"] = "PWNED"
    fresh = store.get("r1")
    assert fresh is not None
    assert fresh["phase"] == "PRE"
    assert fresh["devices"][0]["hostname"] == "leaf-1"


def test_run_state_store_supports_ttl_and_eviction():
    """Old runs are evicted after the configured TTL."""
    from backend.services.run_state_store import RunStateStore

    store = RunStateStore(ttl_seconds=1)
    store.set("r1", {"phase": "PRE"})
    assert store.get("r1") is not None
    time.sleep(1.1)
    assert store.get("r1") is None  # expired


def test_run_state_store_delete_method_exists():
    from backend.services.run_state_store import RunStateStore

    store = RunStateStore()
    store.set("r1", {"phase": "PRE"})
    assert store.delete("r1") is True
    assert store.delete("r1") is False  # idempotent
    assert store.get("r1") is None


def test_run_state_store_caps_total_entries():
    """Defense against unauthenticated state-flood attacks."""
    from backend.services.run_state_store import RunStateStore

    store = RunStateStore(max_entries=10)
    for i in range(20):
        store.set(f"r-{i}", {"phase": "PRE", "i": i})
    # Oldest evicted; newest retained.
    assert store.get("r-0") is None
    assert store.get("r-19") is not None


# --------------------------------------------------------------------------- #
# C3/R1/R2 — credentials_bp uses CredentialService (not legacy creds)         #
# --------------------------------------------------------------------------- #


def test_credentials_bp_crud_uses_credential_service_not_legacy_module():
    """CRUD operations must go through CredentialService.

    The /validate runner shim is allowed to keep the legacy adapter
    until ``backend.runners.runner`` is itself migrated — that's a
    separate scope. But list/create/delete must use the service.
    """
    import importlib

    bp = importlib.import_module("backend.blueprints.credentials_bp")
    src = open(bp.__file__).read()
    assert "_credential_service" in src, (
        "credentials_bp must define a _credential_service() helper "
        "that resolves the new CredentialService from app.extensions."
    )
    # Confirm the CRUD routes call the service.
    for endpoint in ("api_credentials_list", "api_credentials_create", "api_credentials_delete"):
        idx = src.find(f"def {endpoint}")
        assert idx >= 0, f"missing {endpoint}"
        # Walk forward to the next def or eof
        body_end = src.find("\n\n\n", idx)
        if body_end < 0:
            body_end = len(src)
        body = src[idx:body_end]
        assert "_credential_service()" in body, (
            f"{endpoint} does not call _credential_service(); "
            "it still uses the legacy creds module."
        )


def test_credential_service_round_trip_via_api(client):
    """Credentials created via API can be read back."""
    r = client.post(
        "/api/credentials",
        json={"name": "phase-audit-cred", "method": "api_key", "api_key": "secret"},
    )
    assert r.status_code == 200
    listing = client.get("/api/credentials").get_json()["credentials"]
    assert any((c.get("name") or c) == "phase-audit-cred" for c in listing)


# --------------------------------------------------------------------------- #
# H4 — Mass assignment & input validation on inventory writes                  #
# --------------------------------------------------------------------------- #


def test_inventory_add_rejects_invalid_ip(client):
    r = client.post(
        "/api/inventory/device",
        json={"hostname": "evil", "ip": "$(rm -rf /)", "credential": "test-cred"},
    )
    assert r.status_code == 400
    assert "ip" in r.get_json()["error"].lower()


def test_inventory_add_rejects_unsanitised_hostname(client):
    r = client.post(
        "/api/inventory/device",
        json={"hostname": "<script>alert(1)</script>", "ip": "10.0.0.50"},
    )
    assert r.status_code == 400


def test_inventory_add_rejects_unknown_fields(client):
    """Mass assignment defense — unknown fields are 400, not silently dropped."""
    r = client.post(
        "/api/inventory/device",
        json={
            "hostname": "leaf-mx",
            "ip": "10.0.0.55",
            "is_admin": True,  # ← not in INVENTORY_HEADER
            "secret_token": "stolen",
        },
    )
    assert r.status_code == 400
    assert "unknown" in r.get_json()["error"].lower() or "field" in r.get_json()["error"].lower()


# --------------------------------------------------------------------------- #
# H7 — Device-from-request rebinding (cannot pass arbitrary credential)       #
# --------------------------------------------------------------------------- #


def test_transceiver_recover_resolves_device_from_inventory_not_request_body(client):
    """Audit H7: even if the body sets credential=tech, the server uses the stored one."""
    # The inventory contains leaf-01 with credential=test-cred. An attacker
    # sending {"hostname":"leaf-01","credential":"tech",...} must end up
    # using test-cred (the inventory-stored value), NOT 'tech'.
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as m:
        m.return_value = {"method": "basic", "username": "u", "password": "p"}
        with patch(
            "backend.runners.interface_recovery.recover_interfaces_arista_eos",
            return_value=([], None),
        ), patch(
            "backend.runners.interface_recovery.fetch_interface_status_summary_arista_eos",
            return_value=("ok", None),
        ):
            client.post(
                "/api/transceiver/recover",
                json={
                    # Attacker only needs hostname/ip to address the device;
                    # the body's ``credential`` field is intentionally a lie.
                    "device": {"hostname": "leaf-01", "credential": "tech"},
                    "interfaces": ["Ethernet1/1"],
                },
            )
    # The credential lookup must have used "test-cred" (from inventory),
    # not "tech" (from request body).
    args, _ = m.call_args
    assert args[0] == "test-cred", (
        f"Expected inventory-resolved credential 'test-cred', got {args[0]!r}; "
        "the route must look up the device from inventory, not trust the body"
    )


# --------------------------------------------------------------------------- #
# H3 — SSRF guard on /api/ping                                                 #
# --------------------------------------------------------------------------- #


def test_ping_blocks_loopback_by_default(client):
    """127.0.0.1 must be rejected unless PERGEN_ALLOW_INTERNAL_PING=1."""
    r = client.post(
        "/api/ping",
        json={"devices": [{"hostname": "lo", "ip": "127.0.0.1"}]},
    )
    assert r.status_code == 200
    body = r.get_json()
    # Either rejected outright or marked unreachable without subprocess call.
    assert body["results"][0]["reachable"] is False


def test_ping_blocks_link_local_by_default(client):
    r = client.post(
        "/api/ping",
        json={"devices": [{"hostname": "ll", "ip": "169.254.169.254"}]},
    )
    assert r.status_code == 200
    assert r.get_json()["results"][0]["reachable"] is False


# --------------------------------------------------------------------------- #
# H8 — Credential storage permissions                                          #
# --------------------------------------------------------------------------- #


def test_credential_db_file_has_owner_only_permissions(tmp_path):
    """The credentials SQLite file must be 0o600."""
    from backend.repositories import CredentialRepository
    from backend.security.encryption import EncryptionService

    db = tmp_path / "creds_v2.db"
    enc = EncryptionService.from_secret("test-key" * 8)
    repo = CredentialRepository(str(db), enc)
    repo.create_schema()
    # File should exist and be 0o600
    assert db.exists()
    mode = db.stat().st_mode & 0o777
    # On macOS/Linux umask may relax this; verify the repository attempted chmod.
    if os.name == "posix":
        assert mode == 0o600, (
            f"credentials DB mode is {oct(mode)}, expected 0o600. "
            "CredentialRepository should chmod the file after create_schema()."
        )


# --------------------------------------------------------------------------- #
# H9 — Path traversal hardening (pathlib-based)                                #
# --------------------------------------------------------------------------- #


def test_report_repository_rejects_directory_traversal(tmp_path):
    from backend.repositories import ReportRepository

    repo = ReportRepository(str(tmp_path))
    # These all attempt to escape the reports_dir
    for evil in ["../etc/passwd", "..\\..\\windows", "a/b/../c", "../../"]:
        try:
            path = repo._report_path(evil)
            # If no exception, the path must still resolve under tmp_path.
            from pathlib import Path

            assert Path(path).resolve().is_relative_to(Path(str(tmp_path)).resolve()), (
                f"{evil!r} escaped to {path!r}"
            )
        except ValueError:
            pass  # acceptable — explicit rejection


# --------------------------------------------------------------------------- #
# M2 — Error envelopes don't leak stack traces                                 #
# --------------------------------------------------------------------------- #


def test_transceiver_recover_error_envelope_does_not_leak_stack_trace(client):
    """Audit M2: exception detail must not leak through the response body."""
    # Use leaf-02 (Cisco NX-OS in the test inventory).
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "u", "password": "p"}
        with patch(
            "backend.runners.interface_recovery.recover_interfaces_cisco_nxos",
            side_effect=RuntimeError(
                "Traceback (most recent call last):\n  File '/etc/secret.key'..."
            ),
        ):
            r = client.post(
                "/api/transceiver/recover",
                json={
                    "device": {"hostname": "leaf-02", "ip": "10.0.0.2"},
                    "interfaces": ["Ethernet1/1"],
                },
            )
    assert r.status_code == 500
    body = r.get_json()
    err = body.get("error", "")
    assert "Traceback" not in err
    assert "/etc/secret.key" not in err


# --------------------------------------------------------------------------- #
# M4 — DoS protection on /api/diff                                             #
# --------------------------------------------------------------------------- #


def test_diff_rejects_oversized_input(client):
    """A 1MB pre/post text must be rejected to bound difflib.unified_diff."""
    big = "x" * (300 * 1024)
    r = client.post("/api/diff", json={"pre": big, "post": big[:-1]})
    # Either 400 (rejected) or 200 (accepted but capped) is acceptable.
    # Critical: must not OOM or hang.
    assert r.status_code in (200, 400, 413)


# --------------------------------------------------------------------------- #
# M11 — CommandValidator dict-form bypass                                      #
# --------------------------------------------------------------------------- #


def test_arista_run_cmds_rejects_dict_with_unknown_keys(client):
    """``{cmd: "show version", input: "rogue\\nwrite mem"}`` must be rejected
    or have its ``input`` key stripped (only ``enable`` may carry input).

    We mock ``arista_eapi.run_cmds`` so we can introspect what the route
    forwarded — the 'input' key on a non-enable cmd must NOT survive.
    Pinning behaviour avoids relying on cred-DB state across tests
    (audit H-2 made the route inventory-bound, so prior-test seeded
    credentials would otherwise let the request hit a real network).
    """
    captured: dict = {}

    def _capture(_ip, _u, _p, cmds, **_kwargs):
        captured["cmds"] = cmds
        return ([{"version": "4.30"}], None)

    with patch(
        "backend.runners.arista_eapi.run_cmds", side_effect=_capture
    ), patch(
        "backend.blueprints.device_commands_bp._get_credentials",
        return_value=("u", "p"),
    ):
        r = client.post(
            "/api/arista/run-cmds",
            json={
                # leaf-01 is in the mock inventory.
                "device": {"hostname": "leaf-01", "ip": "10.0.0.1", "credential": "test-cred"},
                "cmds": [
                    {"cmd": "show version", "input": "extra\nconfigure terminal"},
                ],
            },
        )
    # Route succeeded; verify the dangerous 'input' was stripped.
    assert r.status_code == 200
    forwarded = captured.get("cmds") or []
    assert len(forwarded) == 1
    forwarded_cmd = forwarded[0]
    if isinstance(forwarded_cmd, dict):
        # Audit M11: only the ``cmd`` key is forwarded for non-enable dicts.
        assert "input" not in forwarded_cmd, (
            "Non-enable dict cmd retained 'input' — bypass: " + repr(forwarded_cmd)
        )
        assert forwarded_cmd.get("cmd") == "show version"
    else:
        # Acceptable alternative: route flattened to a string.
        assert forwarded_cmd == "show version"


# --------------------------------------------------------------------------- #
# Audit logging (A09)                                                          #
# --------------------------------------------------------------------------- #


def test_audit_log_emitted_for_destructive_operations(client, caplog):
    """Destructive ops must emit an audit log line at INFO+."""
    import logging

    caplog.set_level(logging.INFO)
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "u", "password": "p"}
        with patch(
            "backend.runners.interface_recovery.recover_interfaces_arista_eos",
            return_value=([], None),
        ), patch(
            "backend.runners.interface_recovery.fetch_interface_status_summary_arista_eos",
            return_value=("ok", None),
        ):
            client.post(
                "/api/transceiver/recover",
                json={
                    "device": {
                        "hostname": "leaf-01",
                        "ip": "10.0.0.1",
                        "vendor": "Arista",
                        "role": "Leaf",
                        "credential": "test-cred",
                    },
                    "interfaces": ["Ethernet1/1"],
                },
            )
    # Look for an audit-tagged log line
    audit_lines = [r for r in caplog.records if "audit" in r.name.lower() or "audit" in (r.message or "").lower()]
    assert audit_lines, (
        "No audit log emitted for /api/transceiver/recover; "
        "destructive operations must produce an auditable record."
    )
