# DONE — Plan: Tighten CSP / HSTS Headers on JSON Responses

> **Status:** PLAN ONLY — no code changes in this document.
> **Owner:** TBA · **Tracker:** Deferred follow-up #N of 8 · **Author:** planner agent
> **Scope:** `backend/request_logging.py` after_request hook + paired test refactor

---

## 1. Requirements Restatement

The Phase-13 `after_request` hook in `backend/request_logging.py` already attaches
`Content-Security-Policy` and `Strict-Transport-Security` to **every** response (it
does not gate on `Content-Type`). The real gap is **assurance**, not behaviour:

- `tests/test_security_html_responses_include_csp.py` only verifies the policy on
  the HTML SPA root (`GET /`), so a future regression that gates these headers on
  HTML — e.g. someone adds `if response.mimetype == "text/html":` — would silently
  pass CI.
- `test_security_audit_batch3.py::test_response_carries_*` checks **presence**
  on `/api/v2/health` (a JSON endpoint) but does **not** assert any directive
  contents (no `default-src`, no `script-src`, no `unsafe-inline` ban, no HSTS
  `max-age` floor).

The work is therefore a **policy + test refactor in lockstep**:

1. **Production change:** decide whether JSON responses should carry the *same*
   CSP as HTML or a *stricter* `default-src 'none'` variant, then implement.
2. **Test change:** extend the regression suite so the JSON CSP policy is pinned
   directive-by-directive, mirroring the HTML test, and assert HSTS contents
   (`max-age`, `includeSubDomains`).
3. **Lock the gating contract:** add a parametrised test that exercises both an
   HTML route (`GET /`) and a JSON route (`GET /api/health` or
   `/api/v2/health`) and asserts both carry the documented headers. This makes
   any future Content-Type gating regression fail loudly.

### Out of scope
- HSTS `preload` flag and submission to the HSTS preload list (separate
  operational decision; requires real-world TLS readiness).
- CSP `report-uri` / `report-to` reporting endpoint (no reporting collector
  exists in the codebase today).
- Per-route CSP overrides (the current `setdefault` pattern already supports
  this; no caller uses it).

---

## 2. Current State Analysis

### 2.1 Middleware location

`backend/request_logging.py:68-104` — the `_log_request_end` `after_request`
hook applies six security headers via `response.headers.setdefault(...)`:

| Header | Value | Line |
|---|---|---|
| `X-Frame-Options` | `DENY` | 78 |
| `X-Content-Type-Options` | `nosniff` | 79 |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | 80–82 |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` | 83–85 |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains` | 89–92 |
| `Content-Security-Policy` | `default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'` | 93–104 |

**Critical observation:** there is **no Content-Type gate** anywhere in this
hook. JSON responses already receive the identical CSP and HSTS today. The
flagged concern ("JSON is excluded today") is **not literally true in the
current code** — it is a *risk that the test suite cannot detect a regression
into that state*. The plan is therefore primarily a **test hardening** exercise
plus a small policy decision codified in code.

### 2.2 Current CSP directives (what is and is not safe)

- `default-src 'self'` ✅ baseline
- `img-src 'self' data:` ⚠ `data:` allowed for inline favicons / SPA icons
- `script-src 'self'` ✅ no `'unsafe-inline'`, no `'unsafe-eval'`, no CDN
- `style-src 'self' 'unsafe-inline'` ⚠ inline styles permitted for the SPA
- `object-src 'none'` ✅ blocks Flash/legacy plugins
- `base-uri 'self'` ✅ blocks `<base href>` injection
- `frame-ancestors 'none'` ✅ pairs with `X-Frame-Options: DENY`
- **Missing:** `form-action`, `connect-src`, `font-src`, `media-src`,
  `worker-src`, `manifest-src`, `upgrade-insecure-requests`. All fall through
  to `default-src 'self'` which is acceptable but explicit is safer for JSON.

### 2.3 Current tests

