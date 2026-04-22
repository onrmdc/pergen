# DONE — E2E + Frontend Test Coverage — Wave-4 Gap Analysis

**Date:** 2026-04-22
**Scope:** Playwright E2E (`tests/e2e/specs/`) + Vitest unit (`tests/frontend/unit/`)
**Audit type:** Read-only inventory and gap detection — no code changes.

---

## 1. Headline numbers

| Metric                                            | Count      |
| ------------------------------------------------- | ---------- |
| Playwright spec files                             | **38**     |
| Playwright tests (verified via `--list`)          | **85**     |
| Vitest spec files                                 | **2**      |
| Vitest tests                                      | **37**     |
| Backend `@bp.route` declarations                  | **53**     |
| Endpoints tested by Playwright (UI mock + smoke)  | **42 / 53** (79.2%) |
| SPA hash routes (user journeys, top-nav)          | **14**     |
| SPA hash routes with at least one E2E spec        | **13 / 14** (93%) — `#help` page uncovered |
| Helpers in `backend/static/js/lib/*.js`           | **10**     |
| Helpers covered by Vitest                         | **10 / 10** (100%) |

Wave-3 added the 15 specs the user listed; `npx playwright test --list` confirms `Total: 85 tests in 38 files`.

---

## 2. Endpoint × Spec coverage matrix

Source-of-truth: `grep -rn '@.*_bp\.\(route\|get\|post\|put\|delete\|patch\)(' backend/blueprints/*.py` → 53 routes.

Legend:
- ✅ **UI** — exercised through a real SPA flow with `page.route()` mocks
- 🟡 **Smoke** — hit only by `tests/e2e/specs/api-routes.spec.ts` or `flow-mutating-api-smoke.spec.ts` (status-code-only assertion)
- ❌ — no Playwright coverage at all

### `bgp_bp.py` (8 endpoints)

| Method | Path                                | Cov | Spec |
| ------ | ----------------------------------- | --- | ---- |
| GET    | `/api/bgp/status`                   | ✅  | `flow-bgp-lookup`, `flow-bgp-favourites` |
| GET    | `/api/bgp/history`                  | ✅  | `flow-bgp-lookup`, `flow-bgp-favourites` |
| GET    | `/api/bgp/visibility`               | ✅  | `flow-bgp-lookup`, `flow-bgp-favourites` |
| GET    | `/api/bgp/looking-glass`            | ✅  | `flow-bgp-lookup`, `flow-bgp-favourites` |
| GET    | `/api/bgp/bgplay`                   | ✅  | `flow-bgp-lookup`, `flow-bgp-favourites` |
| GET    | `/api/bgp/as-info`                  | ❌  | — |
| GET    | `/api/bgp/announced-prefixes`       | ❌  | — |
| GET    | `/api/bgp/wan-rtr-match`            | ✅  | `flow-bgp-lookup`, `flow-bgp-favourites` |

### `commands_bp.py` (3)

| Method | Path                          | Cov | Spec |
| ------ | ----------------------------- | --- | ---- |
| GET    | `/api/commands`               | 🟡  | `api-routes` |
| GET    | `/api/parsers/fields`         | 🟡  | `api-routes` |
| GET    | `/api/parsers/<command_id>`   | ❌  | — |

### `credentials_bp.py` (4)

| Method | Path                                   | Cov | Spec |
| ------ | -------------------------------------- | --- | ---- |
| GET    | `/api/credentials`                     | ✅  | `flow-credential-add`, `flow-credential-validate`, `credential` |
| POST   | `/api/credentials`                     | 🟡  | `flow-mutating-api-smoke` |
| DELETE | `/api/credentials/<name>`              | 🟡  | `flow-mutating-api-smoke` |
| POST   | `/api/credentials/<name>/validate`     | ✅  | `flow-credential-validate` |

### `device_commands_bp.py` (4)

