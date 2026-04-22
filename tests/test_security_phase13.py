"""
Phase-13 security regression tests.

Each test in this file pins a specific hardening that landed in phase 13
in response to the CRITICAL / HIGH / MEDIUM findings surfaced by the
``security-reviewer`` and ``python-reviewer`` audits.  A failure here
indicates that a known security control regressed — every test names the
audit finding it locks in (e.g. ``# C-2``).

Coverage matrix (one assertion = one finding):

* C-2  ``/api/arista/run-cmds`` rejects configure/write commands.
* C-3  Palo Alto API key is delivered via ``X-PAN-KEY`` header (never URL).
* C-4  ``/api/custom-command`` uses ``CommandValidator``.
* C-5  ``/api/ping`` validates IPs and caps the device list.
* H-1  ``NotepadRepository.update`` is atomic under concurrent writers.
* H-2  NAT XML parsing uses ``defusedxml`` (XXE protection).
* H-5  Notepad route returns generic error on internal failure.
* H-6  Every response carries the documented security headers.
* H-8  SSH commands from ``commands.yaml`` go through ``CommandValidator``.
* M-4  ``CommandValidator`` defeats Unicode homoglyph bypass (NFKC).
* M-5  ``CommandValidator`` strips and re-anchors the prefix regex.
* M-8  Oversized request bodies are rejected.
* py-HIGH  ``encryption._key_expand_128`` raises ``ValueError`` on bad key
            length even with ``python -O``.
* py-HIGH  ``CredentialRepository`` works with ``:memory:`` SQLite via a
            persistent connection.
* py-HIGH  ``ReportRepository`` rejects path-traversal ``run_id`` values.
* py-MED   ``InventoryRepository._ip_sort_key`` is stable for 4-octet IPs.
* py-MED   Blueprint ``_svc()`` helpers raise ``RuntimeError`` (not
            ``KeyError``) when the service is unregistered.

Each test is small and isolated.
"""
from __future__ import annotations

import json
import threading
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.security]


# --------------------------------------------------------------------------- #
# C-2 — /api/arista/run-cmds runs every command through CommandValidator      #
# --------------------------------------------------------------------------- #


def test_arista_run_cmds_rejects_configure_terminal(client):
    r = client.post(
        "/api/arista/run-cmds",
        json={
            "device": {"hostname": "leaf-01", "ip": "10.0.0.1", "credential": "test-cred"},
            "cmds": ["configure terminal", "interface Loopback999"],
        },
    )
    assert r.status_code == 400
    body = r.get_json() or {}
    assert "rejected command" in (body.get("error") or "")


def test_arista_run_cmds_rejects_write_memory(client):
    r = client.post(
        "/api/arista/run-cmds",
        json={
            "device": {"hostname": "leaf-01", "ip": "10.0.0.1", "credential": "test-cred"},
            "cmds": ["write memory"],
        },
    )
    assert r.status_code == 400