| File | Coverage | Gap |
|---|---|---|
| `tests/test_security_html_responses_include_csp.py:31-44` | HTML `GET /` carries `default-src 'self'` + `script-src 'self'`, no `'unsafe-inline'` in `script-src` | **HTML only** — JSON not exercised |
| `tests/test_security_audit_batch3.py:152-163` | JSON `GET /api/v2/health` has *some* CSP and *some* HSTS header | **No directive content asserted** |
| `tests/test_security_phase13.py:285-302` | JSON `GET /api/health` carries `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` | **CSP / HSTS not asserted on JSON** |

### 2.4 HTML-renderable JSON endpoints?

Searched (`render_template|send_from_directory|text/html` under `backend/`).
The **only** HTML-emitting route is `network_ops_bp.py:107-113` (`GET /`),
which falls back to a JSON sentinel when `static/index.html` is missing. No
JSON endpoint serves HTML-renderable content. **Safe to apply a strict CSP to
JSON** — no browser will execute scripts inside an `application/json` body
regardless of CSP, but a strict CSP defends against MIME-confusion attacks
where a misconfigured proxy or test harness reinterprets the body.

### 2.5 Why the plan even matters if behaviour is already correct

Three reasons:

1. **Regression fence.** Without a JSON-specific test, a future change that
   adds `if response.mimetype.startswith("text/html"):` around the CSP
   `setdefault` block (a plausible "optimisation") would pass all current
   security tests.
2. **Policy precision.** Today JSON inherits `style-src 'unsafe-inline'` it
   does not need. A stricter JSON-only policy removes capability that has no
   legitimate use on JSON responses.
3. **Audit clarity.** External auditors expect to see the JSON API surface
   covered by the same controls as the HTML surface, with explicit tests.

---

## 3. Header Policy Decision

### Option A — Single shared policy (status quo, simplest)
Keep one CSP applied to all responses. Pros: one source of truth, no
Content-Type branching, easiest to reason about. Cons: JSON inherits
`style-src 'unsafe-inline'` it does not need.

### Option B — Stricter JSON variant `default-src 'none'`
Branch on `response.mimetype == "application/json"` and emit
`default-src 'none'; frame-ancestors 'none'; base-uri 'none'`. Pros: minimum
capability for JSON. Cons: introduces the very Content-Type branch we are
trying to defend against; doubles the test matrix; bug surface for SPA
endpoints that occasionally return `text/html` error pages from JSON
blueprints.

### Option C — Single shared, **tightened** policy (RECOMMENDED)
Keep one policy applied universally, but **tighten the shared policy** so it
is acceptable for both HTML and JSON:

```
default-src 'self';
img-src 'self' data:;
script-src 'self';
style-src 'self' 'unsafe-inline';
object-src 'none';
base-uri 'self';
frame-ancestors 'none';
form-action 'self';
connect-src 'self';
upgrade-insecure-requests
```

Additions vs today: `form-action 'self'` (blocks form-jacking),
`connect-src 'self'` (explicit XHR/fetch/websocket origin),
`upgrade-insecure-requests` (defends mixed-content).

**Why C:** keeps one source of truth, removes the Content-Type branching
risk that the task originally flagged, and the additions are safe for both
HTML and JSON. The `'unsafe-inline'` on `style-src` remains only because the
SPA needs it; it is harmless on JSON (no browser parses styles from a JSON
body). HSTS stays unchanged — `max-age=63072000; includeSubDomains` is
already the OWASP recommended floor; **do not add `preload`** without an
operator decision.

> **Decision required from operator before implementation:** confirm Option C.
> If operator prefers Option B for defence-in-depth, swap step 3.2 below for
> a Content-Type-gated emit and double the assertion matrix in step 2.

---

## 4. Implementation Phases (TDD-first, paired test+code)

Each phase is one PR-sized step. The `tests/` changes land in the **same** PR
as the corresponding production change — never split them, or CI will go red
on one side of the merge.

### Phase 1 — RED: pin current JSON behaviour

**Goal:** prove the existing test gap, lock in current behaviour before
changing anything.

