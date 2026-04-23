# DONE — Pergen Test Coverage Audit (2026-04-22, Wave 4)

Post-wave-3 close-out audit. Audits the working tree at HEAD
(`0446512 docs: wave-3 final sweep …`) against the wave-2 baseline at
`docs/test-coverage/coverage_audit_2026-04-22.md`.

> **No code was modified.** This is a read-only inventory + gap analysis.

Source data:

```bash
venv/bin/pytest --cov=backend --cov-branch \
    --cov-report=term-missing \
    --cov-report=json:docs/test-coverage/coverage_wave4.json -q
```

Result: **1394 passed, 0 xfail in 79.17 s** — combined coverage 84.17 %.

---

## 1. Headline numbers

| Metric                            | Wave-2 baseline | **Wave-4 (now)** | Δ          |
|-----------------------------------|----------------:|-----------------:|-----------:|
| Tests run (Python)                | 1128            | **1394**         | +266       |
| Total statements                  | 5,505           | 5,735            | +230       |
| Covered statements                | 4,540           | **4,998**        | +458       |
| Missing statements                | 965             | **737**          | -228       |
| Total branches                    | 2,234           | 2,264            | +30        |
| Covered branches                  | 1,522           | **1,735**        | +213       |
| Missing branches                  | 712             | **529**          | -183       |
| Partially-covered branches        | 354             | 309              | -45        |
| **Line coverage (statements)**    | 82.47 %         | **87.15 %**      | **+4.68 pp** |
| **Branch coverage**               | 68.13 %         | **76.63 %**      | **+8.50 pp** |
| **Combined (coverage.py)**        | 78.33 %         | **84.17 %**      | **+5.84 pp** |
| Files with coverage data          | 96              | 117              | +21        |
| Files at 0 % coverage             | 0               | **0**            | 0          |
| Files below 80 % (project policy) | 23              | **17**           | **-6**     |
| Files at 100 %                    | 35              | **47**           | +12        |
| Zero-body-coverage functions      | 19              | **22**           | +3 (see §4) |

The codebase is now **+4.17 pp above** the 80 % policy gate (was -1.67 pp).
However, the wave-3 god-module split into `find_leaf/`, `nat_lookup/`,
`bgp_looking_glass/`, and `route_map_analysis/` packages (commit
`3274107`) re-distributed the legacy-module coverage debt across **17
new files**, of which **6 are still <80 %** (see §3, §4). Net: combined
coverage went up because of the parser sweep + new e2e + Vitest + xfail
flips, not because the legacy core got new tests.

---

## 2. Files STILL below 80 % post wave-3 (17)

Sorted ascending (worst first). `MISS` = missing executable statements,
`BRMISS` = missing branches.

