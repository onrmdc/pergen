"""M-08 — Inventory write routes leak whether a hostname/IP exists.

`POST /api/inventory/device` with a duplicate hostname returns a 400 with
the existing hostname in the message. Combined with H-03 (no CSRF), an
attacker can enumerate the inventory by trying hostnames and reading the
distinguishable error.

Audit reference: ``docs/security/audit_2026-04-22.md`` §3.2 M-08.

Desired contract: error message must NOT echo the colliding name. XFAIL
until the error sanitisation lands.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security]


def test_inventory_add_unique_violation_does_not_disclose_existing_hostname(client) -> None:
    """Sequence: add 'leaf-99', try to re-add. The 400 must not contain 'leaf-99'."""
    # Seed via the same route (acts as a fixture in test mode).
    seed = client.post(
        "/api/inventory/device",
        json={"hostname": "leaf-99", "ip": "10.0.0.99"},
    )
    # If seed already collides (because the test conftest seeds a row), that's fine —
    # we still want to prove the second attempt does not echo the name.
    assert seed.status_code in (200, 201, 400)

    r = client.post(
        "/api/inventory/device",
        json={"hostname": "leaf-99", "ip": "10.0.0.100"},
    )
    assert r.status_code == 400
    body = r.get_data(as_text=True)
    assert "leaf-99" not in body, (
        "duplicate-hostname error message echoes the colliding name; "
        "see docs/security/audit_2026-04-22.md M-08"
    )
