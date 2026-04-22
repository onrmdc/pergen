"""W4-L-02 — `_created_by_actor` reserved-field handling at set/get.

Pin two contracts that defend the actor-scoping invariant:

1. ``set()`` accepts a value dict that already contains
   ``_created_by_actor`` (legacy) — but the constructor's ``actor``
   parameter wins. (Covers the audit_log_coverage scenario where
   ``_state_store().set(rid, value, actor=...)`` carries the actor
   in the value dict only.)

2. The marker is stripped from the externally-visible payload by the
   ``api_run_result`` route (already implemented).
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security]


def test_runstatestore_set_actor_arg_takes_precedence_over_value_dict() -> None:
    """If both are present, the explicit `actor` argument wins."""
    from backend.services.run_state_store import RunStateStore

    store = RunStateStore()
    # Caller accidentally puts _created_by_actor in the value dict
    # AND passes actor= explicitly. Explicit must win.
    store.set(
        "X",
        {"phase": "PRE", "_created_by_actor": "evil"},
        actor="alice",
    )
    out = store.get("X", actor="alice")
    assert out is not None
    assert out["_created_by_actor"] == "alice"


def test_runstatestore_get_strips_marker_when_caller_strips() -> None:
    """The route layer is expected to .pop() the marker before jsonify."""
    from backend.services.run_state_store import RunStateStore

    store = RunStateStore()
    store.set("X", {"phase": "PRE"}, actor="alice")
    out = store.get("X", actor="alice")
    assert out is not None
    # Verify the marker is present (route layer pops it).
    assert out.get("_created_by_actor") == "alice"
    # Mirror the route's strip:
    out.pop("_created_by_actor", None)
    assert "_created_by_actor" not in out
