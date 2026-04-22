# DONE — Wave-4 Audit Follow-ups — SEALED

**Status:** **CLOSED 2026-04-22** in the wave-5 refactor close-out
session (commits land on the same `refactor/ood-tdd` branch). Every
audit-tracker `xfail` is now a passing test. The refactor program is
officially sealed.

**Source:** `docs/security/audit_2026-04-22-wave4.md` — 1 NEW HIGH (closed),
5 NEW MEDIUM (all closed), 4 LOW + 3 INFO (intentionally not pinned;
polish-pass items).

## Closed in wave-4

- **W4-H-01** — `/api/run/post/complete` actor-scoping bypass — 1-line fix
  in `backend/blueprints/runs_bp.py:312` (`actor=_current_actor()` arg
  added). Pinned by `tests/test_security_run_post_complete_actor_scoping.py`.
- **W4-M-04** — notepad log-injection — control-char strip + 64-char cap
  in `backend/blueprints/notepad_bp.py:58`. Pinned by
  `tests/test_security_notepad_log_injection.py`.
- **W4-M-05** — bgp_lg `_get_json` Location-header echo — opaque envelope
  in `backend/bgp_looking_glass/http_client.py:51`. Pinned by
  `tests/test_security_bgp_lg_redirect_no_location_echo.py`.

## Closed in wave-5 (refactor close-out)

### W4-M-01 — `POST /api/reports/<id>/restore` actor-scoping ✅

**Test:** `tests/test_security_report_restore_actor_scoping.py` — passing.

**Implementation:**
1. Added `created_by_actor: str | None = None` parameter to
   `ReportRepository.save()` (`backend/repositories/report_repository.py:55`).
   Persisted into both the gzipped payload AND the index entry.
2. `load(run_id, actor=None)` returns `None` for cross-actor reads —
   mirrors `RunStateStore.get` semantics (treats IDOR mismatch as
   "not found" so the response cannot disclose run-id existence).
3. `list(actor=None)` projects out cross-actor entries.
4. `delete(run_id, actor=None)` becomes a silent no-op for cross-actor
   delete attempts (no-disclosure).
5. `api_reports_list`, `api_report_get`, `api_report_restore`,
   `api_report_delete` all thread `_scoping_actor()`.
6. `_report_service().save(...)` callers in `runs_bp.py` now pass
   `created_by_actor=_current_actor() or "anonymous"`.
7. Operator backfill CLI:
   `python -m backend.cli.backfill_report_actors [--owner=...] [--dry-run]`
   stamps existing reports with the supplied owner (default "legacy").
   Idempotent: re-running on a partially-stamped dataset is a no-op.
8. CLI is unit-tested at `tests/test_cli_backfill_report_actors.py` (8 tests).

### W4-M-02 — Anonymous-actor runs leak to authenticated actors ✅

**Test:** `tests/test_security_runstatestore_anonymous_isolation.py` — passing.

**Implementation:**
1. `RunStateStore.set()` now ALWAYS records `_created_by_actor` —
   either the supplied `actor` or the literal `"anonymous"` sentinel.
2. `get()` enforces cross-bucket isolation:
   `caller = actor if actor is not None else "anonymous"; if owner != caller: return None`
3. Updated `tests/test_security_audit_findings.py::test_run_state_store_concurrent_set_does_not_lose_writes`
   to pop the marker before strict equality compare.
4. The 2 callers (`runs_bp` + `reports_bp`) already passed `actor=`
   correctly — no behavioural change for in-tree code.

### W4-M-03 — `RunStateStore.update()` has no actor parameter ✅

**Test:** `tests/test_security_runstatestore_update_actor_scoping.py` — both passing.

**Implementation:**
1. New signature:
   `update(self, run_id, *, actor: str | None = None, **fields) -> dict | None`
2. Same cross-bucket actor check as `get()`.
3. Raises `ValueError` if `_created_by_actor` is in `fields` —
   ownership marker is set exclusively by `set()`.
4. Both callers in `runs_bp.py` (lines 286 + 329) now pass
   `actor=_current_actor()`.

## LOW + INFO findings

The 4 LOW + 3 INFO findings from `docs/security/audit_2026-04-22-wave4.md`
§3.3 and §3.4 are noted but not pinned by tests — they are minor hardening
items deferred to a future polish pass.

## Final state

After wave-5 close-out:

- pytest: **1631 passed, 0 xfailed** (was 1619 + 4 at wave-5 start).
- Vitest: 37 passing.
- Playwright: 90 tests in 41 spec files.
- Whole-project coverage: **90.23 %** (held essentially flat at 90.4 %
  with +12 production LOC offset by +8 CLI tests).
- New module: `backend/cli/` with the W4-M-01 backfill operator tool.

The wave-4 audit is fully addressed. Every remaining item in
`docs/refactor/` is reclassified as **future feature work**, not
unfinished refactor debt — see the "Reclassified" section in
`wave3_roadmap.md`.
