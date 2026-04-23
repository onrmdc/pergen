# DONE — Pergen E2E & UI Test Coverage Gap Analysis

**Date:** 2026-04-22
**Auditor:** OpenCode (audit-only, zero code or package changes)
**Repo:** `/Users/asim.ceylan/pergen`
**Scope:** Browser-level (E2E), UI behaviour, and backend route → service → repository integration coverage
**Status of pytest suite:** 1128 tests passing (per user statement)

---

## 1. Executive summary

| Question | Answer |
|---|---|
| Is any browser/E2E framework installed? | **Yes — Playwright `^1.49.0` is already wired up** (`package.json`, `playwright.config.ts`, `tests/e2e/`) |
| Is the E2E suite empty? | **No** — 21 spec files / ~50 tests already exist |
| Is the suite *deep* enough for "frontend UI tests, end to end from backend to UI"? | **No.** Most specs are render-and-smoke. Only 3 cover full happy-path round-trips (notepad, credential add/delete, diff). The high-risk write paths — inventory CRUD, run/pre, run/post, diff between runs, transceiver recover, custom-command — have **zero** UI-driven coverage. |
| Total backend REST endpoints | **52** (from `@bp.route(...)` declarations across 12 blueprints) |
| Endpoints exercised by pytest blueprint tests | **~52 / 52** (all blueprints have a dedicated `test_*_bp_phaseN.py` file) |
| Endpoints exercised end-to-end by Playwright | **~16 / 52** (15 GETs in `api-routes.spec.ts` + a few POST/DELETE round-trips). **~36 endpoints are never hit through the actual UI surface.** |
| Total user journeys (SPA pages with forms/actions) | **14** (home + 13 functional pages) |
| User journeys with at least one E2E spec | **14 / 14** render checks ✅ |
| User journeys with a real **end-to-end happy-path flow** | **3 / 14** (notepad roundtrip, credential add+delete, diff render). 11 / 14 only assert "page renders" |
| Recommendation | **Keep Playwright. Expand the existing `tests/e2e/specs/` directory** with the 14 prioritized flow specs listed in §7. No new framework is needed. |

---

## 2. Inventory of existing test infrastructure

### 2.1 Browser / E2E framework
- **Playwright** is installed and configured.
  - `package.json:11-14` — `@playwright/test ^1.49.0`, `typescript ^5.4.0`
  - `playwright.config.ts:1-51` — testDir `./tests/e2e/specs`, baseURL `http://127.0.0.1:5000`, auto-starts Flask via `./run.sh`, JUnit + HTML reporters, screenshots on failure, video on retry.
  - `node_modules/` exists, so install is already done.
  - npm scripts: `npm run e2e`, `npm run e2e:headed`, `npm run e2e:report`.
- **No** Cypress, Selenium, WebdriverIO, Puppeteer, or any other browser framework present.
- A Page Object skeleton exists: `tests/e2e/pages/AppShell.ts` (69 lines — only the global hash router shell; no per-page POMs yet).

### 2.2 Frontend unit tests
- **None.** Glob for `**/*.test.js` and `**/*.spec.js` returned zero files.
- `backend/static/js/app.js` is **5253 lines of plain JS** with no module boundary, no bundler, and no harness for unit testing functions in isolation. UI behaviour is currently only assertable through Playwright.

### 2.3 Backend integration tests (Flask test client)
The pytest suite uses the real `create_app("testing")` factory through `tests/conftest.py:96-146`, with isolated tmp instance dir + mock inventory CSV. This exercises real route → service → repository chains. Files (one per blueprint):

