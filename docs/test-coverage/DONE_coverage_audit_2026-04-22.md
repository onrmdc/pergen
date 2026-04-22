# DONE — Pergen Test Coverage Audit (2026-04-22)

Audit of the test coverage for the entire `/Users/asim.ceylan/pergen` codebase.
Source data: `pytest --cov=backend --cov-branch --cov-report=term-missing
--cov-report=json:coverage_audit.json` against the working tree at HEAD.

> **No code was modified.** This is a read-only inventory + gap analysis.

---

## 1. Headline numbers

| Metric                            | Value          |
|-----------------------------------|----------------|
| Tests run                         | **1128 passed, 9 xfail** |
| Total statements                  | 5,505          |
| Covered statements                | 4,540          |
| Missing statements                | 965            |
| Total branches                    | 2,234          |
| Covered branches                  | 1,522          |
| Missing branches                  | 712            |
| Partially-covered branches        | 354            |
| **Line coverage (statements)**    | **82.47 %**    |
| **Branch coverage**               | **68.13 %**    |
| **Combined (coverage.py)**        | **78.33 %**    |
| Files with coverage data          | 96             |
| Files at 0 % coverage             | **0**          |
| Files below 80 % (project policy) | **23**         |
| Files at 100 %                    | 35             |

Threshold reality:

- `pytest.ini` / `pyproject.toml` gate: **45 %** (intentionally lax — see
  `[tool.coverage.report]` comment about the legacy modules).
- Repo policy in `AGENTS.md`: **80 %**.
- `make cov-new` (scoped to the new OOD layer) gate: **85 %**.

The codebase is currently **1.67 percentage points below its stated 80 %
policy** when the legacy modules are included, and the legacy
`find_leaf.py` / `nat_lookup.py` / `route_map_analysis.py` trio is the
single largest drag on the average.

The user-reported "parser surface ~67 %" figure matches: aggregating only
`backend/parsers/**`, statement coverage is **71.9 %** and branch coverage
is **58.0 %** — i.e. parsers are the second-largest gap after legacy.

---

## 2. Files below 80 % coverage

Sorted ascending (worst first). `MISS` = missing executable statements,
`BRMISS` = missing branches.

| Cov %  | Stmts | Miss | BRMISS | File                                                  |
|-------:|------:|-----:|-------:|-------------------------------------------------------|
| 16.9   |  88   |  70  |  53    | `backend/parsers/cisco_nxos/arp_suppression.py`       |
| 28.8   |  99   |  64  |  62    | `backend/parsers/cisco_nxos/transceiver.py`           |
| 36.2   | 184   | 114  |  48    | `backend/find_leaf.py`                                |
| 37.1   | 183   | 102  |  66    | `backend/nat_lookup.py`                               |
| 38.0   |  32   |  17  |  14    | `backend/parsers/arista/arp.py`                       |
| 38.7   |  89   |  49  |  51    | `backend/parsers/cisco_nxos/arp.py`                   |
| 42.1   |  24   |  11  |  11    | `backend/parsers/arista/bgp.py`                       |
| 45.5   |  39   |  20  |  10    | `backend/parsers/cisco_nxos/power.py`                 |
| 50.9   | 175   |  78  |  58    | `backend/route_map_analysis.py`                       |
| 66.3   |  68   |  22  |   9    | `backend/runners/ssh_runner.py`                       |
| 67.0   | 133   |  35  |  30    | `backend/parsers/arista/interface_status.py`          |
| 68.2   |  70   |  19  |  16    | `backend/parsers/cisco_nxos/interface_status.py`      |
| 68.3   |  38   |  11  |   8    | `backend/parsers/cisco_nxos/interface_description.py` |
| 70.7   |  52   |  12  |  12    | `backend/parsers/cisco_nxos/isis_brief.py`            |
| 71.9   |  24   |   6  |   3    | `backend/parsers/arista/cpu.py`                       |
| 72.7   |  42   |  11  |   7    | `backend/parsers/cisco_nxos/interface_mtu.py`         |
| 73.9   |  62   |  14  |  10    | `backend/parsers/cisco_nxos/interface_detailed.py`    |
| 74.0   |  65   |  15  |   4    | `backend/credential_store.py` (legacy)                |
| 74.0   | 296   |  58  |  61    | `backend/bgp_looking_glass.py`                        |
| 74.2   | 105   |  21  |  18    | `backend/runners/interface_recovery.py`               |
| 75.9   |  25   |   6  |   1    | `backend/parsers/arista/uptime.py`                    |
| 76.5   |  24   |   5  |   3    | `backend/parsers/arista/disk.py`                      |
| 77.3   |  18   |   4  |   1    | `backend/parsers/cisco_nxos/system_uptime.py`         |

