# Pergen — Current Status for Agents

> Onboarding brief for AI agents and human teammates joining the
> `refactor/ood-tdd` branch. Read this **first**, then jump to the
> deeper docs linked at the bottom of each section.
>
> Generated: 2026-04-27.
> Reference snapshot: wave-7.10 (commit `f3c2500`,
> `patch_notes.md` v0.7.10, 2026-04-23).

---

## 1. TL;DR

Pergen is a **Flask 3 + vanilla-JS SPA** that operators use to drive a
mixed Arista EOS + Cisco NX-OS + Palo Alto fleet (Pre/Post checks, NAT
lookup, Find Leaf, BGP looking glass, transceiver DOM + recovery,
route-map compare, encrypted credential store, CSV inventory).

The codebase has just exited a multi-wave **OOD + TDD refactor**:

- Legacy 1,577-line `backend/app.py` monolith → **87-line shim**
  (`backend/app.py:1`).
- Legacy 1,552-line `backend/parse_output.py` god module → **151-line
  shim** delegating to a 31-module `backend/parsers/` package
  (`backend/parsers/dispatcher.py`, `backend/parsers/engine.py`).
- All routes now live in **12 per-domain Flask Blueprints** registered
  through `backend/app_factory.py::create_app()`.
- **Refactor program FULLY COMPLETE** — every plan under
  `docs/refactor/` is `DONE_*`-prefixed; wave-7 closed the last
  CRITICAL/HIGH cluster on 2026-04-23.

**Current quality gates (all green, verified 2026-04-23 wave-7.10):**

| Surface | Result |
|---|---|
| pytest | **1888 passed, 1 xfailed** in ~110 s |
| Combined coverage | **90.50 %** (gate 45 %) |
| OOD-scoped (`make cov-new`) | **91.28 %** (gate 85 %) |
| Vitest (frontend unit) | **54 / 54** in ~1 s, 100 % on extracted utils |
| Playwright (E2E) | **100 / 100** in ~16 s across 43 spec files |
| Boot smoke | factory boots, 13 blueprints registered, `/api/health` returns `{"status":"ok"}`, live `/api/inventory` returns 1132 devices |
| Lint (`ruff check`) — new code | **0 errors** (122 pre-existing style findings, advisory) |

The single `xfailed` is the strict tracker for **audit GAP #8**
(inventory import row cap) — known and intentional, will XPASS once
the cap lands.

> **Production-readiness call (internal use):** all gates green;
> `2042` automated tests passing; release tag `v0.7.10` cut on the
> branch; awaiting an internal-prod go-live decision.

---

## 2. Tech stack

### Backend

| Layer | Tech | Notes |
|---|---|---|
| Language | **Python 3.11+** (`pyproject.toml` `requires-python = ">=3.11"`; `HOWTOUSE.md` documents 3.9+ as the bare floor — anything you add must work on 3.11) |
| Web framework | **Flask 3.x** with App Factory pattern (`backend/app_factory.py:create_app()`) |
| HTTP client | **requests 2.28+** (with `verify=DEVICE_TLS_VERIFY=False` for fleet devices, `verify=True` for public APIs — single source of truth in `backend/runners/_http.py`) |
| SSH | **paramiko 3.x** (default `AutoAddPolicy` — intentional for internal device enrollment; `RejectPolicy` opt-in via `PERGEN_SSH_STRICT_HOST_KEY=1` + `PERGEN_SSH_KNOWN_HOSTS=<path>`) |
| XML parsing | **defusedxml ≥ 0.7.1** (HARD requirement — stdlib `xml.etree` fallback removed) |
| Crypto | **cryptography ≥ 41** — PBKDF2 ≥ 600k iters, AES-128-CBC + HMAC-SHA256 (`backend/security/encryption.py`) |
| Persistence | **SQLite** (legacy `instance/credentials.db` + new `instance/credentials_v2.db` with two-tier fall-through) + plain CSV for inventory + JSON files for reports/notepad |
| Config | **PyYAML ≥ 6** (`backend/config/commands.yaml`, `backend/config/parsers.yaml`) |
| Env loading | **python-dotenv ≥ 1** (`run.sh` + Flask CLI auto-load `.env`) |
| WSGI in front of LB | `werkzeug.middleware.proxy_fix.ProxyFix` mounted only when `PERGEN_TRUST_PROXY=1` (wave-7 H-1) |