| Blueprint file | Test file |
|---|---|
| `bgp_bp.py` | `test_bgp_bp_phase7.py`, `test_bgp_looking_glass.py` |
| `commands_bp.py` | `test_commands_bp_phase4.py` |
| `credentials_bp.py` | `test_credentials_bp_phase6.py` |
| `device_commands_bp.py` | `test_device_commands_bp_phase10.py` (13 tests) |
| `health_bp.py` | covered by `test_app_factory.py` + `test_security_health_disclosure.py` |
| `inventory_bp.py` | `test_inventory_writes_phase3.py` (19 tests) + `test_inventory_repository.py` |
| `network_lookup_bp.py` | `test_network_lookup_bp_phase8.py` |
| `network_ops_bp.py` | `test_network_ops_bp_phase5.py` |
| `notepad_bp.py` | `test_phase9_blueprints.py` + `test_notepad_repository.py` |
| `reports_bp.py` | `test_runs_reports_bp_phase11.py` (20 tests) + `test_report_repository.py` |
| `runs_bp.py` | `test_runs_reports_bp_phase11.py` |
| `transceiver_bp.py` | `test_transceiver_bp_phase9.py` (separate file beyond the listed phase set) |

Backend-side, every blueprint has a dedicated test file. Coverage at the route-handler level looks comprehensive (1128 tests, `cov-new` gate held at 85% on the OOD layer per `Makefile:46-58`).

### 2.4 Test fixtures
- `tests/fixtures/golden/` — 28 JSON snapshot files for parser determinism (Arista + Cisco show-command outputs, dispatcher decisions).
- `tests/golden/` — `_snapshot.py` helper + 4 baseline pytest files (`test_inventory_baseline.py`, `test_parsers_golden.py`, `test_routes_baseline.py`, `test_runners_baseline.py`).
- `tests/parsers/` — table-driven parser tests for arista / cisco_nxos / common / generic, plus `test_dispatcher.py`.
- `tests/conftest.py` — provides `flask_app`, `client`, `isolated_instance_dir`, `mock_inventory_csv`, stable `SECRET_KEY`. Forces module re-import so env-var-driven config is honoured between tests.

### 2.5 Existing Playwright specs (`tests/e2e/specs/`)
21 spec files:

| Spec | Coverage type | Depth |
|---|---|---|
| `api-health.spec.ts` | Backend smoke | 2 health endpoints, full payload assertion |
| `api-routes.spec.ts` | Backend smoke | 15 GET endpoints — status `< 500` only |
| `bgp.spec.ts` | UI render | input + button visible, empty-lookup keeps page alive |
| `credential.spec.ts` | UI render | form + method-switch field swap |
| `csp-no-inline.spec.ts` | Security regression | zero CSP violations on home |
| `diff.spec.ts` | UI render + identical-text path | 2 tests |
| `findleaf.spec.ts` | UI render | 2 tests, no real device call |
| `flow-credential-add.spec.ts` | **Real round-trip** | create → list → delete via UI + intercepted POST/DELETE |
| `flow-diff-checker.spec.ts` | **Real round-trip** | paste two configs, assert +/- markers |
| `flow-notepad-roundtrip.spec.ts` | **Real round-trip** | type → blur-save → reload → assert persisted |
| `home.spec.ts` | Navigation | 12 home cards visible + click navigates |
| `nat.spec.ts` | UI render + bad-input | 2 tests |
| `navigation.spec.ts` | Hash router | 14 hashes × activate-page assertion |
| `notepad.spec.ts` | UI render | 2 tests |
| `prepost.spec.ts` | UI render + fabric dropdown populated | 2 tests |
| `restapi.spec.ts` | UI render + example button populates input | 2 tests |
| `routemap.spec.ts` | UI render + scope dropdown values | 2 tests |
| `security-headers.spec.ts` | Security smoke | 5 required headers, plus same on `/api/health` |
| `subnet.spec.ts` | UI render + Update button renders table | 2 tests |
| `transceiver.spec.ts` | UI render + recover button hidden until errors | 2 tests |

**No spec for the inventory page** (`#page-inventory` exists in `index.html:1088` with Add/Edit/Import/Export buttons + modal CRUD, no Playwright file).

---

## 3. Backend endpoint → test mapping

