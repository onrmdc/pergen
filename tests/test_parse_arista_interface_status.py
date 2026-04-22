"""Tests for Arista interface status parser (interfaces{} vs TABLE_interface)."""
import os
import sys
import unittest

import pytest as _pytest_for_marker  # noqa: F401

pytestmark = [_pytest_for_marker.mark.unit]

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)


class TestAristaInterfaceStatusTable(unittest.TestCase):
    def test_table_interface_eth_link_and_reset(self):
        from backend.parse_output import _parse_arista_interface_status

        raw = {
            "TABLE_interface": {
                "ROW_interface": [
                    {
                        "interface": "Ethernet1/15",
                        "state": "down",
                        "state_rsn_desc": "linkFlapErrDisabled",
                        "eth_link_flapped": "14week(s) 2day(s)",
                        "eth_reset_cntr": "25",
                        "eth_mtu": "9216",
                        "eth_inerr": "12",
                        "eth_crc": "3",
                    }
                ]
            }
        }
        out = _parse_arista_interface_status(raw)
        rows = out["interface_status_rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["interface"], "Ethernet1/15")
        self.assertEqual(rows[0]["flap_count"], "25")
        self.assertEqual(rows[0]["last_link_flapped"], "14week(s) 2day(s)")
        self.assertEqual(rows[0]["in_errors"], "12")
        self.assertEqual(rows[0]["crc_count"], "3")

    def test_interfaces_dict_interface_counters_in_and_fcs(self):
        """Native EOS interfaces{} shape: interfaceCounters.inErrors / fcsErrors."""
        from backend.parse_output import _parse_arista_interface_status

        raw = {
            "interfaces": {
                "Ethernet1/1": {
                    "interfaceStatus": "connected",
                    "interfaceCounters": {
                        "inErrors": 7,
                        "fcsErrors": 2,
                        "linkStatusChanges": 4,
                    },
                    "mtu": 9216,
                }
            }
        }
        out = _parse_arista_interface_status(raw)
        rows = out["interface_status_rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["interface"], "Ethernet1/1")
        self.assertEqual(rows[0]["in_errors"], "7")
        self.assertEqual(rows[0]["crc_count"], "2")
        self.assertEqual(rows[0]["flap_count"], "4")

    def test_relative_week_day(self):
        from backend.parse_output import _parse_relative_seconds_ago

        sec = _parse_relative_seconds_ago("14week(s) 2day(s)")
        self.assertIsNotNone(sec)
        self.assertAlmostEqual(sec, 14 * 7 * 86400 + 2 * 86400, delta=1)


if __name__ == "__main__":
    unittest.main()
