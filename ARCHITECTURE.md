# Pergen — Architecture

This document describes the architecture **after the OOD/TDD refactor**
(branch `refactor/ood-tdd`). Phases 0–9 introduced an App Factory, a
config hierarchy, structured logging, a security layer, repository /
runner / parser / service layers, and the first per-domain Blueprints.
**Phase 13** added post-audit security hardening across every layer
(see §10). **Phases 1–12 (decomposition)** then extracted every
remaining route from the 1,577-line `backend/app.py` monolith into
twelve per-domain Flask Blueprints registered through
`backend/app_factory.py::create_app()`. **Audit batches 1–3** then
remediated 24 findings (4 CRITICAL / 9 HIGH / 11 MEDIUM) from the
post-decomposition `security-reviewer`, `python-reviewer`, and
coverage audits (see §11).

`backend/app.py` is now an **87-line shim** holding only the Flask
global, SECRET_KEY wiring, legacy `_*` helper aliases, and the
`__main__` entry point. All routes live in blueprints; all business
logic lives in services.

---

## 1. High-level layout (after Phase 12 + audit batches)

```
backend/
├── app.py                       # 87-line shim — Flask global + legacy aliases
├── app_factory.py               # create_app() — registers 12 blueprints + auth gate
├── blueprints/                  # 12 per-domain Flask Blueprints
│   ├── bgp_bp.py                #   8 BGP looking-glass routes
│   ├── commands_bp.py           #   3 commands/parsers routes
│   ├── credentials_bp.py        #   4 credential routes (uses CredentialService)
│   ├── device_commands_bp.py    #   4 routes: arista runCmds, custom-command, route-map
│   ├── health_bp.py             #   2 health endpoints
│   ├── inventory_bp.py          #  12 read + write inventory routes
│   ├── network_lookup_bp.py     #   3 routes: find-leaf, NAT lookup
│   ├── network_ops_bp.py        #   2 routes: /api/ping (SSRF-guarded), SPA fallback
│   ├── notepad_bp.py            #   notepad CRUD
│   ├── reports_bp.py            #   3 saved-report routes
│   ├── runs_bp.py               #   8 pre/post run routes
│   └── transceiver_bp.py        #   3 transceiver routes (recover/clear gated)
├── config/
│   ├── app_config.py            # Base/Dev/Test/Prod config (placeholder dedup + min-len)
│   ├── settings.py              # Path resolution
│   ├── commands.yaml            # Vendor-specific command catalog
│   ├── commands_loader.py       # YAML loader for commands
│   └── parsers.yaml             # Parser registry config
├── inventory/
│   ├── inventory.csv            # Operator's inventory (gitignored)
│   ├── example_inventory.csv
│   └── loader.py                # Pure-function inventory helpers (legacy)
├── logging_config.py            # JSON / Colour formatters, redaction
├── request_logging.py           # Per-request middleware + CSP/HSTS/X-Frame headers
├── parsers/
│   └── engine.py                # ParserEngine class
├── parse_output.py              # Legacy parser dispatcher
├── repositories/                # Persistence façades
│   ├── credential_repository.py # encrypted SQLite + 0o600 chmod + secure_delete
│   ├── inventory_repository.py  # CSV file-backed + csv_path public property
│   ├── notepad_repository.py    # atomic update under lock
│   └── report_repository.py     # gzip JSON + pathlib path-traversal guard
├── runners/
│   ├── base_runner.py           # Abstract base
│   ├── arista_runner.py         # AristaEapiRunner
│   ├── cisco_runner.py          # CiscoNxapiRunner
│   ├── ssh_runner_class.py      # SshRunner
│   ├── factory.py          # RunnerFactory singleton cache (phase 6)
│   └── arista_eapi.py / cisco_nxapi.py / ssh_runner.py / runner.py  (legacy)
├── security/               # Phase 3
│   ├── encryption.py       # EncryptionService (Fernet + AES-128-CBC+HMAC fallback)
│   ├── sanitizer.py        # InputSanitizer (ip/host/cred/asn/prefix/string)
│   └── validator.py        # CommandValidator (show/dir prefix + blocklist)
├── services/                    # Use-case façades
│   ├── inventory_service.py     # CRUD + validate_device_row (mass-assign guard)
│   ├── notepad_service.py
│   ├── report_service.py        # + compare_runs(pre, post) (Phase 11)
│   ├── credential_service.py    # validates names via InputSanitizer
│   ├── device_service.py        # orchestrates cred → runner → parser
│   ├── transceiver_service.py   # 4-stage device pipeline (Phase 9)
│   └── run_state_store.py       # Thread-safe RLock + TTL + eviction (Phase 11)
├── utils/                       # Pure helpers (Phase 2 extraction)
│   ├── interface_status.py      # iface_status_lookup, merge_cisco_detailed_flap, traces
│   ├── transceiver_display.py   # errors_display, last_flap_display
│   ├── bgp_helpers.py           # wan_rtr_has_bgp_as
│   └── ping.py                  # single_ping + MAX_PING_DEVICES
└── credential_store.py / find_leaf.py / nat_lookup.py / ...  (legacy domain)

tests/                           # 840 tests across 47 files
├── conftest.py                  # Fixtures (instance dir isolation, mock CSV, factory client)
├── golden/                      # Phase 1 — characterisation snapshots
│   ├── _snapshot.py
│   ├── test_parsers_golden.py
│   ├── test_runners_baseline.py
│   ├── test_routes_baseline.py
│   └── test_inventory_baseline.py
├── test_config_classes.py / test_logging_config.py / test_request_logging.py
├── test_input_sanitizer.py / test_command_validator.py / test_encryption_service.py
├── test_app_factory.py
├── test_credential_repository.py / test_inventory_repository.py / ...
├── test_runner_classes.py / test_parser_engine.py / test_services.py
├── test_phase9_blueprints.py
├── test_security_phase13.py     # 33 phase-13 security regression tests
├── test_security_owasp.py       # 72 OWASP Top-10 tests
├── test_utils_phase2.py         # 30 helper extraction tests
├── test_inventory_writes_phase3.py     # 19 inventory CRUD tests
├── test_commands_bp_phase4.py          # 6 commands_bp tests
├── test_network_ops_bp_phase5.py       # 7 ping/SPA tests
├── test_credentials_bp_phase6.py       # 10 credential tests
├── test_bgp_bp_phase7.py               # 15 BGP tests
├── test_network_lookup_bp_phase8.py    # 10 find-leaf/nat tests
├── test_transceiver_bp_phase9.py       # 11 transceiver tests
├── test_device_commands_bp_phase10.py  # 13 device-commands tests
├── test_runs_reports_bp_phase11.py     # 20 runs/reports tests
├── test_security_audit_findings.py     # 25 audit batch 1+2 tests
├── test_security_audit_batch3.py       # 14 audit batch 3 tests
├── test_coverage_push.py               # 71 coverage-lift tests
├── test_legacy_coverage_bgp_lg.py      # 24 BGP-LG legacy tests
├── test_legacy_coverage_route_map.py   # 12 route-map legacy tests
├── test_legacy_coverage_find_leaf_nat.py  # 14 find-leaf + nat tests
├── test_legacy_coverage_parse_output.py   # 43 parse_output tests
├── test_legacy_coverage_runners.py     # 35 runner + ssh + loader tests
├── test_security_audit_batch4.py       # 24 audit-batch-4 security tests
└── test_runner_dispatch_coverage.py    # 13 runner.run_device_commands branches
```

