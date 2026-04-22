# Test results — Pergen `refactor/ood-tdd`

Generated for the refactor branch after **phases 1–12 decomposition** +
**audit batches 1–4 remediation** + **UI/CSP/boot-path alignment** +
**audit-wave-1** + **parse_output refactor (8 phases)** + **audit-wave-2**
(`v0.3.0` — security audit + Python review + coverage audit + E2E gap
analysis + 16 vendor parser unit tests + 11 new security tests + 4 new
Playwright specs + Vitest scaffold).
All numbers are reproducible by running `python -m pytest -q`,
`npx playwright test`, `npm run test:frontend`, and the `coverage`
commands shown below.

---

## 1. Headline numbers (current)

| Metric | Value |
|--------|-------|
| Tests passing (pytest) | **1619 / 1619** + **4 xfailed** (3 wave-4 audit followups deferred) |
| Total test functions | **1623** (1619 pass + 4 xfail) |
| Test files (Python) | **88** (was 74 at wave-3 close — +7 wave-4 security tests + +10 Tier-1 unit-test files in 4 new test dirs) |
| Time to run full pytest suite | ~70 s on an M-series Mac |
| End-to-end tests (Playwright) | **90** in **41 spec files** (+3 P0 wave-4 specs; 1 wave-3 spec renamed for clarity) |
| Frontend unit tests (Vitest) | **37 / 37** in <1 s (utils.js + subnet.js helpers) |
| Lint (`ruff check`) on new code | **0 errors** |
| Coverage — parser surface (`backend.parsers/*` + shim) | **87 %** (wave-2 baseline) |
| Coverage — wave-3 4 new packages combined | **92 %** (was 57 % at wave-3 close — +35 pp from Tier-1 tests) |
| Coverage — whole-project | **90.42 %** (was 84.17 % at wave-4 start; +6.25 pp) |
| Audit findings remediated | **38 / 38** (batches 1–4) + **7 frontend XSS** (audit-wave-1) + **24 wave-3 closures** + **3 wave-4 closures** (W4-H-01, W4-M-04, W4-M-05) |
| Audit findings tracked via `xfail` | **4** total (3 wave-4 deferred MED + 1 paired assertion) |
| God modules remaining | **0** (find_leaf, nat_lookup, bgp_looking_glass, route_map_analysis all split into packages in wave-3 Phase 8) |
| `backend/parse_output.py` size | **151 lines** (was 1,552 — 90 % reduction; now a back-compat shim over `backend/parsers/*` package, 31 modules) |
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
| **Audit-wave-1** (XSS lint guards, vendor integrity, CSP/JSON, BGP host pin, token-gate parsing, /api/diff DoS, audit-log coverage, /api/v2/health, router-devices projection, legacy credstore deprecation, token-gate immutability) | 11 | 12 + 9 xfail = 21 |
| **Audit-wave-2 — vendor parser unit tests** (8 Arista + 8 Cisco NX-OS, lifted parser coverage from 67 → 87 %) | 16 | 196 |
| **Audit-wave-2 — new security tests** (CSRF, XSS dropdowns, XSS findleaf/NAT, diff line DoS, dev-boot open API, run-result IDOR, report restore method, report empty-id, inventory enum, ssh leak, RIPEStat redirect, parsers no-IO) | 12 | 44 + 15 xfail = 59 |
| **Audit-wave-2 — parser shim contract** | 1 | 83 |
| **Audit-wave-2 — parsers/common + dispatcher unit tests** | 9 | 256 |
| **Vitest frontend unit tests** (escapeHtml, formatBytes, isValidIPv4, parseHash) | 1 | 16 |
| **Total** | **74** | **1392** (1368 pass + 24 xfail) — pytest only; +16 Vitest |

### Coverage by layer (new OOD code)

Run: `python -m coverage run --source=backend.blueprints,backend.services,backend.utils -m pytest -q && python -m coverage report`

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
| `backend/services/credential_service.py` | 100 % |
| `backend/services/device_service.py` | 100 % |
| `backend/services/notepad_service.py` | 100 % |
| `backend/services/report_service.py` | 100 % |
| `backend/services/inventory_service.py` | 92 % |
| `backend/services/run_state_store.py` | 100 % |
| `backend/services/transceiver_service.py` | 90 % |
| `backend/utils/transceiver_display.py` | 94 % |
| `backend/utils/bgp_helpers.py` | 92 % |
| `backend/utils/interface_status.py` | 97 % |
| `backend/utils/ping.py` | 87 % (Windows branch only) |
| **TOTAL** | **94 %** |