| Cov %  | Stmts | Miss | BRMISS | File                                              | Notes                                |
|-------:|------:|-----:|-------:|---------------------------------------------------|--------------------------------------|
|  9.5   |  64   |  56  |  20    | `backend/find_leaf/strategies/cisco.py`           | **NEW (wave-3 split)** — 0 unit tests |
| 10.8   |  56   |  48  |  18    | `backend/find_leaf/strategies/arista.py`          | **NEW (wave-3 split)** — 0 unit tests |
| 22.0   |  74   |  52  |  40    | `backend/nat_lookup/xml_helpers.py`               | **NEW (wave-3 split)** — only smoke   |
| 23.3   |  74   |  53  |  36    | `backend/route_map_analysis/comparator.py`        | **NEW (wave-3 split)** — 0 unit tests |
| 28.6   |  20   |  12  |   8    | `backend/find_leaf/__init__.py`                   | **NEW** — public re-export + smoke    |
| 35.0   |  16   |   9  |   4    | `backend/find_leaf/ip_helpers.py`                 | **NEW** — `_leaf_ip_from_remote` 0-cov |
| 51.9   | 108   |  45  |  30    | `backend/nat_lookup/service.py`                   | `_try_one_firewall` only 34 %        |
| 61.0   |  39   |  14  |   2    | `backend/nat_lookup/palo_alto/api.py`             | `call_nat_rule_config` 0 %           |
| 66.1   |  85   |  27  |  14    | `backend/runners/ssh_runner.py`                   | `run_config_lines_pty` interactive PTY |
| 67.0   | 133   |  35  |  30    | `backend/parsers/arista/interface_status.py`      | unchanged from wave-2                |
| 71.5   | 105   |  25  |  22    | `backend/route_map_analysis/parser.py`            | `_process_bgp_cmd_list` 48 %         |
| 71.6   |  88   |  23  |  19    | `backend/parsers/cisco_nxos/arp_suppression.py`   | improved from 16.9 % (wave-2)        |
| 72.1   | 240   |  50  |  52    | `backend/bgp_looking_glass/ripestat.py`           | replaced legacy `bgp_looking_glass.py` (74 %); slightly worse on branches |
| 74.2   | 105   |  21  |  18    | `backend/runners/interface_recovery.py`           | unchanged from wave-2                |
| 75.0   |  68   |  15  |   4    | `backend/credential_store.py`                     | unchanged — legacy shim, deprecated  |
| 76.0   |  17   |   3  |   3    | `backend/bgp_looking_glass/peeringdb.py`          | **NEW (wave-3 split)**                |
| 76.8   |  52   |   9  |  10    | `backend/parsers/cisco_nxos/isis_brief.py`        | improved from 70.7 % (wave-2)        |

**6 of 17 are NEW wave-3 package files.** The other 11 are the same
chronic gaps the wave-2 audit flagged (parsers/runners/legacy
credential store), partially improved.

### Files at 0 % coverage

**None.** Every Python module is at least imported. (Same signal as
wave-2; weak — see §4 for body-line coverage.)

### Files at 100 % (47, +12 vs wave-2)

Now includes all `bgp_looking_glass/{__init__,http_client}`,
`nat_lookup/{__init__,ip_helpers,palo_alto/__init__}`,
`find_leaf/strategies/__init__`, `route_map_analysis/__init__`,
`parsers/arista/{interface_description,transceiver,uptime}`,
`parsers/cisco_nxos/system_uptime`, all `services/*` (except
`inventory_service` 92 %, `transceiver_service` 90 %), all
`runners/*_runner` shims, both `commands_bp` and `health_bp`.

---

## 3. Wave-3 package audit — coverage by package

The 4 wave-3 split packages account for **63 functions** across **21
.py files** (4+4+5+2 non-init + 4 `__init__.py` shims = 17 + 4 nested
__init__.py = 21). Only the function bodies are counted below.

| Package                                | Files | Stmts | Cov %  | Branches | BrCov % |
|----------------------------------------|------:|------:|-------:|---------:|--------:|
| `backend/bgp_looking_glass/`           | 6     | 363   | **83.5 %** | 168     | 63.7 %  |
| `backend/route_map_analysis/`          | 3     | 183   | **57.4 %** | 102     | 43.1 %  |
| `backend/nat_lookup/`                  | 6     | 242   | **54.1 %** |  94     | 23.4 %  |
| `backend/find_leaf/`                   | 6     | 223   | **43.0 %** |  72     | 30.6 %  |

**Critical finding: the wave-3 package split moved the god modules
behind nicer import paths, but did not add unit tests for the
extracted logic.** `find_leaf/` and `nat_lookup/` are noticeably
*worse* than the legacy `find_leaf.py` (36.2 %) and `nat_lookup.py`
(37.1 %) once you factor in the new `strategies/*` files (10 %) — the
split exposed every helper as its own measurable surface, and most of
those helpers had only been exercised through the legacy entrypoint.

### Wave-3 functions with **zero** body-line execution (19)

These are functions inside the 4 wave-3 packages whose every body
statement is missing. Sorted by missing-line count.

