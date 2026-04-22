"""Wave-6 Phase F: unit tests for backend/security/csrf.py.

Pure-function tests — no Flask app context required.
"""
from __future__ import annotations

import pytest

from backend.security.csrf import issue_csrf_token, verify_csrf_token

pytestmark = [pytest.mark.security]


def test_issue_csrf_token_returns_high_entropy_string() -> None:
    tok = issue_csrf_token()
    # secrets.token_urlsafe(32) → ~43 chars URL-safe base64.
    assert isinstance(tok, str)
    assert len(tok) >= 32, f"CSRF token too short: {len(tok)} chars"
    # URL-safe alphabet only.
    import string
    allowed = set(string.ascii_letters + string.digits + "-_")
    assert set(tok).issubset(allowed)


def test_issue_csrf_token_is_unique() -> None:
    """1000 fresh tokens should all be distinct (probabilistic but ~1)."""
    tokens = {issue_csrf_token() for _ in range(1000)}
    assert len(tokens) == 1000


def test_verify_csrf_token_accepts_match() -> None:
    tok = issue_csrf_token()
    assert verify_csrf_token(tok, tok) is True


def test_verify_csrf_token_rejects_mismatch() -> None:
    a = issue_csrf_token()
    b = issue_csrf_token()
    assert verify_csrf_token(a, b) is False


def test_verify_csrf_token_rejects_empty_or_none() -> None:
    """Falsy values on either side must never authenticate."""
    assert verify_csrf_token("", "x") is False
    assert verify_csrf_token("x", "") is False
    assert verify_csrf_token(None, "x") is False
    assert verify_csrf_token("x", None) is False
    assert verify_csrf_token(None, None) is False
    assert verify_csrf_token("", "") is False


def test_verify_csrf_token_handles_length_mismatch_safely() -> None:
    """Different-length inputs must return False without raising."""
    assert verify_csrf_token("short", "much-longer-expected") is False
    assert verify_csrf_token("very-long-supplied-token", "x") is False
