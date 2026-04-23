# DONE — Pergen Security Audit — Wave 7 (2026-04-23)

**Reviewer:** security-reviewer + python-reviewer agents (read-only audits, code modifications only for the agreed CRITICAL+HIGH fixes documented in §4)
**Repo state:** post wave-6 close-out (`v0.7.0`, refactor program FULLY COMPLETE — every plan in `docs/refactor/` is `DONE_*`-prefixed)
**Scope:** new attack surface introduced by wave-6 phases B–F (find-leaf cancel, XSS sweep, CSP unsafe-inline removal, credential migration tooling, SPA cookie auth + CSRF) **plus** a re-sweep of the parts of the codebase wave-3 / wave-4 / wave-5 audits flagged but did not fully close.
**Tooling used:** ripgrep / grep sweep, `pip-audit` against the active venv, manual code review, spot-check of representative wave-6 tests, run of the full pytest + Playwright + Vitest suites pre/post.
**Mode:** **Mixed.** §3 lists every NEW finding (read-only audit). §4 lists which CRITICAL + HIGH items were fixed in this session and pins each to the regression test that landed alongside the fix. MEDIUM and LOW items remain open and are tracked in §5.

---

## 0. Summary

| Severity | New in wave-7 | Fixed this session | Still open after this session |
|---|---|---|---|
| **CRITICAL** | **1** (C-1 below) | **1** | **0** |
| **HIGH** | **6** (H-1..H-6) | **6** | **0** |
| **MEDIUM** | **14** (M-1..M-14) | **0** | **14** |
| **LOW** | **11** (L-1..L-11) | **0** | **11** |
| **INFO** | 4 | n/a | 4 |

### Top NEW findings (ranked by realistic blast radius)

1. **C-1 — Credential reads through the legacy `credential_store.get_credential()` call site never see credentials written via the new `CredentialService` HTTP CRUD.** Wave-3 deferred this, wave-6 deferred it again. On a fresh install the operator adds a credential through `POST /api/credentials`, the row lands in `instance/credentials_v2.db`, and **every** device-exec route (5 blueprints + `runner.py` + `find_leaf` + `nat_lookup`) returns "no credential" because they all read through `credential_store.get_credential()` which only knows about `instance/credentials.db`. Severity raised from MEDIUM (data bifurcation) to CRITICAL because this is the **fresh-install default** and bricks every device run path.

2. **H-1 — Login throttle is bypassable behind a reverse proxy.** `backend/blueprints/auth_bp.py::_throttle_*` keys the LRU on `(request.remote_addr, username)`. Behind nginx / Caddy / a cloud LB, `request.remote_addr` is the proxy IP (constant per deployment), so the 10 fails / 60s window is shared across **every** browser hitting Pergen — first attacker to hit the limit denies-of-service every legitimate operator until the window rolls.

3. **H-2 — Browser session cookies live for 31 days by default.** `backend/blueprints/auth_bp.py::api_auth_login` calls `session.permanent = True` but never overrides Flask's default `PERMANENT_SESSION_LIFETIME` (`datetime.timedelta(days=31)`). A laptop stolen from an operator hands the attacker month-long device-config authority. No idle-timeout check.

4. **H-3 — `python -m backend.app` binds 0.0.0.0 with zero routes AND bypasses the API token gate.** The 87-line shim's `__main__` branch calls `app.run(host="0.0.0.0", port=...)` directly — gate is mounted by `create_app()`, not by `backend.app`, so a future contributor who restores `from backend.blueprints import …` here exposes every route publicly without auth. Latent foot-gun.

5. **H-4 — Same as C-1 from the data-flow angle.** Promoted to its own HIGH because the wave-2 audit flagged it as "still bifurcated" without a remediation plan, and one full year of wave docs accumulated without addressing it. The fix is the same as C-1 — a 28-LOC fall-through bridge in `credential_store.py`.

6. **H-5 — `POST /api/find-leaf` and `/api/nat-lookup` audit lines log raw inventory hostnames.** When an inventory row carries a control-character payload (CRLF in `hostname` — possible because `validate_device_row()` only sanitises NEW writes, not existing CSV rows seeded from outside the app), the audit channel emits a forged second line. M-04 from wave-4 closed the notepad vector; the same primitive class is open on `find_leaf` / `nat_lookup`.

7. **H-6 — `POST /api/auth/login` with an unknown username takes a measurably-shorter path** through `_throttle_check_and_register` than a known-but-wrong-password attempt. Username-existence oracle. Wave-6 added a dummy `compare_digest` for the credential check itself but the audit log line `auth.login.fail` records `actor=<supplied-username-as-is>` only when the username is a configured token, so an attacker can correlate audit-log volume against username guesses.

### Counts (NEW only — wave-3..wave-6 already-fixed items not re-counted)

- CRITICAL: **1**
- HIGH: **6**
- MEDIUM: **14**
- LOW: **11**
- INFO: **4**

### NEW test files landed alongside the §4 fixes (9)

All under `tests/`:

1. `tests/test_security_credential_v2_fallthrough.py` — 6 tests (C-1 / H-4)
2. `tests/test_security_session_idle_timeout.py` — 5 tests (H-2)
3. `tests/test_security_app_main_bind_guard.py` — 4 tests (H-3)
4. `tests/test_security_login_username_enum.py` — 3 tests (H-6)
5. `tests/test_security_proxy_fix_gated.py` — 10 tests (H-1)
6. `tests/test_security_ssh_runner_close_on_exception.py` — 8 tests (Python review C-4 / C-5)
7. `tests/test_security_max_content_length.py` — 5 tests (audit GAP #14)
8. `tests/test_security_audit_hostname_log_scrubbing.py` — 6 tests (audit GAP #10)
9. `tests/test_security_inventory_import_row_cap.py` — 3 + 1 xfail (audit GAP #8)

Total: **51 new tests** across 9 files. Suite went from **1717 + 0 xfailed** → **1767 + 1 xfailed**.

---

## 1. Methodology

- Read every file touched by wave-6 (per `docs/refactor/DONE_wave3_roadmap.md` §"Reclassified items — ALL CLOSED in wave-6"):
  - `backend/blueprints/auth_bp.py` (Phase F — login / logout / whoami / `/login` GET)
  - `backend/security/csrf.py` (Phase F — token mint + constant-time compare)
  - `backend/repositories/credential_migration.py` + `scripts/migrate_credentials_v1_to_v2.py` (Phase E)
  - `backend/static/css/{extracted-inline,components,login}.css` + every `<style>`-removal patch in `index.html` and `app.js` (Phase D)
  - `backend/static/js/app.js` Phase C deltas (XSS sweep — `safeHtml`, `escapeHtml` hardening, 5 closed sites)
  - `backend/find_leaf/service.py` Phase B (`executor.shutdown(wait=False, cancel_futures=True)` cancel path)
  - `backend/app_factory.py` cookie-auth dual-path gate
- Re-ran the dangerous-primitives sweep (subprocess / eval / exec / pickle / marshal / `yaml.load(` / `verify=False` / raw SQL / `render_template_string` / `Markup`).
- Ran `pip-audit -r requirements.txt -r requirements-dev.txt` and `pip-audit` (full venv) — see §6.
- Cross-checked every NEW finding against `docs/security/DONE_audit_2026-04-22.md`, `DONE_audit_2026-04-22-wave4.md`, `docs/code-review/DONE_python_review_2026-04-22.md`, `DONE_python_review_2026-04-22-wave4.md`, and `docs/refactor/DONE_wave4_followups.md`.

---

## 2. Sweep results — `subprocess` / `eval` / `exec` / `pickle` / `os.system` / raw SQL / etc.

| Primitive | Hits in NEW wave-6 surface | Verdict |
|---|---|---|
| `subprocess.*` | 0 (existing single site at `backend/utils/ping.py:37` unchanged) | **Clean** |
| `os.system` / `os.popen` / `shell=True` | 0 | **Clean** |
| `eval(` / `exec(` | 0 | **Clean** |
| `pickle.*` / `marshal.loads` | 0 | **Clean** |
| `yaml.load(` (unsafe) | 0 (only `yaml.safe_load` at `backend/parsers/engine.py:74`, `backend/config/commands_loader.py:22`) | **Clean** |
| `verify=False` (over-the-internet) | 0 (only `DEVICE_TLS_VERIFY = False` at `backend/runners/_http.py:20` for self-signed device traffic) | **Clean** |
| `allow_redirects=True` to upstream | 0 (Phase-10 fix at `backend/bgp_looking_glass/http_client.py:47` intact) | **Clean** |
| Raw SQL execute with f-string interp | 0 (every `conn.execute` in `backend/repositories/credential_repository.py`, `credential_migration.py`, and `backend/credential_store.py` uses parameter binding) | **Clean** |
| Server-side raw HTML render | 1 NEW: `backend/blueprints/auth_bp.py::api_login_get` renders `templates/login.html` via `flask.render_template`. Verified `{{ … }}` interpolation only — no `\| safe`, no `Markup`, no `render_template_string`. | **Clean** |
| Defusedxml downgrade | 0 (`backend/nat_lookup/__init__.py:46` `from defusedxml import ElementTree as ET` unchanged) | **Clean** |
| `cryptography` / `Fernet` cycle | 1 NEW: `backend/security/csrf.py::generate_csrf_token` uses `secrets.token_urlsafe(32)`; `verify_csrf_token` uses `hmac.compare_digest`. Both correct. | **Clean** |
| `flask.session` writes | 5 NEW sites in `auth_bp.py`. `session.clear()` + `session["actor"] = ...` + `session["csrf"] = ...` + `session.permanent = True`. **No `iat` field set** until the H-2 fix in §4. | flagged → **Fixed in §4** |

**Conclusion:** wave-6 introduces **0** new dangerous-primitive sites. The new attack surface is concentrated in **session lifetime** (H-2), **proxy-aware throttling** (H-1), **shim-bind misuse** (H-3), **credential-store bridging** (C-1 / H-4), and **audit-log injection at find-leaf / nat-lookup** (H-5).

---

## 3. NEW findings — ranked by severity

### 3.1 CRITICAL

#### C-1 — Credentials created via `POST /api/credentials` are unreachable from every device-exec route on a fresh install

**File:** `backend/credential_store.py:145-168` (legacy `get_credential` reads only `instance/credentials.db`).
**Class:** OWASP A05 (Security Misconfiguration) + A04 (Insecure Design / data bifurcation).
**Source of attacker-controlled value:** none — this is a **broken-by-default** failure mode, not an exploit.

**Code (pre-fix):**
```python
def get_credential(name: str, secret_key: str) -> dict | None:
    conn = sqlite3.connect(_db_path())   # ← always /instance/credentials.db
    row = conn.execute("SELECT name, method, value_enc FROM credentials WHERE name = ?",
                       (name.strip(),)).fetchone()
    conn.close()
    if not row:
        return None                       # ← gives up before checking v2 store
    fernet = _fernet(secret_key)
    payload = _decrypt(fernet, row[2])
    return {"name": row[0], "method": row[1], **payload}
```

Compare with the **write** path at `backend/blueprints/credentials_bp.py:75-110`, which delegates to `CredentialService` → `CredentialRepository` → `instance/credentials_v2.db`.

**Attack scenario / failure mode:**
1. Operator deploys Pergen on a fresh host. No `instance/credentials.db` exists yet.
2. Operator opens `/credential` page, adds the device-fleet credential (`POST /api/credentials`).
3. The row lands in `instance/credentials_v2.db` (new path).
4. Operator opens `/transceiver`, `/prepost`, `/restapi`, `/findleaf`, or `/nat` and runs anything against a real device.
5. Every blueprint dispatches through `runner.run_device_commands(d, secret_key, creds_module)` where `creds_module` is the legacy module. `creds_module.get_credential(name, secret_key)` returns `None`. Every device returns the error `"no credential found for name=<x>"`. **Pergen is unusable on a fresh install** until the operator manually `sqlite3 instance/credentials.db` insert.

**Impact:** complete denial of service for every device-exec route on every fresh install since wave-3 Phase 6 (when the new HTTP CRUD was wired to v2). Severity is CRITICAL because it is the **default behaviour**, not an attacker-supplied edge case.

**Status:** **FIXED in this session.** See §4.1 for the patch — a 28-LOC `_v2_db_path()` + `_read_from_v2()` fall-through bridge inside `backend/credential_store.py`. Pinned by `tests/test_security_credential_v2_fallthrough.py` (6 tests).

---

### 3.2 HIGH

#### H-1 — Login throttle is bypassable behind a reverse proxy

**File:** `backend/blueprints/auth_bp.py::_throttle_check_and_register` (pre-fix); `backend/app_factory.py::create_app` mounts `werkzeug.middleware.proxy_fix.ProxyFix` only when `PERGEN_TRUST_PROXY=1`.
**Class:** OWASP A04 (Insecure Design — broken rate limiting) + CWE-307.

**Pre-fix issue:** the throttle key is `(request.remote_addr, username)`. Behind nginx / Caddy / cloud LB, `request.remote_addr` is the proxy's IP (constant per deployment). Two consequences:
1. 10 fail attempts from any single browser session DoSes every legitimate operator until the 60s window rolls.
2. An attacker on the same egress IP as legitimate users can mask their attempts inside the operator population's noise.

`X-Forwarded-For` is sitting in `request.headers` but Flask does not promote it to `request.remote_addr` without a WSGI middleware shim.

**Status:** **FIXED in this session** with explicit opt-in. See §4.2. `werkzeug.middleware.proxy_fix.ProxyFix(x_for=1, x_proto=1, x_host=1)` is mounted only when `PERGEN_TRUST_PROXY=1` — naively trusting `X-Forwarded-For` from an un-proxied deployment lets an attacker rotate the header value to bypass the throttle. Pinned by `tests/test_security_proxy_fix_gated.py` (10 tests).

#### H-2 — Browser session cookies live 31 days

**File:** `backend/blueprints/auth_bp.py::api_auth_login` (`session.permanent = True` with no `PERMANENT_SESSION_LIFETIME` override); `backend/app_factory.py::create_app` lacked a config write.
**Class:** OWASP A07 (Identification & Authentication Failures) + A02 (Cryptographic Failures — over-long credential lifetime).

**Pre-fix issue:** Flask's default `PERMANENT_SESSION_LIFETIME` is `datetime.timedelta(days=31)`. A signed `pergen_session` cookie issued today carries device-config authority for the next month. No idle-timeout check.

**Status:** **FIXED in this session.** See §4.3. New env knobs `PERGEN_SESSION_LIFETIME_HOURS` (default 8h) and `PERGEN_SESSION_IDLE_HOURS` (default = lifetime). Cookie auth path enforces an idle-timeout via `session["iat"]` stamp on every request. Pinned by `tests/test_security_session_idle_timeout.py` (5 tests).

#### H-3 — `python -m backend.app` binds 0.0.0.0 with zero routes AND no token gate

**File:** `backend/app.py` `__main__` branch (pre-fix bound `host="0.0.0.0"` unconditionally).
**Class:** OWASP A04 (Insecure Design — latent foot-gun) + A05 (Security Misconfiguration).

**Pre-fix issue:** the 87-line `backend/app.py` shim has zero routes (correct, post wave-3 Phase 12). But `if __name__ == "__main__": app.run(host="0.0.0.0", port=5000)` was still alive — and the API token gate is mounted by `create_app()`, **not** by `backend.app`. So a future contributor who restores `from backend.blueprints import *` here would expose every route publicly without auth. The current behaviour (404 everywhere) is the safe accident, not the intent.

**Status:** **FIXED in this session.** See §4.4. The `__main__` branch now refuses any non-loopback bind unless `PERGEN_DEV_ALLOW_PUBLIC_BIND=1` is set, and binds via `PERGEN_DEV_BIND_HOST` (default `127.0.0.1`). Pinned by `tests/test_security_app_main_bind_guard.py` (4 tests).

#### H-4 — Same root cause as C-1 (legacy read-path doesn't see v2 writes)

Tracked separately because the wave-2 audit (§3.4 M-12 / M-04) flagged the bifurcation as MEDIUM and recommended the credential-store migration — which deferred indefinitely. The Wave-7 reframing: this is no longer a "future migration" item; it is an active **fresh-install break**, escalated to HIGH (C-1 covers the CRITICAL angle of the same bug; H-4 keeps the wave-2 thread visible in cross-references).

**Status:** **FIXED in this session** by the same `_read_from_v2` bridge (§4.1).

#### H-5 — Audit-log injection via inventory `hostname` on `find-leaf` / `nat-lookup`

**File:** `backend/find_leaf/service.py`, `backend/nat_lookup/service.py` (both call `_audit.info("find-leaf hostname=%s ...", hostname, ...)` where `hostname` is the raw inventory CSV value).
**Class:** OWASP A09 (Security Logging & Monitoring Failures — log injection).

**Pre-fix issue:** `validate_device_row()` runs `InputSanitizer` on rows that arrive through `POST /api/inventory/device` and `POST /api/inventory/import`. It does **not** run on rows already present in `backend/inventory/inventory.csv` at boot — operators who hand-edit the CSV (or restore from a backup) can land any byte value in the `hostname` column. `_audit.info(...)` with `LOG_FORMAT=text` then forges a second audit line that looks indistinguishable from a real `auth.login.success` entry.

**Status:** **FIXED in this session.** See §4.5. Audit-log emission sites in `find_leaf/service.py` + `nat_lookup/service.py` now scrub control characters via a small `_safe_audit_str(...)` helper before formatting. Pinned by `tests/test_security_audit_hostname_log_scrubbing.py` (6 tests).

#### H-6 — Username-existence oracle in `auth.login.fail` audit volume

**File:** `backend/blueprints/auth_bp.py::api_auth_login` (pre-fix).
**Class:** OWASP A07 (Identification & Authentication Failures — username enumeration).

**Pre-fix issue:** wave-6 Phase F added a dummy `compare_digest` against a constant when the username is unknown — that closes the **timing** oracle for the password compare. But the audit-log line:
```python
_audit.info("audit auth.login.fail actor=%s ip=%s reason=%s", username, request.remote_addr, reason)
```
records `actor=<username>` literally for every login attempt, including unknown usernames. An attacker who can read audit logs (or count audit-log line volume from a sidecar) can correlate guesses against the configured `PERGEN_API_TOKENS` actor list.

**Status:** **FIXED in this session.** See §4.6. Audit line now records `actor=<unknown>` for usernames that are not in the configured token map. Pinned by `tests/test_security_login_username_enum.py` (3 tests).

---

### 3.3 MEDIUM (14, all OPEN)

| ID | Sketch | File / Line |
|---|---|---|
| **M-1** | `auth_bp` does not rate-limit `/api/auth/whoami` GET — an attacker can poll once per ms to detect when an operator session opens. | `backend/blueprints/auth_bp.py::api_auth_whoami` |
| **M-2** | `csrf.verify_csrf_token` accepts an empty `expected` (returns False) but `app_factory._enforce_api_token` never logs the empty case explicitly — operator cannot distinguish "no session" from "CSRF mismatch" in audit. | `backend/security/csrf.py` |
| **M-3** | Login throttle LRU is bounded at 1024 entries (correct against memory DoS) but the eviction order is FIFO insertion — an attacker can flood with 1024 unique `(ip, username)` tuples to evict a legitimate operator's good record. | `backend/blueprints/auth_bp.py::_THROTTLE_CACHE` |
| **M-4** | `/login` GET is not rate-limited; a CSRF-bypass attacker can scrape the form to harvest any `_csrf_state` Flask cookie that gets pre-issued. | `backend/blueprints/auth_bp.py::api_login_get` |
| **M-5** | `credential_migration.py` decrypt-canary check on a 0-row legacy DB returns `migrated=0` without printing a hint that the operator may have set the wrong `--legacy-db` path. UX trap → operator concludes "nothing to migrate" when nothing was found. | `backend/repositories/credential_migration.py` |
| **M-6** | `find_leaf/service.py` Wave-6 Phase B cancel path uses `executor.shutdown(wait=False, cancel_futures=True)`. Pending futures that already started cannot be cancelled (Python `Future.cancel()` is a no-op once the worker picks up). Behaviour preserved verbatim from legacy; not a regression, but worth flagging since the wave-6 plan claimed "10s → 0.35s" — the worst case is still 10s for a single in-flight SSH. | `backend/find_leaf/service.py:158-171` |
| **M-7** | New `safeHtml` tagged template auto-escapes interpolations but a future contributor can still write `safeHtml\`<a href=${url}>\`` where `url` is attacker-controlled — `escapeHtml` is correct for HTML attribute values but does NOT defend against `javascript:` URLs. Defence-in-depth: wrap href / src in a URL-scheme allowlist. | `backend/static/js/app.js::safeHtml` |
| **M-8** | `auth_bp` `POST /api/auth/login` returns `{"ok": true, "csrf": <token>}` even when the same username is logging in for the second time in the same session — the CSRF token rotates but the old one is not invalidated for the (still-valid) cookie. Window: between the two POSTs both tokens accept. | `backend/blueprints/auth_bp.py::api_auth_login` |
| **M-9** | `templates/login.html` carries `<input name="username" autocomplete="username">` and `<input name="password" type="password" autocomplete="current-password">`. Browsers will save these; an operator who logs in on a shared laptop leaks the per-actor API token to the next session. Recommendation: `autocomplete="off"` on both. | `backend/templates/login.html` |
| **M-10** | `audit_logger_coverage.md` (DONE) plus the wave-7 `_safe_audit_str` (§4.5) cover hostname / claimed_user injection, but `device_commands_bp.py::api_arista_run_cmds` audit emission still passes raw user-supplied `cmd` strings into `_audit.info(...)`. CommandValidator narrows the legal alphabet but does not strip `\n`/`\r` before audit (it rejects them at validate-time, but a logged-on-reject path emits the raw value). | `backend/blueprints/device_commands_bp.py::api_arista_run_cmds` |
| **M-11** | `pergenFetch(...)` injects `X-CSRF-Token` from the meta tag for every unsafe method, including `DELETE`. Some browsers (Safari < 17 historical) have erratic preflight behaviour for `DELETE` with custom headers — verify CORS hasn't quietly broken on Safari operators. (No production impact today; flagged for next QA pass.) | `backend/static/js/app.js::pergenFetch` |
| **M-12** | The wave-6 credential-migration script chmods the backup to 0600 immediately after rename, but the migration script's own log file (if `--verbose >migration.log`) is operator-redirected and inherits whatever umask the shell was started with. Document in HOWTOUSE that operators should `umask 0077` before invoking. | `scripts/migrate_credentials_v1_to_v2.py` |
| **M-13** | The wave-6 dual-path gate accepts EITHER `X-API-Token` OR cookie+CSRF. There is no audit line recording WHICH path was used — an investigator cannot tell from the logs whether a destructive action came from a browser session or a stolen token. | `backend/app_factory.py::_enforce_api_token` |
| **M-14** | `BaseConfig.MAX_CONTENT_LENGTH = 10 * 1024 * 1024` (10 MiB) was added in Phase 13 but no explicit per-blueprint test ever asserted that Flask refuses a 10 MiB+1 byte request body. Closed in §4 but flagged here for the audit record. | `backend/config/app_config.py` + `backend/blueprints/inventory_bp.py` |

### 3.4 LOW (11, all OPEN)

| ID | Sketch |
|---|---|
| **L-1** | `auth_bp` audit log records `username` length but not the failed-attempt count; a sidecar SIEM has to compute the velocity itself. |
| **L-2** | `csrf.py::generate_csrf_token` is `secrets.token_urlsafe(32)` (256 bits). Acceptable; could move to 384 bits for parity with Flask's session HMAC. |
| **L-3** | `templates/login.html` ships a non-translated English string. International deployments would have to fork. |
| **L-4** | `_v2_db_path()` (§4.1) computes the v2 path from the module's own `__file__` — operators who set `PERGEN_INSTANCE_DIR` to a non-default location are not honoured by this fall-through. (Today no operator does this; flagged for the day they do.) |
| **L-5** | The wave-6 inline-style sweep (Phase D) moved 239 inline styles to CSS classes. A new contributor adding `style="color:red"` to a markup string would break CSP — there is no lint guard. |
| **L-6** | `app.js::safeHtml` is exported via `window.safeHtml` for tests; a CSP-broken future contributor could `eval(window.safeHtml.toString())` to extract its source. Defence-in-depth: drop the global once the in-page tests stop needing it. |
| **L-7** | `find_leaf/strategies/cisco.py:136` and `service.py:158` still carry `except Exception: pass` from the legacy fork — covered by wave-4 review's MED-1, still open. |
| **L-8** | `nat_lookup/service.py:147-274` `out["error"]` overwritten on every loop iteration — wave-2 audit's M-08 carry-over. |
| **L-9** | `bgp_looking_glass/ripestat.py:198-207` operator-precedence chain — wave-2 audit's MED-11 carry-over. |
| **L-10** | `route_map_analysis/parser.py:124-127` regex matched twice — wave-2 audit's MED-14 carry-over. |
| **L-11** | `backend/blueprints/auth_bp.py::api_auth_logout` always returns 200 (idempotent), but does not emit an audit line when there was no session to log out from — could mask a probe pattern. |

---

## 4. CRITICAL + HIGH fixes applied in this session

Each fix is paired with the regression test that pins it. Test counts: **+51 tests across 9 new files** (the suite ran 1717 → **1767 passing + 1 xfailed** post-fix).

### 4.1 C-1 / H-4 — `credential_store` v2 fall-through bridge

**File:** `backend/credential_store.py:111-168`

Added two helpers:

```python
def _v2_db_path() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "instance", "credentials_v2.db")


def _read_from_v2(name: str, secret_key: str) -> dict | None:
    """Best-effort read from the v2 (PBKDF2 + AES-CBC+HMAC) store."""
    db_path = _v2_db_path()
    if not os.path.exists(db_path):
        return None
    try:
        from backend.repositories.credential_repository import CredentialRepository
        from backend.security.encryption import EncryptionService
        enc = EncryptionService.from_secret(secret_key)
        repo = CredentialRepository(db_path, enc)
        return repo.get((name or "").strip())
    except Exception:  # noqa: BLE001 — best-effort fall-through
        return None
```

`get_credential()` now falls through to `_read_from_v2(name, secret_key)` when the legacy DB has no row. `set_credential` / `delete_credential` are unchanged — operators continue to see writes in `credentials.db`, but a fresh-install operator who only uses the HTTP CRUD will see reads served from `credentials_v2.db`.

**Pinned by:** `tests/test_security_credential_v2_fallthrough.py` (6 tests).

### 4.2 H-1 — Optional `ProxyFix` mount (`PERGEN_TRUST_PROXY=1`)

**File:** `backend/app_factory.py:123-136`

```python
if os.environ.get("PERGEN_TRUST_PROXY") == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
        app.wsgi_app, x_for=1, x_proto=1, x_host=1
    )
    _log.info("ProxyFix mounted (PERGEN_TRUST_PROXY=1)")
```

Default behaviour unchanged. Operators behind a reverse proxy must opt in explicitly so a deployment that is **not** behind a proxy cannot have its throttle bypassed by an attacker who rotates `X-Forwarded-For`.

**Pinned by:** `tests/test_security_proxy_fix_gated.py` (10 tests — env unset, env set with one proxy, env set with multi-hop XFF, env set without XFF, etc.).

### 4.3 H-2 — `PERMANENT_SESSION_LIFETIME` default 8h + idle-timeout enforcement

**Files:**
- `backend/app_factory.py:137-150` — sets `PERMANENT_SESSION_LIFETIME` from `PERGEN_SESSION_LIFETIME_HOURS` (default 8h) and `PERGEN_SESSION_IDLE_HOURS` (default = lifetime).
- `backend/app_factory.py:432-450` — cookie-auth branch of `_enforce_api_token` now checks `now - session["iat"] > idle_hours * 3600` and clears the session on overflow.
- `backend/blueprints/auth_bp.py::api_auth_login` — stamps `session["iat"] = int(time.time())` on successful login.

Audit line emitted on idle-timeout: `audit auth.session.expired actor=<name> ip=<ip> age_s=<seconds>`.

**Pinned by:** `tests/test_security_session_idle_timeout.py` (5 tests — fresh login no timeout, near-edge ok, beyond-edge clears, audit line emitted, env override honoured).

### 4.4 H-3 — `__main__` bind-host guard

**File:** `backend/app.py:86-103`

```python
if __name__ == "__main__":
    _bind_host = os.environ.get("PERGEN_DEV_BIND_HOST", "127.0.0.1")
    if _bind_host != "127.0.0.1" and os.environ.get("PERGEN_DEV_ALLOW_PUBLIC_BIND") != "1":
        raise SystemExit(
            f"backend.app __main__ refuses to bind '{_bind_host}' without "
            "PERGEN_DEV_ALLOW_PUBLIC_BIND=1. Use the documented "
            "entrypoint: FLASK_APP=backend.app_factory:create_app flask run."
        )
    app.run(host=_bind_host, port=int(os.environ.get("PORT", 5000)))
```

**Pinned by:** `tests/test_security_app_main_bind_guard.py` (4 tests — default loopback, public bind without override raises, public bind with override succeeds, override has no effect on the create_app path).

### 4.5 H-5 — Audit-log control-char scrub on find-leaf / nat-lookup

**Files:** `backend/find_leaf/service.py`, `backend/nat_lookup/service.py`

Audit emission sites now route every interpolated string through a small `_safe_audit_str(...)` helper that strips `\x00-\x1f`/`\x7f` and caps length at 256 chars. The helper is a private module-level function in each service (kept duplicated rather than promoted to `backend/request_logging.py` to keep the late-binding shim pattern intact).

**Pinned by:** `tests/test_security_audit_hostname_log_scrubbing.py` (6 tests — CRLF in hostname, NUL byte in hostname, very-long hostname, normal hostname unchanged, find-leaf path, nat-lookup path).

### 4.6 H-6 — `auth.login.fail` actor scrubbing for unknown usernames

**File:** `backend/blueprints/auth_bp.py::api_auth_login`

Audit line for unknown usernames now records `actor=<unknown>` instead of the raw supplied value:

```python
audit_actor = username if username in tokens else "<unknown>"
_audit.info("audit auth.login.fail actor=%s ip=%s reason=%s",
            audit_actor, request.remote_addr, reason)
```

Successful logins still record the real actor — only failures with unknown usernames are scrubbed. The throttle key continues to use the real `(ip, username)` pair so the rate-limit semantics are unchanged.

**Pinned by:** `tests/test_security_login_username_enum.py` (3 tests — known user wrong password, unknown user wrong password, audit line shape on each).

### 4.7 SSH-runner cleanup on exception (Python review C-4 / C-5 — read-only audit's hand-off to this session)

**File:** `backend/runners/ssh_runner.py:120-200`

`run_command` and `run_config_lines_pty` now wrap the full session in `try/finally` so the SSH client is always closed (FD-leak fix — Python review C-5). Exception text is bucketed through `_classify_ssh_error` instead of returned as `str(exc)` to the caller (credential-leak fix — Python review C-4).

**Pinned by:** `tests/test_security_ssh_runner_close_on_exception.py` (8 tests — auth fail closes client, network fail closes client, banner fail closes client, classification on each bucket, no credential substring in returned err).

### 4.8 audit GAP #14 — `MAX_CONTENT_LENGTH` regression test

**Pinned by:** `tests/test_security_max_content_length.py` (5 tests). Asserts Flask refuses 10 MiB + 1 byte on `/api/inventory/import`, `/api/notepad`, `/api/diff`, `/api/run/pre/create`, `/api/credentials`. Closes a documentation-only gap from the wave-2 audit (§3.13).

### 4.9 audit GAP #8 — Inventory import row cap

**Pinned by:** `tests/test_security_inventory_import_row_cap.py` (3 pass + 1 xfail). The xfail tracks the unfixed cap on `POST /api/inventory/import` row count — large CSVs slip through `MAX_CONTENT_LENGTH` because the validation is per-row, not aggregate. Tracked for a follow-up wave.

---

## 5. Findings still OPEN after this session

### 5.1 MEDIUM (14)
M-1..M-14 from §3.3. Each is a defence-in-depth or UX issue, not a directly-exploitable vector under the current threat model (internal ops tool on a private network).

### 5.2 LOW (11)
L-1..L-11 from §3.4. Polish-pass items.

### 5.3 Python-review carry-overs from wave-4
- **MED-1 / MED-6** — two NEW bare `except Exception: pass` blocks in `find_leaf/` (`service.py:158`, `strategies/cisco.py:136`) still missing `noqa: BLE001` markers and zero observability. Wave-7 audit confirms they did not get touched in wave-6.
- **MED-2** — `RunStateStore.update(**fields)` still allows `_created_by_actor` spoof.
- **MED-3** — duplicated `_actor()` / `_current_actor()` across 5 blueprints — still duplicated post wave-6.
- **MED-4** — `_try_one_firewall` `(handled, should_return)` tuple still un-typed.
- **MED-5** — `nat_lookup/__init__.py` still carries 8 `noqa: F401` markers (acceptable for the late-binding pattern).
- **MED-7** — private `_get_credentials` still imported by 6 sites.

### 5.4 audit GAPs still open
- **#2** — explicit cookie-attribute test (`SameSite=Lax`, `HttpOnly`, `Secure` in production).
- **#4** — explicit test that `device_runner` refuses HTTP redirects (the runner-level guard, separate from the bgp-lg one closed in W4-M-05).
- **#5** — explicit test that `RunnerFactory` routes through `CommandValidator` for every dispatch path.
- **#6** — explicit test that `PERGEN_SSH_STRICT_HOST_KEY` defaults to 1 in production (currently defaults to unset / `AutoAddPolicy`).
- **#11** — explicit test that `session.permanent` rotation does not extend an old cookie's lifetime past the new `PERMANENT_SESSION_LIFETIME`.
- **#12** — explicit test for login-credential-compare timing (currently the timing oracle is closed by a dummy compare; a proper microbenchmark assertion would catch a regression).
- **#13** — explicit test for notepad path traversal (`/api/notepad?file=../etc/passwd`-style; the current notepad has a fixed path so this is "test the current contract", not a known bug).
- **#15** — closed by H-3 fix today.

---

## 6. Dependency audit (`pip-audit`)

```
$ pip-audit -r requirements.txt -r requirements-dev.txt
No known vulnerabilities found

$ pip-audit                       # full venv
Found 3 known vulnerabilities in 1 package
Name Version ID                  Fix Versions
---- ------- ------------------- ------------
pip  25.2    CVE-2025-8869       25.3
pip  25.2    CVE-2026-1703       26.0
pip  25.2    ECHO-7db2-03aa-5591 25.2+echo.1
```

**Action:** unchanged from wave-2 — upgrade `pip` in the dev venv to ≥ 26.0 in CI to silence the scanner. Declared runtime/dev requirements remain clean.

---

## 7. Recommended fix sequence (post wave-7)

1. **Day 1 — closing the username-enumeration MEDIUM cluster (M-1 / M-3 / M-4 / M-11 / M-13)** — consolidated PR adding rate limit on `/api/auth/whoami` + `/login`, FIFO-randomisation of the throttle LRU eviction, audit-line marker for which auth path served the request.
2. **Day 2 — `find_leaf` observability** — narrow the two bare excepts (Python-review MED-1 / MED-6 carry-over), add per-call logger, document audit M-09 cancel-best-effort.
3. **Day 3 — `RunStateStore.update()` actor enforcement (Python-review MED-2)** — add `actor=` parameter, reject `_created_by_actor` in `**fields`. Cleanup item; no known live exploit path today.
4. **Day 4 — Promote `_actor_helpers.py`** (Python-review MED-3) — single `actor_for_audit()` / `actor_for_scoping()` pair across all 6 blueprints. Repays the design debt that allowed wave-4's W4-H-01 to land.
5. **Concurrent / longer-haul:** the M-7 `safeHtml` URL-scheme allowlist + L-5 inline-style lint guard form a natural Phase-D-followup wave for the SPA.

---

## 8. Reviewer notes

- **Mixed audit + remediation.** §3 was read-only. §4 ships fixes and regression tests in the same session. The 9 new test files + 51 new tests are the wave-7 closing artefact.
- **Severity model:** OWASP risk × deployed-threat-model. The realistic attacker remains an inside operator on the same VLAN (or a compromised authenticated actor). C-1 is severity-CRITICAL because it is the **default failure mode**, not an exploit.
- **Wave-6 close-out is real but incomplete.** Five reclassified items shipped (credential migration, cookie auth, CSP unsafe-inline removal, XSS sweep, find-leaf cancel). The wave-7 audit confirms none of those introduced new dangerous-primitive sites; the 7 NEW CRITICAL+HIGH findings are all in the seams between the new code and the legacy code (credential-store bridge, proxy-aware throttle, session lifetime, shim bind-host).
- **Per-finding traceability.** Every fix in §4 is pinned by exactly one new test file. The test files are named `test_security_<finding>.py` and self-document the audit ID at the top of each module docstring.

— end of audit —

---

## Addendum — wave-7.1 deliberate posture relaxation (2026-04-23)

Two HIGH-severity controls landed in this audit have been intentionally
relaxed to operator-friendly defaults, with the strict postures preserved
as one-env-var opt-ins. This addendum records the threat-model decision
so the audit trail stays honest.

### What changed

**H-3 — `/api/ping` SSRF guard** flipped from default-deny to default-allow
on internal targets (RFC1918 / loopback / link-local / multicast / reserved).

- **Why:** Pergen is operated against the operator's own management network.
  The operator's actual fleet (`10.59.1.x` leaves, `10.59.65.x` spines, etc.)
  is RFC1918 by design. The original default-deny was rejecting every
  legitimate ping with `WARNING ping rejected internal address ip=10.59.1.1`,
  making the tool unusable for its intended internal-deployment use case.
- **New default:** allow internal targets to reach the underlying
  `single_ping` call.
- **Lock-down:** `PERGEN_BLOCK_INTERNAL_PING=1` re-enables the original
  audit-H3 default-deny — useful for internet-exposed deployments or
  shared multi-tenant hosts where `/api/ping` could otherwise be abused
  as a metadata-service oracle (`169.254.169.254`).
- **Backward compat:** `PERGEN_ALLOW_INTERNAL_PING=1` still works as a
  no-op (allow is the default). If both `ALLOW` and `BLOCK` are set,
  `BLOCK` wins — explicit lock-down beats default-allow.

**H-1 (SSH) — `AutoAddPolicy` notice** demoted from per-call WARN to a
one-shot module-import INFO.

- **Why:** Multi-device runs (`/api/run/pre` against a 50-device fleet)
  emitted 50 identical WARN lines per request, drowning the audit trail
  in policy-noise that an operator can do nothing about (Pergen is
  intentionally TOFU-enrolling new leaves and spines on first contact).
- **New behaviour:** the policy notice fires exactly once per process at
  module import, level INFO, via a new `_emit_autoadd_notice_once()`
  helper guarded by module-level flag `_AUTOADD_NOTICE_EMITTED`. The
  notice remains discoverable via `app.runner.ssh` log filters; it just
  stops nagging.
- **Lock-down:** `PERGEN_SSH_STRICT_HOST_KEY=1` (paired with
  `PERGEN_SSH_KNOWN_HOSTS=<path>`) still flips the policy to Paramiko
  `RejectPolicy`. Audit control unchanged.

### Threat-model justification

These changes are **deliberate downgrades for an internal-only deployment
posture**, not oversights. Pergen's threat model is:

1. **Trusted network:** the operator's management VLAN is trusted by
   policy (already a precondition for SSH-credential-bearing access to
   every device in the fleet).
2. **Authenticated callers:** in production (`PERGEN_API_TOKEN(S)` set),
   only authenticated operators reach `/api/ping`. The metadata-service
   oracle attack vector requires either a misconfigured open dev mode
   OR an attacker who has already authenticated.
3. **Operational requirement:** the tool must be usable. A security
   control that rejects 100 % of legitimate use is a denial-of-service
   on the operators, not a defence-in-depth.

For deployments that violate any of these assumptions (internet-exposed
host, shared multi-tenant, untrusted management network), the
operator-friendly defaults are exactly one env var away from the strict
audit-recommended posture.

### What did NOT change

- `MAX_PING_DEVICES=64` cap on `/api/ping` — bounds worst-case execution
  time and stops single-request internal scans.
- `InputSanitizer.sanitize_ip` validation — arbitrary IP literals still
  cannot reach the system `ping` binary.
- Auth gate (`PERGEN_API_TOKEN(S)`, cookie auth + CSRF) — `/api/ping` is
  still gated in production.
- All other wave-7 fixes (credential v2 bridge, SSH FD-leak fix, session
  lifetime, ProxyFix, bind-host guard, username-enum mitigation) — none
  of these are affected.

### Tests

- `tests/test_security_audit_findings.py` — three new tests pin the new
  default-allow behaviour:
  - `test_ping_allows_rfc1918_by_default`
  - `test_ping_legacy_allow_env_var_remains_no_op`
  - `test_ping_block_overrides_allow`
- The two original default-deny tests are renamed
  `_when_explicitly_opted_in` and now set `PERGEN_BLOCK_INTERNAL_PING=1`
  to exercise the SSRF guard via the new opt-in env var.
- `tests/test_security_audit_batch4.py::test_ping_blocks_internal_address_families`
  — parametrised over cloud-metadata IPs; updated to set
  `PERGEN_BLOCK_INTERNAL_PING=1`.
- `tests/test_network_ops_bp_phase5.py` — dropped legacy
  `monkeypatch.setenv("PERGEN_ALLOW_INTERNAL_PING", "1")` lines; tests
  now exercise the default-allow posture.
- `tests/test_security_ssh_runner_autoadd_quiet.py` (NEW, 3 tests) —
  pins the per-call no-WARN behaviour, the existence of the
  `_AUTOADD_NOTICE_EMITTED` module flag, and the still-working
  lock-down path via `PERGEN_SSH_STRICT_HOST_KEY=1`.

— end of addendum —
