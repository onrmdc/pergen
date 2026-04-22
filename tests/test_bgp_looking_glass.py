"""Unit tests for backend.bgp_looking_glass with mocked requests."""
import os
import sys
import unittest
from unittest.mock import patch

import pytest as _pytest_for_marker  # noqa: F401

pytestmark = [_pytest_for_marker.mark.integration]

# Ensure project root is on path so "backend" can be imported
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)


class TestNormalizeResource(unittest.TestCase):
    def test_empty(self):
        from backend.bgp_looking_glass import normalize_resource
        r, k = normalize_resource("")
        self.assertEqual(r, "")
        self.assertEqual(k, "")

    def test_prefix_bare_ip(self):
        from backend.bgp_looking_glass import normalize_resource
        r, k = normalize_resource("1.1.1.0")
        self.assertEqual(r, "1.1.1.0/24")
        self.assertEqual(k, "prefix")

    def test_prefix_cidr(self):
        from backend.bgp_looking_glass import normalize_resource
        r, k = normalize_resource("192.168.0.0/16")
        self.assertEqual(r, "192.168.0.0/16")
        self.assertEqual(k, "prefix")

    def test_asn_number(self):
        from backend.bgp_looking_glass import normalize_resource
        r, k = normalize_resource("13335")
        self.assertEqual(r, "AS13335")
        self.assertEqual(k, "asn")

    def test_asn_with_prefix(self):
        from backend.bgp_looking_glass import normalize_resource
        r, k = normalize_resource("AS13335")
        self.assertEqual(r, "AS13335")
        self.assertEqual(k, "asn")


class TestGetBgpStatus(unittest.TestCase):
    @patch("backend.bgp_looking_glass._get_json")
    def test_empty_resource(self, mock_get):
        from backend.bgp_looking_glass import get_bgp_status
        out = get_bgp_status("")
        self.assertIn("error", out)
        self.assertTrue("Empty" in (out.get("error") or ""))

    @patch("backend.bgp_looking_glass._get_json")
    def test_routing_status_error(self, mock_get):
        from backend.bgp_looking_glass import get_bgp_status
        mock_get.return_value = {"_error": "timeout"}
        out = get_bgp_status("1.1.1.0/24")
        self.assertEqual(out.get("error"), "timeout")

    @patch("backend.bgp_looking_glass._get_json")
    def test_routing_status_ok(self, mock_get):
        from backend.bgp_looking_glass import get_bgp_status
        mock_get.side_effect = [
            {"data": {"origins": [{"origin": 13335}], "last_seen": {"visibility": {"v4": {"ris_peers_seeing": 100, "total_ris_peers": 200}}}}},
            {"data": {"status": "valid"}},
            {"data": [{"name": "Cloudflare"}]},
        ]
        out = get_bgp_status("1.1.1.0/24")
        self.assertIsNone(out.get("error"))
        self.assertTrue(out.get("announced"))
        self.assertEqual(out.get("origin_as"), "13335")
        self.assertEqual(out.get("rpki_status"), "Valid")
        self.assertEqual(out.get("as_name"), "Cloudflare")


class TestGetBgpLookingGlass(unittest.TestCase):
    @patch("backend.bgp_looking_glass._get_json")
    def test_empty_resource(self, mock_get):
        from backend.bgp_looking_glass import get_bgp_looking_glass
        out = get_bgp_looking_glass("")
        self.assertIn("error", out)
        self.assertTrue("Empty" in (out.get("error") or ""))

    @patch("backend.bgp_looking_glass._get_json")
    def test_api_error(self, mock_get):
        from backend.bgp_looking_glass import get_bgp_looking_glass
        mock_get.return_value = {"_error": "timeout"}
        out = get_bgp_looking_glass("1.1.1.0/24")
        self.assertEqual(out.get("error"), "timeout")

    @patch("backend.bgp_looking_glass._get_json")
    def test_ok_flat_peers(self, mock_get):
        from backend.bgp_looking_glass import get_bgp_looking_glass
        mock_get.return_value = {
            "data": {
                "rrcs": [
                    {"rrc": 0, "location": "Amsterdam", "peers": [{"peer": "10.0.0.1", "as_number": 3333}]},
                ]
            }
        }
        out = get_bgp_looking_glass("1.1.1.0/24")
        self.assertIsNone(out.get("error"))
        self.assertEqual(len(out.get("peers", [])), 1)
        self.assertEqual(out["peers"][0]["ip"], "10.0.0.1")
        self.assertEqual(out["peers"][0]["as_number"], "3333")
        self.assertEqual(len(out.get("rrcs", [])), 1)


class TestGetBgpPlay(unittest.TestCase):
    @patch("backend.bgp_looking_glass._get_json")
    def test_empty_resource(self, mock_get):
        from backend.bgp_looking_glass import get_bgp_play
        out = get_bgp_play("")
        self.assertIn("error", out)
        self.assertTrue("Empty" in (out.get("error") or ""))

    @patch("backend.bgp_looking_glass._get_json")
    def test_api_error(self, mock_get):
        from backend.bgp_looking_glass import get_bgp_play
        mock_get.return_value = {"_error": "timeout"}
        out = get_bgp_play("1.1.1.0/24")
        self.assertEqual(out.get("error"), "timeout")

    @patch("backend.bgp_looking_glass._get_json")
    def test_ok_path_changes(self, mock_get):
        from backend.bgp_looking_glass import get_bgp_play
        mock_get.return_value = {
            "data": {
                "query_starttime": "2024-12-21T07:00:00",
                "query_endtime": "2024-12-21T15:00:00",
                "initial_state": [{"source_id": 1, "target_prefix": "1.1.1.0/24", "path": [3333, 13335]}],
                "events": [
                    {"attrs": {"source_id": 1, "target_prefix": "1.1.1.0/24", "path": [3333, 13335, 15169]}, "timestamp": "2024-12-21T10:00:00"},
                ],
                "sources": [{"id": 1, "ip": "10.0.0.1", "as_number": 3333, "rrc": 0}],
                "nodes": [{"as_number": 3333, "owner": "RIPE NCC"}],
            }
        }
        out = get_bgp_play("1.1.1.0/24", starttime="1703145600", endtime="1703174400")
        self.assertIsNone(out.get("error"))
        self.assertEqual(out.get("query_starttime"), "2024-12-21T07:00:00")
        self.assertEqual(len(out.get("path_changes", [])), 1)
        pc = out["path_changes"][0]
        self.assertEqual(pc["target_prefix"], "1.1.1.0/24")
        self.assertEqual(pc["previous_path"], [3333, 13335])
        self.assertEqual(pc["new_path"], [3333, 13335, 15169])
        self.assertEqual(pc["source_as"], 3333)
        self.assertEqual(pc["source_owner"], "RIPE NCC")


if __name__ == "__main__":
    unittest.main()
