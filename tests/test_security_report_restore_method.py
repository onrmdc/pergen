"""M-03 — `/api/reports/<id>?restore=1` causes side effect via GET.

A GET request triggers a write into the in-memory run-state store. This
violates HTTP semantics and dodges any future POST-only CSRF guard.

Audit reference: ``docs/security/audit_2026-04-22.md`` §3.2 M-03.

Desired contract: restore must require POST. XFAIL until the route is
fixed.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security]


@pytest.mark.xfail(
    reason="audit M-03 — restore is reachable via GET; should require POST",
    strict=True,
)
def test_restore_via_get_is_method_not_allowed(client) -> None:
    """A GET to /api/reports/<id>?restore=1 must return 405."""
    # Use any string id; the method check should reject before lookup.
    r = client.get("/api/reports/anything?restore=1")
    assert r.status_code == 405, (
        f"GET ?restore=1 returned {r.status_code}; restore must be POST-only"
    )


@pytest.mark.xfail(
    reason="audit M-03 — POST verb for restore is not yet implemented (currently 405)",
    strict=True,
)
def test_restore_via_post_is_supported(client) -> None:
    """Once M-03 lands, POST must be the supported verb for restore."""
    # Today returns 405 because /api/reports/<id> only accepts GET.
    # When the fix lands, POST should return 200/204/404 (depending on id).
    r = client.post("/api/reports/nonexistent?restore=1")
    assert r.status_code in (200, 204, 404), (
        f"POST /api/reports/<id>?restore=1 returned {r.status_code}; "
        f"M-03 fix requires POST support for restore"
    )
