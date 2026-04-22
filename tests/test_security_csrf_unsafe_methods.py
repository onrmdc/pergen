"""H-03 — CSRF protection on state-changing endpoints.

In dev/test mode the API token gate is OPEN (`PERGEN_API_TOKEN(S)` unset).
Without a `Content-Type` check, a malicious page can submit a `text/plain`
form whose body parses as JSON and trigger writes from a victim's browser.

Audit reference: ``docs/security/audit_2026-04-22.md`` §3.1 H-03.

Pin the desired contract: every state-changing route must reject requests
that don't carry `Content-Type: application/json` (or a custom header like
`X-Requested-With`). XFAIL until the guard lands.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security]

# Routes whose POST/PUT/DELETE shape accepts JSON bodies and would be CSRF-able
# from a cross-origin form post if Content-Type isn't enforced.
CSRF_TARGETS: list[tuple[str, str, dict]] = [
    ("POST", "/api/inventory/device", {"hostname": "x", "ip": "1.2.3.4"}),
    ("POST", "/api/credentials", {"name": "x", "method": "basic", "username": "u", "password": "p"}),
    ("PUT", "/api/notepad", {"content": "abc"}),
]


@pytest.mark.parametrize("method,path,payload", CSRF_TARGETS)
def test_state_changing_route_rejects_text_plain(
    client, method: str, path: str, payload: dict
) -> None:
    """Cross-origin form POST as text/plain must NOT mutate state."""
    import json as _json

    r = client.open(
        path,
        method=method,
        data=_json.dumps(payload),
        content_type="text/plain",
    )
    # Acceptable: 400 (bad request), 415 (unsupported media), 403 (forbidden).
    # NOT acceptable: 200/201/204 (success — would mean the body was accepted).
    assert r.status_code in (400, 403, 415), (
        f"{method} {path} accepted text/plain CSRF body (status={r.status_code}); "
        f"must reject without a JSON Content-Type"
    )


@pytest.mark.parametrize("method,path,payload", CSRF_TARGETS)
def test_state_changing_route_accepts_application_json(
    client, method: str, path: str, payload: dict
) -> None:
    """Sanity check: same payload via application/json still works (or returns
    a domain-level 400, not a CSRF-bait 415)."""
    r = client.open(path, method=method, json=payload)
    # Domain-level outcomes are fine; a 415 here would indicate the test
    # client itself isn't using application/json.
    assert r.status_code != 415