1.1 **Create `tests/test_security_json_responses_include_csp.py`**
   - Mirror the HTML test structure.
   - Pick 2–3 representative JSON endpoints from blueprints that exist in
     `flask_app`: `/api/health`, `/api/v2/health`, and one POST-only endpoint
     hit via GET expecting 405 (header middleware still runs on 4xx).
   - Assert each response:
     - has `Content-Security-Policy` header
     - has `default-src 'self'` directive
     - has `script-src 'self'` directive
     - `script-src` does not contain `'unsafe-inline'`
     - `script-src` does not contain `'unsafe-eval'`
     - has `frame-ancestors 'none'` directive
     - has `object-src 'none'` directive
   - Assert HSTS contents:
     - `max-age=` present and value ≥ `31536000` (1 year, OWASP minimum)
     - contains `includeSubDomains`
   - These tests should **pass** against the current implementation —
     this phase is a regression fence, not a behaviour change.

1.2 **Create `tests/test_security_headers_apply_to_all_content_types.py`**
   - Single parametrised test over `(method, path, expected_mimetype)`:
     - `("GET", "/", "text/html")` — SPA root
     - `("GET", "/api/health", "application/json")` — health JSON
     - `("GET", "/api/credentials", "application/json")` — list JSON
     - `("GET", "/static/nonexistent.css", None)` — 404 path (still passes
       through `after_request`)
   - Assert CSP and HSTS present on **every** row.
   - This is the test that catches a future "gate on Content-Type" regression.

1.3 **Run full security suite**
   - Command: `pytest tests/ -m security -v`
   - Confirm new tests pass and no existing test breaks.
   - Capture coverage delta on `backend/request_logging.py`
     (`after_request` block currently sits around the high coverage line —
     verify exact number with `pytest --cov=backend.request_logging`).

### Phase 2 — GREEN: tighten the shared policy (Option C)

2.1 **Update CSP string in `backend/request_logging.py:93-104`**
   - Add `form-action 'self'`
   - Add `connect-src 'self'`
   - Add `upgrade-insecure-requests` (no value, just the directive)
   - Order directives alphabetically inside the string for diff readability
   - Keep using `setdefault` so per-route overrides remain possible
   - Update the docstring above the block to list every directive and the
     OWASP rationale (one line each).

2.2 **Extend Phase-1 tests for the new directives**
   - In `test_security_json_responses_include_csp.py` and
     `test_security_html_responses_include_csp.py`:
     - Add assertion: `form-action 'self'` present
     - Add assertion: `connect-src 'self'` present
     - Add assertion: `upgrade-insecure-requests` present
   - Both files must assert the **same** directive set — keep the directive
     list in a shared module-level constant inside each file (do not import
     across test files; pytest discovery treats them as siblings).

2.3 **Sanity-run the SPA E2E suite**
   - Command: `npx playwright test`
   - The SPA still uses `'self'` for scripts and `'unsafe-inline'` for
     styles — Phase 2 changes do not touch those, so E2E should be green.
   - Required because `connect-src 'self'` will block any accidental
     cross-origin XHR the SPA was relying on. If E2E breaks here, that is
     an existing latent bug surfaced by the tightening — investigate before
     loosening the policy.

### Phase 3 — Verification + docs

3.1 **Update `ARCHITECTURE.md`** security section
   - Replace the current CSP listing with the new directive set.
   - Add a one-paragraph note: "CSP is applied uniformly across HTML and
     JSON responses; see `tests/test_security_headers_apply_to_all_content_types.py`."

3.2 **Cross-link in `docs/refactor/csp_hsts_json_headers.md`**
   - Mark this plan as `Status: SHIPPED` with the merge commit SHA once Phase
     2 lands.

3.3 **Run full pre-merge gauntlet**
   - `pytest tests/ -v --cov=backend --cov-report=term-missing`
     — confirm overall coverage ≥ 80% (project minimum) and
     `backend/request_logging.py` coverage unchanged or improved.
   - `npx playwright test`
   - `ruff check backend/ tests/`
   - Hand to **security-reviewer** agent for a final eyeballing of the
     updated CSP string before merge.

---

## 5. Dependencies