All 52 endpoints, grouped by blueprint, with backend-pytest coverage and Playwright (true UI/HTTP) coverage.

Legend: `pt` = pytest test-client coverage, `e2e-api` = Playwright `request.*` smoke, `e2e-ui` = Playwright page-driven flow.

### inventory_bp.py (12 endpoints)
| Endpoint | Method | pt | e2e-api | e2e-ui |
|---|---|---|---|---|
| `/api/fabrics` | GET | ✅ | ✅ | ✅ (prepost dropdown) |
| `/api/sites` | GET | ✅ | ✅ | — |
| `/api/halls` | GET | ✅ | ✅ | — |
| `/api/roles` | GET | ✅ | ✅ | — |
| `/api/devices` | GET | ✅ | ✅ | — |
| `/api/devices-arista` | GET | ✅ | ✅ | — |
| `/api/devices-by-tag` | GET | ✅ | — | — |
| `/api/inventory` | GET | ✅ | ✅ | — |
| `/api/inventory/device` | POST | ✅ | — | **❌ no UI flow** |
| `/api/inventory/device` | PUT | ✅ | — | **❌ no UI flow** |
| `/api/inventory/device` | DELETE | ✅ | — | **❌ no UI flow** |
| `/api/inventory/import` | POST | ✅ | — | **❌ no UI flow** |

### credentials_bp.py (4 endpoints)
| Endpoint | Method | pt | e2e-api | e2e-ui |
|---|---|---|---|---|
| `/api/credentials` | GET | ✅ | ✅ | ✅ |
| `/api/credentials` | POST | ✅ | — | ✅ (`flow-credential-add`) |
| `/api/credentials/<name>` | DELETE | ✅ | — | ✅ |
| `/api/credentials/<name>/validate` | POST | ✅ | — | **❌ no UI flow** |

### runs_bp.py (8 endpoints — highest-risk, touches real devices)
| Endpoint | Method | pt | e2e-api | e2e-ui |
|---|---|---|---|---|
| `/api/run/device` | POST | ✅ | — | **❌** |
| `/api/run/pre` | POST | ✅ | — | **❌** |
| `/api/run/pre/create` | POST | ✅ | — | **❌** |
| `/api/run/pre/restore` | POST | ✅ | — | **❌** |
| `/api/run/post` | POST | ✅ | — | **❌** |
| `/api/run/post/complete` | POST | ✅ | — | **❌** |
| `/api/diff` | POST | ✅ | — | **❌** (separate from on-page text diff) |
| `/api/run/result/<run_id>` | GET | ✅ | — | **❌** |

### device_commands_bp.py (4 endpoints)
| Endpoint | Method | pt | e2e-api | e2e-ui |
|---|---|---|---|---|
| `/api/arista/run-cmds` | POST | ✅ | — | **❌** |
| `/api/router-devices` | GET | ✅ | ✅ | — |
| `/api/route-map/run` | POST | ✅ | — | **❌** |
| `/api/custom-command` | POST | ✅ | — | **❌** |

### network_lookup_bp.py (3 endpoints)
| Endpoint | Method | pt | e2e-api | e2e-ui |
|---|---|---|---|---|
| `/api/find-leaf` | POST | ✅ | — | **❌** (UI only asserts "page alive") |
| `/api/find-leaf-check-device` | POST | ✅ | — | **❌** |
| `/api/nat-lookup` | POST | ✅ | — | **❌** (UI only asserts "page alive") |

### transceiver_bp.py (3 endpoints)
| Endpoint | Method | pt | e2e-api | e2e-ui |
|---|---|---|---|---|
| `/api/transceiver` | POST | ✅ | — | **❌** |
| `/api/transceiver/recover` | POST | ✅ | — | **❌** |
| `/api/transceiver/clear-counters` | POST | ✅ | — | **❌** |

