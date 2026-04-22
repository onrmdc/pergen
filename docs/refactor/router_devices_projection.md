# Refactor Plan — `/api/router-devices` Credential-Field Projection Leak

> **Status:** PLAN ONLY (no code changes). Source: 1 of 8 deferred follow-ups
> in `patch_notes.md` line 1433; existing xfail at
> `tests/test_security_router_devices_projection.py`.
>
> **Author:** planner agent, 2026-04-22
> **Audience:** implementer agent (TDD-guide → code-reviewer → security-reviewer)

---

## 1. Requirements Restatement

### Functional
1. `GET /api/router-devices?scope={dci|wan|all}` must keep returning the
   same envelope shape `{"devices": [...]}` so the SPA continues to work
   without a coordinated frontend deploy.
2. Each device entry must contain **exactly** the fields the SPA
   actually consumes — no more, no less.
3. The route must continue to filter by role (`dci-router`, `wan-router`,
   or both).

### Security (the actual reason for this refactor)
4. The `credential` column (a **credential-bucket name**, not the secret
   itself, but still a high-value reconnaissance signal) must NOT appear
   in the JSON response.
5. Defence-in-depth: also strip any other inventory column the SPA does
   not need, on the principle of least exposure (currently the route
   leaks `fabric`, `site`, `hall`, `tag` too — none are consumed).
6. The downstream `/api/route-map/run` route must still work after the
   projection change. Today the SPA forwards the whole device dict back
   to that endpoint, which reads `vendor`, `model`, `credential`, `ip`,
   `hostname` from the request body. **Before** the projection is
   tightened, `/api/route-map/run` must be hardened to re-resolve
   `vendor`/`model`/`credential` from the inventory server-side
   (Audit H-2 pattern, identical to `_resolve_inventory_device` already
   used by `/api/arista/run-cmds` and `/api/custom-command`). This
   coupling is the exact reason the original task note says
   *"Need to settle which fields the SPA actually consumes before
   pruning."*

### Non-Functional
7. Test the projection at the contract level (test asserts the **set**
   of allowed keys; rejects any drift in either direction).
8. The xfail in `tests/test_security_router_devices_projection.py` must
   flip to a passing test (remove the `@pytest.mark.xfail`).
9. No regression in golden / E2E suites
   (`tests/golden/test_routes_baseline.py`,
   `tests/e2e/specs/api-routes.spec.ts`,
   `tests/test_device_commands_bp_phase10.py`,
   `tests/test_coverage_push.py`).

---

## 2. Current State Analysis

### 2.1 The Route Handler

`backend/blueprints/device_commands_bp.py:127-145`:

```python
@device_commands_bp.route("/api/router-devices", methods=["GET"])
def api_router_devices():
    """Return DCI and/or WAN routers for route-map compare."""
    scope = (request.args.get("scope") or "all").strip().lower()
    inv_svc = current_app.extensions.get("inventory_service")
    if inv_svc is None:
        return jsonify({"devices": []})
    devs = inv_svc.all()
    ...
    return jsonify({"devices": devices})        # ← raw inventory rows
```

The route returns **raw inventory rows verbatim**. No Pydantic model,
no projection, no `to_public_dict()` adapter.

### 2.2 The Inventory Row Shape

`backend/inventory/loader.py:134`:

```python
INVENTORY_HEADER = ["hostname", "ip", "fabric", "site", "hall",
                    "vendor", "model", "role", "tag", "credential"]
```

The repository normalises every row to exactly these 10 keys
(`InventoryService.normalise_device_row`,
`backend/services/inventory_service.py:75-92`). So today the response
exposes **all 10 columns** — including the audit-flagged
`credential` field plus four other columns the SPA never reads.

### 2.3 Frontend Consumption (SPA)

Two `fetch` call sites, both in `backend/static/js/app.js`:

| Site | Line | What it reads from each device |
|------|------|---------------------------------|
| `loadRouterDevices()` (router page list rendering) | `app.js:2797-2807` | `d.hostname`, `d.ip` (only) |
| `runCompareWithDevices()` (prefix-search "load on demand" path) | `app.js:3052-3057` | Caches the response, then forwards the **whole device dict** to `POST /api/route-map/run` |
| `compareBtn` click handler (router page "Compare" button) | `app.js:2976-3005` | Calls `getSelectedRouterDevices()` (line 2810) which returns objects sliced from `routerDevicesCache`; forwards the **whole device dict** to `POST /api/route-map/run` |

### 2.4 What `/api/route-map/run` Reads From Each Forwarded Device

`backend/blueprints/device_commands_bp.py:176-185`:

```python
hostname  = (d.get("hostname")   or "").strip()
ip        = (d.get("ip")         or "").strip()
vendor    = (d.get("vendor")     or "").strip()   # ← drives Arista detection
model     = (d.get("model")      or "").strip()   # ← drives Arista detection
cred_name = (d.get("credential") or "").strip()   # ← used to look up secret
```

So **today** the SPA must round-trip `hostname`, `ip`, `vendor`,
`model`, `credential` for the Compare button to work. **This is the
constraint that blocked the original projection cleanup.**

**However**, this contradicts the Audit H-2 pattern already enforced
on the two sibling routes in the same file:

- `/api/arista/run-cmds` (line 60-119) calls `_resolve_inventory_device()`
  and explicitly distrusts the request body's `credential` / `vendor` /
  `model`.
- `/api/custom-command` (line 231-265) does the same.

`/api/route-map/run` is the **only** route in this blueprint that
trusts the request-body credential — it is the audit gap that the
projection refactor must close at the same time.

### 2.5 Existing Tests That Touch the Shape

| Test file | Line | Asserts | Status |
|-----------|------|---------|--------|
| `tests/test_security_router_devices_projection.py` | 24-66 | `"credential"` not in any device | **xfail** (audit gap) |
| `tests/test_device_commands_bp_phase10.py` | 65-69 | `body["devices"]` is a list | passes |
| `tests/test_device_commands_bp_phase10.py` | 72-76 | `dci` scope returns `[]` against test inv | passes |
| `tests/test_coverage_push.py` | 696-715 | `wan` scope; asserts `devs[0]["hostname"] == "wanrtr-01"` | passes — **uses `hostname` only** |
| `tests/golden/test_routes_baseline.py` | 107-109 | `body == {"devices": []}` against router-less inv | passes |
| `tests/test_security_xss_spa.py` | 57-77 | SPA escapes `d.hostname` and `d.ip` (source-level) | passes |
| `tests/e2e/specs/api-routes.spec.ts` | 13-29 | GET responds with non-5xx | passes (no shape assertion) |

**Conclusion:** No existing test pins `credential`, `vendor`, `model`,
`fabric`, `site`, `hall`, `tag`, or `role` in the router-devices
response. Removing them is a backwards-compatible change for our
own test surface.

### 2.6 Audit / Logging Dependencies on Full Payload

- `backend/request_logging.py:60-66` logs only `method`, `path`,
  `request_id`, `remote_addr`. **No body logging.**
- No `audit_log()` call exists in `api_router_devices`.
- No external consumer documented in `README.md`, `ARCHITECTURE.md`,
  `HOWTOUSE.md`, or `FUNCTIONS_EXPLANATIONS.md` beyond the SPA itself.

**Conclusion:** No hidden audit dependency on the leaked fields.

---

## 3. Fields Matrix

Authoritative diff between what the backend exposes today, what the
SPA actually consumes, and the proposed minimal projection.

| Field        | Backend exposes today | SPA list-render uses | SPA forwards to `/api/route-map/run` | Recommendation |
|--------------|:---------------------:|:--------------------:|:------------------------------------:|----------------|
| `hostname`   | ✅                    | ✅                   | ✅ (used as inventory key)           | **KEEP** |
| `ip`         | ✅                    | ✅                   | ✅ (used as inventory key + display) | **KEEP** |
| `role`       | ✅                    | ❌                   | ❌                                   | DROP — only used server-side as the filter; the response should not echo the filter input back. |
| `vendor`     | ✅                    | ❌                   | ✅ (today only, as input to Arista detection) | **DROP** — but only after `/api/route-map/run` is hardened to re-resolve from inventory (Phase 1, see §4). |
| `model`      | ✅                    | ❌                   | ✅ (today only, as input to Arista detection) | **DROP** — same prerequisite as `vendor`. |
| `credential` | ✅ **(audit leak)**   | ❌                   | ✅ (today only, as input to credential lookup) | **DROP** — same prerequisite as `vendor`. This is the headline fix. |
| `fabric`     | ✅                    | ❌                   | ❌                                   | **DROP** (defence-in-depth; reveals topology). |
| `site`       | ✅                    | ❌                   | ❌                                   | **DROP** (defence-in-depth). |
| `hall`       | ✅                    | ❌                   | ❌                                   | **DROP** (defence-in-depth). |
| `tag`        | ✅                    | ❌                   | ❌                                   | **DROP** (operator metadata). |

### Proposed minimal projection

```jsonc
{
  "devices": [
    { "hostname": "dci-01", "ip": "10.1.0.1" },
    { "hostname": "wan-01", "ip": "10.1.0.2" }
  ]
}
```