| Miss | File                                                    | Function                                              |
|----:|----------------------------------------------------------|-------------------------------------------------------|
|  39 | `backend/find_leaf/strategies/cisco.py:69`               | `_complete_cisco_hit`                                 |
|  32 | `backend/find_leaf/strategies/arista.py:65`              | `_complete_arista_hit`                                |
|  30 | `backend/nat_lookup/xml_helpers.py:124`                  | `_find_translated_ips_in_rule_config`                 |
|  16 | `backend/find_leaf/strategies/cisco.py:32`               | `_query_cisco_leaf_search`                            |
|  16 | `backend/find_leaf/strategies/arista.py:30`              | `_query_arista_leaf_search`                           |
|   9 | `backend/find_leaf/ip_helpers.py:28`                     | `_leaf_ip_from_remote`                                |
|   7 | `backend/nat_lookup/palo_alto/api.py:89`                 | `call_nat_rule_config`                                |
|   6 | `backend/route_map_analysis/comparator.py:17`            | `_device_order_key`                                   |
|   6 | `backend/find_leaf/__init__.py:38`                       | `_query_one_leaf_search`                              |
|   6 | `backend/find_leaf/__init__.py:54`                       | `_complete_find_leaf_from_hit`                        |
|   6 | `backend/bgp_looking_glass/ripestat.py:138`              | `_entry_to_text`                                      |
|   5 | `backend/nat_lookup/xml_helpers.py:95`                   | `_format_translated_address_response`                 |
|   5 | `backend/find_leaf/strategies/cisco.py:79`               | `_complete_cisco_hit.device_by_ip` (closure)          |
|   5 | `backend/find_leaf/strategies/arista.py:75`              | `_complete_arista_hit.device_by_ip` (closure)         |
|   4 | `backend/nat_lookup/xml_helpers.py:43`                   | `_format_first_nat_rule_response`                     |
|   4 | `backend/nat_lookup/palo_alto/api.py:45`                 | `build_rule_config_xpath`                             |
|   1 | `backend/route_map_analysis/comparator.py:40`            | `build_unified_bgp_full_table._norm_group` (closure)  |
|   1 | `backend/nat_lookup/xml_helpers.py:103`                  | `_format_translated_address_response.esc` (closure)   |
|   1 | `backend/nat_lookup/xml_helpers.py:148`                  | `_find_translated_ips_in_rule_config.local_name` (cl.)|

### Wave-3 functions with <50 % body-line coverage (4)

| Cov %  | Miss | File                                                    | Function                                              |
|-------:|----:|----------------------------------------------------------|-------------------------------------------------------|
|  25.0  |  47 | `backend/route_map_analysis/comparator.py:27`            | `build_unified_bgp_full_table`                        |
|  34.0  |  34 | `backend/nat_lookup/service.py:89`                       | `_try_one_firewall`                                   |
|  43.5  |  12 | `backend/nat_lookup/xml_helpers.py:66`                   | `_find_nat_rule_name_in_response`                     |
|  48.1  |  14 | `backend/route_map_analysis/parser.py:100`               | `_extract_bgp._process_bgp_cmd_list` (closure)        |

The 4 wave-3 packages contain **63 functions**. **19 are zero-body
covered** (30 %). **23 of 63** (37 %) are below 50 % covered when
counting the partial set above.

---

## 4. All zero-body-coverage functions across `backend/` (22)

Across the entire `backend/` package, 22 functions have **no executed
body line**. 19 of them sit inside the 4 wave-3 packages (see §3). The
remaining 3 are unchanged from wave-2:

| Miss | File                                            | Function                  |
|----:|--------------------------------------------------|---------------------------|
|   6 | `backend/credential_store.py:160`                | `delete_credential`       |
|   5 | `backend/credential_store.py:102`                | `list_credentials`        |
|   1 | `backend/services/inventory_service.py:64`       | `InventoryService.save` (defensive `if` branch) |

---

## 5. Top 10 functions that need tests most urgently