### bgp_bp.py (8 endpoints)
| Endpoint | Method | pt | e2e-api | e2e-ui |
|---|---|---|---|---|
| `/api/bgp/status` | GET | ✅ | — | **❌** |
| `/api/bgp/history` | GET | ✅ | — | **❌** |
| `/api/bgp/visibility` | GET | ✅ | — | **❌** |
| `/api/bgp/looking-glass` | GET | ✅ | — | **❌** |
| `/api/bgp/bgplay` | GET | ✅ | — | **❌** |
| `/api/bgp/as-info` | GET | ✅ | — | **❌** |
| `/api/bgp/announced-prefixes` | GET | ✅ | — | **❌** |
| `/api/bgp/wan-rtr-match` | GET | ✅ | — | **❌** |

### reports_bp.py (3 endpoints)
| Endpoint | Method | pt | e2e-api | e2e-ui |
|---|---|---|---|---|
| `/api/reports` | GET | ✅ | ✅ | — |
| `/api/reports/<run_id>` | GET | ✅ | — | **❌** |
| `/api/reports/<run_id>` | DELETE | ✅ | — | **❌** |

### commands_bp.py (3 endpoints)
| Endpoint | Method | pt | e2e-api | e2e-ui |
|---|---|---|---|---|
| `/api/commands` | GET | ✅ | ✅ | — |
| `/api/parsers/fields` | GET | ✅ | ✅ | — |
| `/api/parsers/<command_id>` | GET | ✅ | — | — |

### notepad_bp.py (2 endpoints)
| Endpoint | Method | pt | e2e-api | e2e-ui |
|---|---|---|---|---|
| `/api/notepad` | GET | ✅ | ✅ | ✅ |
| `/api/notepad` | PUT/POST | ✅ | — | ✅ (`flow-notepad-roundtrip`) |

### network_ops_bp.py (2 endpoints)
| Endpoint | Method | pt | e2e-api | e2e-ui |
|---|---|---|---|---|
| `/api/ping` | POST | ✅ | — | **❌** |
| `/` (SPA index) | GET | ✅ | ✅ (security-headers) | ✅ (every nav test) |

### health_bp.py (2 endpoints)
| Endpoint | Method | pt | e2e-api | e2e-ui |
|---|---|---|---|---|
| `/api/v2/health` | GET | ✅ | ✅ | — |
| `/api/health` | GET | ✅ | ✅ | — |

**Endpoint coverage totals**
- pytest (route → service → repo): 52 / 52 ✅
- Playwright `request.get` smoke: 16 / 52
- Playwright UI-driven (real button click → real fetch): **5 / 52** (`/api/credentials` POST + DELETE, `/api/notepad` GET + PUT, plus implicit GETs during page loads). The diff page does not call `/api/diff` — it diffs locally in JS.

---

## 4. SPA user journeys → E2E mapping

User journeys identified from `backend/static/index.html` (`<section id="page-…">` declarations, lines 624–1306) and event handler inventory in `backend/static/js/app.js` (166 `addEventListener` matches found).

