"""
HTML responses must carry the Phase-13 CSP header.

The ``after_request`` hook in ``backend/request_logging.py`` attaches
a strict-by-default CSP. Two regressions to lock in:

* ``default-src 'self'`` and ``script-src 'self'`` are present.
* The ``script-src`` directive must not contain ``'unsafe-inline'``
  (style-src is allowed to, since the SPA uses a small inline-style
  block — but scripts must always be external).
"""
from __future__ import annotations

import re

import pytest

pytestmark = [pytest.mark.security]


def _csp(client) -> str:
    r = client.get("/")
    assert r.status_code in (200, 404), (
        f"unexpected status for / (SPA root): {r.status_code}"
    )
    csp = r.headers.get("Content-Security-Policy", "")
    assert csp, "Content-Security-Policy header missing on / response"
    return csp


def test_index_html_response_carries_strict_csp(client) -> None:
    csp = _csp(client)
    assert "default-src 'self'" in csp, f"default-src 'self' missing: {csp!r}"
    assert "script-src 'self'" in csp, f"script-src 'self' missing: {csp!r}"


def test_index_html_response_does_not_have_unsafe_inline_for_scripts(client) -> None:
    csp = _csp(client)
    # Extract the script-src directive (everything up to the next ';').
    m = re.search(r"script-src([^;]*)", csp)
    assert m is not None, f"script-src directive not found in CSP: {csp!r}"
    script_src = m.group(1)
    assert "unsafe-inline" not in script_src, (
        f"script-src must not contain 'unsafe-inline'; got: {script_src!r}"
    )
