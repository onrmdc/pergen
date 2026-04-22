"""
``SshRunner`` — OOD wrapper around ``backend.runners.ssh_runner``.

The module-level helper is kept under its existing name so
``backend/app.py`` continues to work; this class is the new injection
point for the service layer.  We use the suffix ``_class`` for the
wrapper file to avoid clashing with the existing ``ssh_runner.py``
module that already lives in this package.
"""
from __future__ import annotations

from typing import Any

from backend.runners import ssh_runner
from backend.runners.base_runner import BaseRunner


class SshRunner(BaseRunner):
    """Runs commands on devices via SSH (Paramiko)."""

    def run_commands(
        self,
        ip: str,
        username: str,
        password: str,
        commands: list[str],
        timeout: int = 30,
    ) -> tuple[list[Any], str | None]:
        """Delegate to ``backend.runners.ssh_runner.run_commands``."""
        return ssh_runner.run_commands(ip, username, password, commands, timeout=timeout)