| # | Journey (page hash) | Event handlers in app.js | E2E render? | E2E end-to-end flow? |
|---|---|---|---|---|
| 1 | `#home` (12 cards) | card click → hash nav | ✅ `home.spec.ts` | ✅ click navigates |
| 2 | `#prepost` (Pre/Post Check, run config snapshots, restore, diff between runs) | `runBtn`, `runPostBtn`, `showRunDiffSelect`, fabric/site/role/hall cascading dropdowns, `selectAll`/`selectNone`, `pingBtn`, gear popup | ✅ render + dropdown populated | **❌ none** — biggest gap. No flow that runs a (mocked) `/api/run/pre` → asserts table renders |
| 3 | `#nat` (NAT Lookup) | `natLookupBtn` → POST `/api/nat-lookup` | ✅ render + bad-input | **❌** no real lookup with mocked backend |
| 4 | `#findleaf` (Find Leaf) | `findLeafBtn` → POST `/api/find-leaf` then `/api/find-leaf-check-device` | ✅ render + empty-input | **❌** no leaf-found flow |
| 5 | `#bgp` (BGP / Looking Glass / favourites / BGPlay) | `bgpLookupBtn`, fav add/remove, BGPlay prev/next, AS tooltips, prefix link clicks | ✅ render + empty-lookup | **❌** no real lookup, favourites not exercised |
| 6 | `#restapi` (REST API console) | `restapiSubmitBtn`, 3 example buttons, fabric/site/role cascade | ✅ render + example button populates | **❌** no submit→response flow |
| 7 | `#transceiver` (Transceiver check + recover + clear counters) | `transceiverRunBtn`, `recoverAllBtn`, per-row recover buttons, column toggle, sort + filter, fabric cascade | ✅ render + recover hidden | **❌** no run/recover/clear-counters flow — error rows path is untested |
| 8 | `#credential` (credentials CRUD) | `credSubmit`, method swap, `cred-delete`, `cred-validate` | ✅ render + method swap | ✅ add+delete (`flow-credential-add`); **❌ validate button untested** |
| 9 | `#routemap` (DCI/WAN routers, route-map compare, prefix search) | `routerCompareBtn`, `routerPrefixSearchBtn`, scope cascade, sel-all/none, column toggle, sort+filter | ✅ render + scope options | **❌** no compare flow, no prefix search flow |
| 10 | `#inventory` (CSV-backed inventory CRUD: Add, Edit, Import, Export, modal save/delete, column toggle) | `invAddBtn`, `invEditBtn`, `invImportBtn`, `invExportBtn`, `invModalSave`, `invModalDelete`, `invFileInput`, fabric/site/hall/role filters | **❌ NO SPEC AT ALL** | **❌** |
| 11 | `#notepad` (live shared notepad) | `notepadText` input/blur/scroll, `notepadUserName` change/input | ✅ render + load | ✅ (`flow-notepad-roundtrip`) |
| 12 | `#diff` (text diff checker, scroll-to-add, scroll-to-remove) | `diffCheckBtn`, add/remove navigation arrows | ✅ render + empty diff | ✅ (`flow-diff-checker`) — but add/remove navigation buttons untested |
| 13 | `#subnet` (Subnet divider) | `subnetUpdateBtn`, `subnetResetBtn` | ✅ render + Update | **❌** Reset, mask change, multi-row split untested |
| 14 | `#help` | static page | ✅ via navigation.spec | n/a |

Plus three system-wide concerns covered by Playwright:

| # | Concern | Spec |
|---|---|---|
| A | CSP — no inline script violations | ✅ `csp-no-inline.spec.ts` |
| B | Security headers on HTML + API | ✅ `security-headers.spec.ts` |
| C | Hash router activates exactly one section | ✅ `navigation.spec.ts` |

**Journey coverage totals**
- Render checks: 13 / 14 (inventory missing).
- True end-to-end happy-path flows: **3 / 14** (notepad, credential, diff text).

---

## 5. Critical gaps (ranked by risk)

These are paths that touch real devices, mutate persisted state, or are user-visible workflows where a regression would silently break operator work.

### 5.1 P0 — touches real devices or mutates server state, no UI coverage
1. **Pre/Post check run flow** (`#prepost` → POST `/api/run/pre` → render results table → POST `/api/run/post` → POST `/api/diff` → reports listed). The whole point of the tool. Needs a flow spec with the runner mocked at the service boundary so we can assert table render, "show diff" select, and result persistence without hitting real SSH.
2. **Inventory CRUD** (`#inventory` Add/Edit/Delete/Import/Export). No spec exists at all. Mutates `inventory.csv`. Needs add → row appears → edit → save → delete → row gone, plus CSV import and export.
3. **Transceiver run + recover + clear-counters** (`#transceiver`). Recovery touches devices; the recover-all and per-row recover buttons are completely untested through the UI.
4. **Custom command runner** (`#prepost` `phase=custom` + `#page-custom`) → POST `/api/custom-command`. Sends arbitrary commands to selected devices; no UI flow.
5. **Route-map compare** (`#routemap` → POST `/api/route-map/run` for two device sets, render compare table, prefix search). No flow spec.
6. **Find-leaf real lookup** (`#findleaf` with a valid IP → POST `/api/find-leaf` → POST `/api/find-leaf-check-device`). Currently only "page-alive" assertion.
7. **NAT lookup real flow** (`#nat` with a valid src/dst → POST `/api/nat-lookup` → results render). Currently only bad-input assertion.

