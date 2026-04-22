"""Unit tests for ``backend.parsers.common.json_path``.

These tests pin the contract of the path-walking helpers extracted from
``backend/parse_output.py`` (Phase 1 of the parse_output refactor — see
``docs/refactor/parse_output_split.md``).

The legacy behaviour these helpers must reproduce:

* ``_get_path("a.b.c", data)`` — dot-separated walk; if any node is a
  list, take the first element and continue; non-dict, non-list nodes
  return ``None``.
* ``_flatten_nested_list(data, path, inner_path)`` — handles a list
  ``inner_path`` for multi-level NX-API table walks.
* ``_find_key`` / ``_find_key_containing`` — recursive search; the
  ``_containing`` variant is case-insensitive AND skips empty values.
* ``_find_list`` — returns the first list under any key whose name
  contains the substring (case-insensitive).
* ``_get_val(r, *keys)`` — returns the first matching ``_find_key`` hit
  stripped, or empty string.
"""

from __future__ import annotations

import pytest

from backend.parsers.common.json_path import (
    _find_key,
    _find_key_containing,
    _find_list,
    _flatten_nested_list,
    _get_path,
    _get_val,
)


class TestGetPath:
    def test_returns_none_for_empty_path(self) -> None:
        assert _get_path({"a": 1}, "") is None

    def test_returns_none_for_none_data(self) -> None:
        assert _get_path(None, "a.b") is None

    def test_walks_simple_dot_path(self) -> None:
        assert _get_path({"a": {"b": {"c": 42}}}, "a.b.c") == 42

    def test_takes_first_element_of_list(self) -> None:
        data = {"a": [{"b": 1}, {"b": 2}]}
        # walks into the first list element
        assert _get_path(data, "a.b") == 1

    def test_returns_none_for_missing_key(self) -> None:
        assert _get_path({"a": {}}, "a.b") is None

    def test_returns_none_when_intermediate_is_scalar(self) -> None:
        assert _get_path({"a": 5}, "a.b") is None

    def test_handles_empty_list_at_any_level(self) -> None:
        assert _get_path({"a": []}, "a.b") is None

    def test_strips_path_whitespace(self) -> None:
        assert _get_path({"a": {"b": 7}}, "  a.b  ") == 7


class TestFlattenNestedList:
    def test_returns_empty_when_path_missing(self) -> None:
        assert _flatten_nested_list({"x": 1}, "missing", "inner") == []

    def test_returns_empty_when_path_not_list(self) -> None:
        assert _flatten_nested_list({"a": {"b": 1}}, "a", "b") == []

    def test_string_inner_path_extends_lists(self) -> None:
        data = {"rows": [{"items": [1, 2]}, {"items": [3]}]}
        assert _flatten_nested_list(data, "rows", "items") == [1, 2, 3]

    def test_string_inner_path_appends_scalars(self) -> None:
        data = {"rows": [{"v": "a"}, {"v": "b"}]}
        assert _flatten_nested_list(data, "rows", "v") == ["a", "b"]

    def test_string_inner_path_skips_none(self) -> None:
        data = {"rows": [{"v": None}, {"v": "kept"}]}
        assert _flatten_nested_list(data, "rows", "v") == ["kept"]

    def test_list_inner_path_walks_multiple_levels(self) -> None:
        # NX-API style: TABLE_vrf.ROW_vrf -> TABLE_process_adj.ROW_process_adj
        data = {
            "outer": [
                {
                    "TABLE_vrf": {
                        "ROW_vrf": [
                            {
                                "TABLE_process_adj": {
                                    "ROW_process_adj": [
                                        {"adj-id": "1"},
                                        {"adj-id": "2"},
                                    ]
                                }
                            }
                        ]
                    }
                }
            ]
        }
        result = _flatten_nested_list(
            data,
            "outer",
            ["TABLE_vrf.ROW_vrf", "TABLE_process_adj.ROW_process_adj"],
        )
        assert result == [{"adj-id": "1"}, {"adj-id": "2"}]

    def test_empty_inner_path_list_returns_outer_list(self) -> None:
        data = {"a": [1, 2, 3]}
        assert _flatten_nested_list(data, "a", []) == [1, 2, 3]


class TestFindKey:
    def test_returns_none_for_non_dict(self) -> None:
        assert _find_key(["a"], "k") is None
        assert _find_key("scalar", "k") is None
        assert _find_key(None, "k") is None

    def test_returns_value_at_top_level(self) -> None:
        assert _find_key({"k": 1}, "k") == 1

    def test_returns_first_value_in_nested_dict(self) -> None:
        assert _find_key({"a": {"b": {"target": 42}}}, "target") == 42

    def test_returns_none_when_not_found(self) -> None:
        assert _find_key({"a": {"b": 1}}, "missing") is None


class TestFindKeyContaining:
    def test_case_insensitive_substring_match(self) -> None:
        assert _find_key_containing({"smt_if_LAST_link_flapped": "00:01:00"}, "last_link") == "00:01:00"

    def test_skips_empty_values(self) -> None:
        # empty string + empty dict should be skipped, real value returned
        data = {"if_last_a": "", "if_last_b": "kept"}
        assert _find_key_containing(data, "if_last") == "kept"

    def test_recurses_into_nested_dicts(self) -> None:
        data = {"outer": {"inner_match": "found"}}
        assert _find_key_containing(data, "match") == "found"

    def test_recurses_into_lists_of_dicts(self) -> None:
        data = {"rows": [{"a": 1}, {"target_key": "v"}]}
        assert _find_key_containing(data, "target") == "v"

    def test_returns_none_when_not_found(self) -> None:
        assert _find_key_containing({"a": 1}, "z") is None


class TestFindList:
    def test_returns_none_for_non_dict(self) -> None:
        assert _find_list([], "ROW") is None
        assert _find_list(None, "ROW") is None

    def test_finds_list_at_top_level(self) -> None:
        data = {"ROW_interface": [{"x": 1}]}
        assert _find_list(data, "ROW") == [{"x": 1}]

    def test_recurses_into_dict_values(self) -> None:
        data = {"outer": {"ROW_inter": [{"x": 1}]}}
        assert _find_list(data, "ROW_inter") == [{"x": 1}]

    def test_returns_none_when_not_found(self) -> None:
        assert _find_list({"a": 1}, "ROW") is None


class TestGetVal:
    def test_returns_first_matching_key_stripped(self) -> None:
        assert _get_val({"a": "  hello  ", "b": "world"}, "a", "b") == "hello"

    def test_falls_back_to_second_key(self) -> None:
        assert _get_val({"b": "kept"}, "a", "b") == "kept"

    def test_returns_empty_string_when_no_keys_match(self) -> None:
        assert _get_val({"x": 1}, "a", "b") == ""

    def test_finds_keys_in_nested_dicts(self) -> None:
        # _get_val uses _find_key which recurses
        assert _get_val({"outer": {"target": "v"}}, "target") == "v"


class TestSignatureCompatibility:
    """Pin that helpers preserve the legacy callable shape."""

    @pytest.mark.parametrize(
        "fn",
        [
            _get_path,
            _flatten_nested_list,
            _find_key,
            _find_key_containing,
            _find_list,
            _get_val,
        ],
    )
    def test_callable(self, fn) -> None:
        assert callable(fn)
