"""Unit tests for ``backend.bgp_looking_glass.ripestat`` format/parse helpers.

Covers the RIPEStat-specific request shaping and response parsing that was
extracted from the legacy god-module in wave-3 phase 8:

* ``parse_routing_status``     — visibility / origin / announced flags
* ``fetch_routing_status``     — request shape (mocked _get_json)
* ``fetch_rpki_validation``    — happy + unknown branches
* ``fetch_visibility``         — peers seeing / total / percentage
* ``fetch_as_overview``        — holder/name + invalid-ASN error
* ``fetch_announced_prefixes`` — prefixes list + invalid-ASN error
* ``_clean_asn`` / ``_entry_to_text`` — pure helpers

The HTTP layer (``_get_json``) is patched on the package shim so the
late-bound ``_shim_get_json`` proxy resolves to the mock at call time.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.bgp_looking_glass.ripestat import (
    _clean_asn,
    _entry_to_text,
    fetch_announced_prefixes,
    fetch_as_overview,
    fetch_routing_status,
    fetch_rpki_validation,
    fetch_visibility,
    parse_routing_status,
)


# --------------------------------------------------------------------------- #
# parse_routing_status                                                         #
# --------------------------------------------------------------------------- #


class TestParseRoutingStatus:
    def test_announced_with_origin_dict(self) -> None:
        data = {"data": {"origins": [{"origin": "AS65001"}]}}
        out = parse_routing_status(data)
        assert out["announced"] is True
        assert out["withdrawn"] is False
        assert out["origin_as"] == "65001"

    def test_announced_with_origin_int(self) -> None:
        data = {"data": {"origins": [12345]}}
        out = parse_routing_status(data)
        assert out["origin_as"] == "12345"

    def test_announcements_alias_for_origins(self) -> None:
        data = {"data": {"announcements": [{"origin_asn": "AS9999"}]}}
        out = parse_routing_status(data)
        assert out["announced"] is True
        assert out["origin_as"] == "9999"

    def test_withdrawn_when_no_origins(self) -> None:
        data = {"data": {"origins": []}}
        out = parse_routing_status(data)
        assert out["announced"] is False
        assert out["withdrawn"] is True
        assert out["origin_as"] is None

    def test_visibility_summary_from_last_seen(self) -> None:
        data = {
            "data": {
                "origins": [{"origin": "1"}],
                "last_seen": {
                    "visibility": {"v4": {"ris_peers_seeing": 50, "total_ris_peers": 60}}
                },
            }
        }
        out = parse_routing_status(data)
        assert out["visibility_summary"] == {"peers_seeing": 50, "total_peers": 60}

    def test_visibility_summary_from_top_level(self) -> None:
        data = {
            "data": {
                "origins": [{"origin": "1"}],
                "visibility": {"v4": {"peers_seeing": 100, "total_peers": 120}},
            }
        }
        out = parse_routing_status(data)
        assert out["visibility_summary"] == {"peers_seeing": 100, "total_peers": 120}

    def test_empty_payload(self) -> None:
        out = parse_routing_status({})
        assert out["announced"] is False
        assert out["origin_as"] is None
        assert out["visibility_summary"] is None


# --------------------------------------------------------------------------- #
# fetch_routing_status                                                         #
# --------------------------------------------------------------------------- #


class TestFetchRoutingStatus:
    def test_passes_resource_to_get_json(self) -> None:
        with patch(
            "backend.bgp_looking_glass._get_json",
            return_value={"data": {"origins": []}},
        ) as gj:
            out = fetch_routing_status("8.8.8.8")
        assert out == {"data": {"origins": []}}
        args, _ = gj.call_args
        assert "/routing-status/data.json" in args[0]
        assert args[1] == {"resource": "8.8.8.8"}

    def test_returns_empty_dict_on_none(self) -> None:
        with patch("backend.bgp_looking_glass._get_json", return_value=None):
            assert fetch_routing_status("8.8.8.8") == {}


# --------------------------------------------------------------------------- #
# fetch_rpki_validation                                                        #
# --------------------------------------------------------------------------- #


class TestFetchRpkiValidation:
    def test_returns_capitalised_status(self) -> None:
        with patch(
            "backend.bgp_looking_glass._get_json",
            return_value={"data": {"status": "valid"}},
        ):
            assert fetch_rpki_validation("AS15169", "8.8.8.0/24") == "Valid"

    def test_returns_unknown_on_error(self) -> None:
        with patch(
            "backend.bgp_looking_glass._get_json",
            return_value={"_error": "boom"},
        ):
            assert fetch_rpki_validation("AS1", "1.1.1.0/24") == "Unknown"

    def test_returns_unknown_on_none(self) -> None:
        with patch("backend.bgp_looking_glass._get_json", return_value=None):
            assert fetch_rpki_validation("AS1", "1.1.1.0/24") == "Unknown"

    def test_returns_unknown_when_no_status_field(self) -> None:
        with patch(
            "backend.bgp_looking_glass._get_json", return_value={"data": {}}
        ):
            # Default "unknown" → capitalised.
            assert fetch_rpki_validation("AS1", "1.1.1.0/24") == "Unknown"


# --------------------------------------------------------------------------- #
# fetch_visibility                                                             #
# --------------------------------------------------------------------------- #


class TestFetchVisibility:
    def test_happy_path_with_visibility_dict(self) -> None:
        # The parser branches require ``visibility`` to be a dict before
        # consulting the top-level keys (an oddity of the legacy ternary).
        with patch(
            "backend.bgp_looking_glass._get_json",
            return_value={
                "data": {
                    "peers_seeing": 80,
                    "total_peers": 100,
                    "visibility": {},  # presence enables the branch
                }
            },
        ):
            out = fetch_visibility("8.8.8.8")
        assert out["probes_seeing"] == 80
        assert out["total_probes"] == 100
        assert out["percentage"] == 80.0
        assert out["error"] is None

    def test_happy_path_with_nested_visibility_keys(self) -> None:
        with patch(
            "backend.bgp_looking_glass._get_json",
            return_value={
                "data": {
                    "visibility": {"peers_seeing": 60, "total_peers": 80}
                }
            },
        ):
            out = fetch_visibility("8.8.8.8")
        assert out["probes_seeing"] == 60
        assert out["total_probes"] == 80
        assert out["percentage"] == 75.0

    def test_error_envelope(self) -> None:
        with patch(
            "backend.bgp_looking_glass._get_json", return_value={"_error": "boom"}
        ):
            out = fetch_visibility("8.8.8.8")
        assert out["error"] == "boom"
        assert out["probes_seeing"] is None

    def test_no_data_envelope(self) -> None:
        with patch("backend.bgp_looking_glass._get_json", return_value=None):
            out = fetch_visibility("8.8.8.8")
        assert out["error"] == "No visibility data"

    def test_zero_total_skips_percentage(self) -> None:
        with patch(
            "backend.bgp_looking_glass._get_json",
            return_value={
                "data": {
                    "peers_seeing": 0,
                    "total_peers": 0,
                    "visibility": {},
                }
            },
        ):
            out = fetch_visibility("8.8.8.8")
        assert out["percentage"] is None


# --------------------------------------------------------------------------- #
# fetch_as_overview                                                            #
# --------------------------------------------------------------------------- #


class TestFetchAsOverview:
    def test_happy_path_returns_holder_name(self) -> None:
        with patch(
            "backend.bgp_looking_glass._get_json",
            return_value={"data": {"holder": "Google LLC"}},
        ):
            out = fetch_as_overview("AS15169")
        assert out == {"asn": "AS15169", "name": "Google LLC"}

    def test_invalid_asn(self) -> None:
        out = fetch_as_overview("not-an-asn")
        assert out["error"] == "Invalid ASN"
        assert out["name"] is None

    def test_empty_asn(self) -> None:
        out = fetch_as_overview("")
        assert out["error"] == "Invalid ASN"

    def test_error_in_response(self) -> None:
        with patch(
            "backend.bgp_looking_glass._get_json",
            return_value={"_error": "ripestat down"},
        ):
            out = fetch_as_overview("15169")
        assert out["asn"] == "AS15169"
        assert out["error"] == "ripestat down"

    def test_no_data_returns_name_none(self) -> None:
        with patch("backend.bgp_looking_glass._get_json", return_value={}):
            out = fetch_as_overview("AS15169")
        assert out == {"asn": "AS15169", "name": None}

    def test_blank_holder_returns_none_name(self) -> None:
        with patch(
            "backend.bgp_looking_glass._get_json",
            return_value={"data": {"holder": "   "}},
        ):
            out = fetch_as_overview("AS1")
        assert out["name"] is None


# --------------------------------------------------------------------------- #
# fetch_announced_prefixes                                                     #
# --------------------------------------------------------------------------- #


class TestFetchAnnouncedPrefixes:
    def test_happy_path_extracts_prefixes(self) -> None:
        with patch(
            "backend.bgp_looking_glass._get_json",
            return_value={
                "data": {
                    "prefixes": [
                        {"prefix": "8.8.8.0/24"},
                        {"prefix": "8.8.4.0/24"},
                    ]
                }
            },
        ):
            out = fetch_announced_prefixes("AS15169")
        assert out == {"prefixes": ["8.8.8.0/24", "8.8.4.0/24"]}

    def test_handles_string_entries(self) -> None:
        with patch(
            "backend.bgp_looking_glass._get_json",
            return_value={"data": {"prefixes": ["10.0.0.0/8"]}},
        ):
            out = fetch_announced_prefixes("AS1")
        assert out == {"prefixes": ["10.0.0.0/8"]}

    def test_invalid_asn_returns_empty(self) -> None:
        out = fetch_announced_prefixes("garbage")
        assert out == {"prefixes": [], "error": "Invalid ASN"}

    def test_error_in_response(self) -> None:
        with patch(
            "backend.bgp_looking_glass._get_json",
            return_value={"_error": "ripestat down"},
        ):
            out = fetch_announced_prefixes("15169")
        assert out["error"] == "ripestat down"
        assert out["prefixes"] == []

    def test_no_data_returns_empty(self) -> None:
        with patch("backend.bgp_looking_glass._get_json", return_value={}):
            out = fetch_announced_prefixes("AS1")
        assert out == {"prefixes": []}


# --------------------------------------------------------------------------- #
# Pure helpers                                                                 #
# --------------------------------------------------------------------------- #


class TestCleanAsn:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("AS15169", "15169"),
            ("as15169", "15169"),
            (" 15169 ", "15169"),
            ("AS1", "1"),
            (None, ""),
            ("", ""),
        ],
    )
    def test_strips_as_prefix(self, raw, expected) -> None:
        assert _clean_asn(raw) == expected


class TestEntryToText:
    def test_serialises_dict_sorted(self) -> None:
        out = _entry_to_text({"b": 2, "a": 1})
        # Sorted by key.
        assert out == "a: 1\nb: 2"

    def test_skips_none_and_blank_values(self) -> None:
        out = _entry_to_text({"a": None, "b": "  ", "c": "x"})
        assert out == "c: x"

    def test_non_dict_input_returns_empty(self) -> None:
        assert _entry_to_text(None) == ""
        assert _entry_to_text("scalar") == ""
        assert _entry_to_text([]) == ""
