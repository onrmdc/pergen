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

## Status Log

| Date | Phase | Outcome |
|------|-------|---------|
| 2026-04-22 | 0   | (this commit) baseline locked |
| (pending) | 1-14 | in execution |

Each phase lands as its own commit (or small commit set) on this branch
with a phase header in the commit message. The roadmap doc is updated
after each phase to record the outcome and any deviation from plan.
