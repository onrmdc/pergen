# Pergen — How To Use

Operational guide for running, configuring, testing and developing
Pergen after the OOD/TDD refactor.

---

## 1. Prerequisites

- Python 3.9+
- macOS / Linux (Windows works under WSL2)
- A device inventory CSV with the canonical 10-column header
  (`hostname,ip,fabric,site,hall,vendor,model,role,tag,credential`)

---

## 2. First-time setup

```bash
git clone git@github.com:asceylan/pergen.git
cd pergen
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt        # production deps
pip install -r requirements-dev.txt    # tests + ruff + coverage
```

Place your inventory CSV at `backend/inventory/inventory.csv`
(or set `PERGEN_INVENTORY_PATH=/abs/path/to/inv.csv`).  If neither
exists the app falls back to `backend/inventory/example_inventory.csv`.

---

## 3. Environment variables

### Core configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | `pergen-default-secret-CHANGE-ME` | Master secret. **Production refuses both this and the historic `dev-secret-change-in-prod`** placeholder; min length 16 chars. |
| `FLASK_ENV` / `PERGEN_CONFIG` | `development` | Selects `development` / `testing` / `production` from `CONFIG_MAP`. |
| `PERGEN_INVENTORY_PATH` | `backend/inventory/inventory.csv` | Inventory CSV path. |
| `PERGEN_INSTANCE_DIR` | `backend/instance` | Notepad / reports / credential DB root. |
| `LOG_LEVEL` | `INFO` (`DEBUG` in dev) | Root log level. |
| `LOG_FORMAT` | `colour` (dev) / `json` (prod) | Stream formatter. |
| `LOG_FILE` | unset | If set, also rotate logs to this file (10 MB × 5). |
| `LOG_SLOW_MS` | `500` | Slow-request WARN threshold. |
| `CREDENTIAL_DB_PATH` | `backend/instance/credentials_v2.db` | Encrypted credential store (chmodded 0o600 + `PRAGMA secure_delete`). |

### Audit-batch security knobs (post-Phase-13 + audit batch 4)

In **production** (`PERGEN_CONFIG=production` / `FLASK_ENV=production`)
two protections are now **mandatory** — `create_app("production")` will
refuse to start otherwise:

| Variable | Production | Purpose |
|----------|-----------|---------|
| `PERGEN_API_TOKEN` or `PERGEN_API_TOKENS` | **REQUIRED** (≥32 chars per token) | Without it, `/api/*` would be open. Audit C-1 fail-closed. |
| `PERGEN_REQUIRE_DESTRUCTIVE_CONFIRM` | **always-on** in prod | Destructive routes (`/api/transceiver/recover`, `/api/transceiver/clear-counters`) require `X-Confirm-Destructive: yes`. |

In **development / testing** these stay opt-in so the developer
experience is unchanged. A WARN line is logged on first request to
flag the open posture.

#### Multi-actor token configuration (audit C-2)

Prefer per-operator tokens so audit log lines can record who took an
action:

```bash
export PERGEN_API_TOKENS="alice:$(openssl rand -hex 32),bob:$(openssl rand -hex 32)"
```

The matched actor is stored on `flask.g.actor` and recorded in
`audit credential.set actor=<name> ...` log lines. The legacy
single-bearer form (`PERGEN_API_TOKEN`) still works and resolves
to `actor=shared`.

#### Optional knobs