| Method | Path                       | Cov | Spec |
| ------ | -------------------------- | --- | ---- |
| POST   | `/api/arista/run-cmds`     | ✅  | `flow-restapi-submit`, `flow-custom-command` |
| GET    | `/api/router-devices`      | ✅  | `flow-route-map-compare`, `api-routes` |
| POST   | `/api/route-map/run`       | ✅  | `flow-route-map-compare` |
| POST   | `/api/custom-command`      | ❌  | **see Finding #3 below** |

### `health_bp.py` (2)

| Method | Path                | Cov | Spec |
| ------ | ------------------- | --- | ---- |
| GET    | `/api/v2/health`    | ✅  | `api-health`, `api-routes` |
| GET    | `/api/health`       | ✅  | `api-health`, `api-routes` |

### `inventory_bp.py` (11)

| Method | Path                              | Cov | Spec |
| ------ | --------------------------------- | --- | ---- |
| GET    | `/api/fabrics`                    | ✅  | `flow-prepost-run`, `flow-restapi-submit`, etc. |
| GET    | `/api/sites`                      | ✅  | `flow-prepost-run`, `flow-restapi-submit`, etc. |
| GET    | `/api/halls`                      | ✅  | multiple flow specs |
| GET    | `/api/roles`                      | ✅  | multiple flow specs |
| GET    | `/api/devices`                    | ✅  | `flow-prepost-run`, `flow-restapi-submit` |
| GET    | `/api/devices-arista`             | ✅  | `flow-restapi-submit`, `api-routes` |
| GET    | `/api/devices-by-tag`             | ✅  | `flow-find-leaf-success`, `flow-nat-lookup-success` |
| GET    | `/api/inventory`                  | ✅  | `flow-inventory-crud`, `flow-inventory-import-export` |
| POST   | `/api/inventory/device`           | ✅  | `flow-inventory-crud` |
| PUT    | `/api/inventory/device`           | ✅  | `flow-inventory-crud` |
| DELETE | `/api/inventory/device`           | ✅  | `flow-inventory-crud` |
| POST   | `/api/inventory/import`           | ✅  | `flow-inventory-import-export` (+ smoke) |

### `network_lookup_bp.py` (3)

| Method | Path                                | Cov | Spec |
| ------ | ----------------------------------- | --- | ---- |
| POST   | `/api/find-leaf`                    | ✅  | `flow-error-paths` (5xx path), `findleaf` |
| POST   | `/api/find-leaf-check-device`       | ✅  | `flow-find-leaf-success`, `flow-nat-lookup-success`, `flow-xss-defence` |
| POST   | `/api/nat-lookup`                   | ✅  | `flow-nat-lookup-success` |

### `network_ops_bp.py` (2)

| Method | Path        | Cov | Spec |
| ------ | ----------- | --- | ---- |
| POST   | `/api/ping` | ✅  | `flow-prepost-run`, `flow-restapi-submit`, `flow-transceiver-run` |
| GET    | `/`         | ✅  | `home`, `navigation` (every spec hits the SPA shell) |

### `notepad_bp.py` (2)

| Method   | Path            | Cov | Spec |
| -------- | --------------- | --- | ---- |
| GET      | `/api/notepad`  | ✅  | `notepad`, `flow-notepad-roundtrip` |
| POST/PUT | `/api/notepad`  | 🟡  | `flow-mutating-api-smoke` (PUT) — POST never tested |

### `reports_bp.py` (4)

| Method | Path                              | Cov | Spec |
| ------ | --------------------------------- | --- | ---- |
| GET    | `/api/reports`                    | 🟡  | `api-routes` |
| GET    | `/api/reports/<run_id>`           | ❌  | — |
| POST   | `/api/reports/<run_id>/restore`   | ❌  | — |
| DELETE | `/api/reports/<run_id>`           | ❌  | — |

### `runs_bp.py` (8)

| Method | Path                              | Cov | Spec |
| ------ | --------------------------------- | --- | ---- |
| POST   | `/api/run/device`                 | ✅  | `flow-prepost-run` |
| POST   | `/api/run/pre`                    | ❌  | — |
| POST   | `/api/run/pre/create`             | ✅  | `flow-prepost-run` |
| POST   | `/api/run/pre/restore`            | ❌  | — |
| POST   | `/api/run/post`                   | ❌  | — |
| POST   | `/api/run/post/complete`          | ❌  | — |
| POST   | `/api/diff`                       | ✅  | `flow-diff-checker`, `flow-diff-navigation`, `flow-error-paths`, `flow-mutating-api-smoke`, `diff` |
| GET    | `/api/run/result/<run_id>`        | ❌  | — |

