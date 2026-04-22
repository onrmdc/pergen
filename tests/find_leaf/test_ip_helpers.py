"""Unit tests for ``backend.find_leaf.ip_helpers``.

Covers the IPv4 validator (``_is_valid_ip``) and the leaf-IP combinator
(``_leaf_ip_from_remote``) extracted from the legacy ``backend/find_leaf.py``
god-module in wave-3 phase 8.

Both helpers are pure functions — no I/O — so the tests are simple
parametric coverage of the happy paths and every malformed-input branch.
"""

from __future__ import annotations

import pytest

from backend.find_leaf.ip_helpers import (
    _IPV4_RE,
    _is_valid_ip,
    _leaf_ip_from_remote,
)


class TestIsValidIp:
    @pytest.mark.parametrize(
        "ip",
        [
            "0.0.0.0",
            "10.0.0.1",
            "192.168.1.1",
            "255.255.255.255",
            "1.2.3.4",
            "100.200.50.25",
        ],
    )
    def test_valid_dotted_quads(self, ip: str) -> None:
        assert _is_valid_ip(ip) is True

    @pytest.mark.parametrize(
        "ip",
        [
            "",
            "   ",
            None,
            "not-an-ip",
            "10.0.0",          # 3 octets
            "10.0.0.0.0",      # 5 octets
            "256.0.0.1",       # > 255
            "10.0.0.999",      # > 255 in last
            "10.0.0.-1",       # negative
            "abc.def.ghi.jkl", # alpha
            "10.0.0.1 ",       # trailing space — _is_valid_ip strips first then matches
        ],
    )
    def test_invalid_inputs(self, ip) -> None:
        # Trailing space is stripped before regex match — so "10.0.0.1 " IS valid.
        # Override the assertion for the strip-recoverable case.
        if ip == "10.0.0.1 ":
            assert _is_valid_ip(ip) is True
        else:
            assert _is_valid_ip(ip) is False

    def test_regex_object_exposed(self) -> None:
        # _IPV4_RE is part of the public-private surface; ensure it compiles.
        assert _IPV4_RE.match("10.0.0.1") is not None
        assert _IPV4_RE.match("999.0.0.1") is None

    def test_strips_whitespace(self) -> None:
        assert _is_valid_ip("  10.1.2.3  ") is True


class TestLeafIpFromRemote:
    def test_canonical_combination(self) -> None:
        # First 3 octets from current, last from remote_vtep.
        assert _leaf_ip_from_remote("10.10.20.30", "192.168.1.99") == "10.10.20.99"

    def test_identical_subnet(self) -> None:
        assert _leaf_ip_from_remote("172.16.5.1", "172.16.5.250") == "172.16.5.250"

    def test_strips_inputs(self) -> None:
        assert _leaf_ip_from_remote("  10.0.0.1  ", "  192.168.1.50 ") == "10.0.0.50"

    @pytest.mark.parametrize(
        "current,remote",
        [
            ("", "1.2.3.4"),
            ("1.2.3.4", ""),
            (None, "1.2.3.4"),
            ("1.2.3.4", None),
            ("not-an-ip", "1.2.3.4"),
            ("1.2.3.4", "garbage"),
            ("256.0.0.0", "1.2.3.4"),
            ("1.2.3.4", "256.0.0.0"),
        ],
    )
    def test_invalid_inputs_return_none(self, current, remote) -> None:
        assert _leaf_ip_from_remote(current, remote) is None

    def test_zero_octet(self) -> None:
        assert _leaf_ip_from_remote("10.0.0.1", "192.168.1.0") == "10.0.0.0"
