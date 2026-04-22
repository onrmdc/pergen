"""
Coverage push for ``backend/runners/runner.py`` dispatch logic.

These tests mock the network-touching modules (arista_eapi, cisco_nxapi,
ssh_runner) so we exercise the orchestration branches in
``run_device_commands`` without spinning up real devices. Focus areas:

* api / ssh / unknown-method dispatch
* command_id_filter / command_id_exact filtering
* per-command CommandValidator gate
* hostname extraction from API responses
* parser application

This file is a pure dispatch test — it intentionally does not test
parsing or vendor-specific request shapes (those live in their own
test files).

Test isolation note: the ``conftest.flask_app`` fixture pops
``backend.config.commands_loader`` between tests, which invalidates
patches against the ORIGINAL module path because ``runner.py`` binds
``cmd_loader`` at import time. Each test below patches the symbol
**inside ``backend.runners.runner``** (the module-local re-export) so
the mock is observed regardless of conftest's module gymnastics.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def _basic_creds_module():
    """Return a mock cred-store module that always resolves to (u, p)."""
    creds = MagicMock()
    creds.get_credential.return_value = {
        "method": "basic",
        "username": "u",
        "password": "p",
    }
    return creds


# --------------------------------------------------------------------------- #
# API dispatch                                                                 #
# --------------------------------------------------------------------------- #


def test_run_device_commands_dispatches_to_arista_eapi_for_command_api_path():
    from backend.runners.runner import run_device_commands

    cmd_cfg = [
        {
            "id": "show-version",
            "method": "api",
            "api": {"path": "/command-api", "commands": ["show version"]},
        }
    ]
    creds = _basic_creds_module()
    with patch(
        "backend.runners.runner.cmd_loader.get_commands_for_device", return_value=cmd_cfg
    ), patch(
        "backend.runners.arista_eapi.run_commands",
        return_value=([{"version": "4.30"}], None),
    ) as m_eapi, patch(
        "backend.runners.runner.cmd_loader.get_parser", return_value=None
    ):
        out = run_device_commands(
            {"ip": "10.0.0.1", "vendor": "Arista", "model": "EOS", "credential": "test"},
            "k",
            creds,
        )
    assert out["error"] is None
    assert m_eapi.called
    assert out["commands"][0]["raw"] == {"version": "4.30"}


def test_run_device_commands_dispatches_to_cisco_nxapi_for_ins_path():
    from backend.runners.runner import run_device_commands

    cmd_cfg = [
        {
            "id": "show-version",
            "method": "api",
            "api": {"path": "/ins", "commands": ["show version"]},
        }
    ]
    creds = _basic_creds_module()
    with patch(
        "backend.runners.runner.cmd_loader.get_commands_for_device", return_value=cmd_cfg
    ), patch(
        "backend.runners.cisco_nxapi.run_commands",
        return_value=(["Hostname: nx-leaf-01"], None),
    ) as m_nx, patch(
        "backend.runners.runner.cmd_loader.get_parser", return_value=None
    ):
        out = run_device_commands(
            {"ip": "10.0.0.2", "vendor": "Cisco", "model": "NX-OS", "credential": "test"},
            "k",
            creds,
        )
    assert out["error"] is None
    assert m_nx.called
    assert "Hostname" in out["commands"][0]["raw"]


def test_run_device_commands_records_unknown_api_path_error():
    from backend.runners.runner import run_device_commands

    cmd_cfg = [
        {
            "id": "weird-cmd",
            "method": "api",
            "api": {"path": "/some/other/path", "commands": ["x"]},
        }
    ]
    creds = _basic_creds_module()
    with patch(
        "backend.runners.runner.cmd_loader.get_commands_for_device", return_value=cmd_cfg
    ):
        out = run_device_commands(
            {"ip": "10.0.0.1", "vendor": "X", "model": "Y", "credential": "test"},
            "k",
            creds,
        )
    assert "unknown api path" in out["commands"][0]["error"]


def test_run_device_commands_records_no_commands_in_api_spec():
    from backend.runners.runner import run_device_commands

    cmd_cfg = [
        {"id": "empty", "method": "api", "api": {"path": "/command-api", "commands": []}}
    ]
    creds = _basic_creds_module()
    with patch(
        "backend.runners.runner.cmd_loader.get_commands_for_device", return_value=cmd_cfg
    ):
        out = run_device_commands(
            {"ip": "10.0.0.1", "vendor": "Arista", "model": "EOS", "credential": "test"},
            "k",
            creds,
        )
    assert out["commands"][0]["error"] == "no commands in api spec"


# --------------------------------------------------------------------------- #
# SSH dispatch + CommandValidator                                              #
# --------------------------------------------------------------------------- #


def test_run_device_commands_dispatches_to_ssh_runner():
    from backend.runners.runner import run_device_commands

    cmd_cfg = [
        {
            "id": "show-uptime",
            "method": "ssh",
            "ssh": {"command": "show version"},
        }
    ]
    creds = _basic_creds_module()
    with patch(
        "backend.runners.runner.cmd_loader.get_commands_for_device", return_value=cmd_cfg
    ), patch(
        "backend.runners.ssh_runner.run_command",
        return_value=("Uptime: 14 days", None),
    ) as m_ssh, patch(
        "backend.runners.runner.cmd_loader.get_parser", return_value=None
    ):
        out = run_device_commands(
            {"ip": "10.0.0.3", "vendor": "X", "model": "Y", "credential": "test"},
            "k",
            creds,
        )
    assert out["error"] is None
    assert m_ssh.called
    assert "14 days" in out["commands"][0]["raw"]


def test_run_device_commands_ssh_rejects_dangerous_command_via_validator():
    """Phase 13 defence-in-depth: even YAML-supplied commands go through
    CommandValidator. A `configure terminal` cmd from a compromised YAML
    must be refused.
    """
    from backend.runners.runner import run_device_commands

    cmd_cfg = [
        {"id": "evil", "method": "ssh", "ssh": {"command": "configure terminal"}}
    ]
    creds = _basic_creds_module()
    with patch(
        "backend.runners.runner.cmd_loader.get_commands_for_device", return_value=cmd_cfg
    ):
        out = run_device_commands(
            {"ip": "10.0.0.3", "vendor": "X", "model": "Y", "credential": "test"},
            "k",
            creds,
        )
    assert "rejected by CommandValidator" in out["commands"][0]["error"]


def test_run_device_commands_records_no_command_in_ssh_spec():
    from backend.runners.runner import run_device_commands

    cmd_cfg = [{"id": "empty-ssh", "method": "ssh", "ssh": {"command": ""}}]
    creds = _basic_creds_module()
    with patch(
        "backend.runners.runner.cmd_loader.get_commands_for_device", return_value=cmd_cfg
    ):
        out = run_device_commands(
            {"ip": "10.0.0.3", "vendor": "X", "model": "Y", "credential": "test"},
            "k",
            creds,
        )
    assert out["commands"][0]["error"] == "no command in ssh spec"


def test_run_device_commands_unknown_method_recorded():
    from backend.runners.runner import run_device_commands

    cmd_cfg = [{"id": "no-method", "method": "telnet"}]
    creds = _basic_creds_module()
    with patch(
        "backend.runners.runner.cmd_loader.get_commands_for_device", return_value=cmd_cfg
    ):
        out = run_device_commands(
            {"ip": "10.0.0.3", "vendor": "X", "model": "Y", "credential": "test"},
            "k",
            creds,
        )
    assert "unknown method" in out["commands"][0]["error"]


# --------------------------------------------------------------------------- #
# Filter/exact controls                                                        #
# --------------------------------------------------------------------------- #


def test_run_device_commands_command_id_exact_match_filters_to_single():
    from backend.runners.runner import run_device_commands

    cmd_cfg = [
        {"id": "alpha", "method": "ssh", "ssh": {"command": "show v"}},
        {"id": "beta", "method": "ssh", "ssh": {"command": "show i"}},
    ]
    creds = _basic_creds_module()
    with patch(
        "backend.runners.runner.cmd_loader.get_commands_for_device", return_value=cmd_cfg
    ), patch(
        "backend.runners.ssh_runner.run_command", return_value=("ok", None)
    ), patch(
        "backend.runners.runner.cmd_loader.get_parser", return_value=None
    ):
        out = run_device_commands(
            {"ip": "10.0.0.3", "vendor": "X", "model": "Y", "credential": "test"},
            "k",
            creds,
            command_id_exact="alpha",
        )
    assert len(out["commands"]) == 1
    assert out["commands"][0]["command_id"] == "alpha"


def test_run_device_commands_command_id_filter_matches_substring():
    from backend.runners.runner import run_device_commands

    cmd_cfg = [
        {"id": "show-version", "method": "ssh", "ssh": {"command": "show v"}},
        {"id": "show-uptime", "method": "ssh", "ssh": {"command": "show u"}},
        {"id": "dir", "method": "ssh", "ssh": {"command": "dir"}},
    ]
    creds = _basic_creds_module()
    with patch(
        "backend.runners.runner.cmd_loader.get_commands_for_device", return_value=cmd_cfg
    ), patch(
        "backend.runners.ssh_runner.run_command", return_value=("ok", None)
    ), patch(
        "backend.runners.runner.cmd_loader.get_parser", return_value=None
    ):
        out = run_device_commands(
            {"ip": "10.0.0.3", "vendor": "X", "model": "Y", "credential": "test"},
            "k",
            creds,
            command_id_filter="show",
        )
    cids = [c["command_id"] for c in out["commands"]]
    assert sorted(cids) == ["show-uptime", "show-version"]


def test_run_device_commands_command_id_exact_no_match_returns_empty():
    from backend.runners.runner import run_device_commands

    cmd_cfg = [{"id": "alpha", "method": "ssh", "ssh": {"command": "show v"}}]
    creds = _basic_creds_module()
    with patch(
        "backend.runners.runner.cmd_loader.get_commands_for_device", return_value=cmd_cfg
    ):
        out = run_device_commands(
            {"ip": "10.0.0.3", "vendor": "X", "model": "Y", "credential": "test"},
            "k",
            creds,
            command_id_exact="zeta",
        )
    assert out["commands"] == []


# --------------------------------------------------------------------------- #
# Hostname extraction + parser application                                     #
# --------------------------------------------------------------------------- #


def test_run_device_commands_extracts_hostname_from_api_response():
    from backend.runners.runner import run_device_commands

    cmd_cfg = [
        {
            "id": "show-version",
            "method": "api",
            "api": {"path": "/command-api", "commands": ["show version"]},
        }
    ]
    creds = _basic_creds_module()
    with patch(
        "backend.runners.runner.cmd_loader.get_commands_for_device", return_value=cmd_cfg
    ), patch(
        "backend.runners.arista_eapi.run_commands",
        return_value=([{"hostname": "leaf-eapi-01", "version": "4.30"}], None),
    ), patch(
        "backend.runners.runner.cmd_loader.get_parser", return_value=None
    ):
        out = run_device_commands(
            {"ip": "10.0.0.1", "vendor": "Arista", "model": "EOS", "credential": "test"},
            "k",
            creds,
        )
    assert out["hostname"] == "leaf-eapi-01"


def test_run_device_commands_applies_parser_when_configured():
    from backend.runners.runner import run_device_commands

    cmd_cfg = [
        {
            "id": "show-version",
            "method": "api",
            "api": {"path": "/command-api", "commands": ["show version"]},
        }
    ]
    parser_cfg = {"some": "parser"}
    creds = _basic_creds_module()
    with patch(
        "backend.runners.runner.cmd_loader.get_commands_for_device", return_value=cmd_cfg
    ), patch(
        "backend.runners.arista_eapi.run_commands",
        return_value=([{"version": "4.30"}], None),
    ), patch(
        "backend.runners.runner.cmd_loader.get_parser", return_value=parser_cfg
    ), patch(
        "backend.parse_output.parse_output",
        return_value={"Version": "4.30"},
    ) as m_parse:
        out = run_device_commands(
            {"ip": "10.0.0.1", "vendor": "Arista", "model": "EOS", "credential": "test"},
            "k",
            creds,
        )
    assert m_parse.called
    assert out["parsed_flat"] == {"Version": "4.30"}
    assert out["commands"][0]["parsed"] == {"Version": "4.30"}
