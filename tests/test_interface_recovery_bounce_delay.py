"""
Wave-7.3 — Interface bounce recovery: deterministic 5-second delay.

Bug fix: ``/api/transceiver/recover`` used to send ``shutdown`` and
``no shutdown`` back-to-back inside a single config script. NX-OS
schedules link-state changes asynchronously and coalesces the two
commands, so the port often never observes a real down→up transition
and stays errdisabled / flapping. The API returned ``200 ok`` even
though nothing recovered.

Confirmed in production logs against ``Ethernet1/15`` on
``LSW-IL2-H2-R509-VENUSTEST-P1-N04`` (2026-04-23). Operator-validated
fix: split the bounce into TWO sessions per interface with a 5-second
sleep between them — matching the canonical CLI sequence:

    conf t
    interface <name>
    shutdown
    ! wait 5 seconds (operator-side)
    no shutdown
    end

Hardening (operator's explicit constraint): the runner must NEVER be
able to send anything beyond the canonical recovery commands. A
strict regex allowlist enforces this — any line that does not match
``configure terminal`` / ``configure`` / ``interface <validated>`` /
``shutdown`` / ``no shutdown`` / ``end`` raises ``ValueError`` before
any SSH/eAPI dispatch.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.security, pytest.mark.unit]


# --------------------------------------------------------------------------- #
# Plan structure                                                              #
# --------------------------------------------------------------------------- #


class TestPlanStructure:
    def test_nxos_plan_emits_two_stanzas_per_interface(self):
        """Each interface produces two scripts: shutdown then no-shutdown."""
        from backend.runners.interface_recovery import (
            build_cisco_nxos_recovery_plan,
        )

        plan = build_cisco_nxos_recovery_plan(["Ethernet1/15"])
        assert len(plan) == 2, (
            f"expected exactly two stanzas per interface, got {len(plan)}: {plan}"
        )
        shutdown_stanza, noshut_stanza = plan
        assert shutdown_stanza["interface"] == "Ethernet1/15"
        assert noshut_stanza["interface"] == "Ethernet1/15"
        assert shutdown_stanza["phase"] == "shutdown"
        assert noshut_stanza["phase"] == "no_shutdown"
        # The shutdown stanza carries the post-stanza delay.
        assert shutdown_stanza["post_delay_sec"] >= 5
        assert noshut_stanza["post_delay_sec"] == 0

    def test_nxos_plan_lines_match_canonical_sequence(self):
        from backend.runners.interface_recovery import (
            build_cisco_nxos_recovery_plan,
        )

        plan = build_cisco_nxos_recovery_plan(["Ethernet1/15"])
        sd, nsd = plan
        assert sd["lines"] == [
            "configure terminal",
            "interface Ethernet1/15",
            "shutdown",
            "end",
        ]
        assert nsd["lines"] == [
            "configure terminal",
            "interface Ethernet1/15",
            "no shutdown",
            "end",
        ]

    def test_nxos_plan_is_per_interface_sequential(self):
        """Multi-interface request: each interface gets its own pair of
        stanzas, in the same order the operator listed them. Sequential
        execution (not parallel) is the documented batch semantics.
        """
        from backend.runners.interface_recovery import (
            build_cisco_nxos_recovery_plan,
        )

        plan = build_cisco_nxos_recovery_plan(
            ["Ethernet1/15", "Ethernet1/20"]
        )
        assert len(plan) == 4
        assert [s["interface"] for s in plan] == [
            "Ethernet1/15",
            "Ethernet1/15",
            "Ethernet1/20",
            "Ethernet1/20",
        ]
        assert [s["phase"] for s in plan] == [
            "shutdown",
            "no_shutdown",
            "shutdown",
            "no_shutdown",
        ]

    def test_arista_plan_emits_two_batches_per_interface(self):
        from backend.runners.interface_recovery import (
            build_arista_recovery_plan,
        )

        plan = build_arista_recovery_plan(["Ethernet1/15"])
        assert len(plan) == 2
        sd, nsd = plan
        assert sd["lines"] == [
            "configure",
            "interface Ethernet1/15",
            "shutdown",
            "end",
        ]
        assert nsd["lines"] == [
            "configure",
            "interface Ethernet1/15",
            "no shutdown",
            "end",
        ]
        assert sd["post_delay_sec"] >= 5


# --------------------------------------------------------------------------- #
# Strict allowlist (operator's explicit hardening constraint)                 #
# --------------------------------------------------------------------------- #


class TestStrictAllowlist:
    @pytest.mark.parametrize(
        "line",
        [
            "configure terminal",
            "configure",
            "interface Ethernet1/15",
            "interface Port-Channel1",
            "interface Ethernet1/1.100",
            "shutdown",
            "no shutdown",
            "end",
        ],
    )
    def test_canonical_lines_are_allowed(self, line):
        from backend.runners.interface_recovery import _assert_lines_allowed

        # Must not raise.
        _assert_lines_allowed([line])

    @pytest.mark.parametrize(
        "rogue_line",
        [
            "hostname FOO",
            "ip address 1.2.3.4/24",
            "write erase",
            "reload",
            "copy running-config startup-config",
            "shutdown ; reload",
            "shutdown && reload",
            "no shutdown | exclude foo",
            "interface Ethernet1/15 ; shutdown",
            "interface Ethernet1/15\n shutdown",
            "switchport mode trunk",
            "vlan 100",
            "username admin privilege 15 secret pwn",
            "no logging",
            "interface ../etc/passwd",
            "  shutdown ",  # trailing/leading whitespace not in canonical form
            "Shutdown",  # case-sensitive — canonical is lowercase
            "",
        ],
    )
    def test_rogue_lines_are_rejected(self, rogue_line):
        from backend.runners.interface_recovery import _assert_lines_allowed

        with pytest.raises(ValueError):
            _assert_lines_allowed([rogue_line])

    def test_allowlist_rejects_oversized_script(self):
        """Defensive cap: max 4 lines per script (configure + interface +
        action + end). Anything longer is suspect.
        """
        from backend.runners.interface_recovery import _assert_lines_allowed

        # 5 valid-looking lines — too many.
        oversized = [
            "configure terminal",
            "interface Ethernet1/15",
            "shutdown",
            "shutdown",  # duplicate, but more importantly — too many lines
            "end",
        ]
        with pytest.raises(ValueError):
            _assert_lines_allowed(oversized)

    def test_allowlist_rejects_two_interface_stanzas_in_one_script(self):
        """Each script must touch exactly one interface. If the caller
        somehow produces two ``interface`` lines in one script, refuse.
        """
        from backend.runners.interface_recovery import _assert_lines_allowed

        bad = [
            "configure terminal",
            "interface Ethernet1/15",
            "interface Ethernet1/20",
            "end",
        ]
        with pytest.raises(ValueError):
            _assert_lines_allowed(bad)


# --------------------------------------------------------------------------- #
# Recovery dispatch — sleep + sequential per-interface                        #
# --------------------------------------------------------------------------- #


class TestNxosRecoverySleepAndDispatch:
    def test_calls_ssh_twice_per_interface_with_sleep_between(self):
        """The bounce must:
        1. Open SSH, send the shutdown stanza, close.
        2. ``time.sleep(5)``.
        3. Open SSH again, send the no-shutdown stanza, close.
        """
        from backend.runners import interface_recovery

        with (
            patch(
                "backend.runners.ssh_runner.run_config_lines_pty",
                return_value=("ok", None),
            ) as mock_pty,
            patch(
                "backend.runners.interface_recovery.time.sleep"
            ) as mock_sleep,
        ):
            out, err = interface_recovery.recover_interfaces_cisco_nxos(
                "10.59.65.4", "u", "p", ["Ethernet1/15"]
            )

        assert err is None, f"unexpected error: {err}"
        assert mock_pty.call_count == 2, (
            f"expected 2 SSH dispatches per interface, got {mock_pty.call_count}"
        )
        # First call: shutdown stanza
        first_lines = mock_pty.call_args_list[0][0][3]
        assert "shutdown" in first_lines
        assert "no shutdown" not in first_lines
        # Second call: no-shutdown stanza
        second_lines = mock_pty.call_args_list[1][0][3]
        assert "no shutdown" in second_lines
        assert "shutdown" not in [
            ln for ln in second_lines if ln != "no shutdown"
        ]
        # Sleep was called with the configured delay.
        mock_sleep.assert_called_once()
        slept_for = mock_sleep.call_args[0][0]
        assert slept_for >= 5, f"expected >=5s sleep, got {slept_for}"

    def test_short_circuits_on_shutdown_failure(self):
        """If the shutdown stanza fails, do NOT proceed to no-shutdown
        (would leave port admin-down).
        """
        from backend.runners import interface_recovery

        with (
            patch(
                "backend.runners.ssh_runner.run_config_lines_pty",
                return_value=(None, "auth_failed"),
            ) as mock_pty,
            patch(
                "backend.runners.interface_recovery.time.sleep"
            ) as mock_sleep,
        ):
            out, err = interface_recovery.recover_interfaces_cisco_nxos(
                "10.59.65.4", "u", "p", ["Ethernet1/15"]
            )

        assert err == "auth_failed"
        assert mock_pty.call_count == 1, (
            "must NOT proceed to no-shutdown if shutdown failed"
        )
        mock_sleep.assert_not_called()

    def test_sequential_per_interface_with_two_interfaces(self):
        """Two interfaces → 4 SSH calls + 2 sleeps, in strict order:
        iface1.shutdown → sleep → iface1.noshut → iface2.shutdown →
        sleep → iface2.noshut.
        """
        from backend.runners import interface_recovery

        with (
            patch(
                "backend.runners.ssh_runner.run_config_lines_pty",
                return_value=("ok", None),
            ) as mock_pty,
            patch(
                "backend.runners.interface_recovery.time.sleep"
            ) as mock_sleep,
        ):
            out, err = interface_recovery.recover_interfaces_cisco_nxos(
                "10.59.65.4", "u", "p", ["Ethernet1/15", "Ethernet1/20"]
            )

        assert err is None
        assert mock_pty.call_count == 4
        assert mock_sleep.call_count == 2

        # Verify per-call interface ordering.
        observed = []
        for call in mock_pty.call_args_list:
            lines = call[0][3]
            iface_line = next(ln for ln in lines if ln.startswith("interface "))
            action = "shutdown" if "shutdown" in lines and "no shutdown" not in lines else "no_shutdown"
            observed.append((iface_line, action))
        assert observed == [
            ("interface Ethernet1/15", "shutdown"),
            ("interface Ethernet1/15", "no_shutdown"),
            ("interface Ethernet1/20", "shutdown"),
            ("interface Ethernet1/20", "no_shutdown"),
        ]


class TestAristaRecoverySleepAndDispatch:
    def test_calls_eapi_twice_per_interface_with_sleep_between(self):
        from backend.runners import interface_recovery

        with (
            patch(
                "backend.runners.arista_eapi.run_commands",
                return_value=([{}], None),
            ) as mock_eapi,
            patch(
                "backend.runners.interface_recovery.time.sleep"
            ) as mock_sleep,
        ):
            results, err = interface_recovery.recover_interfaces_arista_eos(
                "10.0.0.1", "u", "p", ["Ethernet1/15"]
            )

        assert err is None
        assert mock_eapi.call_count == 2
        first_cmds = mock_eapi.call_args_list[0][0][3]
        assert "shutdown" in first_cmds
        assert "no shutdown" not in first_cmds
        second_cmds = mock_eapi.call_args_list[1][0][3]
        assert "no shutdown" in second_cmds
        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] >= 5


# --------------------------------------------------------------------------- #
# Configurable delay via env knob                                             #
# --------------------------------------------------------------------------- #


class TestConfigurableDelay:
    def test_env_override_is_honoured(self, monkeypatch):
        from backend.runners import interface_recovery

        monkeypatch.setenv("PERGEN_RECOVERY_BOUNCE_DELAY_SEC", "8")
        delay = interface_recovery._resolve_bounce_delay_sec()
        assert delay == 8

    def test_env_override_clamps_below_one(self, monkeypatch):
        from backend.runners import interface_recovery

        monkeypatch.setenv("PERGEN_RECOVERY_BOUNCE_DELAY_SEC", "0")
        assert interface_recovery._resolve_bounce_delay_sec() >= 1

    def test_env_override_clamps_above_thirty(self, monkeypatch):
        from backend.runners import interface_recovery

        monkeypatch.setenv("PERGEN_RECOVERY_BOUNCE_DELAY_SEC", "999")
        assert interface_recovery._resolve_bounce_delay_sec() <= 30

    def test_env_override_ignores_garbage(self, monkeypatch):
        from backend.runners import interface_recovery

        monkeypatch.setenv("PERGEN_RECOVERY_BOUNCE_DELAY_SEC", "not-a-number")
        # Falls back to default (5).
        assert interface_recovery._resolve_bounce_delay_sec() == 5

    def test_default_is_five_seconds(self, monkeypatch):
        from backend.runners import interface_recovery

        monkeypatch.delenv("PERGEN_RECOVERY_BOUNCE_DELAY_SEC", raising=False)
        assert interface_recovery._resolve_bounce_delay_sec() == 5
