"""
``BaseRunner`` — abstract contract for all device-execution runners.

Every concrete runner (Arista eAPI, Cisco NX-API, generic SSH, …)
implements ``run_commands`` returning a uniform tuple
``(results, error_message_or_none)``.  This lets the service layer
treat all transports uniformly.

Stateless requirement
---------------------
Runners must be **stateless** — credentials are passed per call, never
stored on the instance.  This allows the ``RunnerFactory`` to keep one
shared singleton per (vendor, model, method) tuple safely across
threads.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseRunner(ABC):
    """Abstract base class for device runners."""

    @abstractmethod
    def run_commands(
        self,
        ip: str,
        username: str,
        password: str,
        commands: list[str],
        timeout: int = 30,
    ) -> tuple[list[Any], str | None]:
        """
        Execute ``commands`` on the device at ``ip`` and return
        ``(results, error_message_or_none)``.

        Inputs
        ------
        ip : device management address (caller is responsible for
            sanitisation via ``InputSanitizer.sanitize_ip``).
        username, password : credentials resolved from the credential
            repository.
        commands : list of read-only commands (caller is responsible for
            ``CommandValidator.validate`` on each entry).
        timeout : per-call connection / read timeout in seconds.

        Outputs
        -------
        Tuple of ``(results, error)`` where ``results`` is a list whose
        elements may be ``str``, ``dict``, or other JSON-serialisable
        values depending on the transport, and ``error`` is None on
        success or a short error string on failure.

        Security
        --------
        * Self-signed device certs are accepted (network-device
          convention); external public APIs MUST verify TLS.
        * Runners MUST NOT log the password in cleartext.
        * Runners MUST NOT raise — every failure path returns an error
          string so the orchestrator can keep iterating over devices.
        """
        raise NotImplementedError