### Frontend

| Layer | Tech | Notes |
|---|---|---|
| UI | **Vanilla JS SPA** — no framework |
| Entry | `backend/static/index.html` (~1,350 lines, markup only) |
| Logic | `backend/static/js/app.js` (~5,250-line event bus + panels + API clients + table renderers) |
| Theme bootstrap | `backend/static/js/theme-init.js` (runs before SPA renders, no flash) |
| Vendor JS | `backend/static/vendor/jszip.min.js` (3.10.1, vendored — replaces former CDN) |
| CSP posture | **strict** — `script-src 'self'`, `style-src 'self'` (no inline, no CDN). Enforced by `backend/request_logging.py` + Playwright `csp-no-inline.spec.ts` regression guard |
| Dynamic HTML | every dynamic `el.innerHTML = ...` write MUST route every interpolation through `escapeHtml(...)` or the `safeHtml` tagged template, or carry an explicit `// xss-safe: <reason>` annotation. Lint-enforced by `tests/test_security_innerhtml_lint.py`. Full policy: [`docs/security/spa_xss_policy.md`](docs/security/spa_xss_policy.md) |

### Testing

| Surface | Tool | Where |
|---|---|---|
| Python unit / integration / security / golden | **pytest 8 + pytest-cov + pytest-mock + responses + freezegun** | `tests/` (157 files, 1888 tests, 1 strict xfail) |
| Frontend unit | **Vitest 2 + @vitest/coverage-v8 + jsdom** | `tests/frontend/` (54 tests) |
| End-to-end | **Playwright 1.49 (Chromium)** | `tests/e2e/specs/` (43 specs, 100 tests) — boots **real Flask server** via `webServer` config, NOT a mocked backend |
| Lint | **ruff 0.5+** | `pyproject.toml` `[tool.ruff]`, `make lint` / `make lint-fix` |
| Coverage | `pytest-cov` global + `make cov-new` for the OOD-scoped gate (85 %) | `Makefile`, `pyproject.toml` `[tool.coverage]` |
| Markers | `unit`, `integration`, `security`, `golden` | `pytest.ini` (strict markers + strict config) |

### Tooling

| Concern | Tool |
|---|---|
| Dev runner | `./run.sh` (sets `FLASK_APP=backend.app_factory:create_app`, `FLASK_CONFIG=development`, loads `.env`) |
| Make targets | `make install` / `install-dev` / `test` / `test-fast` / `lint` / `lint-fix` / `cov` / `cov-new` / `e2e-install` / `e2e` / `clean` |
| Frontend scripts | `npm run e2e` / `e2e:headed` / `e2e:report` / `test:frontend` / `test:frontend:watch` / `test:frontend:coverage` |
| TypeScript | `tsconfig.json` (only used for Playwright/Vitest typing; no production TS) |
| Vendored Python | `vendor_pkgs/` (read-only mirror of pinned wheels; ignored by ruff + coverage) |

---

## 3. Preferred development methodologies

### 3.1 Test-Driven Development (TDD) — mandatory

Every feature, bug fix, or refactor lands in this order:

1. **RED** — write a failing test first under `tests/`. Use the right
   marker (`unit`, `integration`, `security`, `golden`).
2. **GREEN** — write the minimal implementation to pass.
3. **REFACTOR** — clean up; verify coverage still meets the gates
   (`make cov` ≥ 45 % global, `make cov-new` ≥ 85 % on the OOD layer).

The 1888-test safety net exists specifically so refactor work can move
fast without breaking byte-for-byte API/parser shapes. **Do not skip
the test step.** When in doubt, delegate to the **`tdd-guide`** agent.

Repo guidelines (see [`AGENTS.md`](AGENTS.md)):

