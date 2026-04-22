"""W4-M-02 — Anonymous-actor runs leak to every authenticated actor.

Wave-4 audit §3.2 W4-M-02. The actor-scoping check in
``RunStateStore.get`` reads:

    if actor is not None and owner is not None and owner != actor:

The ``owner is not None`` guard makes scoping a no-op when no owner
was recorded — every run created with ``actor=None`` is readable by
every authenticated actor that subsequently asks for it.

Fixing this requires tightening ``set()`` to always record an owner
(defaulting to ``"anonymous"``) AND updating ``get()`` to refuse
when ``owner == "anonymous"`` AND the caller passes a non-None actor.

Marked xfail until the tightening lands.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security]


def test_runstatestore_anonymous_run_not_readable_by_named_actor() -> None:
    """A run stored with actor=None must not leak to actor='alice'."""
    from backend.services.run_state_store import RunStateStore

    store = RunStateStore()
    store.set("X", {"phase": "PRE", "data": 1}, actor=None)
    assert store.get("X", actor="alice") is None, (
        "anonymous-create run leaked to a named actor — see W4-M-02"
    )


def test_runstatestore_anonymous_run_readable_by_anonymous() -> None:
    """Sanity: when both creator and reader are anonymous, the read works."""
    from backend.services.run_state_store import RunStateStore

    store = RunStateStore()
    store.set("X", {"phase": "PRE", "data": 1}, actor=None)
    # Both anonymous — read must succeed (legacy permissive mode).
    assert store.get("X", actor=None) is not None
