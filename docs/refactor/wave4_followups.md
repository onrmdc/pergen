# Wave-4 Audit Follow-ups

**Status:** plan only — no production code changes proposed in this doc.
Each item below is pinned by a strict-`xfail` test under `tests/test_security_*.py`
that flips to a real green pass once the fix lands.

**Source:** `docs/security/audit_2026-04-22-wave4.md` — 1 NEW HIGH (closed),
5 NEW MEDIUM (2 closed in wave-4, 3 deferred to this plan), 4 LOW, 3 INFO.

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

## Deferred (3 items, each pinned by strict-xfail)

### W4-M-01 — `POST /api/reports/<id>/restore` actor-scoping

**Test:** `tests/test_security_report_restore_actor_scoping.py` (1 strict-xfail).

**Why deferred:** report-on-disk format (`backend/repositories/report_repository.py`)
carries no `created_by_actor` field. Adding it requires:
1. Tighten `ReportRepository.save()` to record creator
2. Tighten `ReportRepository.list()` and `load()` to optionally filter by actor
3. Backfill the existing `instance/reports/` files (data migration)
4. Update `api_reports_list` and `api_report_get` to project / refuse cross-actor

**Estimated effort:** 1.5 days. Includes a one-shot CLI to backfill
`created_by_actor="legacy"` on existing reports.

**Plan:**
1. Add `created_by_actor: str | None = None` parameter to `ReportRepository.save`.
2. Persist into the gzipped JSON payload AND the index entry.
3. `load(run_id, actor=None)` returns None for cross-actor reads (mirror
   `RunStateStore.get` semantics).
4. `list(actor=None)` projects out cross-actor entries.
5. Update `api_reports_list`, `api_report_get`, `api_report_restore` to thread
   the current actor.
6. Backfill CLI: `python -m backend.cli backfill-report-actors --legacy-actor=migration-2026`.

### W4-M-02 — Anonymous-actor runs leak to authenticated actors

**Test:** `tests/test_security_runstatestore_anonymous_isolation.py` (1 strict-xfail).

**Why deferred:** changes the actor-scope semantics from "scoping is opt-in
via the actor= argument" to "scoping is always active when ANY caller is
non-anonymous". Need to verify no existing test or route relies on the
permissive behaviour.

**Estimated effort:** 0.5 day. Single-file change in
`backend/services/run_state_store.py` with grep audit of every caller.

**Plan:**
1. In `RunStateStore.set()`: if `actor` is None, store
   `_created_by_actor="anonymous"` (always-record).
2. In `RunStateStore.get()`: refuse cross-bucket reads —
   `if owner == "anonymous" and actor is not None: return None`
   (named caller cannot read anonymous; anonymous caller cannot read named).
3. Verify the 2 callers (`runs_bp` + `reports_bp`) pass actor= correctly.

### W4-M-03 — `RunStateStore.update()` has no actor parameter

**Test:** `tests/test_security_runstatestore_update_actor_scoping.py` (2 strict-xfail).

**Why deferred:** API surface change. Need to add `actor=` parameter mirroring
`get()` AND reject `_created_by_actor` as a writable field. No HTTP route
currently passes `**user_data` so this is fragile-API rather than directly
exploitable.

**Estimated effort:** 0.5 day.

**Plan:**
1. `update(self, run_id, *, actor: str | None = None, **fields) -> dict | None`.
2. Same actor-scope check as `get()`.
3. Raise `ValueError` if `_created_by_actor` is in `fields`.
4. Update the 1 caller in `runs_bp.py:325` to pass `actor=_current_actor()`.

## LOW + INFO findings

The 4 LOW + 3 INFO findings from `docs/security/audit_2026-04-22-wave4.md`
§3.3 and §3.4 are noted but not pinned by tests — they are minor hardening
items deferred to a future polish pass.

## Suggested shipping order

1. **W4-M-02** (0.5 day) — single-file change, no data migration.
2. **W4-M-03** (0.5 day) — adds `actor=` parameter; same shape as M-02.
3. **W4-M-01** (1.5 days) — data-bearing change, requires backfill CLI.

After all 3 land, the wave-4 strict-xfail count drops from 4 → 0 (the
last xfail is `W4-M-03`'s second assertion which auto-flips when the
`update()` API change lands).