### Coverage by layer (whole-project)

Run: `python -m coverage run --source=backend -m pytest && python -m coverage report --sort=cover`

| Module group | Coverage |
|--------------|----------|
| New OOD layer (blueprints + services + utils + factory) | 94 % |
| Repositories (credential / inventory / notepad / report) | 88–98 % |
| Security (sanitizer / validator / encryption) | 90–92 % |
| Runners (arista_eapi, cisco_nxapi, ssh_runner, interface_recovery) | 51–86 % |
| Parsers (engine + parse_output) | 53–90 % |
| Helpers (bgp_looking_glass, route_map_analysis, find_leaf, nat_lookup) | 36–74 % |
| Other (logging, config, request_logging) | 82–98 % |
| **WHOLE-PROJECT** | **78.33 %** (line 82.47 %, branch 68.13 %; was 74.94 % pre-wave-2) |

The legacy parsers (`parse_output.py` 53 %, `find_leaf.py` 36 %,
`nat_lookup.py` 42 %, `route_map_analysis.py` 51 %) drag the average
down. Their **public APIs are all covered**; only deep parser branches
that exercise specific device-output shapes remain uncovered. Lifting
those to 90 % would require ~500 LOC of canned-fixture tests; tracked
as future work.

### Audit-batch security regression tests (76 total)

* `tests/test_security_audit_findings.py` — 25 tests (batches 1+2)
* `tests/test_security_audit_batch3.py` — 14 tests (batch 3)
* `tests/test_security_audit_batch4.py` — 24 tests (batch 4: fail-closed
  prod auth, per-actor tokens, hard `cryptography` / `defusedxml` imports,
  inventory-binding on every device-targeted route, sanitised credential
  delete, SSRF guard on cloud-metadata IPs, `hmac.compare_digest` regression
  detection, generic error envelopes on `find-leaf` / `nat-lookup`)
* `tests/test_runner_dispatch_coverage.py` — 13 tests covering every branch
  of `runner.run_device_commands` (api/ssh/unknown method, `command_id_filter`,
  `command_id_exact`, hostname extraction, parser application). Lifted
  `backend/runners/runner.py` from 51 % → 91.7 %.

Each test names its audit finding ID (C1, H6, M11, etc.) so the audit
report and the test suite are cross-referenceable.

---

## 2. Per-test-file pass matrix

| File | Tests | Status | Phase |
|------|-------|--------|-------|
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
| `tests/test_bgp_looking_glass.py` (legacy) | 14 | ✅ | pre-refactor |
| `tests/test_interface_recovery.py` (legacy) | 9 | ✅ | pre-refactor |
| `tests/test_parse_arista_interface_status.py` (legacy) | 3 | ✅ | pre-refactor |
| `tests/test_transceiver_recovery_policy.py` (legacy) | 2 | ✅ | pre-refactor |
| `tests/test_parse_cisco_interface_detailed.py` (legacy) | 1 | ✅ | pre-refactor |
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
| `tests/test_legacy_coverage_bgp_lg.py` | 24 | ✅ | legacy-coverage |
| `tests/test_legacy_coverage_route_map.py` | 12 | ✅ | legacy-coverage |
| `tests/test_legacy_coverage_find_leaf_nat.py` | 14 | ✅ | legacy-coverage |
| `tests/test_legacy_coverage_parse_output.py` | 43 | ✅ | legacy-coverage |
| `tests/test_legacy_coverage_runners.py` | 35 | ✅ | legacy-coverage |
| `tests/test_security_xss_spa.py` | 4 | ✅ | audit-wave-1 |
| `tests/test_security_vendor_integrity.py` | 1 | ✅ | audit-wave-1 |
| `tests/test_security_html_responses_include_csp.py` | 2 | ✅ | audit-wave-1 |
| `tests/test_security_bgp_routes_pin_ripestat_host.py` | 2 | ✅ | audit-wave-1 |
| `tests/test_security_token_gate_parsing.py` | 2 | ✅ | audit-wave-1 |
| `tests/test_security_diff_dos.py` | 1 | ✅ | audit-wave-1 |
| `tests/test_security_audit_log_coverage.py` | 1 + 4 xfail | ✅ / ⚠ xfail | audit-wave-1 |
| `tests/test_security_health_disclosure.py` | 1 xfail | ⚠ xfail | audit-wave-1 |
| `tests/test_security_router_devices_projection.py` | 1 xfail | ⚠ xfail | audit-wave-1 |
| `tests/test_security_legacy_credstore_deprecation.py` | 2 xfail | ⚠ xfail | audit-wave-1 |
| `tests/test_security_token_gate_immutable.py` | 1 xfail | ⚠ xfail | audit-wave-1 |
| **Total** | **861** (852 pass + 9 xfail) | **✅** | — |

