"""Unit tests for ``backend.parsers.arista.arp``.

Pin the lookup contract: given an Arista 'show ip arp vrf all | json'
response and an IP, return the matching interface — but skip Vxlan
interfaces because the operator is looking for the underlay leaf.
"""

from __future__ import annotations

import pytest

from backend.parsers.arista.arp import parse_arista_arp_interface_for_ip


@pytest.fixture()
def arp_response_two_ips() -> dict:
    """Two ipv4 neighbors in the default vrf."""
    return {
        "vrfs": {
            "default": {
                "ipV4Neighbors": [
                    {"address": "10.0.0.1", "interface": "Ethernet1/1"},
                    {"address": "10.0.0.2", "interface": "Ethernet1/2"},
                ]
            }
        }
    }


class TestParseAristaArp:
    def test_returns_interface_for_match(self, arp_response_two_ips) -> None:
        assert parse_arista_arp_interface_for_ip(arp_response_two_ips, "10.0.0.1") == "Ethernet1/1"

    def test_returns_interface_for_second_match(self, arp_response_two_ips) -> None:
        assert parse_arista_arp_interface_for_ip(arp_response_two_ips, "10.0.0.2") == "Ethernet1/2"

    def test_returns_none_for_unknown_ip(self, arp_response_two_ips) -> None:
        assert parse_arista_arp_interface_for_ip(arp_response_two_ips, "10.99.99.99") is None

    def test_skips_vxlan_interface(self) -> None:
        raw = {
            "vrfs": {
                "default": {
                    "ipV4Neighbors": [{"address": "10.0.0.5", "interface": "Vxlan1"}]
                }
            }
        }
        assert parse_arista_arp_interface_for_ip(raw, "10.0.0.5") is None

    @pytest.mark.parametrize("ip", [None, "", "   "])
    def test_blank_ip_returns_none(self, arp_response_two_ips, ip) -> None:
        assert parse_arista_arp_interface_for_ip(arp_response_two_ips, ip) is None

    def test_non_dict_response_returns_none(self) -> None:
        assert parse_arista_arp_interface_for_ip(None, "10.0.0.1") is None
        assert parse_arista_arp_interface_for_ip("scalar", "10.0.0.1") is None

    def test_list_wrapped_response(self, arp_response_two_ips) -> None:
        # eAPI returns a list of results
        assert parse_arista_arp_interface_for_ip([arp_response_two_ips], "10.0.0.1") == "Ethernet1/1"

    def test_index_selects_response(self) -> None:
        responses = [
            {"vrfs": {}},  # index 0 — empty
            {
                "vrfs": {
                    "v": {"ipV4Neighbors": [{"address": "1.1.1.1", "interface": "Ethernet9/9"}]}
                }
            },  # index 1 — has the IP
        ]
        assert parse_arista_arp_interface_for_ip(responses, "1.1.1.1", index=1) == "Ethernet9/9"

    def test_skips_vrf_entries_that_arent_dicts(self) -> None:
        raw = {
            "vrfs": {
                "junk": "not-a-dict",
                "default": {
                    "ipV4Neighbors": [{"address": "1.1.1.1", "interface": "Ethernet1/1"}]
                },
            }
        }
        assert parse_arista_arp_interface_for_ip(raw, "1.1.1.1") == "Ethernet1/1"

    def test_skips_neighbor_entries_that_arent_dicts(self) -> None:
        raw = {
            "vrfs": {
                "default": {
                    "ipV4Neighbors": [
                        "junk",
                        {"address": "1.1.1.1", "interface": "Ethernet1/1"},
                    ]
                }
            }
        }
        assert parse_arista_arp_interface_for_ip(raw, "1.1.1.1") == "Ethernet1/1"
