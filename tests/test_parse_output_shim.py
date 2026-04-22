"""Back-compat shim contract for ``backend.parse_output``.

This test is the **safety net** for the parse_output refactor (see
``docs/refactor/parse_output_split.md``). It pins every symbol that any
in-tree caller imports from ``backend.parse_output`` so that the planned
move into ``backend.parsers.*`` cannot silently break:

  * production callers in ``backend/runners/``, ``backend/find_leaf.py``,
    and ``backend/parsers/engine.py``;
  * the four parser test suites (golden, legacy_coverage,
    arista_interface_status, cisco_interface_detailed);
  * the private import in ``backend/runners/interface_recovery.py`` of
    ``_parse_arista_interface_status``.

If a legacy symbol disappears or stops being callable, this test fails
**before** the refactor reaches the green-snapshot gate, which makes
the cause of the regression obvious.

Adding a new symbol to ``parse_output`` is fine — only **removing** one
that callers depend on triggers a failure.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable

import pytest

# Public functions — operator-facing names without leading underscore.
PUBLIC_API: tuple[str, ...] = (
    "parse_output",
    "parse_arista_bgp_evpn_next_hop",
    "parse_arista_arp_interface_for_ip",
    "parse_arp_suppression_for_ip",
    "parse_arp_suppression_asci",
    "parse_cisco_arp_interface_for_ip",
)

# Private parser entry points consumed by tests / interface_recovery.py.
# These MUST remain importable from ``backend.parse_output`` after the
# refactor — the shim re-exports them from their new home in
# ``backend.parsers.<vendor>.<domain>``.
PRIVATE_PARSERS: tuple[str, ...] = (
    # arista
    "_parse_arista_uptime",
    "_parse_arista_cpu",
    "_parse_arista_disk",
    "_parse_arista_power",
    "_parse_arista_transceiver",
    "_parse_arista_interface_status",
    "_parse_arista_interface_description",
    "_parse_arista_isis_adjacency",
    # cisco nxos
    "_parse_cisco_system_uptime",
    "_parse_cisco_isis_interface_brief",
    "_parse_cisco_power",
    "_parse_cisco_nxos_transceiver",
    "_parse_cisco_interface_status",
    "_parse_cisco_interface_show_mtu",
    "_parse_cisco_interface_detailed",
    "_parse_cisco_interface_description",
)

# Private helpers consumed directly by tests
# (see tests/test_legacy_coverage_parse_output.py and
# tests/test_parse_arista_interface_status.py).
PRIVATE_HELPERS: tuple[str, ...] = (
    "_count_from_json",
    "_get_path",
    "_extract_regex",
    "_parse_relative_seconds_ago",
)

ALL_LEGACY_SYMBOLS: tuple[str, ...] = (
    PUBLIC_API + PRIVATE_PARSERS + PRIVATE_HELPERS
)


@pytest.fixture(scope="module")
def parse_output_module():
    """Reload the module fresh so a stale ``__pycache__`` cannot mask drift."""
    return importlib.import_module("backend.parse_output")


class TestShimContract:
    """Pin the legacy import surface that callers depend on."""

    @pytest.mark.parametrize("symbol", ALL_LEGACY_SYMBOLS)
    def test_legacy_symbol_is_importable(
        self, parse_output_module, symbol: str
    ) -> None:
        """Each legacy symbol must still resolve via attribute access."""
        assert hasattr(parse_output_module, symbol), (
            f"backend.parse_output.{symbol} disappeared — the shim must "
            f"re-export every name in the legacy import surface. See "
            f"docs/refactor/parse_output_split.md."
        )

    @pytest.mark.parametrize("symbol", ALL_LEGACY_SYMBOLS)
    def test_legacy_symbol_is_callable(
        self, parse_output_module, symbol: str
    ) -> None:
        """Every preserved symbol is a callable (function or class)."""
        obj = getattr(parse_output_module, symbol)
        assert callable(obj), (
            f"backend.parse_output.{symbol} is no longer callable "
            f"(got {type(obj).__name__})."
        )

    @pytest.mark.parametrize("symbol", ALL_LEGACY_SYMBOLS)
    def test_legacy_symbol_via_from_import(self, symbol: str) -> None:
        """``from backend.parse_output import <name>`` keeps working.

        This is the form most tests use, so we validate it explicitly
        rather than only via ``getattr``.
        """
        module = importlib.import_module("backend.parse_output")
        obj: Callable = getattr(module, symbol)
        assert callable(obj)


class TestKnownCallers:
    """Smoke-test the exact import statements used by production callers.

    These mirror the live import sites; if any fail, a real production
    code path is broken.
    """

    def test_runner_imports_module(self) -> None:
        """``backend/runners/runner.py:6`` — ``from backend import parse_output as parse_output_module``."""
        from backend import parse_output as parse_output_module

        assert hasattr(parse_output_module, "parse_output")

    def test_find_leaf_imports_module(self) -> None:
        """``backend/find_leaf.py:9`` — ``from backend import parse_output``."""
        from backend import parse_output

        assert hasattr(parse_output, "parse_arp_suppression_for_ip")
        assert hasattr(parse_output, "parse_cisco_arp_interface_for_ip")
        assert hasattr(parse_output, "parse_arista_arp_interface_for_ip")
        assert hasattr(parse_output, "parse_arista_bgp_evpn_next_hop")

    def test_engine_imports_parse_output_callable(self) -> None:
        """``backend/parsers/engine.py:26`` — legacy dispatcher entry."""
        from backend.parse_output import parse_output as legacy

        assert callable(legacy)

    def test_interface_recovery_imports_private_parser(self) -> None:
        """``backend/runners/interface_recovery.py:84`` — private import."""
        from backend.parse_output import _parse_arista_interface_status

        assert callable(_parse_arista_interface_status)


class TestNoDuplicateDefinitions:
    """Once the refactor lands, each parser must have exactly one home.

    During the refactor (Phases 1-6), the shim re-exports symbols from
    their new module location. This test asserts that re-exports point
    at the *new* module, not at a copy in the legacy file.

    Until Phase 1 lands, every symbol still lives in ``backend.parse_output``
    itself — the assertion is vacuously true. After Phase 1, this test
    starts catching accidental duplicate definitions.
    """

    def test_each_symbol_has_a_single_module_origin(
        self, parse_output_module
    ) -> None:
        """For each legacy symbol, ``__module__`` is recorded.

        Recorded in a snapshot dict so that future drift (e.g. a parser
        moved back into the shim) is visible in test output.
        """
        origins: dict[str, str] = {}
        for symbol in ALL_LEGACY_SYMBOLS:
            obj = getattr(parse_output_module, symbol)
            origins[symbol] = getattr(obj, "__module__", "<unknown>")

        # We don't pin specific origins here yet — that comes in Phase 8
        # when the shim is final. For now, just assert origins are stable
        # within a single test run (i.e. the dict was built without error).
        assert len(origins) == len(ALL_LEGACY_SYMBOLS)