### 5.2 P1 — high-traffic read paths with no UI assertion
8. **BGP lookup** (`#bgp`) — 8 BGP endpoints, all GET, all unhit through the UI. At minimum: enter resource → click Lookup → status reflects "ok"/"error", history populates.
9. **BGP favourites** — add/remove buttons + per-fav row clicks. Local-storage persistence path.
10. **REST API console** (`#restapi`) — submit a request and assert response renders.
11. **Credential validate** (`/api/credentials/<name>/validate`). No UI flow.
12. **Diff add/remove navigation arrows** on `#diff`. The spec asserts the diff renders but never clicks the "next add" / "next remove" navigation buttons.
13. **Subnet calculator multi-mask split + Reset**. Only `/24` default + Update is exercised.

### 5.3 P2 — quality/observability nice-to-haves
14. **Empty-state coverage** — every list-rendering page (transceiver table, route-map table, custom-command table, inventory table) should be exercised with zero rows to lock the empty-state UI.
15. **Header progress popup + command-logs popup + success/warn/fail toasts** (`app.js:87-231`). Shared global UX widgets, no spec.
16. **Notepad — name validation**. Saving with no name should be refused; not tested.
17. **Visual regression / screenshot snapshots** — none. With 5253 lines of plain-JS UI and no bundler boundary, a small style or markup regression is invisible until a human notices. Adding `await expect(page).toHaveScreenshot()` on the home and a couple of complex tables would catch this cheaply.

### 5.4 No coverage gap — already strong
- Backend route handlers (52/52 pytest).
- Parsers (golden snapshots in `tests/fixtures/golden/`).
- Encryption / credential store / security audit batches (multiple `test_security_*` files).
- CSP and security headers (`csp-no-inline.spec.ts`, `security-headers.spec.ts`).

---

## 6. Framework recommendation

**Keep Playwright. Do not introduce a second framework.**

Reasons:
1. Already installed and configured (`playwright.config.ts`, `node_modules/`).
2. It already auto-starts the Flask app via `webServer.command = "./run.sh"` and reuses an existing dev server — zero ceremony for local runs.
3. AGENTS.md already lists Playwright as the project E2E tool (`e2e-runner` agent + `e2e-testing` skill).
4. The existing 21 specs follow a consistent style with a Page Object stub (`AppShell.ts`) — the pattern is already in place.
5. Playwright supports both UI flows (`page.locator(...).click()`) **and** API testing (`request.get(...)` in `api-routes.spec.ts`) in one harness, so the new POST/PUT/DELETE smoke checks land in the same project.

What's missing in the harness itself (cheap follow-up, not blocking):
- A **per-page Page Object** for each large journey (currently only `AppShell.ts`). With 14 journeys, a `pages/` directory of small POMs would deduplicate locators.
- A **test fixture for an isolated backend** — the current `webServer` reuses dev-mode state, so any flow that mutates inventory/credentials/notepad pollutes the operator's real `instance/` dir. Recommend either:
  - Pass `PERGEN_INSTANCE_DIR=$(mktemp -d)` and `PERGEN_INVENTORY_PATH=tests/fixtures/inventory_e2e.csv` via the `webServer.env` block, or
  - Add a tiny `/api/test/reset` endpoint gated on `FLASK_CONFIG=testing` for the E2E suite to call in `beforeEach`.
- **Network mocking** for device-touching endpoints — `page.route("**/api/run/pre", route => route.fulfill({...}))` lets us drive run flows without real SSH. Already a Playwright built-in.

