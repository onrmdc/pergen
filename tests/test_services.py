"""
TDD tests for the service layer (phase 8).

The service layer composes repositories (phase 5), runners (phase 6),
and the parser engine (phase 7) into the use-case-shaped APIs that
phase-9 routes will consume.

Five services are introduced:

* ``InventoryService``   — wraps ``InventoryRepository``.
* ``CredentialService``  — wraps ``CredentialRepository`` with
                           ``InputSanitizer`` name validation.
* ``NotepadService``     — wraps ``NotepadRepository``.
* ``ReportService``      — wraps ``ReportRepository``.
* ``DeviceService``      — orchestrates credential lookup → runner
                           → parser for one device.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


# ===================================================================== #
#                          InventoryService
# ===================================================================== #
def test_inventory_service_lists_fabrics_via_repo():
    from backend.services.inventory_service import InventoryService

    repo = MagicMock()
    repo.fabrics.return_value = ["F1", "F2"]
    svc = InventoryService(inventory_repo=repo)
    assert svc.fabrics() == ["F1", "F2"]
    repo.fabrics.assert_called_once()


def test_inventory_service_devices_passes_filters():
    from backend.services.inventory_service import InventoryService

    repo = MagicMock()
    repo.devices.return_value = [{"hostname": "leaf-1"}]
    svc = InventoryService(inventory_repo=repo)
    out = svc.devices(fabric="F1", site="Mars", role="Leaf", hall="h1")
    assert out == [{"hostname": "leaf-1"}]
    repo.devices.assert_called_once_with(
        fabric="F1", site="Mars", role="Leaf", hall="h1"
    )


def test_inventory_service_devices_by_tag_lowercases_internally():
    from backend.services.inventory_service import InventoryService

    repo = MagicMock()
    repo.devices_by_tag.return_value = []
    svc = InventoryService(inventory_repo=repo)
    svc.devices_by_tag("PROD")
    repo.devices_by_tag.assert_called_once_with(tag="PROD")


# ===================================================================== #
#                         CredentialService
# ===================================================================== #
def test_credential_service_list_delegates():
    from backend.services.credential_service import CredentialService

    repo = MagicMock()
    repo.list.return_value = [{"name": "x", "method": "basic"}]
    svc = CredentialService(repo)
    assert svc.list() == [{"name": "x", "method": "basic"}]


def test_credential_service_set_validates_name():
    """Bogus names (with shell metacharacters / null bytes) must be
    rejected by ``InputSanitizer.sanitize_credential_name`` before the
    repo is touched."""
    from backend.services.credential_service import CredentialService

    repo = MagicMock()
    svc = CredentialService(repo)
    with pytest.raises(ValueError):
        svc.set("bad name; rm -rf /", method="basic", username="u", password="p")
    repo.set.assert_not_called()


def test_credential_service_set_passes_through_for_valid_name():
    from backend.services.credential_service import CredentialService

    repo = MagicMock()
    svc = CredentialService(repo)
    svc.set("good_name", method="basic", username="u", password="p")
    repo.set.assert_called_once_with(
        "good_name", method="basic", api_key=None, username="u", password="p"
    )


def test_credential_service_get_returns_repo_payload():
    from backend.services.credential_service import CredentialService

    repo = MagicMock()
    repo.get.return_value = {"name": "x", "method": "basic", "username": "u", "password": "p"}
    svc = CredentialService(repo)
    assert svc.get("x") == {"name": "x", "method": "basic", "username": "u", "password": "p"}


def test_credential_service_delete_returns_repo_value():
    from backend.services.credential_service import CredentialService

    repo = MagicMock()
    repo.delete.return_value = True
    svc = CredentialService(repo)
    assert svc.delete("x") is True


# ===================================================================== #
#                          NotepadService
# ===================================================================== #
def test_notepad_service_get_delegates():
    from backend.services.notepad_service import NotepadService

    repo = MagicMock()
    repo.load.return_value = {"content": "hi", "line_editors": ["a"]}
    svc = NotepadService(repo)
    assert svc.get() == {"content": "hi", "line_editors": ["a"]}


def test_notepad_service_update_delegates():
    from backend.services.notepad_service import NotepadService

    repo = MagicMock()
    repo.update.return_value = {"content": "x", "line_editors": ["u"]}
    svc = NotepadService(repo)
    out = svc.update("x", "u")
    assert out == {"content": "x", "line_editors": ["u"]}
    repo.update.assert_called_once_with("x", "u")


# ===================================================================== #
#                           ReportService
# ===================================================================== #
def test_report_service_save_delegates():
    from backend.services.report_service import ReportService

    repo = MagicMock()
    svc = ReportService(repo)
    svc.save(
        run_id="r1",
        name="n",
        created_at="t",
        devices=[],
        device_results=[],
    )
    repo.save.assert_called_once()


def test_report_service_load_returns_repo_payload():
    from backend.services.report_service import ReportService

    repo = MagicMock()
    repo.load.return_value = {"run_id": "r1"}
    svc = ReportService(repo)
    assert svc.load("r1") == {"run_id": "r1"}


def test_report_service_delete_and_list_delegate():
    from backend.services.report_service import ReportService

    repo = MagicMock()
    repo.delete.return_value = True
    repo.list.return_value = [{"run_id": "r1"}]
    svc = ReportService(repo)
    assert svc.delete("r1") is True
    assert svc.list() == [{"run_id": "r1"}]


# ===================================================================== #
#                           DeviceService
# ===================================================================== #
def test_device_service_runs_commands_and_parses():
    """End-to-end orchestration with mocked deps."""
    from backend.services.device_service import DeviceService

    cred_svc = MagicMock()
    cred_svc.get.return_value = {
        "name": "c1",
        "method": "basic",
        "username": "admin",
        "password": "pw",
    }

    runner = MagicMock()
    runner.run_commands.return_value = ([{"version": "4.30"}], None)
    runner_factory = MagicMock()
    runner_factory.get_runner.return_value = runner

    parser_engine = MagicMock()
    parser_engine.parse.return_value = {"version": "4.30"}

    svc = DeviceService(
        credential_service=cred_svc,
        runner_factory=runner_factory,
        parser_engine=parser_engine,
    )
    device = {
        "hostname": "leaf-1",
        "ip": "10.0.0.1",
        "vendor": "Arista",
        "model": "EOS",
        "credential": "c1",
    }
    result = svc.run(
        device,
        method="api",
        commands=[("arista_show_version", "show version")],
    )
    assert result["hostname"] == "leaf-1"
    assert result["ip"] == "10.0.0.1"
    assert result["vendor"] == "Arista"
    assert result["error"] is None
    assert len(result["commands"]) == 1
    cmd_result = result["commands"][0]
    assert cmd_result["command_id"] == "arista_show_version"
    assert cmd_result["raw"] == {"version": "4.30"}
    assert cmd_result["parsed"] == {"version": "4.30"}
    runner_factory.get_runner.assert_called_once_with(
        vendor="Arista", model="EOS", method="api"
    )
    runner.run_commands.assert_called_once()


def test_device_service_returns_error_when_no_credential():
    from backend.services.device_service import DeviceService

    cred_svc = MagicMock()
    cred_svc.get.return_value = None
    svc = DeviceService(
        credential_service=cred_svc,
        runner_factory=MagicMock(),
        parser_engine=MagicMock(),
    )
    result = svc.run(
        device={"hostname": "leaf-1", "ip": "10.0.0.1", "vendor": "Arista", "credential": "c1"},
        method="api",
        commands=[("a", "show version")],
    )
    assert result["error"] is not None
    assert "credential" in result["error"].lower()
    assert result["commands"] == []


def test_device_service_returns_error_when_runner_unsupported():
    from backend.services.device_service import DeviceService

    cred_svc = MagicMock()
    cred_svc.get.return_value = {
        "method": "basic", "username": "u", "password": "p", "name": "c1",
    }
    runner_factory = MagicMock()
    runner_factory.get_runner.side_effect = ValueError("unsupported")
    svc = DeviceService(
        credential_service=cred_svc,
        runner_factory=runner_factory,
        parser_engine=MagicMock(),
    )
    result = svc.run(
        device={"hostname": "h", "ip": "10.0.0.1", "vendor": "Unknown", "credential": "c1"},
        method="api",
        commands=[("a", "show version")],
    )
    assert "unsupported" in (result["error"] or "")
    assert result["commands"] == []


def test_device_service_returns_runner_error_on_failure():
    from backend.services.device_service import DeviceService

    cred_svc = MagicMock()
    cred_svc.get.return_value = {
        "method": "basic", "username": "u", "password": "p", "name": "c1",
    }
    runner = MagicMock()
    runner.run_commands.return_value = ([], "connection refused")
    runner_factory = MagicMock()
    runner_factory.get_runner.return_value = runner
    svc = DeviceService(
        credential_service=cred_svc,
        runner_factory=runner_factory,
        parser_engine=MagicMock(),
    )
    result = svc.run(
        device={"hostname": "h", "ip": "10.0.0.1", "vendor": "Arista", "credential": "c1"},
        method="api",
        commands=[("a", "show version")],
    )
    assert result["error"] == "connection refused"
    assert result["commands"] == []


def test_device_service_uses_api_key_credential():
    """When the credential method is ``api_key``, password becomes the
    api key value (matches legacy ``runner.py`` behaviour)."""
    from backend.services.device_service import DeviceService

    cred_svc = MagicMock()
    cred_svc.get.return_value = {
        "method": "api_key", "api_key": "TOKEN", "name": "c1",
    }
    runner = MagicMock()
    runner.run_commands.return_value = ([{"v": 1}], None)
    runner_factory = MagicMock()
    runner_factory.get_runner.return_value = runner
    parser_engine = MagicMock()
    parser_engine.parse.return_value = {}
    svc = DeviceService(
        credential_service=cred_svc,
        runner_factory=runner_factory,
        parser_engine=parser_engine,
    )
    svc.run(
        device={"hostname": "h", "ip": "10.0.0.1", "vendor": "Arista", "credential": "c1"},
        method="api",
        commands=[("a", "show version")],
    )
    args, kwargs = runner.run_commands.call_args
    assert args[1] == ""           # username blank for api_key
    assert args[2] == "TOKEN"      # password slot carries the token
