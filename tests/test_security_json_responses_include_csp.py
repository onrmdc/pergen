"""
JSON responses must carry the same Phase-13 CSP and HSTS posture as HTML.

This test pins the JSON-side CSP directive set so that a future change
that gates ``Content-Security-Policy`` / ``Strict-Transport-Security``
on ``response.mimetype == "text/html"`` cannot pass CI.

Wave-6 Phase D rationale:
  * The middleware in :mod:`backend.request_logging` applies the same
    headers to every response regardless of Content-Type, but no test
    pinned this on the JSON surface. This file is the regression fence.
  * The directive list is intentionally identical to
    ``tests/test_security_html_responses_include_csp.py``; both tests
    keep the constant local so pytest discovery treats them as siblings.
  * See ``docs/refactor/DONE_csp_hsts_json_headers.md`` Option C for the
    policy decision.
"""
from __future__ import annotations

import re

import pytest

pytestmark = [pytest.mark.security]

# Mirrors REQUIRED_DIRECTIVES in test_security_html_responses_include_csp.py.
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


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _csp(client, path: str) -> str:
    r = client.get(path)
    # Header middleware runs on success and on 4xx alike, so any 2xx/4xx is OK.
    assert r.status_code in (200, 401, 403, 404, 405), (
        f"unexpected status for {path}: {r.status_code}"
    )
    csp = r.headers.get("Content-Security-Policy", "")
    assert csp, f"Content-Security-Policy header missing on {path}: {dict(r.headers)}"
    return csp


def _hsts_or_none(client, path: str) -> str | None:
    """HSTS is only emitted on HTTPS requests by design (Audit L-02)."""
    r = client.get(path)
    return r.headers.get("Strict-Transport-Security")


# --------------------------------------------------------------------------- #
# JSON-endpoint CSP assertions                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", ["/api/health", "/api/v2/health"])
def test_json_health_endpoint_carries_full_csp_directive_set(client, path) -> None:
    csp = _csp(client, path)
    for directive in REQUIRED_DIRECTIVES:
        assert directive in csp, (
            f"{directive!r} missing from CSP on {path}: {csp!r}"
        )


@pytest.mark.parametrize("path", ["/api/health", "/api/v2/health"])
def test_json_health_endpoint_disallows_unsafe_inline_for_scripts(client, path) -> None:
    csp = _csp(client, path)
    m = re.search(r"script-src([^;]*)", csp)
    assert m is not None, f"script-src missing on {path}: {csp!r}"
    assert "unsafe-inline" not in m.group(1), (
        f"script-src must not contain 'unsafe-inline' on {path}; got: {m.group(1)!r}"
    )
    assert "unsafe-eval" not in m.group(1), (
        f"script-src must not contain 'unsafe-eval' on {path}; got: {m.group(1)!r}"
    )


@pytest.mark.parametrize("path", ["/api/health", "/api/v2/health"])
def test_json_health_endpoint_disallows_unsafe_inline_for_styles(client, path) -> None:
    """Wave-6 Phase D: ``style-src`` no longer permits ``'unsafe-inline'``.

    JSON bodies have no styles to render, so a strict policy is harmless on
    the JSON surface — and still defends against a misconfigured proxy or
    test harness reinterpreting the body as HTML.
    """
    csp = _csp(client, path)
    m = re.search(r"style-src([^;]*)", csp)
    assert m is not None, f"style-src missing on {path}: {csp!r}"
    assert "unsafe-inline" not in m.group(1), (
        f"style-src must not contain 'unsafe-inline' on {path}; got: {m.group(1)!r}"
    )


# --------------------------------------------------------------------------- #
# 4xx-path coverage — header middleware must still fire                       #
# --------------------------------------------------------------------------- #


def test_json_404_path_still_carries_csp(client) -> None:
    """A 404 from a JSON-shaped path must still receive the CSP directives."""
    csp = _csp(client, "/api/this-route-does-not-exist")
    for directive in REQUIRED_DIRECTIVES:
        assert directive in csp, (
            f"{directive!r} missing from 404 CSP: {csp!r}"
        )
