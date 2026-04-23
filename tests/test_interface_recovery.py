"""Tests for interface recovery (validate names, mocked runners)."""
import os
import sys
import unittest
from unittest.mock import patch

import pytest as _pytest_for_marker  # noqa: F401

pytestmark = [_pytest_for_marker.mark.integration]

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

class TestValidateInterfaceNames(unittest.TestCase):
    def test_ok(self):
        from backend.runners.interface_recovery import validate_interface_names

        names, err = validate_interface_names(["Ethernet1/1", "Port-Channel10"])
        self.assertIsNone(err)
        self.assertEqual(names, ["Ethernet1/1", "Port-Channel10"])

    def test_reject_injection(self):
        from backend.runners.interface_recovery import validate_interface_names

        names, err = validate_interface_names(["Ethernet1/1;exit"])
        self.assertIsNotNone(err)
        self.assertEqual(names, [])


class TestRecoverCisco(unittest.TestCase):
    @patch("backend.runners.interface_recovery.time.sleep")
    @patch("backend.runners.ssh_runner.run_config_lines_shell")
    def test_cisco_builds_lines(self, mock_pty, _mock_sleep):
        """Wave-7.3: each interface bounce now executes as TWO separate
        SSH sessions (shutdown stanza + no-shutdown stanza) with a
        delay between them. Each stanza is the canonical 4-line script.
        """
        from backend.runners.interface_recovery import recover_interfaces_cisco_nxos

        mock_pty.return_value = ("ok", None)
        out, err = recover_interfaces_cisco_nxos("10.0.0.1", "u", "p", ["Ethernet1/1"])
        self.assertIsNone(err)
        # Two sessions: shutdown then no-shutdown.
        self.assertEqual(mock_pty.call_count, 2)
        first_lines = mock_pty.call_args_list[0][0][3]
        second_lines = mock_pty.call_args_list[1][0][3]
        # First (shutdown) stanza.
        self.assertEqual(
            first_lines,
            [
                "configure terminal",
                "interface Ethernet1/1",
                "shutdown",
                "end",
            ],
        )
        # Second (no-shutdown) stanza.
        self.assertEqual(
            second_lines,
            [
                "configure terminal",
                "interface Ethernet1/1",
                "no shutdown",
                "end",
            ],
        )


class TestRecoverArista(unittest.TestCase):
    @patch("backend.runners.interface_recovery.time.sleep")
    @patch("backend.runners.arista_eapi.run_commands")
    def test_arista_cmds(self, mock_rc, _mock_sleep):
        """Wave-7.3: Arista bounce now also splits into two eAPI batches."""
        from backend.runners.interface_recovery import recover_interfaces_arista_eos

        mock_rc.return_value = ([{}], None)
        recover_interfaces_arista_eos("10.0.0.1", "u", "p", ["Ethernet1/1"])
        self.assertEqual(mock_rc.call_count, 2)
        first_cmds = mock_rc.call_args_list[0][0][3]
        second_cmds = mock_rc.call_args_list[1][0][3]
        self.assertEqual(
            first_cmds,
            ["configure", "interface Ethernet1/1", "shutdown", "end"],
        )
        self.assertEqual(
            second_cmds,
            ["configure", "interface Ethernet1/1", "no shutdown", "end"],
        )


class TestClearCounters(unittest.TestCase):
    def test_build_command(self):
        from backend.runners.interface_recovery import build_clear_counters_command

        self.assertEqual(build_clear_counters_command("Ethernet8"), "clear counters interface Ethernet8")
        self.assertEqual(build_clear_counters_command(""), "")

    @patch("backend.runners.arista_eapi.run_commands")
    def test_arista_clear_calls_eapi(self, mock_rc):
        from backend.runners.interface_recovery import clear_counters_arista_eos

        mock_rc.return_value = ([{}], None)
        clear_counters_arista_eos("10.0.0.1", "u", "p", "Ethernet1/1")
        mock_rc.assert_called_once()
        cmd = mock_rc.call_args[0][3][0]
        self.assertIn("clear counters interface", cmd)
        self.assertIn("Ethernet1/1", cmd)

    @patch("backend.runners.ssh_runner.run_command")
    def test_cisco_clear_calls_ssh(self, mock_cmd):
        from backend.runners.interface_recovery import clear_counters_cisco_nxos

        mock_cmd.return_value = ("", None)
        clear_counters_cisco_nxos("10.0.0.1", "u", "p", "Ethernet1/1")
        mock_cmd.assert_called_once()
        self.assertIn("clear counters interface", mock_cmd.call_args[0][3])


class TestInterfaceStatusSummary(unittest.TestCase):
    @patch("backend.runners.arista_eapi.run_commands")
    def test_arista_status_one_line(self, mock_rc):
        from backend.runners.interface_recovery import fetch_interface_status_summary_arista_eos

        mock_rc.return_value = (
            [
                {
                    "interfaces": {
                        "Ethernet8": {
                            "interfaceStatus": "connected",
                            "interfaceCounters": {"inErrors": 0},
                            "mtu": 9214,
                            "lastStatusChangeTimestamp": 1700000000.0,
                        }
                    }
                }
            ],
            None,
        )
        text, err = fetch_interface_status_summary_arista_eos("10.0.0.1", "u", "p", ["Ethernet8"])
        self.assertIsNone(err)
        self.assertIn("Ethernet8", text)
        self.assertIn("state=", text)

    @patch("backend.runners.ssh_runner.run_command")
    def test_cisco_status_snippet(self, mock_cmd):
        from backend.runners.interface_recovery import fetch_interface_status_summary_cisco_nxos

        mock_cmd.return_value = ("Ethernet1/1 is up\nline protocol is up", None)
        text, err = fetch_interface_status_summary_cisco_nxos("10.0.0.1", "u", "p", ["Ethernet1/1"])
        self.assertIsNone(err)
        self.assertIn("Ethernet1/1", text)
        self.assertIn("line protocol", text)


if __name__ == "__main__":
    unittest.main()