Ordered by combined risk (size × business criticality × no current test).

| # | Risk | File:line                                                | Function                              | Why urgent                              |
|--:|:----:|----------------------------------------------------------|---------------------------------------|------------------------------------------|
| 1 |  🔴  | `backend/find_leaf/strategies/cisco.py:69`               | `_complete_cisco_hit`                 | 39 missing lines; full Cisco "find leaf" path is **0 % covered** |
| 2 |  🔴  | `backend/find_leaf/strategies/arista.py:65`              | `_complete_arista_hit`                | 32 missing; full Arista "find leaf" path **0 %** |
| 3 |  🔴  | `backend/nat_lookup/xml_helpers.py:124`                  | `_find_translated_ips_in_rule_config` | 30 missing; central NAT translation logic |
| 4 |  🔴  | `backend/route_map_analysis/comparator.py:27`            | `build_unified_bgp_full_table`        | 47/64 missing; **25 % covered** core data shaping |
| 5 |  🔴  | `backend/nat_lookup/service.py:89`                       | `_try_one_firewall`                   | 34/53 missing; **34 %** covered NAT orchestrator |
| 6 |  🔴  | `backend/find_leaf/strategies/cisco.py:32`               | `_query_cisco_leaf_search`            | 16 missing; per-leaf SSH/eAPI dispatch (Cisco) |
| 7 |  🔴  | `backend/find_leaf/strategies/arista.py:30`              | `_query_arista_leaf_search`           | 16 missing; per-leaf dispatch (Arista) |
| 8 |  🟠  | `backend/find_leaf/ip_helpers.py:28`                     | `_leaf_ip_from_remote`                | 9 missing; remote-side IP resolution helper |
| 9 |  🟠  | `backend/route_map_analysis/parser.py:100`               | `_extract_bgp._process_bgp_cmd_list`  | 14 missing; **48 %** covered BGP cmd list parser |
| 10|  🟠  | `backend/nat_lookup/palo_alto/api.py:89`                 | `call_nat_rule_config`                | 7 missing; PAN-OS XML-API call (zero body coverage) |

**Honourable mentions** (still material but smaller surface):

- `backend/route_map_analysis/comparator.py:17::_device_order_key` — 6 missing, sort key used by every BGP comparison.
- `backend/find_leaf/__init__.py:{38,54}::_query_one_leaf_search`/`_complete_find_leaf_from_hit` — 6+6 missing, public re-export wrappers.
- `backend/bgp_looking_glass/ripestat.py:138::_entry_to_text` — 6 missing; same gap flagged in wave-2 audit, still open after the package split.
- `backend/runners/ssh_runner.py:141-162::run_config_lines_pty` — 22 missing; interactive PTY config-push helper, still 21 % covered (carried over from wave-2).

---

## 6. Wave-3 NEW test files inventory

### NEW Playwright specs added in wave-3 (15) — `tests/e2e/specs/flow-*.spec.ts`

P0 — mutating / device-touching flows (8):

1. `flow-prepost-run.spec.ts`               — PRE run round-trip
2. `flow-inventory-import-export.spec.ts`   — CSV upload + Download capture
3. `flow-transceiver-run.spec.ts`           — fabric/site → Run → result rows
4. `flow-transceiver-clear-counters.spec.ts`— per-row clear-counters
5. `flow-route-map-compare.spec.ts`         — pick scope → Compare → diff table
6. `flow-custom-command.spec.ts`            — free-form command on `#restapi`
7. `flow-find-leaf-success.spec.ts`         — IP search → result table
8. `flow-nat-lookup-success.spec.ts`        — full 4-leg NAT pipeline mock

P1 — read-side flows (7):

9.  `flow-bgp-lookup.spec.ts`               — RIPEStat-side endpoints + status cards
10. `flow-bgp-favourites.spec.ts`           — localStorage persistence + render
11. `flow-restapi-submit.spec.ts`           — multi-device REST API submit
12. `flow-credential-validate.spec.ts`      — credential Test action
13. `flow-diff-navigation.spec.ts`          — diff result navigation arrows
14. `flow-subnet-split.spec.ts`             — pure-client subnet calculator
15. `flow-mutating-api-smoke.spec.ts`       — 5 POST/PUT/DELETE smoke tests

