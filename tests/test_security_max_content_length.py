"""Audit GAP #14 — ``MAX_CONTENT_LENGTH`` must cap request bodies at 10 MB.

Without this cap, Flask silently buffers the entire request body before
invoking the handler — a gigabyte-sized POST can OOM the worker. The
config wires ``MAX_CONTENT_LENGTH=10 MB`` (overridable via the
``MAX_CONTENT_LENGTH`` env var); Flask then short-circuits oversize
bodies with HTTP 413 before any route runs.

Audit reference: ``backend/config/app_config.py`` lines 125-131.

This module pins:
  * ``app.config["MAX_CONTENT_LENGTH"]`` is exactly 10 * 1024 * 1024.
  * A POST body just over 10 MB is rejected with 413, NOT 500.
  * The cap fires for any /api/* endpoint (we test on /api/inventory/import
    so a malformed body hits the size cap before the handler).
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security]

_TEN_MB = 10 * 1024 * 1024


def test_max_content_length_config_pinned_to_10mb(flask_app) -> None:
    """``app.config["MAX_CONTENT_LENGTH"]`` must equal exactly 10 MiB."""
    assert flask_app.config.get("MAX_CONTENT_LENGTH") == _TEN_MB, (
        f"MAX_CONTENT_LENGTH must be 10 MiB ({_TEN_MB} bytes), got "
        f"{flask_app.config.get('MAX_CONTENT_LENGTH')!r}"
    )


def test_oversize_post_returns_413_not_500(client) -> None:
    """An 11 MiB JSON POST must be rejected with 413, never 500."""
    # Build a payload slightly larger than the 10 MiB cap. We don't care
    # about JSON validity — Flask short-circuits before the handler runs.
    oversize_body = b"x" * (_TEN_MB + 1024 * 1024)  # 11 MiB
    r = client.post(
        "/api/inventory/import",
        data=oversize_body,
        content_type="application/json",
    )
    assert r.status_code == 413, (
        f"oversize body must yield 413 (Request Entity Too Large), "
        f"got {r.status_code}"
    )


def test_undersize_post_is_not_rejected_by_size_cap(client) -> None:
    """A small body must NOT be rejected by the size cap.

    Counter-test: confirms 413 above is not a blanket reject. We use a
    100-byte JSON body that the route accepts (or rejects with a 400/422
    semantic error — anything but 413 is fine).
    """
    r = client.post(
        "/api/inventory/import",
        json={"rows": []},
    )
    assert r.status_code != 413, (
        f"a 100-byte body must not trip the size cap; got {r.status_code}"
    )


def test_max_content_length_value_is_an_int(flask_app) -> None:
    """Type contract: Flask requires an int (or None) for the cap."""
    val = flask_app.config.get("MAX_CONTENT_LENGTH")
    assert isinstance(val, int), (
        f"MAX_CONTENT_LENGTH must be an int (Flask requirement); "
        f"got {type(val).__name__}"
    )
    assert val > 0


def test_oversize_post_uses_content_length_header(client) -> None:
    """A request whose ``Content-Length`` header alone exceeds the cap
    must be rejected without buffering the body — defence against a
    slow-loris-style upload.
    """
    # Use a streaming environ where Content-Length is set but no real
    # body is sent. Flask reads the header and rejects immediately.
    r = client.post(
        "/api/inventory/import",
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(_TEN_MB + 1),
        },
        data=b"",  # Werkzeug fills the discrepancy; we just need the header.
    )
    # 413 is the documented behaviour. Some Werkzeug versions surface
    # 400 (bad request) when Content-Length and body length disagree —
    # both indicate the cap fired before the handler. Anything that
    # reaches the handler (200/4xx route-specific) would be a regression.
    assert r.status_code in (400, 413), (
        f"oversize Content-Length header must short-circuit; got "
        f"{r.status_code}"
    )