- Minimum coverage target: **80 %** (the OOD layer is held to 85 %; the
  global gate is intentionally low at 45 % because some legacy modules
  drag the average down).
- All three test types are required for new features: **unit**,
  **integration** (Flask test-client), **E2E** (Playwright).
- Do not modify tests to make them pass unless the test itself is wrong.

### 3.2 Object-Oriented Design (OOD) — strict layering

```
HTTP request
   ↓
Blueprint   (backend/blueprints/*.py — thin: parse + validate + call)
   ↓
Service     (backend/services/*.py — business logic, orchestration)
   ↓
Repository  (backend/repositories/*.py — data access only)
   ↓
Storage     (SQLite / CSV / JSON file)

Device-side:
Blueprint → DeviceService → RunnerFactory → concrete Runner
                                              (Arista eAPI / Cisco NX-API / SSH)
                                              ↓
                                            ParserEngine → Dispatcher → vendor parser
```

Rules:

- **Blueprints stay thin.** No business logic, no SQL, no parsing.
- **Services own business logic.** They depend on repositories and
  runner/parser abstractions, never on Flask globals (other than the
  bound app via `current_app.extensions[...]`).
- **Repositories own data access.** Standard interface
  (`findAll` / `findById` / `create` / `update` / `delete`).
- **Runners and parsers are vendor-agnostic** at the interface and
  vendor-specific at the implementation. Add a new vendor by adding a
  Runner + a parsers subpackage + wiring it into the
  `RunnerFactory` / `Dispatcher` — never by branching inside a
  blueprint.
- **Immutability is non-negotiable.** Always create new objects;
  never mutate in place. Return new copies with changes applied.
- **File size budget:** 200–400 lines typical, **800 max**. Functions
  **< 50 lines**, nesting **≤ 4 levels**.

### 3.3 Security-first

The wave-1 → wave-7 audits surfaced and closed **129 findings** (38 +
49 + 24 + 6 + 5 + 7 across the waves; see `README.md` § Audit
hardening for the full table). Standing rules:

- **No hardcoded secrets.** Use env vars; production refuses
  `pergen-default-secret-CHANGE-ME` and the historic
  `dev-secret-change-in-prod`. `SECRET_KEY` ≥ 16 chars; API tokens
  ≥ 32 chars.
- **All user input** validated via `backend/security/sanitizer.py` +
  `backend/security/validator.py` at system boundaries. SQL is
  parameterized; XML is `defusedxml`; HTML is `escapeHtml` /
  `safeHtml`.
- **Bearer auth fail-closed in production.** `PERGEN_API_TOKEN(S)` is
  REQUIRED; constant-time compare via `hmac.compare_digest`. Multi-actor
  form: `PERGEN_API_TOKENS=alice:tok1,bob:tok2`. The matched actor
  lands on `flask.g.actor` and in every audit log line.
- **Destructive routes** (`/api/transceiver/recover`, `clear-counters`)
  require `X-Confirm-Destructive: yes` (always-on in production).
- **SPA XSS rule** (Wave-6 Phase C, lint-enforced): see § 2 frontend
  table.
- **Credential v2 fall-through bridge** is the single most important
  context for any task touching credentials, runners, or device-exec
  routes — see [`AGENTS.md`](AGENTS.md) "Pergen credential store" for
  the full diagram. Do **not** refactor away `_v2_db_path()` or
  `_read_from_v2()` in `backend/credential_store.py` until Phase 5/6 of
  [`docs/refactor/DONE_credential_store_migration.md`](docs/refactor/DONE_credential_store_migration.md)
  lands. Use `CredentialService` for any new write/read code path.

If you find a security issue: **STOP** → invoke the **`security-reviewer`**
agent → fix CRITICAL first → rotate any exposed secret → grep the
codebase for similar shapes.

### 3.4 Plan before execute

Multi-PR or multi-session work goes through a **planning step** first
(invoke the **`planner`** or **`architect`** agent for non-trivial
features). Single-file edits and obvious bug fixes do not need a plan.

### 3.5 Conventional commits

