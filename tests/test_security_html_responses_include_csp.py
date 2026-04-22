"""
HTML responses must carry the Phase-13 CSP header.

The ``after_request`` hook in ``backend/request_logging.py`` attaches
a strict-by-default CSP. Wave-6 Phase D regressions to lock in:

* ``default-src 'self'`` and ``script-src 'self'`` are present.
* Neither ``script-src`` nor ``style-src`` may contain ``'unsafe-inline'``.
  The SPA was refactored (Wave-6 Phase D) to externalise every inline
  style — see ``backend/static/css/extracted-inline.css`` and
  ``backend/static/css/components.css``.
* ``form-action 'self'``, ``connect-src 'self'``, and
  ``upgrade-insecure-requests`` must all be present (Wave-6 Phase D
  tightening, Option C of ``docs/refactor/DONE_csp_hsts_json_headers.md``).
"""
from __future__ import annotations

import re

import pytest

pytestmark = [pytest.mark.security]

# Directive set asserted on every HTML response. Mirrored in
# tests/test_security_json_responses_include_csp.py — keep in sync.
REQUIRED_DIRECTIVES: tuple[str, ...] = (
    "default-src 'self'",
    "script-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "connect-src 'self'",
    "upgrade-insecure-requests",
)


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
    for directive in REQUIRED_DIRECTIVES:
        assert directive in csp, f"{directive!r} missing from CSP: {csp!r}"


def test_index_html_response_does_not_have_unsafe_inline_for_scripts(client) -> None:
    csp = _csp(client)
    # Extract the script-src directive (everything up to the next ';').
    m = re.search(r"script-src([^;]*)", csp)
    assert m is not None, f"script-src directive not found in CSP: {csp!r}"
    script_src = m.group(1)
    assert "unsafe-inline" not in script_src, (
        f"script-src must not contain 'unsafe-inline'; got: {script_src!r}"
    )


def test_index_html_response_does_not_have_unsafe_inline_for_styles(client) -> None:
    """Wave-6 Phase D: style-src no longer permits 'unsafe-inline'.

    The SPA's single inline ``<style>`` block plus 239 inline ``style="..."``
    attributes were converted to external CSS classes. JS-side
    ``style.cssText`` writes were replaced with class toggles + dynamic
    CSSOM property assignments (which are not policed by ``style-src-attr``
    in major browsers).
    """
    csp = _csp(client)
    m = re.search(r"style-src([^;]*)", csp)
    assert m is not None, f"style-src directive not found in CSP: {csp!r}"
    style_src = m.group(1)
    assert "unsafe-inline" not in style_src, (
        f"style-src must not contain 'unsafe-inline'; got: {style_src!r}"
    )
    assert "unsafe-eval" not in style_src, (
        f"style-src must not contain 'unsafe-eval'; got: {style_src!r}"
    )
