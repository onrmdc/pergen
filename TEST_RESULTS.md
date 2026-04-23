# Test results — Pergen `refactor/ood-tdd`

Generated for the refactor branch after **phases 1–12 decomposition** +
**audit batches 1–4 remediation** + **UI/CSP/boot-path alignment** +
**audit-wave-1** + **parse_output refactor (8 phases)** + **audit-wave-2**
+ **wave-3 god-module split** + **wave-4 actor-scoping followups** +
**wave-5 close-out** + **wave-6 reclassified-items shipped** +
**wave-7 audit followup 2026-04-23** (CRITICAL+HIGH cluster fixed,
12 brittle Playwright specs stabilised).

All numbers are reproducible by running `python -m pytest -q`,
`npx playwright test`, `npm run test:frontend`, and the `coverage`
commands shown below.

---

## 1. Headline numbers (current)

| Metric | Value |
|--------|-------|
| Tests passing (pytest) | **1767 / 1768** + **1 xfailed** (wave-7: +50 new tests across 9 files; xfail tracks the open audit GAP #8 inventory-import row cap) |
| Total test functions | **1768** (1767 pass + 1 strict xfail) |
| Test files (Python) | **111** (was 102 at wave-6 close — +9 wave-7 security regression files) |
| Time to run full pytest suite | ~93 s on an M-series Mac |
| End-to-end tests (Playwright) | **100 / 100 passing** in **43 spec files** (was 88 / 12 failing at wave-6 close; **wave-7 fixed all 12** with test-only changes — no SPA / backend modifications) |
| Frontend unit tests (Vitest) | **45 / 45** in <1 s (utils.js helpers + safeHtml + escapeHtml hardening) |
| Lint (`ruff check`) on new code | **0 errors** |
| Coverage — parser surface (`backend.parsers/*` + shim) | **87 %** |
| Coverage — wave-3 4 new packages combined | **92 %** |
| Coverage — wave-6 new modules (auth_bp, csrf, credential_migration) | **97 %** combined |
| Coverage — frontend extracted helpers (subnet.js, utils.js) | **100 %** |
| Coverage — whole-project | **90.79 %** (gate 45 %; was 90.51 % at wave-6 close) |
| Coverage — OOD-scoped (`make cov-new`) | **91.34 %** (gate 85 %) |
| Coverage — branch | **~88 %** (was 86.4 % at wave-6 close) |
| Audit findings remediated | **38 / 38** (batches 1–4) + **7 frontend XSS** (wave-1) + **24 wave-3** + **6 wave-4** + **5 wave-6 reclassified items** + **7 wave-7** (1 CRITICAL + 6 HIGH, plus 2 Python-review CRITICAL ssh_runner) |
| Audit findings tracked via `xfail` | **1** (audit GAP #8 — inventory import row cap) |
| God modules remaining | **0** |
| CSP `'unsafe-inline'` | **REMOVED** from `style-src` (wave-6 Phase D) |
| Inline `style="..."` attributes in SPA | **0** |
| Cookie auth + CSRF | **shipped** (wave-6 Phase F, Council Option B) — opt-in via `PERGEN_AUTH_COOKIE_ENABLED=1` |
| Session lifetime | **bounded** (wave-7 H-2) — default 8h via `PERGEN_SESSION_LIFETIME_HOURS`; idle-timeout via `PERGEN_SESSION_IDLE_HOURS` (default = lifetime); was 31-day Flask default |
| Reverse-proxy support | **opt-in** (wave-7 H-1) — `PERGEN_TRUST_PROXY=1` mounts `werkzeug.middleware.proxy_fix.ProxyFix` so login throttle keys on the real client IP |
| Credential read v2 fall-through | **shipped** (wave-7 C-1 / H-4) — `credential_store.get_credential()` falls through to `credentials_v2.db` when the legacy DB has no row; closes the fresh-install device-exec break |
| Credential migration tooling | **shipped** (wave-6 Phase E) — `python scripts/migrate_credentials_v1_to_v2.py [--dry-run]` |
| `docs/refactor/` plans remaining | **0** (all `DONE_*`-prefixed) |
| `backend/parse_output.py` size | **151 lines** (was 1,552 — 90 % reduction; back-compat shim over `backend/parsers/*`) |
| `backend/app.py` size | **87 lines** (was 1,577 — 95 % reduction) |
| Routes registered through factory | **55** across **12 blueprints** |

### Test breakdown by category

| Category | Files | Tests |
|----------|-------|-------|
| Golden / baseline (Phase-pre) | 4 | 78 |
| Phase-13 security (pre-decomp) | 2 | 105 (33 phase-13 + 72 OWASP) |
| Phase 2 utils | 1 | 30 |
| Phase 3 inventory writes | 1 | 19 |
| Phase 4 commands_bp | 1 | 6 |
| Phase 5 network_ops_bp | 1 | 7 |
| Phase 6 credentials_bp | 1 | 10 |
| Phase 7 bgp_bp | 1 | 15 |
| Phase 8 network_lookup_bp | 1 | 10 |
| Phase 9 transceiver_bp + service | 1 | 11 |
| Phase 10 device_commands_bp | 1 | 13 |
| Phase 11 runs_bp + reports_bp | 1 | 20 |
| Audit findings batch 1+2 | 1 | 25 |
| Audit findings batch 3 | 1 | 14 |
| Audit findings batch 4 (security sweep) | 1 | 24 |
| Runner dispatch coverage | 1 | 13 |
| Coverage push (NEW code) | 1 | 71 |
| Legacy coverage (bgp_lg, route_map, find_leaf, nat_lookup, parse_output, runner, loader) | 5 | 152 |
| Pre-existing unit/integration | 9 | 216 |
| **Audit-wave-1** lint guards / xfail trackers | 11 | 12 (post-flip pre-wave-6) |
| **Audit-wave-2 — vendor parser unit tests** (8 Arista + 8 Cisco NX-OS) | 16 | 196 |
| **Audit-wave-2 — security tests** | 12 | 59 (post-flip pre-wave-5) |
| **Audit-wave-2 — parser shim contract** | 1 | 83 |
| **Audit-wave-2 — parsers/common + dispatcher unit tests** | 9 | 256 |
| **Wave-3 / wave-4 / wave-5 closures** (cumulative) | ~30 | ~250 |
| **Wave-6 reclassified-items tests** (XSS lint, CSP HTML/JSON/all-types, credential-migration, SPA fetch wrapper, CSRF unit + required, auth login flow + actor pinning + session fixation + throttling, find-leaf cancel) | 13 | ~85 |
| **Wave-7 audit followup** — see §1.1 below | **9** | **51** |
| **Vitest frontend unit tests** (escapeHtml, formatBytes, isValidIPv4, parseHash, subnet helpers, safeHtml/escapeHtml hardening) | 2 | **45** |
| **Total (Python)** | **111** | **1767 + 1 xfail** |

### 1.1 Wave-7 NEW test files (2026-04-23)

Nine new security-regression files landed in this session, pinning the
CRITICAL + HIGH fixes documented in
`docs/security/DONE_audit_2026-04-23-wave7.md` §4 and
`docs/code-review/DONE_python_review_2026-04-23-wave7.md` §4:

| File | Tests | Pinning | Audit ID |
|------|------:|---------|----------|
| `tests/test_security_credential_v2_fallthrough.py` | 6 | `_v2_db_path()` + `_read_from_v2()` bridge in `credential_store.py` | C-1 / H-4 |
| `tests/test_security_session_idle_timeout.py` | 5 | `PERMANENT_SESSION_LIFETIME` + `PERGEN_SESSION_IDLE_HOURS` enforcement in `app_factory._enforce_api_token` | H-2 |
| `tests/test_security_app_main_bind_guard.py` | 4 | `python -m backend.app` refuses non-loopback bind without `PERGEN_DEV_ALLOW_PUBLIC_BIND=1` | H-3 |
| `tests/test_security_login_username_enum.py` | 3 | `auth.login.fail` audit line records `actor=<unknown>` for unknown usernames | H-6 |
| `tests/test_security_proxy_fix_gated.py` | 10 | `werkzeug.middleware.proxy_fix.ProxyFix` mounted only when `PERGEN_TRUST_PROXY=1` | H-1 |
| `tests/test_security_ssh_runner_close_on_exception.py` | 8 | `try/finally: client.close()` + `_classify_ssh_error` bucketing | Python-review C-4 / C-5 |
| `tests/test_security_max_content_length.py` | 5 | Flask refuses request bodies > `MAX_CONTENT_LENGTH` (10 MiB) on 5 routes | audit GAP #14 |
| `tests/test_security_audit_hostname_log_scrubbing.py` | 6 | `_safe_audit_str(...)` strips control chars in find-leaf / nat-lookup audit emission | audit GAP #10 (NEW H-5) |
| `tests/test_security_inventory_import_row_cap.py` | 3 + 1 xfail | row-count cap on `POST /api/inventory/import` (xfail tracks the unfixed cap) | audit GAP #8 |
| **Total** | **51** | — | — |

### Coverage by layer (new OOD code)

Run: `make cov-new`

| Module | Coverage |
|--------|----------|
| `backend/blueprints/__init__.py` | 100 % |
| `backend/blueprints/commands_bp.py` | 100 % |
| `backend/blueprints/health_bp.py` | 100 % |
| `backend/blueprints/inventory_bp.py` | 96 % |
| `backend/blueprints/network_ops_bp.py` | 94 % |
| `backend/blueprints/notepad_bp.py` | 95 % |
| `backend/blueprints/network_lookup_bp.py` | 92 % |
| `backend/blueprints/runs_bp.py` | 98 % |
| `backend/blueprints/device_commands_bp.py` | 99 % |
| `backend/blueprints/credentials_bp.py` | 90 % |
| `backend/blueprints/reports_bp.py` | 93 % |
| `backend/blueprints/bgp_bp.py` | 95 % |
| `backend/blueprints/transceiver_bp.py` | 88 % |
| `backend/blueprints/auth_bp.py` (wave-6) | 95 % |
| `backend/services/credential_service.py` | 100 % |
| `backend/services/device_service.py` | 100 % |
| `backend/services/notepad_service.py` | 100 % |
| `backend/services/report_service.py` | 100 % |
| `backend/services/inventory_service.py` | 92 % |
| `backend/services/run_state_store.py` | 100 % |
| `backend/services/transceiver_service.py` | 90 % |
| `backend/security/csrf.py` (wave-6) | 100 % |
| `backend/repositories/credential_migration.py` (wave-6) | 97 % |
| `backend/runners/ssh_runner.py` (wave-7 fix lifted) | **83 %** (was 66 %) |
| `backend/utils/transceiver_display.py` | 94 % |
| `backend/utils/bgp_helpers.py` | 100 % |
| `backend/utils/interface_status.py` | 97 % |
| `backend/utils/ping.py` | 87 % (Windows branch only) |
| **TOTAL (`make cov-new`)** | **91.34 %** (gate 85) |

### Coverage by layer (whole-project)

Run: `python -m pytest --cov=backend --cov-branch --cov-report=term -q`

| Module group | Coverage |
|--------------|----------|
| New OOD layer (blueprints + services + utils + factory + auth_bp + csrf + credential_migration) | 91.34 % |
| Repositories (credential / inventory / notepad / report) | 88–97 % |
| Security (sanitizer / validator / encryption / csrf) | 90–100 % |
| Runners (arista_eapi, cisco_nxapi, ssh_runner, interface_recovery) | 74–100 % |
| Parsers (engine + parse_output + dispatcher + 31-module package) | 67–100 % |
| Helpers (bgp_looking_glass, route_map_analysis, find_leaf, nat_lookup) | 86–97 % (was 36–74 % pre-wave-3) |
| Other (logging, config, request_logging) | 82–100 % |
| **WHOLE-PROJECT** | **90.79 %** (line); **~88 %** (branch); was 74.94 % pre-wave-2 |

The 6 sub-80 % files post wave-7 are all chronic operator-output-variance
gaps in the parser surface plus the legacy `credential_store.py` shim
(75 %) — see `docs/test-coverage/DONE_coverage_audit_2026-04-23-wave7.md` §2.

### Audit-batch security regression tests (76 + 51 = 127 total)

* `tests/test_security_audit_findings.py` — 25 tests (batches 1+2)
* `tests/test_security_audit_batch3.py` — 14 tests (batch 3)
* `tests/test_security_audit_batch4.py` — 24 tests (batch 4)
* `tests/test_runner_dispatch_coverage.py` — 13 tests
* **Wave-7 (2026-04-23):** 9 new files / 51 tests — see §1.1.

Each test names its audit finding ID (C1, H6, M11, W4-H-01, W7-C-1, etc.)
so the audit report and the test suite are cross-referenceable.

---

## 2. Per-test-file pass matrix

| File | Tests | Status | Phase / Wave |
|------|-------|--------|--------------|
| `tests/golden/test_parsers_golden.py` | 22 | ✅ | 1 |
| `tests/golden/test_runners_baseline.py` | 17 | ✅ | 1 |
| `tests/golden/test_routes_baseline.py` | 31 | ✅ | 1 |
| `tests/golden/test_inventory_baseline.py` | 8 | ✅ | 1 |
| `tests/test_config_classes.py` | 8 | ✅ | 2 |
| `tests/test_logging_config.py` | 8 | ✅ | 2 |
| `tests/test_request_logging.py` | 5 | ✅ | 2 |
| `tests/test_input_sanitizer.py` | 65 | ✅ | 3 |
| `tests/test_command_validator.py` | 25 | ✅ | 3 |
| `tests/test_encryption_service.py` | 12 | ✅ | 3 |
| `tests/test_app_factory.py` | 8 | ✅ | 4 |
| `tests/test_credential_repository.py` | 12 | ✅ | 5 |
| `tests/test_inventory_repository.py` | 11 | ✅ | 5 |
| `tests/test_notepad_repository.py` | 10 | ✅ | 5 |
| `tests/test_report_repository.py` | 9  | ✅ | 5 |
| `tests/test_runner_classes.py` | 13 | ✅ | 6 |
| `tests/test_parser_engine.py` | 10 | ✅ | 7 |
| `tests/test_services.py` | 18 | ✅ | 8 |
| `tests/test_phase9_blueprints.py` | 9 | ✅ | 9 |
| `tests/test_security_owasp.py` | 72 | ✅ | 11 |
| `tests/test_security_phase13.py` | 33 | ✅ | 13 |
| `tests/test_utils_phase2.py` | 30 | ✅ | decomp-2 |
| `tests/test_inventory_writes_phase3.py` | 19 | ✅ | decomp-3 |
| `tests/test_commands_bp_phase4.py` | 6 | ✅ | decomp-4 |
| `tests/test_network_ops_bp_phase5.py` | 7 | ✅ | decomp-5 |
| `tests/test_credentials_bp_phase6.py` | 10 | ✅ | decomp-6 |
| `tests/test_bgp_bp_phase7.py` | 15 | ✅ | decomp-7 |
| `tests/test_network_lookup_bp_phase8.py` | 10 | ✅ | decomp-8 |
| `tests/test_transceiver_bp_phase9.py` | 11 | ✅ | decomp-9 |
| `tests/test_device_commands_bp_phase10.py` | 13 | ✅ | decomp-10 |
| `tests/test_runs_reports_bp_phase11.py` | 20 | ✅ | decomp-11 |
| `tests/test_security_audit_findings.py` | 25 | ✅ | audit-batch-1+2 |
| `tests/test_security_audit_batch3.py` | 14 | ✅ | audit-batch-3 |
| `tests/test_security_audit_batch4.py` | 24 | ✅ | audit-batch-4 |
| `tests/test_runner_dispatch_coverage.py` | 13 | ✅ | audit-batch-4 |
| `tests/test_coverage_push.py` | 71 | ✅ | coverage-push |
| `tests/test_legacy_coverage_*` (5 files) | 152 | ✅ | legacy-coverage |
| **Wave-1..wave-6 security tests** (~30 files) | ~250 | ✅ | wave-1..wave-6 |
| **Wave-7 (2026-04-23) security tests** (9 files — see §1.1) | **50 + 1 xfail** | ✅ / ⚠ xfail | wave-7 |
| **Total** | **1768** (1767 pass + 1 xfail) | **✅** | — |

Re-run a single file with:

```bash
venv/bin/python -m pytest tests/test_security_credential_v2_fallthrough.py -q
```

Re-run the whole suite with:

```bash
make test           # quiet
make cov            # global coverage report (gate 45 %, currently 90.79 %)
make cov-new        # OOD-layer coverage report (gate 85 %, currently 91.34 %)
```

---

## 3. Coverage — new OOD layer

```
$ make cov-new
TOTAL                                            ...    91.34%
```

See §1 "Coverage by layer (new OOD code)" for the per-module breakdown.
The wave-6 modules (`auth_bp` 95 %, `csrf` 100 %, `credential_migration`
97 %) and the wave-7 `ssh_runner` lift (66 % → 83 %) are the most
recent additions.

---

## 4. Coverage — global

```
TOTAL  6162  430  2376  296  90.79%  (line) / ~88% (branch)
```

The remaining gap is concentrated in:

| Module | Coverage | Why |
|--------|----------|-----|
| `backend/parsers/arista/interface_status.py` | 67 % | operator-output shape variance; chronic gap |
| `backend/parsers/cisco_nxos/arp_suppression.py` | 71.6 % | same |
| `backend/runners/interface_recovery.py` | 74 % | interactive PTY config-push paths |
| `backend/credential_store.py` | 75 % | legacy module; `_v2_db_path` + `_read_from_v2` (wave-7) covered, but legacy `list_credentials` / `delete_credential` 0-body |
| `backend/bgp_looking_glass/peeringdb.py` | 76 % | unchanged from wave-4 |
| `backend/parsers/cisco_nxos/isis_brief.py` | 76.8 % | minor |

These will rise when (a) the operator-fleet output corpus expands, and
(b) the legacy `credential_store` shim is deleted (Phase 6 of the
migration plan in `docs/refactor/DONE_credential_store_migration.md`).

---

## 5. Security evaluation (OWASP Top-10 + business-logic + wave-7 sweep)

`tests/test_security_owasp.py` ships **72 named tests** grouped by
OWASP category. Every category has at least one regression test.
The wave-7 cluster adds **51 more security regression tests** across
9 files — see §1.1.

| Category | Test count | Status |
|----------|------------|--------|
| **A01** Broken Access Control | 1 (OWASP) + ~30 (audit batches + actor-scoping waves) | ✅ |
| **A02 / A08** Cryptographic Failures + Software/Data Integrity | 4 (OWASP) + the new `csrf` module (100 % covered) + wave-7 credential v2 fall-through | ✅ |
| **A03** Injection | 47 (OWASP) + audit batches 3/4 + wave-7 audit-log scrubbing | ✅ |
| **A04** Insecure Design | 3 (OWASP) + wave-7 H-3 (`__main__` bind guard) | ✅ |
| **A05** Security Misconfiguration | 1 (OWASP) + wave-7 C-1 (credential v2 fall-through) | ✅ |
| **A07** Identification & Auth Failures | 1 (OWASP) + wave-6 cookie auth (auth_bp 95 %) + wave-7 H-2 (session lifetime) + wave-7 H-6 (username enum) | ✅ |
| **A09** Logging & Monitoring Failures | 1 (OWASP) + wave-7 H-5 (audit hostname scrub) + audit_logger_coverage closures | ✅ |
| **A10 / business-logic** | 5 (OWASP) | ✅ |
| Cross-cutting helpers + parametrised cases | 9 | ✅ |
| **Wave-7 NEW security regressions** | **51** (9 files; see §1.1) | ✅ + 1 xfail |
| **Total** | **123** named + the audit-batch / wave-N closures | ✅ |

### Notes on what was *not* possible to weaken

* `EncryptionService` refuses to instantiate with an empty secret.
* `EncryptionService` refuses to instantiate at all when neither the
  `cryptography` package nor the in-tree AES-128-CBC + HMAC-SHA256
  fallback can produce a valid Fernet-shape key.
* `ProductionConfig` refuses to start with the placeholder secret.
* `CommandValidator` is the only gate to a runner — every non-`show /
  dir` command is rejected before transport.
* Every blueprint route logs a request id, both inbound and outbound.
* **Wave-7 additions:** session cookies are bounded at
  `PERGEN_SESSION_LIFETIME_HOURS` (default 8h) AND idle-timeouted via
  `PERGEN_SESSION_IDLE_HOURS`. `python -m backend.app` refuses any
  non-loopback bind without `PERGEN_DEV_ALLOW_PUBLIC_BIND=1`.
  `credential_store.get_credential()` falls through to
  `credentials_v2.db` when the legacy DB has no row, so a fresh-install
  operator who only used the new HTTP CRUD has working device-exec
  routes. SSH runner closes its client on every exception path.

---

## 6. Reproducibility

```bash
git clone https://github.com/asceylan/pergen.git
cd pergen
git checkout refactor/ood-tdd
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements-dev.txt
make test         # 1767 passed + 1 xfailed (~93 s)
make cov-new      # 91.34 % on the new layer (gate 85)
make cov          # 90.79 % global (gate 45)
make lint         # ruff clean on new files
npm run test:frontend   # 45 Vitest
make e2e          # 100 / 100 Playwright
```

If any number above changes, `patch_notes.md` is updated in the same
commit.

---

## 7. Phase-13 security hardening — regression matrix

`tests/test_security_phase13.py` ships **33 named tests**. Every
control listed in the wave-2 matrix is still in effect; the wave-7
audit re-confirmed each via a representative spot-check.

| Audit ID | Severity | Fix | Tests |
|----------|----------|-----|-------|
| C-2 | CRITICAL | `/api/arista/run-cmds` routes every cmd through `CommandValidator` | 3 |
| C-3 | CRITICAL | Palo Alto API key moved to `X-PAN-KEY` header | 1 |
| C-4 | CRITICAL | `/api/custom-command` uses `CommandValidator` | 3 |
| C-5 | CRITICAL | `/api/ping` validates IPs + caps device list at 64 | 3 |
| H-1 | HIGH     | `NotepadRepository.update` is atomic | 1 |
| H-2 | HIGH     | NAT XML uses `defusedxml` | 1 |
| H-5 | HIGH     | Notepad write returns generic 500 envelope | 1 |
| H-6 | HIGH     | Defence-in-depth headers on every response | 4 |
| H-8 | HIGH     | SSH commands from `commands.yaml` go through `CommandValidator` | 1 |
| M-4 | MEDIUM   | `CommandValidator` NFKC-normalises input | 3 |
| M-5 | MEDIUM   | Strips leading whitespace, rejects embedded `\n`/`\r` | 2 |
| M-8 | MEDIUM   | `MAX_CONTENT_LENGTH` set on `BaseConfig`; per-route notepad cap → 413 | 2 (+5 new wave-7 tests) |
| py-HIGH | HIGH  | `encryption._key_expand_128` raises `ValueError` (survives `python -O`) | 1 |
| py-HIGH | HIGH  | `CredentialRepository` works with `:memory:` SQLite | 1 |
| py-HIGH | HIGH  | `ReportRepository._safe_id` strips path separators | 2 |
| py-MED  | MED   | `_ip_sort_key` returns 4-tuple for malformed IPs | 1 |
| py-MED  | MED   | Blueprint `_svc()` helpers raise `RuntimeError` instead of `KeyError` | 2 |
| **Total** | — | — | **33** |

---

## 8. Playwright E2E (post wave-7 stability fixes)

The Playwright suite drives the real SPA against a real Flask server
(no mocked backend). `webServer` config in `playwright.config.ts` boots
`./run.sh` and reuses any server already on port 5000.

| Metric | Value |
|--------|-------|
| Spec files | **43** under `tests/e2e/specs/` |
| Tests | **100 / 100 passing** (was 88 / 12 failing at wave-6 close) |
| Wall time | **~10–30 s** on a warm M-series Mac, headless Chromium |
| Browser | Chromium only (`projects: [{ name: "chromium" }]`) |
| Reporters | `list` (stdout) + `html` (`playwright-report/`) + `junit` (`test-results/junit.xml`) |
| Artefacts on failure | screenshot + video + trace on retry |
| Boot path under test | `./run.sh` → `FLASK_APP=backend.app_factory:create_app` |

### 8.1 Wave-7 spec stability fixes (12 specs)

The wave-6 SPA refactor (Phase D inline-style sweep + Phase F cookie
auth) introduced selector / dialog / URL-shape changes that invalidated
12 wave-5 / wave-6 specs. Wave-7 fixed all 12 with **test-only changes**
— no SPA, no backend, no CSS:

| Spec | Root cause | Fix |
|------|------------|-----|
| `security-headers.spec.ts` | HSTS asserted over HTTP | scoped to HTTPS only |
| `flow-subnet-split.spec.ts` | unhandled `confirm()` dialog on mask change | accept dialog before assertion |
| `flow-transceiver-run.spec.ts` | devices only load on role select | walk full `fabric→site→hall→role` cascade |
| `flow-transceiver-clear-counters.spec.ts` | same | same |
| `flow-prepost-run.spec.ts` | missing role select | inserted role-select step |
| `flow-postrun-complete.spec.ts` | placeholder selectors against unwritten DOM | rewritten against real `#runId` + Run Post + success banner |
| `flow-inventory-crud.spec.ts` | Delete clicked row, not checkbox; DELETE URL has query string | switched to checkbox; relaxed URL regex |
| `flow-report-restore.spec.ts` | saved-reports list empty by default | pre-seed `localStorage["pergen_saved_reports"]` |
| `flow-error-paths.spec.ts` | find-leaf input matched hidden bgp page input | scoped to `#page-findleaf input[type=text]` |
| `flow-error-paths-extended.spec.ts` | same selector ambiguity | same scoping fix |
| `flow-xss-defence.spec.ts` | same | same |

Full per-spec table: `docs/test-coverage/DONE_e2e_gap_analysis_2026-04-23-wave7.md` §2.

### 8.2 Spec coverage (essentially unchanged from wave-4 audit)

20 base specs from wave-1 + 15 wave-3 flow specs + 8 wave-5/6 P0 flows +
the wave-6 auth + XSS regression specs = 43 spec files. Coverage matrix:

- **42 / 53** endpoints have at least one spec (UI mock + smoke).
- **34 / 53** endpoints fully UI-tested.
- **13 / 14** SPA hash routes covered (`#help` still uncovered).
- **10 / 10** extracted `lib/` helpers covered by Vitest (100 %).

See `docs/test-coverage/DONE_e2e_gap_analysis_2026-04-23-wave7.md` §3-§5
for the full matrix.

Run with:

```bash
make e2e-install     # one-time
make e2e             # 100 / 100 in ~10–30 s
npx playwright show-report   # open the HTML report
```

---

## 9. Cross-references

- `docs/security/DONE_audit_2026-04-23-wave7.md` — full wave-7 security audit (1 CRITICAL + 6 HIGH fixes + remaining MEDIUM/LOW open list).
- `docs/code-review/DONE_python_review_2026-04-23-wave7.md` — wave-7 Python review (5 CRITICAL fixes + remaining MEDIUM cluster).
- `docs/test-coverage/DONE_coverage_audit_2026-04-23-wave7.md` — coverage breakdown by module + Tier-1 backfill closure.
- `docs/test-coverage/DONE_e2e_gap_analysis_2026-04-23-wave7.md` — Playwright suite stability + per-spec fix list.
- `docs/refactor/DONE_credential_store_migration.md` "Wave-7 update" — v2 fall-through bridge.
- `patch_notes.md` v0.7.1 — full wave-7 changelog entry.