`<type>: <description>` — Types: `feat`, `fix`, `refactor`, `docs`,
`test`, `chore`, `perf`, `ci`. Recent log on `refactor/ood-tdd` follows
this strictly; match the existing pattern.

---

## 4. Repository layout

```
pergen/
├── backend/
│   ├── app.py                     # 87-line legacy shim (Flask global + aliases)
│   ├── app_factory.py             # create_app() — registers 12 blueprints + auth gate
│   ├── credential_store.py        # legacy module + wave-7 v2 fall-through bridge
│   ├── parse_output.py            # 151-line back-compat shim → backend/parsers/
│   ├── transceiver_recovery_policy.py  # Leaf-only + Ethernet1/1–1/48 policy gate
│   ├── logging_config.py          # structured logging (CSP/HSTS headers)
│   ├── request_logging.py         # per-request audit + security headers
│   ├── blueprints/                # 12 per-domain Flask Blueprints + auth_bp + health_bp
│   ├── services/                  # business logic (device / credential / inventory / notepad / report / transceiver / run_state_store)
│   ├── repositories/              # data access (credential / inventory / notepad / report) + credential_migration
│   ├── runners/                   # Arista eAPI, Cisco NX-API, SSH, interface_recovery + factory + base_runner
│   ├── parsers/                   # 31 modules: common/ arista/ cisco_nxos/ generic/ + dispatcher.py + engine.py
│   ├── security/                  # sanitizer / validator / encryption / csrf
│   ├── utils/                     # interface_status / transceiver_display / bgp_helpers / ping
│   ├── config/                    # app_config.py, commands.yaml, parsers.yaml, settings.py, commands_loader.py
│   ├── cli/                       # backfill / migration entrypoints
│   ├── inventory/                 # CSV inventory + sample (real CSV is gitignored)
│   ├── instance/                  # SQLite credential DBs, notepad, reports (gitignored)
│   ├── static/                    # SPA: index.html, js/{theme-init,app}.js, vendor/jszip.min.js, screenshots/
│   ├── bgp_looking_glass/         # legacy BGP module (still in use, wrapped by bgp_bp)
│   ├── find_leaf/                 # legacy find-leaf module (wrapped by network_lookup_bp)
│   ├── nat_lookup/                # legacy NAT lookup module (wrapped by network_lookup_bp)
│   └── route_map_analysis/        # legacy route-map module (wrapped by network_ops_bp)
│
├── tests/                         # 157 .py files, 1888 tests + 1 xfail
│   ├── conftest.py                # shared fixtures
│   ├── e2e/specs/                 # 43 Playwright specs, 100 tests
│   ├── frontend/                  # 54 Vitest tests
│   ├── golden/                    # 28 vendor parser snapshots (byte-for-byte locks)
│   ├── parsers/                   # parser unit tests
│   ├── fixtures/                  # captured device output for golden tests
│   ├── bgp_looking_glass/, find_leaf/, nat_lookup/, route_map_analysis/  # legacy module coverage
│   └── test_*.py                  # service / blueprint / security / regression tests
│
├── docs/                          # all DONE_*-prefixed; refactor program sealed
│   ├── code-review/               # python-reviewer outputs per wave
│   ├── refactor/                  # all 14 plans, all DONE_
│   ├── security/                  # security-reviewer outputs + spa_xss_policy.md
│   ├── test-coverage/             # coverage + e2e gap analyses per wave
│   └── audit/                     # cross-cutting audit notes
│
├── scripts/
│   ├── migrate_credentials_v1_to_v2.py   # canonical operator credential migration (idempotent + verify)
│   └── __init__.py
│
├── vendor_pkgs/                   # pinned wheels; read-only; ignored by ruff + coverage
├── playwright.config.ts           # Playwright config (boots real Flask via run.sh)
├── vitest.config.ts               # Vitest config (jsdom)
├── pytest.ini                     # strict markers + strict config
├── pyproject.toml                 # ruff + coverage config
├── package.json                   # devDependencies for E2E + frontend tests
├── Makefile                       # canonical task runner (see § 5)
├── run.sh                         # dev server boot (auto-loads .env, sets FLASK_APP)
├── requirements.txt               # production deps
├── requirements-dev.txt           # test + lint deps
├── .env.example                   # operator template (copy to .env, never commit)
└── *.md                           # top-level docs (see § 6)
```