**Total tests: 840**, all green. Lint clean on every blueprint, service,
util, factory, app.py, config, hardened runner, security module,
and request_logging. Audit batch 4 added 24 security-regression tests
(`tests/test_security_audit_batch4.py`) and 13 runner-dispatch coverage
tests (`tests/test_runner_dispatch_coverage.py`) — see
`patch_notes.md` "Audit batch 4" for the per-finding map.

---

## 2. Layered Object-Oriented Design

```
                ┌──────────────────────────────────────────────┐
                │   Flask Blueprints (per-domain)              │
                │   inventory_bp · notepad_bp · health_bp · …  │
                └──────────────────────────────────────────────┘
                                    │
                                    ▼
                ┌──────────────────────────────────────────────┐
                │   Service layer (use-case shaped)            │
                │   InventoryService · NotepadService ·        │
                │   ReportService · CredentialService ·        │
                │   DeviceService                              │
                └──────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
  │  Repositories    │   │  RunnerFactory   │   │  ParserEngine    │
  │  (persistence)   │   │  + concrete      │   │  (registry +     │
  │                  │   │  runners         │   │  delegate)       │
  └──────────────────┘   └──────────────────┘   └──────────────────┘
            │                       │                       │
            ▼                       ▼                       ▼
   SQLite / CSV / JSON     Arista eAPI / Cisco       backend/parse_output
   files (encrypted        NX-API / SSH               (legacy YAML +
   credentials, gzipped    transports                 custom parsers)
   reports, notepad)
```

