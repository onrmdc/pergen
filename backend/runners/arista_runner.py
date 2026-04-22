"""
``AristaEapiRunner`` — OOD wrapper around ``backend.runners.arista_eapi``.

The class form makes the runner injectable into the service layer and
lets the ``RunnerFactory`` cache a single shared instance.  Behaviour
is *exactly* delegated to the existing module-level ``run_commands``
helper — no rewrites, no behavioural drift.
"""
from __future__ import annotations

from typing import Any

from backend.runners import arista_eapi
from backend.runners.base_runner import BaseRunner


class AristaEapiRunner(BaseRunner):
    """Runs commands on Arista EOS devices via eAPI (HTTPS POST)."""

    def run_commands(
        self,
        ip: str,
        username: str,
        password: str,
        commands: list[str],
        timeout: int = 30,
    ) -> tuple[list[Any], str | None]:
        """Delegate to ``backend.runners.arista_eapi.run_commands``."""
        return arista_eapi.run_commands(ip, username, password, commands, timeout=timeout)