---

## 5. Common commands

### Boot the dev server

```bash
source venv/bin/activate
./run.sh                                  # canonical — sets FLASK_APP, loads .env, prints URL
# or, manually:
export FLASK_APP=backend.app_factory:create_app
export FLASK_CONFIG=development
python -m flask run
```

> **Never** boot `FLASK_APP=backend.app` directly — that shim has zero
> routes and will 404 on every URL.

### Tests

```bash
make test           # full pytest suite (~110 s)
make test-fast      # only @pytest.mark.unit tests
make cov            # global coverage (gate: 45 %)
make cov-new        # OOD-scoped coverage (gate: 85 %)
make e2e-install    # one-time: npm install + npx playwright install chromium
make e2e            # Playwright suite (~16 s)
npm run test:frontend          # Vitest (54 tests, ~1 s)
npm run test:frontend:coverage # Vitest with coverage
```

### Lint

```bash
make lint           # ruff check (read-only)
make lint-fix       # ruff check --fix
```

---

## 6. Documentation guide — where to look

### Top-level (read in this order on day one)

| File | What's inside |
|---|---|
| [`README.md`](README.md) | Feature tour, refactor at a glance, audit-hardening table, screenshots, run-locally guide, API endpoint table |
| [`AGENTS.md`](AGENTS.md) | **Read first if you are an AI agent.** Generic ECC plugin guidance + Pergen-specific notes (env knobs, credential store v2 fall-through, audit references) |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Layered design, module reference, per-blueprint routing table, post-Phase-13 hardening details |
| [`HOWTOUSE.md`](HOWTOUSE.md) | Operational guide: prerequisites, env vars, migration script, test commands, deployment recipes |
| [`FUNCTIONS_EXPLANATIONS.md`](FUNCTIONS_EXPLANATIONS.md) | Per-class function reference (use as a lookup table, not a tutorial) |
| [`TEST_RESULTS.md`](TEST_RESULTS.md) | Full test matrix with breakdown by category, headline numbers per wave |
| [`patch_notes.md`](patch_notes.md) | Per-version changelog (currently `v0.7.10` at the top, descends through wave-7 → wave-1) |
| [`ECC_USAGE_GUIDE.md`](ECC_USAGE_GUIDE.md) | How to use the ECC plugin (agents/skills/commands/hooks) inside this repo |
| [`comparison_from_original.md`](comparison_from_original.md) | What changed from the pre-refactor baseline (historical reference) |
| [`.env.example`](.env.example) | All env knobs with defaults — copy to `.env`, never commit `.env` |

### Latest audit references (start here when investigating a regression)

| Area | File |
|---|---|
| Security audit (current) | [`docs/security/DONE_audit_2026-04-23-wave7.md`](docs/security/DONE_audit_2026-04-23-wave7.md) |
| Python review (current) | [`docs/code-review/DONE_python_review_2026-04-23-wave7.md`](docs/code-review/DONE_python_review_2026-04-23-wave7.md) |
| Coverage by module | [`docs/test-coverage/DONE_coverage_audit_2026-04-23-wave7.md`](docs/test-coverage/DONE_coverage_audit_2026-04-23-wave7.md) |
| Playwright stability | [`docs/test-coverage/DONE_e2e_gap_analysis_2026-04-23-wave7.md`](docs/test-coverage/DONE_e2e_gap_analysis_2026-04-23-wave7.md) |
| SPA XSS policy | [`docs/security/spa_xss_policy.md`](docs/security/spa_xss_policy.md) |

### Historical / sealed plans (carry context, not current work)

- `docs/refactor/DONE_*` — every refactor plan, all 14 sealed.
  Notable: `DONE_credential_store_migration.md` (still has Phase 5/6
  pending — required reading before touching `credential_store.py`),
  `DONE_app_decomposition.md`, `DONE_parse_output_split.md`,
  `DONE_spa_auth_ui.md`, `DONE_xss_innerhtml_audit.md`,
  `DONE_wave3_roadmap.md`, `DONE_wave4_followups.md`.
