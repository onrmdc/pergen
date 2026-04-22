"""
Pergen runners.

OOD layer (phase 6):
* ``BaseRunner`` ABC (``base_runner.py``)
* ``AristaEapiRunner`` (``arista_runner.py``)
* ``CiscoNxapiRunner`` (``cisco_runner.py``)
* ``SshRunner`` (``ssh_runner_class.py``)
* ``RunnerFactory`` (``factory.py``)

Legacy module-level helpers (``arista_eapi.run_commands``, …) and the
orchestration entry point ``run_device_commands`` are kept unchanged —
the OOD wrappers delegate to them.
"""
from backend.runners.arista_runner import AristaEapiRunner
from backend.runners.base_runner import BaseRunner
from backend.runners.cisco_runner import CiscoNxapiRunner
from backend.runners.factory import RunnerFactory
from backend.runners.runner import run_device_commands
from backend.runners.ssh_runner_class import SshRunner

__all__ = [
    "AristaEapiRunner",
    "BaseRunner",
    "CiscoNxapiRunner",
    "RunnerFactory",
    "SshRunner",
    "run_device_commands",
]
