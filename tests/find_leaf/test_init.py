"""Unit tests for the ``backend.find_leaf`` package shim.

Covers the vendor-dispatch wrappers (``_query_one_leaf_search`` and
``_complete_find_leaf_from_hit``) that route to the Arista or Cisco
strategies based on ``dev["vendor"]`` / ``hit["vendor"]``. These wrappers
are tiny but are the only call site for the strategies in production —
the late-binding shim pattern means tests must hit them via the
``backend.find_leaf`` namespace.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import backend.find_leaf as fl


# --------------------------------------------------------------------------- #
# _query_one_leaf_search                                                       #
# --------------------------------------------------------------------------- #


class TestQueryOneLeafSearchDispatch:
    def test_arista_routes_to_arista_strategy(self) -> None:
        sentinel = {"vendor": "arista", "hit": True}
        with patch(
            "backend.find_leaf._query_arista_leaf_search", return_value=sentinel
        ) as ma, patch(
            "backend.find_leaf._query_cisco_leaf_search", return_value=None
        ) as mc:
            out = fl._query_one_leaf_search(
                {"vendor": "Arista"}, "10.0.0.1", "key", MagicMock()
            )
        assert out is sentinel
        ma.assert_called_once()
        mc.assert_not_called()

    def test_cisco_routes_to_cisco_strategy(self) -> None:
        sentinel = {"vendor": "cisco", "hit": True}
        with patch(
            "backend.find_leaf._query_arista_leaf_search", return_value=None
        ) as ma, patch(
            "backend.find_leaf._query_cisco_leaf_search", return_value=sentinel
        ) as mc:
            out = fl._query_one_leaf_search(
                {"vendor": "Cisco"}, "10.0.0.1", "key", MagicMock()
            )
        assert out is sentinel
        mc.assert_called_once()
        ma.assert_not_called()

    @pytest.mark.parametrize("vendor", ["", "  ", "juniper", "fortinet", None])
    def test_unknown_vendor_returns_none(self, vendor) -> None:
        with patch(
            "backend.find_leaf._query_arista_leaf_search"
        ) as ma, patch(
            "backend.find_leaf._query_cisco_leaf_search"
        ) as mc:
            out = fl._query_one_leaf_search(
                {"vendor": vendor}, "10.0.0.1", "key", MagicMock()
            )
        assert out is None
        ma.assert_not_called()
        mc.assert_not_called()

    def test_vendor_normalised_strip_lower(self) -> None:
        # "  ARISTA  " should match the arista branch after .strip().lower().
        with patch(
            "backend.find_leaf._query_arista_leaf_search", return_value={"ok": True}
        ) as ma:
            out = fl._query_one_leaf_search(
                {"vendor": "  ARISTA  "}, "10.0.0.1", "k", MagicMock()
            )
        assert out == {"ok": True}
        ma.assert_called_once()


# --------------------------------------------------------------------------- #
# _complete_find_leaf_from_hit                                                 #
# --------------------------------------------------------------------------- #


class TestCompleteFindLeafFromHit:
    def test_arista_routes_to_arista_completer(self) -> None:
        sentinel = {"found": True, "vendor": "arista"}
        with patch(
            "backend.find_leaf._complete_arista_hit", return_value=sentinel
        ) as ma, patch(
            "backend.find_leaf._complete_cisco_hit", return_value={}
        ) as mc:
            out = fl._complete_find_leaf_from_hit(
                {"vendor": "arista"}, "10.0.0.1", [], "key", MagicMock()
            )
        assert out is sentinel
        ma.assert_called_once()
        mc.assert_not_called()

    def test_cisco_routes_to_cisco_completer(self) -> None:
        sentinel = {"found": True, "vendor": "cisco"}
        with patch(
            "backend.find_leaf._complete_arista_hit", return_value={}
        ) as ma, patch(
            "backend.find_leaf._complete_cisco_hit", return_value=sentinel
        ) as mc:
            out = fl._complete_find_leaf_from_hit(
                {"vendor": "cisco"}, "10.0.0.1", [], "key", MagicMock()
            )
        assert out is sentinel
        mc.assert_called_once()
        ma.assert_not_called()

    def test_unknown_vendor_returns_empty_envelope(self) -> None:
        out = fl._complete_find_leaf_from_hit(
            {"vendor": "junos"}, "10.0.0.1", [], "key", MagicMock()
        )
        assert out["found"] is True
        assert out["error"] is None
        assert out["leaf_hostname"] == ""
        assert out["leaf_ip"] == ""
        assert out["interface"] == ""
        assert out["vendor"] == ""
        assert out["fabric"] == ""
        assert out["hall"] == ""
        assert out["site"] == ""
        assert out["remote_vtep_addr"] == ""
        assert out["physical_iod"] == ""

    def test_missing_vendor_key_returns_empty_envelope(self) -> None:
        out = fl._complete_find_leaf_from_hit(
            {}, "10.0.0.1", [], "key", MagicMock()
        )
        assert out["found"] is True
        assert out["vendor"] == ""


class TestShimReExports:
    """Sanity checks that the shim re-exports the symbols tests/code import."""

    def test_ip_helpers_reexported(self) -> None:
        assert fl._is_valid_ip is not None
        assert fl._leaf_ip_from_remote is not None
        assert fl._IPV4_RE is not None

    def test_strategies_reexported(self) -> None:
        assert fl._query_arista_leaf_search is not None
        assert fl._complete_arista_hit is not None
        assert fl._query_cisco_leaf_search is not None
        assert fl._complete_cisco_hit is not None

    def test_public_api_reexported(self) -> None:
        assert callable(fl.find_leaf)
        assert callable(fl.find_leaf_check_device)
