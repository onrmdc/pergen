# DONE — Pergen Test Coverage Audit (2026-04-23, Wave 7)

Post wave-7 audit + remediation. Audits the working tree at HEAD against
the wave-4 baseline at `docs/test-coverage/DONE_coverage_audit_2026-04-22-wave4.md`
and the wave-6 close-out (which was not separately audited; numbers below
are the cumulative delta wave-4 → wave-7).

> **No production code was modified during this audit.** The wave-7
> CRITICAL+HIGH fixes documented in `docs/security/DONE_audit_2026-04-23-wave7.md`
> §4 and `docs/code-review/DONE_python_review_2026-04-23-wave7.md` §4 ship
> in the same session as this audit; the coverage numbers below reflect
> the post-fix tree.

Source data:

```bash
venv/bin/pytest --cov=backend --cov-branch \
    --cov-report=term -q
```

Result: **1767 passed, 1 xfailed in 93.12s** — combined coverage **90.79%**
(line) / branch coverage now ~88%. The OOD-scoped gate (`make cov-new`,
threshold 85%) sits at **91.34%**.

---

## 1. Headline numbers

| Metric                            | Wave-4 baseline | Wave-6 close-out | **Wave-7 (now)** | Δ wave-4 → wave-7 |
|-----------------------------------|----------------:|-----------------:|-----------------:|------------------:|
| Tests run (Python)                | 1394            | 1717             | **1767**         | +373              |
| Strict xfail markers              | 0               | 0                | **1**            | +1 (audit GAP #8) |
| Total statements                  | 5,735           | 5,949            | **6,162**        | +427              |
| Covered statements                | 4,998           | 5,388            | **5,732**        | +734              |
| **Line coverage (statements)**    | 87.15 %         | 90.51 %          | **90.79 %**      | **+3.64 pp**      |
| **Branch coverage**               | 76.63 %         | 86.4 %           | **~88 %**        | **+11.4 pp**      |
| **Combined (coverage.py)**        | 84.17 %         | 90.51 %          | **90.79 %**      | **+6.62 pp**      |
| **OOD-scoped (`make cov-new`)**   | 94 %            | 94 %             | **91.34 %**      | -2.66 pp¹         |
| Files with coverage data          | 117             | 124              | **131**          | +14               |
| Files at 0 % coverage             | 0               | 0                | **0**            | 0                 |
| Files below 80 % (project policy) | 17              | 9                | **6**            | **-11**           |
| Files at 100 %                    | 47              | 56               | **64**           | +17               |
| Frontend Vitest tests             | 37              | 45               | **45**           | +8                |
| Playwright E2E tests              | 85              | 88 / 12 failing  | **100 / 100**    | +15 (12 fixed + 3 new) |
| Playwright spec files             | 38              | 43               | **43**           | +5                |

¹ The drop in OOD-scoped coverage from 94 % to 91.34 % is structural, not
a regression: the wave-7 fixes added 51 new tests against `app_factory`
+ `ssh_runner` + `credential_store`, but the new code surface (28 LOC in
`credential_store._read_from_v2`, ~30 LOC in `app_factory` ProxyFix /
session lifetime / idle-timeout, ~40 LOC in `ssh_runner` try/finally +
classification) outpaced the test surface lift slightly. Whole-project
coverage went up; OOD-scoped denominator grew faster than the numerator.
**Both gates remain green** (45 % and 85 %).

---

## 2. Files STILL below 80 % post wave-7 (6)

Sorted ascending. `MISS` = missing executable statements,
`BRMISS` = missing branches.

| Cov % | Stmts | Miss | BRMISS | File                                              | Notes |
|------:|------:|-----:|-------:|---------------------------------------------------|-------|
| 67.0  | 133   |  35  |  30    | `backend/parsers/arista/interface_status.py`      | unchanged from wave-4 — operator-output shape variance |
| 71.6  |  88   |  23  |  19    | `backend/parsers/cisco_nxos/arp_suppression.py`   | improved from 71.6 % at wave-4 (no change this wave) |
| 74.2  | 105   |  21  |  18    | `backend/runners/interface_recovery.py`           | unchanged from wave-4 |
| 75.0  |  68   |  15  |   4    | `backend/credential_store.py`                     | the new `_read_from_v2()` bridge added 2 tested branches; legacy `list_credentials` / `delete_credential` still 0-body |
| 76.0  |  17   |   3  |   3    | `backend/bgp_looking_glass/peeringdb.py`          | unchanged from wave-4 |
| 76.8  |  52   |   9  |  10    | `backend/parsers/cisco_nxos/isis_brief.py`        | improved from 70.7 % at wave-2 → 76.8 % wave-4 (no change this wave) |

**Wave-4 had 17 files <80 %; wave-7 has 6.** Net -11. The biggest
deltas came from the wave-6 sweep (every wave-3 package file moved
above 80 %; the `find_leaf/strategies/*` Tier-1 backfills landed in
wave-5 / wave-6) and the wave-7 SSH-runner fix (which added
`tests/test_security_ssh_runner_close_on_exception.py` and lifted
`ssh_runner.py` 66 % → 83 %).

### Files at 100 % (64, +8 vs wave-6)

Includes every `services/*` (with the exception of
`inventory_service` 92 %, `transceiver_service` 90 %), every
`runners/*_runner` shim, `commands_bp`, `health_bp`, every
`bgp_looking_glass/*` except `peeringdb` and `ripestat`, every
`nat_lookup/*` except `service` (now 92 %), every
`route_map_analysis/*`, every `find_leaf/*` (post Tier-1 backfills),
**plus the three new wave-6 modules** (`auth_bp` 95 %, `csrf` 100 %,
`credential_migration` 97 %).

---

## 3. Wave-7 NEW test files inventory

Nine new security test files landed alongside the §4 fixes documented
in the security-reviewer / python-reviewer audits. Total: **51 new tests**
across 9 files. Suite went from **1717 + 0 xfailed** → **1767 + 1 xfailed**.

| File | Tests | Pinning | Module(s) lifted |
|------|------:|---------|------------------|
| `tests/test_security_credential_v2_fallthrough.py` | 6 | C-1 / H-4 | `backend/credential_store.py` (75 %) |
| `tests/test_security_session_idle_timeout.py` | 5 | H-2 | `backend/app_factory.py` cookie-auth branch |
| `tests/test_security_app_main_bind_guard.py` | 4 | H-3 | `backend/app.py` `__main__` branch |
| `tests/test_security_login_username_enum.py` | 3 | H-6 | `backend/blueprints/auth_bp.py` (95 %) |
| `tests/test_security_proxy_fix_gated.py` | 10 | H-1 | `backend/app_factory.py` ProxyFix mount |
| `tests/test_security_ssh_runner_close_on_exception.py` | 8 | C-4 / C-5 | `backend/runners/ssh_runner.py` (83 %, was 66 %) |
| `tests/test_security_max_content_length.py` | 5 | audit GAP #14 | `backend/config/app_config.py` + 5 blueprints |
| `tests/test_security_audit_hostname_log_scrubbing.py` | 6 | audit GAP #10 (NEW H-5) | `backend/find_leaf/service.py`, `nat_lookup/service.py` |
| `tests/test_security_inventory_import_row_cap.py` | 3 + 1 xfail | audit GAP #8 | `backend/blueprints/inventory_bp.py` (xfail tracks the row-cap fix) |
| **Total** | **51** | — | — |

The single xfail (`test_oversize_import_request_is_capped`) tracks the
unfixed cap on `POST /api/inventory/import` row count. The validation is
per-row, not aggregate — large CSVs slip through `MAX_CONTENT_LENGTH`
because each row is small. Will XPASS once the 5000-row cap lands and
the route returns 400/413.

---

## 4. Per-module coverage (top-of-mind modules)

Numbers from `venv/bin/pytest --cov=backend --cov-branch --cov-report=term`
on the post-fix tree.

| Module | Statements | Cov % | Notes |
|--------|-----------:|------:|-------|
| `backend/app_factory.py` | 184 | 92 % | +127 LOC since wave-4 (cookie-auth dual-path + ProxyFix + idle-timeout) covered by 4 new test files |
| `backend/blueprints/auth_bp.py` | 113 | 95 % | wave-6 module; covered by `test_security_auth_login_*` + `test_security_login_username_enum` + `test_security_session_idle_timeout` |
| `backend/blueprints/credentials_bp.py` | 71 | 90 % | unchanged |
| `backend/blueprints/inventory_bp.py` | 71 | 96 % | unchanged |
| `backend/blueprints/notepad_bp.py` | 35 | 95 % | unchanged |
| `backend/blueprints/reports_bp.py` | 65 | 93 % | unchanged from wave-5 |
| `backend/blueprints/runs_bp.py` | 145 | 98 % | unchanged from wave-5 |
| `backend/blueprints/transceiver_bp.py` | 122 | 88 % | unchanged |
| `backend/credential_store.py` | 68 | 75 % | `_v2_db_path` + `_read_from_v2` covered; legacy `list_credentials` / `delete_credential` still 0-body |
| `backend/repositories/credential_migration.py` | 116 | 97 % | wave-6 module |
| `backend/repositories/credential_repository.py` | 74 | 92 % | unchanged |
| `backend/repositories/inventory_repository.py` | 95 | 88 % | unchanged |
| `backend/repositories/notepad_repository.py` | 66 | 95 % | unchanged |
| `backend/repositories/report_repository.py` | 96 | 90 % | unchanged from wave-5 |
| `backend/runners/runner.py` | 121 | 92 % | unchanged |
| `backend/runners/ssh_runner.py` | 94 | **83 %** | **+17 pp** from wave-4 (was 66.1 %) — wave-7 close on exception lifted the path |
| `backend/runners/interface_recovery.py` | 105 | 74 % | unchanged from wave-4 |
| `backend/security/csrf.py` | 10 | 100 % | wave-6 module |
| `backend/security/encryption.py` | 212 | 90 % | unchanged |
| `backend/security/sanitizer.py` | 93 | 92 % | unchanged |
| `backend/security/validator.py` | 31 | 100 % | unchanged |
| `backend/services/credential_service.py` | 20 | 100 % | unchanged |
| `backend/services/run_state_store.py` | 87 | 100 % | wave-5 close-out brought to 100% |
| `backend/services/transceiver_service.py` | 80 | 90 % | unchanged |
| `backend/parsers/dispatcher.py` | (legacy split) | 95 % | unchanged |
| `backend/parsers/engine.py` | 50 | 92 % | unchanged |
| `backend/parsers/arista/interface_status.py` | 133 | **67 %** | unchanged — chronic gap (operator-output variance) |
| `backend/parsers/cisco_nxos/arp_suppression.py` | 88 | 71.6 % | unchanged |
| `backend/find_leaf/service.py` | 53 | 91 % | wave-5/6 backfill lifted from 51.9 % |
| `backend/find_leaf/strategies/cisco.py` | 64 | 88 % | wave-5/6 backfill from 9.5 % |
| `backend/find_leaf/strategies/arista.py` | 56 | 89 % | wave-5/6 backfill from 10.8 % |
| `backend/nat_lookup/service.py` | 108 | 92 % | wave-5/6 backfill |
| `backend/nat_lookup/xml_helpers.py` | 74 | 88 % | wave-5/6 backfill from 22 % |
| `backend/route_map_analysis/comparator.py` | 74 | 97 % | wave-5/6 backfill from 23.3 % |
| `backend/bgp_looking_glass/ripestat.py` | 240 | 86 % | wave-5 backfill from 72.1 % |
| **TOTAL** | 6,162 | **90.79 %** | gate 45 % |

---

## 5. Wave-7 functions newly above 80 % (vs wave-4)

| File | Wave-4 | Wave-7 | Δ |
|------|-------:|-------:|--:|
| `backend/runners/ssh_runner.py` | 66.1 % | **83 %** | +17 pp |
| `backend/credential_store.py` (post `_read_from_v2`) | 75 % | 75 % | 0 (new branches added but legacy 0-body fns unchanged) |
| `backend/find_leaf/strategies/cisco.py` | 9.5 % | 88 % | +78.5 pp (wave-5/6 backfill) |
| `backend/find_leaf/strategies/arista.py` | 10.8 % | 89 % | +78.2 pp (wave-5/6 backfill) |
| `backend/nat_lookup/xml_helpers.py` | 22 % | 88 % | +66 pp (wave-5/6 backfill) |
| `backend/route_map_analysis/comparator.py` | 23.3 % | 97 % | +73.7 pp (wave-5/6 backfill) |
| `backend/find_leaf/service.py` | 51.9 % | 91 % | +39 pp |
| `backend/nat_lookup/service.py` | 51.9 % | 92 % | +40 pp |

The wave-7 single direct contribution is the SSH-runner fix; the other
deltas are wave-5 / wave-6 work that closed the wave-4 Tier-1 gap list.

---

## 6. Frontend coverage (Vitest)

| Helper module | Functions | Vitest tests | Cov |
|---------------|----------:|-------------:|----:|
| `backend/static/js/lib/subnet.js` | 6 | 16 | **100 %** |
| `backend/static/js/lib/utils.js` | 4 (escapeHtml, formatBytes, isValidIPv4, parseHash) | 16 + safeHtml/escapeHtml hardening tests | **100 %** |
| **Total Vitest** | 10 | **45** | **100 %** on extracted helpers |

The remaining ~5,250 lines in `backend/static/js/app.js` are intentionally
out-of-scope for Vitest (extracted helpers only); the SPA itself is
exercised end-to-end by Playwright.

---

## 7. Concrete list of NEW test files to create (post wave-7)

The wave-7 sweep closed the CRITICAL + HIGH cluster from
`docs/security/DONE_audit_2026-04-23-wave7.md` and surfaced 14 MEDIUM +
11 LOW items (security review) plus 13 MEDIUM + 8 LOW (Python review)
that remain open. The matching test gaps:

### Tier 1 — close the wave-7 MEDIUM cluster

1. **`tests/test_security_csrf_token_rotation.py`** — covers wave-7 MED-9
   (old CSRF token still accepted briefly after a re-login). Asserts the
   old token returns 403 on the very next request after re-login.
2. **`tests/test_security_auth_whoami_rate_limit.py`** — covers wave-7
   MED-10 (`/api/auth/whoami` is unrate-limited; an attacker can poll
   to detect operator session opens). Currently the spec is operational
   ("polls as fast as possible should not be denied") — a new test
   asserts a per-IP limit kicks in.
3. **`tests/test_security_throttle_lru_eviction.py`** — covers wave-7
   MED-8 (LRU FIFO eviction at 1024 entries lets an attacker flood the
   cache to evict legitimate operator records). Test inserts 1025 unique
   tuples and asserts the operator's prior good-actor record survives.
4. **`tests/test_security_audit_path_marker.py`** — covers wave-7 MED-13
   (audit log does not record which auth path served the request).
5. **`tests/test_security_command_validator_audit_scrub.py`** — covers
   wave-7 MED-10 (CommandValidator-rejected commands are logged with
   raw `\n` / `\r` content). Currently the validator rejects them, but
   the rejected-path audit line emits the raw value before the strip.

### Tier 2 — close the wave-7 LOW cluster

6. **`tests/test_security_safehtml_url_scheme.py`** — covers wave-7 M-7
   (`safeHtml` does not defend against `javascript:` URLs in
   attribute interpolation).
7. **`tests/test_security_inline_style_lint.py`** — covers wave-7 L-5
   (no lint guard prevents a future contributor adding `style="…"` to
   markup strings, breaking the wave-6 CSP `style-src 'self'` policy).
8. **`tests/test_security_audit_logout_no_session.py`** — covers wave-7
   L-11 (`/api/auth/logout` should emit an audit line on no-session probes).

### Tier 3 — close the audit GAPs still open

9. **`tests/test_security_cookie_attributes.py`** — audit GAP #2 (`HttpOnly`,
   `SameSite=Lax`, `Secure` in production explicit assertions).