| Variable | Default | Purpose |
|----------|---------|---------|
| `PERGEN_API_TOKEN` | unset (dev) / required (prod) | Single shared bearer. Constant-time compare via `hmac.compare_digest`. `/api/health`, `/api/v2/health`, `/` (SPA) always exempt. |
| `PERGEN_API_TOKENS` | unset | Per-actor format `actor1:tok1,actor2:tok2`. Preferred over `PERGEN_API_TOKEN` for accountability. |
| `PERGEN_AUTH_COOKIE_ENABLED` | unset (cookie path off) | When `=1`, the SPA can authenticate via `POST /api/auth/login` → HttpOnly signed-session cookie + `X-CSRF-Token` header instead of pasting `X-API-Token` everywhere. The legacy `X-API-Token` path keeps working unchanged for CI / curl. See **§4.5 SPA cookie auth** below. |
| `PERGEN_REQUIRE_DESTRUCTIVE_CONFIRM` | unset (dev) / on (prod) | When `=1`, `/api/transceiver/recover` and `/api/transceiver/clear-counters` require an `X-Confirm-Destructive: yes` header. Returns 403 otherwise. |
| `PERGEN_BLOCK_INTERNAL_PING` | unset | **Wave-7.1 (2026-04-23):** `/api/ping` now defaults to **allow** internal targets — RFC1918, loopback, link-local, multicast, reserved — because Pergen is operated against the operator's own management network and the original default-deny posture made the tool unusable for its intended use case. Set `=1` to re-enable the audit-H3 default-deny SSRF guard for an internet-exposed deployment. The legacy `PERGEN_ALLOW_INTERNAL_PING=1` is honoured as a no-op; if both are set, `BLOCK` wins. |
| `PERGEN_ALLOW_DEBUG_RESPONSES` | unset | When `=1`, `/api/nat-lookup` honours `debug=true` in the request body (otherwise the field is suppressed to prevent Palo Alto API body leakage). |
| `PERGEN_SSH_STRICT_HOST_KEY` | unset | **Default `AutoAddPolicy` is intentional** for an internal Pergen deployment: paramiko TOFUs each device's host key on first contact, so adding a new leaf or spine to the inventory just works. Set `=1` (paired with `PERGEN_SSH_KNOWN_HOSTS=<path>`) to flip to Paramiko `RejectPolicy` for an untrusted-network deployment. **Wave-7.1**: the AutoAdd notice now fires once per process at module-import (level INFO), not WARN-per-call — multi-device runs no longer drown the audit log. |
| `PERGEN_RECOVERY_BOUNCE_DELAY_SEC` | `5` | **Wave-7.3 (2026-04-23) bug fix.** Sleep duration (seconds) between the `shutdown` and `no shutdown` stanzas of an interface bounce in `/api/transceiver/recover`. Each interface now bounces as TWO separate SSH/eAPI sessions per bounce (was one script that NX-OS coalesced asynchronously, so the link never actually went down → up). Default 5s matches the operator-validated CLI workflow; clamped to `[1, 30]`. Sequential per-interface (interface 1 fully bounced before interface 2 starts). A strict regex allowlist refuses any line outside `configure terminal` / `configure` / `interface <name>` / `shutdown` / `no shutdown` / `end`. |
| `PERGEN_SSH_KNOWN_HOSTS` | unset | Path to a managed `known_hosts` file. Loaded before `connect()`. |

#### Wave-7 knobs (audit followup 2026-04-23)

These knobs were added in wave-7 to close audit findings H-1, H-2, and H-3.
All default to safe values; existing deployments require no operator action.

| Variable | Default | Purpose |
|----------|---------|---------|
| `PERGEN_SESSION_LIFETIME_HOURS` | `8` | Maximum lifetime of a `pergen_session` cookie (the optional cookie-auth path). Was Flask's 31-day default; that was far too long for an operator tool with SSH credential authority. (Wave-7 H-2.) |
| `PERGEN_SESSION_IDLE_HOURS` | = `PERGEN_SESSION_LIFETIME_HOURS` | Idle-timeout threshold. Cookie-auth branch of `_enforce_api_token` clears the session and treats it as anonymous when `now - session["iat"] > PERGEN_SESSION_IDLE_HOURS * 3600`. Audit line emitted: `audit auth.session.expired actor=<name> ip=<ip> age_s=<seconds>`. (Wave-7 H-2.) |
| `PERGEN_TRUST_PROXY` | unset | When `=1`, mount `werkzeug.middleware.proxy_fix.ProxyFix(x_for=1, x_proto=1, x_host=1)` so `request.remote_addr` reflects the original client IP instead of the reverse proxy. **Required behind nginx / Caddy / cloud LB** for the login throttle to key correctly on `(client_ip, username)`. **Do NOT set this on deployments that are NOT behind a proxy** — naively trusting `X-Forwarded-For` from un-proxied deployments lets an attacker rotate the header value to bypass the throttle. (Wave-7 H-1.) |
| `PERGEN_DEV_BIND_HOST` | `127.0.0.1` | Bind host for the legacy `python -m backend.app __main__` entry point. (Wave-7 H-3.) |
| `PERGEN_DEV_ALLOW_PUBLIC_BIND` | unset | Override for the bind-host guard. Required only for `python -m backend.app`; production should always boot via `FLASK_APP=backend.app_factory:create_app`. The shim refuses any non-loopback bind unless this is `=1`. (Wave-7 H-3.) |

