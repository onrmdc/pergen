"""Unit tests for ``backend.find_leaf.strategies.cisco``.

Covers the two functions extracted from the legacy ``find_leaf`` god-module
in wave-3 phase 8:

* ``_query_cisco_leaf_search`` — issues the ARP-suppression NX-API call and
  parses the suppression entry for ``search_ip``.
* ``_complete_cisco_hit`` — resolves the hit's remote VTEP into a leaf,
  fetches the leaf's ARP table, parses the interface, and falls back to the
  parsed ``physical_iod`` when the ARP fetch fails.

I/O boundaries (``cisco_nxapi.run_commands``, ``_get_credentials``) are
mocked so the tests are deterministic and run as pure-function unit tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.find_leaf.strategies.cisco import (
    _complete_cisco_hit,
    _query_cisco_leaf_search,
)


# --------------------------------------------------------------------------- #
# _query_cisco_leaf_search                                                     #
# --------------------------------------------------------------------------- #


class TestQueryCiscoLeafSearch:
    @pytest.fixture
    def dev(self) -> dict:
        return {
            "hostname": "spine-1",
            "ip": "10.0.0.1",
            "credential": "c1",
            "vendor": "Cisco",
        }

    def test_returns_none_when_no_credentials(self, dev) -> None:
        with patch(
            "backend.find_leaf.strategies.cisco._get_credentials",
            return_value=("", ""),
        ):
            out = _query_cisco_leaf_search(dev, "10.0.0.99", "secret", MagicMock())
        assert out is None

    def test_returns_none_when_runner_errors(self, dev) -> None:
        with patch(
            "backend.find_leaf.strategies.cisco._get_credentials",
            return_value=("user", "pass"),
        ), patch(
            "backend.runners.cisco_nxapi.run_commands",
            return_value=([], "boom"),
        ):
            out = _query_cisco_leaf_search(dev, "10.0.0.99", "secret", MagicMock())
        assert out is None

    def test_returns_none_when_parse_returns_empty(self, dev) -> None:
        with patch(
            "backend.find_leaf.strategies.cisco._get_credentials",
            return_value=("user", "pass"),
        ), patch(
            "backend.runners.cisco_nxapi.run_commands",
            return_value=([{"raw": "no entry"}], None),
        ), patch(
            "backend.parse_output.parse_arp_suppression_for_ip",
            return_value=None,
        ):
            out = _query_cisco_leaf_search(dev, "10.0.0.99", "secret", MagicMock())
        assert out is None

    def test_returns_none_when_results_empty(self, dev) -> None:
        # results=[] → raw=None → parse skipped → returns None.
        with patch(
            "backend.find_leaf.strategies.cisco._get_credentials",
            return_value=("user", "pass"),
        ), patch(
            "backend.runners.cisco_nxapi.run_commands",
            return_value=([], None),
        ):
            out = _query_cisco_leaf_search(dev, "10.0.0.99", "secret", MagicMock())
        assert out is None

    def test_happy_path_returns_hit_dict(self, dev) -> None:
        parsed = {
            "remote_vtep_addr": "10.0.0.20",
            "physical_iod": "Ethernet1/5",
        }
        with patch(
            "backend.find_leaf.strategies.cisco._get_credentials",
            return_value=("user", "pass"),
        ), patch(
            "backend.runners.cisco_nxapi.run_commands",
            return_value=([{"raw": "blob"}], None),
        ) as run_mock, patch(
            "backend.parse_output.parse_arp_suppression_for_ip",
            return_value=parsed,
        ):
            out = _query_cisco_leaf_search(dev, "10.0.0.99", "secret", MagicMock())

        assert out is not None
        assert out["vendor"] == "cisco"
        assert out["spine_ip"] == "10.0.0.1"
        assert out["spine_hostname"] == "spine-1"
        assert out["parsed"] == parsed
        assert out["username"] == "user"
        assert out["password"] == "pass"
        assert out["dev"] is dev
        # NX-API must be invoked with the canonical command.
        args, kwargs = run_mock.call_args
        assert args[3] == ["show ip arp suppression-cache detail"]

    def test_handles_missing_hostname_and_ip(self) -> None:
        dev = {"hostname": "  ", "ip": "  ", "credential": "c1"}
        with patch(
            "backend.find_leaf.strategies.cisco._get_credentials",
            return_value=("u", "p"),
        ), patch(
            "backend.runners.cisco_nxapi.run_commands",
            return_value=([{"x": 1}], None),
        ), patch(
            "backend.parse_output.parse_arp_suppression_for_ip",
            return_value={"remote_vtep_addr": "1.1.1.1"},
        ):
            out = _query_cisco_leaf_search(dev, "10.0.0.99", "k", MagicMock())
        assert out is not None
        assert out["spine_ip"] == ""
        assert out["spine_hostname"] == ""


# --------------------------------------------------------------------------- #
# _complete_cisco_hit                                                          #
# --------------------------------------------------------------------------- #


class TestCompleteCiscoHit:
    @pytest.fixture
    def base_hit(self) -> dict:
        return {
            "vendor": "cisco",
            "spine_ip": "10.0.0.1",
            "spine_hostname": "spine-1",
            "parsed": {
                "remote_vtep_addr": "192.168.1.20",
                "physical_iod": "Ethernet1/5",
            },
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
            "backend.find_leaf.strategies.cisco._get_credentials",
            return_value=("luser", "lpass"),
        ), patch(
            "backend.runners.cisco_nxapi.run_commands",
            return_value=([{"arp": "rows"}], None),
        ), patch(
            "backend.parse_output.parse_cisco_arp_interface_for_ip",
            return_value="Ethernet1/9",
        ):
            out = _complete_cisco_hit(
                base_hit, "10.0.0.99", devices, "secret", MagicMock()
            )

        assert out["found"] is True
        assert out["error"] is None
        assert out["leaf_hostname"] == "leaf-A"
        assert out["leaf_ip"] == "10.0.0.20"
        assert out["interface"] == "Ethernet1/9"
        assert out["vendor"] == "cisco"
        assert out["fabric"] == "F1"
        assert out["hall"] == "Hall-1"
        assert out["site"] == "Mars"
        assert out["remote_vtep_addr"] == "192.168.1.20"
        assert out["physical_iod"] == "Ethernet1/5"

    def test_falls_back_to_physical_iod_when_arp_fails(self, base_hit, devices) -> None:
        with patch(
            "backend.find_leaf.strategies.cisco._get_credentials",
            return_value=("luser", "lpass"),
        ), patch(
            "backend.runners.cisco_nxapi.run_commands",
            return_value=([], "arp_err"),
        ):
            out = _complete_cisco_hit(
                base_hit, "10.0.0.99", devices, "secret", MagicMock()
            )
        # No interface from ARP — fallback to parsed.physical_iod.
        assert out["interface"] == "Ethernet1/5"

    def test_handles_arp_runner_exception(self, base_hit, devices) -> None:
        # cisco_nxapi.run_commands raising mid-call must not crash _complete_cisco_hit.
        with patch(
            "backend.find_leaf.strategies.cisco._get_credentials",
            return_value=("u", "p"),
        ), patch(
            "backend.runners.cisco_nxapi.run_commands",
            side_effect=RuntimeError("network down"),
        ):
            out = _complete_cisco_hit(
                base_hit, "10.0.0.99", devices, "secret", MagicMock()
            )
        assert out["found"] is True
        assert out["interface"] == "Ethernet1/5"  # falls back to physical_iod

    def test_uses_remote_vtep_when_no_inventory_match(self, base_hit) -> None:
        # No matching device for leaf_ip → leaf_hostname falls back to remote_vtep.
        with patch(
            "backend.find_leaf.strategies.cisco._get_credentials",
            return_value=("u", "p"),
        ), patch(
            "backend.runners.cisco_nxapi.run_commands",
            return_value=([], "err"),
        ):
            out = _complete_cisco_hit(
                base_hit, "10.0.0.99", [], "secret", MagicMock()
            )
        # No leaf_dev → leaf_hostname is the remote_vtep (since remote_vtep is set).
        assert out["leaf_hostname"] == "192.168.1.20"
        # leaf_ip = combinator of spine + remote octet 20 → 10.0.0.20
        assert out["leaf_ip"] == "10.0.0.20"
        assert out["fabric"] == ""
        assert out["hall"] == ""
        assert out["site"] == ""

    def test_no_remote_vtep_uses_spine_ip(self, devices) -> None:
        hit = {
            "vendor": "cisco",
            "spine_ip": "10.0.0.20",  # match a leaf device
            "spine_hostname": "spine-1",
            "parsed": {"remote_vtep_addr": "", "physical_iod": "Ethernet1/2"},
            "username": "u",
            "password": "p",
            "dev": {},
        }
        with patch(
            "backend.find_leaf.strategies.cisco._get_credentials",
            return_value=("u", "p"),
        ), patch(
            "backend.runners.cisco_nxapi.run_commands",
            return_value=([], "err"),
        ):
            out = _complete_cisco_hit(hit, "10.0.0.99", devices, "secret", MagicMock())
        # remote_vtep was empty, so leaf_ip = spine_ip = 10.0.0.20 → matches devices[0].
        assert out["leaf_ip"] == "10.0.0.20"
        assert out["leaf_hostname"] == "leaf-A"

    def test_no_credentials_skips_arp(self, base_hit, devices) -> None:
        # _get_credentials returns ("", "") for the leaf credential — but the
        # `or hit_creds` fallback means the arp call still happens.
        # Use a hit with empty creds to genuinely skip the arp branch.
        hit = {
            **base_hit,
            "username": "",
            "password": "",
        }
        with patch(
            "backend.find_leaf.strategies.cisco._get_credentials",
            return_value=("", ""),
        ), patch(
            "backend.runners.cisco_nxapi.run_commands"
        ) as run_mock:
            out = _complete_cisco_hit(hit, "10.0.0.99", devices, "secret", MagicMock())
        # No creds → no arp run.
        run_mock.assert_not_called()
        assert out["interface"] == "Ethernet1/5"

    def test_invalid_remote_vtep_falls_back(self, devices) -> None:
        hit = {
            "vendor": "cisco",
            "spine_ip": "10.0.0.1",
            "spine_hostname": "spine-1",
            "parsed": {"remote_vtep_addr": "garbage", "physical_iod": "Eth1/2"},
            "username": "u",
            "password": "p",
            "dev": {},
        }
        with patch(
            "backend.find_leaf.strategies.cisco._get_credentials",
            return_value=("u", "p"),
        ), patch(
            "backend.runners.cisco_nxapi.run_commands",
            return_value=([], "err"),
        ):
            out = _complete_cisco_hit(hit, "10.0.0.99", devices, "secret", MagicMock())
        # _leaf_ip_from_remote returned None for invalid VTEP → leaf_ip = remote or ip.
        assert out["leaf_ip"] == "garbage"
