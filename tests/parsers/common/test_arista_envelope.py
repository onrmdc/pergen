"""Unit tests for ``backend.parsers.common.arista_envelope``."""

from __future__ import annotations

from backend.parsers.common.arista_envelope import (
    _arista_result_obj,
    _arista_result_to_dict,
)


class TestAristaResultObj:
    def test_passes_through_dict(self) -> None:
        obj = {"a": 1}
        assert _arista_result_obj(obj) is obj

    def test_returns_first_element_of_list(self) -> None:
        first = {"a": 1}
        assert _arista_result_obj([first, {"b": 2}]) is first

    def test_returns_indexed_element(self) -> None:
        elems = [{"a": 1}, {"b": 2}, {"c": 3}]
        assert _arista_result_obj(elems, index=2) == {"c": 3}

    def test_index_out_of_bounds_falls_back_to_first(self) -> None:
        # Defensive: when index >= len, fall back to [0]
        elems = [{"a": 1}]
        assert _arista_result_obj(elems, index=5) == {"a": 1}

    def test_returns_none_for_empty_list(self) -> None:
        assert _arista_result_obj([]) is None

    def test_returns_none_for_scalar(self) -> None:
        assert _arista_result_obj("string") is None
        assert _arista_result_obj(42) is None
        assert _arista_result_obj(None) is None


class TestAristaResultToDict:
    def test_returns_none_for_non_dict(self) -> None:
        assert _arista_result_to_dict([1]) is None
        assert _arista_result_to_dict("x") is None
        assert _arista_result_to_dict(None) is None

    def test_unwraps_output_key(self) -> None:
        wrapped = {"output": {"data": 1}}
        assert _arista_result_to_dict(wrapped) == {"data": 1}

    def test_unwraps_result_dict(self) -> None:
        wrapped = {"result": {"data": 2}}
        assert _arista_result_to_dict(wrapped) == {"data": 2}

    def test_unwraps_result_list_takes_first(self) -> None:
        wrapped = {"result": [{"first": 1}, {"second": 2}]}
        assert _arista_result_to_dict(wrapped) == {"first": 1}

    def test_returns_input_when_no_output_or_result(self) -> None:
        plain = {"plain": True}
        assert _arista_result_to_dict(plain) is plain

    def test_output_takes_precedence_over_result(self) -> None:
        # output is checked first
        wrapped = {"output": {"a": 1}, "result": {"b": 2}}
        assert _arista_result_to_dict(wrapped) == {"a": 1}

    def test_output_non_dict_falls_through_to_result(self) -> None:
        # If output isn't a dict, the helper falls through; result wins
        wrapped = {"output": "not-a-dict", "result": {"b": 2}}
        assert _arista_result_to_dict(wrapped) == {"b": 2}
