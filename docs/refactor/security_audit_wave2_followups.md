# Security Audit Wave-2 — Follow-up Plans

**Status:** plan only — no production code changes proposed in this doc.
Each item below is pinned by a strict `xfail` test under `tests/test_security_*.py`
that flips to a real green pass once the fix lands.

**Source:** `docs/security/audit_2026-04-22.md` (5 NEW HIGH + 9 NEW MEDIUM
findings beyond the 9 already-tracked items from wave-1).

---

## H-01 — XSS via inventory `fabric/site/hall/role` dropdowns

**Test:** `tests/test_security_xss_dropdown_columns.py` (4 strict-xfail).
**Existing plan:** `docs/refactor/xss_innerhtml_audit.md` Phase 4
(rows #2-#5 in the UNSAFE bucket).

**Delta from existing plan:** the wave-2 audit confirmed exploitability
via the open-inventory write API (#H-05). The fix is unchanged: wrap every
interpolation in `escapeHtml(...)`. Land alongside H-02 in a single
"escape every UNSAFE site" PR that flips both this test and H-02 to green.

**Estimated effort:** 0.5 day (≈12 sites edited, all in `app.js`).

---

## H-02 — XSS via find-leaf / NAT-lookup result tables

**Test:** `tests/test_security_xss_findleaf_natlookup.py` (2 strict-xfail).
**Existing plan:** `docs/refactor/xss_innerhtml_audit.md` rows #11/#13/#14.

**Delta:** confirmed reachable via hostile firewall returning HTML in NAT
rule names. **Land with H-01.**

---

## H-03 — CSRF protection on state-changing endpoints

**Test:** `tests/test_security_csrf_unsafe_methods.py` — **already passes**.

**Why it's resolved:** the audit's worst-case hypothesis (form-encoded
`text/plain` POST bypass) was tested empirically and the routes already
return 400 because `request.get_json(silent=True)` returns `None` and
the input validators fail-closed on missing `hostname`/`name` fields.

**Forward work:** the broader CSRF-via-stolen-token concern still belongs
in `docs/refactor/spa_auth_ui.md` (in-app login + HttpOnly cookie +
CSRF token). No additional plan needed here; the existing council-decided
plan covers it.

---

## H-04 — `/api/diff` per-line CPU explosion

**Test:** `tests/test_security_diff_line_dos.py` (1 strict-xfail).

**Plan:**
1. Add `_DIFF_MAX_LINES = 8192` (per side) constant in
   `backend/blueprints/runs_bp.py:333`.
2. After the byte cap, count `pre_text.count("\n")` and
   `post_text.count("\n")`; if either exceeds the cap, return 413 with
   `error="diff inputs capped at <N> lines per side …"`.
3. Update `tests/test_security_diff_dos.py` if the byte-cap test
   relies on >8192 lines (verify — it likely uses 48-byte lines so
   ~5400 lines, safely under).
4. Flip `tests/test_security_diff_line_dos.py::test_diff_rejects_pathological_line_count`
   from xfail to green.

**Estimated effort:** 0.5 day (single-file change, paired test landing).

---

## H-05 — Open inventory + credential write in non-production

**Test:** `tests/test_security_dev_boot_open_api.py` (1 strict-xfail + 2 pass).

**Plan:**
1. In `backend/app_factory.py:240` (`_install_api_token_gate`), if neither
   `PERGEN_API_TOKEN` nor `PERGEN_API_TOKENS` is set AND `config_name`
   is not `"production"`, check for `PERGEN_DEV_OPEN_API`:
   - if set → log a one-time WARN (current behaviour) and serve open.
   - if unset → `raise RuntimeError("refusing to boot with open API in
     development; set PERGEN_API_TOKEN or PERGEN_DEV_OPEN_API=1 to
     override")`.
2. Update `run.sh` to set `PERGEN_DEV_OPEN_API=1` for first-time
   contributors who haven't generated a local token yet (so the dev
   experience doesn't regress).
3. Document the new flag in `HOWTOUSE.md`.
4. Flip the strict-xfail to green.

**Estimated effort:** 0.5 day (single-file change, paired test, doc update).

---

## M-01 — RIPEStat redirect / IP allow-list

**Test:** `tests/test_security_ripestat_redirect_guard.py` (1 strict-xfail).

**Plan:** central `_safe_get(url, *, allowed_hosts={"stat.ripe.net",
"www.peeringdb.com"})` helper in `backend/bgp_looking_glass.py` that
asserts `urlparse(url).hostname in allowed_hosts` and pins
`allow_redirects=False`. Apply to both call sites at lines 9-12 and 50-56.

---

## M-02 — `/api/run/result/<run_id>` IDOR

**Test:** `tests/test_security_run_result_actor_scoping.py` (1 strict-xfail).

**Plan:** record `created_by_actor` on `RunStateStore.set()`, check it on
`get()`. Use `actor_for_request()` from `backend/security/auth.py`. Refuse
mismatched actor with 403 (or 404 to avoid existence disclosure — the test
accepts either).

---

## M-03 — `/api/reports/<run_id>?restore=1` is a GET side-effect

**Test:** `tests/test_security_report_restore_method.py` (2 strict-xfail).

**Plan:** split the `?restore=1` branch into a separate
`@reports_bp.route("/api/reports/<id>/restore", methods=["POST"])`
handler. Keep `GET /api/reports/<id>` as the read path. Flip xfail when
SPA migrates to POST too.

---

## M-05 — `ReportRepository._safe_id("")` coerces to `default`

**Test:** `tests/test_security_report_repo_empty_id.py` (2 strict-xfail).

**Plan:** in `backend/repositories/report_repository.py:130` add
`if not (run_id or "").strip(): raise ValueError("run_id is required")`.
One-line change, fully covered by the new tests.

---

## M-08 — Inventory enumeration via 400 message

**Test:** `tests/test_security_inventory_no_enumeration.py` — **already passes**.

**Why it's resolved:** the inventory service already returns a generic
400 without echoing the colliding hostname. No plan needed; the test
locks the contract going forward.

---

## M-11 — `ssh_runner` echoes paramiko exception text

**Test:** `tests/test_security_ssh_runner_no_credential_leak.py` (1 strict-xfail).

**Plan:** map paramiko exceptions to a controlled vocabulary
(`{auth_failed, network, timeout, banner_mismatch, other}`) inside
`backend/runners/ssh_runner.py:run_command`. Server-side log keeps the
original `repr(e)` for diagnosis; only the controlled label is returned
to the caller.

---

## I-04 — Parsers must not perform I/O

**Test:** `tests/test_security_parsers_no_io.py` — **17 pass**.

**Why it's resolved:** the new `backend/parsers/` package is pure logic.
The test pins this contract by stubbing `builtins.open` and `socket.socket`
to raise during every registered parser's call. Adding a new parser that
needs I/O will fail this gate.

---

## Shipping order recommendation

1. **H-04 + H-05** — both single-file, both have ready-to-flip tests.
   ~1 day combined.
2. **M-05** — one-line repository fix, clears 2 xfails.
3. **H-01 + H-02** — XSS sweep wave (escape every site identified in
   `xss_innerhtml_audit.md`); ~1 day.
4. **M-01 + M-11** — security hardening, both with unit-testable scopes.
5. **M-02 + M-03** — actor-scoping + restore-via-POST; touches the
   `RunStateStore` and routes — ~1 day combined.

After all items land, the strict-xfail count drops from 24 → 9 (the
remaining 9 are the architectural items from wave-1: token-gate
immutability, credstore migration, audit logger coverage, /health leak,
router-devices projection, SPA auth, CSP/HSTS, app decomposition).