- **No new packages.** All changes use Flask + pytest already in the project.
- **No DB migrations.** Headers are response-time only.
- **No env-var changes.** Policy stays hardcoded; per-deploy variation can
  reuse the existing `setdefault` override path.
- **No coordination with frontend** unless Phase 2.3 surfaces a real
  cross-origin XHR — in which case loop in the SPA owner before merging.
- **Sequencing within Phase 2:** test additions (2.2) and code change (2.1)
  must land in the **same commit** to keep TDD discipline; do not split the
  PR. Phase 1 may land separately as a pure test addition.

---

## 6. Risks

| Severity | Risk | Mitigation |
|---|---|---|
| **HIGH** | `connect-src 'self'` breaks an undeclared cross-origin call from the SPA (e.g. CDN-hosted icon font, analytics beacon, RIPEstat lookup proxied via the browser). | Run Playwright E2E in Phase 2.3 *before* merge. If something breaks, identify the specific origin and add it to `connect-src` (do **not** fall back to `'self' *`). |
| **MEDIUM** | `upgrade-insecure-requests` rewrites `http://` to `https://` for any internal lab device the SPA may iframe or fetch. | Codebase search showed no such fetches; SPA only talks to its own origin. Re-run grep before merge: `grep -RIn "http://" frontend/ src/ static/`. |
| **MEDIUM** | A future blueprint adds an HTML-emitting JSON endpoint (e.g. an HTML error page from a JSON 500) and the stricter policy now blocks legitimate inline elements on that page. | Document in the new test file's docstring that any HTML-emitting route must explicitly override `Content-Security-Policy` per-route via `response.headers["Content-Security-Policy"] = ...` *before* return — `setdefault` already supports this. |
| **LOW** | HSTS `max-age=63072000` + `includeSubDomains` will lock browsers to HTTPS for 2 years on first contact. Already shipped — not a new risk for this plan. | Leave unchanged. Do **not** add `preload` without an operator decision and a real cert chain audit. |
| **LOW** | Test names diverge from the HTML test's naming conventions, making future grep harder. | Mirror the existing file name (`test_security_html_responses_include_csp.py` → `test_security_json_responses_include_csp.py`) and the helper function shape (`_csp(client) -> str`). |
| **LOW** | Monitoring tools (Prometheus scrapers, uptime checkers) parse JSON responses and may "see" CSP headers. CSP is browser-only — non-browser clients ignore them. | No action needed. Documented for clarity. |

---

## 7. Estimated Complexity

| Dimension | Rating | Notes |
|---|---|---|
| LOC changed (production) | ~10 | One CSP string + a 3-line docstring update in `backend/request_logging.py` |
| LOC added (tests) | ~120 | Two new test files, ~60 lines each |
| Files touched | 4 | `backend/request_logging.py`, 2 new test files, `ARCHITECTURE.md` |
| Risk surface | LOW–MEDIUM | One Playwright-flagged risk (`connect-src`); rest is additive |
| Reviewer load | LOW | Diff is small and security-reviewer-friendly |
| Wall-clock estimate | 2–3 hours | Including Playwright run and one round of review |
| Confidence in plan | HIGH | Behaviour already correct; this is primarily test hardening |

---

## 8. Success Criteria

- [ ] `tests/test_security_json_responses_include_csp.py` exists and asserts
      every directive listed in §3 Option C against ≥ 2 JSON endpoints.
- [ ] `tests/test_security_headers_apply_to_all_content_types.py` exists and
      parametrises across HTML, JSON, and 404 paths.
- [ ] `backend/request_logging.py` CSP string contains the three new
      directives (`form-action`, `connect-src`, `upgrade-insecure-requests`).
- [ ] HSTS unchanged (still `max-age=63072000; includeSubDomains`, no preload).
- [ ] `pytest tests/ -m security` is green.
- [ ] `pytest --cov=backend` ≥ 80% overall, `backend/request_logging.py`
      coverage not regressed.
- [ ] `npx playwright test` green.
- [ ] `ARCHITECTURE.md` reflects the new directive set.
- [ ] security-reviewer agent signs off on the final diff.