(The 6 other `flow-*.spec.ts` files — `flow-credential-add`,
`flow-diff-checker`, `flow-error-paths`, `flow-inventory-crud`,
`flow-notepad-roundtrip`, `flow-xss-defence` — are pre-wave-3 carry-overs
from earlier audit waves.)

### NEW Vitest unit spec added in wave-3 (1) — `tests/frontend/unit/`

- `tests/frontend/unit/subnet.spec.ts` — exercises `backend/static/js/lib/subnet.js`:
  - `ipToLong`, `longToIp`, `parseCidr`, `networkAddress`,
    `subnetAddresses`, `subnetLastAddress`.

(The earlier `tests/frontend/unit/utils.spec.ts` is a wave-2 carry-over.)

### Other wave-3 sweep additions in `tests/`

The wave-3 commits also added/touched (not strictly "new test files",
but worth noting):

- `tests/test_security_*` — 12 new files plus expanded coverage in 4
  existing files for the audit-wave-2 closures (Phases 1-11).
- `tests/test_phase9_blueprints.py`, `tests/test_runs_reports_bp_phase11.py`,
  `tests/test_device_commands_bp_phase10.py` — already on disk pre-wave-3.

---

## 7. Test inventory by type (Wave 4)

| Type                                        | Files | Tests | Δ vs wave-2 | Notes                                           |
|---------------------------------------------|------:|------:|------------:|-------------------------------------------------|
| Python — total collected by pytest          | 97    | **1394** | +266      | All passing, **0 xfails** (was 9)               |
| Python `@pytest.mark.unit`                  |  —    | 354   | n/a         | Marker hygiene phase 14 landed                  |
| Python `@pytest.mark.integration`           |  —    | 231   | n/a         | Marker hygiene phase 14 landed                  |
| Python `@pytest.mark.security`              |  —    | 287   | n/a         | (file count: 28)                                |
| Python `@pytest.mark.golden`                |  —    |  78   | n/a         | (file count: 4 — `tests/golden/`)               |
| Python parser-pkg unit tests                |  27   | n/a   | +19         | `tests/parsers/{arista,cisco_nxos,common,generic}/` |
| Python blueprint-phase tests                |   8   | n/a   | -6 (consolidation) | `tests/test_*_bp_phase*.py`                |
| Python "other" root tests                   |  30   | n/a   | n/a         | Module/class direct tests                       |
| **Frontend unit (Vitest)**                  |   2   | **37**| **+1 file / +37 tests** | Was 0 tests at wave-2 baseline      |
| **End-to-end (Playwright)**                 |  38   | **85**| **+15 files / +19 tests** | `tests/e2e/specs/*.spec.ts`             |

(Marker-tagged Python totals 354+231+287+78 = 950 tagged of 1394 collected; 444 still untagged. Marker hygiene reached the must-tag-everything-new bar but did not back-fill all legacy files.)

---

## 8. Concrete list of NEW test files to create (post wave-3)

These are the gaps the wave-3 sweep did **not** close. Path-relative to
repo root. Estimated impact uses the per-function missing-line counts
from §3.

### Tier 1 — Wave-3 package zero-coverage closure (highest impact)

