# DONE — `/api/v2/health` config-name leak — implementation plan

**Status:** PLAN ONLY — no code changes performed.
**Owner:** TBD
**Related audit ticket:** Audit-wave-1 / `tests/test_security_health_disclosure.py` (xfail)
**References:** `patch_notes.md:1359`, `patch_notes.md:1432`, `ARCHITECTURE.md:327`

---

## 1. Requirements Restatement

### Functional requirement
The `GET /api/v2/health` endpoint must not echo the internal Flask config
name (`production`, `testing`, `development`) to unauthenticated callers.
Today it returns the literal string in the JSON body's `config` field
(`backend/blueprints/health_bp.py:51`), allowing any probe to fingerprint
environment posture.

### Behavioural contract
After the fix, calling `GET /api/v2/health` against any config must return:

- `200 OK`
- JSON body containing **at minimum** `service`, `status`, `timestamp`,
  `request_id`
- The substring `"production"` MUST NOT appear anywhere in the response
  body or headers (per the existing xfail assertion at
  `tests/test_security_health_disclosure.py:60`)
- The `config` field MUST be absent (or empty string) under **all**
  configs (per `tests/test_security_health_disclosure.py:63`)

### Test contract
- The xfail marker on
  `test_v2_health_does_not_leak_config_name` must be removed.
- The test must pass (xpass → pass) for both the `testing` and
  `production` parametrize values it already exercises.
- An additional row covering `development` must be added so the
  suppression is enforced uniformly.

### Existing consumers that the fix MUST keep green
| File | Line | Assertion |
|---|---|---|
| `tests/test_app_factory.py` | 106 | `body["config"] == "testing"` — must be updated |
| `tests/e2e/specs/api-health.spec.ts` | 14–22 | `service`, `status`, `timestamp`, `request_id` only — already safe |
| `tests/e2e/specs/api-routes.spec.ts` | 15 | route is in the smoke list — already safe |
| `tests/test_security_audit_batch3.py` | 27, 153, 160 | only checks status code + headers — already safe |

### Out of scope
- The legacy `/api/health` route (`backend/blueprints/health_bp.py:57`)
  already returns only `{"status": "ok"}` — no leak, no change.
- General log redaction, CSP tightening, or other audit items.

---

## 2. Current State Analysis

### 2.1 Endpoint that leaks (`backend/blueprints/health_bp.py:46-54`)
```text
return jsonify({
    "service": "pergen",
    "status": "ok",
    "timestamp": datetime.now(UTC).isoformat(),
    "config": current_app.config.get("CONFIG_NAME", ""),   # ← leak
    "request_id": getattr(g, "request_id", ""),
})
```

### 2.2 How `CONFIG_NAME` is populated
- Stamped onto `app.config` by the factory at
  `backend/app_factory.py:105`:
  ```text
  app.config["CONFIG_NAME"] = config_name
  ```
- Used elsewhere (legitimate, internal-only) to gate behaviour:
  - `backend/app_factory.py:220` — production-only branch
  - `backend/blueprints/transceiver_bp.py:104, 116` — destructive-confirm
    auto-on in production
- These internal usages are unaffected by suppressing the *response* field;
  `app.config["CONFIG_NAME"]` itself stays.

### 2.3 The xfail test (`tests/test_security_health_disclosure.py`)
- Lines 38–41: `@pytest.mark.xfail(reason="audit gap …", strict=False)`
- Lines 42: parametrized over `["testing", "production"]`
- Lines 56–64: asserts (a) status 200, (b) literal `"production"` not in
  response text, (c) `body["config"]` is absent/empty.
- Boots a fresh app per parametrize via `_boot()` which evicts cached
  modules (lines 22–35) — safe, no cross-test pollution.

### 2.4 Frontend / monitoring consumers
- `grep -ri "health" backend/static/js/` — **zero hits**. The SPA does not
  read the field.
- `tests/e2e/specs/api-health.spec.ts` — does not touch `body.config`.
- No Prometheus/Grafana scrape config in repo references the field.
- Conclusion: **no production consumer depends on `config` in the
  response body**.

### 2.5 Documentation references that mention the field
- `backend/blueprints/health_bp.py:14-15` (docstring)
- `backend/blueprints/health_bp.py:37-39` (docstring)
- `FUNCTIONS_EXPLANATIONS.md:222`
- `patch_notes.md:1359, 1432`
- `ARCHITECTURE.md:327`
These must be reconciled with whichever option below is chosen.

