"""M-02 — `/api/run/result/<run_id>` returns full state with no actor scope.

Any authenticated caller who knows a `run_id` can fetch the full PRE/POST
state of any run — including sensitive command outputs (BGP advertisements,
ARP tables). With multi-actor token gating, an actor should only see runs
they created.

Audit reference: ``docs/security/audit_2026-04-22.md`` §3.2 M-02.

XFAIL until per-run actor scoping lands (requires `RunStateStore` to record
`created_by_actor`).
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security]


@pytest.mark.xfail(
    reason="audit M-02 — run state is not actor-scoped",
    strict=True,
)
def test_run_result_rejects_actor_mismatch(monkeypatch, client) -> None:
    """Bob must not be able to read Alice's run state via /api/run/result/<id>."""
    monkeypatch.setenv(
        "PERGEN_API_TOKENS",
        "alice:" + "a" * 32 + ",bob:" + "b" * 32,
    )
    # Alice creates a pre-run.
    pre_payload = {
        "name": "alice-run",
        "devices": [{"hostname": "h", "ip": "1.2.3.4"}],
        "device_results": {},
    }
    rcreate = client.post(
        "/api/run/pre/create",
        json=pre_payload,
        headers={"X-API-Token": "a" * 32},
    )
    assert rcreate.status_code in (200, 201), rcreate.get_data(as_text=True)
    rid = rcreate.get_json().get("run_id") or rcreate.get_json().get("id")
    assert rid

    # Bob attempts to read Alice's run.
    r = client.get(
        f"/api/run/result/{rid}",
        headers={"X-API-Token": "b" * 32},
    )
    assert r.status_code in (403, 404), (
        f"actor scoping missing: bob reached alice's run state ({r.status_code})"
    )