- `docs/security/DONE_audit_*.md`, `docs/code-review/DONE_python_review_*.md`,
  `docs/test-coverage/DONE_coverage_audit_*.md`,
  `docs/test-coverage/DONE_e2e_gap_analysis_*.md` — one set per wave
  (waves 1, 2, 4, 7 have current files; intermediate waves are folded
  into adjacent ones).

### Cursor / agent rule files

- [`.cursorrules`](.cursorrules) — repo-wide guidance for Cursor.
- `.cursor/` — per-area cursor rules (read-only, do not edit casually).
- `.opencode/skills/` — project-scoped OpenCode skills available in
  this repo.

---

## 7. Operationally important env knobs

Full table in [`AGENTS.md`](AGENTS.md) "Pergen env knobs" and
[`HOWTOUSE.md`](HOWTOUSE.md) § 3. The ones you will trip on first:

| Variable | Default | Purpose |
|---|---|---|
| `PERGEN_API_TOKEN` / `PERGEN_API_TOKENS` | unset (dev) / **REQUIRED** in prod (≥32 chars) | Bearer auth gate; multi-actor form `actor:token,actor:token` lands on `flask.g.actor` |
| `PERGEN_AUTH_COOKIE_ENABLED` | unset | When `=1`, SPA can auth via `POST /api/auth/login` → `pergen_session` cookie + `X-CSRF-Token` |
| `PERGEN_SESSION_LIFETIME_HOURS` | `8` | Max cookie lifetime (was Flask's 31-day default) |
| `PERGEN_SESSION_IDLE_HOURS` | = lifetime | Idle-timeout |
| `PERGEN_TRUST_PROXY` | unset | `=1` mounts `ProxyFix`; **required behind nginx/Caddy/cloud LB**, do NOT set otherwise |
| `PERGEN_DEV_BIND_HOST` | `127.0.0.1` | Bind host for the legacy `python -m backend.app __main__` shim |
| `PERGEN_DEV_ALLOW_PUBLIC_BIND` | unset | Override for the bind-host guard (not needed when booting through `app_factory`) |
| `PERGEN_REQUIRE_DESTRUCTIVE_CONFIRM` | unset (dev) / always-on (prod) | Requires `X-Confirm-Destructive: yes` on transceiver recover/clear-counters |
| `PERGEN_BLOCK_INTERNAL_PING` | unset | `/api/ping` defaults to **allow** internal targets (wave-7.1 deliberate posture); set `=1` for default-deny SSRF guard |
| `PERGEN_DEV_OPEN_API` | unset | When `=1`, dev/test boot with no token gate is allowed |
| `PERGEN_SSH_STRICT_HOST_KEY` / `PERGEN_SSH_KNOWN_HOSTS` | unset / unset | `=1` + path locks paramiko to `RejectPolicy`; default `AutoAddPolicy` is intentional for internal device enrollment |
| `PERGEN_RECOVERY_BOUNCE_DELAY_SEC` | `5` | Delay between `shutdown` and `no shutdown` in interface bounce; clamped to `[1, 30]` |
| `PERGEN_INVENTORY_PATH` | `backend/inventory/inventory.csv` | CSV inventory path |
| `PERGEN_INSTANCE_DIR` | `backend/instance` | Notepad / reports / credential DB root |
| `SECRET_KEY` | `pergen-default-secret-CHANGE-ME` (refused in prod) | Master secret, ≥16 chars |

---

## 8. Available agents (delegate proactively)

The ECC plugin ships 28 agents; the ones most relevant to Pergen work:

| Agent | When |
|---|---|
| **planner** | Multi-PR features, refactoring, anything spanning >2 files |
| **architect** | New layer, new vendor, cross-cutting concerns |
| **tdd-guide** | Any new feature or bug fix — write the test first |
| **code-reviewer** | Immediately after writing/modifying code |
| **security-reviewer** | Before commits touching auth / crypto / input parsing / SSH / SQL / HTML rendering |
| **python-reviewer** | After writing Python — idiom, type hints, error handling |
| **e2e-runner** | When adding or debugging Playwright specs |
| **doc-updater** | Keep `ARCHITECTURE.md`, `HOWTOUSE.md`, `FUNCTIONS_EXPLANATIONS.md`, `patch_notes.md`, `TEST_RESULTS.md`, `README.md` in sync |
| **refactor-cleaner** | Dead code sweeps |
| **build-error-resolver** | When `make test` or `make cov-new` fails on import / collection errors |

Use **parallel execution** for independent operations (security review +
python review + coverage + E2E can all run concurrently — wave-1
through wave-7 audits did exactly this).

---

## 9. First-task playbook for a new agent

1. **Read** this file → [`AGENTS.md`](AGENTS.md) → [`README.md`](README.md)
   (top section) → [`ARCHITECTURE.md`](ARCHITECTURE.md) (§ 1 layout +
   § relevant blueprint).
2. **Verify the environment** boots:
   `source venv/bin/activate && make test-fast` should be < 30 s green.
3. **Pick the right layer** — blueprint? service? repository? runner?
   parser? Match the existing pattern. Do NOT invent a new layer.
4. **Write the failing test first** under `tests/` with the right
   marker. For a new HTTP route, that's typically a Flask test-client
   test plus a Playwright spec under `tests/e2e/specs/`.
5. **Implement** in the right layer. Keep blueprints thin, keep
   services pure, keep parsers vendor-scoped.
6. **Run the gates** — `make test`, `make cov-new`, `npm run test:frontend`,
   `make e2e`. All four must be green.
7. **Lint** — `make lint`. Your new code must be **0 errors** (122
   pre-existing style findings exist; do not let your diff add to
   them).
8. **Document** — patch_notes.md (top entry), and any of
   `ARCHITECTURE.md` / `HOWTOUSE.md` / `FUNCTIONS_EXPLANATIONS.md` /
   `TEST_RESULTS.md` / `README.md` whose surface you changed.
9. **Commit** with conventional-commit format. Match the wave-7
   commits in `git log` for the house style.
10. **For credentials work** — re-read [`AGENTS.md`](AGENTS.md)
    "Pergen credential store" first. The two-tier fall-through is the
    most common foot-gun.

---

## 10. Known gaps and pending work

- **Audit GAP #8** — inventory import row cap not yet enforced.
  Tracked by the single strict `xfail` in the suite. Will XPASS when
  the cap lands.
- **Credential migration Phase 5 / Phase 6** — still pending in
  [`docs/refactor/DONE_credential_store_migration.md`](docs/refactor/DONE_credential_store_migration.md).
  The wave-7 fall-through bridge is the transition aid; do not remove
  it until both phases ship.
- **122 pre-existing ruff style findings** — `I001` import-sort,
  `B904` raise-from, `UP006`/`UP035` modern typing. Advisory; clean up
  opportunistically when you are already in the file.
- **6 npm moderate vulnerabilities** — `vite-node` dev-only, never
  shipped. Track but do not block on.
- **Boot foot-gun** — `FLASK_APP=backend.app` (no `_factory`) starts
  Flask but serves 404 on every URL. Always boot through
  `app_factory:create_app` or `./run.sh`.

---

## 11. Quick links

- Branch: `refactor/ood-tdd`
- Latest tag (internal): `v0.7.10`
- Patch notes head: [`patch_notes.md`](patch_notes.md) v0.7.10
- App factory entry: `backend/app_factory.py:create_app`
- 12 blueprints registered: `backend/blueprints/`
- Credential v2 bridge: `backend/credential_store.py` (`_v2_db_path`,
  `_read_from_v2`)
- Credential migration script:
  `scripts/migrate_credentials_v1_to_v2.py`
- SPA entry: `backend/static/index.html` + `backend/static/js/app.js`
- Playwright config: `playwright.config.ts` (boots real Flask via
  `run.sh`)
- Make canonical task runner: `Makefile`
