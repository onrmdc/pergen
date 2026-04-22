# Comparison: `refactor/ood-tdd` vs Upstream `onrmdc/pergen@main`

> **Branch under review:** `refactor/ood-tdd` (single squashed commit `7a3a888`)
> **Upstream baseline:** `onrmdc/pergen@main` (HEAD `eaf6d29`, 17 commits)
> **Methodology:** Tree-level diff (`git diff origin/main..HEAD`). The current branch was force-pushed as a single
> orphan commit, so there is no shared merge base; differences are described file-by-file rather than commit-by-commit.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Diff at a Glance](#2-diff-at-a-glance)
3. [Backend Structure: God-Object → App Factory](#3-backend-structure-god-object--app-factory)
4. [Layered Architecture (New)](#4-layered-architecture-new)
5. [Runner Refactor: Vendor Classes + Factory](#5-runner-refactor-vendor-classes--factory)
6. [Configuration & App Bootstrapping](#6-configuration--app-bootstrapping)
7. [Logging & Observability](#7-logging--observability)
8. [Security Hardening](#8-security-hardening)
9. [Testing & Coverage](#9-testing--coverage)
10. [Tooling & Developer Experience](#10-tooling--developer-experience)
11. [Documentation](#11-documentation)
12. [What Upstream Has That Was Restructured](#12-what-upstream-has-that-was-restructured)
13. [Risks & Trade-offs](#13-risks--trade-offs)
14. [Recommended Path Forward](#14-recommended-path-forward)
15. [Appendix: Full File Inventory](#15-appendix-full-file-inventory)

---

## 1. Executive Summary

The `refactor/ood-tdd` branch is a **comprehensive object-oriented redesign and TDD-driven hardening** of the original
single-file Pergen application. The original `backend/app.py` was a 1,727-line god-object holding 53 routes, inline
business logic, inline credential handling, and inline runner dispatch. After the refactor:

| Dimension | Upstream `main` | `refactor/ood-tdd` | Δ |
|---|---|---|---|
| `backend/app.py` size | 1,727 lines | **87 lines** (95% reduction) | shim only |
| Routes registered in `app.py` | 53 (`@app.route`) | **0** | all moved to blueprints |
| Flask Blueprints | 0 | **12** (54 routes total) | new layer |
| Service classes | 0 | **7** | new layer |
| Repository classes | 0 | **4** | new layer |
| Security modules | 0 | **3** (sanitizer, validator, encryption) | new layer |
| Vendor runner classes | 0 (procedural) | **3** (Cisco, Arista, SSH) + factory + base | new abstraction |
| Test files | 6 | **46** | +40 (≈ 7.7×) |
| Coverage (line %) | not measured | **74.8 %** (4,245 / 5,340 stmts) | enforced via `Makefile cov` |
| Top-level docs | 1 (`README.md`) | **8** (+ARCHITECTURE, HOWTOUSE, FUNCTIONS_EXPLANATIONS, TEST_RESULTS, patch_notes…) | +7 |
| Tooling files | `run.sh` only | `Makefile`, `pyproject.toml`, `pytest.ini`, `requirements-dev.txt` | full dev loop |

**Diff total:** `147 files changed, +21,262 insertions, -1,837 deletions`.

The refactor preserves the same operator-facing functionality (every legacy route still resolves) while introducing the
layers needed to test it, secure it, and grow it without re-touching a 1,700-line file.

---

## 2. Diff at a Glance

```
$ git diff origin/main..HEAD --stat | tail -1
147 files changed, 21262 insertions(+), 1837 deletions(-)

$ git diff origin/main..HEAD --diff-filter=A --name-only | wc -l
129  # added files

$ git diff origin/main..HEAD --diff-filter=M --name-only | wc -l
18   # modified files

$ git diff origin/main..HEAD --diff-filter=D --name-only | wc -l
0    # no files deleted (legacy modules kept as shims/re-exports)
```

**Modified files (18):**
`.gitignore`, `README.md`, `requirements.txt`, `backend/app.py`, `backend/bgp_looking_glass.py`,
`backend/credential_store.py`, `backend/find_leaf.py`, `backend/inventory/__init__.py`, `backend/inventory/loader.py`,
`backend/inventory/normalize_inventory.py`, `backend/nat_lookup.py`, `backend/parse_output.py`,
`backend/runners/__init__.py`, `backend/runners/arista_eapi.py`, `backend/runners/cisco_nxapi.py`,
`backend/runners/interface_recovery.py`, `backend/runners/runner.py`, `backend/runners/ssh_runner.py`.

**Top-level files added:** `ARCHITECTURE.md`, `FUNCTIONS_EXPLANATIONS.md`, `HOWTOUSE.md`, `TEST_RESULTS.md`,
`patch_notes.md`, `Makefile`, `pyproject.toml`, `pytest.ini`, `requirements-dev.txt`.

**Backend modules added (47):** see [§15 Appendix](#15-appendix-full-file-inventory).

**Test files added:** 72 new files under `tests/` (44 top-level test modules + golden + helpers).

---

## 3. Backend Structure: God-Object → App Factory

### Upstream (`origin/main`)

```
backend/
├── app.py                   1,727 lines, 53 @app.route handlers
├── bgp_looking_glass.py
├── credential_store.py
├── find_leaf.py
├── nat_lookup.py
├── parse_output.py
├── route_map_analysis.py
├── transceiver_recovery_policy.py
├── config/
│   ├── commands_loader.py
│   ├── commands.yaml
│   ├── parsers.yaml
│   └── settings.py
├── inventory/
│   ├── loader.py
│   └── normalize_inventory.py
├── runners/
│   ├── __init__.py          (1 export: run_device_commands)
│   ├── arista_eapi.py
│   ├── cisco_nxapi.py
│   ├── interface_recovery.py
│   ├── runner.py
│   └── ssh_runner.py
└── static/
```

`backend/app.py` was the single entry point: it created the `Flask` global, registered every route, called the runners
directly, parsed responses inline, and managed the credential store on import. The file held ~85% of all backend logic.

### `refactor/ood-tdd`

```
backend/
├── app.py                   87 lines — Flask global + legacy _* aliases only
├── app_factory.py           create_app() — registers all 12 blueprints
├── blueprints/              12 modules, 54 routes total
│   ├── bgp_bp.py            (8 routes)
│   ├── commands_bp.py       (3)
│   ├── credentials_bp.py    (4)
│   ├── device_commands_bp.py(4)
│   ├── health_bp.py         (2)
│   ├── inventory_bp.py      (12)
│   ├── network_lookup_bp.py (3)
│   ├── network_ops_bp.py    (2)
│   ├── notepad_bp.py        (2)
│   ├── reports_bp.py        (3)
│   ├── runs_bp.py           (8)
│   └── transceiver_bp.py    (3)
├── services/                7 service classes
├── repositories/            4 repository classes
├── parsers/                 ParserEngine class wrapping legacy parse_output
├── security/                sanitizer + validator + encryption
├── config/
│   ├── app_config.py        BaseConfig / DevelopmentConfig / TestingConfig / ProductionConfig
│   ├── commands_loader.py   (kept)
│   ├── commands.yaml        (kept)
│   ├── parsers.yaml         (kept)
│   └── settings.py          (kept)
├── utils/                   bgp_helpers / interface_status / ping / transceiver_display
├── logging_config.py        LoggingConfig (text + JSON formatters)
├── request_logging.py       RequestLogger middleware (req-ID + timing)
└── runners/                 base_runner + factory + cisco_runner + arista_runner + ssh_runner_class + _http (+ legacy)
```

### What changed in `app.py`

| Aspect | Upstream | Refactor |
|---|---|---|
| Total lines | 1,727 | 87 |
| `@app.route` handlers | 53 | 0 |
| Service-layer calls | direct vendor SDK calls inline | not present (delegated to blueprints/services) |
| SECRET_KEY handling | inline default | sentinel placeholder rejected by `ProductionConfig.validate()` |
| Route registration | side-effect of import | explicit via `create_app()` in `app_factory.py` |
| Helper functions | ~30 free functions inline | extracted to `backend/utils/*` (with `_*` aliases re-exported for backward compatibility) |

### Wrapping vs. rewriting

The refactor uses a **wrapping App Factory**: `backend/app_factory.py::create_app()` imports the legacy module to keep
the side-effect-based `Flask(__name__)` global, then layers config validation, structured logging, and request
middleware on top, then mounts the new blueprints. This was a deliberate choice (documented in `app_factory.py:13-35`)
to avoid silent route drift while migrating — the **107 golden tests** in `tests/golden/` lock the pre-refactor route
contract so any regression is caught by the test suite, not in production.

After Phase 12 the legacy `app.py` is now only the Flask global + SECRET_KEY wiring + `_*` helper re-exports, and every
route lives in a blueprint. The 87-line shim exists solely so existing `FLASK_APP=backend.app flask run` invocations
keep working.

---

## 4. Layered Architecture (New)

The refactor introduces five new layers between HTTP and storage. None existed upstream.

### 4.1 Service Layer (`backend/services/`)

| Service | Responsibility |
|---|---|
| `credential_service.py` | Encrypted credential CRUD; wraps `CredentialRepository` + `EncryptionService` |
| `device_service.py` | Orchestrates runners + parsers for a `(device, command)` request |
| `inventory_service.py` | Inventory load + filter + lookup; wraps `InventoryRepository` |
| `notepad_service.py` | Notepad CRUD; wraps `NotepadRepository` |
| `report_service.py` | Saved-report list / get / delete; wraps `ReportRepository` |
| `run_state_store.py` | In-memory pre/post run state (thread-safe) |
| `transceiver_service.py` | Cross-vendor transceiver merge + recovery policy application |

Services are **pure-Python objects** with constructor-injected dependencies. Blueprints instantiate them once at module
load; tests instantiate them with mock repositories and runners.

### 4.2 Repository Layer (`backend/repositories/`)

| Repository | Storage backend |
|---|---|
| `credential_repository.py` | SQLite (encrypted blobs) |
| `inventory_repository.py` | CSV file (`backend/inventory/inventory.csv` or `PERGEN_INVENTORY_PATH`) |
| `notepad_repository.py` | JSON file |
| `report_repository.py` | gzip-compressed JSON files on disk |

Each exposes `findAll / findById / create / update / delete` (where applicable). Services depend on the abstract
interface, not the concrete storage — swapping CSV → DB or filesystem → S3 is a one-class change.

### 4.3 Parser Layer (`backend/parsers/engine.py`)

`ParserEngine` is a class wrapper around the legacy `parse_output` dispatcher and the YAML parser registry. Why a
class:

- Routes / services depend on a single injectable object instead of a free function + module-level dict.
- Test doubles can supply an in-memory registry (no YAML file needed).
- Unknown command IDs return `{}` instead of raising — the engine is the authoritative *"do I know how to parse this?"*
  check.

### 4.4 Security Layer (`backend/security/`)

See [§8 Security Hardening](#8-security-hardening).

### 4.5 Utilities (`backend/utils/`)

Helpers extracted from the legacy `app.py`:

- `bgp_helpers.py` — `wan_rtr_has_bgp_as`
- `interface_status.py` — `iface_status_lookup`, `interface_status_trace`, `cisco_interface_detailed_trace`,
  `merge_cisco_detailed_flap`
- `ping.py` — `single_ping`, `MAX_PING_DEVICES`
- `transceiver_display.py` — `transceiver_errors_display`, `transceiver_last_flap_display`

`backend/app.py` re-exports these under their original `_*` names so any in-tree caller (and the regression test that
resolves `backend.app._foo`) continues to work.

---

## 5. Runner Refactor: Vendor Classes + Factory

### Upstream

```python
# backend/runners/__init__.py (upstream)
from .runner import run_device_commands
__all__ = ["run_device_commands"]
```

A single `run_device_commands(...)` function in `backend/runners/runner.py` switched on `vendor` / `method` strings and
called procedural helpers (`backend/runners/arista_eapi.py`, `backend/runners/cisco_nxapi.py`,
`backend/runners/ssh_runner.py`).

### Refactor

```
backend/runners/
├── __init__.py
├── base_runner.py          BaseRunner (ABC) — uniform run_commands() contract
├── factory.py              RunnerFactory — thread-safe singleton cache per (vendor, model, method)
├── cisco_runner.py         CiscoNxapiRunner(BaseRunner)
├── arista_runner.py        AristaEapiRunner(BaseRunner)
├── ssh_runner_class.py     SshRunner(BaseRunner)
├── _http.py                Shared HTTP helpers (TLS, retries, timeouts) used by Cisco + Arista
├── interface_recovery.py   (kept)
├── runner.py               (kept — wrapped by factory)
├── arista_eapi.py          (kept — used by AristaEapiRunner)
├── cisco_nxapi.py          (kept — used by CiscoNxapiRunner)
└── ssh_runner.py           (kept — used by SshRunner)
```

Key properties:

- **Stateless runners** — credentials are passed per call, never stored on the instance, so the factory can safely
  share singletons across threads.
- **Uniform return contract** — every `run_commands()` returns `(results, error_message_or_none)` so the service layer
  treats all transports identically.
- **Lookup precedence** (factory.py:9-15):
  1. `method == "ssh"` → `SshRunner` regardless of vendor
  2. `method == "api"`, vendor `"arista"` → `AristaEapiRunner`
  3. `method == "api"`, vendor `"cisco"` → `CiscoNxapiRunner`
  4. anything else → `ValueError`

The legacy procedural functions remain in place as private implementation details; the new classes wrap and harden
them (TLS verification flags, sane timeouts, structured error reporting via `_http.py`).

---

## 6. Configuration & App Bootstrapping

### Upstream

`backend/config/settings.py` exposed module-level constants. `SECRET_KEY` was set inline in `backend/app.py` with no
production validation.

### Refactor

`backend/config/app_config.py` introduces a config hierarchy:

| Class | DEBUG | TESTING | Notes |
|---|---|---|---|
| `BaseConfig` | — | — | Shared defaults, env resolution |
| `DevelopmentConfig` | True | False | Verbose colour logging, scheduler enabled |
| `TestingConfig` | False | True | In-memory SQLite, scheduler disabled |
| `ProductionConfig` | False | False | JSON logs, `validate()` rejects placeholder `SECRET_KEY` |

`ProductionConfig.validate()` enforces:

- `SECRET_KEY` ≠ `pergen-default-secret-CHANGE-ME` (the new sentinel)
- `SECRET_KEY` ≠ `dev-secret-change-in-prod` (the historic upstream placeholder — also rejected so an operator who
  copied the value forward also fails fast)
- `len(SECRET_KEY) >= 16`

`backend/app_factory.py::create_app(config_name)` performs:

1. Look up the config class from `CONFIG_MAP`.
2. Validate it (production refuses default secret).
3. Import legacy `backend.app` (registers Flask global as side-effect).
4. Apply the new config values onto `app.config`.
5. Configure logging (`LoggingConfig`) per resolved config.
6. Mount `RequestLogger.init_app(app)` middleware.
7. Re-init credential DB if `SECRET_KEY` changed (for tests).
8. Return `app`.

`backend/config/settings.py`, `commands_loader.py`, `commands.yaml`, and `parsers.yaml` are kept unchanged for runtime
compatibility.

---

## 7. Logging & Observability

### Upstream

Plain `print()` and the default Flask logger. No request IDs, no structured fields, no correlation IDs.

### Refactor

| Module | Purpose |
|---|---|
| `backend/logging_config.py` | `LoggingConfig` — text and JSON formatters; per-env log level / format / file routing |
| `backend/request_logging.py` | `RequestLogger` — Flask middleware adding request-ID, timing, and structured per-request log lines |

`ProductionConfig` enables JSON formatter so logs ship cleanly into ELK / Loki / CloudWatch. Each request gets a UUID
threaded through every log line emitted during its lifetime, making cross-service tracing possible.

Per `tests/test_security_phase13.py` and `tests/test_security_audit_findings.py`, security-relevant events
(rejected inputs, blocked commands, tampered credentials) are logged at `WARNING` for downstream SIEM consumption.

---

## 8. Security Hardening

The single largest functional improvement vs. upstream. **Audit batches 1–4** remediated 24+ findings (4 CRITICAL, 9
HIGH, 11 MEDIUM) raised by automated reviewers (`security-reviewer`, `python-reviewer`).

### 8.1 New `backend/security/` module

| File | Class | Highlights |
|---|---|---|
| `sanitizer.py` | `InputSanitizer` | Pure-function validators returning `(ok, value_or_reason)` 2-tuples; never raises; rejects null bytes; ReDoS-safe pre-compiled patterns; logs every rejection at WARNING |
| `validator.py` | `CommandValidator` | Defence-in-depth read-only command guard; max length 512; allows `show ` / `dir ` only; blocklists `;`, `&&`, `\|\|`, backticks, `$(`, `conf t`, `configure terminal`, `write mem`, `copy run start`, `\| write` |
| `encryption.py` | `EncryptionService` | AES-128-CBC + HMAC-SHA256 (or Fernet when `cryptography` is present); PBKDF2-HMAC-SHA256 with 200 000 iterations; encrypt-then-MAC; `from_secret('')` raises instead of silently producing an empty key |

### 8.2 Hardening applied across the codebase

- **defusedxml hard-required** (`requirements.txt`): the legacy `nat_lookup.py` parses untrusted XML from network
  firewalls; the stdlib `xml.etree` parser is vulnerable to billion-laughs / XXE.
- **SECRET_KEY placeholder rejection** (`backend/config/app_config.py`).
- **API token gate** (`backend/app_factory.py:48`): minimum 32-char token when the auth gate is active.
- **SSRF guard** on `/api/ping` (network_ops_bp.py).
- **Input sanitisation** at every blueprint boundary (the `InputSanitizer` returns `(ok, reason)` tuples that
  blueprints translate to `400` responses with safe error messages).
- **Path-handling hardened with `pathlib`** — Audit H-9 batch 3.
- **TLS verification flags** correctly defaulted in `_http.py`.
- **Encrypted credential storage** replaces upstream's base64 fallback in `credential_store.py`.

### 8.3 Security test corpus

| Test file | Tests | Scope |
|---|---|---|
| `tests/test_security_owasp.py` | 72 | OWASP Top-10 coverage (XSS / SQLi / SSRF / open redirect / path traversal / null-byte injection / etc.) |
| `tests/test_security_phase13.py` | 33 | Hardening surface for the security/ module itself |
| `tests/test_security_audit_findings.py` | regression tests for batches 1–2 |
| `tests/test_security_audit_batch3.py` | regression tests for batch 3 (24 findings) |
| `tests/test_security_audit_batch4.py` | regression tests for batch 4 |

---

## 9. Testing & Coverage

### Upstream

```
tests/
├── __init__.py
├── test_bgp_looking_glass.py
├── test_interface_recovery.py
├── test_parse_arista_interface_status.py
├── test_parse_cisco_interface_detailed.py
└── test_transceiver_recovery_policy.py        (5 test modules)
```

No coverage instrumentation, no `pytest.ini`, no test markers, no security tests.

### Refactor

```
tests/                                          (44 test modules + helpers)
├── golden/                                     route-baseline regression tests
│   └── test_routes_baseline.py                 locks pre-refactor route behaviour
├── test_app_factory.py
├── test_blueprints_*.py                        per-blueprint
├── test_security_*.py                          OWASP + audit batches
├── test_runner_dispatch_coverage.py
├── test_*_phase{2,8,9,10,11,13}.py             per-decomposition-phase tests
└── ...
```

| Metric | Value |
|---|---|
| Total test modules | **46** |
| Total test functions | **802** (per `TEST_RESULTS.md`) |
| Coverage — line | **74.8 %** (4,245 / 5,340 statements) |
| Coverage — branch | **64 %** (1,449 / 2,270 branches) |
| Coverage — new OOD layer (blueprints + services + utils) | **94 %** (target gate: 90 %) |
| Coverage — whole-project gate | 45 % (legacy modules drag the average down) |
| Lint (`ruff check` on new code) | **0 errors** |
| Audit findings remediated | **24 / 24** |

`pytest.ini` defines test markers (`unit`, `integration`, `security`, `golden`) and `filterwarnings`. `Makefile cov`
and `Makefile cov-new` enforce the coverage gates.

### Test categories

| Category | Notes |
|---|---|
| **Unit** | Pure-Python service / repository / parser / security tests |
| **Integration** | Flask test client driving full request → blueprint → service → repository chains |
| **Security** | OWASP fuzz + injection + SSRF + audit-finding regression |
| **Golden** | `tests/golden/test_routes_baseline.py` snapshots every legacy route's contract so the refactor cannot silently change behaviour |

---

## 10. Tooling & Developer Experience

| Tool | Upstream | Refactor |
|---|---|---|
| Run script | `run.sh` | `run.sh` (kept) + `Makefile run` |
| Test runner | manual `pytest` | `make test`, `make test-fast`, `make cov`, `make cov-new` |
| Coverage | none | `pytest-cov` configured via `pyproject.toml` + `Makefile cov` |
| Linter | none | `ruff` configured + `make lint` / `make lint-fix` |
| Dev install | manual | `make install-dev` |
| Test markers | none | `unit`, `integration`, `security`, `golden` (in `pytest.ini`) |
| Project metadata | none | `pyproject.toml` (PEP 621) |
| Dev requirements | shared with prod | separate `requirements-dev.txt` (`pytest`, `pytest-cov`, `pytest-mock`, `responses`, `freezegun`, `ruff`) |

`.gitignore` extended to exclude `.pytest_cache/`, `.ruff_cache/`, `.coverage`, `coverage.xml`, `htmlcov/`, `logs/`,
plus the `.opencode/` and `.cursor/` workspace dirs (not source-controlled).

---

## 11. Documentation

### Upstream

- `README.md` (184 lines) — install + screenshots + feature overview.

### Refactor

- `README.md` (288 lines) — extended for the OOD/TDD layout.
- `ARCHITECTURE.md` — full layered-architecture map (blueprints / services / repositories / runners / security / config).
- `HOWTOUSE.md` — operator runbook (install, env, run, configure, test).
- `FUNCTIONS_EXPLANATIONS.md` — per-route / per-function reference.
- `TEST_RESULTS.md` — reproducible numbers (test counts, coverage, lint, audit closures).
- `patch_notes.md` — per-phase changelog of the refactor work.
- `AGENTS.md` — agent-instruction file (project-level Claude Code / OpenCode policy).
- `ECC_USAGE_GUIDE.md` — Everything Claude Code usage notes.

> The `.opencode/` and `.cursor/` workspace directories were intentionally excluded when the branch was force-pushed
> (per `.gitignore`).

---

## 12. What Upstream Has That Was Restructured

The original branch `onrmdc/pergen@main` shipped these features in the latest 17 commits (oldest → newest):

```
3241d78 Initial commit: Pergen network device panel
1cf3acc README: screenshots above description, image below (full width)
c7b03fb Remove full inventory from repo: ignore example_inventory.csv, add minimal inventory_sample.csv
1169152 Narrow success-popup and errors-popup screenshots
7e4c743 Merge pull request #1 from onrmdc/onur-setup
1907fff README: sync docs/screenshots popup images with static (new photos)
3010ee4 Use single screenshot folder: backend/static/screenshots
baf5e15 README: show success/errors popup screenshots at 33% width
b8c54f8 Merge branch 'onur-setup'
1e738da checkpoint: saved reports on backend (gzip), API list/get/delete, frontend uses API
39cd245 Merge pull request #2 from onrmdc/onur-setup
0cc29b3 checkpoint: Live Notepad (name, line editors, icons), Diff Checker (LCS, Added/Deleted/Changed, scroll guide)
1035088 Subnet: icon on card, rename to Subnet Divide Calculator, add davidc/subnets reference
e639f51 README: Run locally (clone, venv, flask), Subnet feature + davidc/subnets thanks
88caf2b Transceiver: Cisco MTU from show interface (eth_mtu), UI columns and merge
6fc7546 Transceiver: Cisco/Arista merge, Errors column, recovery policy, UI icons
eaf6d29 docs: expand README for transceiver, API, recovery policy
```

| Upstream feature | Status in `refactor/ood-tdd` | Where it lives now |
|---|---|---|
| Saved reports (gzip backend, API list/get/delete) | Preserved | `backend/blueprints/reports_bp.py` + `backend/services/report_service.py` + `backend/repositories/report_repository.py` |
| Live Notepad (name, line editors) | Preserved | `backend/blueprints/notepad_bp.py` + `backend/services/notepad_service.py` + `backend/repositories/notepad_repository.py` |
| Diff Checker (LCS, Added/Deleted/Changed) | Preserved (frontend feature; backend exposes whatever it needed) | `backend/static/` (frontend asset) |
| Subnet Divide Calculator | Preserved (frontend) | `backend/static/` |
| Transceiver Cisco/Arista merge | Preserved + extracted to service | `backend/services/transceiver_service.py` + `backend/blueprints/transceiver_bp.py` |
| Transceiver recovery policy | Preserved (legacy module kept) | `backend/transceiver_recovery_policy.py` (untouched) |
| Cisco MTU from `show interface` (`eth_mtu`) | Preserved | inside `transceiver_service.py` merge logic |
| Static screenshots / docs assets | Preserved | `backend/static/screenshots/`, `backend/static/assets/` |

**Nothing visible to operators was removed.** The refactor is additive: every upstream route still resolves, every
upstream feature still works, and the same `FLASK_APP=backend.app flask run` command still boots the app. The added
layers wrap the legacy code rather than replacing it.

---

## 13. Risks & Trade-offs

| Risk | Severity | Mitigation in branch |
|---|---|---|
| **Squashed history** — no merge base with `origin/main`, hard to attribute hunks to specific phases | MEDIUM | This document + `patch_notes.md` reconstruct the phase-by-phase narrative |
| **Wrapping factory** still imports the legacy module for its side-effects | MEDIUM | Documented in `app_factory.py:13-35`; 107 golden tests catch route drift |
| **Coverage gate split** (45 % global vs 85 % new code) hides legacy gaps | LOW | Explicit two-gate `Makefile cov` / `Makefile cov-new` makes the split visible |
| **Legacy files kept as shims** (`backend/runners/runner.py`, `arista_eapi.py`, `cisco_nxapi.py`, `ssh_runner.py`) | LOW | Documented as "kept — used by the new class wrappers" |
| **Large diff** (147 files / +21 k LOC) is hard to review as a single PR | HIGH (review effort) | Recommend slicing into phase PRs against upstream — see [§14](#14-recommended-path-forward) |
| **Coverage 74.8 %** is below the 80 % project target in `AGENTS.md` | MEDIUM | New code is at 94 %; remaining gap is in legacy modules slated for further extraction |
| **Branch was force-pushed** with purged history | LOW | Intentional and confirmed by user; this document is the historical record |

---

## 14. Recommended Path Forward

### If the goal is to upstream this work to `onrmdc/pergen`

A 21 k-LOC single PR will not realistically merge. Slice into landable phases:

1. **Tooling + tests scaffolding** — `pyproject.toml`, `pytest.ini`, `Makefile`, `requirements-dev.txt`, golden tests.
   *No behavioural change.*
2. **Security module** — `backend/security/`, tighten `requirements.txt` (defusedxml), reject placeholder SECRET_KEY,
   batches 1–2 audit fixes. *Net security improvement, low review risk.*
3. **Config + logging** — `backend/config/app_config.py`, `backend/logging_config.py`, `backend/request_logging.py`,
   `backend/app_factory.py` (still wrapping). *Behavioural changes only when `FLASK_CONFIG` is set.*
4. **Repositories + services + parsers** — extract storage and business logic; blueprints arrive in subsequent steps.
5. **Runner OO refactor** — base class + factory + vendor classes, keeping legacy procedural callers.
6. **Blueprints** — one PR per blueprint (12 small PRs), each enforced by a slice of golden tests.
7. **Audit batches 3–4** — final hardening + coverage push.

Each step can be reviewed in isolation against `onrmdc/pergen@main`.

### If the goal is to maintain `refactor/ood-tdd` as a fork

- Keep this document + `patch_notes.md` updated with each phase.
- Run `make test cov cov-new lint` in CI on every push.
- Re-fetch upstream weekly and merge new commits as they arrive (most upstream changes will land in `backend/static/`
  or in the legacy modules and won't conflict with the new layers).

---

## 15. Appendix: Full File Inventory

### Added backend modules (47)

```
backend/app_factory.py
backend/blueprints/__init__.py
backend/blueprints/bgp_bp.py
backend/blueprints/commands_bp.py
backend/blueprints/credentials_bp.py
backend/blueprints/device_commands_bp.py
backend/blueprints/health_bp.py
backend/blueprints/inventory_bp.py
backend/blueprints/network_lookup_bp.py
backend/blueprints/network_ops_bp.py
backend/blueprints/notepad_bp.py
backend/blueprints/reports_bp.py
backend/blueprints/runs_bp.py
backend/blueprints/transceiver_bp.py
backend/config/app_config.py
backend/logging_config.py
backend/parsers/__init__.py
backend/parsers/engine.py
backend/repositories/__init__.py
backend/repositories/credential_repository.py
backend/repositories/inventory_repository.py
backend/repositories/notepad_repository.py
backend/repositories/report_repository.py
backend/request_logging.py
backend/runners/_http.py
backend/runners/arista_runner.py
backend/runners/base_runner.py
backend/runners/cisco_runner.py
backend/runners/factory.py
backend/runners/ssh_runner_class.py
backend/security/__init__.py
backend/security/encryption.py
backend/security/sanitizer.py
backend/security/validator.py
backend/services/__init__.py
backend/services/credential_service.py
backend/services/device_service.py
backend/services/inventory_service.py
backend/services/notepad_service.py
backend/services/report_service.py
backend/services/run_state_store.py
backend/services/transceiver_service.py
backend/utils/__init__.py
backend/utils/bgp_helpers.py
backend/utils/interface_status.py
backend/utils/ping.py
backend/utils/transceiver_display.py
```

### Added top-level files

```
ARCHITECTURE.md
FUNCTIONS_EXPLANATIONS.md
HOWTOUSE.md
TEST_RESULTS.md
Makefile
patch_notes.md
pyproject.toml
pytest.ini
requirements-dev.txt
```

### Added test files (excerpt — 72 total)

```
tests/golden/test_routes_baseline.py
tests/test_app_factory.py
tests/test_coverage_push.py
tests/test_credentials_bp_phase7.py
tests/test_device_commands_bp_phase10.py
tests/test_health_bp.py
tests/test_inventory_bp.py
tests/test_legacy_coverage_runners.py
tests/test_logging_config.py
tests/test_network_lookup_bp_phase8.py
tests/test_notepad_bp.py
tests/test_parsers_engine.py
tests/test_repositories.py
tests/test_request_logging.py
tests/test_reports_bp.py
tests/test_runner_dispatch_coverage.py
tests/test_runners_factory.py
tests/test_runs_reports_bp_phase11.py
tests/test_security_audit_batch3.py
tests/test_security_audit_batch4.py
tests/test_security_audit_findings.py
tests/test_security_owasp.py
tests/test_security_phase13.py
tests/test_services.py
tests/test_transceiver_bp_phase9.py
tests/test_utils_phase2.py
…
```

---

## Document metadata

- **Generated:** Wed Apr 22 2026
- **Branch:** `refactor/ood-tdd` @ `7a3a888`
- **Compared against:** `origin/main` (`onrmdc/pergen`) @ `eaf6d29`
- **Method:** `git diff origin/main..HEAD` plus tree inspection (`git ls-tree -r origin/main`)
- **Author:** Generated via OpenCode (`anthropic/claude-opus-4-7`) at user request