> **Inventory-binding posture (not configurable).** Every device-targeted route (`/api/run/device`, `/api/run/pre`, `/api/arista/run-cmds`, `/api/custom-command`, `/api/transceiver/recover`, `/api/transceiver/clear-counters`) RESOLVES the device against the inventory CSV by hostname/IP and uses the inventory's `credential` field. Caller-supplied `credential`, `vendor` and `model` fields are ignored. Audit H-2 prevents an attacker from binding an arbitrary IP to a privileged credential.

> **Device TLS posture (not configurable).** All HTTPS calls to network devices (Arista eAPI, Cisco NX-API, Palo Alto XML API) are sent with `verify=False` because devices in this fleet present local self-signed certificates. The single source of truth is `DEVICE_TLS_VERIFY` in `backend/runners/_http.py`. If you deploy CA-signed device certs in the future, flip that constant rather than reintroducing per-runner toggles. Public APIs (RIPE, PeeringDB) keep `verify=True`.

> **XML parsing (not configurable).** `nat_lookup` parses untrusted XML responses from network firewalls. `defusedxml` is a HARD requirement (no fallback) — a missing dependency raises `ImportError` at module import time rather than silently downgrading to the unsafe stdlib parser. Audit H-1.

> **Credential storage (not configurable).** `cryptography` is a HARD requirement. The legacy `backend/credential_store.py` no longer falls back to base64 when the import fails — it now raises at module import time. Audit C-3.

---

## 4. Running the app

### 4.1 Development (factory + auto-reload, recommended)

```bash
export FLASK_APP=backend.app_factory:create_app
export FLASK_CONFIG=development                          # selects DevelopmentConfig
export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
python -m flask run --host 0.0.0.0 --port 5000
```

`./run.sh` is the operator-friendly equivalent — it activates `venv`,
exports the same two `FLASK_*` defaults, prints the resolved values
and the URL, then `exec`s `python -m flask run`. Override either by
exporting it before the script:

```bash
FLASK_CONFIG=production FLASK_RUN_HOST=0.0.0.0 ./run.sh
```

**Wave-7.2 — `.env` auto-loading.** `./run.sh` now auto-loads `.env`
from the repo root before launching Flask. Put your tokens, secret
key, and any other env knobs in `.env` (copy from `.env.example`):

```bash
cp .env.example .env
# edit .env: set SECRET_KEY, PERGEN_API_TOKEN (≥ 32 chars) or
# PERGEN_DEV_OPEN_API=1
./run.sh
```

Existing shell exports take precedence over `.env` (`.env` is a
baseline, not an override) — set a variable inline (`FOO=bar ./run.sh`)
and the inline value wins. The Flask CLI also auto-loads `.env` when
`python-dotenv` is installed (it ships in `requirements.txt` since
wave-7.2); the `run.sh` parser is the belt-and-suspenders fallback for
older venvs.

**Common boot failure: "Refusing to boot with an open API in
development."** This means neither `PERGEN_API_TOKEN(S)` nor
`PERGEN_DEV_OPEN_API=1` is in the environment. Either:
- set a token (must be ≥ 32 characters): `PERGEN_API_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")`, or
- explicitly opt into the open posture: `PERGEN_DEV_OPEN_API=1`,

then add it to `.env` (or export it in your shell). The factory
refuses to silently boot open in development since wave-7 (audit
H-05).

**Common runtime failure: every API call returns 401, UI is empty.**
This happens when you set BOTH a token AND `PERGEN_DEV_OPEN_API=1` in
the same `.env`. The runtime gate ALWAYS enforces tokens when any are
configured — `PERGEN_DEV_OPEN_API` is consulted only at boot time (it
controls the H-05 boot guard, not the runtime auth check). Wave-7.2
emits a clear WARN at startup for this contradictory configuration:

```
PERGEN_DEV_OPEN_API=1 has no effect when PERGEN_API_TOKEN(S) is also
set; the gate enforces tokens at runtime. To use the open posture,
unset PERGEN_API_TOKEN(S). To use token auth with the SPA, also set
PERGEN_AUTH_COOKIE_ENABLED=1 so the browser can log in via /login.
```

Pick ONE auth mode (see `.env.example` for full details):

- **Posture A — token auth (recommended):** keep `PERGEN_API_TOKEN`,
  drop `PERGEN_DEV_OPEN_API`, ADD `PERGEN_AUTH_COOKIE_ENABLED=1`. The
  SPA will redirect to `/login` on first load; type your actor name
  (`shared` for the single-token form) and the token itself as the
  password.
- **Posture B — open API (internal-only, no auth):** drop
  `PERGEN_API_TOKEN` entirely, keep only `PERGEN_DEV_OPEN_API=1`. The
  SPA loads with no auth challenge.

### 4.2 Direct factory call (for embedding / scripts)

```bash
python3 -c "from backend.app_factory import create_app; create_app('development').run(host='0.0.0.0', port=5000, debug=True)"
```

### 4.3 Legacy `backend.app` entry point — DO NOT USE

The 1,577-line monolith was decomposed in Phase 12. `backend/app.py` is
now an **87-line shim with zero `@app.route` handlers** kept only so
in-tree code that does `from backend.app import _foo` (legacy helper
re-exports) keeps working.

```bash
# Boots Flask but every URL returns 404 — the shim has no routes:
FLASK_APP=backend.app flask run                         # ❌ broken
```

If you see 404s from a freshly-cloned tree, this is the cause —
switch `FLASK_APP` to `backend.app_factory:create_app`.

**Wave-7 bind-host guard.** The `python -m backend.app __main__` branch
now binds via `PERGEN_DEV_BIND_HOST` (default `127.0.0.1`) and refuses
any non-loopback bind unless `PERGEN_DEV_ALLOW_PUBLIC_BIND=1` is set.
Closes the latent foot-gun where the shim could expose every route
publicly without auth if a future contributor restored
`from backend.blueprints import …` here (the API token gate is mounted
by `create_app()`, not by `backend.app`):

```bash
# Refused — exits with a documented error message:
PERGEN_DEV_BIND_HOST=0.0.0.0 python -m backend.app

# Allowed (with the override):
PERGEN_DEV_ALLOW_PUBLIC_BIND=1 PERGEN_DEV_BIND_HOST=0.0.0.0 python -m backend.app
```

The override should never be set in production. Use
`FLASK_APP=backend.app_factory:create_app flask run --host 0.0.0.0`
instead — that path goes through `create_app()` which mounts the
API token gate.

### 4.4 Production (gunicorn or similar)

```bash
export PERGEN_CONFIG=production
export SECRET_KEY=...                  # MUST be a non-default value
export LOG_FORMAT=json
export LOG_FILE=/var/log/pergen/app.log
gunicorn -w 4 -b 0.0.0.0:8000 'backend.app_factory:create_app("production")'
```

`ProductionConfig.validate()` raises `RuntimeError` on the default
`SECRET_KEY`, so a misconfigured deploy fails before binding to a port.

### 4.5 SPA cookie auth (Wave-6 Phase F, opt-in)

By default Pergen's API gate accepts only the `X-API-Token` header.
That works for CI / curl / scripts, but every browser hit needs the
operator to paste the token somewhere — there is no in-app login UI in
the legacy posture.

Wave-6 Phase F adds a second auth path: a server-rendered `/login`
form that, on success, sets a Flask-signed `pergen_session` cookie
(`HttpOnly; SameSite=Lax`; `Secure` in prod) carrying `{actor, csrf}`.
Every state-changing API call from the SPA then carries the cookie
**and** an `X-CSRF-Token` header pulled from `<meta name="pergen-csrf">`
by the `pergenFetch(...)` wrapper. The token gate accepts EITHER:

1. `X-API-Token: <per-actor-token>` (legacy, machine clients), OR
2. The signed `pergen_session` cookie + matching `X-CSRF-Token` for
   POST/PUT/DELETE/PATCH (browsers).

