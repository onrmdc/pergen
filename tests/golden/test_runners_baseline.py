"""
Baseline / characterization tests for the network device runners.

These pin down the **wire contract** (URL, JSON-RPC body, basic-auth tuple,
SSL-verify flag) and the **return shape** of each runner so the upcoming
``RunnerFactory`` + ``BaseRunner`` ABC refactor cannot drift accidentally.

No real network calls are made — ``requests.post`` and ``paramiko`` are
mocked.  Sandbox / CI safe.
"""
from __future__ import annotations

from unittest import mock

import pytest

pytestmark = pytest.mark.golden


# --------------------------------------------------------------------------- #
# Arista eAPI                                                                 #
# --------------------------------------------------------------------------- #


def _fake_response(payload: dict, status: int = 200):
    resp = mock.MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_arista_eapi_run_commands_wire_contract():
    """Locks the JSON-RPC body, URL and verify=False posture."""
    from backend.runners import arista_eapi

    captured: dict = {}

    def _capture(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _fake_response({"result": [{"version": "4.30"}]})

    with mock.patch("backend.runners.arista_eapi.requests.post", side_effect=_capture):
        results, err = arista_eapi.run_commands(
            "10.0.0.1", "user", "pw", ["show version"], timeout=15
        )

    assert err is None
    assert results == [{"version": "4.30"}]
    assert captured["url"] == "https://10.0.0.1/command-api"

    body = captured["kwargs"]["json"]
    assert body["method"] == "runCmds"
    assert body["params"]["cmds"] == ["show version"]
    assert body["params"]["format"] == "json"
    assert body["jsonrpc"] == "2.0"

    assert captured["kwargs"]["auth"] == ("user", "pw")
    assert captured["kwargs"]["verify"] is False
    assert captured["kwargs"]["timeout"] == 15


def test_arista_eapi_run_commands_returns_error_message():
    from backend.runners import arista_eapi

    err_payload = {"error": {"message": "auth failed"}}
    with mock.patch(
        "backend.runners.arista_eapi.requests.post",
        return_value=_fake_response(err_payload),
    ):
        results, err = arista_eapi.run_commands("10.0.0.1", "u", "p", ["x"])

    assert results == []
    assert err == "auth failed"


def test_arista_eapi_run_commands_handles_request_exception():
    """Network errors must come back as (empty list, string error) — never raise."""
    import requests

    from backend.runners import arista_eapi

    with mock.patch(
        "backend.runners.arista_eapi.requests.post",
        side_effect=requests.exceptions.ConnectionError("unreachable"),
    ):
        results, err = arista_eapi.run_commands("10.0.0.1", "u", "p", ["x"])

    assert results == []
    assert err == "unreachable"


def test_arista_eapi_run_cmds_passes_advanced_params():
    """The lower-level ``run_cmds`` exposes Arista's runCmds knobs verbatim."""
    from backend.runners import arista_eapi

    captured: dict = {}

    def _capture(url, **kwargs):
        captured["body"] = kwargs["json"]
        return _fake_response({"result": []})

    with mock.patch("backend.runners.arista_eapi.requests.post", side_effect=_capture):
        arista_eapi.run_cmds(
            "10.0.0.1",
            "u",
            "p",
            [{"cmd": "enable", "input": "secret"}, "show version"],
            timestamps=True,
            stop_on_error=False,
        )

    params = captured["body"]["params"]
    assert params["timestamps"] is True
    assert params["stopOnError"] is False
    assert params["cmds"] == [{"cmd": "enable", "input": "secret"}, "show version"]
    assert captured["body"]["id"] == "EapiExplorer-1"


# --------------------------------------------------------------------------- #
# Cisco NX-API                                                                #
# --------------------------------------------------------------------------- #


def test_cisco_nxapi_run_commands_one_per_command():
    """NX-API issues one POST per command (unlike Arista's batch runCmds)."""
    from backend.runners import cisco_nxapi

    calls: list = []

    def _capture(url, **kwargs):
        calls.append((url, kwargs["json"]["params"]["cmd"]))
        return _fake_response({"result": {"body": "Hostname: leaf-01"}})

    with mock.patch("backend.runners.cisco_nxapi.requests.post", side_effect=_capture):
        results, err = cisco_nxapi.run_commands(
            "10.0.0.2", "u", "p", ["show version", "show interface"]
        )

    assert err is None
    assert results == ["Hostname: leaf-01", "Hostname: leaf-01"]
    assert [url for url, _ in calls] == ["https://10.0.0.2/ins"] * 2
    assert [cmd for _, cmd in calls] == ["show version", "show interface"]


def test_cisco_nxapi_returns_dict_body_when_json_response():
    from backend.runners import cisco_nxapi

    payload = {"result": {"body": {"hostname": "leaf-01"}}}
    with mock.patch("backend.runners.cisco_nxapi.requests.post", return_value=_fake_response(payload)):
        results, err = cisco_nxapi.run_commands("10.0.0.2", "u", "p", ["show version"])

    assert err is None
    assert results == [{"hostname": "leaf-01"}]


def test_cisco_nxapi_returns_partial_results_on_mid_command_error():
    """A failure on command N must keep the N-1 already-collected results."""
    from backend.runners import cisco_nxapi

    side_effects = [
        _fake_response({"result": {"body": "ok"}}),
        _fake_response({"error": {"message": "command not supported"}}),
    ]
    with mock.patch("backend.runners.cisco_nxapi.requests.post", side_effect=side_effects):
        results, err = cisco_nxapi.run_commands("10.0.0.2", "u", "p", ["a", "b"])

    assert results == ["ok"]
    assert err == "command not supported"


def test_cisco_nxapi_sets_jsonrpc_content_type_header():
    from backend.runners import cisco_nxapi

    captured: dict = {}

    def _capture(url, **kwargs):
        captured["headers"] = kwargs.get("headers")
        return _fake_response({"result": {"body": ""}})

    with mock.patch("backend.runners.cisco_nxapi.requests.post", side_effect=_capture):
        cisco_nxapi.run_commands("10.0.0.2", "u", "p", ["show version"])

    assert captured["headers"] == {"Content-Type": "application/json-rpc"}


# --------------------------------------------------------------------------- #
# SSH runner                                                                  #
# --------------------------------------------------------------------------- #


def _ssh_client_mock(stdout_text: str = "", stderr_text: str = "") -> mock.MagicMock:
    client = mock.MagicMock()
    stdout = mock.MagicMock()
    stderr = mock.MagicMock()
    stdout.read.return_value = stdout_text.encode("utf-8")
    stderr.read.return_value = stderr_text.encode("utf-8")
    client.exec_command.return_value = (mock.MagicMock(), stdout, stderr)
    return client


def test_ssh_runner_run_command_basic():
    from backend.runners import ssh_runner

    if ssh_runner.paramiko is None:
        pytest.skip("paramiko not installed")

    fake = _ssh_client_mock(stdout_text="System uptime: 14 days\n")
    with mock.patch.object(ssh_runner.paramiko, "SSHClient", return_value=fake):
        out, err = ssh_runner.run_command("10.0.0.3", "u", "p", "show version")

    assert err is None
    assert out == "System uptime: 14 days"
    fake.connect.assert_called_once()
    kwargs = fake.connect.call_args.kwargs
    assert kwargs["username"] == "u"
    assert kwargs["password"] == "p"
    assert kwargs["allow_agent"] is False
    assert kwargs["look_for_keys"] is False


def test_ssh_runner_run_command_returns_stderr_when_no_stdout():
    from backend.runners import ssh_runner

    if ssh_runner.paramiko is None:
        pytest.skip("paramiko not installed")

    fake = _ssh_client_mock(stdout_text="", stderr_text="permission denied")
    with mock.patch.object(ssh_runner.paramiko, "SSHClient", return_value=fake):
        out, err = ssh_runner.run_command("10.0.0.3", "u", "p", "show version")

    assert out is None
    assert err == "permission denied"


def test_ssh_runner_run_commands_aggregates_outputs():
    from backend.runners import ssh_runner

    if ssh_runner.paramiko is None:
        pytest.skip("paramiko not installed")

    fake = _ssh_client_mock(stdout_text="ok")
    with mock.patch.object(ssh_runner.paramiko, "SSHClient", return_value=fake):
        results, err = ssh_runner.run_commands("10.0.0.3", "u", "p", ["a", "b", "c"])

    assert err is None
    assert results == ["ok", "ok", "ok"]


def test_ssh_runner_run_commands_short_circuits_on_error():
    from backend.runners import ssh_runner

    if ssh_runner.paramiko is None:
        pytest.skip("paramiko not installed")

    bad = _ssh_client_mock(stdout_text="", stderr_text="boom")
    with mock.patch.object(ssh_runner.paramiko, "SSHClient", return_value=bad):
        results, err = ssh_runner.run_commands("10.0.0.3", "u", "p", ["a", "b"])

    assert err == "boom"
    assert results == []


# --------------------------------------------------------------------------- #
# High-level orchestrator (runner.run_device_commands)                        #
# --------------------------------------------------------------------------- #


def test_run_device_commands_missing_ip_returns_error():
    from backend.runners.runner import run_device_commands

    out = run_device_commands({}, "secret", mock.MagicMock())
    assert out["error"] == "missing ip"
    assert out["commands"] == []


def test_run_device_commands_missing_credential_returns_error():
    from backend.runners.runner import run_device_commands

    cred_store = mock.MagicMock()
    cred_store.get_credential.return_value = None
    out = run_device_commands(
        {"ip": "10.0.0.1", "credential": "missing-cred"},
        "secret",
        cred_store,
    )
    assert "no credential" in out["error"]
    cred_store.get_credential.assert_called_once_with("missing-cred", "secret")


def test_run_device_commands_resolves_username_password_credential():
    """Pin the (username, password) extraction path used by API + SSH runners."""
    from backend.runners.runner import _get_credentials

    cred_store = mock.MagicMock()
    cred_store.get_credential.return_value = {
        "method": "ssh",
        "username": "admin",
        "password": "p4ss",
    }
    user, pwd = _get_credentials("creds", "secret", cred_store)
    assert (user, pwd) == ("admin", "p4ss")


def test_run_device_commands_resolves_api_key_credential():
    """API-key credentials surface as ('', api_key) — locked-in shape."""
    from backend.runners.runner import _get_credentials

    cred_store = mock.MagicMock()
    cred_store.get_credential.return_value = {"method": "api_key", "api_key": "tok-123"}
    user, pwd = _get_credentials("k", "s", cred_store)
    assert (user, pwd) == ("", "tok-123")


def test_hostname_extractor_walks_nested_dicts():
    from backend.runners.runner import _hostname_from_api_output

    nested = {"output": {"meta": {"hostname": "leaf-99"}}}
    assert _hostname_from_api_output(nested) == "leaf-99"
    assert _hostname_from_api_output([{"hostname": "spine-1"}]) == "spine-1"
    assert _hostname_from_api_output("not a dict") == ""