Two fields. Nothing else.

---

## 4. Implementation Phases (TDD-First)

### Phase 0 — Branch & Pre-Flight (no code yet)

1. Create branch `refactor/router-devices-projection`.
2. Confirm baseline: run the four affected suites; record
   the xfail and current pass counts.
   - `pytest tests/test_security_router_devices_projection.py -v`
   - `pytest tests/test_device_commands_bp_phase10.py -v`
   - `pytest tests/test_coverage_push.py::test_router_devices_wan_scope -v`
   - `pytest tests/golden/test_routes_baseline.py::test_router_devices_returns_empty_when_no_router_role -v`

### Phase 1 — Harden `/api/route-map/run` (PREREQUISITE, RED → GREEN)

The projection cannot ship until the SPA stops needing to send
`vendor`/`model`/`credential` back. This phase removes that need.

**Step 1.1** — Write a failing test
`tests/test_security_route_map_run_inventory_bound.py` that asserts:
- A request whose body includes `{"hostname": "dci-01", "vendor": "Cisco", "model": "junk", "credential": "evil-cred"}` is still routed against the **inventory's** `vendor`/`model`/`credential` for that hostname (use a seeded test inventory à la the existing xfail test).
- A request for a hostname NOT in inventory returns an `errors[]` entry (does not silently use the request body's credential).
- File: NEW — `tests/test_security_route_map_run_inventory_bound.py` (~60 lines, mirroring the projection-leak test's inventory-seeding harness at lines 31-56 of the existing test).

**Step 1.2** — Implement the fix in
`backend/blueprints/device_commands_bp.py:153-223`:
- Inside the `for d in devices:` loop, replace the body-trusted
  reads of `vendor`/`model`/`credential` with a call to
  `_resolve_inventory_device(d)` (already defined at line 32 of
  the same file — zero new code surface). Read `vendor`, `model`,
  `credential`, `ip` from the canonical row.
- Keep `hostname` from the request only if needed for the
  `errors[]` envelope's user-friendly identifier; otherwise also
  prefer canonical.
- If `_resolve_inventory_device` returns `None`, append
  `{"hostname": hostname, "error": "device not in inventory"}` to
  errors and `continue`.
- Risk: **MEDIUM** — this changes the trust boundary on a route
  the SPA already drives. The existing
  `test_route_map_run_skips_non_arista` test
  (`tests/test_device_commands_bp_phase10.py:90-112`) sends
  `vendor: "Cisco"` for `leaf-01`; **after** the refactor the
  vendor will be re-read from the mock inventory's `leaf-01` row
  (Arista). Update that test to either (a) seed a non-Arista
  device into the mock inventory, or (b) assert on the new
  "device not in inventory" path with a hostname like `nonexistent`.

**Step 1.3** — Run Phase 1 test; confirm GREEN.

### Phase 2 — Lock the New Projection (RED → GREEN)

**Step 2.1** — Strengthen the existing projection test:
- File: `tests/test_security_router_devices_projection.py`
- Remove the `@pytest.mark.xfail` decorator (lines 20-23).
- Replace the `"credential" not in d` check with a stricter
  contract assertion:
  ```text
  ALLOWED = {"hostname", "ip"}
  for d in devices:
      assert set(d.keys()) == ALLOWED, (
          f"router-devices projection drift: extra={set(d.keys())-ALLOWED} "
          f"missing={ALLOWED-set(d.keys())}"
      )
  ```
- Rename test to `test_router_devices_response_matches_minimal_projection`.

**Step 2.2** — Add a second test in the same file that proves the
shape under both `?scope=dci` and `?scope=wan`, not just `?scope=all`,
to catch any per-scope code-path divergence.

**Step 2.3** — Run; expect RED.

**Step 2.4** — Implement the projection in
`backend/blueprints/device_commands_bp.py:127-145`:

- Add a module-level constant near the top of the file:
  ```text
  # Public projection for /api/router-devices. Audit fix: the inventory
  # row carries 10 columns including `credential`. The SPA only needs
  # hostname + ip for list rendering; the route-map flow re-resolves
  # vendor/model/credential from inventory server-side (Audit H-2).
  _ROUTER_DEVICE_PUBLIC_FIELDS = ("hostname", "ip")
  ```
- Add a tiny private helper in the same file:
  ```text
  def _project_router_device(d: dict) -> dict:
      return {k: (d.get(k) or "") for k in _ROUTER_DEVICE_PUBLIC_FIELDS}
  ```
- Change the final `return` of `api_router_devices` to:
  `return jsonify({"devices": [_project_router_device(d) for d in devices]})`
- Risk: **LOW** (pure projection over a list comprehension; no I/O,
  no new dependencies, ≤10 LOC).

**Step 2.5** — Run; expect GREEN. Run full
`tests/test_device_commands_bp_phase10.py`,
`tests/test_coverage_push.py::test_router_devices_wan_scope`, and
`tests/golden/test_routes_baseline.py::test_router_devices_returns_empty_when_no_router_role`
to confirm no regression (they don't assert on the dropped fields).

### Phase 3 — Tighten Audit Surface (defence-in-depth)

**Step 3.1** — Add an `audit_log()` call inside `api_router_devices`
emitting `event="ROUTER_DEVICES_LIST"` with
`extra={"scope": scope, "count": len(devices)}` so an operator can
diff list-call volume after the projection change. File:
`backend/blueprints/device_commands_bp.py` (one new import, two
new lines). This addresses one row of the deferred
"audit-log coverage gaps" follow-up *for this specific endpoint
only* — the full uniform AuditLogger is still its own PR.

**Step 3.2** — Add a focused unit test
`tests/test_security_router_devices_audit_log.py` asserting that
`app.audit` records a `ROUTER_DEVICES_LIST` event on a successful
GET (use `caplog` on the `app.audit` logger, mirror the pattern
from `tests/test_security_audit_log_coverage.py`).

### Phase 4 — Documentation & Bookkeeping

**Step 4.1** — Update `patch_notes.md` line 1433: move the row from
the "Deferred" table into a new "Resolved in this wave" entry,
linking to this plan and the new tests.

**Step 4.2** — Update `tests/e2e/specs/api-routes.spec.ts:28` —
optionally add a positive assertion that the response body's first
device, if present, has exactly `hostname` and `ip` keys (defence
against a future hand-edit re-introducing leaked fields). Optional;
skip if it adds Playwright complexity.

**Step 4.3** — Update `TEST_RESULTS.md` line 187 to flip the
`xfail` annotation to a passing entry.

**Step 4.4** — Update `ARCHITECTURE.md` line 328 reference to
`/api/router-devices credential projection leak` to mark it
resolved.

### Phase 5 — Verification Loop

1. `pytest tests/ -v -k "router_devices or route_map_run"`
2. `pytest tests/ -v --cov=backend/blueprints/device_commands_bp` —
   ensure coverage on the projection helper hits 100%.
3. `make e2e` — Playwright smoke (must pass without changes; SPA
   call sites untouched).
4. Manual smoke on the SPA:
   - Router page → scope = WAN → device list still renders.
   - Router page → scope = WAN → select 1 device → Compare → table
     populates (proves Phase 1 inventory-rebind works).
   - Router page → scope = DCI → enter prefix `0.0.0.0/0` → Search
     → no JS console errors (proves the second fetch path).
5. `code-reviewer` agent on the diff.
6. `security-reviewer` agent on the diff (focus: "is the credential
   field really gone in every code path including the not-found
   fast-return at line 133?").

---

## 5. Dependencies

### Internal (within this PR)
- **Phase 2 depends on Phase 1.** Cannot ship the projection until
  the route-map endpoint stops needing `vendor`/`model`/`credential`
  from the request body.
- Phase 3 depends on Phase 2 (the audit event uses the projected
  count, but only as a number; could ship independently).
- Phase 4 depends on Phases 1-3 being merged.

### External (other components / files)
- `backend/blueprints/device_commands_bp.py` — touched in Phases 1, 2, 3.
- `backend/services/inventory_service.py` — read-only consumer
  (`inv_svc.all()`); no change required.
- `backend/inventory/loader.py` — `INVENTORY_HEADER` is the source
  of truth for what *could* be exposed; no change required.
- `backend/static/js/app.js` — **no change required**. Both call
  sites already only render `d.hostname` and `d.ip`; the dropped
  fields are forwarded to `/api/route-map/run` but ignored after
  Phase 1.
- `backend/request_logging.py` — provides `audit_log()` used in Phase 3.
- `tests/test_device_commands_bp_phase10.py::test_route_map_run_skips_non_arista`
  — must be updated as part of Phase 1.2 (vendor/model are now
  re-read from inventory, so the existing fixture needs adjustment).

### No external API consumers
A grep across the whole repo (`backend/`, `tests/`, docs) shows
the SPA is the only documented consumer. There is no OpenAPI schema,
no published SDK, no `examples/` directory using this endpoint.

---

## 6. Risks

| Severity | Risk | Mitigation |
|----------|------|------------|
| **HIGH** | Phase 1 changes the trust boundary on `/api/route-map/run`. If the inventory lookup fails for a host the SPA selected (e.g. inventory edited between list call and Compare click), the user sees a "device not in inventory" error that the previous flow would have silently coerced. | Acceptable — this is the correct behaviour (Audit H-2). Document in the SPA's Compare error toast. Add an integration test that exercises the "list → mutate inventory → compare" race. |
| **HIGH** | Phase 1 breaks the existing `test_route_map_run_skips_non_arista` test, which seeds `vendor: "Cisco"` from the request body for a hostname (`leaf-01`) whose inventory row is Arista. | Update the test in the same commit as Phase 1.2. Either (a) introduce a non-Arista row into the test inventory CSV, or (b) assert the "device not in inventory" path with a hostname not present in the seeded inventory. |
| MEDIUM | An undocumented external HTTP consumer (cron, monitoring scrape, tcpdump-derived script) might depend on the leaked `role`/`vendor`/`fabric` fields. | Search confirms none in repo. Mitigation: keep the projection helper centralised so adding a field back is a one-line change; release-note the projection in `patch_notes.md`. |
| MEDIUM | Phase 3 audit-log emission could be noisy on routers refreshed by SPA polling. | The router page does **not** poll this endpoint (verified — only `change` listener on the scope select and the Compare button trigger calls). Volume = operator-driven, not background. |
| LOW | Caller passes `?scope=garbage` and falls into the `else` branch (line 144) — projection still applied uniformly. | Existing branch already returns DCI+WAN; no new edge case. |
| LOW | The two-line `_project_router_device` helper duplicates a pattern that may be needed elsewhere. | Acceptable for now — a generic `project_inventory_row(row, fields)` in `services/inventory_service.py` is a future refactor; do not pre-generalise. |
| LOW | `inv_svc is None` early-return at line 133 already returns `{"devices": []}` — projection helper not exercised on this path. | Add an explicit test for the empty-list path; verify the response shape is identical (`{"devices": []}`). |

---

## 7. Estimated Complexity

| Phase | LOC delta | Test LOC delta | Risk | Time (single-agent) |
|-------|-----------|----------------|------|---------------------|
| 0 | 0 | 0 | — | 5 min |
| 1 | ~15 (route-map handler) + ~5 (existing test fixup) | ~60 (new inventory-bound test) | **HIGH** | 45 min |
| 2 | ~10 (constant + helper + 1-line return) | ~15 (xfail removal + 2 stricter asserts) | LOW | 25 min |
| 3 | ~3 (one audit_log call + import) | ~30 (new audit test) | LOW | 20 min |
| 4 | 0 production / ~5 docs | 0 | — | 15 min |
| 5 | 0 | 0 | — | 20 min (verification loop) |
| **Total** | **~33 production LOC** | **~110 test LOC** | **MEDIUM overall (Phase 1 dominates)** | **~2h 10min** |

### Single-PR vs. multi-PR

Single PR is acceptable because:
- All four production-code touches live in one file
  (`backend/blueprints/device_commands_bp.py`).
- The Phase 1 → Phase 2 ordering is enforceable in one diff.
- Total production delta is small (~33 LOC).

If reviewer prefers strict single-concern PRs:
- **PR-A**: Phase 1 only (route-map inventory-bound rebind).
- **PR-B**: Phases 2-4 (projection + audit + docs), opened against
  PR-A's branch.

---

## 8. Success Criteria

- [ ] `tests/test_security_router_devices_projection.py` flips from
      `xfail` to **PASS** with a stricter `set(d.keys()) == {"hostname", "ip"}` assertion.
- [ ] New test `tests/test_security_route_map_run_inventory_bound.py`
      passes; proves `/api/route-map/run` distrusts request body's
      `vendor`/`model`/`credential`.
- [ ] New test `tests/test_security_router_devices_audit_log.py`
      passes; proves the list call is audit-logged.
- [ ] `tests/test_device_commands_bp_phase10.py` and
      `tests/test_coverage_push.py::test_router_devices_wan_scope`
      and `tests/golden/test_routes_baseline.py` continue to pass.
- [ ] `make e2e` continues to pass (SPA visually unaffected).
- [ ] Manual SPA smoke (router list + Compare + prefix search) works.
- [ ] `code-reviewer` returns no CRITICAL/HIGH findings.
- [ ] `security-reviewer` confirms `credential` does not appear in any
      response code path of `/api/router-devices`.
- [ ] `patch_notes.md` deferred-table row removed; resolved entry added.
- [ ] `TEST_RESULTS.md` xfail entry flipped to pass.
