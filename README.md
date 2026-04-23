# Pergen — Network device panel

> **`refactor/ood-tdd` branch — phases 0–13 + audit-wave-1 + parse_output
> refactor (8 phases) + audit-wave-2 + wave-3 god-module split + wave-4
> actor-scoping followups + wave-5 close-out + wave-6 reclassified-items
> shipped + wave-7 audit followup (2026-04-23).**
>
> Pergen has been migrated to a strict OOD layout (App Factory +
> 12 Blueprints + service layer + RunnerFactory + ParserEngine) on top
> of a TDD safety net. The legacy 1,577-line `backend/app.py` monolith
> is an **87-line shim**; the legacy 1,552-line `backend/parse_output.py`
> god module is now a **151-line shim** delegating to the
> 31-module `backend/parsers/` package via a vendor-routed `Dispatcher`.
> Every route lives in a per-domain blueprint registered through
> `create_app()`.
>
> Post-decomposition, parallel audits (`security-reviewer`,
> `python-reviewer`, `coverage analysis`, `e2e-runner`) surfaced and
> closed **38 findings in wave 1**, **49 in wave 2**, **24 in wave 3**,
> **6 in wave 4**, **5 reclassified items in wave 6**, and **7
> CRITICAL+HIGH in wave 7** (1 CRITICAL + 6 HIGH security + 2 CRITICAL
> Python — credential v2 fall-through bridge, SSH runner FD leak,
> proxy-aware throttle, bounded session lifetime, `__main__` bind guard,
> audit-log scrubbing, username-enum closure).
>
> Every existing API still ships unchanged — **1,888 pytest tests + 1
> strict xfail + 54 Vitest + 100 Playwright** (verified 2026-04-23
> wave-7.10) lock the response shapes byte-for-byte across all 28
> golden parser snapshots.
>
> **Coverage:** **87 %** on the parser surface; **92 %** on the 4 new
> wave-3 packages; **97 %** on the wave-6 modules (auth_bp, csrf,
> credential_migration); **100 %** on extracted frontend helpers
> (`subnet.js`, `utils.js`); **90.50 %** whole-project (was 74.94 %
> pre-refactor, +15.56 pp net); **91.28 %** on the OOD-scoped layer
> (`make cov-new`, gate 85).
>
> **Refactor program FULLY COMPLETE** — wave-6 shipped all 5 reclassified
> items in a single dedicated session: credential migration tooling
> (`scripts/migrate_credentials_v1_to_v2.py`), SPA cookie auth + CSRF
> (Council Option B, opt-in via `PERGEN_AUTH_COOKIE_ENABLED=1`), CSP
> `'unsafe-inline'` removal (240 inline styles → CSS classes; final
> CSP locked down to `style-src 'self'`), long-tail XSS sweep with
> CI lint guard + classifier + 5 audit-confirmed XSS sites closed,
> and find-leaf parallel-cancel (10s → 0.35s). Every plan in
> `docs/refactor/` is now `DONE_*`-prefixed.
>
> **Latest (wave-7, 2026-04-23):** post-`v0.7.0` security + python
> reviews surfaced 1 CRITICAL + 6 HIGH (audit) + 2 CRITICAL (python)
> findings in the seams between the wave-6 surface and the legacy
> modules. **All 9 fixed in the same session**, pinned by 9 new test
> files (51 tests). The 12 brittle Playwright specs failing at wave-6
> close were stabilised with **test-only changes** — suite is back to
> **100 / 100 green**. New env knobs:
> `PERGEN_SESSION_LIFETIME_HOURS` (default 8h, was 31 days),
> `PERGEN_SESSION_IDLE_HOURS`, `PERGEN_TRUST_PROXY`,
> `PERGEN_DEV_BIND_HOST` (default `127.0.0.1`),
> `PERGEN_DEV_ALLOW_PUBLIC_BIND`. See
> [`patch_notes.md` v0.7.1](./patch_notes.md) for the full changelog.
>
> **Recent UI/Boot work**: the Phase-13 CSP (`script-src 'self'`) is
> served by `backend/static/js/{theme-init,app}.js` + the vendored
> `backend/static/vendor/jszip.min.js`. `run.sh` defaults to
> `FLASK_APP=backend.app_factory:create_app`; booting
> `FLASK_APP=backend.app` directly serves 404 on every URL. **Wave-7
> (2026-04-23):** `python -m backend.app __main__` now refuses any
> non-loopback bind unless `PERGEN_DEV_ALLOW_PUBLIC_BIND=1` is set —
> closes the latent foot-gun where the shim could have exposed every
> route publicly without auth if a future contributor restored
> blueprint imports there.
>
> See [`patch_notes.md`](./patch_notes.md) for the per-phase log,
> [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the layered design,
> [`HOWTOUSE.md`](./HOWTOUSE.md) for the operational guide,
> [`FUNCTIONS_EXPLANATIONS.md`](./FUNCTIONS_EXPLANATIONS.md) for the
> per-class reference, [`TEST_RESULTS.md`](./TEST_RESULTS.md) for
> the full test matrix, and
> [`docs/security/DONE_audit_2026-04-23-wave7.md`](docs/security/DONE_audit_2026-04-23-wave7.md)
> for the wave-7 audit deep-dive.

## Refactor at a glance (Phase 12 final shape)

| Layer | Module | Coverage |
|-------|--------|----------|
| App Factory | `backend/app_factory.py` (auth gate + path-aware service rebind) | 98 % |
| Blueprints  | `backend/blueprints/` (12 files: health, inventory, notepad, commands, network_ops, credentials, bgp, network_lookup, transceiver, device_commands, runs, reports) | 88–100 % |
| Services    | `backend/services/` (device / credential / inventory / notepad / report / transceiver / run_state_store) | 90–100 % |
| Repositories | `backend/repositories/` (credential / inventory / notepad / report) | 88–98 % |
| Runners | `backend/runners/` (Arista eAPI, Cisco NX-API, SSH, interface_recovery) | 51–86 % |
| Parsers | `backend/parsers/` (31 modules: `common/`, `arista/`, `cisco_nxos/`, `generic/`, `dispatcher.py`, `engine.py`) + `backend/parse_output.py` (151-line shim) | **87 %** (was 53 % pre-wave-2) |
| Pure utils | `backend/utils/` (interface_status, transceiver_display, bgp_helpers, ping) | 87–97 % |
| Security | `backend/security/` (sanitizer / validator / encryption — PBKDF2 ≥ 600k, AES-128-CBC + HMAC) | 90–92 % |
| Logging | `backend/logging_config.py` + `backend/request_logging.py` (CSP + HSTS) | 82–95 % |
| Config | `backend/config/app_config.py` (placeholder dedup + min-length enforcement) | 89 % |

`backend/app.py` final size: **87 lines** (was 1,577 — 95 % reduction).

### Audit hardening (post-Phase 13 batches 1–4)

| ID | Severity | Fix |
|----|----------|-----|
| **C1** | CRITICAL | API token gate is **fail-closed in production**: `create_app("production")` raises `RuntimeError` unless `PERGEN_API_TOKEN(S)` is set with ≥32-char tokens. Dev/test stay opt-in (WARN logged). Constant-time compare via `hmac.compare_digest`. |
| **C2** | CRITICAL | Per-actor token routing via `PERGEN_API_TOKENS=alice:tok,bob:tok`. The matched actor is stored on `flask.g.actor` and recorded in `audit ... actor=<name> ...` log lines for accountability. |
| **C2-pre** | CRITICAL | Eliminated dual `SECRET_KEY` defaults — `ProductionConfig.validate()` rejects historic strings + enforces 16+ char length. |
| **C3** | CRITICAL | `credentials_bp` wires through `CredentialService` + `EncryptionService` (AES-128-CBC + HMAC, PBKDF2 600k). The legacy `backend/credential_store.py` base64 fallback is **removed entirely** — `cryptography` is now a hard import (raises at module load if absent). |
| **C4** | CRITICAL | `PERGEN_REQUIRE_DESTRUCTIVE_CONFIRM=1` (always-on in production) requires `X-Confirm-Destructive: yes` on transceiver/recover and clear-counters. |
| **H1** | HIGH | `defusedxml` is a hard requirement (declared in `requirements.txt`). The silent fallback to `xml.etree` is removed — XXE / billion-laughs surface eliminated. |
| **H1-ssh** | HIGH | SSH `RejectPolicy` opt-in via `PERGEN_SSH_STRICT_HOST_KEY=1` + `PERGEN_SSH_KNOWN_HOSTS=<path>`. Default `AutoAddPolicy` is the intentional behaviour for internal device enrollment; the notice now fires once per process at module-import (wave-7.1). |
| **H1-encap** | HIGH | `InventoryService.csv_path` and `InventoryRepository.csv_path` are public read-only properties. |
| **H2** | HIGH | Device HTTPS to Arista/Cisco/Palo Alto skips TLS verification by design — fleet devices present self-signed certs. Single source of truth: `DEVICE_TLS_VERIFY` in `backend/runners/_http.py`. Public APIs (RIPE, PeeringDB) keep `verify=True`. |
| **H2-bind** | HIGH | `/api/run/device`, `/api/run/pre`, `/api/arista/run-cmds`, `/api/custom-command` now **resolve the device from inventory** (audit pattern previously only on `transceiver/*`). Caller-supplied `credential`, `vendor` and `model` are ignored. |
| **H3** | HIGH | **Wave-7.1 deliberate posture change.** `/api/ping` now ALLOWS internal targets (RFC1918 / loopback / link-local / multicast / reserved) by default — Pergen is operated against the operator's own management network and the original default-deny was making the tool unusable for its intended use case. Set `PERGEN_BLOCK_INTERNAL_PING=1` to re-enable the audit-H3 SSRF guard for an internet-exposed deployment; the legacy `PERGEN_ALLOW_INTERNAL_PING=1` env var remains a no-op for backward compat. |
| **H3-cred** | HIGH | `runner._get_credentials` runs the credential name through `InputSanitizer` before any DB lookup; rejects log-injection / control-byte names. |
| **H4** | HIGH | `CredentialService.delete` validates the name (mirrors `set()`), preventing CRLF/control-byte names from forging audit log lines. |
| **H4-mass** | HIGH | Inventory writes go through `validate_device_row()` — `InputSanitizer` per field + mass-assignment guard rejects unknown keys. |
| **H5** | HIGH | `find-leaf` / `find-leaf-check-device` / `nat-lookup` envelopes return generic error strings; raw exception text only goes to server logs. |
| **H6** | HIGH | `RunStateStore` is thread-safe (`RLock`), returns deep copies, supports TTL (1 h default) + FIFO eviction (1024 default). |
| **H7** | HIGH | `transceiver/recover` and `clear-counters` resolve the device from inventory by hostname/ip; caller-supplied `credential` field is ignored. |
| **H8** | HIGH | Credential DB chmodded to 0o600 + `PRAGMA secure_delete = ON`; instance-dir created with `umask 0o077`. |
| **H9** | HIGH | `ReportRepository._report_path` uses `pathlib.Path.is_relative_to` (POSIX + Windows-safe). |
| **M1** | MED | `/api/nat-lookup` `debug=true` requires `PERGEN_ALLOW_DEBUG_RESPONSES=1` (prevents Palo Alto API body leak). |
| **M2** | MED | Error envelopes return generic messages — `str(exception)` never echoed. |
| **M4** | MED | `/api/diff` rejects inputs > 256 KB per side (prevents O(n·m) `difflib` lockup). |
| **M6** | MED | Legacy `credential_store` `init_db` now chmods the SQLite file to `0o600` on POSIX. |
| **M8** | MED | Every response carries CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy. |
| **M10** | MED | `_PBKDF2_ITERS = 600_000` (was 200,000; OWASP 2023 minimum). |
| **M11** | MED | Arista runCmds dict-form whitelist — non-`enable` dicts only forward `{cmd}`; injection vectors stripped. |
| **L1** | LOW | `route-map/run` per-device errors log full detail server-side; envelope stays generic. |
| **A09** | INFO | Audit log channel (`app.audit`) records `actor=<name>` on every credential set/delete and interface bounce (audit C-2). |
| **W7-C-1** / **W7-H-4** | CRITICAL / HIGH | (Wave-7, 2026-04-23) `credential_store.get_credential()` falls through to `credentials_v2.db` via new `_v2_db_path()` + `_read_from_v2()` helpers when the legacy DB has no row — closes the fresh-install device-exec break for operators who only used the new HTTP CRUD. |
| **W7-H-1** | HIGH | (Wave-7) `werkzeug.middleware.proxy_fix.ProxyFix` mounted only when `PERGEN_TRUST_PROXY=1` so the login throttle can key on the real client IP behind nginx / Caddy / cloud LB without naively trusting `X-Forwarded-For` from un-proxied deployments. |
| **W7-H-2** | HIGH | (Wave-7) Session cookie lifetime bounded at 8h via `PERGEN_SESSION_LIFETIME_HOURS` (was Flask's 31-day default); idle-timeout enforced via `PERGEN_SESSION_IDLE_HOURS`; cookie-auth branch clears the session and emits `audit auth.session.expired` on overflow. |
| **W7-H-3** | HIGH | (Wave-7) `python -m backend.app __main__` refuses any non-loopback bind unless `PERGEN_DEV_ALLOW_PUBLIC_BIND=1` is set; binds via `PERGEN_DEV_BIND_HOST` (default `127.0.0.1`). Closes the latent foot-gun where the shim could expose every route publicly without auth. |
| **W7-H-5** | HIGH | (Wave-7) Audit-log emission on find-leaf / nat-lookup routes scrubs control characters via a small `_safe_audit_str(...)` helper before formatting — closes the audit-log injection vector for inventory rows seeded from outside the app. |
| **W7-H-6** | HIGH | (Wave-7) `auth.login.fail` audit line records `actor=<unknown>` for usernames that are not in the configured token map — closes the username-existence oracle via audit-log volume. |
| **W7-py-C-4** / **W7-py-C-5** | CRITICAL | (Wave-7, python review) `backend/runners/ssh_runner.py` `run_command` and `run_config_lines_pty` now wrap the full session in `try/finally: client.close()` (FD-leak fix) and bucket exceptions through `_classify_ssh_error()` (controlled vocabulary, no credential-tail leak via `str(exc)`). |

### Phase-13 hardening (preserved)

* **Command path** — every endpoint that forwards a string to a
  network device (`/api/arista/run-cmds`, `/api/custom-command`, the
  SSH branch of `runner.py`) goes through `CommandValidator`
  before transport. The validator NFKC-normalises the input,
  strips leading whitespace, rejects embedded `\n`/`\r`, and enforces
  the `show`/`dir` allowlist.
* **Network reachability** — `/api/ping` validates each IP via
  `InputSanitizer.sanitize_ip` before invoking `subprocess.run` and
  caps the device list at 64 (audit H3 adds the SSRF guard on top).
* **NAT lookup** — Palo Alto API key is delivered via the
  `X-PAN-KEY` HTTP header (no longer leaked into URL access logs);
  XML parsing uses `defusedxml` to defeat XXE / Billion-Laughs
  payloads.
* **Persistence** — `NotepadRepository.update` is fully atomic under
  concurrent writers; `ReportRepository` rejects path-traversal
  `run_id` values (audit H9 hardens with `pathlib.is_relative_to`);
  `CredentialRepository` keeps a persistent `:memory:` SQLite
  connection so schema and rows survive across service calls.
* **Crypto integrity** — `_key_expand_128` raises `ValueError` on
  bad key length so the guard survives `python -O`. `Encryption`
  `from_secret('')` raises `ValueError` (fail-closed).

A web panel for pre/post checks, NAT lookup, Find Leaf, BGP Looking Glass, route-map comparison, transceiver checks, and inventory management. Single CSV inventory, encrypted credentials, and hierarchical device selection (Fabric → Site → Hall → Role).

![Home](backend/static/screenshots/home.png)

## Features

| Feature | Description |
|--------|-------------|
| **Pre/Post Check** | Capture device state before and after changes; compare diffs, save reports, export as ZIP. Interface consistency view shows devices as columns with up/down status per interface. |
| **Live Notepad** | Single shared plain-text notepad; everyone sees and edits the same content. Changes sync every few seconds (polling). No formatting. |
| **NAT Lookup** | Find NAT rule and translated IP for a source/destination pair via Palo Alto firewalls; link to BGP page with translated prefix. |
| **Find Leaf** | Locate which leaf switch has a given IP in the fabric (uses devices with tag `leaf-search`). |
| **BGP / Looking Glass** | Prefix or AS lookup via RIPEStat: status, RPKI, visibility, history diff. Per-prefix best two AS paths from one router (with router icon viz). WAN RTR search: which WAN routers have `router bgp <AS>` in config. |
| **REST API** | Run single or multi eAPI (Arista) requests on selected devices. |
| **Transceiver Check** | SFP/optics DOM (temp, TX/RX power) per interface on **Arista EOS** and **Cisco NX-OS** (NX-API). Merges interface status for status, flap count, **CRC / input errors** (`errors` column as `crc/in`), and **Last Flap** as `DDMMYYYY-HHMM` when a timestamp is available. Cisco uses `show interface` detail where needed for flap/CRC counters. **Interfaces with error in status** lists err-disabled-style ports; **Recover** (bounce) and **clear counters** use icon buttons with tooltips. Recovery and clear-counters are **only allowed for inventory role `Leaf`** on host ports **Ethernet1/1–Ethernet1/48** (or `1/1`–`1/48`); enforced in the API. Requires a **basic** (username/password) credential, not API-key-only. |
| **Credential** | Store and manage login credentials (encrypted); reference by name in inventory. |
| **DCI / WAN Routers** | Compare route-maps on Arista DCI/WAN routers; search by prefix. |
| **Subnet Divide Calculator** | Visual subnet calculator: network + mask, divide/join subnets in a table. Inspired by [davidc/subnets](https://github.com/davidc/subnets) — thank you. |
| **Inventory** | Manage devices: hostname, IP, fabric, site, hall, vendor, model, role, tag. |

## Screenshots

Order: Home → Navigation (event popups) → Pre/Post Check → Pre/Post consistency → NAT Lookup → Find Leaf → BGP (lookup, Looking Glass table, WAN paths) → Transceiver → Credential → DCI/WAN Routers → Inventory.

**Home** — 3×3 feature cards

![Home](backend/static/screenshots/home.png)

**Navigation** — Successful operations popup

<img src="backend/static/screenshots/success-popup.png" width="33%" alt="Success popup" />

**Navigation** — Errors popup (connection refused, only Arista EOS supported)

<img src="backend/static/screenshots/errors-popup.png" width="33%" alt="Errors popup" />

**Pre/Post Check** — Phase, filters, device list, Run PRE/POST

![Pre/Post Check](backend/static/screenshots/prepost-check.png)

**Pre/Post** — BGP/IS-IS shortfall (DOWN interfaces) and interface consistency (column layout)

![Pre/Post consistency](backend/static/screenshots/prepost-consistency.png)

**Export ZIP (Pre/Post)** — On the Pre/Post results page, use **Export as ZIP (HTML + styles)** to download a ZIP file containing a self-contained HTML report. The report includes: the main results table (hostname, IP, vendor, model, parsed fields), BGP/IS-IS shortfall (interfaces DOWN), interface consistency (devices as columns, status per interface), ports flapped in the last 24 hours, and the PRE vs POST diff section. Styles are embedded so the ZIP can be opened offline in any browser.

**NAT Lookup** — Source/Destination IP, results with "Open on BGP page" link

![NAT Lookup](backend/static/screenshots/nat-lookup.png)

**Find Leaf** — Search by IP, found devices, leaf details

![Find Leaf](backend/static/screenshots/find-leaf.png)

**BGP / Looking Glass** — Prefix or AS input, favourites, status cards

![BGP Lookup](backend/static/screenshots/bgp-lookup.png)

**BGP** — Looking Glass (RIS peers) and BGP play (path changes)

![BGP Looking Glass](backend/static/screenshots/bgp-looking-glass.png)

**BGP** — WAN RTR match table, visibility, per-prefix paths (Path 1 & 2)

![BGP WAN paths](backend/static/screenshots/bgp-wan-paths.png)

**Transceiver Check** — Fabric/site/hall/role filters, device multi-select, main table (hostname, interface, description, optics, status, Last Flap, Flap, CRC/Input Err), and optional error-status table with recover/clear actions for eligible Leaf host ports.

![Transceiver](backend/static/screenshots/transceiver.png)

**Credential** — Add/Update form and credential table (Name, Method)

![Credential](backend/static/screenshots/credential.png)

**DCI / WAN Routers** — Prefix search, route-map IN/OUT, prefix-lists

![DCI WAN Routers](backend/static/screenshots/dci-wan-routers.png)

**Inventory** — Filters, Add/Edit/Import/Export, device table

![Inventory](backend/static/screenshots/inventory.png)

## Run locally

Clone the repo and start the app:

```bash
git clone https://github.com/onrmdc/pergen.git
cd pergen
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
export FLASK_APP=backend.app_factory:create_app
export FLASK_CONFIG=development
python -m flask run
```

Open http://127.0.0.1:5000 in your browser. Default port is **5000**.

> **Boot path note (post-OOD/TDD refactor).** All routes are registered through `backend.app_factory.create_app()` via 12 per-domain blueprints. The legacy `backend/app.py` is now an **87-line shim with zero routes** (it only owns the Flask global, `SECRET_KEY` wiring, and `_*` helper re-exports for in-tree imports). Booting `FLASK_APP=backend.app` directly will start Flask but serve **404 for every URL** — always boot through the App Factory entry point above, or use `./run.sh` which sets it for you.

**Alternative (same directory as `run.sh`):** after creating `venv` and installing deps once, `chmod +x run.sh && ./run.sh`

`run.sh` now defaults to `FLASK_APP=backend.app_factory:create_app` and `FLASK_CONFIG=development`, and prints the resolved values + URL on startup. Override either by exporting them before launch (e.g. `FLASK_CONFIG=production ./run.sh`).

### venv / “cannot run the app” checklist

1. **Working directory** — Commands must run from the **repository root** (the folder that contains `backend/` and `requirements.txt`). If you `cd backend` first, imports like `backend.app_factory` will fail.
2. **Activate the venv** — You should see `(venv)` in your shell prompt after `source venv/bin/activate` (macOS/Linux). Every new terminal needs `source venv/bin/activate` again.
3. **Install into the venv** — Use `python -m pip install -r requirements.txt` so packages go into `venv`, not the system Python.
4. **`flask` not found** — Use `python -m flask run` instead of `flask run` (avoids a different `flask` on your PATH).
5. **`FLASK_APP`** — Must point at the factory: `export FLASK_APP=backend.app_factory:create_app` (or use `./run.sh`, which sets it). Do **not** set it to `backend.app` — that shim has no routes and will 404 on every request.
6. **Listen on all interfaces** — `export FLASK_RUN_HOST=0.0.0.0` then run again (or `./run.sh` after exporting).

## Backend (Flask)

Same steps if you already have the repo: `cd pergen`, create/activate venv, `python -m pip install -r requirements.txt`, `export FLASK_APP=backend.app_factory:create_app`, `python -m flask run` (or `./run.sh`).
UI: `backend/static/index.html` at `/`. Inventory: `backend/inventory/inventory.csv` (or `example_inventory.csv` if present, else `inventory_sample.csv`). Override with `PERGEN_INVENTORY_PATH`.

### Frontend / CSP layout

The SPA is served from `backend/static/index.html` plus three split-out asset bundles so the production CSP header `script-src 'self'` will accept everything (no inline scripts, no third-party CDN):

- `backend/static/js/theme-init.js` — runs before the SPA renders to apply the persisted light/dark theme without a flash. Replaces a previous inline `<script>` block.
- `backend/static/js/app.js` — the ~5,250-line SPA logic (event bus, panels, API clients, table renderers). Extracted from `index.html` so the document is now ~1,350 lines instead of ~6,600.
- `backend/static/vendor/jszip.min.js` — vendored copy of JSZip 3.10.1 (used by Pre/Post **Export as ZIP**). Replaces the previous `cdnjs.cloudflare.com` `<script src="…">`. Update by replacing the file in place.

When editing the SPA, change `backend/static/js/app.js` (markup-only changes still go in `index.html`). Hard-reload the browser (Cmd/Ctrl+Shift+R) to bypass the static cache.

### Frontend testing (Playwright E2E)

The SPA is exercised end-to-end by a Playwright suite added in
`v0.2.0-audit-wave-1`. The suite boots the real Flask server via
`webServer` config (no mocked backend), navigates every page, and
asserts CSP / security headers + 3 full operator flows.

```bash
make e2e-install     # one-time: `npm install` + `npx playwright install chromium`
make e2e             # run the suite (62 tests / ~8 s on a warm M-series Mac)
```

Reports land in `playwright-report/` (HTML; open with
`npx playwright show-report`) and `test-results/junit.xml`. Specs
live under `tests/e2e/specs/` — 20 files covering all 12 SPA pages,
API smokes, the `csp-no-inline` regression guard, security headers,
and 3 end-to-end flows (`flow-credential-add`,
`flow-notepad-roundtrip`, `flow-diff-checker`).

### API overview

| Endpoint | Description |
|---------|-------------|
| `GET /api/fabrics` | List fabrics |
| `GET /api/sites?fabric=` | List sites |
| `GET /api/halls?fabric=&site=` | List halls |
| `GET /api/roles?fabric=&site=&hall=` | List roles |
| `GET /api/devices?fabric=&site=&role=&hall=` | List devices |
| `POST /api/ping` | Ping devices; body `{"devices": [{"hostname","ip"}, ...]}` |
| `GET /api/inventory` | Full inventory |
| `GET /api/credentials` | List credentials |
| `POST /api/credentials` | Add credential (name, method: api_key \| basic) |
| `DELETE /api/credentials/<name>` | Delete credential |
| `GET /api/commands?vendor=&model=&role=` | Commands for device (from `backend/config/commands.yaml`) |
| `GET /api/parsers/fields` | Parser field names |
| `GET /api/parsers/<command_id>` | Parser config |
| `POST /api/run/pre` | Run PRE; returns `run_id`, `device_results` |
| `POST /api/run/post` | Run POST; body `{ "run_id": "..." }`; returns comparison |
| `GET /api/run/result/<run_id>` | Stored run (PRE/POST) |
| `GET /api/notepad` | Live notepad content (plain text) |
| `PUT /api/notepad` | Update notepad; body `{"content": "..."}` |
| `GET /api/bgp/status?prefix=&asn=` | BGP status (RIPEStat) |
| `GET /api/bgp/looking-glass?prefix=&asn=` | Looking Glass peers |
| `GET /api/bgp/wan-rtr-match?asn=` | WAN routers with `router bgp <AS>` |
| `POST /api/transceiver` | Transceiver + interface status; body `{"devices": [<inventory device dict>, ...]}`; returns `rows`, `errors`, `interface_status_trace` |
| `POST /api/transceiver/recover` | Bounce interfaces (configure + shutdown / no shutdown); body `{"device": {...}, "interfaces": ["Ethernet1/1", ...]}`; **Leaf + Ethernet1/1–1/48 only**; basic credential |
| `POST /api/transceiver/clear-counters` | `clear counters interface <name>`; body `{"device": {...}, "interface": "..."}`; same Leaf/host-port rules |

### Transceiver implementation notes

- **Commands** are defined in `backend/config/commands.yaml`; parsers in `backend/config/parsers.yaml` with custom logic in `backend/parse_output.py`.
- **Runner** supports `command_id_filter` (substring) and `command_id_exact` for a single command id (e.g. Cisco `show interface` without matching `show interface status` twice).
- **Policy**: `backend/transceiver_recovery_policy.py` (`Leaf` role + `Ethernet1/1`–`Ethernet1/48` / short `1/x` form).
- **Recovery**: `backend/runners/interface_recovery.py` (Arista eAPI configure, Cisco NX-OS SSH PTY for config lines).

## Security and Git (no credentials in repo)

These are **ignored** by Git so they are never committed:

- **`.env`** / **`.env.local`** — Environment variables (e.g. `SECRET_KEY`). Copy `.env.example` to `.env` and set your own `SECRET_KEY` locally.
- **`backend/instance/`** — Credential store (SQLite DB with encrypted passwords/API keys). Created at first run; keep it local only.
- **`backend/inventory/inventory.csv`** — Your real device list.
- **`backend/inventory/example_inventory.csv`** — Optional local sample; if present it is used when `inventory.csv` is missing. Not in the repo (gitignored).
- Repo includes only **`backend/inventory/inventory_sample.csv`** (minimal 2-row sample) as reference.

**Before pushing to your Git account:** Ensure you have no `.env` or `backend/inventory/inventory.csv` in the repo (they are in `.gitignore`). Credential *names* in inventory (e.g. `tyc`, `wallet`) are not secrets; the actual credentials are stored in the app via the Credential page and saved under `instance/`, which is gitignored.

If you already committed `inventory.csv`, `example_inventory.csv`, or `.env` in the past, remove them from Git (files stay on disk):  
`git rm --cached backend/inventory/inventory.csv` and/or `git rm --cached backend/inventory/example_inventory.csv` and/or `git rm --cached .env` then commit.

## Configuration

- **Inventory**: CSV with columns such as hostname, ip, fabric, site, hall, vendor, model, role, tag, credential. Use tag `leaf-search` for Find Leaf, `nat lookup` for NAT Lookup firewalls, role `wan-router` for BGP WAN RTR search. Put your file at `backend/inventory/inventory.csv` (or set `PERGEN_INVENTORY_PATH`). Repo contains only `inventory_sample.csv` (minimal); `inventory.csv` and `example_inventory.csv` are gitignored.
- **Credentials**: Stored encrypted in `backend/instance/credentials.db` (legacy) and/or `backend/instance/credentials_v2.db` (new — written by `POST /api/credentials`). The legacy `credential_store.get_credential()` now falls through to the v2 store when the legacy DB has no row (wave-7 C-1 / H-4 fix), so a fresh-install operator who only used the new HTTP CRUD has working device-exec routes. The migration script (`scripts/migrate_credentials_v1_to_v2.py`) remains the canonical operator action when both stores are populated. Set credential name per device in inventory; use the **Credential** page to add/update; do not commit `.env` or the `instance/` folder.
- **Binding**: For the canonical entry point (`FLASK_APP=backend.app_factory:create_app`), set `FLASK_RUN_HOST=0.0.0.0` for production; default is `127.0.0.1`. The legacy `python -m backend.app __main__` shim binds via `PERGEN_DEV_BIND_HOST` (default `127.0.0.1`) and refuses any non-loopback bind unless `PERGEN_DEV_ALLOW_PUBLIC_BIND=1` is set (wave-7 H-3 fix).
- **Session lifetime** (wave-7 H-2): `PERGEN_SESSION_LIFETIME_HOURS` (default `8`) bounds the maximum lifetime of a `pergen_session` cookie issued by the optional cookie-auth path. `PERGEN_SESSION_IDLE_HOURS` (default = lifetime) enforces an idle-timeout via the `iat` stamp on every request. Audit line emitted on idle-timeout: `audit auth.session.expired actor=<name> ip=<ip> age_s=<seconds>`.
- **Reverse proxy** (wave-7 H-1): set `PERGEN_TRUST_PROXY=1` to mount `werkzeug.middleware.proxy_fix.ProxyFix` so the login throttle keys on the real client IP. **Required behind nginx / Caddy / cloud LB**. Do NOT set this in deployments that are NOT behind a proxy — naively trusting `X-Forwarded-For` lets an attacker rotate the header value to bypass the throttle.

## Troubleshooting

- **Connection refused (HTTPS to device)** — Device unreachable on port 443 or eAPI not enabled. Check firewall and device config.
- **“Only Arista EOS supported”** — The operation (e.g. route-map compare, WAN RTR config check) is implemented for Arista EOS. Other vendors (e.g. Cisco NX-OS) are not supported for that feature yet.
- **Event bar** — Top bar shows success (green), warnings (amber), and errors (red). Click a counter to open the event list and see timestamps and messages.
- **Transceiver recovery “not allowed”** — Device must have **role** `Leaf` in inventory, and the interface must match **Ethernet1/1** through **Ethernet1/48** (first module, ports 1–48). Spine or uplink interfaces are blocked by policy.
- **Recovery requires basic credential** — API-key-only credentials cannot run SSH recover or clear-counters; configure a username/password credential in the app and reference it in inventory.

## Help

In the app, open **Help** from the menu for a short guide to each page (navigation, Pre/Post, NAT, Find Leaf, BGP, REST API, Transceiver—including optics columns and error recovery—Credential, DCI/WAN Routers, Inventory, tables, theme).