### Files at 0 % coverage

**None.** Every Python module in `backend/` is at least imported during
test runs (mostly as a side effect of `app_factory` boot). This is a
weak signal — many of these "covered at import" modules still contain
zero-coverage *functions* (see §4).

### Files at 100 % coverage (35)

Includes all of `services/*` (except `inventory_service` 92 %,
`transceiver_service` 90 %), most of `repositories/*`, `runners/factory`,
`parsers/dispatcher`, `parsers/common/{formatting,regex_helpers}`, all
runner subclass shims, both `commands_bp` and `health_bp`, and the
entire `security/validator` / `security/__init__` surface.

---

## 3. Frontend, blueprints, runners, parsers — surface checks

### Frontend (`backend/static/js/app.js`)

- `app.js` is **5,253 lines** and contains ~244 functions/closures.
- **No JS unit-test framework is installed** (no Jest, no Vitest — only
  `@playwright/test`). `package.json` exposes only `e2e`, `e2e:headed`,
  `e2e:report`. There are zero `*.test.ts` / `*.spec.js` unit files.
- Coverage of `app.js` is therefore **indirect only** — exercised through
  20 Playwright specs against the running Flask app. There is no
  per-function JS coverage report.
- **Surface gap:** input validation, render helpers, diff/highlight logic,
  notepad serialization, copy-to-clipboard handlers, modal flows, and
  WebSocket-style polling code in `app.js` have no targeted tests.

### Blueprints — every endpoint has at least one route test

All 12 blueprints are at **≥89 % coverage**. The phase-* test files in
`tests/test_*_bp_phase*.py` exercise each blueprint with a real Flask
test client. Misses are limited to defensive branches (404/500 fallbacks,
edge-case validation):

| Blueprint                | Cov   | Notes on misses                                |
|--------------------------|------:|------------------------------------------------|
| `health_bp`              | 100 % | —                                              |
| `commands_bp`            | 100 % | —                                              |
| `inventory_bp`           | 96 %  | 2 unreachable branches (lines 120, 122)        |
| `device_commands_bp`     | 96 %  | 4 error paths (42, 81, 133, 253)               |
| `bgp_bp`                 | 95 %  | 2 lines + 3 partial branches                   |
| `notepad_bp`             | 95 %  | 1 error path (56)                              |
| `runs_bp`                | 94 %  | 6 lines, mostly defensive guards               |
| `network_ops_bp`         | 94 %  | 3 lines (55-58 error-handling, 113)            |
| `reports_bp`             | 93 %  | 2 lines (32, 50)                               |
| `network_lookup_bp`      | 92 %  | 5 lines (44-46, 122-129)                       |
| `credentials_bp`         | 90 %  | 6 lines incl. error path 98-102               |
| `transceiver_bp`         | 89 %  | 16 lines incl. error paths and one polling branch |

**Verdict:** blueprint route coverage is in good shape — the gaps are
small and targeted. No new "endpoint X is completely untested" finding.

### Runners

Touch real network I/O — kept honest by mocks in
`tests/test_runner_classes.py`, `test_runner_dispatch_coverage.py`,
`test_legacy_coverage_runners.py`, and `tests/golden/test_runners_baseline.py`.

| File                                    | Cov   | Gap                                              |
|-----------------------------------------|------:|--------------------------------------------------|
| `runners/_http.py`                      | 100 % | —                                                |
| `runners/{base,arista,cisco}_runner.py` | 100 % | —                                                |
| `runners/ssh_runner_class.py`           | 100 % | —                                                |
| `runners/factory.py`                    | 100 % | —                                                |
| `runners/runner.py`                     |  92 % | 7 lines — error fallbacks                        |
| `runners/arista_eapi.py`                |  88 % | 3 lines — HTTP error path (97, 100-102)          |
| `runners/cisco_nxapi.py`                |  84 % | 4 lines — HTTP failure / non-200 (62, 66, 72-74) |
| `runners/interface_recovery.py`         |  74 % | 21 lines — multiple recovery paths                |
| `runners/ssh_runner.py`                 |  66 % | 22 lines — the legacy interactive PTY path        |

**`ssh_runner.py:run_config_lines_pty`** (interactive config-push
helper) is only 21 % covered and is a real risk surface.

