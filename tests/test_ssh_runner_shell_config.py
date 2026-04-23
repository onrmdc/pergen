"""
Wave-7.4 — interactive-shell-based config runner.

The wave-7.3 fix split the bounce into two SSH sessions but still used
``ssh_runner.run_config_lines_pty`` which calls ``client.exec_command``
with the script as a single argument. NX-OS's SSH ``exec_command``
channel does NOT run multi-line config scripts the way an interactive
shell does — it interprets only the first line as the command and the
rest is fed back as channel input that NX-OS does not act on.

Operator log evidence (2026-04-23): the dispatch ran
``configure terminal\\ninterface Ethernet1/15\\nshutdown\\nend\\n``
in a single PTY-enabled exec_command, the channel sent EOF in ~1
second, and the device's interface state never actually changed.

This test pins the new path: ``ssh_runner.run_config_lines_shell``
uses ``client.invoke_shell()`` (real interactive PTY), waits for the
device's prompt before each line, dispatches each line individually,
and reads the device's response between commands. This is the
standard paramiko pattern for NX-OS / IOS-style config sessions.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.security, pytest.mark.unit]


# --------------------------------------------------------------------------- #
# Prompt-detection regex                                                      #
# --------------------------------------------------------------------------- #


class TestPromptRegex:
    @pytest.mark.parametrize(
        "line",
        [
            "switch# ",
            "switch(config)# ",
            "switch(config-if)# ",
            "LSW-IL2-H2-R509-VENUSTEST-P1-N04# ",
            "LSW-IL2-H2-R509-VENUSTEST-P1-N04(config)# ",
            "LSW-IL2-H2-R509-VENUSTEST-P1-N04(config-if)# ",
            "leaf-01(config-if-Ethernet1/15)# ",
            "core# ",
        ],
    )
    def test_prompt_regex_matches_canonical_nxos_prompts(self, line):
        from backend.runners.ssh_runner import _CONFIG_PROMPT_RE

        assert _CONFIG_PROMPT_RE.search(line) is not None, (
            f"prompt regex must match {line!r}"
        )

    @pytest.mark.parametrize(
        "line",
        [
            "User Access Verification\n",
            "Password: ",
            "Login: ",
            "show version",
            "% Invalid input",
            "this is not a prompt",
        ],
    )
    def test_prompt_regex_rejects_non_prompts(self, line):
        from backend.runners.ssh_runner import _CONFIG_PROMPT_RE

        assert _CONFIG_PROMPT_RE.search(line) is None, (
            f"prompt regex must NOT match {line!r}"
        )


# --------------------------------------------------------------------------- #
# run_config_lines_shell() — happy path                                       #
# --------------------------------------------------------------------------- #


def _make_shell(transcript: list[bytes]):
    """Build a mock paramiko shell channel.

    The transcript is consumed one chunk per "interaction" (initial
    connection or each ``send()`` call). After delivering its chunk,
    ``recv`` returns ``b""`` until the next ``send`` arrives. This
    mimics a real PTY: data flows from the device only after a request,
    and there's nothing to read until the next round-trip.
    """
    chan = MagicMock()
    state = {"pending": None, "iter": iter(transcript)}

    # The very first interaction (before any send) is the initial banner
    # + prompt that appears right after invoke_shell.
    try:
        state["pending"] = next(state["iter"])
    except StopIteration:
        state["pending"] = None

    def _recv(_n: int) -> bytes:
        chunk = state["pending"]
        state["pending"] = None
        return chunk if chunk is not None else b""

    def _send(payload: bytes) -> int:
        # The next recv() call should return the next transcript chunk.
        try:
            state["pending"] = next(state["iter"])
        except StopIteration:
            state["pending"] = None
        return len(payload)

    chan.recv.side_effect = _recv
    chan.send.side_effect = _send
    chan.recv_ready.return_value = True
    chan.exit_status_ready.return_value = False
    chan.closed = False
    return chan


class TestShellHappyPath:
    """Wave-7.5: every dispatch starts with two prelude sends (wake
    newline + ``terminal length 0``) BEFORE the operator's lines.
    Tests must include matching prompts in the transcript.
    """

    def test_sends_each_line_and_waits_for_prompt(self):
        from backend.runners import ssh_runner

        # Simulate NX-OS responding with a prompt after every line,
        # including the wake-newline and terminal-length-0 prelude.
        chan = _make_shell(
            [
                b"\r\nleaf-01# ",  # initial banner+prompt after invoke_shell
                b"\r\nleaf-01# ",  # after wake "\n"
                b"\r\nleaf-01# ",  # after "terminal length 0"
                b"\r\nleaf-01(config)# ",  # after "configure terminal"
                b"\r\nleaf-01(config-if)# ",  # after "interface Ethernet1/15"
                b"\r\nleaf-01(config-if)# ",  # after "shutdown"
                b"\r\nleaf-01# ",  # after "end"
            ]
        )

        with patch.object(
            ssh_runner, "_open_shell_channel", return_value=chan
        ):
            out, err = ssh_runner.run_config_lines_shell(
                "10.59.65.4",
                "u",
                "p",
                ["configure terminal", "interface Ethernet1/15", "shutdown", "end"],
                timeout=10,
            )

        assert err is None, f"unexpected error: {err}"
        # All sends accounted for (wake + paging + 4 operator lines).
        sent_payloads = [c.args[0] for c in chan.send.call_args_list]
        assert b"\n" in sent_payloads  # wake newline
        assert b"terminal length 0\n" in sent_payloads
        assert b"configure terminal\n" in sent_payloads
        assert b"interface Ethernet1/15\n" in sent_payloads
        assert b"shutdown\n" in sent_payloads
        assert b"end\n" in sent_payloads
        # Output must include the device responses so the audit log can
        # surface what NX-OS actually said.
        assert "leaf-01(config-if)#" in out
        assert "leaf-01(config)#" in out

    def test_sends_lines_in_order(self):
        from backend.runners import ssh_runner

        chan = _make_shell(
            [
                b"\r\nsw# ",  # initial
                b"\r\nsw# ",  # after wake \n
                b"\r\nsw# ",  # after terminal length 0
                b"\r\nsw(config)# ",
                b"\r\nsw(config-if)# ",
                b"\r\nsw(config-if)# ",
                b"\r\nsw# ",
            ]
        )

        with patch.object(ssh_runner, "_open_shell_channel", return_value=chan):
            ssh_runner.run_config_lines_shell(
                "1.2.3.4",
                "u",
                "p",
                ["configure terminal", "interface Eth1/1", "shutdown", "end"],
                timeout=10,
            )

        sent_order = [c.args[0] for c in chan.send.call_args_list]
        # Wake newline + paging-disable come BEFORE the operator's lines.
        assert sent_order == [
            b"\n",
            b"terminal length 0\n",
            b"configure terminal\n",
            b"interface Eth1/1\n",
            b"shutdown\n",
            b"end\n",
        ]


# --------------------------------------------------------------------------- #
# Failure modes                                                               #
# --------------------------------------------------------------------------- #


class TestShellFailureModes:
    def test_returns_error_on_invalid_input_response(self):
        """If NX-OS responds with '% Invalid input detected', surface
        that as an error rather than silently succeeding.

        Wave-7.5: account for the wake-newline + paging prelude.
        """
        from backend.runners import ssh_runner

        chan = _make_shell(
            [
                b"\r\nsw# ",  # initial
                b"\r\nsw# ",  # after wake \n
                b"\r\nsw# ",  # after terminal length 0
                b"\r\nsw(config)# ",  # after "configure terminal"
                # Bogus interface name — NX-OS would reject this:
                b"\r\n% Invalid command at '^' marker.\r\nsw(config)# ",
                b"\r\nsw# ",
            ]
        )

        with patch.object(ssh_runner, "_open_shell_channel", return_value=chan):
            out, err = ssh_runner.run_config_lines_shell(
                "1.2.3.4",
                "u",
                "p",
                ["configure terminal", "interface BadName", "end"],
                timeout=10,
            )

        assert err is not None
        assert "rejected" in err.lower() or "invalid" in err.lower(), (
            f"expected device-error message, got: {err!r}"
        )

    def test_times_out_when_prompt_never_arrives(self):
        """If the device never sends a prompt back, the runner must
        return a 'timeout' bucket rather than hang indefinitely.
        """
        from backend.runners import ssh_runner

        chan = MagicMock()
        chan.recv.return_value = b""  # no data ever
        chan.recv_ready.return_value = False
        chan.exit_status_ready.return_value = False
        chan.closed = False

        with patch.object(ssh_runner, "_open_shell_channel", return_value=chan):
            out, err = ssh_runner.run_config_lines_shell(
                "1.2.3.4",
                "u",
                "p",
                ["configure terminal"],
                timeout=2,  # short timeout for the test
            )

        assert err == "timeout", f"expected 'timeout' bucket, got {err!r}"

    def test_returns_paramiko_not_installed_when_module_missing(self, monkeypatch):
        from backend.runners import ssh_runner

        monkeypatch.setattr(ssh_runner, "paramiko", None)
        out, err = ssh_runner.run_config_lines_shell(
            "1.2.3.4", "u", "p", ["configure terminal"], timeout=5
        )
        assert err == "paramiko not installed"
        assert out is None

    def test_empty_lines_returns_friendly_error(self):
        from backend.runners import ssh_runner

        out, err = ssh_runner.run_config_lines_shell(
            "1.2.3.4", "u", "p", [], timeout=5
        )
        assert err is not None
        assert "no configuration lines" in err.lower()


# --------------------------------------------------------------------------- #
# Wave-7.5 — banner skip + paging disable + non-blocking polling              #
# --------------------------------------------------------------------------- #


class TestBannerSkipAndPagingDisable:
    """NX-OS sends a long MOTD banner on session open and may not emit
    a prompt until the user presses Enter. The runner must:

    1. Send a wake-up newline immediately after invoke_shell so the
       device flushes its banner and emits a prompt.
    2. Send ``terminal length 0`` to disable paging — otherwise
       multi-page command output triggers ``--More--`` and waits for
       a key press.
    3. Use short polling (NOT a 30-second blocking recv) so the runner
       does not idle for the full timeout when no data is arriving.
    """

    def test_sends_wake_newline_after_shell_open(self):
        """The first thing on the wire after invoke_shell must be a
        bare ``\\n`` to nudge NX-OS past its banner.
        """
        from backend.runners import ssh_runner

        chan = _make_shell(
            [
                # Initial banner — no prompt yet (NX-OS waits for Enter).
                b"Cisco Nexus Operating System (NX-OS) Software\r\n"
                b"TAC support: http://www.cisco.com/tac\r\n"
                b"Copyright ...\r\n",
                # After wake \n, the real prompt appears.
                b"\r\nleaf-01# ",
                # After "terminal length 0", another prompt.
                b"\r\nleaf-01# ",
                # After "configure terminal":
                b"\r\nleaf-01(config)# ",
                # After "interface Ethernet1/15":
                b"\r\nleaf-01(config-if)# ",
                # After "shutdown":
                b"\r\nleaf-01(config-if)# ",
                # After "end":
                b"\r\nleaf-01# ",
            ]
        )

        with patch.object(
            ssh_runner, "_open_shell_channel", return_value=chan
        ):
            out, err = ssh_runner.run_config_lines_shell(
                "10.59.65.4",
                "u",
                "p",
                [
                    "configure terminal",
                    "interface Ethernet1/15",
                    "shutdown",
                    "end",
                ],
                timeout=10,
            )

        assert err is None, f"unexpected error: {err}"
        sent = [c.args[0] for c in chan.send.call_args_list]
        # First send must be the wake-up newline.
        assert sent[0] == b"\n", f"expected wake-up newline, got {sent[0]!r}"
        # Second send must be the paging-disable.
        assert sent[1] == b"terminal length 0\n", (
            f"expected paging-disable, got {sent[1]!r}"
        )
        # Then the operator's lines, in order.
        assert sent[2:] == [
            b"configure terminal\n",
            b"interface Ethernet1/15\n",
            b"shutdown\n",
            b"end\n",
        ]

    def test_does_not_block_for_full_timeout_when_idle(self):
        """If the channel is idle (no data arriving), the runner must
        not consume the entire timeout window. Earlier bug: each
        recv() blocked for 30 seconds because chan.settimeout was 30s.
        """
        import time as _t

        from backend.runners import ssh_runner

        # Channel that never emits anything.
        chan = MagicMock()
        chan.recv.return_value = b""
        chan.recv_ready.return_value = False
        chan.send.return_value = 1
        chan.exit_status_ready.return_value = False
        chan.closed = False

        with patch.object(
            ssh_runner, "_open_shell_channel", return_value=chan
        ):
            t0 = _t.monotonic()
            out, err = ssh_runner.run_config_lines_shell(
                "1.2.3.4",
                "u",
                "p",
                ["configure terminal"],
                timeout=3,
            )
            elapsed = _t.monotonic() - t0

        assert err == "timeout"
        # Must respect the timeout (not wildly exceed it). Allow some
        # slack for the grace-period reads, but reject anything > 2x.
        assert elapsed < 6.0, (
            f"runner blocked for {elapsed:.1f}s with timeout=3 — "
            "non-blocking polling is broken"
        )