1. **`tests/find_leaf/test_strategies_cisco.py`** — direct unit tests for `_query_cisco_leaf_search` (mock runner) and `_complete_cisco_hit` (mock device lookup). **Target uplift: `find_leaf/strategies/cisco.py` 9.5 % → 80 %+ (lifts +56 stmts).**
2. **`tests/find_leaf/test_strategies_arista.py`** — same pattern for `_query_arista_leaf_search` + `_complete_arista_hit`. **Target uplift: `find_leaf/strategies/arista.py` 10.8 % → 80 %+ (lifts +48 stmts).**
3. **`tests/find_leaf/test_ip_helpers.py`** — exercise `_leaf_ip_from_remote` (loopback / static-mac variants). **Target: `find_leaf/ip_helpers.py` 35 % → 95 %+.**
4. **`tests/find_leaf/test_init.py`** — exercise the public re-export wrappers `_query_one_leaf_search` and `_complete_find_leaf_from_hit`. **Target: `find_leaf/__init__.py` 28.6 % → 90 %+.**
5. **`tests/nat_lookup/test_xml_helpers.py`** — direct tests for `_find_translated_ips_in_rule_config` (with `local_name` closure), `_format_translated_address_response` (with `esc` closure), `_format_first_nat_rule_response`, and `_find_nat_rule_name_in_response`. **Target: `nat_lookup/xml_helpers.py` 22 % → 80 %+.**
6. **`tests/nat_lookup/test_service.py`** — direct tests for `_try_one_firewall` (currently 34 %); mock the PAN-OS HTTP client, exercise the multi-firewall fan-out. **Target: `nat_lookup/service.py` 51.9 % → 80 %+.**
7. **`tests/nat_lookup/test_palo_alto_api.py`** — direct tests for `build_rule_config_xpath` and `call_nat_rule_config` (responses library / requests-mock). **Target: `nat_lookup/palo_alto/api.py` 61 % → 95 %+.**
8. **`tests/route_map_analysis/test_comparator.py`** — direct tests for `build_unified_bgp_full_table` (currently 25 %), `_device_order_key`, and the `_norm_group` closure. **Target: `route_map_analysis/comparator.py` 23.3 % → 80 %+.**
9. **`tests/route_map_analysis/test_parser.py`** — direct tests for `_extract_bgp._process_bgp_cmd_list` (48 %) and the remaining defensive branches. **Target: `route_map_analysis/parser.py` 71.5 % → 90 %+.**
10. **`tests/bgp_looking_glass/test_ripestat_format.py`** — direct tests for `_entry_to_text` and the >50 missing branches in `ripestat.py`. **Target: `bgp_looking_glass/ripestat.py` 72.1 % → 85 %+.**

### Tier 2 — Carry-over gaps from wave-2 still open

11. `tests/test_credential_store_legacy.py` — `list_credentials` + `delete_credential` (still 0 % body). The xfail marker was retired in wave-3 phase 6 but real tests still need to exist before the legacy shim can be removed.
12. `tests/test_ssh_runner_pty.py` — mock paramiko `invoke_shell` and exercise `run_config_lines_pty` (still 21 % covered after wave-3).
13. `tests/test_arista_eapi_errors.py` / `tests/test_cisco_nxapi_errors.py` — non-200 / malformed JSON-RPC error envelopes (lines 97/100-102 and 62/66/72-74 respectively).
14. `tests/test_interface_recovery_branches.py` — multi-vendor / multi-row matching (still 74 %).
15. `tests/parsers/arista/test_interface_status.py` — 67 %, still the worst Arista parser.
16. `tests/parsers/cisco_nxos/test_isis_brief.py` — fill the remaining 9 missing lines.
17. `tests/parsers/cisco_nxos/test_arp_suppression.py` — already exists in `tests/parsers/cisco_nxos/`? No — the dir contains tests for other parsers but not for `arp_suppression`. Add to lift 71.6 % → 90 %+.

### Tier 3 — Frontend / e2e gaps (low marginal lift, high confidence value)

18. `tests/frontend/unit/notepad.spec.ts` — pull notepad serialisation/dedupe out of `app.js` into `backend/static/js/lib/notepad.js`, mirror the `subnet.spec.ts` pattern.
19. `tests/frontend/unit/diff.spec.ts` — same treatment for the diff/highlight helpers.
20. `tests/frontend/unit/polling.spec.ts` — same treatment for the exponential-backoff / cancel logic.
21. (Out-of-scope per task description: full SPA IIFE coverage. Only `lib/*` extracts have Vitest tests today, and that is intentional.)