**Cross-cutting concerns**
- **Config**: `BaseConfig`/`DevelopmentConfig`/`TestingConfig`/`ProductionConfig`
  in `backend/config/app_config.py`, selected via `CONFIG_MAP`.
  `ProductionConfig.validate()` rejects the default `SECRET_KEY`.
- **Logging**: `LoggingConfig.configure(app)` mounts JSON + Colour
  formatters with sensitive-key redaction (`password`, `api_key`,
  `token`, `cookie`, `authorization`, …).  `RequestLogger.init_app(app)`
  attaches a UUID4 `request_id`, X-Request-ID response header, and a
  slow-request WARN above `LOG_SLOW_MS`.
- **Security**: every public sanitiser returns `(bool, cleaned|reason)`.
  All commands sent to network devices must pass `CommandValidator`
  (read-only `show`/`dir` prefix + blocklist).  Encryption uses
  Fernet when `cryptography` is installed, else a pure-stdlib
  AES-128-CBC + HMAC-SHA256 backend.

---

## 3. App Factory

`backend/app_factory.py::create_app(config_name)` performs:

1. Resolve config class from `CONFIG_MAP` and call `validate()` (production
   refuses default `SECRET_KEY` and missing/weak `PERGEN_API_TOKEN(S)`).
2. Import the legacy `backend.app` module via `importlib` to grab the
   module-level `Flask` global. **The shim has zero `@app.route`
   handlers** since Phase 12 — this import only provides the `app`
   object plus the `_*` helper aliases that legacy in-tree callers
   still resolve through `backend.app`.
3. Apply the config values onto `app.config`.
4. `LoggingConfig.configure(app)` — JSON to stream, optional rotating file.
5. `RequestLogger.init_app(app)` — request id + slow-request WARN.
6. `_register_services(app)` — build and stash each service into
   `app.extensions` keyed by `inventory_service`, `notepad_service`,
   `report_service`, `credential_service`, `device_service`,
   `transceiver_service`, `run_state_store`.
7. `_register_blueprints(app)` — mount the 12 per-domain blueprints
   (`health_bp`, `inventory_bp`, `notepad_bp`, `commands_bp`,
   `network_ops_bp`, `credentials_bp`, `bgp_bp`, `network_lookup_bp`,
   `transceiver_bp`, `device_commands_bp`, `runs_bp`, `reports_bp`),
   idempotent across repeated `create_app` calls.
8. Re-init the legacy credential store (so `SECRET_KEY` changes
   propagate during tests).
9. Install the API-token gate (`_install_api_token_gate`) — fail-closed
   in production per audit C-1.
10. Stamp `CONFIG_NAME` on `app.config` and return.

After Phase 12 the factory is **the only supported entry point** —
the `backend/app.py` shim no longer carries routes, so booting
`FLASK_APP=backend.app` directly serves 404s. `run.sh` and the
operator docs (`README.md`, `HOWTOUSE.md`) point `FLASK_APP` at
`backend.app_factory:create_app`. Subsequent phases will continue to peel routes out into
blueprints incrementally.

---

## 4. Concurrency model

- **Runners** are stateless (credentials passed per call) and shared
  across threads via `RunnerFactory`'s threading-locked singleton cache.
- **Repositories** that touch shared mutable state (CSV, JSON, SQLite)
  guard writes with `threading.Lock()`.
