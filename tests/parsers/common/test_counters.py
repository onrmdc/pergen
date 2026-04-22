"""Unit tests for ``backend.parsers.common.counters``."""

from __future__ import annotations

from backend.parsers.common.counters import (
    _count_from_json,
    _count_where,
    _get_from_dict_by_key_prefix,
)


class TestCountFromJson:
    def test_counts_list_length(self) -> None:
        assert _count_from_json({"a": [1, 2, 3]}, "a") == 3

    def test_counts_dict_length(self) -> None:
        assert _count_from_json({"a": {"x": 1, "y": 2}}, "a") == 2

    def test_returns_zero_for_missing_path(self) -> None:
        assert _count_from_json({"a": 1}, "missing") == 0

    def test_returns_zero_for_scalar_path(self) -> None:
        # str at path → 0 (not an int/float, not a list/dict)
        assert _count_from_json({"a": "hello"}, "a") == 0

    def test_int_value_at_path_returns_int(self) -> None:
        assert _count_from_json({"a": 5}, "a") == 5

    def test_float_value_at_path_truncates_to_int(self) -> None:
        assert _count_from_json({"a": 5.7}, "a") == 5

    def test_flatten_inner_counts_total(self) -> None:
        data = {"rows": [{"items": [1, 2]}, {"items": [3]}]}
        assert _count_from_json(data, "rows", flatten_inner_path="items") == 3


class TestCountWhere:
    def test_counts_matching_dicts_in_list(self) -> None:
        data = {"rows": [{"state": "up"}, {"state": "down"}, {"state": "up"}]}
        assert _count_where(data, "rows", {"state": "up"}) == 2

    def test_counts_matching_in_dict_values(self) -> None:
        # When value at path is dict, iterate over .values()
        data = {"ifaces": {"e1": {"state": "up"}, "e2": {"state": "down"}}}
        assert _count_where(data, "ifaces", {"state": "up"}) == 1

    def test_key_prefix_filters_dict_keys(self) -> None:
        data = {"ifaces": {"Eth1": {"state": "up"}, "Mgmt0": {"state": "up"}, "Eth2": {"state": "up"}}}
        assert _count_where(data, "ifaces", {"state": "up"}, key_prefix="Eth") == 2

    def test_key_prefix_exclude_skips_dict_keys(self) -> None:
        data = {"ifaces": {"Eth1": {"state": "up"}, "Mgmt0": {"state": "up"}}}
        assert _count_where(data, "ifaces", {"state": "up"}, key_prefix_exclude="Mgmt") == 1

    def test_returns_zero_for_missing_path(self) -> None:
        assert _count_where({"a": 1}, "missing", {"k": "v"}) == 0

    def test_string_coercion_for_comparison(self) -> None:
        # int "1" matches str "1"
        data = {"rows": [{"n": 1}, {"n": 2}]}
        assert _count_where(data, "rows", {"n": "1"}) == 1

    def test_skips_non_dict_items_in_list(self) -> None:
        data = {"rows": [{"k": "v"}, "not-a-dict", {"k": "v"}]}
        assert _count_where(data, "rows", {"k": "v"}) == 2


class TestGetFromDictByKeyPrefix:
    def test_returns_value_for_first_matching_prefix(self) -> None:
        data = {"sensors": {"Eth1/1": {"temp": 30}, "Eth1/2": {"temp": 35}}}
        assert _get_from_dict_by_key_prefix(data, "sensors", "Eth", "temp") == 30

    def test_applies_divisor(self) -> None:
        data = {"mem": {"total": {"bytes": 1024}}}
        assert _get_from_dict_by_key_prefix(data, "mem", "total", "bytes", divisor=1024) == 1.0

    def test_returns_none_when_no_prefix_match(self) -> None:
        data = {"sensors": {"Mgmt0": {"temp": 30}}}
        assert _get_from_dict_by_key_prefix(data, "sensors", "Eth", "temp") is None

    def test_returns_none_when_path_not_dict(self) -> None:
        assert _get_from_dict_by_key_prefix({"a": 1}, "a", "k", "v") is None

    def test_returns_value_unchanged_on_divisor_typeerror(self) -> None:
        data = {"x": {"k": {"v": "not-a-number"}}}
        assert _get_from_dict_by_key_prefix(data, "x", "k", "v", divisor=2) == "not-a-number"

    def test_zero_divisor_returns_value_unchanged(self) -> None:
        data = {"x": {"k": {"v": 10}}}
        assert _get_from_dict_by_key_prefix(data, "x", "k", "v", divisor=0) == 10
