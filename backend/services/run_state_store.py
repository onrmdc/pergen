"""
``RunStateStore`` — thread-safe in-memory store for active pre/post run state.

Replaces the module-global ``_run_state`` dict in ``backend/app.py``
with an explicit, lock-protected, TTL-aware object.

Audit H6 fixes (post-Phase-13):
* ``threading.RLock`` guards every operation (set/get/update/delete).
* ``get`` returns a deep copy so callers cannot mutate the store via
  the returned reference.
* Optional TTL evicts old runs (defaults to 1 h) — bounds memory growth
  under unauthenticated load.
* Optional ``max_entries`` cap with FIFO eviction prevents an attacker
  from flooding the store.
* Explicit ``delete`` method so callers can free state on
  ``/api/run/result`` cleanup or admin requests.
"""
from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from typing import Any

# Defaults chosen so the historical zero-config behaviour stays usable:
# 1 hour TTL is comfortably longer than any real pre→post operator flow,
# and 1024 entries fits within ~tens of MB even with large device_results.
_DEFAULT_TTL = 3600
_DEFAULT_MAX_ENTRIES = 1024


class RunStateStore:
    """Thread-safe key/value store for transient pre/post run state."""

    def __init__(
        self,
        ttl_seconds: int | None = _DEFAULT_TTL,
        max_entries: int = _DEFAULT_MAX_ENTRIES,
    ) -> None:
        # OrderedDict so we get O(1) FIFO eviction.
        self._state: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._lock = threading.RLock()
        self._ttl = ttl_seconds  # None disables TTL
        self._max = max_entries

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #
    # Sentinel literal for the anonymous-actor bucket. Stored verbatim
    # in ``_created_by_actor`` so the actor-scope check below can refuse
    # cross-bucket reads (named caller cannot read anonymous-create;
    # anonymous caller cannot read named-create).
    _ANON_OWNER: str = "anonymous"

    def get(self, run_id: str, actor: str | None = None) -> dict | None:
        """Return a *deep copy* of the stored value, or ``None`` if expired/missing.

        Audit M-02 (wave-3) + W4-M-02 (wave-4): scoping is now ALWAYS active.
        ``set()`` always records an owner — either the supplied ``actor`` or
        the literal ``"anonymous"``. ``get(actor=X)`` returns ``None`` (not
        the value) for any cross-bucket attempt:

        * named caller, anonymous-create entry → refused.
        * anonymous caller, named-create entry → refused.
        * named caller, different-named-create → refused (the wave-3 case).

        IDOR mismatch is treated identically to "not found" so the
        response cannot disclose run-id existence.
        """
        with self._lock:
            entry = self._state.get(run_id)
            if entry is None:
                return None
            ts, value = entry
            if self._is_expired(ts):
                # Lazy expiry — pop on read.
                self._state.pop(run_id, None)
                return None
            # Wave-4 W4-M-02: cross-bucket actor check (always active).
            owner = value.get("_created_by_actor", self._ANON_OWNER)
            caller = actor if actor is not None else self._ANON_OWNER
            if owner != caller:
                return None
            # Move to end (LRU touch) so accessed runs survive eviction.
            self._state.move_to_end(run_id)
            return copy.deepcopy(value)

    def set(self, run_id: str, value: dict, *, actor: str | None = None) -> None:
        """Store a *deep copy* of ``value`` under ``run_id``.

        Audit M-02 (wave-3) + W4-M-02 (wave-4): ``_created_by_actor`` is
        ALWAYS recorded — either the supplied ``actor`` or the literal
        ``"anonymous"``. The explicit ``actor=`` argument always wins
        over any value already in ``value["_created_by_actor"]``.
        """
        with self._lock:
            self._evict_expired()
            stored = copy.deepcopy(value)
            stored["_created_by_actor"] = actor if actor is not None else self._ANON_OWNER
            self._state[run_id] = (time.monotonic(), stored)
            self._state.move_to_end(run_id)
            # FIFO cap (oldest entry first).
            while len(self._state) > self._max:
                self._state.popitem(last=False)

    def update(
        self, run_id: str, *, actor: str | None = None, **fields: Any
    ) -> dict | None:
        """Patch fields on an existing run; return a deep copy or ``None``.

        Wave-4 W4-M-03: ``actor`` mirrors ``get()`` semantics — cross-bucket
        updates are refused with the same "not found" disclosure-safe shape.

        Wave-4 W4-M-03 paired guard: ``_created_by_actor`` is rejected as
        a writable field. The ownership marker is set exclusively by
        ``set()`` (or by an explicit future re-assign API) — never by an
        ad-hoc ``update`` call.
        """
        if "_created_by_actor" in fields:
            raise ValueError(
                "_created_by_actor is a reserved field; use set() to assign ownership"
            )
        with self._lock:
            entry = self._state.get(run_id)
            if entry is None:
                return None
            ts, value = entry
            if self._is_expired(ts):
                self._state.pop(run_id, None)
                return None
            # Wave-4 W4-M-03: cross-bucket actor check (mirrors get()).
            owner = value.get("_created_by_actor", self._ANON_OWNER)
            caller = actor if actor is not None else self._ANON_OWNER
            if owner != caller:
                return None
            new_value = copy.deepcopy(value)
            new_value.update(fields)
            self._state[run_id] = (time.monotonic(), new_value)
            self._state.move_to_end(run_id)
            return copy.deepcopy(new_value)

    def delete(self, run_id: str) -> bool:
        """Remove ``run_id`` from the store. Returns True iff something was removed."""
        with self._lock:
            return self._state.pop(run_id, None) is not None

    def __contains__(self, run_id: str) -> bool:
        with self._lock:
            entry = self._state.get(run_id)
            if entry is None:
                return False
            ts, _ = entry
            if self._is_expired(ts):
                self._state.pop(run_id, None)
                return False
            return True

    def __len__(self) -> int:
        with self._lock:
            self._evict_expired()
            return len(self._state)

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #
    def _is_expired(self, ts: float) -> bool:
        if self._ttl is None:
            return False
        return (time.monotonic() - ts) > self._ttl

    def _evict_expired(self) -> None:
        if self._ttl is None:
            return
        now = time.monotonic()
        expired = [k for k, (ts, _) in self._state.items() if (now - ts) > self._ttl]
        for k in expired:
            self._state.pop(k, None)
