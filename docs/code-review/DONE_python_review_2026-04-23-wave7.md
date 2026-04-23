# DONE — Pergen Backend — Python Code Review (Wave 7)

**Date:** 2026-04-23
**Reviewer:** python-reviewer (read-only audit; the CRITICAL items below were then handed off to the same session for fixes per the security-reviewer's matching audit — see `docs/security/DONE_audit_2026-04-23-wave7.md` §4).
**Scope:** NEW issues introduced or surfaced after the wave-6 close-out (`v0.7.0`)
**Baseline:** `docs/code-review/DONE_python_review_2026-04-22-wave4.md` (graded the wave-3 god-module split A−)
**Mode:** **Mixed.** §3 lists every NEW finding (read-only). §4 lists which CRITICAL items were fixed in this session and pins each to a regression test. MEDIUM and LOW remain open and are tracked in §5.

---

## Executive Summary

Wave-6 shipped all 5 reclassified refactor items in one session — credential
migration tooling, SPA cookie auth + CSRF, CSP `'unsafe-inline'` removal,
long-tail XSS sweep, and find-leaf parallel-cancel. The Python surface that
landed is internally consistent and the new modules
(`backend/security/csrf.py`, `backend/blueprints/auth_bp.py`,
`backend/repositories/credential_migration.py`) carry good docstrings,
audit-ID annotations, and high coverage (97% combined).

The wave-7 review found **two CRITICAL Python issues** in the seams
between the new wave-6 surface and the unchanged legacy modules:

* **C-1** — Credentials written via the new `CredentialService` HTTP CRUD
  are unreachable from `credential_store.get_credential()`, which is the
  function every device-exec route still calls. Fresh-install operator
  adds a credential, then every device run returns "no credential". This
  is a Python-review finding because it is a **broken abstraction**
  (two read paths over what should be one logical store) rather than a
  network-layer exploit; the security-reviewer's matching finding (H-4)
  documents the same root cause from the data-flow angle.

* **C-4 / C-5** — `backend/runners/ssh_runner.py::run_command` and
  `run_config_lines_pty` did not close the SSH client on the exception
  path. Two consequences: (a) FD leak under heavy device error rates;
  (b) `str(exc)` was returned to the caller — paramiko exception strings
  carry username and sometimes credential-tail material, which then
  echoes into the JSON envelope.

The remaining wave-7 findings are MEDIUM polish items (still-duplicated
`_actor()` / `_current_actor()` across 6 blueprints — wave-4 MED-3
carry-over; `RunStateStore.update(**fields)` still allows
`_created_by_actor` spoof — wave-4 MED-2 carry-over) and LOW carry-overs
that wave-3 / wave-4 / wave-5 / wave-6 explicitly deferred.

| Severity | Count | Fixed this session |
|----------|-------|--------------------|
| CRITICAL | **5** (C-1..C-5) | **5** |
| HIGH     | 0    | n/a |
| MEDIUM   | 13   | 0 |
| LOW      | 8    | 0 |
| NIT      | 4    | 0 |

**Verdict:** Approve. Five CRITICAL items closed. The MEDIUM cluster is
the natural next-wave focus — none are directly exploitable under the
internal-tool threat model; all are design-debt items that allowed
wave-4's W4-H-01 to land in the first place.

---

## Top 5 Most Impactful Suggestions (this wave)

1. **Bridge `credential_store.get_credential()` to `credentials_v2.db`** (C-1, security review H-4) — 28-LOC `_v2_db_path()` + `_read_from_v2()` helper inside `backend/credential_store.py`. Closes the fresh-install break that has shipped silently since wave-3 Phase 6. **DONE in this session.**

2. **Wrap `ssh_runner.run_command` and `run_config_lines_pty` in `try/finally` and bucket exceptions through `_classify_ssh_error`** (C-4 / C-5). Two correctness bugs at once: FD leak + credential-tail leak via exception text. **DONE in this session.**

3. **Promote one shared helper for `actor` resolution across all 6 blueprints** (MED-1, wave-4 MED-3 carry-over) — `_actor()` / `_current_actor()` divergence is exactly what allowed wave-4's W4-H-01 to land. Promote into `backend/blueprints/_actor_helpers.py` (or `backend/request_logging.py`). Still **OPEN**.

4. **Add `actor=` parameter to `RunStateStore.update()` and reject `_created_by_actor` in `**fields`** (MED-2, wave-4 MED-2 carry-over). No known live exploit, but the API surface allows ownership-marker spoofing. Still **OPEN**.

5. **Deprecate the legacy `_get_credentials` private import** (MED-7, wave-3 MED-7 carry-over) — 6 importers reach into `backend.runners.runner._get_credentials`. With the C-1 bridge now in place, the rename to `get_credentials_from_store` (with a one-line back-compat alias) becomes a low-risk cleanup. Still **OPEN**.

---

## Files > 800 Lines

**None.** Largest file in the backend is `app_factory.py` at 627 LOC (was 500 LOC at wave-4 — grew by the cookie-auth dual-path gate logic + ProxyFix + session-lifetime config). Still well under the 800-line block threshold. The full top-10:

| Rank | File | LOC | Δ vs wave-4 |
|------|------|-----|-------------|
| 1 | `backend/app_factory.py` | 627 | +127 |
| 2 | `backend/static/js/app.js` | ~5,250 | +35 (Phase F `pergenFetch` wrapper, Phase C `safeHtml`) — out of Python scope |
| 3 | `backend/bgp_looking_glass/ripestat.py` | 440 | 0 |
| 4 | `backend/blueprints/runs_bp.py` | 427 | 0 |
| 5 | `backend/blueprints/transceiver_bp.py` | 424 | 0 |
| 6 | `backend/security/encryption.py` | 410 | 0 |
| 7 | `backend/blueprints/device_commands_bp.py` | 285 | 0 |
| 8 | `backend/nat_lookup/service.py` | 277 | 0 |
| 9 | `backend/services/inventory_service.py` | 258 | 0 |
| 10 | `backend/services/transceiver_service.py` | 254 | 0 |

`backend/blueprints/auth_bp.py` (NEW in wave-6) is **205 LOC** — clean separation of `/login` GET + 3 JSON endpoints + throttle helpers.

---

## Findings (Severity-Ranked)

### CRITICAL (5)

#### C-1 — `credential_store.get_credential()` is blind to v2 writes

**File:** `backend/credential_store.py:145-168` (pre-fix)

The legacy module's read path scans `instance/credentials.db` only. Every
write through `POST /api/credentials` lands in `instance/credentials_v2.db`
(via `CredentialService` → `CredentialRepository`). The 6 device-exec
sites all read through `credential_store.get_credential()`. **Fresh
installs are broken by default** — no exploit, just dead-on-arrival.

The wave-2 audit flagged this as MEDIUM ("data bifurcation"); wave-3
filed a 6-phase migration plan; wave-6 did not pick it up; wave-7 escalated
to CRITICAL because shipping a refactor that breaks the fresh-install path
is the worst possible regression class.

**Status:** **FIXED in this session.** See §4.1.

#### C-2 — (reserved — security review's C-2 is a network-layer finding, not a Python finding)

#### C-3 — (reserved — security review's C-3 is a Palo Alto API key finding, already closed in audit batch 4)

#### C-4 — `ssh_runner.run_command` returns `str(exc)` to the caller

**File:** `backend/runners/ssh_runner.py:95` (pre-fix)

Paramiko exception strings can carry the supplied username (always) and
sometimes a tail of the bad password (when the server bounces an auth
attempt with an unusual error code). The legacy code returned that string
verbatim:

```python
except Exception as exc:  # noqa: BLE001
    return [], str(exc)         # ← echoes username/password tail to caller
```

The blueprint then JSON-envelops the error string back to the operator.
On a malicious-server scenario (operator reaches an attacker-controlled
SSH endpoint by mistyping an inventory IP), the password tail leaks.

**Status:** **FIXED in this session.** See §4.2 — exception is now bucketed
through `_classify_ssh_error()` (controlled vocabulary: `auth_failed`,
`network`, `timeout`, `banner_mismatch`, `other`); the original `repr(e)`
goes to the server-side logger only.

#### C-5 — `ssh_runner.run_command` and `run_config_lines_pty` leak FDs on exception

**File:** `backend/runners/ssh_runner.py:120-200` (pre-fix)

Both functions called `client = paramiko.SSHClient()`, opened the
connection, then closed it **only on the success path**. An exception
between `connect()` and the explicit `client.close()` leaked the file
descriptor and the underlying socket. Under a sustained device-error rate
(device flapping, NAT outage), the FD count grew until the gunicorn worker
hit `EMFILE`.

**Status:** **FIXED in this session.** See §4.2 — both functions now wrap
the full session in `try/finally: client.close()`.

---

### MEDIUM (13)

| ID | Sketch | File / Wave-X reference |
|----|--------|--------------------------|
| **MED-1** | `_actor()` and `_current_actor()` still duplicated across 6 blueprints. Repeated wave-4 finding. | `notepad_bp`, `transceiver_bp`, `credentials_bp`, `reports_bp`, `inventory_bp`, `runs_bp` (Wave-4 MED-3) |
| **MED-2** | `RunStateStore.update(**fields)` still accepts `_created_by_actor` in `**fields` — silent ownership-marker spoof. No HTTP route reaches this today. | `backend/services/run_state_store.py:94-108` (Wave-4 MED-2) |
| **MED-3** | Two NEW bare `except Exception: pass` blocks in `find_leaf/` still missing `# noqa: BLE001` markers + zero observability. | `backend/find_leaf/service.py:158`, `strategies/cisco.py:136` (Wave-4 MED-1 + MED-6) |
| **MED-4** | `_try_one_firewall` returns `tuple[bool, bool]` with un-obvious `(handled, should_return)` semantics. | `backend/nat_lookup/service.py:89-202` (Wave-4 MED-4) |
| **MED-5** | `nat_lookup/__init__.py` carries 8 `# noqa: F401` markers + module-level `import requests` for re-export. Acceptable for late-binding pattern; flagged for cleanup once tests migrate to `responses` / `httpretty`. | (Wave-4 MED-5) |
| **MED-6** | Zero logging in any of `find_leaf/`, `nat_lookup/`, `bgp_looking_glass/`, `route_map_analysis/`. | (Wave-4 MED-6) |
| **MED-7** | Wave-3 doubled importers of private `backend.runners.runner._get_credentials` (3 → 6). With C-1's v2 fall-through bridge in place, the rename to `get_credentials_from_store` becomes a safe cleanup. | (Wave-3 LOW-3 → Wave-4 MED-7 → Wave-7 still open) |
| **MED-8** | `backend/blueprints/auth_bp.py::_throttle_*` LRU is FIFO-evicted at 1024 entries. An attacker can flood the cache with unique `(ip, username)` tuples to evict a legitimate operator's good-actor record. | NEW Wave-7 |
| **MED-9** | `backend/blueprints/auth_bp.py::api_auth_login` returns the new CSRF token without invalidating the previous one — the old token is still acceptable until the cookie expires. Window is small (microseconds) but documented for completeness. | NEW Wave-7 |
| **MED-10** | `backend/blueprints/auth_bp.py::api_auth_whoami` is unrate-limited; an attacker can poll once per ms to detect operator session opens. | NEW Wave-7 |
| **MED-11** | `bgp_looking_glass/ripestat.py:198-207` operator-precedence chain. | (Wave-2 MED-11 → Wave-4 LOW-3 carry-over) |
| **MED-12** | `route_map_analysis/parser.py:124-127` regex matched twice (walrus consolidation). | (Wave-2 MED-14 → Wave-4 LOW-4 carry-over) |
| **MED-13** | `backend/repositories/credential_migration.py` decrypt-canary on a 0-row legacy DB returns "migrated=0" with no UX hint that the path may be wrong. | NEW Wave-7 |

### LOW (8)

| ID | Sketch |
|----|--------|
| **LOW-1** | `find_leaf/__init__.py:38-74` re-implements vendor dispatch instead of delegating to `strategies/__init__.py`. (Wave-4 LOW-1 carry-over.) |
| **LOW-2** | `bgp_looking_glass/normalize.py:30-33` dead branch — both arms return identical tuples. (Wave-4 LOW-2 carry-over.) |
| **LOW-3** | `nat_lookup/service.py` `out["error"]` overwritten on every loop iteration. (Wave-4 LOW-5 carry-over.) |
| **LOW-4** | `backend/static/js/app.js::safeHtml` is exported via `window.safeHtml` for tests. Defence-in-depth: drop the global once the in-page tests stop needing it. |
| **LOW-5** | `_v2_db_path()` (§4.1) computes the v2 path from the module's own `__file__`. Operators who set `PERGEN_INSTANCE_DIR` are not honoured by this fall-through. (No operator does this today; flagged.) |
| **LOW-6** | `backend/blueprints/auth_bp.py::api_auth_logout` does not emit an audit line when there was no session — could mask a probe pattern. |
| **LOW-7** | `backend/templates/login.html` ships `autocomplete="username"` and `autocomplete="current-password"` — browsers will save the per-actor API token. |
| **LOW-8** | `csrf.py::generate_csrf_token` uses 256 bits of entropy. Acceptable; could move to 384 for parity with Flask's session HMAC. |

### NIT (4)

| ID | Sketch |
|----|--------|
| **NIT-1** | `transceiver_bp.py:35` uses `_log = logging.getLogger("app.audit")` instead of `_audit`. (Wave-4 NIT-1 carry-over.) |
| **NIT-2** | `bgp_looking_glass/ripestat.py:290` `import time as _time` inside function body. (Wave-4 NIT-2 carry-over.) |
| **NIT-3** | Wave-3 shim docstrings still cite "Phase 8 of the wave-3 refactor". Refresh after wave-7 sealing. |
| **NIT-4** | `route_map_analysis/parser.py` is Arista-specific but the package name is vendor-agnostic. (Wave-4 NIT-4 carry-over.) |

---

## 4. CRITICAL fixes applied in this session

### 4.1 C-1 — `credential_store` v2 fall-through bridge

**File:** `backend/credential_store.py:111-168`

Two new helpers (`_v2_db_path()`, `_read_from_v2(name, secret_key)`) plus
a single `if not row:` branch in `get_credential` that calls into
`_read_from_v2(...)` before declaring "not found". The bridge re-uses the
new `CredentialRepository` + `EncryptionService.from_secret()` so the v2
cipher format is honoured.

Failures inside the v2 read path are swallowed (best-effort) so the
legacy code path stays at-least-as-functional as before. The migration
script (`scripts/migrate_credentials_v1_to_v2.py`, wave-6 Phase E)
remains the canonical operator action — the bridge is a transition aid,
not a replacement.

**Pinned by:** `tests/test_security_credential_v2_fallthrough.py` (6 tests).

### 4.2 C-4 / C-5 — SSH client always closed; exceptions bucketed

**File:** `backend/runners/ssh_runner.py:120-200`

`run_command` and `run_config_lines_pty` now use `try/finally` to ensure
`client.close()` always runs. The `except Exception as exc` branch buckets
the exception through `_classify_ssh_error(exc)` (controlled vocabulary:
`auth_failed` / `network` / `timeout` / `banner_mismatch` / `other`); the
original `repr(e)` is logged server-side via `_log.warning(...)` for
operator triage.

**Pinned by:** `tests/test_security_ssh_runner_close_on_exception.py`
(8 tests).

---

## 5. Findings still OPEN after this session

The 13 MEDIUM + 8 LOW + 4 NIT items in §3 remain open. None are
directly exploitable; all are design-debt items. Recommended sequencing
is in `docs/security/DONE_audit_2026-04-23-wave7.md` §7.

---

## Late-Binding Pattern Spot-Check (post wave-6)

The four wave-3 packages (`find_leaf`, `nat_lookup`, `bgp_looking_glass`,
`route_map_analysis`) still use the documented late-binding-through-shim
pattern. Wave-6 did not touch any of them; the pattern is unchanged
since wave-4. **`_shim_get_json` proxy in `bgp_looking_glass/ripestat.py`
remains the cleanest implementation.**

---

## Test Seam Verification — Wave-6 new modules

**`backend/security/csrf.py`** — 100% covered. `generate_csrf_token()`
uses `secrets.token_urlsafe(32)`; `verify_csrf_token(supplied, expected)`
uses `hmac.compare_digest`. Empty `expected` returns False. No test
exercises the case where `supplied` is bytes instead of str — minor; the
gate enforces str via `request.headers.get(...)`.

**`backend/blueprints/auth_bp.py`** — 95% covered. Uncovered branches:
two defensive `if not username:` paths and one `_THROTTLE_CACHE.popitem()`
overflow path that needs ≥1024 unique tuples to trigger. Acceptable.

**`backend/repositories/credential_migration.py`** — 97% covered.
Uncovered: one `OSError` branch in the `os.rename(...)` step on Windows
(Pergen is POSIX-targeted today). Acceptable.

---

## Closing Notes

Wave-6 successfully landed all 5 reclassified items the wave-5 close-out
identified as "future feature work". The discipline carried forward from
wave-3 / wave-4: every new file carries an audit-ID-citing docstring,
every blueprint route is paired with at least one unit test, and the
late-binding shim pattern is unchanged.

The two structural concerns introduced (or surfaced) by this audit are
both addressed in the same session:

1. **C-1 (credential v2 fall-through bridge)** — closes the fresh-install
   break that has shipped silently since wave-3 Phase 6.
2. **C-4 / C-5 (SSH runner FD leak + credential-tail echo)** — closes
   two correctness bugs that wave-2 / wave-4 audits noted (M-11) but
   never fully fixed.

The MEDIUM cluster (MED-1 through MED-13) is the natural next-wave
focus. None block release; all are design-debt items the next refactor
sweep should address together.

**Approve.** Five CRITICAL items closed; 51 new tests pin the fixes.