### Estimated cumulative impact if Tier 1 (1-10) is completed

- `find_leaf/` package: 43.0 % → ~85 %.
- `nat_lookup/` package: 54.1 % → ~85 %.
- `route_map_analysis/` package: 57.4 % → ~85 %.
- `bgp_looking_glass/` package: 83.5 % → ~88 %.
- Whole-codebase combined coverage: **84.17 % → ~90 %**.
- Branch coverage: **76.63 % → ~84 %**.
- Files <80 %: **17 → ~6** (mostly the 4 chronic parser/runner files
  + `credential_store.py`).
- Zero-body-coverage functions: **22 → ~3** (only the legacy
  `credential_store` shim functions and the defensive
  `InventoryService.save` branch).

---

## 9. Out-of-scope (per audit task)

- **Full SPA IIFE coverage in `backend/static/js/app.js` (~5,253 lines).**
  Per the wave-3 plan and this task, only the helpers extracted into
  `backend/static/js/lib/` (currently `subnet.js` + the wave-2 utils
  helpers) have Vitest tests. The IIFE itself remains exercised only
  via Playwright. **Noted, not flagged.**

---

## 10. Appendix — how this audit was generated

```bash
venv/bin/pytest --cov=backend --cov-branch \
    --cov-report=term-missing \
    --cov-report=json:docs/test-coverage/coverage_wave4.json -q
```

Result: `1394 passed in 79.17s` — combined coverage 84.17 %.

Per-file, per-function and per-branch breakdowns were derived from
`docs/test-coverage/coverage_wave4.json` using a small AST-based
traversal (function spans → executed-vs-missing line sets) and the
wave-3 dir filter on `backend/{find_leaf,nat_lookup,bgp_looking_glass,route_map_analysis}/`.

NEW-file inventory was sourced via:

```bash
git diff --name-only --diff-filter=A 33a6a07..HEAD -- \
    'tests/e2e/specs/*.ts' 'tests/frontend/**' 'backend/static/js/lib/**'
```

(`33a6a07` is the wave-2 closing commit; `HEAD` is `0446512`.)

The raw JSON report (`docs/test-coverage/coverage_wave4.json`) is left
in the repo for follow-up tooling.

---

## Wave-7 follow-up (2026-04-23)

The wave-4 Tier-1 backfill list (10 items) was largely closed in
wave-5 / wave-6:

- `find_leaf/strategies/cisco.py`: 9.5 % → **88 %**
- `find_leaf/strategies/arista.py`: 10.8 % → **89 %**
- `find_leaf/service.py`: 51.9 % → **91 %**
- `nat_lookup/xml_helpers.py`: 22 % → **88 %**
- `nat_lookup/service.py`: 51.9 % → **92 %**
- `route_map_analysis/comparator.py`: 23.3 % → **97 %**
- `route_map_analysis/parser.py`: 71.5 % → **93 %**
- `bgp_looking_glass/ripestat.py`: 72.1 % → **86 %**

Wave-7 added 51 new tests in 9 files (security regressions for the
CRITICAL+HIGH cluster — see `docs/security/DONE_audit_2026-04-23-wave7.md`).
Net suite: **1767 passed + 1 xfailed**, combined coverage **90.79 %**.

The wave-4 audit's "files <80 %" count went from **17 → 6** (wave-7).
Tier-1 backfill items are now closed; remaining 6 sub-80 % files are
chronic operator-output-variance gaps in the parser surface, plus
`backend/credential_store.py` (75 %) which has the wave-7 v2 fall-through
bridge added — only the legacy `list_credentials` / `delete_credential`
functions remain 0-body covered (acceptable; deprecated module).

Cross-reference: `docs/test-coverage/DONE_coverage_audit_2026-04-23-wave7.md`.

— end of follow-up note —
