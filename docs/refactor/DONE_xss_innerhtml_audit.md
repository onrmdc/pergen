# DONE — XSS `innerHTML` Long-Tail Sweep — Implementation Plan

> **Scope**: Sweeping audit of the remaining ~125 `innerHTML` sites in the SPA frontend after the 7 hot-spot fixes already shipped.
> **Status**: PLAN ONLY — no code changes in this document.
> **Owner**: Frontend / Security
> **Related deferred items**: 1 of 8 follow-ups.

---

## 1. Requirements Restatement

1. Eliminate XSS risk introduced by `element.innerHTML = …` patterns where interpolated values originate from untrusted sources (server JSON, URL params, user input, device hostnames pulled from inventory, BGP API responses, etc.).
2. Preserve every existing UI behaviour — tables, dropdowns, device lists, BGP path chips, diff views, credential rows, error messages — must render identically.
3. Preserve event-binding integrity. Code that wipes a container with `innerHTML = ""` or replaces inner HTML and then expects child elements to exist must continue to work; click/keydown listeners attached to dynamically inserted nodes must keep firing.
4. Add a regression test layer that **fails** if a known XSS payload (`<img src=x onerror=…>`, `"><script>…`, etc.) reaches the DOM as a live element rather than text.
5. Single PR-sized deliverable that future audits can reference (a.k.a. don't ship 7 PRs over 7 weeks).
6. No new build step **unless** the strategic templating option is selected and explicitly approved.

### Non-goals
- Refactoring `app.js` into modules (tracked separately under app decomposition).
- Replacing the entire frontend with a framework (React/Vue/etc.).
- Adding a Content Security Policy `script-src` tightening pass (separate item, although touched by this work — see Risks).

---

## 2. Current State Analysis

### File layout
- **SPA entry**: `backend/static/index.html` (1,349 lines, includes inlined HTML structure for every tab)
- **Single SPA bundle**: `backend/static/js/app.js` — **5,253 lines**, plain ES2018 (no bundler, no transpiler, no modules)
- **Loaded as**: `<script src="/static/js/app.js"></script>` at line 1349 of `index.html`
- **Other JS**: `theme-init.js` (no `innerHTML` usage), `vendor/jszip.min.js` (third-party, out of scope)

### Tooling
- `package.json` defines **only** Playwright + TypeScript (`@playwright/test ^1.49.0`, `typescript ^5.4.0`).
- **No bundler** (no Vite/webpack/esbuild/Rollup).
- **No transpiler** (no Babel).
- **No frontend test runner** (no Jest/Vitest/jsdom present).
- E2E tests live in `tests/e2e/specs/*.spec.ts` (20 specs incl. `csp-no-inline.spec.ts`, `security-headers.spec.ts`).

### `innerHTML` inventory
```
$ grep -rn "innerHTML" backend/static/
backend/static/js/app.js: 135 hits
                          (134 are .innerHTML = …; 1 is the escapeHtml helper internally calling div.innerHTML to read back, which is SAFE)
```
- **0 hits** in `index.html`, `theme-init.js`, `assets/`, `vendor/`.
- Of the 135 hits, **~83 already pass through `escapeHtml(...)`** for at least one interpolated value (sample grep at `backend/static/js/app.js:47, 169, 338, 427, 601, 793, 805, 817, 831, 847, 1372, 1630, 1683, 1700, 1734, 1895, 2061, 2381, 2500, 2548, 2583, 2606, 2695, 2746, 2800, 3084, 3214, 3456, 3469, 3482, 3497, 3514, 3587, 3639, 3780, 4424, 4530, 5164` and others).
- Remaining ~52 sites are either (a) constant strings, (b) clearing operations (`= ""`), or (c) **interpolating server data with no escape** — the high-priority targets.

### Existing `escapeHtml` helper
```
backend/static/js/app.js:347
    function escapeHtml(s) {
      const div = document.createElement("div");
      div.textContent = s;
      return div.innerHTML;
    }
```
- Lives **inside** an IIFE / function scope — already proven correct (relies on browser's text→HTML encoder).
- Some sites use ad-hoc partial escapes (e.g. `String(p).replace(/"/g, "&quot;").replace(/</g, "&lt;")` at `app.js:2385`) which **miss** `>`, `&`, `'` — fragile.

---

## 3. Sample Site Classification (15 representative cases)

Legend:
- **SAFE-CONST** — literal HTML, no interpolation.
- **SAFE-CLEAR** — `= ""` to wipe a container.
- **SAFE-ESCAPED** — interpolates dynamic values, all routed through `escapeHtml(…)`.
- **UNSAFE** — interpolates server/user data **without** escape, or with fragile partial escape.
- **PARTIAL** — escapes some fields but leaves others raw.

| # | Line | Snippet (truncated) | Class | Why |
|---|------|---------------------|-------|-----|
| 1 | `app.js:49` | `body.innerHTML = "<table>…<tbody>" + rows + "</tbody></table>"` | SAFE-ESCAPED | `rows` is built at `:47` via `escapeHtml` for every cell. Wrapper is constant. |
| 2 | `app.js:273` | `fabricSel.innerHTML = "<option…>" + fabrics.map(f => \`<option value="${f}">${f}</option>\`)` | **UNSAFE** | `fabrics` come from `/api/fabrics`. Raw template-literal interpolation, no escape. |
| 3 | `app.js:284` | `siteSel.innerHTML = … + sites.map(s => \`<option value="${s}">${s}</option>\`)` | **UNSAFE** | Server data, no escape. |
| 4 | `app.js:297` | halls dropdown, same pattern | **UNSAFE** | Server data, no escape. |
| 5 | `app.js:311` | roles dropdown, same pattern | **UNSAFE** | Server data, no escape. |
| 6 | `app.js:281` / `316` / `294` / `306` / `465` | `deviceList.innerHTML = ""` | SAFE-CLEAR | Empty literal. |
| 7 | `app.js:587` | `tbody.innerHTML = "<tr class=\"transceiver-err-empty\">…No ports…</tr>"` | SAFE-CONST | No interpolation. |
| 8 | `app.js:755` | `sel.innerHTML = "<option value=\"in\">in</option><option value=\"not-in\">not-in</option>"` | SAFE-CONST | Literal. |
| 9 | `app.js:847` | `device-row` builder using `escapeHtml(d.hostname)` and `escapeHtml(d.ip)` | SAFE-ESCAPED | All dynamic fields escaped. |
|10 | `app.js:2385` | `String(p).replace(/"/g, "&quot;").replace(/</g, "&lt;")` then injected into HTML | **PARTIAL** | Misses `>`, `&`, `'`. Replace with `escapeHtml`. |
|11 | `app.js:4055` | `resultBody.innerHTML = rows.map(r => "<tr><td>" + r[0] + "</td><td>" + (r[1] ? String(r[1]) : "") + "</td></tr>")` | **UNSAFE** | `r[1]` includes `d.leaf_hostname`, `d.leaf_ip`, `d.fabric`, `d.site`, `d.hall`, `d.interface` — all from `/api/find-leaf-*` server response, not escaped. |
|12 | `app.js:4135` | `li.innerHTML = "<span…>" + (label ? label + " " : "") + name + "</span>…"` | **UNSAFE** | `name = d.hostname \|\| d.ip` from API, raw interpolation. |
|13 | `app.js:4232` | `resultBody.innerHTML = "<tr><td colspan=\"2\">" + (data.error \|\| "") + "</td></tr>"` | **UNSAFE** | `data.error` from server response. |
|14 | `app.js:4248` | NAT lookup row builder, same pattern as #11 | **UNSAFE** | Server data, no escape. |
|15 | `app.js:4042` / `4143` | `status.innerHTML = found ? "<span class=\"device-check-ok\">✓</span>" : "<span class=\"device-check-fail\">✗</span>"` | SAFE-CONST | Both branches are literals. |

### Projected breakdown across all 135 sites (after sampling ratio)
- **SAFE-CONST + SAFE-CLEAR**: ~55–65 sites (clears, headers, empty-state messages, constant option lists, DOM resets).
- **SAFE-ESCAPED**: ~50–60 sites (already routed through `escapeHtml` — the patterns introduced in earlier waves).
- **PARTIAL**: ~3–5 sites (ad-hoc `replace()` chains, mostly in BGP module around `app.js:2385`–`2548`).
- **UNSAFE**: ~10–18 sites — concentrated in:
  - Fabric/Site/Hall/Role dropdown builders (`:273, :284, :297, :311`)
  - `find-leaf` and NAT result tables (`:4055, :4135, :4232, :4248`)
  - Possibly: `chipsBar.innerHTML = ""` resets are SAFE but the corresponding chip *builders* nearby may interpolate; needs full pass.

> Confidence: classifier numbers above are sampled; the Phase-1 audit script will produce exact counts.

---

## 4. Surgical vs Strategic Decision

### Option A — Surgical
- Classify all 135 sites with a script + manual review.
- Replace UNSAFE/PARTIAL sites with `escapeHtml(…)`, `textContent`, or DOM API equivalents (`createElement` + `appendChild`).
- Keep `app.js` as a single plain-JS file.
- **Effort**: ~1–2 days. **Risk**: low. **Diff size**: ~300–500 lines touched.

### Option B — Strategic (templating layer)
- Introduce a **tiny tagged-template helper** (no dependency, ~30 lines):
  ```
  // pseudocode for plan only
  html`<tr><td>${name}</td></tr>`   // auto-escapes interpolations
  ```
  or adopt **lit-html** (~5 KB gzip) or **htm + uhtml** (~2 KB gzip).
- Migrate the file (or just the table/list builders) to the tag.
- **Effort**: ~3–5 days for full migration of 135 sites + tests. **Risk**: medium (event re-binding, behaviour parity, file is 5 K lines).
- **Diff size**: huge — touches almost every render function.

### Recommendation: **HYBRID, surgical-first**

1. **Phase A (this PR)**: Surgical — classify and fix every UNSAFE/PARTIAL site with `escapeHtml` / `textContent` / DOM APIs. Add a tiny in-file helper `safeHtml` (tagged template, ~25 lines, **zero dependency**) but **do not** force migration of safe sites.
2. **Phase B (future, optional)**: When `app.js` decomposition (already tracked in `docs/refactor/app_decomposition.md`) splits the file into modules, opportunistically migrate each module to the `safeHtml` tag during the move.

**Why hybrid wins:**
- The user's quoted concern is XSS, not architecture. Surgical solves XSS in one PR.
- Introducing lit-html *now* requires either (a) a build step (the repo has none) or (b) an ESM script tag + import-map work, which is a separate friction point.
- The 5,253-line monolith is already on the decomposition roadmap. Forcing a templating migration inside the monolith doubles diff size and conflicts with that work.
- The `safeHtml` tag keeps the door open: same author ergonomics as lit-html, swap the implementation later if migration is approved.

---

## 5. Surgical Triage Method

### 5.1 Regex-based classifier (build a one-shot Node script under `scripts/audit/innerhtml_classifier.mjs`)
Pseudocode:
1. Read `backend/static/js/app.js` line by line.
2. For each line containing `\.innerHTML\s*=`, extract the right-hand side until matching `;`.
3. Apply the following rules in order:
   - RHS is `""` → **SAFE-CLEAR**.
   - RHS contains no template-literal `${…}` and no `+ ` concatenation with an identifier → **SAFE-CONST** (verify by checking for absence of `[a-zA-Z_$]\s*\+` and `\${`).
   - RHS contains `${…}` or `+ <ident>` and **every** dynamic fragment is wrapped in `escapeHtml(` → **SAFE-ESCAPED**.
   - RHS contains `.replace(/"/g` or `.replace(/</g` ad-hoc → **PARTIAL** (flag for manual review).
   - Otherwise → **UNSAFE**.
4. Emit a CSV `audit/innerhtml_sites.csv` with columns: `line, classification, snippet (first 120 chars)`.

> The script is **advisory, not authoritative**. Every UNSAFE / PARTIAL hit gets manual review before the fix.

### 5.2 Manual review checklist (per UNSAFE site)
For each flagged line, answer:
1. **What is the source** of every interpolated value? (literal, DOM read, fetch response, URL param, user input)
2. **Is the value already escaped** upstream? (rare in this file)
3. **Does the markup contain attributes** with the dynamic value? (attribute injection requires `escapeHtml` AND quoted attribute, or use `dataset` / `setAttribute`)
4. **Does the dynamic value need to be HTML** (i.e. an icon SVG fragment, a pre-built row)? If yes — confirm it is built from a constant template; otherwise convert to `textContent` + child node.
5. **Is there an event listener bound** to the resulting node? If yes — does the replacement preserve the selector path?

### 5.3 Fix patterns (decision table)

| Situation | Fix |
|---|---|
| Inserting text into a `<td>`, `<span>`, `<option>`, etc. | Replace with `el.textContent = value` (preferred — no parsing at all) |
| Building a row/list from N items | Use `escapeHtml(value)` for every interpolation, OR build with `document.createElement` and `appendChild` |
| Inserting into an attribute (`title="${x}"`) | Use `escapeHtml(value).replace(/"/g, "&quot;")` OR `el.setAttribute("title", value)` after the element exists |
| Inserting a known constant HTML fragment (icon, badge) | Leave as-is, mark with `// xss-safe: constant` comment |
| Bulk wipe before re-render | `el.replaceChildren()` (modern, atomic) instead of `el.innerHTML = ""` (functionally equivalent but signals intent) |
| Need to insert HTML built from many parts | Tagged template helper (Phase A): `el.replaceChildren(...safeHtml`<tr>…</tr>`)` |

### 5.4 Tiny `safeHtml` tag (pseudocode for the plan — not code)
- Tagged template that auto-escapes every `${…}` interpolation using the existing `escapeHtml` helper.
- Returns either a string (drop-in for `innerHTML =`) or a `DocumentFragment` (preferred, plays nicer with event listeners).
- ~25 lines, lives next to `escapeHtml` at `app.js:347`.
- Allows opt-in raw insertion via a sentinel (e.g. `safeHtml.raw(constHtml)`) for known-safe icon SVGs.

---

## 6. Implementation Phases (TDD-first)

### Phase 0 — Baseline & safety net (½ day)
- Snapshot current behaviour with `npm run e2e` (existing 20 Playwright specs) — must be GREEN before starting.
- Confirm `tests/e2e/specs/csp-no-inline.spec.ts` and `security-headers.spec.ts` still pass.
- Capture screenshots of: device list, BGP path view, NAT result, find-leaf result, credential list, transceiver table, diff view (for visual regression sanity).

**Exit gate**: 20/20 specs pass; screenshots filed under `tests/e2e/__baseline__/`.

### Phase 1 — Audit script + classification (½ day)
- Add `scripts/audit/innerhtml_classifier.mjs` (the regex classifier from §5.1).
- Run it; commit `docs/refactor/innerhtml_audit_report.csv` for review.
- Manually verify the SAFE-CONST and SAFE-CLEAR buckets by spot-check (10 random per bucket).
- Hand-classify everything in PARTIAL and UNSAFE.

**Exit gate**: CSV checked in; UNSAFE list is finite (expected 10–18 entries) and signed off.

### Phase 2 — RED tests (XSS regression suite) (½ day)
Add `tests/e2e/specs/xss-innerhtml.spec.ts`. For each UNSAFE site, write a Playwright test that:
1. Mocks the relevant API (use `page.route`) to return a payload containing the canary string `"><img src=x onerror="window.__xss=1">`.
2. Triggers the UI flow that renders the value.
3. Asserts:
   - `await page.evaluate(() => window.__xss)` is `undefined` (no script execution).
   - The canary text is visible in the DOM as **text content**, not as an `<img>` element: `await expect(page.locator('img[src="x"]')).toHaveCount(0)`.

Suggested initial scenarios (matched to UNSAFE sites in §3):
- Fabric / Site / Hall / Role dropdowns (mock `/api/fabrics`, `/api/sites`, etc.) — covers `:273, :284, :297, :311`.
- Find-leaf result table (mock `/api/find-leaf-by-ip`) — covers `:4055, :4135`.
- NAT lookup result + error row (mock `/api/find-leaf-by-translated-ip`) — covers `:4232, :4248`.
- BGP announced-prefixes chip list — covers `:2385`.

> All tests should **FAIL** at the start of Phase 2. This proves the regression suite catches real bugs.

**Exit gate**: All new XSS specs run, all FAIL with the pre-fix code.

### Phase 3 — Add `safeHtml` helper (¼ day)
- Add the tagged-template helper alongside `escapeHtml` at `app.js:347`.
- Add unit-style assertions inside an existing test (or a new tiny `tests/e2e/specs/xss-safehtml.spec.ts`) that loads the helper and verifies:
  - Plain interpolation is escaped.
  - `safeHtml.raw(…)` passthrough works for whitelisted constants.
  - Nested templates compose correctly.

**Exit gate**: helper exists, unit assertions pass.

### Phase 4 — Surgical fixes (1 day)
For every UNSAFE / PARTIAL site identified in Phase 1, apply the §5.3 decision table. Order of attack:

1. **Dropdown builders** (`:273, :284, :297, :311, and any matching pattern in transceiver/router/restapi sections`). Replace template literals with `escapeHtml`-wrapped values. Verify the corresponding Phase-2 spec turns GREEN.
2. **Find-leaf / NAT result tables** (`:4055, :4135, :4232, :4248`). Convert to `safeHtml` tag or row-by-row DOM construction.
3. **BGP partial-escape sites** (`:2385, :2532, :2548, :1912–1915`). Replace ad-hoc `replace()` chains with `escapeHtml`.
4. **Anything else** flagged in Phase 1.

After each fix: re-run that scenario's XSS spec until GREEN; re-run the full Playwright suite once at the end of the phase.

**Exit gate**: all XSS specs GREEN; baseline 20 specs still GREEN.

### Phase 5 — Defense in depth (¼ day)
- Add a CI lint step (or a Playwright "static" check spec) that fails if a future commit introduces `\.innerHTML\s*=\s*[^"]*\$\{` (template literal RHS) without the line being annotated `// xss-safe`.
- Document the policy in `AGENTS.md` under Security Guidelines.

**Exit gate**: CI catches a deliberately-injected unsafe pattern in a throwaway commit.

### Phase 6 — Cleanup & docs (¼ day)
- Update `docs/refactor/xss_innerhtml_audit.md` (this file) with the final classification numbers.
- Add a short `docs/security/spa_xss_policy.md` describing: when to use `textContent`, when `safeHtml`, when raw is allowed.
- Reference both from `AGENTS.md`.

**Exit gate**: PR ready for review.

---

## 7. Dependencies

- **Hard**: existing `escapeHtml` helper (`app.js:347`) must remain.
- **Hard**: existing Playwright E2E setup (`playwright.config.ts`, `tests/e2e/`).
- **Soft**: app decomposition work in `docs/refactor/app_decomposition.md` is **not** a blocker — sweep can ship before or after.
- **None**: no new npm dependencies, no build step, no transpiler.

---

## 8. Risks

### HIGH
- **Event-listener regressions after `innerHTML` replacement.** Several UNSAFE sites also re-attach `addEventListener` after rebuilding the container (`:2388–2391` for BGP chips, `:4029` for device list, `:5163` for credential rows). Switching from `innerHTML = htmlString` to `replaceChildren(documentFragment)` can break query selectors if the rebuild order changes. **Mitigation**: keep the renderer's external contract identical — same selectors, same attributes, same DOM order. Each Phase-4 fix runs the matching Playwright happy-path spec, not just the XSS spec.
- **Attribute-context interpolation.** Sites like `app.js:340` interpolate inside `data-hostname="${escapeHtml(d.hostname)}"`. `escapeHtml` does encode `"`, but ad-hoc patterns at `:1912–1915` and `:2500` use `.replace(/"/g, "&quot;")` *after* `escapeHtml` — the redundant replace must remain or be migrated together to avoid breaking double-encoding. **Mitigation**: prefer `setAttribute` when possible; otherwise keep the existing `&quot;` re-replace and add a comment.

### MEDIUM
- **Behavior parity in dropdowns.** Replacing `<option value="${f}">${f}</option>` with `escapeHtml(f)` versions can silently change selected-value handling if `f` contains `&` (now becomes `&amp;` in the DOM, but `select.value` returns the original). **Mitigation**: write a Phase-2 spec that selects an option whose value contains `&` and asserts `select.value === "a&b"`.
- **`safeHtml` tag adoption is opt-in.** Authors might still write `innerHTML = …` ad-hoc. **Mitigation**: Phase-5 lint check.
- **Performance.** `replaceChildren(...documentFragment)` and per-cell `escapeHtml` calls add work on large tables (transceiver list, inventory, diff). **Mitigation**: keep the string-concatenation + `innerHTML` path for tables but route every dynamic cell through `escapeHtml`.

### LOW
- **CSP interaction.** The repo already has a no-inline-script CSP (`tests/e2e/specs/csp-no-inline.spec.ts`). Nothing in this sweep touches `<script>` tags or inline handlers, but if a future fix accidentally adds `onclick="…"` it will be caught by the existing CSP test.
- **File-size growth.** The ~25-line `safeHtml` helper adds negligible bytes.
- **Reviewer fatigue.** Diff will touch ~15–20 functions. **Mitigation**: PR description points reviewers at the audit CSV and the §3 classification table for context.

---

## 9. Estimated Complexity

| Phase | Effort | Risk | Reviewer load |
|------|--------|------|---------------|
| 0 — Baseline | 0.5 d | LOW | minimal |
| 1 — Audit + classify | 0.5 d | LOW | 1 CSV |
| 2 — RED XSS specs | 0.5 d | LOW | 1 spec file |
| 3 — `safeHtml` helper | 0.25 d | LOW | ~30 lines |
| 4 — Surgical fixes | 1.0 d | **MEDIUM** | ~300–500 lines touched |
| 5 — Defense in depth | 0.25 d | LOW | 1 lint check |
| 6 — Docs | 0.25 d | LOW | 2 short docs |
| **Total** | **~3–4 days** | **MEDIUM (driven by Phase 4)** | one PR, ~600–800 line diff |

---

## 10. Success Criteria

- [ ] Audit CSV checked in; UNSAFE bucket finite and itemized.
- [ ] Every UNSAFE site has a Playwright spec that asserts no XSS execution and no live `<img>` / `<script>` injection.
- [ ] All 20 baseline E2E specs still pass.
- [ ] `safeHtml` helper exists, documented, and used by at least the converted hot spots.
- [ ] CI lint catches a synthetic future regression.
- [ ] No new npm dependency, no build step introduced.
- [ ] `AGENTS.md` updated with the SPA XSS policy reference.

---

## 11. Open Questions for Reviewer Sign-off

1. Is the no-build-step constraint firm, or is a small `npm run build` step acceptable in exchange for lit-html ergonomics?
2. Should we ship a **`safeHtml` `DocumentFragment` return** (preferred) or stay with **string return** for drop-in compatibility with existing `innerHTML =` assignments?
3. Is there appetite for a follow-up PR that adopts `Trusted Types` (browser-native XSS guardrail) once the surgical sweep lands?