### Parser package — recently refactored

Aggregate: **71.9 % statements / 58.0 % branches** across 30 modules.

| Status                                                   | Count |
|----------------------------------------------------------|------:|
| `parsers/dispatcher.py`, `engine.py`, all common helpers | 91-100 % |
| Vendor-specific parsers <80 %                            | 14    |
| Vendor-specific parsers <50 %                            | 5     |

The Cisco NX-OS family is in worst shape, exactly matching the user's
expectation:

- `cisco_nxos/arp_suppression.py` — **17 %** (parsing of L2VPN EVPN
  ARP-suppression cache is largely unexercised).
- `cisco_nxos/transceiver.py` — **29 %** (DOM Tx/Rx extraction across
  varied schema shapes is mostly untested).
- `cisco_nxos/arp.py` — **39 %**.
- `cisco_nxos/power.py` — **45 %**.

The Arista vendor split is also weak in the same areas:

- `arista/arp.py` — **38 %**.
- `arista/bgp.py` — **42 %**.

### Important: vendor parser test directories are *empty*

```
tests/parsers/arista/__init__.py        (only __init__.py, 0 test files)
tests/parsers/cisco_nxos/__init__.py    (only __init__.py, 0 test files)
```

The vendor scaffold exists in `tests/parsers/` but contains no actual
test modules. The only vendor parser coverage today comes from
`tests/golden/test_parsers_golden.py` (snapshot tests against fixtures
in `tests/fixtures/golden/`). There are 28 golden fixtures, but for
the ARP-suppression / Cisco-transceiver / vendor-ARP / vendor-BGP
parsers, no unit tests exist that exercise edge cases or error paths.

---

## 4. Functions with **zero** executed body lines (19)

These are public or private functions where coverage.py recorded *no*
hit on a single body statement. Sorted by missing-line count.

| Miss | File                                            | Function                                       |
|----:|--------------------------------------------------|------------------------------------------------|
| 68 | `backend/find_leaf.py:100`                        | `_complete_find_leaf_from_hit()`               |
| 42 | `backend/parsers/cisco_nxos/transceiver.py:17`    | `_cisco_find_tx_rx_in_dict()`                  |
| 31 | `backend/nat_lookup.py:114`                       | `_find_translated_ips_in_rule_config()`        |
| 30 | `backend/find_leaf.py:40`                         | `_query_one_leaf_search()`                     |
| 17 | `backend/parsers/cisco_nxos/arp_suppression.py:16`| `_get_arp_suppression_entries_list()`          |
| 16 | `backend/parsers/cisco_nxos/arp.py:38`            | `_parse_cisco_arp_ascii_for_ip()`              |
|  9 | `backend/find_leaf.py:24`                         | `_leaf_ip_from_remote()`                       |
|  6 | `backend/bgp_looking_glass.py:173`                | `_entry_to_text()`                             |
|  6 | `backend/credential_store.py:135`                 | `delete_credential()` (legacy module)          |
|  6 | `backend/route_map_analysis.py:10`                | `_device_order_key()`                          |
|  5 | `backend/credential_store.py:77`                  | `list_credentials()` (legacy)                  |
|  5 | `backend/find_leaf.py:108`                        | `device_by_ip()`                               |
|  5 | `backend/find_leaf.py:295`                        | `device_by_ip()` (second definition)           |
|  5 | `backend/nat_lookup.py:91`                        | `_format_translated_address_response()`        |
|  4 | `backend/nat_lookup.py:39`                        | `_format_first_nat_rule_response()`            |
|  1 | `backend/nat_lookup.py:93`                        | `esc()` (closure)                              |
|  1 | `backend/nat_lookup.py:138`                       | `local_name()` (closure)                       |
|  1 | `backend/route_map_analysis.py:158`               | `_norm_group()` (closure)                      |
|  1 | `backend/services/inventory_service.py:64`        | `save()` (defensive branch in service layer)   |

### Top 10 functions that need tests most urgently

Ordered by combined risk (size × business criticality × no current test):

