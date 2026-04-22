"""
TDD tests for the OOD runner layer.

Contracts
---------
* ``BaseRunner`` is an ABC — instantiation raises ``TypeError``.
* Concrete runners (``AristaEapiRunner``, ``CiscoNxapiRunner``,
  ``SshRunner``) implement ``run_commands(ip, username, password,
  commands, timeout)`` returning ``(list[Any], str | None)`` and
  delegate to the existing module-level helpers.
* ``RunnerFactory.get_runner(vendor, model, method)`` returns the
  correct concrete class instance, caches it (singleton per kind),
  and raises ``ValueError`` for unknown combinations.
* Concurrent ``get_runner`` calls from multiple threads still resolve
  to a single shared instance (lock holds).
"""
from __future__ import annotations

import threading
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


def test_base_runner_cannot_be_instantiated():
    from backend.runners.base_runner import BaseRunner

    with pytest.raises(TypeError):
        BaseRunner()  # type: ignore[abstract]


def test_arista_runner_delegates_to_module():
    from backend.runners.arista_runner import AristaEapiRunner

    runner = AristaEapiRunner()
    with patch("backend.runners.arista_eapi.run_commands") as mock_call:
        mock_call.return_value = ([{"version": "4.30"}], None)
        results, err = runner.run_commands(
            "10.0.0.1", "admin", "pw", ["show version"], timeout=15
        )
    assert err is None
    assert results == [{"version": "4.30"}]
    mock_call.assert_called_once_with(
        "10.0.0.1", "admin", "pw", ["show version"], timeout=15
    )


def test_cisco_runner_delegates_to_module():
    from backend.runners.cisco_runner import CiscoNxapiRunner

    runner = CiscoNxapiRunner()
    with patch("backend.runners.cisco_nxapi.run_commands") as mock_call:
        mock_call.return_value = (["raw text"], None)
        results, err = runner.run_commands(
            "10.0.0.2", "u", "p", ["show vpc"], timeout=20
        )
    assert err is None
    assert results == ["raw text"]
    mock_call.assert_called_once_with(
        "10.0.0.2", "u", "p", ["show vpc"], timeout=20
    )


def test_ssh_runner_delegates_to_module():
    from backend.runners.ssh_runner_class import SshRunner

    runner = SshRunner()
    with patch("backend.runners.ssh_runner.run_commands") as mock_call:
        mock_call.return_value = (["uptime: 1d"], None)
        results, err = runner.run_commands(
            "10.0.0.3", "u", "p", ["show uptime"], timeout=10
        )
    assert err is None
    assert results == ["uptime: 1d"]
    mock_call.assert_called_once_with(
        "10.0.0.3", "u", "p", ["show uptime"], timeout=10
    )


def test_runner_returns_error_string_on_failure():
    from backend.runners.arista_runner import AristaEapiRunner

    runner = AristaEapiRunner()
    with patch("backend.runners.arista_eapi.run_commands") as mock_call:
        mock_call.return_value = ([], "connection refused")
        results, err = runner.run_commands("10.0.0.1", "u", "p", ["show version"])
    assert results == []
    assert err == "connection refused"


# ---------------------------------------------------------------- factory


def test_factory_returns_arista_for_arista_api():
    from backend.runners.arista_runner import AristaEapiRunner
    from backend.runners.factory import RunnerFactory

    factory = RunnerFactory()
    r = factory.get_runner(vendor="Arista", model="EOS", method="api")
    assert isinstance(r, AristaEapiRunner)


def test_factory_returns_cisco_for_cisco_api():
    from backend.runners.cisco_runner import CiscoNxapiRunner
    from backend.runners.factory import RunnerFactory

    factory = RunnerFactory()
    r = factory.get_runner(vendor="Cisco", model="NX-OS", method="api")
    assert isinstance(r, CiscoNxapiRunner)


def test_factory_returns_ssh_for_ssh_method():
    from backend.runners.factory import RunnerFactory
    from backend.runners.ssh_runner_class import SshRunner

    factory = RunnerFactory()
    r = factory.get_runner(vendor="Cisco", model="NX-OS", method="ssh")
    assert isinstance(r, SshRunner)


def test_factory_caches_instances():
    from backend.runners.factory import RunnerFactory

    factory = RunnerFactory()
    a1 = factory.get_runner("Arista", "EOS", "api")
    a2 = factory.get_runner("Arista", "EOS", "api")
    assert a1 is a2


def test_factory_unknown_vendor_raises():
    from backend.runners.factory import RunnerFactory

    factory = RunnerFactory()
    with pytest.raises(ValueError):
        factory.get_runner(vendor="Unknown", model="X", method="api")


def test_factory_unknown_method_raises():
    from backend.runners.factory import RunnerFactory

    factory = RunnerFactory()
    with pytest.raises(ValueError):
        factory.get_runner(vendor="Arista", model="EOS", method="bogus")


def test_factory_is_case_insensitive_on_vendor():
    """Inventory vendor strings vary in case (Arista / arista / ARISTA)."""
    from backend.runners.arista_runner import AristaEapiRunner
    from backend.runners.factory import RunnerFactory

    factory = RunnerFactory()
    r1 = factory.get_runner("ARISTA", "eos", "API")
    r2 = factory.get_runner("arista", "EOS", "api")
    assert isinstance(r1, AristaEapiRunner)
    assert r1 is r2


def test_factory_is_thread_safe():
    """Concurrent get_runner calls must converge on a single instance."""
    from backend.runners.factory import RunnerFactory

    factory = RunnerFactory()
    seen: list = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        seen.append(factory.get_runner("Arista", "EOS", "api"))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(seen) == 8
    first = seen[0]
    for r in seen[1:]:
        assert r is first