Re-run a single file with:

```bash
venv/bin/python -m pytest tests/test_security_owasp.py -q
```

Re-run the whole suite with:

```bash
make test           # quiet
make cov            # global coverage report
make cov-new        # OOD-layer coverage report
```

---

## 3. Coverage — new OOD layer

```
backend/app_factory.py                             65      1     18      1    98%
backend/blueprints/__init__.py                      4      0      0      0   100%
backend/blueprints/health_bp.py                     7      0      0      0   100%
backend/blueprints/inventory_bp.py                 67      2     16      2    95%
backend/blueprints/notepad_bp.py                   26      4      4      1    83%
backend/config/__init__.py                          2      0      0      0   100%
backend/config/app_config.py                       56      4      6      2    90%
backend/config/commands_loader.py                  72     38     28      4    46%
backend/config/settings.py                          6      0      0      0   100%
backend/logging_config.py                          85     15     24      5    82%
backend/parsers/__init__.py                         2      0      0      0   100%
backend/parsers/engine.py                          33      2      8      2    90%
backend/repositories/__init__.py                    5      0      0      0   100%
backend/repositories/credential_repository.py      65      5     12      2    91%
backend/repositories/inventory_repository.py       90      8     24      6    88%
backend/repositories/notepad_repository.py         62      2     14      2    95%
backend/repositories/report_repository.py          73      0     10      0   100%
backend/request_logging.py                         33      1      4      1    95%
backend/runners/arista_runner.py                    7      0      0      0   100%
backend/runners/base_runner.py                      6      0      0      0   100%
backend/runners/cisco_runner.py                     7      0      0      0   100%
backend/runners/factory.py                         34      0     10      0   100%
backend/runners/ssh_runner_class.py                 7      0      0      0   100%
backend/security/__init__.py                        4      0      0      0   100%
backend/security/encryption.py                    211     16     54     11    90%
backend/security/sanitizer.py                      93      7     52      5    92%
backend/security/validator.py                      27      0     12      0   100%
backend/services/__init__.py                        6      0      0      0   100%
backend/services/credential_service.py             17      0      2      0   100%
backend/services/device_service.py                 45      0      8      0   100%
backend/services/inventory_service.py              21      1      0      0    95%
backend/services/notepad_service.py                 9      0      0      0   100%
backend/services/report_service.py                 13      0      0      0   100%
TOTAL                                            1260    106    306     44    90%
```

`backend/config/commands_loader.py` is left at 46% on purpose — it is
a pure thin loader for `commands.yaml` and is exercised end-to-end by
the golden tests (no error in any baseline run).  Adding a dedicated
unit test is tracked as a follow-up.

---

## 4. Coverage — global

```
TOTAL  4837  2270  2094  297  47%
```

The 53% gap is entirely inside the legacy modules listed below.  Each
is unchanged by this PR and is still served by the legacy
`backend/app.py` Flask routes for the domains that have not yet been
migrated to a Blueprint:

| Module | Coverage | Why |
|--------|----------|-----|
| `backend/app.py` | 21% | Most routes still here (BGP, NAT, Find Leaf, transceiver, run, credentials).  Phases 9–10 only migrated `inventory_*` + `notepad`. |
| `backend/find_leaf.py` | 5% | Pure legacy, unchanged. |
| `backend/nat_lookup.py` | 7% | Pure legacy, unchanged. |
| `backend/route_map_analysis.py` | 4% | Pure legacy, unchanged. |
| `backend/parse_output.py` | 42% | 1223 statements; only the parsers exercised by the golden snapshots are covered. |

These will rise automatically as subsequent phases migrate each
domain to its own Blueprint + Service + Repository.

---