- The legacy `backend/runners/runner.py` orchestrator continues to use
  a `ThreadPoolExecutor` capped at 12 workers / 200 devices.  The new
  `DeviceService.run` is synchronous per-device; the phase-10+
  blueprints will introduce concurrent fan-out via a thin executor
  helper that sits between the route and the service.

---

## 5. Test strategy

- **Golden / characterisation** (`tests/golden/`) — 107 tests that
  freeze the legacy HTTP, parser, runner and inventory contracts.  They
  are the safety net for every refactor commit.
- **Per-layer TDD** — each new layer has its own test module written
  *before* the implementation (phase 2 onwards).
- **Fixtures** — `conftest.py` provides `mock_inventory_csv` (two
  leaves in `FAB1/Mars/Hall-1`) and `isolated_instance_dir`
  (per-test temp directory pointed at by `PERGEN_INSTANCE_DIR`).  The
  `flask_app` fixture builds via `create_app("testing")` so blueprint
  wiring is exercised on every request.
- **No real network** — every runner test patches the underlying
  transport (`pyeapi`, `requests`, `paramiko`).

---

## 6. Outstanding items (post-phase-13 + audit batches)

- **Blueprint migration: COMPLETE.** All heavy device-execution routes
  (transceiver, find-leaf, nat, bgp, run/pre, run/post, custom-command,
  route-map, run/device, ping, parsers, commands, transceiver/recover,
  transceiver/clear-counters, arista/run-cmds, router-devices, reports
  list/get/delete, diff, credentials/<name>/validate, /api/health, /)
  now live in their per-domain blueprint under `backend/blueprints/`.
  `backend/app.py` is an 87-line shim with **zero `@app.route`
  handlers** kept only so in-tree code that imports `_*` helper
  aliases still resolves them.
- **Frontend / CSP**: inline `<script>` blocks were extracted to
  `backend/static/js/theme-init.js` + `backend/static/js/app.js`, and
  the JSZip CDN dependency was vendored to
  `backend/static/vendor/jszip.min.js`. The SPA now satisfies
  `Content-Security-Policy: script-src 'self'`.
- **Boot path**: `run.sh` defaults to
  `FLASK_APP=backend.app_factory:create_app` and prints the resolved
  `FLASK_APP` / `FLASK_CONFIG` / URL on startup. Booting
  `FLASK_APP=backend.app` directly will start Flask but serve 404 for
  every URL (the shim has no routes).
- Credential store migration (legacy Fernet blob → new
  `EncryptionService` AES-128-CBC + HMAC-SHA256) is staged but not
  cut over: blueprint registration uses a separate `credentials_v2.db`
  so the new and legacy stores can coexist.
- Phase 11 added OWASP Top-10 + business-logic security tests.
- Phase 12 published `TEST_RESULTS.md`, polished `README.md`, and
  pushed the new-OOD-layer coverage past 85 % (now 94 %).
- **Phase 13** completed (see §10).
- **Audit batches 1–3** remediated 24 findings (4 CRITICAL, 9 HIGH,
  11 MEDIUM) — see `README.md` audit table.

---

## 10. Security-by-design posture (post phase 13)

The phase-13 audit + remediation cycle locked the following controls
into the architecture.  Each item is testable from
`tests/test_security_phase13.py`.

