"""
``RunnerFactory`` — thread-safe singleton cache for concrete runners.

The factory picks the right ``BaseRunner`` subclass for a
``(vendor, model, method)`` triple.  One instance per concrete class
is created on first request and reused for the lifetime of the
factory — runners are stateless, so sharing is safe.

Lookup precedence
-----------------
1. If ``method`` is ``"ssh"`` → ``SshRunner`` regardless of vendor.
2. If ``method`` is ``"api"``:
   * vendor ``"arista"`` → ``AristaEapiRunner``
   * vendor ``"cisco"`` → ``CiscoNxapiRunner``
3. Anything else → ``ValueError``.

The vendor / model / method strings are normalised to lowercase before
matching so inventory rows like ``ARISTA`` / ``arista`` / ``Arista`` all
resolve to the same runner.
"""
from __future__ import annotations

import threading
from typing import ClassVar

from backend.runners.arista_runner import AristaEapiRunner
from backend.runners.base_runner import BaseRunner
from backend.runners.cisco_runner import CiscoNxapiRunner
from backend.runners.ssh_runner_class import SshRunner


class RunnerFactory:
    """Singleton-cached factory of ``BaseRunner`` instances."""

    _ALLOWED_METHODS: ClassVar[frozenset[str]] = frozenset({"api", "ssh"})

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._instances: dict[str, BaseRunner] = {}

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    def get_runner(self, vendor: str, model: str, method: str) -> BaseRunner:
        """
        Resolve and return the runner for ``(vendor, model, method)``.

        Inputs
        ------
        vendor : ``"Arista"`` / ``"Cisco"`` / … (case-insensitive).
        model : ``"EOS"`` / ``"NX-OS"`` / … (currently unused for
            dispatch but kept in the signature for forward compatibility
            with future per-model runners).
        method : ``"api"`` or ``"ssh"`` (case-insensitive).

        Outputs
        -------
        Concrete ``BaseRunner`` instance.

        Security
        --------
        Unknown combinations raise ``ValueError`` rather than silently
        defaulting to a runner — the caller should surface that as a
        per-device error and keep iterating.
        """
        v = (vendor or "").strip().lower()
        m = (model or "").strip().lower()
        meth = (method or "").strip().lower()

        if meth not in self._ALLOWED_METHODS:
            raise ValueError(f"unsupported runner method: {method!r}")

        runner_cls = self._resolve(v, m, meth)
        key = runner_cls.__name__
        with self._lock:
            inst = self._instances.get(key)
            if inst is None:
                inst = runner_cls()
                self._instances[key] = inst
            return inst

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _resolve(self, vendor: str, model: str, method: str) -> type[BaseRunner]:
        if method == "ssh":
            return SshRunner
        if vendor == "arista":
            return AristaEapiRunner
        if vendor == "cisco":
            return CiscoNxapiRunner
        raise ValueError(f"unsupported runner combination: vendor={vendor!r} method={method!r}")
