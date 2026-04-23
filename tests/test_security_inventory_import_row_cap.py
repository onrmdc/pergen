"""Audit GAP #8 — ``/api/inventory/import`` accepts unbounded ``rows``.

Audit reference: ``backend/services/inventory_service.py::import_devices``
loops over every entry in the ``rows`` array with no maximum. A 6 000+
row body is well under the 10 MiB ``MAX_CONTENT_LENGTH`` cap (each row
is ~100 bytes), so the size guard does not protect this endpoint —
the loop runs to completion, holding the inventory mutex and burning
CPU on per-row sanitiser regex.

The hardening (not yet landed): cap rows at 5 000 and return 400 / 413
when exceeded. This file pins the *current* behaviour so a future
operator who lands the cap sees an immediate green XPASS and knows to
flip the assertion direction.

Marked ``xfail(strict=False)`` deliberately:
  * If the cap has not landed → request succeeds with 200 (today) →
    inverted assertion fails → xfail "encodes the gap".
  * If the cap lands → request returns 400/413 → assertion passes →
    XPASS surfaces in CI as a signal to flip the marker.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security]

# The threshold the audit recommends. Above this, the endpoint should
# refuse the request rather than silently iterate.
_RECOMMENDED_CAP = 5000
# Test payload size: well above the cap so the threshold is unambiguous.
_OVERSIZE_ROW_COUNT = 6000


def _row(i: int) -> dict:
    """Build a unique, valid inventory row.

    IP allocation starts at ``10.10.0.0`` so we never collide with the
    seed inventory the ``mock_inventory_csv`` fixture provides
    (``10.0.0.1`` / ``10.0.0.2``).
    """
    base = i + 10 * 65536  # offset into the 10.10.0.0/16 block
    return {
        "hostname": f"capacity-test-{i:05d}",
        "ip": f"10.{(base // 65536) % 256}.{(base // 256) % 256}.{base % 256}",
        "fabric": "FAB1",
        "site": "Mars",
        "hall": "Hall-1",
        "vendor": "Arista",
        "model": "EOS",
        "role": "Leaf",
        "tag": "",
        "credential": "test-cred",
    }


def test_oversize_import_request_succeeds_today_baseline(client) -> None:
    """Pin current behaviour: 6000 rows is accepted (200) — no cap exists.

    This is the un-marked baseline assertion. When the cap lands and this
    starts failing, replace it with the assertion in the xfail test below
    (status in (400, 413)).
    """
    rows = [_row(i) for i in range(_OVERSIZE_ROW_COUNT)]
    r = client.post("/api/inventory/import", json={"rows": rows})
    # Today's behaviour: 200 + body documents what was added/skipped.
    # If this changes to 400/413 the cap has landed — flip the marker.
    assert r.status_code == 200, (
        f"baseline drift: oversize import used to return 200; got "
        f"{r.status_code}. If the row cap has landed, update the xfail "
        f"marker on test_oversize_import_request_is_capped below."
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Audit GAP #8: /api/inventory/import has no row cap. Currently "
        "iterates over arbitrarily large `rows` arrays. Will XPASS once "
        "the 5000-row cap lands and the route returns 400/413."
    ),
)
def test_oversize_import_request_is_capped(client) -> None:
    """Desired behaviour: 6000 rows is rejected with 400 or 413."""
    rows = [_row(i) for i in range(_OVERSIZE_ROW_COUNT)]
    r = client.post("/api/inventory/import", json={"rows": rows})
    assert r.status_code in (400, 413), (
        f"oversize import must be rejected with 400 or 413, got "
        f"{r.status_code}; body={r.get_data(as_text=True)[:200]!r}"
    )


def test_undersize_import_is_accepted(client) -> None:
    """Counter-test: a small batch (10 rows) is always accepted.

    Guards against an over-eager cap that rejects legitimate operator
    bulk-add workflows.
    """
    rows = [_row(i) for i in range(10)]
    r = client.post("/api/inventory/import", json={"rows": rows})
    assert r.status_code == 200, (
        f"a 10-row import must succeed; got {r.status_code} "
        f"body={r.get_data(as_text=True)!r}"
    )
    body = r.get_json()
    assert body.get("ok") is True
    assert body.get("added", 0) == 10
    assert body.get("skipped") == []


def test_recommended_cap_is_documented_in_test() -> None:
    """Self-documenting: pin the recommended cap value at 5 000.

    If the audit recommendation changes, update both ``_RECOMMENDED_CAP``
    here and the corresponding constant in
    ``backend/services/inventory_service.py``.
    """
    assert _RECOMMENDED_CAP == 5000
    assert _OVERSIZE_ROW_COUNT > _RECOMMENDED_CAP, (
        "test payload must exceed the recommended cap to be a meaningful "
        "regression test"
    )
