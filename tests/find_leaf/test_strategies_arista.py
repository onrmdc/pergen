"""Unit tests for ``backend.find_leaf.strategies.arista``.

Covers the two functions extracted from the legacy ``find_leaf`` god-module
in wave-3 phase 8:

* ``_query_arista_leaf_search`` — issues the BGP-EVPN mac-ip eAPI call and
  parses the next-hop for ``search_ip``.
* ``_complete_arista_hit`` — resolves the next-hop into a leaf, fetches the
  leaf's ARP table, and parses the interface for ``search_ip``.

I/O boundaries (``arista_eapi.run_commands``, ``_get_credentials``) are
mocked so the tests are deterministic and run as pure-function unit tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.find_leaf.strategies.arista import (
    _complete_arista_hit,
    _query_arista_leaf_search,
)


# --------------------------------------------------------------------------- #
# _query_arista_leaf_search                                                    #
# --------------------------------------------------------------------------- #


class TestQueryAristaLeafSearch:
    @pytest.fixture
    def dev(self) -> dict:
        return {
            "hostname": "spine-1",
            "ip": "10.0.0.1",
            "credential": "c1",
            "vendor": "Arista",
        }

    def test_returns_none_when_no_credentials(self, dev) -> None:
        with patch(
            "backend.find_leaf.strategies.arista._get_credentials",
            return_value=("", ""),
        ):
            out = _query_arista_leaf_search(dev, "10.0.0.99", "secret", MagicMock())
        assert out is None

    def test_returns_none_when_runner_errors(self, dev) -> None:
        with patch(
            "backend.find_leaf.strategies.arista._get_credentials",
            return_value=("u", "p"),
        ), patch(
            "backend.runners.arista_eapi.run_commands",
            return_value=([], "boom"),
        ):
            out = _query_arista_leaf_search(dev, "10.0.0.99", "secret", MagicMock())
        assert out is None

    def test_returns_none_when_results_empty(self, dev) -> None:
        with patch(
            "backend.find_leaf.strategies.arista._get_credentials",
            return_value=("u", "p"),
        ), patch(
            "backend.runners.arista_eapi.run_commands",
            return_value=([], None),
        ):
            out = _query_arista_leaf_search(dev, "10.0.0.99", "secret", MagicMock())
        assert out is None

    def test_returns_none_when_next_hop_unparseable(self, dev) -> None:
        with patch(
            "backend.find_leaf.strategies.arista._get_credentials",
            return_value=("u", "p"),
        ), patch(
            "backend.runners.arista_eapi.run_commands",
            return_value=([{"x": 1}], None),
        ), patch(
            "backend.parse_output.parse_arista_bgp_evpn_next_hop",
            return_value=None,
        ):
            out = _query_arista_leaf_search(dev, "10.0.0.99", "secret", MagicMock())
        assert out is None

    def test_happy_path_returns_hit_dict(self, dev) -> None:
        with patch(
            "backend.find_leaf.strategies.arista._get_credentials",
            return_value=("user", "pass"),
        ), patch(
            "backend.runners.arista_eapi.run_commands",
            return_value=([{"json": "blob"}], None),
        ) as run_mock, patch(
            "backend.parse_output.parse_arista_bgp_evpn_next_hop",
            return_value="  10.0.0.20  ",  # whitespace stripped
        ):
            out = _query_arista_leaf_search(dev, "10.0.0.99", "secret", MagicMock())

        assert out is not None
        assert out["vendor"] == "arista"
        assert out["spine_ip"] == "10.0.0.1"
        assert out["spine_hostname"] == "spine-1"
        assert out["next_hop"] == "10.0.0.20"
        assert out["username"] == "user"
        assert out["password"] == "pass"
        assert out["dev"] is dev
        # Verify the eAPI command shape uses the canonical search_ip template.
        args, _ = run_mock.call_args
        assert args[3] == ["show bgp evpn route-type mac-ip 10.0.0.99 | json"]


# --------------------------------------------------------------------------- #
# _complete_arista_hit                                                         #
# --------------------------------------------------------------------------- #


class TestCompleteAristaHit:
    @pytest.fixture
    def base_hit(self) -> dict:
        return {
            "vendor": "arista",
            "spine_ip": "10.0.0.1",
            "spine_hostname": "spine-1",
            "next_hop": "192.168.1.20",
            "username": "u",
            "password": "p",
            "dev": {},
        }

    @pytest.fixture
    def devices(self) -> list:
        return [
            {
                "hostname": "leaf-A",
                "ip": "10.0.0.20",
                "credential": "c2",
                "fabric": "F1",
                "hall": "Hall-1",
                "site": "Mars",
            },
        ]

    def test_completes_with_arp_lookup_success(self, base_hit, devices) -> None:
        with patch(
            "backend.find_leaf.strategies.arista._get_credentials",
            return_value=("luser", "lpass"),
        ), patch(
            "backend.runners.arista_eapi.run_commands",
            return_value=([{"arp": "rows"}], None),
        ), patch(
            "backend.parse_output.parse_arista_arp_interface_for_ip",
            return_value="Ethernet1/9",
        ):
            out = _complete_arista_hit(
                base_hit, "10.0.0.99", devices, "secret", MagicMock()
            )

        assert out["found"] is True
        assert out["error"] is None
        assert out["leaf_hostname"] == "leaf-A"
        assert out["leaf_ip"] == "10.0.0.20"
        assert out["interface"] == "Ethernet1/9"
        assert out["vendor"] == "arista"
        assert out["fabric"] == "F1"
        assert out["hall"] == "Hall-1"
        assert out["site"] == "Mars"

    def test_no_arp_match_returns_empty_interface(self, base_hit, devices) -> None:
        with patch(
            "backend.find_leaf.strategies.arista._get_credentials",
            return_value=("u", "p"),
        ), patch(
            "backend.runners.arista_eapi.run_commands",
            return_value=([{"arp": "rows"}], None),
        ), patch(
            "backend.parse_output.parse_arista_arp_interface_for_ip",
            return_value=None,
        ):
            out = _complete_arista_hit(
                base_hit, "10.0.0.99", devices, "secret", MagicMock()
            )
        assert out["interface"] == ""

    def test_arp_runner_error_skips_iface(self, base_hit, devices) -> None:
        with patch(
            "backend.find_leaf.strategies.arista._get_credentials",
            return_value=("u", "p"),
        ), patch(
            "backend.runners.arista_eapi.run_commands",
            return_value=([], "arp_err"),
        ):
            out = _complete_arista_hit(
                base_hit, "10.0.0.99", devices, "secret", MagicMock()
            )
        assert out["interface"] == ""
        assert out["leaf_hostname"] == "leaf-A"

    def test_no_inventory_match_falls_back_to_lip(self, base_hit) -> None:
        # No leaf_dev → leaf_hostname = lip OR next_hop; fabric/hall/site empty.
        with patch(
            "backend.find_leaf.strategies.arista._get_credentials",
            return_value=("u", "p"),
        ), patch(
            "backend.runners.arista_eapi.run_commands",
            return_value=([], "err"),
        ):
            out = _complete_arista_hit(
                base_hit, "10.0.0.99", [], "secret", MagicMock()
            )
        # leaf_ip = combinator(spine 10.0.0.1, next_hop oct .20) → 10.0.0.20
        assert out["leaf_ip"] == "10.0.0.20"
        assert out["leaf_hostname"] == "10.0.0.20"
        assert out["fabric"] == ""
        assert out["hall"] == ""
        assert out["site"] == ""

    def test_invalid_next_hop_falls_back_to_raw(self) -> None:
        hit = {
            "vendor": "arista",
            "spine_ip": "10.0.0.1",
            "spine_hostname": "spine-1",
            "next_hop": "garbage",
            "username": "u",
            "password": "p",
            "dev": {},
        }
        with patch(
            "backend.find_leaf.strategies.arista._get_credentials",
            return_value=("u", "p"),
        ), patch(
            "backend.runners.arista_eapi.run_commands",
            return_value=([], "err"),
        ):
            out = _complete_arista_hit(hit, "10.0.0.99", [], "secret", MagicMock())
        # _leaf_ip_from_remote returns None → lip = next_hop = "garbage".
        assert out["leaf_ip"] == "garbage"

    def test_no_creds_skips_arp_call(self, devices) -> None:
        hit = {
            "vendor": "arista",
            "spine_ip": "10.0.0.1",
            "spine_hostname": "spine-1",
            "next_hop": "10.0.0.20",
            "username": "",
            "password": "",
            "dev": {},
        }
        # Force credentials lookup for the leaf to also be empty.
        with patch(
            "backend.find_leaf.strategies.arista._get_credentials",
            return_value=("", ""),
        ), patch(
            "backend.runners.arista_eapi.run_commands"
        ) as run_mock:
            out = _complete_arista_hit(hit, "10.0.0.99", devices, "secret", MagicMock())
        # No creds → no eAPI call.
        run_mock.assert_not_called()
        assert out["interface"] == ""

    def test_leaf_dev_credential_overrides_hit_creds(self, base_hit, devices) -> None:
        called_with = {}

        def fake_run(ip, user, pwd, cmds):
            called_with["user"] = user
            called_with["pwd"] = pwd
            return [{"arp": "rows"}], None

        with patch(
            "backend.find_leaf.strategies.arista._get_credentials",
            return_value=("leaf_user", "leaf_pwd"),
        ), patch(
            "backend.runners.arista_eapi.run_commands",
            side_effect=fake_run,
        ), patch(
            "backend.parse_output.parse_arista_arp_interface_for_ip",
            return_value="Et1/1",
        ):
            _complete_arista_hit(base_hit, "10.0.0.99", devices, "secret", MagicMock())

        assert called_with["user"] == "leaf_user"
        assert called_with["pwd"] == "leaf_pwd"
