"""Transceiver recovery policy: Leaf + Ethernet1/1-1/48 only."""
import os
import sys
import unittest

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)


class TestTransceiverRecoveryPolicy(unittest.TestCase):
    def test_host_port_patterns(self):
        from backend.transceiver_recovery_policy import is_ethernet_module1_host_port

        self.assertTrue(is_ethernet_module1_host_port("Ethernet1/1"))
        self.assertTrue(is_ethernet_module1_host_port("ethernet1/48"))
        self.assertTrue(is_ethernet_module1_host_port("Eth1/12"))
        self.assertTrue(is_ethernet_module1_host_port("Et1/3"))
        self.assertTrue(is_ethernet_module1_host_port("1/1"))
        self.assertTrue(is_ethernet_module1_host_port("1/48"))
        self.assertFalse(is_ethernet_module1_host_port("Ethernet1/49"))
        self.assertFalse(is_ethernet_module1_host_port("Ethernet2/1"))
        self.assertFalse(is_ethernet_module1_host_port("Port-Channel1"))

    def test_leaf_only(self):
        from backend.transceiver_recovery_policy import is_transceiver_recovery_allowed

        leaf = {"role": "Leaf"}
        spine = {"role": "Spine"}
        self.assertTrue(is_transceiver_recovery_allowed(leaf, "Ethernet1/5"))
        self.assertFalse(is_transceiver_recovery_allowed(spine, "Ethernet1/5"))
        self.assertFalse(is_transceiver_recovery_allowed(leaf, "Ethernet2/5"))


if __name__ == "__main__":
    unittest.main()
