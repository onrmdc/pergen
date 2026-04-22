"""H-04 — `/api/diff` line-count DoS guard.

The byte cap (256 KB per side) does not prevent pathological line counts;
``difflib.unified_diff`` is O(n*m), so 130_000 × 130_000 lines comfortably
fit under the byte cap and tie up a worker for minutes.

Audit reference: ``docs/security/audit_2026-04-22.md`` §3.1 H-04.

This test pins the desired contract: pathological inputs must be rejected
with HTTP 413 *and* a clear error message. It is XFAIL until the line cap
is implemented (planned in a future PR; sister to the diff byte cap).
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security]


@pytest.mark.xfail(
    reason="audit H-04 — /api/diff has no line-count cap; only byte cap",
    strict=True,
)
def test_diff_rejects_pathological_line_count(client) -> None:
    """One-byte lines × 130 000 = ~256 KB but ~10^10 difflib comparisons."""
    pre = "a\n" * 130_000
    post = "b\n" * 130_000
    # Both sides ≤ 256 KB so the byte cap passes.
    assert len(pre) <= 256 * 1024
    assert len(post) <= 256 * 1024

    r = client.post("/api/diff", json={"pre": pre, "post": post})

    # Desired contract: pathological line counts are rejected with 413.
    assert r.status_code == 413, (
        f"expected 413 Payload Too Large for {len(pre.splitlines())} lines × "
        f"{len(post.splitlines())} lines; got {r.status_code}"
    )
    body = r.get_json() or {}
    assert "line" in (body.get("error") or "").lower()


def test_diff_below_line_cap_succeeds(client) -> None:
    """A reasonable diff request still works (regression guard)."""
    pre = "old line\n" * 100
    post = "new line\n" * 100
    r = client.post("/api/diff", json={"pre": pre, "post": post})
    assert r.status_code == 200
    body = r.get_json()
    assert "diff" in body