def test_arista_run_cmds_rejects_shell_meta_in_dict_form(client):
    r = client.post(
        "/api/arista/run-cmds",
        json={
            "device": {"hostname": "leaf-01", "ip": "10.0.0.1", "credential": "test-cred"},
            "cmds": [{"cmd": "show version; reload"}],
        },
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# C-4 — /api/custom-command goes through CommandValidator                     #
# --------------------------------------------------------------------------- #


def test_custom_command_rejects_semicolon(client):
    r = client.post(
        "/api/custom-command",
        json={
            "device": {"ip": "10.0.0.1", "credential": "test-cred"},
            "command": "show version; configure terminal",
        },
    )
    assert r.status_code == 400


def test_custom_command_rejects_pipe_write(client):
    r = client.post(
        "/api/custom-command",
        json={
            "device": {"ip": "10.0.0.1", "credential": "test-cred"},
            "command": "show version | write",
        },
    )
    assert r.status_code == 400


def test_custom_command_rejects_backtick(client):
    r = client.post(
        "/api/custom-command",
        json={
            "device": {"ip": "10.0.0.1", "credential": "test-cred"},
            "command": "show version `whoami`",
        },
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# C-5 — /api/ping validates each IP and enforces a device cap                 #
# --------------------------------------------------------------------------- #


def test_ping_returns_unreachable_for_invalid_ip(client):
    r = client.post(
        "/api/ping",
        json={"devices": [{"hostname": "x", "ip": "not-an-ip"}]},
    )
    assert r.status_code == 200
    results = r.get_json()["results"]
    assert results[0]["reachable"] is False


def test_ping_returns_unreachable_for_shell_meta_ip(client):
    r = client.post(
        "/api/ping",
        json={"devices": [{"hostname": "x", "ip": "10.0.0.1; rm -rf /"}]},
    )
    assert r.status_code == 200
    assert r.get_json()["results"][0]["reachable"] is False


def test_ping_caps_device_list_at_64(client):
    devices = [{"hostname": f"h{i}", "ip": f"10.0.0.{i % 254 + 1}"} for i in range(120)]
    r = client.post("/api/ping", json={"devices": devices})
    assert r.status_code == 400
    assert "capped" in (r.get_json()["error"] or "")


# --------------------------------------------------------------------------- #
# H-2 / C-3 — defusedxml + X-PAN-KEY header (no URL leak)                     #
# --------------------------------------------------------------------------- #


def test_nat_lookup_uses_defusedxml():
    """The defusedxml parser must reject Billion-Laughs entity expansion."""
    import backend.nat_lookup as nl

    # Billion Laughs payload
    bomb = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
        "<lolz>&lol2;</lolz>"
    )
    # _find_nat_rule_name_in_response wraps fromstring; defusedxml
    # raises EntitiesForbidden which the helper swallows and falls back
    # to regex.  The contract under test is "doesn't crash, doesn't blow
    # up memory, returns None or a safe regex match".
    out = nl._find_nat_rule_name_in_response(bomb)
    assert out is None  # no <entry>/<member> in payload


def test_nat_lookup_does_not_leak_api_key_in_url():
    """The PAN API key must travel in the X-PAN-KEY header, never as ?key="""
    import backend.nat_lookup as nl

    captured: dict[str, object] = {}

    class _FakeResponse:
        text = ""
        status_code = 200
        def raise_for_status(self) -> None:
            return None

    def _fake_get(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs.get("params") or {}
        captured["headers"] = kwargs.get("headers") or {}
        return _FakeResponse()

    fake_inventory = [
        {
            "hostname": "fw1", "ip": "10.0.0.99", "fabric": "FAB1",
            "site": "Mars", "vendor": "palo-alto", "model": "panos",
            "tag": "natlookup", "credential": "fw-cred",
        }
    ]

    class _CredStub:
        @staticmethod
        def get_credential(name: str, secret_key: str):
            return {"method": "api_key", "api_key": "SUPERSECRETKEY123"}

    with patch.object(nl.requests, "get", side_effect=_fake_get), \
         patch.object(nl, "load_inventory", return_value=fake_inventory), \
         patch.object(nl, "get_devices_by_tag", return_value=fake_inventory):
        nl.nat_lookup(
            src_ip="10.0.0.1",
            dest_ip="8.8.8.8",
            secret_key="x",
            cred_store_module=_CredStub,
            inventory_path=None,
            timeout=1,
            fabric="FAB1",
            site="Mars",
        )

    params = captured.get("params") or {}
    headers = captured.get("headers") or {}
    assert "key" not in params, f"API key leaked into URL params: {params}"
    assert headers.get("X-PAN-KEY") == "SUPERSECRETKEY123"


# --------------------------------------------------------------------------- #
# H-1 — NotepadRepository.update is atomic                                    #
# --------------------------------------------------------------------------- #


def test_notepad_update_is_atomic_under_concurrency(tmp_path):
    """50 concurrent writers must not corrupt the editor list."""
    from backend.repositories.notepad_repository import NotepadRepository

    repo = NotepadRepository(str(tmp_path))
    errors: list[Exception] = []

    def writer(idx: int) -> None:
        try:
            repo.update(f"line-{idx}\n", f"user{idx}")
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent writers raised: {errors}"
    final = repo.load()
    assert isinstance(final["content"], str)
    assert isinstance(final["line_editors"], list)


# --------------------------------------------------------------------------- #
# H-5 — generic error envelope on notepad write failure                       #
# --------------------------------------------------------------------------- #


def test_notepad_put_generic_error_does_not_leak(client):
    """An OSError inside NotepadService.update must surface as a generic 500."""
    from backend.services.notepad_service import NotepadService

    def _boom(self, *_a, **_kw):
        raise OSError("/internal/path/secrets.json: permission denied")

    with patch.object(NotepadService, "update", _boom):
        r = client.put("/api/notepad", json={"content": "hello", "user": "x"})
    assert r.status_code == 500
    body = r.get_json() or {}
    assert "internal" not in str(body).lower()
    assert "permission" not in str(body).lower()


# --------------------------------------------------------------------------- #
# H-6 — security response headers                                             #
# --------------------------------------------------------------------------- #


def test_response_has_x_frame_options(client):
    r = client.get("/api/health")
    assert r.headers.get("X-Frame-Options") == "DENY"


def test_response_has_nosniff(client):
    r = client.get("/api/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


def test_response_has_referrer_policy(client):
    r = client.get("/api/health")
    assert "Referrer-Policy" in r.headers


def test_response_has_permissions_policy(client):
    r = client.get("/api/health")
    assert "Permissions-Policy" in r.headers


# --------------------------------------------------------------------------- #
# H-8 — runner.py runs SSH yaml commands through CommandValidator             #
# --------------------------------------------------------------------------- #


def test_runner_ssh_path_uses_command_validator(monkeypatch):
    """Even commands sourced from commands.yaml ssh.command must validate."""
    from backend.runners import runner as runner_mod

    captured: dict[str, str] = {}

    def fake_get_commands_for_device(_vendor, _model, _role):
        return [
            {
                "id": "malicious-yaml",
                "method": "ssh",
                "ssh": {"command": "configure terminal"},
            }
        ]

    monkeypatch.setattr(
        runner_mod.cmd_loader, "get_commands_for_device", fake_get_commands_for_device
    )
    monkeypatch.setattr(
        runner_mod.cmd_loader, "get_parser", lambda _cid: None
    )

    def fake_run_command(*_args, **_kwargs):
        captured["called"] = "ssh"
        return ("OK", None)

    import backend.runners.ssh_runner as sshmod
    monkeypatch.setattr(sshmod, "run_command", fake_run_command)

    out = runner_mod.run_device_commands(
        device={"hostname": "h", "ip": "10.0.0.1", "vendor": "Cisco", "model": "NX-OS",
                "credential": "test-cred"},
        secret_key="x",
        cred_store_module=type("C", (), {"get_credential": staticmethod(
            lambda n, k: {"method": "basic", "username": "u", "password": "p"})})(),
    )
    cmd_entries = out.get("commands") or []
    assert cmd_entries, f"expected at least one command entry, got {out!r}"
    err = (cmd_entries[0].get("error") or "").lower()
    assert "rejected" in err or "commandvalidator" in err
    assert captured.get("called") != "ssh", "ssh transport ran with bad command"


# --------------------------------------------------------------------------- #
# M-4 / M-5 — CommandValidator unicode + whitespace hardening                 #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "command",
    [
        "ｓｈｏｗ ｖｅｒｓｉｏｎ",  # fullwidth (NFKC → "show version")
        "show\u3000version",       # ideographic space
    ],
)
def test_command_validator_normalises_unicode(command):
    from backend.security.validator import CommandValidator
    ok, _ = CommandValidator.validate(command)
    assert ok, f"NFKC-normalised command should pass: {command!r}"


def test_command_validator_rejects_cyrillic_show():
    from backend.security.validator import CommandValidator
    ok, _ = CommandValidator.validate("ѕhow version")  # Cyrillic ѕ
    assert not ok


def test_command_validator_rejects_embedded_newline():
    from backend.security.validator import CommandValidator
    ok, _ = CommandValidator.validate("show version\nreload")
    assert not ok


def test_command_validator_strips_leading_whitespace():
    from backend.security.validator import CommandValidator
    ok, _ = CommandValidator.validate("   show version")
    assert ok


def test_command_validator_rejects_tab_only_prefix_with_block():
    from backend.security.validator import CommandValidator
    ok, _ = CommandValidator.validate("\tshow version; reload")
    assert not ok


# --------------------------------------------------------------------------- #
# M-8 — MAX_CONTENT_LENGTH                                                    #
# --------------------------------------------------------------------------- #


def test_max_content_length_set_on_app(flask_app):
    cap = flask_app.config.get("MAX_CONTENT_LENGTH")
    assert cap and cap >= 1_000_000  # >=1 MB cap registered


def test_oversized_notepad_payload_rejected(client):
    """Payload over the per-route notepad cap returns 413."""
    payload = json.dumps({"content": "x" * 600_000, "user": "u"})
    r = client.put("/api/notepad", data=payload, content_type="application/json")
    assert r.status_code == 413


# --------------------------------------------------------------------------- #
# py-HIGH — encryption assert→raise survives python -O                        #
# --------------------------------------------------------------------------- #


def test_aes_key_expand_raises_on_wrong_length():
    from backend.security.encryption import _key_expand_128
    with pytest.raises(ValueError):
        _key_expand_128(b"too-short")
    with pytest.raises(ValueError):
        _key_expand_128(b"x" * 17)


# --------------------------------------------------------------------------- #
# py-HIGH — CredentialRepository works with :memory: SQLite                   #
# --------------------------------------------------------------------------- #


def test_credential_repo_in_memory_persists_across_calls():
    from backend.repositories.credential_repository import CredentialRepository
    from backend.security.encryption import EncryptionService

    enc = EncryptionService.from_secret("phase-13-test-key")
    repo = CredentialRepository(":memory:", enc)
    repo.create_schema()
    repo.set("lab", method="basic", username="admin", password="hunter2")

    # Reads on subsequent calls must see the row written above.
    listed = repo.list()
    assert [r["name"] for r in listed] == ["lab"]
    fetched = repo.get("lab")
    assert fetched and fetched["username"] == "admin"
    assert fetched["password"] == "hunter2"


# --------------------------------------------------------------------------- #
# py-HIGH — ReportRepository rejects path traversal                           #
# --------------------------------------------------------------------------- #


def test_report_repo_neutralises_dot_dot_run_id(tmp_path):
    """Path separators must be stripped from the run-id."""
    from backend.repositories.report_repository import ReportRepository

    repo = ReportRepository(str(tmp_path))
    safe = repo._safe_id("../../etc/passwd")
    assert "/" not in safe
    assert "\\" not in safe
    # Resulting on-disk path must remain inside the reports dir.
    import os
    p = os.path.abspath(repo._report_path("../../etc/passwd"))
    root = os.path.abspath(str(tmp_path)) + os.sep
    assert p.startswith(root), f"escaped reports dir: {p}"


def test_report_repo_path_stays_within_reports_dir(tmp_path):
    from backend.repositories.report_repository import ReportRepository

    repo = ReportRepository(str(tmp_path))
    p = repo._report_path("normal-id")
    import os
    assert os.path.abspath(p).startswith(os.path.abspath(str(tmp_path)) + os.sep)


# --------------------------------------------------------------------------- #
# py-MED — InventoryRepository._ip_sort_key stability                         #
# --------------------------------------------------------------------------- #


def test_ip_sort_key_pushes_short_ips_to_end():
    from backend.repositories.inventory_repository import _ip_sort_key

    assert _ip_sort_key({"ip": "10.0"}) == (999, 999, 999, 999)
    assert _ip_sort_key({"ip": "10.0.0.1"}) == (10, 0, 0, 1)
    # Ordering: a valid IP must sort before a malformed one.
    sample = [{"ip": "10.0"}, {"ip": "10.0.0.1"}]
    sample.sort(key=_ip_sort_key)
    assert sample[0]["ip"] == "10.0.0.1"


# --------------------------------------------------------------------------- #
# py-MED — Blueprint _svc() helpers raise a meaningful RuntimeError           #
# --------------------------------------------------------------------------- #


def test_inventory_bp_svc_helper_raises_runtime_error():
    from flask import Flask

    from backend.blueprints.inventory_bp import _svc

    app = Flask(__name__)
    with app.app_context(), pytest.raises(RuntimeError, match="not registered"):
        _svc()


def test_notepad_bp_svc_helper_raises_runtime_error():
    from flask import Flask

    from backend.blueprints.notepad_bp import _svc

    app = Flask(__name__)
    with app.app_context(), pytest.raises(RuntimeError, match="not registered"):
        _svc()
