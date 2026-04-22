"""Unit tests for ``backend.route_map_analysis.comparator``.

Covers ``build_unified_bgp_full_table`` and the ``_device_order_key`` sort
helper extracted from the legacy god-module in wave-3 phase 8.

These are pure functions over already-parsed device dicts (the parser
output from ``analyze_router_config``). No mocking required.
"""

from __future__ import annotations

import pytest

from backend.route_map_analysis.comparator import (
    _device_order_key,
    build_unified_bgp_full_table,
)


# --------------------------------------------------------------------------- #
# _device_order_key                                                            #
# --------------------------------------------------------------------------- #


class TestDeviceOrderKey:
    def test_n01_sorts_before_n02(self) -> None:
        keys = sorted(["leaf-N02", "leaf-N01"], key=_device_order_key)
        assert keys == ["leaf-N01", "leaf-N02"]

    def test_other_hostnames_sort_after(self) -> None:
        keys = sorted(["leaf-X", "leaf-N01", "leaf-N02"], key=_device_order_key)
        assert keys == ["leaf-N01", "leaf-N02", "leaf-X"]

    @pytest.mark.parametrize(
        "host,bucket",
        [("spine-N01", 0), ("spine-N02", 1), ("border", 2), ("", 2), (None, 2)],
    )
    def test_bucket_assignment(self, host, bucket) -> None:
        key = _device_order_key(host)
        assert key[0] == bucket


# --------------------------------------------------------------------------- #
# build_unified_bgp_full_table                                                 #
# --------------------------------------------------------------------------- #


