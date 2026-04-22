"""Back-compat shim for the legacy ``backend.parse_output`` import surface.

The implementation has moved to ``backend.parsers.<vendor>.<domain>``
packages; see ``docs/refactor/parse_output_split.md`` for the layout
and rationale. New code SHOULD import from those packages directly.

This file exists only so that the historic import paths used by:

* ``backend.runners.runner``
* ``backend.find_leaf``
* ``backend.runners.interface_recovery``
* ``tests/test_legacy_coverage_parse_output.py``
* ``tests/golden/test_parsers_golden.py``
* ``tests/test_parse_arista_interface_status.py``
* ``tests/test_parse_cisco_interface_detailed.py``

continue to work. Removal target: a future major release once every
caller has migrated. The shim contract is locked by
``tests/test_parse_output_shim.py``.
"""
from __future__ import annotations

# Standard-library re-exports preserved because tests patch them via
# ``mock.patch("backend.parse_output.<name>")`` (e.g. the golden tests
# patch ``backend.parse_output.time.time``). Keeping these import lines
# ensures patch targets keep resolving without behavioural risk.
import json  # noqa: F401  — preserved for legacy patch targets in tests
import re    # noqa: F401  — preserved for legacy patch targets in tests
import time  # noqa: F401  — preserved for ``mock.patch("backend.parse_output.time.time")``
from datetime import datetime  # noqa: F401  — preserved for legacy import surface
from typing import Any

# --- common utilities ---
from backend.parsers.common.arista_envelope import (
    _arista_result_obj,
    _arista_result_to_dict,
)
from backend.parsers.common.counters import (
    _count_from_json,
    _count_where,
    _get_from_dict_by_key_prefix,
)
from backend.parsers.common.duration import (
    _parse_hhmmss_to_seconds,
    _parse_relative_seconds_ago,
)
from backend.parsers.common.formatting import (
    _apply_value_subtract_and_suffix,
    _format_power_two_decimals,
)
from backend.parsers.common.json_path import (
    _find_key,
    _find_key_containing,
    _find_list,
    _flatten_nested_list,
    _get_path,
    _get_val,
)
from backend.parsers.common.regex_helpers import _count_regex_lines, _extract_regex

# --- Arista vendor parsers ---
from backend.parsers.arista.arp import parse_arista_arp_interface_for_ip
from backend.parsers.arista.bgp import parse_arista_bgp_evpn_next_hop
from backend.parsers.arista.cpu import _parse_arista_cpu
from backend.parsers.arista.disk import _parse_arista_disk
from backend.parsers.arista.interface_description import (
    _parse_arista_interface_description,
)
from backend.parsers.arista.interface_status import (
    _arista_get_interface_counters_dict,
    _arista_in_and_crc_from_counters,
    _parse_arista_interface_status,
    _parse_arista_interface_status_from_table,
)
from backend.parsers.arista.isis import (
    _find_arista_isis_adjacency_list,
    _parse_arista_isis_adjacency,
)
from backend.parsers.arista.power import _parse_arista_power
from backend.parsers.arista.transceiver import _parse_arista_transceiver
from backend.parsers.arista.uptime import _parse_arista_uptime

# --- Cisco NX-OS vendor parsers ---
from backend.parsers.cisco_nxos.arp import (
    _get_cisco_arp_rows,
    _parse_cisco_arp_ascii_for_ip,
    parse_cisco_arp_interface_for_ip,
)
from backend.parsers.cisco_nxos.arp_suppression import (
    _get_arp_suppression_entries_list,
    parse_arp_suppression_asci,
    parse_arp_suppression_for_ip,
)
from backend.parsers.cisco_nxos.interface_description import (
    _parse_cisco_interface_description,
)
from backend.parsers.cisco_nxos.interface_detailed import _parse_cisco_interface_detailed
from backend.parsers.cisco_nxos.interface_mtu import _parse_cisco_interface_show_mtu
from backend.parsers.cisco_nxos.interface_status import _parse_cisco_interface_status
from backend.parsers.cisco_nxos.isis_brief import (
    _find_isis_interface_brief_rows,
    _parse_cisco_isis_interface_brief,
)
from backend.parsers.cisco_nxos.power import _parse_cisco_power
from backend.parsers.cisco_nxos.system_uptime import _parse_cisco_system_uptime
from backend.parsers.cisco_nxos.transceiver import (
    _cisco_find_tx_rx_in_dict,
    _cisco_transceiver_tx_rx_from_row,
    _parse_cisco_nxos_transceiver,
)

# --- vendor-routed dispatcher (replaces the legacy if/elif ladder) ---
from backend.parsers.dispatcher import Dispatcher

# Module-level dispatcher singleton. Tests can patch
# ``backend.parse_output._DEFAULT_DISPATCHER`` to inject a fake without
# monkey-patching ``parse_output`` itself.
_DEFAULT_DISPATCHER = Dispatcher()


def parse_output(
    command_id: str, raw_output: Any, parser_config: dict | None
) -> dict[str, Any]:
    """Apply ``parser_config`` to ``raw_output``.

    Inputs
    ------
    command_id : registered parser identifier (currently unused — kept
        in the signature for routing parity with older callers).
    raw_output : ``dict`` (API JSON) or ``str`` (SSH text).
    parser_config : the parser config from ``backend/config/parsers.yaml``;
        ``None`` returns ``{}``.

    Outputs
    -------
    ``dict`` of ``field_name -> value`` (string or number).
    """
    return _DEFAULT_DISPATCHER.parse(command_id, raw_output, parser_config)


__all__ = [
    # public dispatcher
    "parse_output",
    # public Arista helpers
    "parse_arista_arp_interface_for_ip",
    "parse_arista_bgp_evpn_next_hop",
    # public Cisco NX-OS helpers
    "parse_arp_suppression_asci",
    "parse_arp_suppression_for_ip",
    "parse_cisco_arp_interface_for_ip",
]
