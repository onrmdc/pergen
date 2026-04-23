"""
Wave-7.6 — Arista bare-Ethernet form acceptance.

Operator feedback 2026-04-23: Arista platforms (7050SX / 7060CX / etc.)
expose front-panel host ports as bare ``Ethernet1``, ``Ethernet8``,
``Ethernet9`` — NO module/port slash. The legacy
``transceiver_recovery_policy._HOST_PORT_RE`` requires the
``Ethernet<m>/<p>`` form (which is correct for Cisco NX-OS), so every
Arista interface was rejected by the policy gate before reaching the
recovery dispatch.

Allowed Arista host-port range: ``Ethernet1`` through ``Ethernet48``,
matching the Cisco range (1-48 host ports) so operators have one
mental model. Same range applies to clear-counters.

Pinned by these tests; the original
``test_transceiver_recovery_policy.py`` Cisco assertions still hold.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security, pytest.mark.unit]


# --------------------------------------------------------------------------- #
# Bare Arista form: Ethernet1 .. Ethernet48                                   #
# --------------------------------------------------------------------------- #


class TestAristaBareEthernet:
    @pytest.mark.parametrize(
        "iface",
        [
            "Ethernet1",
            "Ethernet8",
            "Ethernet9",
            "Ethernet24",
            "Ethernet48",
            "ethernet1",  # case-insensitive
            "Eth9",
            "Et24",
        ],
    )
    def test_arista_host_ports_in_range_accepted(self, iface):
        from backend.transceiver_recovery_policy import (
            is_ethernet_module1_host_port,
        )

        assert is_ethernet_module1_host_port(iface), (
            f"Arista bare-Ethernet form must be accepted: {iface!r}"
        )

    @pytest.mark.parametrize(
        "iface",
        [
            "Ethernet0",  # below range
            "Ethernet49",  # above range (uplink)
            "Ethernet64",
            "Ethernet96",
            "Ethernet128",
        ],
    )
    def test_arista_host_ports_out_of_range_rejected(self, iface):
        from backend.transceiver_recovery_policy import (
            is_ethernet_module1_host_port,
        )

        assert not is_ethernet_module1_host_port(iface), (
            f"out-of-range Arista interface must be rejected: {iface!r}"
        )

    @pytest.mark.parametrize(
        "iface",
        [
            "",
            "Management1",  # mgmt port, never a transceiver
            "Loopback0",
            "Port-Channel1",
            "Vlan100",
            "Tunnel1",
            "Ethernet1.100",  # sub-interface
            "Ethernet1; reload",  # injection attempt
            "Ethernet 1",  # space inside name
        ],
    )
    def test_non_host_interface_forms_rejected(self, iface):
        from backend.transceiver_recovery_policy import (
            is_ethernet_module1_host_port,
        )

        assert not is_ethernet_module1_host_port(iface), (
            f"non-host-port form must be rejected: {iface!r}"
        )


class TestAristaPolicyGate:
    """The full policy: leaf + valid host port."""

    def test_arista_leaf_with_bare_ethernet_allowed(self):
        from backend.transceiver_recovery_policy import (
            is_transceiver_recovery_allowed,
        )

        leaf = {"role": "Leaf", "vendor": "arista"}
        assert is_transceiver_recovery_allowed(leaf, "Ethernet8")
        assert is_transceiver_recovery_allowed(leaf, "Ethernet48")

    def test_arista_spine_with_bare_ethernet_rejected(self):
        from backend.transceiver_recovery_policy import (
            is_transceiver_recovery_allowed,
        )

        spine = {"role": "Spine", "vendor": "arista"}
        assert not is_transceiver_recovery_allowed(spine, "Ethernet8")

    def test_arista_leaf_with_uplink_rejected(self):
        from backend.transceiver_recovery_policy import (
            is_transceiver_recovery_allowed,
        )

        leaf = {"role": "Leaf", "vendor": "arista"}
        assert not is_transceiver_recovery_allowed(leaf, "Ethernet49")


# --------------------------------------------------------------------------- #
# Wave-7.3 strict allowlist — bare Ethernet form must pass                    #
# --------------------------------------------------------------------------- #


class TestRecoveryAllowlistAcceptsBareEthernet:
    """The wave-7.3 ``_assert_lines_allowed`` gate must accept the bare
    ``interface Ethernet8`` form so the runner does not reject Arista
    recovery scripts.
    """

    @pytest.mark.parametrize(
        "line",
        [
            "interface Ethernet1",
            "interface Ethernet8",
            "interface Ethernet48",
            "interface ethernet9",
        ],
    )
    def test_bare_ethernet_interface_line_accepted(self, line):
        from backend.runners.interface_recovery import _assert_lines_allowed

        # Wrap in a minimal valid script so the script-level caps don't
        # interfere; this isolates the per-line allowlist behaviour.
        _assert_lines_allowed(["configure", line, "shutdown", "end"])


# --------------------------------------------------------------------------- #
# Plan builders accept bare Arista interface names                             #
# --------------------------------------------------------------------------- #


class TestAristaRecoveryPlanWithBareEthernet:
    def test_plan_emits_correct_script_for_bare_ethernet(self):
        from backend.runners.interface_recovery import (
            build_arista_recovery_plan,
        )

        plan = build_arista_recovery_plan(["Ethernet8"])
        assert len(plan) == 2
        sd, nsd = plan
        assert sd["lines"] == [
            "configure",
            "interface Ethernet8",
            "shutdown",
            "end",
        ]
        assert nsd["lines"] == [
            "configure",
            "interface Ethernet8",
            "no shutdown",
            "end",
        ]