| Control | Layer | Implementation | Audit ID |
|---------|-------|----------------|----------|
| Read-only command allowlist with NFKC normalisation, leading-whitespace strip, and embedded-newline rejection | Security | `backend/security/validator.py` | C-2, C-4, H-8, M-4, M-5 |
| IP sanitisation + per-request device cap before any `subprocess` invocation | Security + legacy route | `backend/security/sanitizer.py`, `backend/app.py::api_ping` | C-5 |
| Palo Alto API key transported via HTTP header, never URL parameter; debug responses scrub exception payloads | Network adapter | `backend/nat_lookup.py` | C-3 |
| XML parsed with `defusedxml` (Billion-Laughs / external-entity safe) | Network adapter | `backend/nat_lookup.py` | H-2 |
| Atomic repository writes via `threading.Lock` (TOCTOU safe) | Repository | `backend/repositories/notepad_repository.py` | H-1 |
| Path-traversal-safe report storage (sanitised id + `startswith(root + sep)` post-check) | Repository | `backend/repositories/report_repository.py` | py-HIGH |
| `:memory:` SQLite uses a persistent connection so schema and rows survive across calls | Repository | `backend/repositories/credential_repository.py` | py-HIGH |
| Crypto guards raise `ValueError` (not `assert`), so they survive `python -O` | Security | `backend/security/encryption.py::_key_expand_128` | py-HIGH |
| Defence-in-depth HTTP headers on every response | Middleware | `backend/request_logging.py::_log_request_end` | H-6 |
| `MAX_CONTENT_LENGTH=10 MiB` enforced by Flask before any route runs | Config | `backend/config/app_config.py` + `backend/app_factory.py` | M-8 |
| Per-route notepad size cap (512 KiB) returning `413` | Blueprint | `backend/blueprints/notepad_bp.py` | M-1 |
| Generic JSON error envelope — never `str(e)` | Blueprint | `backend/blueprints/notepad_bp.py` | H-5 |
| `_svc()` helpers raise `RuntimeError("not registered")` | Blueprint | `backend/blueprints/{inventory,notepad}_bp.py` | py-MED |
| Stable IP sort key (always 4-tuple) | Repository | `backend/repositories/inventory_repository.py::_ip_sort_key` | py-MED |

### 10.1. Batch-4 audit controls (post-Phase-13 sweep)

| Control | Layer | Implementation | Audit ID |
|---------|-------|----------------|----------|
| **Production fail-closed**: `create_app("production")` raises `RuntimeError` unless `PERGEN_API_TOKEN(S)` is set with ≥32-char tokens | App factory | `backend/app_factory.py::_install_api_token_gate` | C-1 |
| **Per-actor token routing**: `PERGEN_API_TOKENS=alice:tok,bob:tok` resolves to `flask.g.actor`; audit log lines record `actor=<name>` | App factory + blueprints | `backend/app_factory.py::_parse_actor_tokens`, `backend/blueprints/{credentials,transceiver}_bp.py` | C-2 |
| **Hard `cryptography` import**: legacy `credential_store` no longer falls back to base64; `ImportError` at module load on a corrupt venv | Crypto | `backend/credential_store.py` | C-3 |
| **Hard `defusedxml` import**: declared in `requirements.txt`; the silent `xml.etree` fallback is removed | XML adapter | `backend/nat_lookup.py` | H-1 |
| **Inventory binding** on every device-targeted route: caller-supplied `credential` / `vendor` / `model` are ignored; the inventory CSV row is the source of truth | Blueprints | `backend/blueprints/runs_bp.py`, `device_commands_bp.py`, `transceiver_bp.py` | H-2 / H-7 |
| **Sanitised credential names** in the legacy resolver: `_get_credentials` runs `InputSanitizer.sanitize_credential_name` before any DB call | Runner | `backend/runners/runner.py::_get_credentials` | H-3 |
| **Sanitised credential delete**: `CredentialService.delete` mirrors `set()` — CRLF / control-byte names cannot reach the audit log | Service | `backend/services/credential_service.py::delete` | H-4 |
| **Generic error envelopes** on `find-leaf`, `find-leaf-check-device`, `nat-lookup`, `route-map/run`: raw exception strings stay in server logs only | Blueprints | `backend/blueprints/network_lookup_bp.py`, `device_commands_bp.py` | H-5 / L-1 |
| **Destructive confirmation gate is always-on in production** (was opt-in via env in dev/test) | Blueprint | `backend/blueprints/transceiver_bp.py::_require_destructive_confirm` | C-1 / C-4 |
| **XPath-safe quote alternation** in PAN-OS rule lookup (XPath 1.0 has no escape; rules with both quote types are rejected) | XML adapter | `backend/nat_lookup.py` | py-H7 |
| **Narrowed exception handling** in eAPI / NX-API runners — only `RequestException` and `ValueError` are caught; programmer errors propagate | Runner | `backend/runners/{arista_eapi,cisco_nxapi}.py` | py-H3 |