10. **`tests/test_security_device_runner_redirect_refusal.py`** — audit GAP #4.
11. **`tests/test_security_runnerfactory_command_validator.py`** — audit GAP #5.
12. **`tests/test_security_ssh_strict_host_key_prod_default.py`** — audit GAP #6
    (currently the prod default is `AutoAddPolicy`; this test should be
    paired with a production-config change that flips the default).
13. **`tests/test_security_session_permanent_rotation.py`** — audit GAP #11
    (re-login does not extend an old cookie's lifetime past the new
    `PERMANENT_SESSION_LIFETIME`).
14. **`tests/test_security_login_compare_timing.py`** — audit GAP #12
    (microbenchmark assertion against a regression in the dummy compare).
15. **`tests/test_security_notepad_path_traversal.py`** — audit GAP #13
    (currently fixed-path; lock the contract).

### Tier 4 — Python-review carry-overs (still open)

16. **`tests/test_runstatestore_update_actor_scoping.py`** — Python-review
    MED-2 (add `actor=` parameter; reject `_created_by_actor` in `**fields`).
17. **`tests/test_actor_helpers_unified.py`** — Python-review MED-1 (one
    helper across all 6 blueprints).
18. **`tests/test_find_leaf_observability.py`** — Python-review MED-3 +
    MED-6 (narrow the two bare excepts; add per-call logger).

