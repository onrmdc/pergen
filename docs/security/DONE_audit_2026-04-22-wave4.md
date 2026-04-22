# DONE — Pergen Security Audit — Wave 4 (2026-04-22)

**Reviewer:** security-reviewer agent (read-only audit, no code modified)
**Repo state:** post wave-3 close-out (24 → 0 audit-tracker xfails closed)
**Scope:** new attack surface introduced by wave-3 phases 4, 5, 8, 9, 10, 11, 12, 13
**Tooling used:** ripgrep / grep sweep, manual code review, spot-check of 15 wave-3 representative tests
**Out of scope already documented as deferred:** see §6 (cross-reference to wave-2 follow-ups still pending)

---

## 0. Summary

| Severity | New in wave-4 | Notes |
|---|---|---|
| **CRITICAL** | **0** | No new CRITICAL findings. |
| **HIGH** | **1** | Actor-scoping bypass in `/api/run/post/complete` (W4-H-01). |
| **MEDIUM** | **5** | W4-M-01..05 — unauthenticated report restore, anonymous-run scope leakage, log-injection in text mode, etc. |
| **LOW** | **4** | W4-L-01..04 — defence-in-depth. |
| **INFO** | **3** | I-01..03 — observation/hygiene, not vulnerabilities. |

### Top 5 most exploitable NEW findings

1. **W4-H-01 — Actor-scoping bypass via `POST /api/run/post/complete`** — `backend/blueprints/runs_bp.py:312`. Any authenticated actor can complete *another actor's* PRE run, write into their state slot, and persist the report to disk under their `run_id`. The sibling route `/api/run/post` correctly threads `actor=_current_actor()` into `store.get(...)`; this route does not.

2. **W4-M-01 — `POST /api/reports/<id>/restore` is unscoped** — `backend/blueprints/reports_bp.py:90`. Reports persisted to disk carry no creator metadata; any authenticated actor (or anyone, in dev-open mode) can restore *any* run_id into the in-memory `RunStateStore` and re-bind ownership to themselves. Combined with the existing token-gate plus `_state_store().set(..., actor=actor)` design, this lets Bob steal Alice's run by restoring her report under his actor identity.

3. **W4-M-02 — Anonymous-actor runs are readable by every authenticated actor** — `backend/services/run_state_store.py:69-71`. When the gate is disabled (or when a route does not pass `actor=...`), `_created_by_actor` is never set on the stored value, and `get(actor=alice)` returns the run because `owner is None`. Mixed-mode deployments (gate flipped on after some open-mode runs were created) leak those runs to every operator.

4. **W4-M-03 — `RunStateStore.update()` does not enforce actor scoping** — `backend/services/run_state_store.py:94-108`. All mutation routes pin the safety check to `get()`; `update()` is unconditionally permissive. Today no route calls `update(**user_data)`, but the design is fragile — one careless `**data` change propagates a privilege bypass.

5. **W4-M-04 — Log-injection via `notepad.save` `claimed_user` field (text-mode logs)** — `backend/blueprints/notepad_bp.py:73-78`. `data.get("user")` is unvalidated and contains `\n`/`\r` are passed to `_audit.info("...claimed_user=%s...", user, ...)`. JSON-mode logs are safe (json.dumps escapes); the default `ColourFormatter` text-mode is **not** safe. An attacker on dev/test can forge audit-log entries.

### Counts (NEW only — wave-3 already-fixed items not re-counted)

- CRITICAL: **0**
- HIGH: **1**
- MEDIUM: **5**
- LOW: **4**
- INFO: **3**

### Recommended new test files

(see §7 for full list — 9 total recommended)

---

## 1. Methodology

- Read every file touched by wave-3:
  - `backend/services/run_state_store.py` (Phase 4 actor scoping)
  - `backend/app_factory.py:_install_api_token_gate` (Phase 5 immutable token snapshot)
  - `backend/find_leaf/`, `backend/nat_lookup/`, `backend/bgp_looking_glass/`, `backend/route_map_analysis/` (Phase 8 god-module split)
  - All audit-log emission sites (Phase 9): `inventory_bp.py`, `notepad_bp.py`, `runs_bp.py`, `reports_bp.py`
  - `backend/bgp_looking_glass/http_client.py` (Phase 10: `allow_redirects=False`)
  - `backend/blueprints/health_bp.py`, `device_commands_bp.py:api_router_devices` (Phase 11 disclosure projection)
  - `playwright.config.ts` (Phase 12)
  - `backend/static/js/lib/subnet.js` (Phase 13)
  - `backend/blueprints/reports_bp.py:api_report_restore` (new POST route)
