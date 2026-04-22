"""Unit tests for ``backend.parsers.generic.field_engine.GenericFieldEngine``.

Pin every branch of the legacy ``parse_output()`` field-loop:

* ``json_path`` — simple, count, count_where, key_prefix+value_key, suffix/subtract
* ``regex``    — simple, count
* ``format_template`` — second-pass templating
* edge cases   — empty config, missing name, JSON-string input
"""

from __future__ import annotations

from backend.parsers.generic.field_engine import GenericFieldEngine


class TestEmptyAndMalformedConfig:
    def test_none_config_returns_empty(self) -> None:
        assert GenericFieldEngine().apply({}, None) == {}

    def test_empty_fields_returns_empty(self) -> None:
        assert GenericFieldEngine().apply({}, {"fields": []}) == {}

    def test_missing_fields_key_returns_empty(self) -> None:
        assert GenericFieldEngine().apply({}, {}) == {}

    def test_field_without_name_skipped(self) -> None:
        cfg = {"fields": [{"name": "", "json_path": "a"}]}
        assert GenericFieldEngine().apply({"a": 1}, cfg) == {}


class TestJsonPathSimple:
    def test_returns_value_at_path(self) -> None:
        cfg = {"fields": [{"name": "v", "json_path": "a.b"}]}
        assert GenericFieldEngine().apply({"a": {"b": 42}}, cfg) == {"v": 42}

    def test_string_input_parsed_as_json(self) -> None:
        cfg = {"fields": [{"name": "v", "json_path": "a"}]}
        assert GenericFieldEngine().apply('{"a": "hello"}', cfg) == {"v": "hello"}

    def test_string_input_invalid_json_falls_through_to_regex(self) -> None:
        # Non-JSON string — json_path field returns None for missing
        cfg = {"fields": [{"name": "v", "json_path": "a"}]}
        assert GenericFieldEngine().apply("not json", cfg) == {"v": None}


class TestJsonPathCount:
    def test_counts_list_length(self) -> None:
        cfg = {"fields": [{"name": "n", "json_path": "rows", "count": True}]}
        assert GenericFieldEngine().apply({"rows": [1, 2, 3]}, cfg) == {"n": 3}

    def test_count_where_filters(self) -> None:
        cfg = {
            "fields": [
                {
                    "name": "ups",
                    "json_path": "rows",
                    "count": True,
                    "count_where": {"state": "up"},
                }
            ]
        }
        data = {"rows": [{"state": "up"}, {"state": "down"}, {"state": "up"}]}
        assert GenericFieldEngine().apply(data, cfg) == {"ups": 2}


class TestJsonPathKeyPrefix:
    def test_value_at_first_matching_prefix(self) -> None:
        cfg = {
            "fields": [
                {
                    "name": "temp",
                    "json_path": "sensors",
                    "key_prefix": "Eth",
                    "value_key": "temp",
                }
            ]
        }
        data = {"sensors": {"Eth1": {"temp": 30}, "Eth2": {"temp": 35}}}
        assert GenericFieldEngine().apply(data, cfg) == {"temp": 30}

    def test_none_when_no_prefix_match(self) -> None:
        cfg = {
            "fields": [
                {
                    "name": "temp",
                    "json_path": "sensors",
                    "key_prefix": "Mgmt",
                    "value_key": "temp",
                }
            ]
        }
        data = {"sensors": {"Eth1": {"temp": 30}}}
        assert GenericFieldEngine().apply(data, cfg) == {"temp": None}

    def test_value_suffix_applied(self) -> None:
        cfg = {
            "fields": [
                {
                    "name": "temp",
                    "json_path": "sensors",
                    "key_prefix": "Eth",
                    "value_key": "temp",
                    "value_suffix": " C",
                }
            ]
        }
        data = {"sensors": {"Eth1": {"temp": 30}}}
        assert GenericFieldEngine().apply(data, cfg) == {"temp": "30 C"}


class TestJsonPathSubtractSuffix:
    def test_value_subtract_from_and_suffix(self) -> None:
        cfg = {
            "fields": [
                {
                    "name": "cpu",
                    "json_path": "idle",
                    "value_subtract_from": 100,
                    "value_suffix": " %",
                }
            ]
        }
        assert GenericFieldEngine().apply({"idle": 25}, cfg) == {"cpu": "75 %"}


class TestRegex:
    def test_extract_first_group(self) -> None:
        cfg = {"fields": [{"name": "ver", "regex": r"version\s+(\S+)"}]}
        assert GenericFieldEngine().apply("version 4.2.1", cfg) == {"ver": "4.2.1"}

    def test_no_match_returns_empty_string(self) -> None:
        cfg = {"fields": [{"name": "ver", "regex": r"version\s+(\S+)"}]}
        assert GenericFieldEngine().apply("nothing matches", cfg) == {"ver": ""}

    def test_count_lines(self) -> None:
        cfg = {"fields": [{"name": "n", "regex": r"^foo", "count": True}]}
        text = "foo\nbar\nfoo\nfoo"
        assert GenericFieldEngine().apply(text, cfg) == {"n": 3}


class TestFormatTemplate:
    def test_combines_two_earlier_fields(self) -> None:
        cfg = {
            "fields": [
                {"name": "up", "json_path": "u"},
                {"name": "total", "json_path": "t"},
                {
                    "name": "summary",
                    "format_template": "{up}/{total}",
                    "format_fields": ["up", "total"],
                },
            ]
        }
        assert GenericFieldEngine().apply({"u": 3, "t": 5}, cfg) == {
            "up": 3,
            "total": 5,
            "summary": "3/5",
        }

    def test_missing_referenced_field_yields_empty_string(self) -> None:
        # If a referenced field is missing it falls back to "" (so .format succeeds)
        cfg = {
            "fields": [
                {
                    "name": "summary",
                    "format_template": "{a}/{b}",
                    "format_fields": ["a", "b"],
                }
            ]
        }
        assert GenericFieldEngine().apply({}, cfg) == {"summary": "/"}

    def test_template_kept_in_field_list_does_not_run_in_first_pass(self) -> None:
        # The first pass skips format_template fields (continue); only the second
        # pass templates them. So ordering doesn't matter.
        cfg = {
            "fields": [
                {
                    "name": "summary",
                    "format_template": "{x}",
                    "format_fields": ["x"],
                },
                {"name": "x", "json_path": "x"},
            ]
        }
        assert GenericFieldEngine().apply({"x": "hello"}, cfg) == {
            "x": "hello",
            "summary": "hello",
        }


class TestParityWithLegacyParseOutput:
    """Direct comparison: the engine must produce the same dict as the
    legacy ``parse_output()`` for inputs without ``custom_parser``."""

    def test_parity_for_simple_json_path(self) -> None:
        from backend.parse_output import parse_output

        cfg = {"fields": [{"name": "v", "json_path": "a.b"}]}
        data = {"a": {"b": 42}}
        assert GenericFieldEngine().apply(data, cfg) == parse_output("anycmd", data, cfg)

    def test_parity_for_format_template(self) -> None:
        from backend.parse_output import parse_output

        cfg = {
            "fields": [
                {"name": "u", "json_path": "u"},
                {"name": "t", "json_path": "t"},
                {
                    "name": "s",
                    "format_template": "{u}/{t}",
                    "format_fields": ["u", "t"],
                },
            ]
        }
        data = {"u": 3, "t": 5}
        assert GenericFieldEngine().apply(data, cfg) == parse_output("anycmd", data, cfg)