1. **`backend/find_leaf.py::_complete_find_leaf_from_hit` (line 100, 68 missing)** — central business logic for the "Find Leaf" feature.
2. **`backend/parsers/cisco_nxos/transceiver.py::_cisco_find_tx_rx_in_dict` (line 17, 42 missing)** — DOM Tx/Rx extraction; user-facing in transceiver page.
3. **`backend/nat_lookup.py::_find_translated_ips_in_rule_config` (line 114, 31 missing)** — NAT rule resolution.
4. **`backend/find_leaf.py::_query_one_leaf_search` (line 40, 30 missing)** — per-leaf SSH/eAPI query orchestration.
5. **`backend/parsers/cisco_nxos/arp_suppression.py::parse_arp_suppression_for_ip` (line 37, 35/40 missing — 12 % covered)** — EVPN ARP-suppression lookup.
6. **`backend/parsers/cisco_nxos/arp_suppression.py::_get_arp_suppression_entries_list` (line 16, 17 missing)** — helper that feeds (5).
7. **`backend/parsers/cisco_nxos/arp.py::parse_cisco_arp_interface_for_ip` (line 59, 27/46 missing — 41 % covered)** — `show ip arp` parsing.
8. **`backend/parsers/cisco_nxos/arp.py::_parse_cisco_arp_ascii_for_ip` (line 38, 16 missing)** — ASCII fallback when JSON not available.
9. **`backend/parsers/cisco_nxos/power.py::_parse_cisco_power` (line 14, 20/33 missing — 39 % covered)** — used in dashboards.
10. **`backend/parsers/arista/arp.py::parse_arista_arp_interface_for_ip` (line 16, 17/27 missing — 37 % covered)** — Arista equivalent of (7).

Honourable mentions also worth tests soon: `route_map_analysis::build_unified_bgp_full_table` (47/63 missing, 25 %), `parsers/cisco_nxos/transceiver::_cisco_transceiver_tx_rx_from_row` (12/19 missing, 37 %), `runners/ssh_runner::run_config_lines_pty` (15/19 missing, 21 %).

---

## 5. Test inventory by type

| Type                                    | Files | Notes                                          |
|-----------------------------------------|------:|------------------------------------------------|
| Python unit tests                       | 24    | Direct module/class tests in `tests/`          |
| Python integration (Flask test client)  | 14    | `test_*_bp_phase*.py`, `test_app_factory.py`, `test_request_logging.py`, `test_logging_config.py`, `test_utils_phase2.py` |
| Security tests                          | 16    | `tests/test_security_*.py`                     |
| Parser-package unit tests               |  8    | `tests/parsers/` — common + generic + dispatcher |
| Golden / snapshot tests                 |  4    | `tests/golden/test_*_baseline.py` + `test_parsers_golden.py` (28 fixtures) |
| Playwright end-to-end specs             | 20    | `tests/e2e/specs/*.spec.ts` (Chromium + real Flask) |
| Frontend JS unit tests                  | **0** | No Jest/Vitest installed; `package.json` only ships Playwright |
| **Total Python test files**             | **66**| (56 in `tests/`, 8 in `tests/parsers/`, 4 in `tests/golden/`; minus a few `__init__.py` shims) |

Test markers from `pytest.ini`: `unit`, `integration`, `security`,
`golden`. Markers are declared but most files do not actually annotate
themselves — `pytest -m unit` runs almost nothing. (Worth fixing later.)

---

## 6. Critical gap analysis — surfaces with **zero** dedicated tests

These are ENTIRE surfaces where nothing in the test suite directly
targets the surface (coverage may exist as side effect of import or
end-to-end traversal, but no module file says "this is a test for X"):