- Re-ran the dangerous-primitives sweep (subprocess / eval / exec / pickle / marshal / `yaml.load(` / `verify=False` / raw SQL).
- Spot-checked 15 representative wave-3 tests (xfails-now-pass) to confirm the mitigations are in place.
- Cross-referenced every NEW finding against the existing audit doc (`docs/security/audit_2026-04-22.md`) and the deferred-items list (`docs/refactor/security_audit_wave2_followups.md` + `wave3_roadmap.md`).

---

## 2. Sweep results — `subprocess` / `eval` / `exec` / `pickle` / `os.system` / raw SQL / etc.

| Primitive | Hits in NEW wave-3 surface | Verdict |
|---|---|---|
| `subprocess.*` | 0 (existing single site at `backend/utils/ping.py:37` is unchanged, validated argv, no shell) | **Clean** |
| `os.system` / `os.popen` / `shell=True` | 0 | **Clean** |
| `eval(` / `exec(` | 0 | **Clean** |
| `pickle.*` / `marshal.loads` | 0 | **Clean** |
| `yaml.load(` (unsafe) | 0 (only `yaml.safe_load` at `backend/parsers/engine.py:74`, `backend/config/commands_loader.py:22`) | **Clean** |
| `verify=False` (over-the-internet) | 0 (only `DEVICE_TLS_VERIFY = False` at `backend/runners/_http.py:20` for self-signed device traffic; RIPEStat / PeeringDB use default `verify=True`) | **Clean** |
| `allow_redirects=True` to upstream | 0 (Phase-10 fix at `backend/bgp_looking_glass/http_client.py:47` enforces `allow_redirects=False` and returns an `_error` envelope on any 3xx) | **Clean** |
| Raw SQL execute with f-string interp | 0 (every `conn.execute` in `backend/repositories/credential_repository.py` and `backend/credential_store.py` uses parameter binding) | **Clean** |
| Server-side raw HTML render | 0 (no Jinja templates) | **Clean** |
| Defusedxml downgrade | 0 (`backend/nat_lookup/__init__.py:46` imports `from defusedxml import ElementTree as ET` unconditionally; the Wave-3 god-module split preserved the H-1 fix verbatim) | **Clean** |

**Conclusion:** wave-3 introduces **0** new dangerous-primitive sites. The god-module split, audit-log emissions, and run-state actor scoping are all pure Python over already-validated input. The new attack surface is concentrated in **logic gaps** (actor-scope enforcement, restore endpoint authz) rather than primitive misuse.

---

## 3. NEW findings — ranked by severity

### 3.1 HIGH

#### W4-H-01 — Actor-scoping bypass via `POST /api/run/post/complete`

**File:** `backend/blueprints/runs_bp.py:305-357` (specifically line 312)
**Class:** OWASP A01 (Broken Access Control / IDOR)
**Source of attacker-controlled value:** authenticated `X-API-Token` belonging to actor B; `run_id` of actor A's PRE run (typically known to A but loggable / shareable / leaked through audit logs).

**Code:**
```python
@runs_bp.route("/api/run/post/complete", methods=["POST"])
def api_run_post_complete():
    data = request.get_json(silent=True) or {}
    run_id = (data.get("run_id") or "").strip()
    device_results = data.get("device_results") or []
    store = _state_store()
    pre_run = store.get(run_id)                 # ← NO actor= argument!
    if not run_id or pre_run is None:
        return jsonify({"error": "run_id not found or expired"}), 404
    ...
    store.update(
        run_id,
        post_device_results=device_results,
        comparison=comparison,
        post_created_at=post_created_at,
    )
    ...
    rs.save(  # persists to disk under Alice's run_id
        run_id=run_id, name=name, ...
    )
```

Compare with the **correct** sibling `api_run_post` at line 276:
```python
pre_run = store.get(run_id, actor=_current_actor())   # ← scoped
```

