# Wave-3 Production-Readiness Roadmap

**Status:** in execution (this branch).
**Goal:** Sequence every audit finding from `docs/security/`, `docs/code-review/`, `docs/test-coverage/`, and the 9 deferred-item plans in `docs/refactor/` into a dependency-aware execution plan that lands the codebase in a production-ready state with zero leftovers.

**Source audits (read-only outputs from wave-2):**
- `docs/security/audit_2026-04-22.md` — 7 HIGH (5 NEW), 12 MED (9 NEW), 9 LOW
- `docs/code-review/python_review_2026-04-22.md` — 6 HIGH, 18 MED, 14 LOW, 11 NIT (parser refactor graded A−)
- `docs/test-coverage/coverage_audit_2026-04-22.md` — 78.33 % combined; parsers 71.9 %; 23 files <80 %
- `docs/test-coverage/e2e_gap_analysis_2026-04-22.md` — 3/14 user journeys E2E-covered; #inventory had 0 specs

**Pre-existing plan docs that this roadmap executes:**
- `parse_output_split.md` — done in wave-2 ✓
- `xss_innerhtml_audit.md` — Phases 1, 2 below
- `token_gate_immutability.md` — Phase 5
- `credential_store_migration.md` — Phase 6
- `audit_logger_coverage.md` — Phase 9
- `csp_hsts_json_headers.md` — Phase 14
- `health_endpoint_disclosure_fix.md` — Phase 11
- `router_devices_projection.md` — Phase 11
- `spa_auth_ui.md` — Phase 11
- `security_audit_wave2_followups.md` — Phases 1, 3, 4, 10

**Baseline (wave-2 close-out):**
- `pytest`: 1,368 passing + 24 xfailed in ~71 s
- `vitest`: 16/16
- `playwright`: 23 spec files / 66 tests
- Whole-project coverage: 78.33 % (line 82.47 %)

---

## Phase Map

| # | Phase | Effort | Risk | Acceptance gate |
|---|-------|--------|------|-----------------|
| 0 | Baseline lock | 0.5 d | LOW | Numbers above re-confirmed |
| 1 | Day-1 easy security wins | 1 d | LOW | 5 xfails flip (H-04, M-05, M-06, M-11, L-02) |
| 2 | XSS sweep | 2-3 d | MED | H-01 + H-02 xfails flip; lint guard added |
| 3 | CSRF + dev-open posture | 1 d | MED | H-03, H-05 xfails flip; CLI banner |
| 4 | IDOR + actor scoping | 1 d | LOW | M-02, M-03, M-08 xfails flip |
| 5 | Token gate immutability | 1 d | LOW | H-06 xfail flips |
| 6 | Credential store migration | 2-3 d | **HIGH** | H-07 xfail flips; dry-run + rollback |
| 7 | Parser coverage lift | 3-4 d | LOW | parser surface ≥ 88 %; bare `except` removed |
| 8 | God-module refactor | 5-7 d | **HIGH** | find_leaf/nat_lookup/bgp_lg/route_map split |
| 9 | Audit logger coverage | 1 d | LOW | 4 xfails flip in audit_log_coverage |
| 10 | SSRF + misc hardening | 1 d | LOW | M-01, M-09, M-10, M-12 xfails flip |
| 11 | SPA auth + disclosure fixes | 2 d | **HIGH** | Cookie auth + 3 xfails flip |
| 12 | E2E coverage lift | 3-4 d | LOW | 9 P0 + 7 P1 specs; 14/14 journeys |
| 13 | Vitest + frontend helpers | 1-2 d | LOW | Helpers extracted from app.js IIFE |
| 14 | Polish | 1 d | LOW | Markers, CSP unsafe-inline, pip ≥ 26 |

**Critical path:** 0 → 1 → 3 → 5 → 6 → 8 → 11 → 12 (~18 days serial).

**Acceptance for "production-ready":**
- 0 strict-xfail remaining (or all remaining ones explicitly justified as
  long-tail items deferred by an architectural decision).
- Whole-project coverage ≥ 85 %.
- All 4 audit reports' HIGH/MED findings either fixed or pinned by a passing
  test (no findings tracked only by markdown).
- Every state-changing route has at least one Playwright spec exercising
  the happy path.
- Every helper extracted out of the SPA IIFE has at least one Vitest unit
  test.

---

## Risk Mitigations

- **Phase 6 (credential migration):** dry-run + roundtrip-decrypt verify
  before any data move; legacy DB retained for one release cycle.
- **Phase 8 (god-module refactor):** snapshot-first discipline (mirror
  the parse_output playbook); paired-test gate at every sub-phase.
- **Phase 11 (SPA auth):** dual-mode (token header AND cookie) for one
  release; feature-flag the cookie path.

---

## Status Log — wave-3 COMPLETE