**Enable it:**

```bash
export PERGEN_AUTH_COOKIE_ENABLED=1
export PERGEN_API_TOKENS="alice:$(openssl rand -hex 32),bob:$(openssl rand -hex 32)"
```

The `password` field on `POST /api/auth/login` is the operator's
per-actor API token from `PERGEN_API_TOKENS` — there is no separate
password store. Pergen's identity model remains a small set of named
operator tokens; the cookie path just stops the operator from having to
paste them into the browser DevTools every time.

**Routes added:**

| Route | Purpose |
|-------|---------|
| `GET  /login`               | Server-rendered login form (CSP-clean: external CSS + JS only). |
| `POST /api/auth/login`      | Body `{username, password}`. On match → `Set-Cookie: pergen_session=...; HttpOnly`. Returns `{ok: true, csrf: <token>}`. |
| `POST /api/auth/logout`     | Clears the session cookie. Idempotent. |
| `GET  /api/auth/whoami`     | Returns `{actor, csrf}` for a logged-in browser, `{actor: null}` otherwise. The SPA calls this on boot to populate the CSRF meta tag. |

**Defences shipped with this path:**

* Session fixation: `session.clear()` is called on every login before
  the new keys are set, so a pre-planted cookie cannot survive.
* Constant-time credential check (`hmac.compare_digest`) on the token
  comparison, including a dummy compare on unknown usernames so the
  response time is not a username-existence oracle.
* Login throttling: 10 fails / 60s per `(remote_addr, username)` →
  429 with `Retry-After`. In-process LRU bounded at 1024 entries.
* Audit lines on `app.audit`: `auth.login.success`, `auth.login.fail`,
  `auth.login.throttled`, `auth.logout`, `auth.csrf.mismatch`.

**Recommended deployment posture (unchanged):** Pergen still expects
to run on a private network. The cookie auth path is the second layer
of defence, not a substitute for not exposing `/api/*` to the public
internet. Run behind a VPN / zero-trust mesh / authenticating proxy
the same way you would have without the cookie path.

**Backwards compatibility:** the legacy `X-API-Token` header is
ALWAYS accepted, even when `PERGEN_AUTH_COOKIE_ENABLED=1`. CI scripts
and `curl` commands continue to work unchanged. The CSRF check only
applies to requests authenticating via the cookie path.

---

## 5. Health check

```bash
curl -s http://localhost:5000/api/health
# {"status": "ok"}

curl -s http://localhost:5000/api/v2/health      # phase-4 blueprint
# {"service": "pergen", "status": "ok",
#  "timestamp": "...", "config": "development",
#  "request_id": "..."}
```

---

## 6. Inventory CRUD

| Method | Path | Owner | Purpose |
|--------|------|-------|---------|
| GET | `/api/fabrics` | `inventory_bp` | List distinct fabrics |
| GET | `/api/sites?fabric=` | `inventory_bp` | Sites within a fabric |
| GET | `/api/halls?fabric=&site=` | `inventory_bp` | Halls |
| GET | `/api/roles?fabric=&site=&hall=` | `inventory_bp` | Roles |
| GET | `/api/devices?fabric=&site=&role=&hall=` | `inventory_bp` | Devices |
| GET | `/api/devices-arista?...` | `inventory_bp` | Arista-only filter |
| GET | `/api/devices-by-tag?tag=&fabric=&site=` | `inventory_bp` | Lookup by tag |
| GET | `/api/inventory` | `inventory_bp` | Full dump (`{"inventory": [...]}`) |
| POST | `/api/inventory/device` | `inventory_bp` | Add device |
| PUT | `/api/inventory/device` | `inventory_bp` | Update device |
| DELETE | `/api/inventory/device` | `inventory_bp` | Delete device |
| POST | `/api/inventory/import` | `inventory_bp` | Bulk CSV import |

Example:

```bash
curl -s "http://localhost:5000/api/devices?fabric=FAB1&site=Mars" | jq .
```

---

## 7. Notepad (shared)

```bash
curl -s http://localhost:5000/api/notepad
# {"content": "...", "line_editors": ["alice", "bob", ...]}

curl -s -X PUT http://localhost:5000/api/notepad \
     -H "content-type: application/json" \
     -d '{"content": "first line\nsecond line", "user": "alice"}'
```

