"""Tests for Cisco NX-OS detailed interface parser (eth_crc, eth_inerr)."""
import os
import sys
import unittest

import pytest as _pytest_for_marker  # noqa: F401

pytestmark = [_pytest_for_marker.mark.unit]

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)


class TestCiscoInterfaceDetailed(unittest.TestCase):
    def test_eth_crc_and_inerr_without_flap(self):
        from backend.parse_output import _parse_cisco_interface_detailed

        raw = {
            "TABLE_interface": {
                "ROW_interface": [
                    {
                        "interface": "Ethernet1/1",
                        "state": "eth-up",
                        "eth_crc": "3",
                        "eth_inerr": "12",
                    }
                ]
            }
        }
        out = _parse_cisco_interface_detailed(raw)
        rows = out["interface_flapped_rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["crc_count"], "3")
        self.assertEqual(rows[0]["in_errors"], "12")
        self.assertEqual(rows[0]["last_link_flapped"], "-")


if __name__ == "__main__":
    unittest.main()