### `transceiver_bp.py` (3)

| Method | Path                                | Cov | Spec |
| ------ | ----------------------------------- | --- | ---- |
| POST   | `/api/transceiver`                  | ✅  | `flow-transceiver-run`, `flow-transceiver-clear-counters` |
| POST   | `/api/transceiver/recover`          | ❌  | — |
| POST   | `/api/transceiver/clear-counters`   | ✅  | `flow-transceiver-clear-counters` |

### Endpoint-coverage summary

- **Total:** 53 endpoints
- **Tested (UI or smoke):** 42
- **Untested:** 11 (see §4)

---

## 3. SPA user-journey coverage

Source-of-truth: `grep -oE 'href="#[a-z_-]+"' backend/static/index.html` → 14 routes.

| Hash       | Tested? | Spec(s) |
| ---------- | ------- | ------- |
| `#home`        | ✅ | `home`, `navigation`, `csp-no-inline` |
| `#prepost`     | ✅ | `prepost`, `flow-prepost-run` |
| `#transceiver` | ✅ | `transceiver`, `flow-transceiver-run`, `flow-transceiver-clear-counters` |
| `#restapi`     | ✅ | `restapi`, `flow-restapi-submit`, `flow-custom-command` |
| `#findleaf`    | ✅ | `findleaf`, `flow-find-leaf-success`, `flow-error-paths`, `flow-xss-defence` |
| `#nat`         | ✅ | `nat`, `flow-nat-lookup-success` |
| `#routemap`    | ✅ | `routemap`, `flow-route-map-compare` |
| `#bgp`         | ✅ | `bgp`, `flow-bgp-lookup`, `flow-bgp-favourites` |
| `#diff`        | ✅ | `diff`, `flow-diff-checker`, `flow-diff-navigation`, `flow-error-paths` |
| `#subnet`      | ✅ | `subnet`, `flow-subnet-split` |
| `#inventory`   | ✅ | `flow-inventory-crud`, `flow-inventory-import-export` |
| `#credential`  | ✅ | `credential`, `flow-credential-add`, `flow-credential-validate` |
| `#notepad`     | ✅ | `notepad`, `flow-notepad-roundtrip` |
| `#help`        | ❌ | — |

**13 / 14 user journeys covered.** `#help` is static HTML — low risk but trivial to add a smoke spec for.

---

## 4. Vitest helper coverage

`backend/static/js/lib/` contains **2 modules with 10 exported functions**, all tested.

| File         | Function              | Vitest covers? |
| ------------ | --------------------- | -------------- |
| `subnet.js`  | `ipToLong`            | ✅ |
| `subnet.js`  | `longToIp`            | ✅ |
| `subnet.js`  | `parseCidr`           | ✅ |
| `subnet.js`  | `networkAddress`      | ✅ |
| `subnet.js`  | `subnetAddresses`     | ✅ |
| `subnet.js`  | `subnetLastAddress`   | ✅ |
| `utils.js`   | `escapeHtml`          | ✅ |
| `utils.js`   | `formatBytes`         | ✅ |
| `utils.js`   | `isValidIPv4`         | ✅ |
| `utils.js`   | `parseHash`           | ✅ |

**Vitest helper coverage: 10 / 10 = 100%.**

The remaining ~5253 lines in `backend/static/js/app.js` are intentionally out-of-scope per the task brief — extracting helpers from the IIFE is queued in `docs/refactor/`.

---

## 5. Wave-3 spec quality spot-check

Reviewed three of the 15 wave-3 specs in detail. All three (a) instantiate `AppShell`, (b) mock backend endpoints with `page.route()`, (c) drive real SPA inputs/buttons, (d) assert visible UI changes — not just "the mock returned what I told it to".