## 5. Security evaluation (OWASP Top-10 + business-logic)

`tests/test_security_owasp.py` ships **72 named tests** grouped by
OWASP category.  Every category has at least one regression test.

| Category | Test count | Status |
|----------|------------|--------|
| **A01** Broken Access Control — credential payload never leaks via `CredentialRepository.list()` | 1 | ✅ |
| **A02 / A08** Cryptographic Failures + Software/Data Integrity — round-trip, single-byte tamper raises `EncryptionError`, empty-secret raises `ValueError`, cross-secret decrypt fails | 4 | ✅ |
| **A03** Injection — `CommandValidator` accepts safe `show`/`dir`, rejects `conf t`, shell meta (`;`, `&&`, `\|`, backticks, `$()`), length explosion, non-string types.  `InputSanitizer` rejects null bytes across `ip / hostname / credential_name / asn / prefix / string`, rejects shell-meta hostnames, rejects garbage IPs. | 47 | ✅ |
| **A04** Insecure Design — `ProductionConfig.validate()` raises on default `SECRET_KEY`, raises on empty, accepts strong | 3 | ✅ |
| **A05** Security Misconfiguration — `redact_sensitive` masks `password / api_key / Authorization / Cookie` (case-insensitive) | 1 | ✅ |
| **A07** Identification & Auth Failures — `CredentialService.set` refuses unsafe credential names *before* the repo is touched | 1 | ✅ |
| **A09** Logging & Monitoring Failures — every Flask response carries `X-Request-ID` | 1 | ✅ |
| **A10 / business-logic** — inventory hierarchy routes return empty lists when required params are missing; notepad PUT rejects missing `content`; notepad GET returns only the documented keys | 5 | ✅ |
| Cross-cutting helpers and parametrised cases | 9 | ✅ |
| **Total** | **72** | ✅ |

### Notes on what was *not* possible to weaken

* `EncryptionService` refuses to instantiate with an empty secret — no
  silent fallback to a default key.
* `EncryptionService` refuses to instantiate at all when neither the
  `cryptography` package nor the in-tree AES-128-CBC + HMAC-SHA256
  fallback can produce a valid Fernet-shape key.
* `ProductionConfig` refuses to start with the placeholder secret —
  enforced by `_register_services` in the App Factory.
* `CommandValidator` is the *only* gate to a runner — every non-`show /
  dir` command is rejected before transport.
* Every blueprint route logs a request id, both inbound and outbound,
  via `RequestLogger` (test asserts the response header).

---

## 6. Reproducibility

```bash
git clone https://github.com/asceylan/pergen.git
cd pergen
git checkout refactor/ood-tdd
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements-dev.txt
make test         # 402 passed
make cov-new      # 89.66 % on the new layer (gate 85)
make cov          # 47.41 % global (gate 45)
make lint         # ruff clean on new files
```

If any number above changes, `patch_notes.md` is updated in the same
commit.

---

## 7. Phase-13 security hardening — regression matrix

`tests/test_security_phase13.py` ships **33 named tests**, one (or
more) per audit finding from the parallel `security-reviewer` and
`python-reviewer` audits.  Every test pins the exact contract that
was fixed; a failure unambiguously identifies the regressed control.

| Audit ID | Severity | Fix | Tests |
|----------|----------|-----|-------|
| C-2 | CRITICAL | `/api/arista/run-cmds` routes every cmd through `CommandValidator` | 3 |
| C-3 | CRITICAL | Palo Alto API key moved to `X-PAN-KEY` header, never in URL | 1 |
| C-4 | CRITICAL | `/api/custom-command` uses `CommandValidator` (replaces local blocklist) | 3 |
| C-5 | CRITICAL | `/api/ping` validates each IP via `InputSanitizer.sanitize_ip` and caps device list at 64 | 3 |
| H-1 | HIGH     | `NotepadRepository.update` is atomic under concurrent writers | 1 |
| H-2 | HIGH     | NAT XML uses `defusedxml` (Billion-Laughs / external-entity) | 1 |
| H-5 | HIGH     | Notepad write returns generic 500 envelope (no message leak) | 1 |
| H-6 | HIGH     | `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` on every response | 4 |
| H-8 | HIGH     | SSH commands from `commands.yaml` go through `CommandValidator` | 1 |
| M-4 | MEDIUM   | `CommandValidator` NFKC-normalises input (defeats homoglyph bypass via fullwidth/IDS) | 3 |
| M-5 | MEDIUM   | `CommandValidator` strips leading whitespace and rejects embedded `\n`/`\r` | 2 |
| M-8 | MEDIUM   | `MAX_CONTENT_LENGTH` set on `BaseConfig`; per-route notepad cap returns 413 | 2 |
| py-HIGH | HIGH  | `encryption._key_expand_128` raises `ValueError` (survives `python -O`) | 1 |
| py-HIGH | HIGH  | `CredentialRepository` works with `:memory:` SQLite (persistent connection) | 1 |
| py-HIGH | HIGH  | `ReportRepository._safe_id` strips path separators; `_report_path` stays in reports dir | 2 |
| py-MED  | MED   | `_ip_sort_key` returns 4-tuple for malformed IPs (sort stability) | 1 |
| py-MED  | MED   | Blueprint `_svc()` helpers raise `RuntimeError` instead of `KeyError` | 2 |
| **Total** | — | — | **33** |

