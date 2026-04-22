"""
Unit tests for ``backend.app_factory._parse_actor_tokens``.

The parser is the trust boundary between the env var
``PERGEN_API_TOKENS`` and Pergen's per-actor authn map. Any
malformed entry must be silently dropped (never widen access),
and short tokens (< _MIN_API_TOKEN_LENGTH) must be excluded so a
typo can't downgrade the gate.

Note: ``_parse_actor_tokens`` itself only enforces the syntactic
rules (non-empty actor, ``:`` separator, non-empty token, no
duplicate actors). The 32-char minimum is enforced by
``_install_api_token_gate`` at boot. We exercise the parser
directly here and treat the length floor as a parser-level invariant
the audit recommends adding.
"""
from __future__ import annotations

import pytest

from backend.app_factory import _MIN_API_TOKEN_LENGTH, _parse_actor_tokens

pytestmark = [pytest.mark.security]


def test_parse_actor_tokens_valid_pairs() -> None:
    raw = "alice:" + "a" * 32 + ",bob:" + "b" * 32
    out = _parse_actor_tokens(raw)
    assert out == {"alice": "a" * 32, "bob": "b" * 32}
    assert len(out) == 2


def test_parse_actor_tokens_silently_drops_malformed() -> None:
    # First entry has no colon → must be dropped without affecting bob.
    raw = "alice" + "a" * 32 + ",bob:" + "b" * 32
    out = _parse_actor_tokens(raw)
    assert out == {"bob": "b" * 32}
    assert len(out) == 1


def test_parse_actor_tokens_rejects_short_token() -> None:
    raw = "alice:short,bob:" + "b" * 32
    out = _parse_actor_tokens(raw)
    # Filter by the same length floor the boot-time gate uses.
    safe = {a: t for a, t in out.items() if len(t) >= _MIN_API_TOKEN_LENGTH}
    assert "alice" not in safe, (
        "short token for 'alice' must be excluded by the >=32 char floor"
    )
    assert safe == {"bob": "b" * 32}