| Spec                                  | AppShell? | Mocks backend? | Asserts SPA UI? | Verdict |
| ------------------------------------- | --------- | -------------- | --------------- | ------- |
| `flow-prepost-run.spec.ts`            | ✅ | ✅ (8 endpoints) | ✅ (`#deviceList .device-row`, `#runStatus`) | **Strong** |
| `flow-mutating-api-smoke.spec.ts`     | n/a (API smoke only) | n/a | n/a (status-only) | **Strong** for its purpose; correctly limited to non-5xx assertions |
| `flow-subnet-split.spec.ts`           | ✅ | n/a (pure client-side) | ✅ (table row count + cell text) | **Strong** |

Additional skim of the remaining 12: `flow-bgp-lookup`, `flow-bgp-favourites`, `flow-credential-validate`, `flow-find-leaf-success`, `flow-route-map-compare`, `flow-diff-navigation`, `flow-restapi-submit`, `flow-inventory-import-export`, `flow-transceiver-clear-counters`, `flow-nat-lookup-success` — all follow the same high-quality pattern.

### Specs that need improvement

| Spec | Issue | Severity | Recommendation |
| ---- | ----- | -------- | -------------- |
| `flow-custom-command.spec.ts` | **Misleading name + coverage gap.** The file's own header acknowledges that `/api/custom-command` is *not* what's being tested — the spec actually exercises `/api/arista/run-cmds`. The Pre/Post page's Custom Command phase (which posts to `/api/custom-command`) has no E2E coverage and the comment's claim that "prepost-run covers it at the SPA-shell level" is incorrect — `flow-prepost-run.spec.ts` only mocks `/api/run/device` and `/api/run/pre/create`. | **Medium** | Either rename this spec to `flow-restapi-arista-run-cmds.spec.ts` *and* add a separate `flow-custom-command-phase.spec.ts` that drives the Pre/Post Custom Command phase end-to-end, or extend this spec with a second `test()` that exercises the Pre/Post phase. |
| `flow-error-paths.spec.ts` (find-leaf branch) | Selector falls back to `input[type=text]` and the Find button selector ORs three forms. This is brittle — a future field rename would silently match the wrong input. The spec also `waitForTimeout(500)` instead of waiting on a real DOM signal. | Low | Pin to the canonical `#findLeafIp` / `#findLeafBtn` IDs and replace the timeout with `expect(page.locator('#findLeafResult, .error-banner')).toBeVisible()`. |
| `flow-diff-navigation.spec.ts` | Hits the real `/api/diff` endpoint (no mock). That's actually fine for diff (pure server-side computation, no external deps), but means a backend regression here will fail this spec instead of producing a clean diagnostic. | Informational | Acceptable as-is; flag if `/api/diff` later grows external dependencies. |

Everything else is in good shape.

---

## 6. Untested user journeys / endpoints (gap inventory)

### 6a. Endpoints with NO Playwright spec at all (11)

1. `GET /api/bgp/as-info`
2. `GET /api/bgp/announced-prefixes`
3. `GET /api/parsers/<command_id>`
4. `POST /api/custom-command` (see spec quality finding above)
5. `GET /api/reports/<run_id>`
6. `POST /api/reports/<run_id>/restore`
7. `DELETE /api/reports/<run_id>`
8. `POST /api/run/pre`              (single-device pre snapshot)
9. `POST /api/run/pre/restore`      (restore from saved report)
10. `POST /api/run/post`            (single-device post snapshot)
11. `POST /api/run/post/complete`   (close the run + write final report)
12. `GET /api/run/result/<run_id>`  (load saved report into the SPA)
13. `POST /api/transceiver/recover` (recovery action button)

(Count is 13 because two of the gaps — `/api/notepad POST` and `/api/credentials POST/DELETE` — are smoke-only and listed separately below.)

### 6b. Endpoints covered ONLY by smoke (status < 500), no UI flow (4)