**Attack scenario:**
1. Alice (actor `alice`) creates a PRE run `run_id=X` via `POST /api/run/pre/create`. `_state_store().set(X, ..., actor="alice")` records `_created_by_actor="alice"`.
2. Bob (actor `bob`) obtains `X` (e.g. via a leaked rid in an audit-log line, a chat message, or by enumerating the audit channel).
3. Bob calls `POST /api/run/post/complete` with `{"run_id": "X", "device_results": [...]}` carrying his `X-API-Token`.
4. The route calls `store.get(run_id)` **without** `actor=`, so the actor-scope check at `RunStateStore.get():69-71` is bypassed (because the function only enforces when `actor is not None`).
5. Bob's POST is accepted; the comparison runs against Alice's PRE outputs, the result is `store.update(...)`'d into Alice's slot, and **`rs.save(run_id="X", ...)` persists Bob's POST results to disk under Alice's run_id.**
6. Alice's next `GET /api/reports/X` returns Bob's tampered POST.

**Impact:** complete loss of integrity for any PRE/POST run identified by `run_id`. Audit-log forgery (Alice appears to have completed the POST at Bob's wall-clock time). The attack works inside the wave-3 actor-scoping model that explicitly intended to *prevent* this exact cross-actor mutation.

**Fix:** thread `actor=_current_actor()` into the `store.get(run_id)` call:
```python
pre_run = store.get(run_id, actor=_current_actor())
```

**Test (assert-style):**
```python
def test_run_post_complete_rejects_actor_mismatch(monkeypatch, tmp_path):
    """W4-H-01 — Bob cannot complete Alice's PRE run."""
    client = _gated_client(monkeypatch, tmp_path,
                           tokens="alice:" + "a"*32 + ",bob:" + "b"*32)
    # Alice creates a PRE
    r1 = client.post(
        "/api/run/pre/create",
        json={"devices": [{"hostname":"h","ip":"1.2.3.4"}],
              "device_results": [{"hostname":"h","parsed_flat":{}}],
              "name":"alice-run"},
        headers={"X-API-Token": "a"*32},
    )
    rid = r1.get_json()["run_id"]
    # Bob attempts to complete it
    r2 = client.post(
        "/api/run/post/complete",
        json={"run_id": rid,
              "device_results": [{"hostname":"h","parsed_flat":{"tampered":1}}]},
        headers={"X-API-Token": "b"*32},
    )
    assert r2.status_code in (403, 404), (
        f"Bob completed Alice's PRE run via post/complete (got {r2.status_code})"
    )
```

---

### 3.2 MEDIUM

#### W4-M-01 — `POST /api/reports/<id>/restore` has no actor scoping

**File:** `backend/blueprints/reports_bp.py:90-125`
**Class:** OWASP A01 (Broken Access Control)

**Code:**
```python
@reports_bp.route("/api/reports/<run_id>/restore", methods=["POST"])
def api_report_restore(run_id: str):
    ...
    report = _service().load(run_id)            # no actor check
    ...
    actor = ...  # Bob's actor name, from g.actor
    _state_store().set(
        run_id,
        {...},
        actor=actor,                            # rebinds creator to Bob
    )
    return jsonify({"ok": True, "run_id": run_id})
```

**Attack scenario:**
1. Alice runs PRE+POST and persists report `R` (with run_id `X`) via `/api/run/post/complete`. `R` lives in `instance/reports/X.json.gz`.
2. Bob enumerates `GET /api/reports` (read-only list, returns every saved report's run_id, name, timestamps — see `report_repository.list()`). The list endpoint also has no actor filter.
3. Bob calls `POST /api/reports/X/restore`. The route loads Alice's report from disk and writes it back into `RunStateStore` with `_created_by_actor="bob"`.
4. Bob now owns the in-memory state for run `X`. Subsequent `GET /api/run/result/X` from Bob returns Alice's data; Alice gets 404.

**Impact:** read-confidentiality breach (Bob reads Alice's pre/post device outputs, which include BGP advertisements, ARP tables, interface descriptions, transceiver telemetry — all considered sensitive in network ops); ownership-takeover of in-memory run state.

**Note:** the wave-3 fix for M-03 correctly moved the restore action from `GET ?restore=1` to `POST /restore`, but **did not add actor scoping** at either the report-load or restore-set step. The report-on-disk format (`ReportRepository.save`) carries no `created_by_actor` field, so even after this fix, a follow-up wave is needed to record the report's owner at save time.

**Fix:**
1. Add `created_by_actor` to the `ReportRepository.save` payload and the index entry.
2. In `api_report_restore`, refuse with 404 when `report["created_by_actor"] != actor` (mirror the M-02 IDOR pattern).
3. Apply the same projection in `api_reports_list` so Bob does not see Alice's run_ids in the index.

**Test:**
```python
def test_report_restore_rejects_cross_actor(monkeypatch, tmp_path):
    """W4-M-01 — Bob cannot restore Alice's saved report."""
    client = _gated_client(monkeypatch, tmp_path,
                           tokens="alice:" + "a"*32 + ",bob:" + "b"*32)
    # Alice saves a report
    r1 = client.post(
        "/api/run/pre/create",
        json={"devices": [{"hostname":"h","ip":"1.2.3.4"}],
              "device_results": [{"hostname":"h","parsed_flat":{"secret":"x"}}],
              "name":"alice-report"},
        headers={"X-API-Token": "a"*32},
    )
    rid = r1.get_json()["run_id"]
    # Bob tries to restore it
    r2 = client.post(
        f"/api/reports/{rid}/restore",
        headers={"X-API-Token": "b"*32},
    )
    assert r2.status_code in (403, 404), (
        f"cross-actor restore succeeded (got {r2.status_code})"
    )
```

---

#### W4-M-02 — Anonymous-actor runs are readable by every authenticated actor

**File:** `backend/services/run_state_store.py:65-74`
**Class:** OWASP A01 (Broken Access Control)

**Code:**
```python
def get(self, run_id: str, actor: str | None = None) -> dict | None:
    with self._lock:
        entry = self._state.get(run_id)
        ...
        owner = value.get("_created_by_actor")
        if actor is not None and owner is not None and owner != actor:
            return None
        ...
        return copy.deepcopy(value)
```

The check `owner is not None` makes the actor-scoping a **no-op when no owner was recorded**. Combined with `RunStateStore.set()` only writing `_created_by_actor` when `actor is not None`, every run created from an anonymous request (gate disabled or `_current_actor()` returns `None`) is readable by **all** authenticated actors after the gate flips on.

**Attack scenario:** Realistic operator timeline:
1. Operator boots in dev-open mode (`PERGEN_DEV_OPEN_API=1`), runs a few PRE/POST jobs against production gear during a test.
2. Operator restarts with `PERGEN_API_TOKENS=alice:...,bob:...` to hand the box off to two NOC engineers. The in-memory `RunStateStore` is now empty, so this scenario is bounded to test cases where state is restored from disk via `/api/reports/<id>/restore` (W4-M-01) — **but** that POST runs through `_state_store().set(..., actor=actor)`, so the restored entry IS scoped. Net real-world impact is small.
3. **However**: in production with a token gate, the route handler `_current_actor()` returns `None` for `g.actor == "anonymous"` (see `runs_bp.py:47-49`). This branch is taken only when **no** token is configured, but the same anonymous fallback occurs if a future route forgets to populate `g.actor` before calling `set()`.

**Impact:** primarily a defence-in-depth concern; the realistic exploit chain is narrow. Flag MEDIUM because the design invariant is "actor-scoping always active in production", and the current implementation silently degrades when `owner is None`.

**Fix:** Make `RunStateStore.set()` always record an owner (defaulting to the literal `"anonymous"` instead of skipping the field). Update `get()` to refuse when `owner == "anonymous"` AND the caller passes a non-None actor — i.e. require that the caller and creator both be either-anonymous or named.

**Test:**
```python
def test_runstatestore_anonymous_run_not_readable_by_named_actor(tmp_path):
    """W4-M-02 — A run stored with actor=None must not leak to actor='alice'."""
    store = RunStateStore()
    store.set("X", {"phase":"PRE","data":1}, actor=None)   # anonymous-create
    # Named actor must NOT be able to read an anonymous-create run.
    assert store.get("X", actor="alice") is None
```

---

#### W4-M-03 — `RunStateStore.update()` does not enforce actor scoping

**File:** `backend/services/run_state_store.py:94-108`
**Class:** OWASP A01 (Broken Access Control / fragile invariant)

**Code:**
```python
def update(self, run_id: str, **fields: Any) -> dict | None:
    with self._lock:
        entry = self._state.get(run_id)         # no actor check
        ...
        new_value = copy.deepcopy(value)
        new_value.update(fields)                # arbitrary field-set merge
        ...
```

**Attack scenario:** today, `update()` is only called from `runs_bp.py` with hard-coded keyword arguments (`post_device_results=...`, `comparison=...`, `post_created_at=...`). No request handler does `store.update(run_id, **data)`. So **today this is not directly exploitable**.

**Why it's MEDIUM not LOW:** the wave-3 actor-scope design pinned the safety check to `get()` only. Any future route that follows the existing "look up, then update" pattern must remember to pass `actor=` to `get()`. W4-H-01 already shows one route forgot this.

Additionally, `update()` allows the caller to overwrite `_created_by_actor` itself — `store.update(run_id, _created_by_actor="bob")` would silently take over ownership. This is unreachable by HTTP today, but represents a poison primitive in the API.

**Fix:**
1. Add an `actor` parameter to `update()` matching `get()` semantics:
   ```python
   def update(self, run_id: str, *, actor: str | None = None, **fields: Any) -> dict | None:
       ...
       owner = value.get("_created_by_actor")
       if actor is not None and owner is not None and owner != actor:
           return None
       ...
   ```
2. Reject `_created_by_actor` as a field key (raise ValueError if present in `fields`).

**Test:**
```python
def test_runstatestore_update_refuses_cross_actor():
    store = RunStateStore()
    store.set("X", {"phase":"PRE"}, actor="alice")
    # Bob tries to update Alice's run
    assert store.update("X", actor="bob", post_results="tampered") is None
    # And cannot rewrite the creator field
    with pytest.raises(ValueError):
        store.update("X", actor="alice", _created_by_actor="bob")
```

---

#### W4-M-04 — Log-injection via `notepad.save` `claimed_user` field (text-mode logs)

**File:** `backend/blueprints/notepad_bp.py:73-78`
**Class:** OWASP A09 (Security Logging & Monitoring Failures — log injection)

**Code:**
```python
data = request.get_json(silent=True) or {}
content = data.get("content")
user = (data.get("user") or "").strip() or "—"   # NO sanitisation; no length cap
...
_audit.info(
    "audit notepad.save actor=%s claimed_user=%s bytes=%d",
    _actor(),
    user,                                        # raw, attacker-controlled
    len(content),
)
```

**Attack scenario:** An attacker who can reach `/api/notepad` (open in dev/test, gated in production but a credential leak unlocks it) submits:
```json
{"content":"x","user":"benign\nINFO audit credential.set actor=root name=admin method=basic"}
```

In **text-mode logs** (`LOG_FORMAT=text`, default for development on a TTY), `ColourFormatter.format()` writes `record.getMessage()` directly via string concatenation with no escaping. The forged second line lands in the audit log indistinguishable from a real `credential.set` event.

In **JSON-mode logs** (`LOG_FORMAT=json`, the production default), `json.dumps()` escapes `\n` to `\\n` inside the `msg` field. **JSON mode is safe.**

**Impact:** audit-log forgery in dev/test. Production deployments using JSON logs are unaffected. Severity is MEDIUM rather than HIGH because:
- The forge is constrained to text-mode logs only.
- A forged line still has a leading non-`audit `-prefixed plain-text fragment (the log timestamp and `INFO ` prefix from `ColourFormatter`) that a careful operator can spot — but the typical SIEM ingest pipeline does line-by-line regex matching and would be fooled.

**Fix:**
1. Sanitise `user` at the route layer — strip control characters (`\x00-\x1f`, `\x7f`) and cap length to ~64 chars.
2. Add a defensive replace inside `ColourFormatter.format()`: strip control chars from `body` before concatenating.

**Test:**
```python
def test_notepad_save_user_field_does_not_inject_log_lines(client, caplog):
    """W4-M-04 — `\\n` in user must not split the audit log entry."""
    caplog.set_level("INFO")
    payload = {"content": "x", "user": "alice\nFORGED audit credential.set"}
    client.put("/api/notepad", json=payload)
    audit_records = [r for r in caplog.records if r.name == "app.audit"]
    assert len(audit_records) == 1
    assert "FORGED" not in audit_records[0].getMessage().replace("\\n", "")
```

---

#### W4-M-05 — `_get_json` `_error` envelope echoes upstream `Location` header to caller

**File:** `backend/bgp_looking_glass/http_client.py:51-53`
**Class:** OWASP A09 (information disclosure via error message)

**Code:**
```python
if 300 <= r.status_code < 400:
    return {"_error": f"refused redirect from {url} → {r.headers.get('Location')!r}"}
```

The `_error` envelope is propagated via `bgp_looking_glass.service.get_bgp_status` (and friends) into the JSON response body of `GET /api/bgp/status` etc.

**Attack scenario:** an attacker who can poison RIPEStat's response (DNS spoof, MITM upstream, or a future malicious cache provider) can stuff arbitrary content into the `Location` header. That content lands inside an HTTP-200 response body to the operator. Combined with any client-side `innerHTML` use of the error string, that becomes a stored-XSS vector.

**Impact:** in practice, RIPEStat is HTTPS-only, so MITM requires a CA-trust compromise. The realistic risk is bounded to the attacker who controls the upstream's response — at which point they could plant payload content in the JSON response body too. The defence-in-depth fix is straightforward: **don't echo the Location header**.

**Fix:**
```python
if 300 <= r.status_code < 400:
    return {"_error": f"refused redirect from upstream (HTTP {r.status_code})"}
```

**Test:**
```python
def test_get_json_redirect_error_does_not_echo_location(monkeypatch):
    """W4-M-05 — Location header from a redirected upstream must not be echoed."""
    class _Resp:
        status_code = 302
        headers = {"Location": "<script>alert(1)</script>"}
    monkeypatch.setattr("requests.get", lambda *a, **kw: _Resp())
    out = http_client._get_json("https://stat.ripe.net/data/x.json")
    assert "<script>" not in out["_error"]
    assert "Location" not in out["_error"] or "alert(1)" not in out["_error"]
```

---

### 3.3 LOW

#### W4-L-01 — `_audit` log lines for `report.delete` run after a no-op delete

**File:** `backend/blueprints/reports_bp.py:128-138`

**Issue:** `_service().delete(run_id)` returns `True` only if a file existed; the route emits the audit line unconditionally. An attacker (or a confused operator) `DELETE /api/reports/nonsense` produces `audit report.delete actor=alice run_id=nonsense` — a misleading line that looks like a successful delete. Defence-in-depth: only log when the delete actually removed something.

**Fix:** check the return value of `delete()` and gate the log line on it.

---

#### W4-L-02 — `RunStateStore.update()` accepts `_created_by_actor` as a field

**File:** `backend/services/run_state_store.py:104-105`

**Issue:** see W4-M-03. Independently of the actor-scope check, `update(run_id, _created_by_actor="bob")` will silently rewrite the creator. No HTTP route reaches this today, but the API surface is fragile.

**Fix:** reject `_created_by_actor` (and any other underscore-prefixed reserved key) at the start of `update()`.

---

#### W4-L-03 — `playwright.config.ts` writes a per-run inventory CSV inside the OS temp dir

**File:** `playwright.config.ts:10-21`

**Issue:** `fs.mkdtempSync(...)` creates a world-readable directory by default (mode 0o700 on Linux but Node defers to OS). On a multi-tenant CI host, another user's process could read the seeded inventory CSV and discover the test fixture's IPs/hostnames. Cosmetic in practice (test-only data) but worth a `chmod 0o700` after the mkdtemp.

**Fix:** add `fs.chmodSync(_e2eRoot, 0o700)` immediately after `mkdtempSync`.

---

#### W4-L-04 — `subnet.js` is exported as ES modules but is not loaded by the SPA

**File:** `backend/static/js/lib/subnet.js`

**Issue:** Wave-3 Phase 13 extracted the helpers but the live SPA `app.js` still defines its own copies (per the file header comment). Until the SPA is refactored to import the shared module, any future fix to `subnet.js` will not propagate to production. **Not a vulnerability**; flagged as a maintainability hazard the security-reviewer noticed during the diff sweep.

**Fix:** load `subnet.js` from the SPA via a `<script type="module">` and remove the duplicates from `app.js`. (Tracked as a follow-on PR per the file's docstring.)

---

### 3.4 INFO

- **W4-I-01** — `playwright.config.ts` sets `PERGEN_DEV_OPEN_API=1` only inside the spawned test webServer's env block; the env var does not leak into the parent shell or any production deploy. Confirmed by inspection: `webServer.env` is scoped to the child process. **No production exposure.**
- **W4-I-02** — `rebuild_token_snapshot` is registered on `app.extensions["pergen"]["rebuild_token_snapshot"]` as a Python callable. There is **no HTTP route** that dispatches to it; it is reachable only via `import` from in-process code (i.e. tests). Confirmed by `grep -r "rebuild_token_snapshot"` — the only call sites are two test files. **Not reachable from the network.**
- **W4-I-03** — The 4 god-module shims (`backend/find_leaf/__init__.py`, `nat_lookup/__init__.py`, `bgp_looking_glass/__init__.py`, `route_map_analysis/__init__.py`) re-export every legacy private symbol so test patches keep landing on the live call sites. Late-binding through `from backend import nat_lookup as _shim` inside service methods correctly preserves the patch surface. **No new attack surface from the late-binding pattern itself.** A future contributor who wants to patch one of these symbols outside a test must remember that the shim is the single source of truth — but that's a maintainability concern, not a security one.

---

## 4. Verification of wave-3 mitigations (5 representative xfail-now-pass tests)

Spot-checked by running the listed tests; all 15 pass:

| Wave-3 fix | Test file | Status |
|---|---|---|
| H-04 — diff line-count cap | `tests/test_security_diff_line_dos.py` | **PASS** ✓ |
| H-05 — dev-boot guard requires `PERGEN_DEV_OPEN_API=1` | `tests/test_security_dev_boot_open_api.py` | **PASS** ✓ (3 cases) |
| H-06 — token-gate immutability via `MappingProxyType` snapshot | `tests/test_security_token_gate_immutable.py` | **PASS** ✓ |
| M-01 — `allow_redirects=False` on RIPEStat / PeeringDB | `tests/test_security_ripestat_redirect_guard.py` | **PASS** ✓ |
| M-02 — actor scoping on `/api/run/result/<id>` | `tests/test_security_run_result_actor_scoping.py` | **PASS** ✓ |
| M-03 — restore is now POST-only | `tests/test_security_report_restore_method.py` | **PASS** ✓ (2 cases) |
| Audit-log coverage for inventory / notepad / runs / reports | `tests/test_security_audit_log_coverage.py` | **PASS** ✓ (4 cases) |
| Health endpoint config disclosure removed | `tests/test_security_health_disclosure.py` | **PASS** ✓ |
| `/api/router-devices` projection drops `credential` | `tests/test_security_router_devices_projection.py` | **PASS** ✓ |

**Test-suite snapshot:** 1394 tests collected, 15 of the wave-3 representatives passed in 1.89s (no xfail, no error). Wave-3 mitigations are still in place.

---

## 5. Sweep verification — dangerous primitives

Already enumerated in §2. Summary:

- **`subprocess.*`**: 1 site (unchanged from pre-wave-3). Validated argv, no shell.
- **`eval` / `exec` / `pickle` / `marshal` / `os.system` / `os.popen` / `shell=True`**: **0 sites**. (Confirmed by `grep -rn -E "(^|\s)(pickle|eval|exec|marshal)\(" backend/`.)
- **Raw SQL with f-string interpolation**: **0** in the wave-3 surface. (`backend/credential_store.py` and `backend/repositories/credential_repository.py` use parameter binding throughout.)
- **`yaml.load(` (unsafe)**: **0**. Only `yaml.safe_load` is used.
- **`render_template_string` / `Markup`**: **0**. No Jinja usage.
- **`verify=False` on the open internet**: **0**. The single `DEVICE_TLS_VERIFY = False` constant at `backend/runners/_http.py:20` is for self-signed device traffic only; RIPEStat / PeeringDB use the default `verify=True`.
- **`allow_redirects=True` to upstream**: **0** at any RIPEStat / PeeringDB call site. The Phase-10 fix at `backend/bgp_looking_glass/http_client.py:47` is intact.
- **Defusedxml downgrade**: **0**. Wave-3 god-module split preserved the H-1 unconditional import.

**Net result:** **0 NEW dangerous-primitive sites introduced by wave-3**.

---

## 6. Cross-reference — wave-2 audit findings still DEFERRED

Per `docs/refactor/wave3_roadmap.md` §"What's intentionally still deferred" and `docs/refactor/security_audit_wave2_followups.md`, the following items remain documented future-work. They are **not** new findings in this audit; they are listed so the deferral record stays explicit.

| Item | Reference | Wave-3 status | Shipping order in roadmap |
|---|---|---|---|
| **D-01** — Full credential_store data migration | `docs/refactor/credential_store_migration.md` | Deprecation marker landed (wave-3 Phase 6); legacy module still imported by 6 callers. | Post-wave-3, dedicated PR — dry-run + roundtrip verify. |
| **D-02** — SPA cookie auth + CSRF (Option B) | `docs/refactor/spa_auth_ui.md` | Token-header auth hardened; cookie/CSRF refactor deferred. | Dedicated wave (~5 days, HIGH risk per the roadmap). |
| **D-03** — CSP `unsafe-inline` removal | `docs/refactor/csp_hsts_json_headers.md` | 1 inline `<style>` block + 239 inline `style="..."` attributes still in `index.html`. | Multi-PR project with paired Playwright visual regression. |
| **D-04** — Long-tail XSS sweep (~125 sites) | `docs/refactor/xss_innerhtml_audit.md` | Wave-3 Phase 2 closed only the audit-confirmed UNSAFE sites (H-01 dropdowns + H-02 result tables). | Dedicated PR after the surgical fixes settle. |
| **D-05** — Find-leaf parallel-no-cancel (M-09) | `backend/find_leaf/service.py:141-143` | Preserved verbatim during the Phase-8 refactor with an explicit `NOTE` comment. | ~1-day fix; defer to a paired test+code change PR. |

**No new exploit chain crosses any of these deferred items.** None of the wave-4 NEW findings depend on D-01..D-05 to be exploitable. (For completeness: W4-H-01 and W4-M-01..03 are all in the new actor-scoping surface, independent of cookie auth or CSRF posture.)

---

## 7. Recommended new test files

Write under `tests/`:

1. **`tests/test_security_run_post_complete_actor_scoping.py`** — covers W4-H-01 (actor-scoping bypass via `/api/run/post/complete`).
2. **`tests/test_security_report_restore_actor_scoping.py`** — covers W4-M-01 (restore IDOR + `created_by_actor` on saved reports).
3. **`tests/test_security_runstatestore_anonymous_isolation.py`** — covers W4-M-02 (anonymous-create runs not readable by named actors).
4. **`tests/test_security_runstatestore_update_actor_scoping.py`** — covers W4-M-03 (`update()` actor enforcement + reserved-key rejection).
5. **`tests/test_security_notepad_log_injection.py`** — covers W4-M-04 (CRLF injection in `claimed_user`).
6. **`tests/test_security_bgp_lg_redirect_no_location_echo.py`** — covers W4-M-05 (`_get_json` Location header echo).
7. **`tests/test_security_report_delete_audit_only_on_success.py`** — covers W4-L-01 (audit line gated on actual delete).
8. **`tests/test_security_runstatestore_reserved_field_rejection.py`** — covers W4-L-02 (`_created_by_actor` reserved key in `update()`).
9. **`tests/test_security_report_index_actor_projection.py`** — covers the index-listing leak that pairs with W4-M-01 (Bob should not see Alice's run_ids in `GET /api/reports`).

All nine are conceptually small (≤30 LOC each) and follow the existing `tests/test_security_*` structure.

---

## 8. Suggested fix sequence

### Day 1 — Easy wins (LOW risk, HIGH value)
- **W4-H-01** — single-line fix in `runs_bp.py:312`: add `actor=_current_actor()` to the `store.get(...)` call.
- **W4-M-04** — sanitise `data.get("user")` in `notepad_bp.py:58` (strip control chars, cap length).
- **W4-M-05** — drop the `Location` header from the `_get_json` error envelope.
- **W4-L-01** — gate the `report.delete` audit line on `delete()`'s return value.
- **W4-L-03** — `chmod 0o700` after `mkdtempSync` in `playwright.config.ts`.

### Day 2 — Actor-scoping completeness
- **W4-M-01** — add `created_by_actor` to `ReportRepository.save()` payload + index; refuse cross-actor restore + project the index.
- **W4-M-02** — make `RunStateStore.set()` always record an owner (default `"anonymous"`); refuse cross-anonymous reads when caller has a named actor.
- **W4-M-03** — add `actor=` to `update()` and reject `_created_by_actor` as a field key.

### Day 3 — Followups not from this audit
- Continue with the deferred items D-01..D-05 per `wave3_roadmap.md` shipping order.

---

## 9. Reviewer notes

- **Read-only audit.** No code modified.
- **Severity model:** OWASP risk × deployed-threat-model. The realistic attacker remains an inside operator on the same VLAN (or a compromised authenticated actor); none of the new findings open an unauthenticated remote-RCE path.
- **Wave-3 close-out is real.** All 24 audit-tracker xfails are now passing tests. The 9 architectural items deferred from wave-2 (token gate, credstore, audit logger, /health, router-devices, SPA auth, CSP/HSTS, app decomposition) are either fixed (token gate, audit logger, /health, router-devices) or have explicit follow-up PRs (credstore migration data, SPA cookie auth, CSP unsafe-inline, find_leaf cancel, full XSS sweep).
- **The new HIGH (W4-H-01) is a textbook "one route forgot the safety check" miss** — exactly the kind of finding the actor-scoping wave was designed to prevent. Recommend pairing the W4-H-01 fix with a small grep guard in the test suite that asserts `_state_store().get(...)` is always called with `actor=` inside `runs_bp.py`.

— end of audit —
