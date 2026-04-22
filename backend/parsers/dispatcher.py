"""Vendor-routed parser dispatcher.

Replaces the giant ``if custom_parser == "..." elif ...`` ladder in the
legacy ``parse_output()`` with a small registry mapping each
``custom_parser`` string to its parser callable. Falls back to
``GenericFieldEngine`` when ``custom_parser`` is unset.

Phase 5 of the parse_output refactor — see
``docs/refactor/parse_output_split.md``. After this lands,
``backend.parse_output.parse_output`` becomes a one-line wrapper around
``Dispatcher().parse(...)``, and ``backend.parsers.engine.ParserEngine``
can drop its lazy trampoline in Phase 6.

Why a registry?
---------------
* Adding a new vendor parser is one map entry, not another ``elif``.
* Tests can register a fake parser without monkey-patching dispatch.
* The engine layer (Phase 6) can introspect registered command kinds.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.parsers.arista.cpu import _parse_arista_cpu
from backend.parsers.arista.disk import _parse_arista_disk
from backend.parsers.arista.interface_description import (
    _parse_arista_interface_description,
)
from backend.parsers.arista.interface_status import _parse_arista_interface_status
from backend.parsers.arista.isis import _parse_arista_isis_adjacency
from backend.parsers.arista.power import _parse_arista_power
from backend.parsers.arista.transceiver import _parse_arista_transceiver
from backend.parsers.arista.uptime import _parse_arista_uptime
from backend.parsers.cisco_nxos.interface_description import (
    _parse_cisco_interface_description,
)
from backend.parsers.cisco_nxos.interface_detailed import _parse_cisco_interface_detailed
from backend.parsers.cisco_nxos.interface_mtu import _parse_cisco_interface_show_mtu
from backend.parsers.cisco_nxos.interface_status import _parse_cisco_interface_status
from backend.parsers.cisco_nxos.isis_brief import _parse_cisco_isis_interface_brief
from backend.parsers.cisco_nxos.power import _parse_cisco_power
from backend.parsers.cisco_nxos.system_uptime import _parse_cisco_system_uptime
from backend.parsers.cisco_nxos.transceiver import _parse_cisco_nxos_transceiver
from backend.parsers.generic.field_engine import GenericFieldEngine

# Type of every registered ``custom_parser`` callable: takes the raw output,
# returns the parsed dict.
CustomParser = Callable[[Any], dict[str, Any]]

# The canonical registry. Mirrors the legacy ``parse_output()`` if/elif
# ladder. Each key is the ``custom_parser`` value from
# ``backend/config/parsers.yaml``.
_DEFAULT_REGISTRY: dict[str, CustomParser] = {
    "arista_cpu": _parse_arista_cpu,
    "arista_disk": _parse_arista_disk,
    "arista_interface_description": _parse_arista_interface_description,
    "arista_interface_status": _parse_arista_interface_status,
    "arista_isis_adjacency": _parse_arista_isis_adjacency,
    "arista_power": _parse_arista_power,
    "arista_transceiver": _parse_arista_transceiver,
    "arista_uptime": _parse_arista_uptime,
    "cisco_interface_description": _parse_cisco_interface_description,
    "cisco_interface_detailed": _parse_cisco_interface_detailed,
    "cisco_interface_show_mtu": _parse_cisco_interface_show_mtu,
    "cisco_interface_status": _parse_cisco_interface_status,
    "cisco_isis_interface_brief": _parse_cisco_isis_interface_brief,
    "cisco_nxos_transceiver": _parse_cisco_nxos_transceiver,
    "cisco_power": _parse_cisco_power,
    "cisco_system_uptime": _parse_cisco_system_uptime,
}


class Dispatcher:
    """Route a (command_id, raw_output, parser_config) tuple to the right parser.

    ``command_id`` is currently unused — kept in the signature so that
    a future routing strategy can switch on it without reshaping the
    callers. The actual routing key today is
    ``parser_config["custom_parser"]``.
    """

    def __init__(
        self,
        registry: dict[str, CustomParser] | None = None,
        field_engine: GenericFieldEngine | None = None,
    ) -> None:
        # Defensive copy so callers (or tests) cannot mutate the live registry.
        self._registry: dict[str, CustomParser] = dict(
            registry if registry is not None else _DEFAULT_REGISTRY
        )
        self._field_engine = field_engine or GenericFieldEngine()

    # ------------------------------------------------------------------ #
    # introspection
    # ------------------------------------------------------------------ #
    def has(self, custom_parser: str) -> bool:
        """Return True iff ``custom_parser`` is a registered vendor parser."""
        return (custom_parser or "") in self._registry

    def custom_parsers(self) -> list[str]:
        """Return registered custom_parser keys, alphabetically."""
        return sorted(self._registry.keys())

    # ------------------------------------------------------------------ #
    # dispatch
    # ------------------------------------------------------------------ #
    def parse(
        self,
        command_id: str,
        raw_output: Any,
        parser_config: dict | None,
    ) -> dict[str, Any]:
        """Apply ``parser_config`` to ``raw_output``.

        Routing
        -------
        * ``parser_config is None``      → ``{}``
        * ``custom_parser`` registered   → call the registered callable
        * otherwise                      → delegate to ``GenericFieldEngine``

        ``command_id`` is accepted for forward-compatibility but unused.
        """
        if parser_config is None:
            return {}
        custom_parser = parser_config.get("custom_parser")
        callable_ = self._registry.get(custom_parser) if custom_parser else None
        if callable_ is not None:
            return callable_(raw_output)
        return self._field_engine.apply(raw_output, parser_config)


__all__ = ["Dispatcher", "CustomParser"]