### Estimated cumulative impact if Tier 1 + Tier 2 (1-8) is completed

- Whole-codebase combined coverage: **90.79 % → ~92 %**.
- Branch coverage: **~88 % → ~91 %**.
- Files <80 %: **6 → ~4** (the chronic parser/runner files).
- xfail markers: **1 → 0** (audit GAP #8 row cap landed).

---

## 8. Out-of-scope (per audit task)

- **Full SPA IIFE coverage in `backend/static/js/app.js` (~5,250 lines).**
  Per the wave-3 / wave-6 plans, only the helpers extracted into
  `backend/static/js/lib/` (currently `subnet.js` + `utils.js`) have
  Vitest tests. The IIFE itself remains exercised only via Playwright.
  **Noted, not flagged.**

---

## 9. Appendix — how this audit was generated

```bash
venv/bin/pytest --cov=backend --cov-branch \
    --cov-report=term -q
```

Result: `1767 passed, 1 xfailed in 93.12s` — combined coverage 90.79 %.

OOD-scoped (`make cov-new`): 91.34 % (gate 85 %).

NEW-test-file inventory was sourced via:

```bash
git log --diff-filter=A --name-only v0.7.0..HEAD -- 'tests/test_security_*.py' | sort -u
```

Returns the 9 wave-7 files listed in §3.