Owned by `notepad_bp` → `NotepadService` → `NotepadRepository`.

---

## 8. Credentials

`/api/credentials*` is owned by `credentials_bp`
(`backend/blueprints/credentials_bp.py`) and goes through
`CredentialService` + `EncryptionService` (AES-128-CBC + HMAC,
PBKDF2 ≥ 600k). The legacy `backend/credential_store.py` base64
fallback was removed in audit batch 1 — `cryptography` is now a
hard import.

```bash
curl -X POST http://localhost:5000/api/credentials \
     -H "content-type: application/json" \
     -d '{"name": "lab", "method": "basic", "username": "admin", "password": "secret"}'

curl http://localhost:5000/api/credentials                 # list
curl -X DELETE http://localhost:5000/api/credentials/lab   # delete
```

> Never commit `credentials.db` / `credentials_v2.db` to git — they
> are excluded by `.gitignore`.

### Migrating from the legacy credential store

Pergen historically wrote credentials to `instance/credentials.db`
using a single SHA-256 → Fernet derivation
(`backend/credential_store.py`, now deprecation-flagged). The new path
is `instance/credentials_v2.db`, encrypted by `EncryptionService`
(PBKDF2-HMAC-SHA256 600 000 iterations → AES-128-CBC + HMAC-SHA256).
HTTP CRUD already writes to the v2 store; this runbook describes the
**operator-led, one-shot data move** for any rows still living in the
legacy DB.

