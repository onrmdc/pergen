"""W4-M-03 — `RunStateStore.update()` does not enforce actor scoping.

Wave-4 audit §3.2 W4-M-03. ``update()`` performs a get-then-merge
without checking the caller's actor, AND it accepts arbitrary
``**fields`` — including the reserved ``_created_by_actor`` key.

No HTTP route reaches this primitive today (every ``update`` call
in ``runs_bp`` uses hardcoded keyword arguments), so the issue is
fragile-API rather than directly exploitable. Marked xfail until
``update()`` grows an ``actor=`` parameter that mirrors ``get()``.

Two related contracts pinned:
1. Cross-actor update is refused.
2. ``_created_by_actor`` is rejected as a writable field.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security]


@pytest.mark.xfail(
    reason="W4-M-03 — RunStateStore.update has no actor parameter; the "
    "wave-3 actor-scope design pinned the safety check to get() only.",
    strict=True,
)
def test_runstatestore_update_refuses_cross_actor() -> None:
    """Bob must not be able to update Alice's run via update()."""
    from backend.services.run_state_store import RunStateStore

    store = RunStateStore()
    store.set("X", {"phase": "PRE"}, actor="alice")
    # update() should grow an actor= parameter; bob should get None back.
    out = store.update("X", actor="bob", post_results="tampered")  # type: ignore[call-arg]
    assert out is None


@pytest.mark.xfail(
    reason="W4-M-03 — update() does not reject the reserved "
    "_created_by_actor key in **fields.",
    strict=True,
)
def test_runstatestore_update_rejects_creator_field() -> None:
    """`_created_by_actor` must not be a writable field via update()."""
    from backend.services.run_state_store import RunStateStore

    store = RunStateStore()
    store.set("X", {"phase": "PRE"}, actor="alice")
    with pytest.raises(ValueError):
        store.update("X", _created_by_actor="bob")