---

## 7. Prioritised list of E2E + UI test files to create

All paths are relative to repo root. Files use the existing `tests/e2e/specs/` + `tests/e2e/pages/` convention.

### P0 — add first (mutates state or simulates real device traffic)

| # | File | Journey + assertion |
|---|---|---|
| 1 | `tests/e2e/specs/flow-prepost-run.spec.ts` | `#prepost`: select fabric/site/role → tick a device → click Run → mock `/api/run/pre` response → assert results table renders rows + "Show diff" select appears + report listed in `savedReportsDetails`. Mirror for `phase=post` and `/api/diff`. |
| 2 | `tests/e2e/specs/flow-inventory-crud.spec.ts` | `#inventory`: open Add modal → fill hostname/ip/fabric/etc → Save → row appears → Edit → change role → Save → row updated → Delete → row gone. Use isolated tmp inventory CSV. |
| 3 | `tests/e2e/specs/flow-inventory-import-export.spec.ts` | `#inventory`: click Export → assert CSV download triggered + content. Click Import → upload tmp CSV via `setInputFiles` → assert new rows render. |
| 4 | `tests/e2e/specs/flow-transceiver-run.spec.ts` | `#transceiver`: select scope → Run → mock `/api/transceiver` to return one OK + one error row → assert main table + error table both render → click Recover all → mock `/api/transceiver/recover` → assert success toast. |
| 5 | `tests/e2e/specs/flow-transceiver-clear-counters.spec.ts` | Per-row "clear counters" path → mock `/api/transceiver/clear-counters` → assert counters reset in row. |
| 6 | `tests/e2e/specs/flow-route-map-compare.spec.ts` | `#routemap`: pick scope → check 2 devices → Compare → mock `/api/route-map/run` → assert compare table renders + sort + filter + column toggle. Then exercise prefix search → POST `/api/bgp/wan-rtr-match`. |
| 7 | `tests/e2e/specs/flow-custom-command.spec.ts` | `#prepost` with `phase=custom`: enter command → tick devices → Run → mock `/api/custom-command` → assert custom-command table renders, sort/filter/column-toggle work. |
| 8 | `tests/e2e/specs/flow-find-leaf-success.spec.ts` | `#findleaf`: enter `10.0.0.1` (matches `mock_inventory_csv`'s `leaf-01`) → mock `/api/find-leaf` + `/api/find-leaf-check-device` → assert leaf is reported and on-device check rendered. |
| 9 | `tests/e2e/specs/flow-nat-lookup-success.spec.ts` | `#nat`: enter valid src + default dest → mock `/api/nat-lookup` → assert results render. |

### P1 — add next (read paths, validate paths, missing widgets)

| # | File | Journey + assertion |
|---|---|---|
| 10 | `tests/e2e/specs/flow-bgp-lookup.spec.ts` | `#bgp`: enter prefix → click Lookup → mock all 8 BGP GETs → assert status, AS path, history, looking-glass, BGPlay panels all render. |
| 11 | `tests/e2e/specs/flow-bgp-favourites.spec.ts` | `#bgp`: lookup → Add fav → reload → fav still listed → click fav chip → reruns lookup → click X → fav removed. |
| 12 | `tests/e2e/specs/flow-restapi-submit.spec.ts` | `#restapi`: pick device → click "version" example → Submit → mock `/api/arista/run-cmds` → assert response rendered. |
| 13 | `tests/e2e/specs/flow-credential-validate.spec.ts` | `#credential`: existing row → click Validate → mock `/api/credentials/<n>/validate` → assert success/failure indicator. |
| 14 | `tests/e2e/specs/flow-diff-navigation.spec.ts` | `#diff`: paste long configs → click "next add" / "next remove" arrow buttons → assert scroll position changed. |
| 15 | `tests/e2e/specs/flow-subnet-split.spec.ts` | `#subnet`: change mask `/16 → /20` → Update → assert N rows → Reset → defaults restored. |
| 16 | `tests/e2e/specs/api-routes-mutating.spec.ts` | Companion to `api-routes.spec.ts` — direct `request.post/put/delete` smoke for every mutating endpoint with a minimal valid payload, asserting `< 500`. |

### P2 — quality/observability (do once P0/P1 land)

| # | File | Journey + assertion |
|---|---|---|
| 17 | `tests/e2e/specs/empty-states.spec.ts` | For each table-rendering page, mock the endpoint to return `[]` → assert empty-state copy/markup. |
| 18 | `tests/e2e/specs/global-widgets.spec.ts` | Header progress popup, command-logs popup, success/warn/fail toasts (`app.js:87-231`) — trigger each via injected event and assert open/close behaviour. |
| 19 | `tests/e2e/specs/notepad-validation.spec.ts` | `#notepad`: try to save with empty name → assert refused/no PUT fires. |
| 20 | `tests/e2e/specs/visual-snapshots.spec.ts` | Screenshot baseline for `#home`, `#prepost` results table, `#routemap` compare table, `#transceiver` results table. Use `expect(page).toHaveScreenshot()`. |

### Supporting Page Objects (refactor as the spec count grows)
- `tests/e2e/pages/PrePostPage.ts`
- `tests/e2e/pages/InventoryPage.ts`
- `tests/e2e/pages/TransceiverPage.ts`
- `tests/e2e/pages/RouteMapPage.ts`
- `tests/e2e/pages/CredentialPage.ts`
- `tests/e2e/pages/BgpPage.ts`

### Suggested harness improvement (one PR before the P0 batch lands)
- Add `tests/e2e/fixtures/test-server.ts` that wires `webServer.env` to point at a per-run tmp `PERGEN_INSTANCE_DIR` + a fixture inventory CSV, so flow specs never touch the operator's real `instance/`. Optionally add a `beforeEach` `/api/test/reset` hook gated on `FLASK_CONFIG=testing`.

---

## 8. Deliverables (summary table for the user)

| Item | Value |
|---|---|
| Report path | `docs/test-coverage/e2e_gap_analysis_2026-04-22.md` |
| Browser/E2E framework installed? | **Yes — Playwright `^1.49.0`** (`package.json`, `playwright.config.ts`, `node_modules/`, 21 spec files in `tests/e2e/specs/`) |
| Endpoints total / pytest-tested / Playwright-UI-tested | **52 / 52 / 5** (plus 16 via direct API smoke) |
| User journeys total / render-tested / true-E2E-tested | **14 / 13 / 3** (`#inventory` has zero coverage) |
| Recommendation | **Stay on Playwright.** Add the 9 P0 flow specs in §7 first (highest risk: prepost run, inventory CRUD, transceiver, route-map compare, custom-command, find-leaf, nat). Then 7 P1 specs, then 4 P2 quality specs. Add the harness isolation fixture before the first mutating flow lands. |

No code or packages were modified during this audit.

---

## Wave-7 follow-up (2026-04-23)

The wave-2 P0 list landed in wave-3 (15 new flow specs, per the wave-4
audit). The wave-7 audit
(`docs/test-coverage/DONE_e2e_gap_analysis_2026-04-23-wave7.md`) measures:

- Spec files: **43** (+5 from wave-6: auth login + XSS regression + 3 wave-5
  P0 flows).
- Tests: **100 / 100 green** (was 88 / 12 failing at wave-6 close; the
  12 failures were all spec-side selector/dialog brittleness from the
  wave-6 SPA refactor and were fixed in wave-7 with no SPA changes).
- SPA hash routes covered: **13 / 14** (`#help` still uncovered).
- Endpoints UI-tested: **34 / 53** (unchanged from wave-4).

Wave-7 itself added zero new specs — the contribution was suite
stability. See the wave-7 doc for the per-spec fix list (12 specs).

— end of follow-up note —