### Findings explicitly *retested* in `test_security_owasp.py`

The pre-existing OWASP suite (72 tests) continues to pass on every
phase-13-modified module: `CommandValidator` still rejects
`conf t / write mem / shell-meta`, `InputSanitizer` still rejects
NUL bytes / shell-meta hostnames / garbage IPs, encryption still
refuses tampered tokens, the Production config still rejects the
default `SECRET_KEY`.  Phase-13 *added* coverage on top; it removed
nothing.

---

## 8. Playwright E2E (audit-wave-1)

Added in `v0.2.0-audit-wave-1`. Drives the real SPA against a real
Flask server (no mocked backend); `webServer` config in
`playwright.config.ts` boots `./run.sh` and reuses any server already
on port 5000.

| Metric | Value |
|--------|-------|
| Spec files | **20** under `tests/e2e/specs/` |
| Tests | **62 / 62 passing** |
| Wall time | **~6–8 s** on a warm M-series Mac, headless Chromium |
| Browser | Chromium only (`projects: [{ name: "chromium" }]`) |
| Reporters | `list` (stdout) + `html` (`playwright-report/`) + `junit` (`test-results/junit.xml`) |
| Artefacts on failure | screenshot + video + trace on retry |
| Boot path under test | `./run.sh` → `FLASK_APP=backend.app_factory:create_app` |

### Spec coverage

| Spec | What it asserts |
|------|-----------------|
| `home.spec.ts` | landing page, 3×3 feature card grid renders |
| `navigation.spec.ts` | hash router, menu transitions, event-popup wiring |
| `prepost.spec.ts` | Pre/Post page boots, filters render |
| `notepad.spec.ts` | notepad page boots, line-editor list visible |
| `nat.spec.ts` | NAT lookup form, "Open on BGP page" link present |
| `findleaf.spec.ts` | Find Leaf page boots |
| `bgp.spec.ts` | BGP / Looking Glass page renders all three sub-tables |
| `restapi.spec.ts` | REST API page accepts a multi-line payload |
| `transceiver.spec.ts` | transceiver page filters + table headers |
| `credential.spec.ts` | credential page form + table render |
| `routemap.spec.ts` | DCI/WAN routers page boots |
| `subnet.spec.ts` | subnet calculator divides + joins correctly |
| `diff.spec.ts` | diff checker accepts two inputs and renders LCS sections |
| `api-health.spec.ts` | `/api/health` and `/api/v2/health` return 200 + expected envelope |
| `api-routes.spec.ts` | `/api/fabrics` / `/api/inventory` / `/api/credentials` smoke |
| `csp-no-inline.spec.ts` | regression guard — index.html has no inline `<script>`; CSP header is `script-src 'self'` |
| `security-headers.spec.ts` | every response carries CSP / HSTS / X-Frame / X-Content-Type / Referrer-Policy / Permissions-Policy |
| `flow-credential-add.spec.ts` | full flow: add credential → list shows it → delete → list empty |
| `flow-notepad-roundtrip.spec.ts` | full flow: PUT notepad → GET → content matches |
| `flow-diff-checker.spec.ts` | full flow: paste two payloads → diff renders, Added/Deleted/Changed counts correct |

Run with:

```bash
make e2e-install     # one-time
make e2e             # 62 / 62 in ~8 s
npx playwright show-report   # open the HTML report
```
