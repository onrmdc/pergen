"""
TDD tests for ``backend.parsers.engine.ParserEngine``.

The engine is a thin OOD façade over the existing
``backend.parse_output.parse_output`` function plus the YAML parser
registry loaded from ``backend/config/parsers.yaml``.

Contracts
---------
* ``ParserEngine.from_yaml(yaml_path)`` constructs an engine seeded
  from the YAML file.
* ``engine.has(command_id)`` returns True iff a config exists for
  that command id.
* ``engine.get_config(command_id)`` returns the parser-config dict
  (or None when missing).
* ``engine.parse(command_id, raw_output)`` returns the parsed dict
  (delegates to legacy ``parse_output``).  Returns ``{}`` when no
  config is registered.
* ``engine.command_ids()`` lists the registered command ids.
* The engine is read-only — registering new parsers requires editing
  the YAML and re-instantiating.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_PARSERS_YAML = Path(__file__).parent.parent / "backend" / "config" / "parsers.yaml"


def test_engine_loads_from_yaml():
    from backend.parsers.engine import ParserEngine

    engine = ParserEngine.from_yaml(str(_PARSERS_YAML))
    ids = engine.command_ids()
    assert isinstance(ids, list)
    assert len(ids) > 0


def test_engine_has_returns_true_for_known_command():
    from backend.parsers.engine import ParserEngine

    engine = ParserEngine.from_yaml(str(_PARSERS_YAML))
    known = engine.command_ids()[0]
    assert engine.has(known) is True


def test_engine_has_returns_false_for_unknown():
    from backend.parsers.engine import ParserEngine

    engine = ParserEngine.from_yaml(str(_PARSERS_YAML))
    assert engine.has("does-not-exist-xyz") is False


def test_engine_get_config_returns_dict_for_known(tmp_path):
    from backend.parsers.engine import ParserEngine

    yml = tmp_path / "p.yaml"
    yml.write_text(
        "my_cmd:\n"
        "  fields:\n"
        "    - name: ver\n"
        "      json_path: version\n",
        encoding="utf-8",
    )
    engine = ParserEngine.from_yaml(str(yml))
    cfg = engine.get_config("my_cmd")
    assert cfg is not None
    assert isinstance(cfg, dict)
    assert cfg.get("fields")[0]["name"] == "ver"


def test_engine_get_config_returns_none_for_unknown():
    from backend.parsers.engine import ParserEngine

    engine = ParserEngine.from_yaml(str(_PARSERS_YAML))
    assert engine.get_config("does-not-exist-xyz") is None


def test_engine_parse_returns_empty_for_unknown(tmp_path):
    from backend.parsers.engine import ParserEngine

    yml = tmp_path / "p.yaml"
    yml.write_text("{}\n", encoding="utf-8")
    engine = ParserEngine.from_yaml(str(yml))
    assert engine.parse("nope", {}) == {}


def test_engine_parse_simple_json_path(tmp_path):
    from backend.parsers.engine import ParserEngine

    yml = tmp_path / "p.yaml"
    yml.write_text(
        "simple:\n"
        "  fields:\n"
        "    - name: ver\n"
        "      json_path: version\n",
        encoding="utf-8",
    )
    engine = ParserEngine.from_yaml(str(yml))
    out = engine.parse("simple", {"version": "EOS-4.30.4M"})
    assert out == {"ver": "EOS-4.30.4M"}


def test_engine_parse_delegates_to_legacy_parser(tmp_path):
    """The engine must call the legacy parse_output with the full
    parser-config dict so behavioural drift is impossible."""
    from unittest.mock import patch

    from backend.parsers.engine import ParserEngine

    yml = tmp_path / "p.yaml"
    yml.write_text(
        "my_cmd:\n"
        "  fields:\n"
        "    - name: ver\n"
        "      json_path: version\n",
        encoding="utf-8",
    )
    engine = ParserEngine.from_yaml(str(yml))
    with patch("backend.parsers.engine._legacy_parse_output") as mock_parse:
        mock_parse.return_value = {"sentinel": True}
        out = engine.parse("my_cmd", {"version": "x"})
    assert out == {"sentinel": True}
    args, _ = mock_parse.call_args
    assert args[0] == "my_cmd"
    assert args[1] == {"version": "x"}
    assert isinstance(args[2], dict)
    assert args[2]["fields"][0]["name"] == "ver"


def test_engine_constructor_accepts_dict_directly():
    from backend.parsers.engine import ParserEngine

    engine = ParserEngine(
        {
            "alpha": {"fields": [{"name": "a", "json_path": "a"}]},
            "beta": {"fields": [{"name": "b", "json_path": "b"}]},
        }
    )
    assert sorted(engine.command_ids()) == ["alpha", "beta"]
    assert engine.parse("alpha", {"a": 1}) == {"a": 1}


def test_engine_command_ids_are_sorted():
    from backend.parsers.engine import ParserEngine

    engine = ParserEngine(
        {"zulu": {"fields": []}, "alpha": {"fields": []}, "mike": {"fields": []}}
    )
    assert engine.command_ids() == ["alpha", "mike", "zulu"]
