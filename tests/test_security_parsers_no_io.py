"""I-04 — Parsers must not perform I/O.

The new ``backend/parsers/`` package is pure logic over device API output.
The audit confirmed no `subprocess`/`eval`/`exec`/`requests`/file I/O —
this test pins that contract so a future contributor cannot quietly
introduce a network call inside a parser.

Strategy: stub `builtins.open`, `socket.socket`, and `urllib.request.urlopen`
to raise; then call every registered parser with a benign empty dict input.
None of them should touch any I/O primitive.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.security]


def _all_parser_callables():
    """Return every registered ``custom_parser`` callable in the dispatcher."""
    from backend.parsers.dispatcher import _DEFAULT_REGISTRY

    return list(_DEFAULT_REGISTRY.items())


@pytest.mark.parametrize("name,fn", _all_parser_callables())
def test_parser_does_not_open_any_file(name: str, fn) -> None:
    """No registered parser may call ``builtins.open`` during ``parse(empty)``."""
    with patch("builtins.open", side_effect=AssertionError(f"{name} called open()")):
        out = fn({})
        assert isinstance(out, dict), f"{name} did not return a dict on empty input"


@pytest.mark.parametrize("name,fn", _all_parser_callables())
def test_parser_does_not_open_any_socket(name: str, fn) -> None:
    """No registered parser may instantiate a socket during ``parse(empty)``."""
    import socket

    with patch.object(
        socket, "socket", side_effect=AssertionError(f"{name} created a socket")
    ):
        out = fn({})
        assert isinstance(out, dict)


def test_field_engine_does_not_open_any_file() -> None:
    """Same guarantee for the ``GenericFieldEngine`` fallback path."""
    from backend.parsers.generic.field_engine import GenericFieldEngine

    cfg = {"fields": [{"name": "v", "json_path": "a.b"}]}
    with patch("builtins.open", side_effect=AssertionError("field engine called open()")):
        out = GenericFieldEngine().apply({"a": {"b": 42}}, cfg)
        assert out == {"v": 42}
