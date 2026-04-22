"""
``CiscoNxapiRunner`` — OOD wrapper around ``backend.runners.cisco_nxapi``.
"""
from __future__ import annotations

from typing import Any

from backend.runners import cisco_nxapi
from backend.runners.base_runner import BaseRunner


class CiscoNxapiRunner(BaseRunner):
    """Runs commands on Cisco NX-OS devices via NX-API (HTTPS POST)."""

    def run_commands(
        self,
        ip: str,
        username: str,
        password: str,
        commands: list[str],
        timeout: int = 30,
    ) -> tuple[list[Any], str | None]:
        """Delegate to ``backend.runners.cisco_nxapi.run_commands``."""
        return cisco_nxapi.run_commands(ip, username, password, commands, timeout=timeout)
