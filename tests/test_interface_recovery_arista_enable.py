"""
Wave-7.8 — Arista eAPI: prepend `enable` and inspect per-cmd results.

Operator log evidence 2026-04-23: every Arista recover request
returned 200 ok in ~6 seconds but the device's interface state never
changed. Backend log:

    audit transceiver.recover ok actor=anonymous
        host=LSW-IL2-H2-R609-MARSTEST-P1-N03 ip=10.59.1.3
        vendor=arista interfaces=['Ethernet8'] bounce_delay_s=5
    ← 200 6005.7ms

Root cause
----------
Arista's eAPI requires the user to be in privileged-exec mode before
``configure`` will be accepted. The legacy dispatch sent
``["configure", "interface Ethernet8", "shutdown", "end"]`` over
``run_commands`` (no enable). For TACACS / RADIUS users without
implicit privilege 15, the device silently rejects the configure
command — but the eAPI ``stopOnError`` semantics combined with the
top-level-only error check meant we never noticed.

Fix
---
1. Prepend ``{"cmd": "enable", "input": <password>}`` to every Arista
   eAPI batch (recover + clear-counters) — same pattern Pergen's
   ``device_commands_bp`` already uses for operator-supplied Arista
   commands.
2. Inspect each per-command result for nested errors and surface the
   first failure to the operator.
3. Log the device-side response so an operator can diagnose any
   future "200 but nothing happened" without re-instrumenting.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.security, pytest.mark.unit]


# --------------------------------------------------------------------------- #
# Recovery: enable is prepended, dispatch uses run_cmds (dict-aware)          #
# --------------------------------------------------------------------------- #


class TestAristaRecoveryPrependsEnable:
    def test_each_stanza_prepends_enable_with_password(self):
        """Each eAPI batch must start with the enable+password dict so
        the device enters privileged-exec before processing configure.
        """
        from backend.runners import interface_recovery

        with (
            patch(
                "backend.runners.arista_eapi.run_cmds",
                return_value=([{}, {}, {}, {}, {}], None),
            ) as mock_cmds,
            patch(
                "backend.runners.interface_recovery.time.sleep"
            ) as mock_sleep,
        ):
            results, err = interface_recovery.recover_interfaces_arista_eos(
                "10.59.1.3", "admin", "secret-pw", ["Ethernet8"]
            )

        assert err is None
        # Two eAPI batches per interface (shutdown + no_shutdown).
        assert mock_cmds.call_count == 2

        # Batch 1: enable + configure + interface + shutdown + end
        first_cmds = mock_cmds.call_args_list[0][0][3]
        assert isinstance(first_cmds[0], dict), (
            "first cmd of every eAPI batch must be the enable dict"
        )
        assert first_cmds[0]["cmd"] == "enable"
        assert first_cmds[0]["input"] == "secret-pw"
        assert first_cmds[1:] == [
            "configure",
            "interface Ethernet8",
            "shutdown",
            "end",
        ]

        # Batch 2: enable + configure + interface + no shutdown + end
        second_cmds = mock_cmds.call_args_list[1][0][3]
        assert isinstance(second_cmds[0], dict)
        assert second_cmds[0]["cmd"] == "enable"
        assert second_cmds[0]["input"] == "secret-pw"
        assert second_cmds[1:] == [
            "configure",
            "interface Ethernet8",
            "no shutdown",
            "end",
        ]

        mock_sleep.assert_called_once()

    def test_prepends_enable_for_each_interface_in_multi_interface_batch(self):
        from backend.runners import interface_recovery

        with (
            patch(
                "backend.runners.arista_eapi.run_cmds",
                return_value=([{}, {}, {}, {}, {}], None),
            ) as mock_cmds,
            patch("backend.runners.interface_recovery.time.sleep"),
        ):
            interface_recovery.recover_interfaces_arista_eos(
                "10.59.1.3",
                "admin",
                "pw",
                ["Ethernet8", "Ethernet9"],
            )

        # 2 interfaces × 2 stanzas = 4 eAPI calls; every call begins with enable.
        assert mock_cmds.call_count == 4
        for call in mock_cmds.call_args_list:
            cmds = call[0][3]
            assert isinstance(cmds[0], dict)
            assert cmds[0]["cmd"] == "enable"

    def test_uses_run_cmds_not_run_commands(self):
        """Must dispatch via ``run_cmds`` (which accepts dict commands
        for the enable-with-input pattern), not the older string-only
        ``run_commands``. A regression guard so a future cleanup doesn't
        silently switch back.
        """
        from backend.runners import interface_recovery

        with (
            patch(
                "backend.runners.arista_eapi.run_cmds",
                return_value=([{}, {}, {}, {}, {}], None),
            ),
            patch(
                "backend.runners.arista_eapi.run_commands",
                return_value=([{}], None),
            ) as mock_run_commands,
            patch("backend.runners.interface_recovery.time.sleep"),
        ):
            interface_recovery.recover_interfaces_arista_eos(
                "10.59.1.3", "admin", "pw", ["Ethernet8"]
            )

        assert mock_run_commands.call_count == 0, (
            "recover must NOT use run_commands (no dict support → no enable)"
        )


class TestAristaRecoveryInspectsPerCmdResults:
    """Even when eAPI returns top-level 200 + no `error` key, individual
    commands inside ``data["result"]`` can still report failure (e.g.
    "% Insufficient privilege"). The dispatcher must surface those.
    """

    def test_returns_error_when_per_cmd_result_contains_errors(self):
        from backend.runners import interface_recovery

        # Simulate: enable ok, configure ok, interface ok, shutdown
        # rejected by the device (privilege-too-low).
        bad_results = [
            {},  # enable
            {},  # configure
            {},  # interface Ethernet8
            {"errors": ["% Insufficient privilege"]},  # shutdown
            {},  # end
        ]
        with (
            patch(
                "backend.runners.arista_eapi.run_cmds",
                return_value=(bad_results, None),
            ),
            patch("backend.runners.interface_recovery.time.sleep"),
        ):
            results, err = interface_recovery.recover_interfaces_arista_eos(
                "10.59.1.3", "admin", "pw", ["Ethernet8"]
            )

        assert err is not None, (
            "per-cmd error inside data['result'] must be surfaced as err"
        )
        assert "privilege" in err.lower() or "insufficient" in err.lower()

    def test_short_circuits_after_first_per_cmd_error(self):
        """If shutdown stanza reports an error, we must NOT proceed to
        the no_shutdown stanza (would mask the failure).
        """
        from backend.runners import interface_recovery

        bad_results = [
            {},
            {},
            {},
            {"errors": ["% Insufficient privilege"]},
            {},
        ]
        with (
            patch(
                "backend.runners.arista_eapi.run_cmds",
                return_value=(bad_results, None),
            ) as mock_cmds,
            patch("backend.runners.interface_recovery.time.sleep") as mock_sleep,
        ):
            interface_recovery.recover_interfaces_arista_eos(
                "10.59.1.3", "admin", "pw", ["Ethernet8"]
            )

        assert mock_cmds.call_count == 1, (
            "must NOT proceed to no_shutdown after shutdown reported error"
        )
        mock_sleep.assert_not_called()


# --------------------------------------------------------------------------- #
# Clear counters: same enable-prepend treatment                               #
# --------------------------------------------------------------------------- #


class TestAristaClearCountersPrependsEnable:
    def test_clear_counters_prepends_enable(self):
        from backend.runners import interface_recovery

        with patch(
            "backend.runners.arista_eapi.run_cmds",
            return_value=([{}, {}], None),
        ) as mock_cmds:
            interface_recovery.clear_counters_arista_eos(
                "10.59.1.3", "admin", "secret-pw", "Ethernet8"
            )

        assert mock_cmds.call_count == 1
        cmds = mock_cmds.call_args[0][3]
        assert isinstance(cmds[0], dict)
        assert cmds[0]["cmd"] == "enable"
        assert cmds[0]["input"] == "secret-pw"
        assert cmds[1] == "clear counters interface Ethernet8"

    def test_clear_counters_surfaces_per_cmd_error(self):
        from backend.runners import interface_recovery

        bad_results = [
            {},  # enable
            {"errors": ["% Insufficient privilege"]},  # clear counters
        ]
        with patch(
            "backend.runners.arista_eapi.run_cmds",
            return_value=(bad_results, None),
        ):
            results, err = interface_recovery.clear_counters_arista_eos(
                "10.59.1.3", "admin", "pw", "Ethernet8"
            )

        assert err is not None
        assert "privilege" in err.lower() or "insufficient" in err.lower()


# --------------------------------------------------------------------------- #
# Diagnostic logging — operator can see what Arista said                      #
# --------------------------------------------------------------------------- #


class TestAristaRecoveryLogsDeviceResponse:
    def test_emits_info_log_with_per_stanza_response(self, caplog):
        """Wave-7.8 (parity with NX-OS wave-7.5): every stanza must
        log the device's response so an operator can diagnose
        "200 ok but nothing happened" without re-instrumenting.
        """
        import logging

        from backend.runners import interface_recovery

        # Attach handler directly so caplog captures records that the
        # interface_recovery module emits during the test (LoggingConfig
        # strips root handlers, but this module's logger propagates to
        # root).
        target = logging.getLogger("app.runner.interface_recovery")
        if caplog.handler not in target.handlers:
            target.addHandler(caplog.handler)
        target.setLevel(logging.DEBUG)

        with (
            patch(
                "backend.runners.arista_eapi.run_cmds",
                return_value=(
                    [{"version": "4.30.1F"}, {}, {}, {}, {}],
                    None,
                ),
            ),
            patch("backend.runners.interface_recovery.time.sleep"),
        ):
            interface_recovery.recover_interfaces_arista_eos(
                "10.59.1.3", "admin", "pw", ["Ethernet8"]
            )

        device_response_lines = [
            r.getMessage()
            for r in caplog.records
            if r.name == "app.runner.interface_recovery"
            and "device-response" in r.getMessage()
            and "arista" in r.getMessage()
        ]
        assert len(device_response_lines) >= 2, (
            f"expected one 'device-response' INFO per stanza (2 total), "
            f"got: {device_response_lines}"
        )