class TestBuildUnifiedBgpFullTable:
    def test_empty_input_returns_empty_list(self) -> None:
        assert build_unified_bgp_full_table([]) == []

    def test_none_safe(self) -> None:
        # Falsy → empty.
        assert build_unified_bgp_full_table(None) == []

    def test_single_device_minimal(self) -> None:
        parsed = {
            "bgp_neighbor_to_group": {"10.1.1.1": "PG-A"},
            "bgp_route_maps": {"PG-A": {"in": "RM-IN", "out": "RM-OUT"}},
            "route_map_prefix_lists": {"RM-IN": ["PL-A"], "RM-OUT": ["PL-B"]},
            "prefix_lists": {
                "PL-A": [{"seq": 10, "action": "permit", "prefix": "10.0.0.0/8"}],
                "PL-B": [{"seq": 10, "action": "permit", "prefix": "192.168.0.0/16"}],
            },
        }
        rows = build_unified_bgp_full_table(
            [{"hostname": "leaf-N01", "parsed": parsed}]
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["peer_group"] == "PG-A"
        assert row["route_map_in"] == "RM-IN"
        assert row["route_map_out"] == "RM-OUT"
        assert row["devices"] == ["leaf-N01"]
        assert row["hierarchy_in"] == [
            {"prefix_list": "PL-A", "prefixes": ["10.0.0.0/8"]}
        ]
        assert row["hierarchy_out"] == [
            {"prefix_list": "PL-B", "prefixes": ["192.168.0.0/16"]}
        ]

    def test_two_devices_same_group_merge(self) -> None:
        # Same peer-group on both devices, different prefix-list contents.
        parsed_a = {
            "bgp_neighbor_to_group": {"1.1.1.1": "PG-X"},
            "bgp_route_maps": {"PG-X": {"in": "RM-A"}},
            "route_map_prefix_lists": {"RM-A": ["PL-1"]},
            "prefix_lists": {
                "PL-1": [{"seq": 10, "action": "permit", "prefix": "10.0.0.0/8"}],
            },
        }
        parsed_b = {
            "bgp_neighbor_to_group": {"2.2.2.2": "PG-X"},
            "bgp_route_maps": {"PG-X": {"in": "RM-A"}},
            "route_map_prefix_lists": {"RM-A": ["PL-1"]},
            "prefix_lists": {
                "PL-1": [{"seq": 20, "action": "permit", "prefix": "172.16.0.0/12"}],
            },
        }
        rows = build_unified_bgp_full_table(
            [
                {"hostname": "leaf-N01", "parsed": parsed_a},
                {"hostname": "leaf-N02", "parsed": parsed_b},
            ]
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["devices"] == ["leaf-N01", "leaf-N02"]
        assert row["route_map_in"] == "RM-A"
        # Merged prefix list contains both entries from both devices.
        merged = row["hierarchy_in"]
        assert len(merged) == 1
        assert merged[0]["prefix_list"] == "PL-1"
        assert merged[0]["prefixes"] == ["10.0.0.0/8", "172.16.0.0/12"]

    def test_different_route_maps_join_with_comma(self) -> None:
        parsed_a = {
            "bgp_neighbor_to_group": {"1.1.1.1": "PG-Y"},
            "bgp_route_maps": {"PG-Y": {"in": "RM-A"}},
            "route_map_prefix_lists": {},
            "prefix_lists": {},
        }
        parsed_b = {
            "bgp_neighbor_to_group": {"2.2.2.2": "PG-Y"},
            "bgp_route_maps": {"PG-Y": {"in": "RM-B"}},
            "route_map_prefix_lists": {},
            "prefix_lists": {},
        }
        rows = build_unified_bgp_full_table(
            [
                {"hostname": "h1", "parsed": parsed_a},
                {"hostname": "h2", "parsed": parsed_b},
            ]
        )
        assert rows[0]["route_map_in"] == "RM-A, RM-B"
        # No outbound configured → em-dash placeholder.
        assert rows[0]["route_map_out"] == "—"

    def test_no_route_map_uses_em_dash(self) -> None:
        parsed = {
            "bgp_neighbor_to_group": {"1.1.1.1": "PG-Z"},
            "bgp_route_maps": {},
            "route_map_prefix_lists": {},
            "prefix_lists": {},
        }
        rows = build_unified_bgp_full_table([{"hostname": "h", "parsed": parsed}])
        assert rows[0]["route_map_in"] == "—"
        assert rows[0]["route_map_out"] == "—"
        assert rows[0]["hierarchy_in"] == []

    def test_route_map_lookup_via_neighbor_ip(self) -> None:
        # When ``bgp_route_maps[group]`` is missing, the comparator falls back
        # to looking up the route-map under one of the neighbor IPs.
        parsed = {
            "bgp_neighbor_to_group": {"10.1.1.1": "PG-A", "10.1.1.2": "PG-A"},
            "bgp_route_maps": {"10.1.1.1": {"in": "RM-VIA-IP"}},
            "route_map_prefix_lists": {},
            "prefix_lists": {},
        }
        rows = build_unified_bgp_full_table([{"hostname": "h", "parsed": parsed}])
        assert rows[0]["route_map_in"] == "RM-VIA-IP"

    def test_skips_empty_groups(self) -> None:
        parsed = {
            "bgp_neighbor_to_group": {"1.1.1.1": "", "2.2.2.2": "  "},
            "bgp_route_maps": {},
            "route_map_prefix_lists": {},
            "prefix_lists": {},
        }
        rows = build_unified_bgp_full_table([{"hostname": "h", "parsed": parsed}])
        assert rows == []

    def test_rows_sorted_by_peer_group(self) -> None:
        parsed = {
            "bgp_neighbor_to_group": {"1.1.1.1": "ZULU", "2.2.2.2": "ALPHA"},
            "bgp_route_maps": {},
            "route_map_prefix_lists": {},
            "prefix_lists": {},
        }
        rows = build_unified_bgp_full_table([{"hostname": "h", "parsed": parsed}])
        assert [r["peer_group"] for r in rows] == ["ALPHA", "ZULU"]

    def test_handles_missing_parsed_key(self) -> None:
        # A device dict without a "parsed" key should be tolerated gracefully.
        rows = build_unified_bgp_full_table([{"hostname": "h"}])
        assert rows == []

    def test_dedups_prefixes_within_pl(self) -> None:
        parsed = {
            "bgp_neighbor_to_group": {"1.1.1.1": "PG"},
            "bgp_route_maps": {"PG": {"in": "RM"}},
            "route_map_prefix_lists": {"RM": ["PL"]},
            "prefix_lists": {
                "PL": [
                    {"seq": 10, "action": "permit", "prefix": "10.0.0.0/8"},
                    {"seq": 20, "action": "permit", "prefix": "10.0.0.0/8"},  # dup
                    {"seq": 30, "action": "permit", "prefix": ""},  # dropped
                ],
            },
        }
        rows = build_unified_bgp_full_table([{"hostname": "h", "parsed": parsed}])
        assert rows[0]["hierarchy_in"][0]["prefixes"] == ["10.0.0.0/8"]

    def test_hierarchy_out_aggregates_across_devices(self) -> None:
        # Both devices contribute to the same RM-OUT but list different prefix-lists.
        parsed_a = {
            "bgp_neighbor_to_group": {"1.1.1.1": "PG"},
            "bgp_route_maps": {"PG": {"out": "RM-OUT"}},
            "route_map_prefix_lists": {"RM-OUT": ["PL-X"]},
            "prefix_lists": {
                "PL-X": [{"seq": 10, "action": "permit", "prefix": "10.0.0.0/8"}],
            },
        }
        parsed_b = {
            "bgp_neighbor_to_group": {"2.2.2.2": "PG"},
            "bgp_route_maps": {"PG": {"out": "RM-OUT"}},
            "route_map_prefix_lists": {"RM-OUT": ["PL-Y"]},
            "prefix_lists": {
                "PL-Y": [{"seq": 10, "action": "permit", "prefix": "192.168.0.0/16"}],
            },
        }
        rows = build_unified_bgp_full_table(
            [
                {"hostname": "leaf-N01", "parsed": parsed_a},
                {"hostname": "leaf-N02", "parsed": parsed_b},
            ]
        )
        assert len(rows) == 1
        h_out = rows[0]["hierarchy_out"]
        # PL-X and PL-Y each appear once after merge — sorted alphabetically.
        assert [h["prefix_list"] for h in h_out] == ["PL-X", "PL-Y"]