1. **Frontend JS (`backend/static/js/app.js`, 5,253 lines, ~244 functions).** No unit-test framework. Only Playwright, which exercises the surface as a black box. Every utility function (formatters, validators, diff helpers, escape helpers, polling logic, notepad CRUD) is uncovered at the unit level.
2. **Vendor-specific parser folders (`tests/parsers/arista/`, `tests/parsers/cisco_nxos/`).** Both contain only an `__init__.py`. The 14 vendor parser modules <80 % have no per-module unit tests — their coverage today is ~71 % via golden snapshots and incidental tests in legacy coverage suites. Behaviours like "input is missing key", "input is a list of dicts not a dict", "vendor returned the ASCII variant" are mostly unexercised.
3. **`backend/find_leaf.py` business logic.** The legacy module has an integration smoke (`tests/test_legacy_coverage_find_leaf_nat.py`) but the core functions `_complete_find_leaf_from_hit`, `_query_one_leaf_search`, `_leaf_ip_from_remote`, `device_by_ip` are zero-covered.
4. **`backend/nat_lookup.py` business logic.** Same shape as (3) — the response formatters and translated-IP discovery have no targeted tests.
5. **`backend/credential_store.py` (legacy module).** `list_credentials()` and `delete_credential()` are zero-covered. The new `repositories/credential_repository.py` (92 %) is well tested but the legacy shim is not, and it's still callable via `credentials_bp` fallbacks.
6. **`backend/route_map_analysis.py` BGP table builder.** `build_unified_bgp_full_table` is 25 % covered; its helpers (`_device_order_key`, `_norm_group`) are zero-covered. This is a core data-shaping function.
7. **`backend/runners/ssh_runner.py::run_config_lines_pty`.** Interactive config-push helper. Network-touching and only 21 % covered. No mock-driven test simulates an actual paramiko `invoke_shell` channel.
8. **`backend/runners/interface_recovery.py`.** 74 % overall but `_find_interface_status_row` and friends carry several branches (multi-vendor row matching) that are unexercised.
9. **`backend/bgp_looking_glass.py` formatting helpers.** `_entry_to_text` is zero-covered; many of the "format BGP entry as plain text" branches have no test.
10. **End-to-end "negative path" coverage.** All 20 Playwright specs are happy-path / structural (`api-health`, `csp-no-inline`, `security-headers`, `home`, `navigation`). There is no Playwright spec that simulates "device unreachable", "credentials wrong", "polling timeout", or "transceiver returned malformed JSON".

---

## 7. Concrete list of new test files to create

Path-relative to repo root. Each entry includes the surface it covers
and the expected coverage uplift.

### Vendor parser unit tests (highest impact per LOC)

1. `tests/parsers/cisco_nxos/test_arp_suppression.py` — covers `parse_arp_suppression_for_ip`, `parse_arp_suppression_asci`, `_get_arp_suppression_entries_list`. Aim: lift module from 17 % → 80 %+.
2. `tests/parsers/cisco_nxos/test_transceiver.py` — covers `_cisco_find_tx_rx_in_dict`, `_cisco_transceiver_tx_rx_from_row`. Aim: 29 % → 80 %+.
3. `tests/parsers/cisco_nxos/test_arp.py` — covers `parse_cisco_arp_interface_for_ip` + `_parse_cisco_arp_ascii_for_ip` JSON / ASCII variants. Aim: 39 % → 80 %+.
4. `tests/parsers/cisco_nxos/test_power.py` — covers `_parse_cisco_power` mixed-PSU scenarios. Aim: 45 % → 85 %+.
5. `tests/parsers/cisco_nxos/test_interface_status.py` — exercise the empty / missing-key / list-not-dict shapes. Aim: 68 % → 85 %+.
6. `tests/parsers/cisco_nxos/test_interface_description.py` — empty-table, no-description, multi-line description shapes. Aim: 68 % → 90 %+.
7. `tests/parsers/cisco_nxos/test_interface_mtu.py` — empty / multi-row / non-Ethernet shapes. Aim: 73 % → 90 %+.
8. `tests/parsers/cisco_nxos/test_interface_detailed.py` — channel-group, MTU lines, port-mode branches. Aim: 74 % → 90 %+.
9. `tests/parsers/cisco_nxos/test_isis_brief.py` — adjacency states, missing-key, vlanif rows. Aim: 71 % → 90 %+.
10. `tests/parsers/cisco_nxos/test_system_uptime.py` — fill the 4 missing branches (16-19). Aim: 77 % → 100 %.
11. `tests/parsers/arista/test_arp.py` — covers `parse_arista_arp_interface_for_ip` empty/error shapes. Aim: 38 % → 90 %+.
12. `tests/parsers/arista/test_bgp.py` — covers `parse_arista_bgp_evpn_next_hop`. Aim: 42 % → 90 %+.
13. `tests/parsers/arista/test_interface_status.py` — native vs table envelopes, counters helper, missing keys. Aim: 67 % → 90 %+.
14. `tests/parsers/arista/test_cpu.py` — IDLE-only / multi-core variants. Aim: 72 % → 95 %+.
15. `tests/parsers/arista/test_disk.py` — empty filesystem / multi-mount variants. Aim: 76 % → 95 %+.
16. `tests/parsers/arista/test_uptime.py` — non-dict, missing-keys variants. Aim: 76 % → 100 %.
17. `tests/parsers/arista/test_power.py` — fill 3 missing lines. Aim: 80 % → 100 %.
18. `tests/parsers/arista/test_interface_description.py` — fill 2 lines. Aim: 87 % → 100 %.
19. `tests/parsers/arista/test_isis.py` — fill 3 lines. Aim: 87 % → 100 %.
20. `tests/parsers/arista/test_transceiver.py` — fill 2 lines. Aim: 87 % → 100 %.