---

## 3. Open Decision

**Question:** Should `config` be suppressed only in `production`, or
removed entirely from the public `/api/v2/health` and exposed (if at all)
under an authenticated `/admin/health` route?

### Option A — Suppress only in production
- Keep field in dev/test, omit it (or empty-string it) when
  `CONFIG_NAME == "production"`.
- Pros: minimal blast radius, matches the literal wording in
  `patch_notes.md:1432` ("intentionally suppressed under production
  config").
- Cons: leaves a posture-leak surface in any environment that is *not*
  production but is still public-reachable (staging, preview deploys,
  shared dev). The current xfail test itself parametrizes `testing` and
  asserts the field must be absent there too — Option A would FAIL that
  test.

### Option B — Remove from public response in **all** configs (RECOMMENDED)
- Drop the `config` key entirely from the `/api/v2/health` payload.
- Internal callers that need posture continue to read
  `current_app.config["CONFIG_NAME"]` directly (already the only real
  consumer, see §2.2).
- Pros: matches what the existing xfail test actually asserts (both
  `testing` and `production` parametrize rows want the field absent);
  zero attacker-visible posture; no env-conditional branch in the
  handler; smallest, simplest diff.
- Cons: trivially diverges from the docstring and from the e2e expectation
  text — both are easy to update.

### Option C — Move to authenticated `/admin/health`
- Drop from `/api/v2/health`, expose richer payload under
  `/api/v2/admin/health` gated by `PERGEN_API_TOKEN`.
- Pros: cleanest separation; gives ops a real introspection surface.
- Cons: scope creep; new route, new auth wiring, new tests, new docs;
  audit ticket explicitly says "trivial code change".

### Recommendation
**Option B.** It is the minimum change that (a) matches the assertions
already pinned in the xfail test, (b) requires no env-conditional
branch, (c) satisfies the security intent uniformly. Option C is a good
follow-up but should be a separate ticket; conflating it here violates
the "trivial code change" framing in `patch_notes.md:1432`.

---

## 4. Implementation Phases (TDD-first)

### Phase 1 — Pin the contract (RED)
**Goal:** make the suite express the desired post-fix behaviour while
the implementation is still leaky, so we see a real failure to drive the
change.

1. **Edit `tests/test_security_health_disclosure.py`**
   - Remove the `@pytest.mark.xfail(...)` decorator (lines 38–41).
   - Extend the parametrize list from `["testing", "production"]` to
     `["development", "testing", "production"]` so the suppression is
     proven uniform across all three configs.
   - Keep both assertions (no `"production"` substring; no `body.config`).
   - Risk: LOW. Self-contained test edit.

2. **Run the test** (`pytest tests/test_security_health_disclosure.py
   -v`). Expectation: it FAILS for at least one row (the production row
   today already passes because the substring check catches the literal,
   but the `body.config` check fails for all three rows since the field
   is always populated). Confirms RED.

3. **Run the full suite** in collection-only mode (`pytest --collect-only
   -q`) to confirm no other test imports the xfail marker.

**Exit criteria:** the modified test fails with the expected assertion,
and `test_app_factory.py::test_create_app_registers_health_blueprint`
also fails (caught early — the existing assertion `body["config"] ==
"testing"` is now wrong under Option B).

### Phase 2 — Update collateral test (still RED, prevent surprise)
4. **Edit `tests/test_app_factory.py:106`**
   - Replace `assert body["config"] == "testing"` with a positive
     assertion that the key is absent: `assert "config" not in body`.
   - Keep all other assertions (`service`, `status`, `request_id`,
     `timestamp`) unchanged — they document the surviving contract.
   - Risk: LOW.

### Phase 3 — Implement suppression (GREEN)
5. **Edit `backend/blueprints/health_bp.py:46-54`** (the `api_v2_health`
   return)
   - Remove the `"config": current_app.config.get("CONFIG_NAME", "")`
     line entirely.
   - Drop the now-unused `current_app` import if no other use remains in
     the module (verify — `health_bp.py` currently uses it only for
     this lookup).
   - Risk: LOW — pure deletion.

6. **Update the docstrings in the same file**
   - Lines 13–15 (module docstring) — drop the "the registered config
     name" sentence.
   - Lines 36–39 (`api_v2_health` docstring) — drop `"config":
     "<config-name>"` from the documented payload shape.

7. **Run the targeted tests**
   - `pytest tests/test_security_health_disclosure.py -v` — expect PASS
     (3 rows).
   - `pytest tests/test_app_factory.py -v` — expect PASS.
   - `pytest tests/test_security_audit_batch3.py -v` — expect PASS
     (untouched, only checks status + headers).

### Phase 4 — Documentation reconciliation
8. **Update `FUNCTIONS_EXPLANATIONS.md:222`** — remove "config name"
   from the `/api/v2/health` description.
9. **Update `ARCHITECTURE.md:327`** — change the bullet from "audit gap"
   to "resolved (Option B: field removed)".
10. **Update `patch_notes.md`** — append a short entry under the latest
    audit-wave section noting the xfail flip and the field removal;
    cross-reference this plan.

### Phase 5 — Verification gate
11. **Full backend suite:** `pytest -q` — expect green, no new
    skips/xfails introduced.
12. **Coverage check:** confirm `backend/blueprints/health_bp.py` line
    coverage is unchanged (the removed line was already exercised; the
    surrounding lines are still covered by `test_app_factory.py` and
    `test_security_audit_batch3.py`).
13. **E2E smoke:** run `npx playwright test
    tests/e2e/specs/api-health.spec.ts` — expect green; no assertion
    references `body.config`.
14. **Manual probe** (optional, in a scratch venv):
    `curl -s http://localhost:5000/api/v2/health | jq` and confirm no
    `config` key.

### Phase 6 — Review & commit
15. Run `code-reviewer` agent on the diff (it will be ~15 lines).
16. Run `security-reviewer` agent — confirm no regressions, confirm the
    `production` substring guarantee is maintained (no other field
    leaks the literal).
17. Commit message:
    `fix(security): drop CONFIG_NAME from /api/v2/health response (audit-wave-1)`
18. PR summary must reference this plan and the resolved xfail.

---

## 5. Dependencies

### Step graph
```
1 (xfail removal + parametrize) ──┐
                                  ├──► 3 (RED confirmed) ──► 5 (impl) ──► 7 (tests pass)
2 (test_app_factory.py update) ───┘                                            │
                                                                               ▼
                                                                       4,8,9,10 (docs)
                                                                               │
                                                                               ▼
                                                                       11–14 (verify)
                                                                               │
                                                                               ▼
                                                                       15–18 (review/commit)
```

- Steps 1, 2 can run in parallel (independent files).
- Steps 8, 9, 10 can run in parallel (independent docs).
- All other steps are sequential.

### External dependencies
- None. No new packages, no migrations, no env vars, no infra changes.

---

## 6. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| A monitoring tool outside the repo (Grafana panel, custom probe) parses `body.config` and breaks silently | **MEDIUM** | Search team's monitoring config repo before merge; announce in the PR description; mention the field removal in `patch_notes.md` so operators see it on upgrade. |
| `test_app_factory.py:106` change is forgotten and CI fails late | LOW | Phase 2 explicitly addresses it before Phase 3. |
| Docstring updates drift from behaviour over time | LOW | Phase 4 handles all three doc surfaces (handler, FUNCTIONS_EXPLANATIONS, ARCHITECTURE) in one PR. |
| Removing `current_app` import breaks if another future change re-adds usage | LOW | Trivial — re-import on demand. |
| Some other endpoint also leaks the literal `"production"` (false-pass on the substring assertion) | LOW | The substring assertion is scoped to `r.get_data(as_text=True)` of `/api/v2/health` only; no cross-route bleed. |
| Choice of Option B regretted later when ops wants posture introspection | LOW | Option C (`/admin/health`) remains available as a follow-up; nothing in this plan precludes it. |

---

## 7. Estimated Complexity

| Dimension | Estimate |
|---|---|
| Files touched | 6 (1 handler + 2 tests + 3 docs) |
| Net LOC change | ~ −5 / +6 |
| Engineer time | 30–45 min including review |
| Test runtime impact | None |
| Rollback | Trivial — single-commit revert |
| Risk profile | LOW |
| Skill alignment | `tdd-workflow`, `security-review`, `django-security` (concepts), `code-reviewer` |

**Verdict:** Trivial-but-load-bearing security fix. Safe to land in a
single PR.
