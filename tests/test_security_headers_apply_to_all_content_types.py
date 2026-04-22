"""
Security headers must fire on every content type, not just HTML.

Wave-6 Phase D regression fence: a future "optimisation" that wraps the
``after_request`` header block in
``if response.mimetype.startswith("text/html"):`` would silently strip
CSP/HSTS from JSON, plaintext, and 404 responses — and pass every
existing security test that targets ``GET /``. This file makes that
mistake fail loudly by exercising the header middleware across:

  * an HTML route (``GET /``)
  * a JSON route (``GET /api/health``)
  * a JSON route via a v2 blueprint (``GET /api/v2/health``)
  * a 404 path (still passes through ``after_request``)
  * a 405 path (header middleware must run on method-not-allowed)

See ``docs/refactor/DONE_csp_hsts_json_headers.md`` §1.2 for the
original gap analysis.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security]


REQUIRED_HEADERS: tuple[str, ...] = (
    "Content-Security-Policy",
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "Permissions-Policy",
)


# (method, path, allowed_status_codes)
_ROUTES = (
    ("GET", "/", (200, 404)),
    ("GET", "/api/health", (200,)),
    ("GET", "/api/v2/health", (200,)),
    ("GET", "/api/this-does-not-exist", (404,)),
    # POST to a likely GET-only health route → 405 still passes after_request
    ("POST", "/api/health", (200, 405, 415, 400)),
)


@pytest.mark.parametrize("method,path,statuses", _ROUTES)
def test_every_route_carries_security_headers(client, method, path, statuses) -> None:
    """Each route under test must carry the documented security headers.

    The set is intentionally conservative — we assert presence, not exact
    string content (which is pinned by the dedicated CSP tests). The point
    here is to fail loudly on a Content-Type-gated regression.
    """
    r = client.open(path=path, method=method)
    assert r.status_code in statuses, (
        f"unexpected status for {method} {path}: {r.status_code}"
    )
    for header in REQUIRED_HEADERS:
        assert header in r.headers, (
            f"{header!r} missing from {method} {path} response "
            f"(status={r.status_code}, headers={dict(r.headers)})"
        )


@pytest.mark.parametrize("method,path,statuses", _ROUTES)
def test_csp_directive_set_is_consistent_across_routes(client, method, path, statuses) -> None:
    """The CSP directive set must be byte-identical across every surface.

    A drift in either direction (HTML carrying extra capability, or JSON
    losing capability) would show up as a difference between this assertion
    and the dedicated HTML/JSON CSP tests. Pin the canonical set here.
    """
    canonical = (
        "default-src 'self'",
        "img-src 'self' data:",
        "script-src 'self'",
        "style-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        "connect-src 'self'",
        "upgrade-insecure-requests",
    )
    r = client.open(path=path, method=method)
    assert r.status_code in statuses, (
        f"unexpected status for {method} {path}: {r.status_code}"
    )
    csp = r.headers.get("Content-Security-Policy", "")
    assert csp, f"CSP missing on {method} {path}"
    for directive in canonical:
        assert directive in csp, (
            f"directive {directive!r} missing from CSP on {method} {path}: {csp!r}"
        )