1. `GET /api/commands`         → no UI flow uses the mocked output
2. `GET /api/parsers/fields`   → same
3. `POST /api/credentials`     → only smoke test, no UI add-flow that asserts row appears (`flow-credential-add` exists but mocks the GET, doesn't drive a real POST round-trip)
4. `POST /api/notepad`         → only PUT is exercised; the POST verb path is never hit

### 6c. SPA pages with NO E2E spec (1)

1. `#help` — static HTML, but a 5-line smoke spec would catch a future refactor that breaks the route.

---

## 7. Negative-path / error-path coverage gaps

`flow-error-paths.spec.ts` covers:
- 5xx on `/api/find-leaf`
- 4xx (413) on `/api/diff`

That's **2 endpoints with negative-path coverage out of 53**. The following error categories have **zero** coverage:

### 7a. 5xx response handling (untested SPA flows)

The SPA renders an error state on every page if its primary endpoint 5xx's, but only two paths are tested. Untested:

- BGP lookup with `status` 500 → does the page show an error card or silently spin forever?
- Inventory list 500 → does `#invTbody` show an empty state or a "failed to load" banner?
- Credentials list 500 → does Validate row render at all?
- Transceiver run 500 → status text behaviour
- Route-map run 500 → result wrap behaviour
- Notepad GET 500 → does the textarea silently render empty?
- Pre/Post run 500 mid-fan-out (some devices succeed, one 500's)
- All 8 BGP lookup endpoints partial-failure (e.g. `status` 200 but `bgplay` 500)

### 7b. Network timeouts / aborted requests

- No spec uses `page.route()` with a `setTimeout` to simulate a hung backend.
- No spec uses `page.route()` `route.abort()` to simulate connection failure.
- The SPA almost certainly has at least one place where it `await`s a fetch with no timeout — should be flagged as a negative test.

### 7c. Empty / null response shapes

- No spec covers the case where `/api/devices` returns `{ devices: [] }` to confirm "no devices match" UX.
- No spec covers `/api/inventory` returning `{}` (missing `inventory` key) to confirm graceful degradation.
- No spec covers `/api/bgp/status` returning `{ announced: false, withdrawn: true }` (the withdrawn-prefix path).

### 7d. Race conditions

- No spec exercises **double-click on Run / Compare / Submit** to confirm the SPA debounces or disables the button.
- No spec exercises **navigating away mid-fetch** (changing hash before fan-out completes) to confirm the SPA cancels stale requests.
- No spec exercises **two parallel BGP lookups** (clicking Lookup twice quickly) where the second's response arrives first.

These three classes (timeouts, null shapes, races) are the highest-yield bug surface for a "happy-path-only" suite. Wave-4 is the right time to add them.

---

## 8. Prioritized list of NEW E2E + UI tests to create

Ordered by **risk-weighted value** (impact × likelihood of regression × ease of writing).

### P0 — write first (blocks operator workflows on 5xx)

| Path | Journey |
| ---- | ------- |
| `tests/e2e/specs/flow-error-paths-extended.spec.ts` | Add 5xx tests for: `/api/inventory` GET, `/api/credentials` GET, `/api/transceiver` POST, `/api/route-map/run` POST, `/api/bgp/status` GET. Assert each renders a visible error banner and emits zero `pageerror` events. |
| `tests/e2e/specs/flow-postrun-complete.spec.ts` | Drive the Pre/Post POST phase end-to-end: pick devices → POST → assert `/api/run/post` and `/api/run/post/complete` fire and the success banner shows the report's `run_id`. Closes the biggest single mutating-flow gap in `runs_bp.py`. |
| `tests/e2e/specs/flow-report-restore.spec.ts` | From a mocked `/api/reports` list, click a row → load via `/api/run/result/<id>` → click Restore → assert `/api/reports/<id>/restore` fires and the SPA shows the restored snapshot. Covers 3 untested endpoints in one spec. |

### P1 — close remaining endpoint gaps

| Path | Journey |
| ---- | ------- |
| `tests/e2e/specs/flow-report-delete.spec.ts` | Delete a saved report from the reports list and assert the row disappears + `/api/reports/<id>` DELETE was called. |
| `tests/e2e/specs/flow-prepost-custom-command.spec.ts` | Pre/Post page → Custom Command phase → POST `/api/custom-command` with mocked response → assert per-device output renders. (Closes the gap behind the misleadingly-named `flow-custom-command.spec.ts`.) |
| `tests/e2e/specs/flow-transceiver-recover.spec.ts` | Drive an err-state row → click the per-row Recover button → assert `/api/transceiver/recover` POSTs with the right device + interface and the row updates. |
| `tests/e2e/specs/flow-bgp-as-info.spec.ts` | BGP page with an AS number input → assert `/api/bgp/as-info` and `/api/bgp/announced-prefixes` both fire and the AS detail card renders. |

### P2 — defensive depth

| Path | Journey |
| ---- | ------- |
| `tests/e2e/specs/flow-network-timeouts.spec.ts` | For 3 representative endpoints (`/api/devices`, `/api/transceiver`, `/api/bgp/status`), simulate a 30-second hung response via `await new Promise(r => setTimeout(r, 30_000))` inside `page.route()` and assert the SPA shows a user-visible "still loading…" state within 2 seconds rather than spinning silently. Tests should fail fast (`test.setTimeout(8_000)`). |
| `tests/e2e/specs/flow-aborted-requests.spec.ts` | For 2 representative endpoints, use `route.abort()` and assert the SPA renders an error state and stays interactive. |
| `tests/e2e/specs/flow-double-click-debounce.spec.ts` | On Pre/Post, REST API, and Route-map pages, double-click the run/compare/submit button and assert the network fan-out fires only once (count `page.route()` invocations). |
| `tests/e2e/specs/flow-empty-shapes.spec.ts` | For 4 representative endpoints, return an empty/missing-key payload and assert the SPA renders a graceful empty state instead of `Cannot read properties of undefined`. |
| `tests/e2e/specs/help.spec.ts` | 5-line smoke spec for `#help` to lock the route in. |

### P3 — secondary smoke

| Path | Journey |
| ---- | ------- |
| `tests/e2e/specs/api-routes-extended.spec.ts` | Extend `READ_ONLY_ROUTES` with `/api/parsers/fields`, `/api/parsers/<known-id>`, `/api/bgp/as-info`, `/api/bgp/announced-prefixes`, `/api/reports/<known-id>`. |

---

## 9. New Vitest UI test files to create

Vitest helper coverage is already 100% for `lib/`. The natural next move is to **extract more helpers from `app.js`** so they become unit-testable — but the task brief flags this as a separate multi-PR project (`docs/refactor/`). No new Vitest specs are blocked on existing helpers.

If wave-4 chooses to seed the extraction, the highest-leverage candidates (frequently-called pure helpers in `app.js`) are:

1. `transceiverIsLeafHostRecoverablePort(role, intfName)` — port-name regex + role check; 100% pure; already informally tested via `flow-transceiver-clear-counters`.
2. `diffComputeRows(left, right)` — diff row generation; pure string→array.
3. `bgpFavouritesParse(rawJson)` and `bgpFavouritesSerialize(arr)` — localStorage round-trip helpers.
4. `routerScopeFilter(devices, scope)` — pure filter for the route-map page.

Each extraction = 1 new file in `lib/` + 1 new Vitest spec. None are required for wave-4 but each one shrinks the IIFE without breaking it.

---

## 10. Summary deliverables

| Deliverable | Value |
| ----------- | ----- |
| Report path | `docs/test-coverage/e2e_gap_analysis_2026-04-22-wave4.md` |
| Endpoints (total / Playwright-tested incl. smoke) | **53 / 42** (79.2%) |
| Endpoints fully UI-tested (excludes smoke-only) | **34 / 53** (64.2%) |
| User journeys (total / E2E-tested) | **14 / 13** (93%) |
| Vitest helpers (covered / total in `lib/`) | **10 / 10** (100%) |
| New E2E specs proposed | **11** (3 P0, 4 P1, 4 P2/P3) |
| Wave-3 specs needing rework | **2** (`flow-custom-command`, error-paths find-leaf branch); 1 informational |

No code or packages were modified during this audit.