The migration script reads the legacy DB read-only, decrypts each row
with the operator's `SECRET_KEY`, and re-encrypts into the v2 DB. It
is **idempotent** (rows already present in v2 by name are skipped —
the operator's manually-set newer credential always wins) and
**non-destructive** (the legacy file is never modified or deleted).

Steps:

```bash
# 1. Stop Pergen so no writes race the migration.
#    (kill the process, stop the systemd unit, etc.)

# 2. Back up the legacy DB out-of-band (the script does NOT do this for you).
cp backend/instance/credentials.db backend/instance/credentials.db.bak.$(date +%Y%m%d)
chmod 0600 backend/instance/credentials.db.bak.*

# 3. Confirm the same SECRET_KEY the running app uses is in your env.
echo "${SECRET_KEY:0:6}..."   # sanity-check: same first 6 chars as the app

# 4. Dry-run first — prints would-be migration count without writing v2.
python scripts/migrate_credentials_v1_to_v2.py --dry-run --verbose

# 5. Real migration. Pre-flight canary-decrypts one entry; refuses to
#    proceed (exit 2) if SECRET_KEY is wrong.
python scripts/migrate_credentials_v1_to_v2.py --verbose

# 6. Restart Pergen and verify.
curl -s http://localhost:5000/api/credentials | jq '.credentials | length'
curl -s -X POST http://localhost:5000/api/credentials/<name>/validate

# 7. Keep credentials.db.bak.<date> for at least one release cycle in
#    case a credential turns up missing post-migration.
```

Flags:

| Flag | Default | Purpose |
|------|---------|---------|
| `--legacy-db` | `$PERGEN_INSTANCE_DIR/credentials.db` | Source path. |
| `--v2-db` | `$PERGEN_INSTANCE_DIR/credentials_v2.db` | Destination path (created if missing). |
| `--dry-run` | off | Decrypt-and-count only; no v2 writes. |
| `--verbose` | off | Per-row `{name, method, status}` line in summary. No payloads ever printed. |

Exit codes: `0` success • `1` at least one row failed (operator
inspects the printed error list) • `2` pre-flight refused (missing
`SECRET_KEY`, missing legacy DB, wrong key).

**Wave-6 keep-shim note.** `backend/credential_store.py` remains
importable after this migration — it emits `DeprecationWarning` on
import (already pinned by
`tests/test_security_legacy_credstore_deprecation.py`) but the 5
blueprint sites + `runners/runner.py` + `find_leaf` + `nat_lookup`
keep working unchanged. The shim → `CredentialService` cut-over is
deliberately a separate wave.

---

## 9. Running commands on devices

Phase 12 finished the blueprint migration — every device-touching
endpoint now lives in a per-domain blueprint under
`backend/blueprints/`. There is **no remaining route in
`backend/app.py`**. Map of who owns what:

| Endpoint(s) | Blueprint | File |
|---|---|---|
| `/api/run/device`, `/api/run/pre`, `/api/run/pre/create`, `/api/run/pre/restore`, `/api/run/post`, `/api/run/post/complete`, `/api/run/result/<run_id>`, `/api/diff` | `runs_bp` | `backend/blueprints/runs_bp.py` |
| `/api/arista/run-cmds`, `/api/custom-command`, `/api/route-map/run`, `/api/router-devices` | `device_commands_bp` | `backend/blueprints/device_commands_bp.py` |
| `/api/transceiver`, `/api/transceiver/recover`, `/api/transceiver/clear-counters` | `transceiver_bp` | `backend/blueprints/transceiver_bp.py` |
| `/api/find-leaf`, `/api/find-leaf-check-device`, `/api/nat-lookup` | `network_lookup_bp` | `backend/blueprints/network_lookup_bp.py` |
| `/api/bgp/status`, `/api/bgp/history`, `/api/bgp/visibility`, `/api/bgp/looking-glass`, `/api/bgp/bgplay`, `/api/bgp/as-info`, `/api/bgp/announced-prefixes`, `/api/bgp/wan-rtr-match` | `bgp_bp` | `backend/blueprints/bgp_bp.py` |
| `/api/ping` | `network_ops_bp` | `backend/blueprints/network_ops_bp.py` |
| `/api/commands`, `/api/parsers/fields`, `/api/parsers/<command_id>` | `commands_bp` | `backend/blueprints/commands_bp.py` |
| `/api/reports`, `/api/reports/<run_id>` (GET/DELETE) | `reports_bp` | `backend/blueprints/reports_bp.py` |
| `/api/credentials*`, `/api/credentials/<name>/validate` | `credentials_bp` | `backend/blueprints/credentials_bp.py` |

Refer to each blueprint module for exact payload shapes — the
golden contract tests in `tests/golden/` lock the response envelopes
byte-for-byte against the pre-refactor baseline.

---

## 10. Tests

```bash
make test                          # full suite (1767 passed + 1 xfailed, ~93 s)
make cov                           # whole-project coverage report (gate 45 %, currently 90.79 %)
npm run test:frontend              # Vitest frontend unit tests (45 tests, <1 s)
npx playwright test                # Playwright E2E (100 / 100 passing, 43 specs, ~10–30 s)

# Operator CLI (wave-5):
python -m backend.cli.backfill_report_actors --dry-run   # preview legacy report stamping
python -m backend.cli.backfill_report_actors --owner=netops-2026   # stamp + commit

# Operator CLI (wave-6 Phase E — credential migration):
python scripts/migrate_credentials_v1_to_v2.py --dry-run            # preview
python scripts/migrate_credentials_v1_to_v2.py --verbose             # real run
# Audit classifier (wave-6 Phase C):
node scripts/audit/innerhtml_classifier.mjs                          # generate XSS site CSV
# SPA cookie auth (wave-6 Phase F) — opt-in:
export PERGEN_AUTH_COOKIE_ENABLED=1                                  # then restart app
make cov-new                       # OOD-layer-only coverage report (gate 85 %, currently 91.34 %)
venv/bin/python -m pytest tests/golden/ -q                # golden / characterisation
venv/bin/python -m pytest -k phase9 -q                    # phase-9 only
venv/bin/python -m pytest tests/test_services.py -q       # service layer
venv/bin/python -m pytest tests/test_security_audit_batch4.py -q   # batch-4 security regressions
venv/bin/python -m pytest tests/test_security_xss_spa.py -q        # audit-wave-1 XSS lint guards
```

Useful environment knobs:

- `PERGEN_REGEN_GOLDEN=1` — regenerate the golden snapshots in
  `tests/fixtures/golden/`.
- `PERGEN_INSTANCE_DIR` / `PERGEN_INVENTORY_PATH` — same as runtime;
  `conftest.py` already wires per-test isolation.

### 10.1 End-to-end (Playwright)

The Playwright suite (added in `v0.2.0-audit-wave-1`, expanded through
wave-3 / wave-5 / wave-6) drives the real SPA against a real Flask server.
Single command, no mocks. **Wave-7 stabilised 12 brittle specs that were
failing at wave-6 close** (test-only changes; no SPA / backend
modifications).

```bash
make e2e-install                   # one-time: npm install + npx playwright install chromium
make e2e                           # 43 spec files / 100 tests, ~10–30 s on a warm Mac
```

`playwright.config.ts` boots `./run.sh` automatically via `webServer`
(reuses an already-running server on port 5000 if present), so you
don't need to start Flask separately.

Reports & artefacts:

- `playwright-report/` — HTML report. Open with
  `npx playwright show-report` (or `npm run e2e:report`).
- `test-results/junit.xml` — JUnit XML for CI.
- `test-results/<spec>/` — screenshots and videos of failed runs
  (`screenshot: only-on-failure`, `video: retain-on-failure`).

Useful filters:

```bash
npx playwright test tests/e2e/specs/flow-credential-add.spec.ts
npx playwright test --grep "csp-no-inline"
npx playwright test --headed                 # see the browser
npx playwright test --debug                  # inspector
```

If a freshly-cloned tree fails immediately, run `make e2e-install`
first — Chromium has to be downloaded once.

---

## 11. Linting / formatting

```bash
make lint                          # ruff check
venv/bin/ruff check --fix .        # auto-fix what is fixable
```

`pyproject.toml` pins the rule sets (`E,F,W,I,B,SIM,S,…`) and the
target Python version.

---

## 12. Adding a new endpoint

The recommended pattern (post-phase-9):

1. **Repository** — if persistence is involved, add or extend a
   `backend/repositories/<thing>_repository.py` class.
2. **Service** — wrap business logic in
   `backend/services/<thing>_service.py`.
3. **Blueprint** — create `backend/blueprints/<thing>_bp.py` that
   pulls the service from `current_app.extensions[...]` and returns
   `jsonify(...)`.
4. **Register** — append the blueprint and service to
   `_register_blueprints` / `_register_services` in
   `backend/app_factory.py`.
5. **Tests first** — write unit tests for the service (mock the
   repository) and one happy-path blueprint test before touching the
   route file.
6. **Phase-13 security checklist for any new endpoint:**
   - If the endpoint forwards a string to a network device, it
     **must** call `CommandValidator.validate(cmd)` before transport
     and return `{"error": "rejected command: …"}` with HTTP 400 on
     failure.
   - If the endpoint accepts an IP, hostname, ASN, prefix or
     credential name, it **must** route the input through
     `InputSanitizer.sanitize_*` before any side effect.
   - If the endpoint accepts a free-form body, set or rely on
     Flask's `MAX_CONTENT_LENGTH` (10 MiB by default; tighten
     per-route as needed — see `_MAX_NOTEPAD_BYTES`).
   - Never echo `str(e)` into a JSON response.  Use
     `current_app.logger.exception(...)` for the full traceback
     server-side and return a generic `{"error": "internal error"}`
     envelope.

---

## 13. Phase-13 security operations notes

* **Response headers** — every Pergen response carries
  `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin`,
  `Permissions-Policy: geolocation=(), microphone=(), camera=()`
  in addition to `X-Request-ID`.  If you front Pergen with a
  reverse proxy that injects its own headers, leave these in
  place — they are set with `setdefault`, so per-route or
  proxy overrides still win.
* **Request size** — Flask refuses requests larger than 10 MiB
  by default; tune via `MAX_CONTENT_LENGTH` env var.  The notepad
  PUT additionally enforces a per-route 512 KiB cap (`HTTP 413`).
* **Ping fan-out** — `/api/ping` rejects payloads with more than
  64 devices in a single call (`HTTP 400`).  Batch operationally
  if you need to reach more than that.
* **Defusedxml** — `nat_lookup` requires `defusedxml` (already in
  `requirements.txt`).  In the highly unlikely event the package
  is missing, the fallback to stdlib `xml.etree` is logged and
  XXE protection degrades; install `defusedxml` to restore it.
* **`python -O` deployments** — safe.  Phase 13 replaced every
  `assert` used as a security guard with `raise ValueError(...)`,
  so optimised builds keep the same hardening.
