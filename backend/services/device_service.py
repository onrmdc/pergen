"""
``DeviceService`` — orchestration of credential lookup → runner →
parser for a single device.

This is the central service of phase 8 — it composes every previous
phase's deliverable:

* ``CredentialService`` (phase 8 / 5) for credential resolution.
* ``RunnerFactory`` (phase 6) for the right transport.
* ``ParserEngine`` (phase 7) for raw → structured field conversion.

The legacy entry point in ``backend/runners/runner.py`` continues to
work; ``DeviceService`` is the OOD replacement that phase-9 routes
will adopt.

Returned shape (matches legacy expectations)
--------------------------------------------
``{
    "hostname": str,
    "ip": str,
    "vendor": str,
    "credential": str,
    "error": str | None,
    "commands": [
        {"command_id": str, "command": str, "raw": Any, "parsed": dict}
    ],
}``
"""
from __future__ import annotations

import logging
from typing import Any

from backend.parsers import ParserEngine
from backend.runners import RunnerFactory
from backend.services.credential_service import CredentialService

_log = logging.getLogger("app.services.device")


class DeviceService:
    """Run commands on a device and parse the results."""

    def __init__(
        self,
        credential_service: CredentialService,
        runner_factory: RunnerFactory,
        parser_engine: ParserEngine,
    ) -> None:
        self._creds = credential_service
        self._runners = runner_factory
        self._parsers = parser_engine

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    def run(
        self,
        device: dict,
        *,
        method: str,
        commands: list[tuple[str, str]],
        timeout: int = 30,
    ) -> dict[str, Any]:
        """
        Resolve credentials, pick a runner, execute *commands*, parse.

        Inputs
        ------
        device : dict with at least ``hostname``, ``ip``, ``vendor``,
            ``credential``.  ``model`` is optional but recommended.
        method : ``"api"`` or ``"ssh"``.
        commands : ``[(command_id, command_string), …]``.  ``command_id``
            is the parser-registry key; ``command_string`` is the raw
            CLI/eAPI command.
        timeout : per-call connection / read timeout in seconds.

        Outputs
        -------
        Result dict (see module docstring).  ``error`` is set when the
        device cannot be reached, the credential is missing, or the
        runner refuses the (vendor, method) pair.

        Security
        --------
        * Credential payload is NEVER returned in the result.
        * On any failure the result still contains the device metadata
          so the caller can keep the per-device map intact.
        """
        hostname = (device.get("hostname") or "").strip()
        ip = (device.get("ip") or "").strip()
        vendor = (device.get("vendor") or "").strip()
        model = (device.get("model") or "").strip()
        cred_name = (device.get("credential") or "").strip()

        base = {
            "hostname": hostname,
            "ip": ip,
            "vendor": vendor,
            "credential": cred_name,
            "error": None,
            "commands": [],
        }

        cred = self._creds.get(cred_name) if cred_name else None
        if not cred:
            base["error"] = f"credential not found: {cred_name!r}"
            return base
        username, password = self._extract_username_password(cred)

        try:
            runner = self._runners.get_runner(vendor=vendor, model=model, method=method)
        except ValueError as exc:
            base["error"] = str(exc)
            return base

        cmd_strings = [c[1] for c in commands]
        results, err = runner.run_commands(ip, username, password, cmd_strings, timeout=timeout)
        if err:
            base["error"] = err
            return base

        parsed_commands: list[dict] = []
        for (cmd_id, cmd_str), raw in zip(commands, results, strict=False):
            parsed = self._parsers.parse(cmd_id, raw)
            parsed_commands.append(
                {
                    "command_id": cmd_id,
                    "command": cmd_str,
                    "raw": raw,
                    "parsed": parsed,
                }
            )
        base["commands"] = parsed_commands
        return base

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_username_password(cred: dict) -> tuple[str, str]:
        """Return ``(username, password)`` for the runner.

        For ``api_key`` credentials the username is blank and the
        password slot carries the token — matches the legacy
        ``runner.py:_get_credentials`` behaviour exactly.
        """
        if cred.get("method") == "api_key":
            return "", (cred.get("api_key") or "")
        return (cred.get("username") or ""), (cred.get("password") or "")