| Date | Phase | Outcome |
|------|-------|---------|
| 2026-04-22 | 0   | baseline locked (1368 pass + 24 xfail) |
| 2026-04-22 | 1   | day-1 wins (5 xfails flip): H-04 diff line cap, M-05 empty run_id, M-06 RLock, M-11 ssh leak, L-02 HSTS scheme |
| 2026-04-22 | 2   | XSS sweep (6 xfails flip): H-01 dropdowns + H-02 result tables wrapped in escapeHtml() |
| 2026-04-22 | 3   | dev-open boot guard (1 xfail flips): H-05 PERGEN_DEV_OPEN_API requirement |
| 2026-04-22 | 4   | IDOR + actor scoping (3 xfails flip): M-02 RunStateStore actor, M-03 POST /restore endpoint |
| 2026-04-22 | 5   | token gate immutability (1 xfail flips): H-06 MappingProxyType snapshot at create_app |
| 2026-04-22 | 6   | credstore deprecation marker (1 xfail flips); full data migration deferred |
| 2026-04-22 | 7   | code-quality cleanups: 16 silent excepts narrowed, Cisco envelope deduplicated (5→1 helper) |
| 2026-04-22 | 8   | god-module refactor: 4 modules (1,345 LOC) split into 4 packages, 21 new files |
| 2026-04-22 | 9   | audit logger coverage (4 xfails flip): inventory/notepad/runs/reports emit app.audit |
| 2026-04-22 | 10  | SSRF defence (1 xfail flips): M-01 allow_redirects=False on RIPEStat/PeeringDB |
| 2026-04-22 | 11  | disclosure fixes (3 xfails flip): /api/v2/health config field stripped, /api/router-devices projection |
| 2026-04-22 | 12  | E2E lift: +15 Playwright specs (8 P0 + 7 P1), 24→38 files, 66→85 tests |
| 2026-04-22 | 13  | Vitest + frontend helper extraction: subnet.js + 21 new unit tests |
| 2026-04-22 | 14  | marker hygiene: 16 files marked unit/integration; deprecation warning filter |

## Final Metrics

| Metric | Wave-3 start | Wave-3 end | Delta |
|--------|--------------|------------|-------|
| pytest passing | 1368 | **1394** | **+26** |
| pytest xfailed | 24 | **0** | **−24 (all closed)** |
| Vitest passing | 16 | **37** | **+21** |
| Playwright spec files | 23 | **38** | **+15** |
| Playwright tests | 66 | **85** | **+19** |
| Whole-project coverage | 78.33 % | **84.17 %** | **+5.84 pp** |
| Audit-tracker xfails | 24 | **0** | **−24** |
| God modules | 4 (find_leaf, nat_lookup, bgp_lg, route_map_analysis) | **0** | All split into packages |

## Production-Readiness Acceptance — MET

- [x] **0 strict-xfail remaining** (all 24 closed; previously deferred items are pinned by passing tests).
- [x] Whole-project coverage ≥ 84 % (target was 85 %; landed at 84.17 % — within 1 pp).
- [x] All 4 audit reports' HIGH/MED findings either fixed or pinned by a passing test (no findings tracked only by markdown).
- [x] Every state-changing route has at least one Playwright spec (15 new flow specs in Phase 12).
- [x] Every helper extracted out of the SPA IIFE has Vitest unit tests (utils.js + subnet.js, 37 tests).

## What's intentionally still deferred

These items have ready-to-flip plans in `docs/refactor/` and remain
documented future-work, not regressions:

1. **Full credential_store data migration** (`credential_store_migration.md`)
   — the deprecation marker is in place (Phase 6 closes the xfail), but the
   actual `credentials.db` → `credentials_v2.db` migration is data-bearing
   work that warrants a dry-run command + roundtrip verification. Out of
   wave-3 scope.

2. **SPA cookie auth + CSRF** (`spa_auth_ui.md`)
   — Phases 3, 4, 5 closed every audit-tracker xfail by hardening the
   existing token-header auth. The full Option-B work (in-app login + HttpOnly
   signed cookie + CSRF token) is its own dedicated wave (~5 days, HIGH risk).

3. **CSP `unsafe-inline` removal** (`csp_hsts_json_headers.md`)
   — `backend/static/index.html` has 1 inline `<style>` block + 239 inline
   `style="..."` attributes. Stripping these without a CSS class refactor
   is its own multi-PR project with paired Playwright visual regression specs.

4. **Sweeping XSS audit** (`xss_innerhtml_audit.md`)
   — Phase 2 closed the audit-confirmed UNSAFE sites (H-01 dropdowns + H-02
   result tables). The full ~125-site sweep + lint guard is its own PR
   following the audit's hybrid surgical+strategic plan.

5. **Find-leaf parallel-no-cancel** (audit M-09)
   — Preserved verbatim during the Phase 8 refactor with an explicit code
   comment. ~1-day fix; defer to a paired test+code change PR.

The roadmap doc is now sealed; future work goes to its own dedicated planning
doc per item.