### Legacy business-logic tests (medium impact, harder to write)

21. `tests/test_find_leaf_unit.py` — direct unit tests for `_complete_find_leaf_from_hit`, `_query_one_leaf_search`, `_leaf_ip_from_remote`, `device_by_ip`. Mock the runner. Target file uplift: 36 % → 70 %+.
22. `tests/test_nat_lookup_unit.py` — direct unit tests for `_find_translated_ips_in_rule_config`, `_find_nat_rule_name_in_response`, the format helpers, and the inner `esc`/`local_name` closures. Target: 37 % → 70 %+.
23. `tests/test_route_map_analysis_unit.py` — direct tests for `build_unified_bgp_full_table` (currently 25 %), `_process_bgp_cmd_list`, `_device_order_key`, `_norm_group`. Target: 51 % → 80 %+.
24. `tests/test_credential_store_legacy.py` — exercise `list_credentials` and `delete_credential`. (xfail test `test_security_legacy_credstore_deprecation` already exists; close the loop with a real test once the deprecation lands.)
25. `tests/test_bgp_looking_glass_format.py` — direct tests for `_entry_to_text` and the missing format branches in `bgp_looking_glass.py` (60+ missing branches).

### Runner / I/O tests

26. `tests/test_ssh_runner_pty.py` — mock paramiko `invoke_shell` and exercise `run_config_lines_pty` (currently 21 % covered, 15 lines missing). Use a fake channel returning a scripted byte stream.
27. `tests/test_arista_eapi_errors.py` — assert behaviour on non-200 / malformed JSON-RPC error envelopes. Closes lines 97, 100-102.
28. `tests/test_cisco_nxapi_errors.py` — same pattern for NX-API. Closes lines 62, 66, 72-74.
29. `tests/test_interface_recovery_branches.py` — multi-vendor / multi-row matching for `_find_interface_status_row` and recovery decisions.

### Frontend tests

30. **Bring in a JS unit-test framework.** Recommend Vitest (lightweight, ESM-friendly). Add:
    - `vitest.config.ts` at repo root.
    - `tests/frontend/unit/utils.spec.ts` — pure helpers: HTML escapers, formatters, diff helpers, validators in `app.js`.
    - `tests/frontend/unit/notepad.spec.ts` — notepad serialisation / dedupe.
    - `tests/frontend/unit/diff.spec.ts` — pre/post diff rendering.
    - `tests/frontend/unit/polling.spec.ts` — exponential-backoff / cancel logic.

    Refactor note: most of `app.js` is currently an IIFE — pulling out
    a handful of `export`able pure helpers into `backend/static/js/lib/`
    would make this tractable without rewriting the SPA.

31. `tests/e2e/specs/error-paths.spec.ts` — Playwright negative-path
    coverage (device unreachable, bad credentials, malformed parser
    response). Closes the gap that all 20 existing specs are happy-path.

### Marker hygiene (zero-effort win)

32. Annotate the existing test files with `@pytest.mark.unit` /
    `@pytest.mark.integration` / `@pytest.mark.security` /
    `@pytest.mark.golden` so that `make test-fast` (which runs
    `pytest -m unit`) actually selects something. Today it selects
    almost nothing.

### Estimated cumulative impact if 1-25 are completed

- Parser surface: 71.9 % → ~88 %.
- `find_leaf` / `nat_lookup` / `route_map_analysis`: ~40 % → ~75 %.
- Whole-codebase combined coverage: 78.3 % → ~88 %, comfortably above
  the 80 % policy gate.
- Branch coverage: 68.1 % → ~80 %.

---

## 8. Appendix — how this audit was generated

```bash
mkdir -p docs/test-coverage
venv/bin/pytest \
    --cov=backend \
    --cov-branch \
    --cov-report=term-missing \
    --cov-report=json:coverage_audit.json \
    -q
```

Result: `1128 passed, 9 xfailed in 77.25s` — combined coverage 78.33 %.

Per-file, per-function and per-branch breakdowns were derived from
`coverage_audit.json` using a small AST-based traversal (function
spans → executed-vs-missing line sets) and surfaced into §2 and §4
above. The xfails listed by pytest are intentional (audit-gap markers
for known-but-unfixed deprecations / disclosures); they were not
counted as failures.

The raw JSON report (`coverage_audit.json`) is left in the repo root
for follow-up tooling.
