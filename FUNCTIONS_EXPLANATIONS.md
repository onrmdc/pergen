# Pergen — Functions & Classes Reference

Auto-style dictionary of every class and function introduced or
re-shaped during the OOD/TDD refactor (phases 0–9).  Legacy modules
that have not yet been migrated keep their existing inline docstrings.

> **Format**: per-module section with one bullet per public symbol —
> inputs, outputs, side effects, security notes.  Private helpers
> (leading underscore) are documented only when they are non-trivial.

---

## 1. `backend/app_factory.py`

| Symbol | Description |
|--------|-------------|
| `create_app(config_name="default") -> Flask` | App Factory entry point. Resolves config class from `CONFIG_MAP`, validates it, imports the legacy `backend.app` module to grab the module-level `Flask` global (the shim no longer registers routes — every route is mounted by `_register_blueprints` below), applies config onto `app.config`, configures structured logging, mounts the request-id middleware, registers the OOD service layer into `app.extensions`, mounts the 12 per-domain blueprints, re-inits the legacy credential store, installs the API-token gate. Returns a fully configured `Flask` instance. Security: `ProductionConfig.validate()` and the API-token gate raise before any side effects on a misconfigured deploy. **Wave-7 (2026-04-23):** also (a) optionally mounts `werkzeug.middleware.proxy_fix.ProxyFix` when `PERGEN_TRUST_PROXY=1` (closes login-throttle bypass behind a reverse proxy — audit H-1); (b) sets `PERMANENT_SESSION_LIFETIME` from `PERGEN_SESSION_LIFETIME_HOURS` (default 8h, was Flask's 31-day default) and `PERGEN_SESSION_IDLE_HOURS` from the matching env var (default = lifetime) — both written onto `app.config` for the cookie-auth idle-timeout enforcement (audit H-2). |
| `_register_services(app)` | Builds `InventoryService`, `NotepadService`, `ReportService`, `CredentialService`, `DeviceService`, `TransceiverService`, `RunStateStore` and stores each in `app.extensions[...]`. Idempotent. Inventory CSV path resolution mirrors the legacy `_inventory_path` helper. Credentials use `credentials_v2.db` to avoid clashing with the legacy Fernet blob format. |
| `_register_blueprints(app)` | Mounts the 12 per-domain blueprints: `health_bp`, `inventory_bp`, `notepad_bp`, `commands_bp`, `network_ops_bp`, `credentials_bp`, `bgp_bp`, `network_lookup_bp`, `transceiver_bp`, `device_commands_bp`, `runs_bp`, `reports_bp`. Wave-6 added `auth_bp` as an optional 13th blueprint when cookie auth is enabled. Skips any blueprint already present in `app.blueprints` (idempotent across multiple `create_app` calls). |
| `_apply_config(app, cfg)` | Mirrors the dataclass attributes of the chosen config class onto `app.config`. |
| `_enforce_api_token(...)` (cookie-auth branch — wave-7 H-2) | Idle-timeout enforcement. Stamped on every request that carries a `pergen_session` cookie: if `now - session["iat"] > PERGEN_SESSION_IDLE_HOURS * 3600`, the session is cleared, treated as anonymous, and the next response surfaces a 401. Audit line emitted before clearing: `audit auth.session.expired actor=<name> ip=<ip> age_s=<seconds>`. The check is a no-op for the legacy `X-API-Token` header path. |

---

## 2. `backend/config/app_config.py`

| Symbol | Description |
|--------|-------------|
| `BaseConfig` | Dataclass holding the canonical defaults (`SECRET_KEY`, `DEBUG`, `LOG_LEVEL`, `LOG_FORMAT`, `LOG_FILE`, `LOG_SLOW_MS`, `INVENTORY_PATH`, `INSTANCE_DIR`, `CREDENTIAL_DB_PATH`, `START_SCHEDULER`).  `validate()` is a no-op. |
| `DevelopmentConfig` | Inherits `BaseConfig`, sets `DEBUG=True`, `LOG_LEVEL=DEBUG`, `LOG_FORMAT=colour`. |
| `TestingConfig` | Inherits `BaseConfig`, sets `TESTING=True`, in-memory-friendly defaults, `START_SCHEDULER=False`. |
| `ProductionConfig` | Inherits `BaseConfig`, sets `DEBUG=False`, `LOG_FORMAT=json`.  `validate()` raises `RuntimeError` if `SECRET_KEY` is the default placeholder. |
| `CONFIG_MAP` | Dict mapping `"development" / "testing" / "production" / "default"` to the right class.  Unknown names fall back to `default` (= `DevelopmentConfig`). |

---

## 3. `backend/logging_config.py`

| Symbol | Description |
|--------|-------------|
| `LoggingConfig.configure(app)` | Configures the root logger from `app.config`.  Mounts a `JsonFormatter` (production) or `ColourFormatter` (dev) on a stream handler; optionally adds a `RotatingFileHandler` (10 MB × 5) when `LOG_FILE` is set.  Permissions on the log file are tightened to `0o600` (best-effort, suppressed via `contextlib.suppress(OSError)` for cross-platform safety). |
| `JsonFormatter` | One JSON object per line, with sensitive-key redaction over `_SENSITIVE_KEYS = {password, passwd, secret, token, api_key, apikey, authorization, cookie, credential}`. |
| `ColourFormatter` | ANSI-coloured human-friendly stream output for development. |
| `redact_extras(extras: dict)` | Returns a copy of `extras` with sensitive values replaced by `"***REDACTED***"`. |

---

## 4. `backend/request_logging.py`

| Symbol | Description |
|--------|-------------|
| `RequestLogger.init_app(app)` | Registers `before_request` / `after_request` hooks.  `before_request` stamps `g.request_id = uuid4().hex`, records `g.start_time`, logs `→ METHOD /path [rid=... ip=...]`.  `after_request` adds `X-Request-ID`, logs `← STATUS duration_ms` and WARNs above `LOG_SLOW_MS`.  The class also exposes a module-level guard so re-initialising the same app is a safe no-op. |
| `audit_log(event, actor, detail="", severity="info")` | Logs to a dedicated `app.audit` logger.  Designed to be persisted to a DB model in a later phase. |
| `log_call(logger, level=logging.DEBUG)` | Decorator that logs function entry (sanitised kwargs), exit, exceptions.  Sensitive kwargs are redacted via `redact_extras`. |
| `timed(logger, threshold_ms=500)` | Decorator that measures wall-clock time; DEBUG below threshold, WARNING above. |

---

## 5. `backend/security/sanitizer.py`

`InputSanitizer` returns `(bool, cleaned|reason)` for every input
type.  All regex patterns are class-level (compiled once, ReDoS-safe).
Null bytes (`\x00`) are rejected in every method with a WARN log.

| Method | Validation |
|--------|-----------|
| `sanitize_ip(value)` | Regex + per-octet 0-255 + max 15 chars. |
| `sanitize_hostname(value)` | Alphanumeric start/end, `-_.` allowed, max 253 chars. |
| `sanitize_credential_name(value)` | Alphanumeric + limited specials, max 64 chars. |
| `sanitize_asn(value)` | Optional `AS` prefix, range 1-4294967295. |
| `sanitize_prefix(value)` | `A.B.C.D/N`, valid octets, `0 ≤ N ≤ 32`. |
| `sanitize_string(value, max_len)` | Length check + null-byte rejection. |

---

## 6. `backend/security/validator.py`

| Symbol | Description |
|--------|-------------|
| `CommandValidator.validate(cmd: str) -> tuple[bool, str]` | Type-checks `cmd` is `str`; rejects > 512 chars; requires `^show ` or `^dir ` prefix (case-insensitive); rejects strings containing `conf t`, `configure terminal`, `\| write`, `write mem`, `copy run start`, `; `, `&&`, `\|\|`, backticks or `$(`.  Returns `(True, "")` on pass, `(False, reason)` on reject; logs WARNING on every rejection. |

---

## 7. `backend/security/encryption.py`

| Symbol | Description |
|--------|-------------|
| `EncryptionService.from_secret(secret: str)` | Factory that derives the symmetric key via PBKDF2-HMAC-SHA256 (200 000 iters, fixed app salt) and returns the wrapper around the best available backend.  Raises `ValueError` on empty secret, `ImportError` if no backend can be loaded.  No insecure base64 fallback. |
| `EncryptionService.encrypt(plaintext: str) -> str` | Authenticated encryption.  Returns a URL-safe blob. |
| `EncryptionService.decrypt(token: str) -> str` | Authenticated decryption; raises `EncryptionError` on tamper / wrong key with a generic message (no internals leaked). |
| `_FernetBackend` | Preferred backend when `cryptography` is installed (Fernet = AES-128-CBC + HMAC-SHA256 internally). |
| `AesCbcHmacBackend` | Pure-stdlib (`hmac`, `hashlib`, `secrets`) authenticated AES-128-CBC fallback.  Encrypt-then-MAC.  Per-record random IV.  Constant-time HMAC compare on decrypt. |

---

## 7a. `backend/credential_store.py` (legacy module + wave-7 v2 fall-through bridge)

The legacy credential store. Marked deprecated in wave-3 Phase 6 but
still imported by 6 callers (5 blueprints + `runner.py`). Rather than
ship a breaking signature change to all 6 consumers, wave-7 added a
small fall-through bridge inside this module so the legacy `get_credential()`
public API can transparently serve credentials written via the new
`CredentialService` HTTP CRUD.

| Symbol | Description |
|--------|-------------|
| `init_db(secret_key)` | Idempotent legacy schema creation in `instance/credentials.db`. Chmodded to `0o600` on POSIX (audit M-6). |
| `set_credential(name, method, secret_key, *, api_key=None, username=None, password=None)` | Legacy write — encrypts via SHA-256 → Fernet (no PBKDF2). Used today only by operators who hand-edit through the legacy module's API. New writes go through `CredentialService`. |
| `get_credential(name, secret_key) -> dict | None` | Legacy read. **Wave-7:** when the legacy DB has no row, falls through to `_read_from_v2(name, secret_key)` before declaring "not found". This closes the fresh-install device-exec break (audit C-1 / H-4). |
| `list_credentials(secret_key) -> list[dict]` | Legacy list (name + method only, no payload). Does NOT fall through to v2 — list operations stay legacy-only because the new HTTP CRUD has its own list at `GET /api/credentials` via `CredentialService`. |
| `delete_credential(name, secret_key) -> bool` | Legacy delete. Does NOT fall through. Delete is destructive; the legacy and v2 stores are independent for delete operations. Operator who needs to delete a v2 credential should use `DELETE /api/credentials/<name>` (which goes through `CredentialService`). |
| **`_v2_db_path() -> str` (NEW wave-7)** | Computes the absolute path to `instance/credentials_v2.db` from this module's own `__file__`. Note: does NOT honour `PERGEN_INSTANCE_DIR` — that's a tracked LOW finding for the day an operator sets a non-default instance path (wave-7 review LOW-5). |
| **`_read_from_v2(name, secret_key) -> dict | None` (NEW wave-7)** | Best-effort read from the v2 store. Imports `CredentialRepository` and `EncryptionService.from_secret(...)` lazily (no module-load cost for legacy-only deployments). Returns `None` if the v2 DB doesn't exist OR the row is missing OR the decrypt fails (`SECRET_KEY` mismatch / corruption). Failures are swallowed by design — the legacy code path stays at-least-as-functional as before the bridge. Audit citation in the docstring: "Audit (Python review C-1 / Security audit H-4)". |

### Wave-7 read-path data flow

```
                    legacy callers (5 blueprints + runner.py + find_leaf + nat_lookup)
                                              │
                                              ▼
                              credential_store.get_credential()
                                              │
                              ┌───────────────┴───────────────┐
                              ▼                               ▼
                    instance/credentials.db          row missing → _read_from_v2()
                    (legacy SHA-256 → Fernet)        instance/credentials_v2.db
                                                     (PBKDF2 600k → AES-CBC+HMAC)
```

The bridge is **a transition aid, not a replacement** for the migration
script (`scripts/migrate_credentials_v1_to_v2.py`, wave-6 Phase E). The
script remains the canonical operator action when the legacy DB has data
that needs the stronger PBKDF2 KDF. See
`docs/refactor/DONE_credential_store_migration.md` "Wave-7 update" for
the complete plan.

---

## 8. `backend/repositories/`

### `CredentialRepository`
| Method | Description |
|--------|-------------|
| `__init__(db_path, encryption: EncryptionService)` | Stores DB path + encryption instance, creates a `threading.Lock`. |
| `create_schema()` | Idempotent `CREATE TABLE IF NOT EXISTS credentials(...)`. |
| `list() -> list[dict]` | Returns `[{name, method, updated_at}, …]` (no payload). |
| `get(name) -> dict | None` | Returns `{name, method, **decrypted_payload}`. |
| `set(name, *, method, api_key=None, username=None, password=None)` | Insert / replace.  `method` whitelist `{basic, api_key}`.  Empty name rejected.  Payload is JSON-serialised then encrypted. |
| `delete(name) -> bool` | Returns `True` iff a row was deleted. |

### `InventoryRepository`
| Method | Description |
|--------|-------------|
| `__init__(csv_path)` | Stores the CSV path.  No file IO until `load`/`save`. |
| `load() -> list[dict]` | Reads the CSV, normalises sites/roles, sorts by IP, lowercases keys. |
| `save(devices)` | Writes back using the canonical 10-column header. |
| `fabrics(devices=None) -> list[str]` | Distinct fabrics. |
| `sites(fabric, devices=None)` / `halls(fabric, site, devices=None)` / `roles(fabric, site, hall=None, devices=None)` | Hierarchy filters. |
| `devices(fabric, site, role=None, hall=None, devices=None)` | Filtered + IP-sorted device list. |
| `devices_by_tag(tag, devices=None)` | Tag lookup. |

### `NotepadRepository`
| Method | Description |
|--------|-------------|
| `__init__(notepad_dir)` | Stores the dir + lock. |
| `load() -> dict` | Returns `{content, line_editors}`.  Falls back to legacy `notepad.txt` if `notepad.json` is missing. |
| `save(content, line_editors)` | Persists LF-normalised content + per-line editors. |
| `update(content, user) -> dict` | Diff-aware update — preserves the editor for unchanged lines, attributes new/changed lines to `user` (defaults to `"—"` when blank). |

### `ReportRepository` (wave-5 W4-M-01: actor scoping)
| Method | Description |
|--------|-------------|
| `__init__(reports_dir)` | Stores the dir + lock. |
| `list(actor=None) -> list[dict]` | Reads the gzipped index file. When `actor` is supplied, projects out cross-actor entries (legacy entries pre-W4-M-01 are visible to every actor for back-compat). |
| `load(run_id, actor=None) -> dict | None` | Returns the gzipped JSON report. When `actor` is supplied, refuses cross-actor reads (returns None — IDOR mismatch treated as "not found"). |
| `save(*, run_id, name, created_at, devices, device_results, post_*, comparison, created_by_actor=None)` | Persists a fresh report + index entry. `created_by_actor` (defaulting to `"anonymous"`) is recorded in BOTH the gzipped payload and the index entry. |
| `delete(run_id, actor=None) -> bool` | Removes report + index entry. When `actor` is supplied, cross-actor delete is a silent no-op (no-disclosure). |

---

## 9. `backend/runners/`

### `BaseRunner` (ABC)
- `run_commands(ip, username, password, commands, timeout=30) -> tuple[list, str|None]` — returns `(results, error)`.
- `run_single(ip, username, password, command, timeout=30) -> tuple[Any, str|None]` — convenience wrapper.

### Concrete runners
- `AristaEapiRunner` — wraps the legacy `backend/runners/arista_eapi.py` JSON-RPC client.
- `CiscoNxapiRunner` — wraps the legacy `backend/runners/cisco_nxapi.py` REST client.
- `SshRunner` — wraps the legacy `backend/runners/ssh_runner.py` paramiko client.

All runners are stateless; credentials and timeouts are passed per call.

### `RunnerFactory`
- `get_runner(*, vendor, model, method) -> BaseRunner` — thread-safe singleton cache keyed by the `(vendor, model, method)` tuple.  Raises `ValueError` for unsupported combinations.

### Wave-7 SSH runner hardening (audit Python-review C-4 / C-5)

`backend/runners/ssh_runner.py` (the legacy paramiko module wrapped by
`SshRunner`) gained two correctness fixes:

| Symbol | Description |
|--------|-------------|
| `_classify_ssh_error(exc) -> str` (NEW wave-7) | Maps a paramiko / network exception to a controlled vocabulary: `auth_failed`, `network`, `timeout`, `banner_mismatch`, `other`. The original `repr(exc)` is logged server-side via `_log.warning(...)` for triage; the returned string is bucket-name only — paramiko exception strings can carry the supplied username (always) and sometimes a password tail (server bouncing an auth attempt with an unusual error code), and pre-wave-7 those would have leaked back to the operator via the JSON envelope. |
| `run_command(...)` (modified wave-7) | Now wraps the full session in `try/finally: client.close()` so the SSH client is always closed on the exception path (FD-leak fix — C-5). Exception text is bucketed through `_classify_ssh_error()` (C-4) instead of returned as `str(exc)`. |
| `run_config_lines_pty(...)` (modified wave-7) | Same pattern as `run_command`. The interactive PTY config-push helper is the highest-blast-radius leak surface because authentication failures during config push happen mid-session, and pre-wave-7 the paramiko exception string was returned verbatim. |

Pinned by `tests/test_security_ssh_runner_close_on_exception.py` (8 tests).

---

## 10. `backend/parsers/` package

The 1,552-line `backend/parse_output.py` god module was split into a 31-module
package in audit-wave-2 (see `docs/refactor/DONE_parse_output_split.md`). The
legacy file is now a 151-line back-compat shim that re-exports every symbol
from its new home.

### `backend/parsers/dispatcher.py` (NEW in wave-2)

| Symbol | Description |
|--------|-------------|
| `Dispatcher(registry=None, field_engine=None)` | Constructor; defaults pull the 16-entry `_DEFAULT_REGISTRY` mapping `custom_parser` strings → vendor parser callables. |
| `Dispatcher.parse(command_id, raw, parser_config) -> dict` | Routes to the registered vendor callable, or to `GenericFieldEngine` for the field-config branch, or returns `{}` for `parser_config is None`. |
| `Dispatcher.has(name)` / `Dispatcher.custom_parsers()` | Introspection helpers. |

### `backend/parsers/engine.py`

| Symbol | Description |
|--------|-------------|
| `ParserEngine(registry=None)` | Constructor accepts a dict of `{command_id: parser_config}` or builds an empty registry. |
| `ParserEngine.from_yaml(path)` | Loads the registry from a YAML file (dict-of-dicts shape). |
| `parse(command_id, raw) -> dict` | Looks up the parser config; delegates to the lazy trampoline `_legacy_parse_output` which forwards to `Dispatcher().parse(...)`. Unknown command ids return `{}` instead of crashing. |
| `known_command_ids() -> list[str]` | Sorted list of registered ids — useful for `/api/commands`. |

### `backend/parsers/common/*.py`

Pure-utility modules shared across vendor parsers. Each is tested in
`tests/parsers/common/`.

| Module | Helpers |
|--------|---------|
| `json_path.py` | `_get_path`, `_flatten_nested_list`, `_find_key`, `_find_key_containing`, `_find_list`, `_get_val` |
| `counters.py` | `_count_from_json`, `_count_where`, `_get_from_dict_by_key_prefix` |
| `regex_helpers.py` | `_extract_regex`, `_count_regex_lines` |
| `formatting.py` | `_apply_value_subtract_and_suffix`, `_format_power_two_decimals` |
| `duration.py` | `_parse_relative_seconds_ago`, `_parse_hhmmss_to_seconds` |
| `arista_envelope.py` | `_arista_result_obj`, `_arista_result_to_dict` |

### `backend/parsers/arista/*.py` and `backend/parsers/cisco_nxos/*.py`

One module per logical parser, named after the operation (uptime, cpu,
disk, power, transceiver, interface_status, interface_description,
isis, arp, bgp for Arista; system_uptime, power, transceiver,
interface_status, interface_detailed, interface_mtu, interface_description,
isis_brief, arp, arp_suppression for Cisco NX-OS). Each is unit-tested
in the matching `tests/parsers/<vendor>/test_<name>.py` (16 files,
196 tests, lifted parser surface coverage from 67 → 87 %).

### `backend/parsers/generic/field_engine.py`

`GenericFieldEngine.apply(raw_output, parser_config) -> dict` — extracted
from the legacy `else` branch of `parse_output()`. Handles `json_path`
(with optional `count`/`count_where`/`key_prefix`+`value_key`), `regex`
(with optional `count`), and the `format_template` second pass. Tested
in `tests/parsers/generic/test_field_engine.py`.

---

## 11. `backend/services/`

### `InventoryService` (read + write)
- `csv_path` property — public read-only path to the underlying CSV
  (audit H1; replaces `svc._repo._csv_path` reach-arounds).
- `all() / fabrics() / sites(fabric) / halls(fabric, site) / roles(fabric, site, hall=None)` — filtered listings.
- `devices(*, fabric, site, role=None, hall=None) / devices_by_tag(tag)` — device lookups.
- `save(devices)` — full-CSV rewrite via the repository.
- `normalise_device_row(d)` — coerce raw request body into one canonical row.
- **Audit H4** `validate_device_row(d) -> (row, error_or_None)` — `InputSanitizer`
  per field + mass-assignment guard against unknown top-level keys.
- `add_device(payload) / update_device(payload) / delete_device(hostname=, ip=) /
  import_devices(rows)` — write-side use cases (return tuples consumed by `inventory_bp`).

### `NotepadService`
- `get() -> dict` — passthrough to `repo.load()`.
- `update(content, user) -> dict` — passthrough to `repo.update()`.

### `ReportService`
- `list() / load(run_id) / save(...) / delete(run_id)` — passthrough to the repository.
- **Phase 11** `compare_runs(pre_results, post_results) -> list[dict]` — per-key
  diff used by `runs_bp.api_run_post` and `api_run_post_complete` (was
  duplicated inline in app.py).

### `CredentialService`
- `list() / get(name) / delete(name)` — passthrough.
- `set(name, *, method, api_key=None, username=None, password=None)` — runs `InputSanitizer.sanitize_credential_name(name)` first; raises `ValueError` on rejection.
- **Audit C3** — wired into `credentials_bp` CRUD; encryption is
  `EncryptionService` (AES-128-CBC + HMAC-SHA256 + PBKDF2 ≥ 600k).

### `DeviceService`
- `__init__(credential_service, runner_factory, parser_engine)` — explicit DI.
- `run(device, *, method, commands, timeout=30) -> dict` — resolves the credential, picks the right runner, executes, parses each command's output through `ParserEngine`, returns `{hostname, ip, vendor, credential, error, commands: [{command_id, command, raw, parsed}, …]}`.  Credential payloads never appear in the result.

### `TransceiverService` (Phase 9)
- `__init__(secret_key, credential_store)` — used by `transceiver_bp`.
- `collect_rows(devices) -> (rows, errors, trace)` — runs the 4-stage
  pipeline per device (transceiver / status / description / Cisco MTU /
  Cisco-detailed flap merge) and merges into output rows.
- **Audit C1** — `_collect_status` returns `(status_map, raw_result)`
  tuple; no hidden `_last_status_result` instance attribute. Service
  is reentrant + safe to cache.

### `RunStateStore` (Phase 11)
- `get(run_id) / set(run_id, value) / update(run_id, **fields) / delete(run_id) / __contains__ / __len__`.
- `RunStateStore(ttl_seconds=3600, max_entries=1024)` — defaults give the
  historical zero-config behaviour usable.
- **Audit H6** — `threading.RLock` guards every operation; `get` / `update`
  return deep copies (no reference leaks); FIFO eviction when over `max_entries`;
  lazy TTL expiry on access.

---

## 12. `backend/blueprints/` (12 blueprints, post-decomposition)

### `health_bp`
- `GET /api/v2/health` — richer liveness probe (config name + request id + UTC timestamp).
- `GET /api/health` — legacy v1 liveness probe (Phase 12 moved here from `app.py`).

### `inventory_bp` (read + write)
- **Read** `GET /api/fabrics`, `/api/sites`, `/api/halls`, `/api/roles`,
  `/api/devices`, `/api/devices-arista`, `/api/devices-by-tag`,
  `/api/inventory` — pure pass-through to `InventoryService`.
- **Write (Phase 3)** `POST/PUT/DELETE /api/inventory/device`,
  `POST /api/inventory/import` — delegate to `InventoryService.add_device` /
  `update_device` / `delete_device` / `import_devices`. All inputs flow
  through `validate_device_row()` (mass-assignment guard + per-field sanitization).

### `notepad_bp` (phase 9, hardened phase 13)
- `GET /api/notepad` and `PUT/POST /api/notepad` — passthrough to
  `NotepadService.get/update`.  PUT without `content` returns 400.
- **Phase 13:** `_MAX_NOTEPAD_BYTES = 512_000` cap on PUT (`413` on
  overflow); narrow `except (OSError, ValueError)` returns a generic
  `{"error": "internal error"}` 500 envelope; `_svc()` raises
  `RuntimeError("notepad_service not registered")` instead of `KeyError`.

### `commands_bp` (Phase 4)
- `GET /api/commands`, `/api/parsers/fields`, `/api/parsers/<command_id>` —
  pure pass-through to `backend.config.commands_loader`.

### `network_ops_bp` (Phase 5 + audit H3 + wave-7.1 posture)
- `POST /api/ping` — ICMP-probe up to 64 devices.
  **Wave-7.1 (2026-04-23) posture change**: internal targets
  (RFC1918 / loopback / link-local / multicast / reserved) are now
  ALLOWED by default. Pergen is operated against the operator's own
  management network, so the original audit-H3 default-deny was
  making the tool unusable for its intended use case. Set
  `PERGEN_BLOCK_INTERNAL_PING=1` to re-enable the SSRF guard for an
  internet-exposed deployment; legacy `PERGEN_ALLOW_INTERNAL_PING=1`
  is a backward-compat no-op (allow is now the default). Implemented
  in `_ssrf_guard_enabled()`; the original `_is_internal_address()`
  classifier is unchanged.
- `GET /` — SPA fallback (serves `index.html` if present, else JSON sentinel).

### `credentials_bp` (Phase 6 + audit C3)
- `GET / POST /api/credentials`, `DELETE /api/credentials/<name>`,
  `POST /api/credentials/<name>/validate`. CRUD goes through
  `CredentialService`; `/validate` still uses the legacy `creds`
  adapter for the runner shim.

### `bgp_bp` (Phase 7)
- 7 pass-through routes for RIPEStat / RPKI / PeeringDB queries.
- `GET /api/bgp/wan-rtr-match` — orchestrated per-vendor runner dispatch
  loop using `wan_rtr_has_bgp_as` from `backend/utils/bgp_helpers.py`.

### `network_lookup_bp` (Phase 8)
- `POST /api/find-leaf`, `/api/find-leaf-check-device`, `/api/nat-lookup` —
  thin pass-through to `backend.find_leaf` and `backend.nat_lookup`.
- Inventory CSV path resolved via `InventoryService.csv_path`.

### `transceiver_bp` (Phase 9 + audit H7 + C4)
- `POST /api/transceiver` — delegates to `TransceiverService.collect_rows`.
- `POST /api/transceiver/recover` and `clear-counters` — **audit H7**:
  device + credential resolved from inventory (caller-supplied
  `credential` field is ignored). **Audit C4**: requires
  `X-Confirm-Destructive: yes` when `PERGEN_REQUIRE_DESTRUCTIVE_CONFIRM=1`.
  **A09**: emits `app.audit` log records on success.

### `device_commands_bp` (Phase 10 + audit M11)
- `POST /api/arista/run-cmds`, `GET /api/router-devices`,
  `POST /api/route-map/run`, `POST /api/custom-command`.
- **Audit M11**: non-`enable` dict cmds in Arista runCmds only forward
  `{cmd}`; `input` and other keys are stripped.

### `runs_bp` (Phase 11)
- 8 routes: `/api/run/device`, `/api/run/pre`, `/api/run/pre/create`,
  `/api/run/pre/restore`, `/api/run/post`, `/api/run/post/complete`,
  `/api/diff`, `/api/run/result/<run_id>`.
- Diff computation unified via `ReportService.compare_runs`.
- `/api/diff` capped at 256 KB per side (audit M4).

### `reports_bp` (Phase 11 + wave-3 M-03 + wave-5 W4-M-01)
- `GET /api/reports` — list saved reports. Wave-5: projects out cross-actor
  entries via `_scoping_actor()`.
- `GET /api/reports/<run_id>` — fetch one (legacy `?restore=1` returns 405;
  use POST `/restore` instead). Wave-5: cross-actor reads return 404.
- `POST /api/reports/<run_id>/restore` — wave-3 M-03 endpoint that pushes
  the saved report back into the in-memory run-state store. Wave-5:
  cross-actor restores return 404.
- `DELETE /api/reports/<run_id>` — wave-5: cross-actor deletes are silent
  no-ops (no-disclosure); audit log line emitted on every call.

---

## 13. `backend/cli/` (operator tools)

### `backend/cli/backfill_report_actors.py` (wave-5 W4-M-01)
- One-shot operator CLI to stamp legacy reports under `instance/reports/`
  with the wave-5 `created_by_actor` field. Idempotent (already-stamped
  reports are skipped). Supports `--owner=<name>`, `--reports-dir=<path>`,
  and `--dry-run`. Default owner is `"legacy"`.
- Invocation: `python -m backend.cli.backfill_report_actors`.
- Unit tested at `tests/test_cli_backfill_report_actors.py` (8 tests).

---

## 14. Phase-13 changed-signature reference

Every change below is a security or robustness fix.  No public API
removed; existing callers continue to work.

### `backend/security/validator.py`

| Symbol | Before | After |
|--------|--------|-------|
| `CommandValidator.validate(command) -> (bool, reason)` | matched `^(show\|dir)\s*` directly on input | NFKC-normalises and `strip()`s input; `_PREFIX_RE = ^(show\|dir)\s+`; rejects embedded `\n`/`\r`; otherwise unchanged behaviour. |

### `backend/security/encryption.py`

| Symbol | Before | After |
|--------|--------|-------|
| `_key_expand_128(key: bytes) -> bytes` | `assert len(key) == 16` (stripped under `python -O`) | `if len(key) != 16: raise ValueError("AES-128 key must be exactly 16 bytes")` |

### `backend/repositories/credential_repository.py`

| Symbol | Before | After |
|--------|--------|-------|
| `CredentialRepository.__init__` | no shared connection field | adds `self._mem_conn: sqlite3.Connection \| None = None` |
| `CredentialRepository._connect()` | `sqlite3.connect(self._db_path)` always | for `:memory:`, lazily creates and reuses `self._mem_conn` so schema and rows survive between calls; file paths still get a per-call connection. |

### `backend/repositories/report_repository.py`

| Symbol | Before | After |
|--------|--------|-------|
| `_safe_id(run_id) -> str` | replaced separators only | additionally strips NUL bytes (`\x00`) and leading dots so `..` cannot crawl out via os.path.join. |
| `_report_path(run_id) -> str` | bare `os.path.join(self._reports_dir, …)` | resolves the absolute path and asserts `abs_path.startswith(abs_root + os.sep)` (raises `ValueError` if escape attempted). |

### `backend/repositories/notepad_repository.py`

| Symbol | Before | After |
|--------|--------|-------|
| `save(state)` | wrote directly | extracted body into private `_save_unlocked(state)`; `save` now wraps that in `with self._lock`. |
| `update(content, user)` | load → diff → save (3 calls, race possible) | entire load → diff → save sequence runs inside `with self._lock`, so concurrent writers cannot corrupt `line_editors`. |

### `backend/repositories/inventory_repository.py`

| Symbol | Before | After |
|--------|--------|-------|
| `_ip_sort_key(row) -> tuple[int, …]` | returned variable-length tuple for malformed IPs | always returns a 4-tuple; non-4-octet IPs sort to `(999, 999, 999, 999)`. |

### `backend/blueprints/inventory_bp.py` and `backend/blueprints/notepad_bp.py`

| Symbol | Before | After |
|--------|--------|-------|
| `_svc()` | `current_app.extensions["…"]` (raises `KeyError` if missing) | typed return (`-> "InventoryService"` / `-> "NotepadService"`), `TYPE_CHECKING`-guarded import, raises `RuntimeError("… not registered")` on miss. |

### `backend/blueprints/notepad_bp.py`

| Symbol | Before | After |
|--------|--------|-------|
| `api_notepad_put()` | unbounded `content` length, `except Exception` | enforces `_MAX_NOTEPAD_BYTES = 512_000` (`413` on overflow); narrow `except (OSError, ValueError)`; returns generic `{"error": "internal error"}`. |

### `backend/runners/runner.py`

| Symbol | Before | After |
|--------|--------|-------|
| `run_device_commands(...)` (SSH branch) | called `ssh_runner.run_command` directly | runs `cmd` through `CommandValidator.validate` first; rejected commands record `entry["error"] = "rejected by CommandValidator: …"` and never reach the transport layer. |

### `backend/nat_lookup/` (wave-3 Phase 8 — split from monolith)

The 341-LOC `backend/nat_lookup.py` was split into a 6-file package
following the parse_output playbook. All callers continue to use the
existing `from backend import nat_lookup` shape — `__init__.py` is
the back-compat shim.

| Module | Role |
|--------|------|
| `nat_lookup/__init__.py` | back-compat shim re-exporting public + private symbols + holds the literal `from defusedxml import ElementTree as ET` line for `inspect.getsource(...)` security tests |
| `nat_lookup/ip_helpers.py` | `_IPV4_RE`, `_is_valid_ip` |
| `nat_lookup/xml_helpers.py` | `_format_first_nat_rule_response`, `_find_nat_rule_name_in_response`, `_format_translated_address_response` (legacy-preserved L-09 escape chain), `_find_translated_ips_in_rule_config` |
| `nat_lookup/palo_alto/api.py` | `build_nat_policy_match_cmd`, `build_rule_config_xpath` (H7 quote-style alternation), `call_nat_policy_match`, `call_nat_rule_config` (X-PAN-KEY header, A02) |
| `nat_lookup/service.py` | `nat_lookup` orchestrator + `_resolve_fabric_site` + `_try_one_firewall` helpers |

**Wave-2 audit hardening preserved verbatim:**
| Symbol | Hardening |
|--------|-----------|
| `import xml.etree.ElementTree as ET` | replaced by `from defusedxml import ElementTree as ET` (stdlib fallback + `_DefusedXmlException` stub) |
| `_find_nat_rule_name_in_response`, `_find_translated_ips_in_rule_config` | `except (_ETParseError, _DefusedXmlException)` swallows XXE/Billion-Laughs payloads; regex fallback runs |
| Outbound `requests.get(...)` for nat-policy-match and rule-config | passes `headers={"X-PAN-KEY": api_key}` (audit A02); error envelopes contain only `type(e).__name__` |

### `backend/find_leaf/` (wave-3 Phase 8)

Split from a 325-LOC monolith. Per-vendor strategies replace the
inlined Arista/Cisco branches.

| Module | Role |
|--------|------|
| `find_leaf/__init__.py` | back-compat shim + vendor-dispatch for `_query_one_leaf_search` / `_complete_find_leaf_from_hit` |
| `find_leaf/ip_helpers.py` | `_IPV4_RE`, `_is_valid_ip`, `_leaf_ip_from_remote` |
| `find_leaf/strategies/arista.py` | `_query_arista_leaf_search` (BGP-EVPN mac-ip lookup) + `_complete_arista_hit` (ARP follow-up on the resolved leaf) |
| `find_leaf/strategies/cisco.py` | `_query_cisco_leaf_search` (ARP-suppression-cache lookup) + `_complete_cisco_hit` |
| `find_leaf/service.py` | `find_leaf` and `find_leaf_check_device` orchestration; preserves the parallel ThreadPoolExecutor first-hit-wins behaviour verbatim (audit M-09 deferred) |

### `backend/bgp_looking_glass/` (wave-3 Phase 8)

Split from a 447-LOC monolith. RIPEStat / RPKI / PeeringDB calls land
in dedicated submodules.

| Module | Role |
|--------|------|
| `bgp_looking_glass/__init__.py` | back-compat shim; re-exports `requests` for tests that patch `backend.bgp_looking_glass.requests.get` |
| `bgp_looking_glass/normalize.py` | pure `normalize_resource` — prefix/AS validator |
| `bgp_looking_glass/http_client.py` | `_get_json` with audit M-01 (`allow_redirects=False`) and W4-M-05 (opaque redirect-error envelope) |
| `bgp_looking_glass/ripestat.py` | RIPEStat fetch+parse helpers (status/RPKI/history/visibility/LG/bgplay/AS-overview/announced-prefixes) |
| `bgp_looking_glass/peeringdb.py` | PeeringDB AS-name lookup |
| `bgp_looking_glass/service.py` | 7 public `get_bgp_*` orchestrators |

### `backend/route_map_analysis/` (wave-3 Phase 8)

Split from a 232-LOC monolith into a 3-file package.

| Module | Role |
|--------|------|
| `route_map_analysis/__init__.py` | back-compat shim |
| `route_map_analysis/parser.py` | Arista `show running-config | json` parser (`analyze_router_config` + `_extract_*` helpers) |
| `route_map_analysis/comparator.py` | cross-device unified BGP table builder (`build_unified_bgp_full_table` + `_device_order_key`) |

### `backend/app.py` (legacy routes hardened)

| Symbol | Change | Audit ID |
|--------|--------|----------|
| `api_arista_run_cmds` | every command (string or `{"cmd": "..."}` form) goes through `CommandValidator.validate` before being sent to the runner. | C-2 |
| `api_custom_command` | replaced the local `_READONLY_BLOCKLIST` helper with `CommandValidator.validate(command)`. | C-4 |
| `api_ping` | adds `_MAX_PING_DEVICES = 64` cap (returns 400 above) and runs every device IP through `InputSanitizer.sanitize_ip` before calling `_single_ping`. | C-5 |

### `backend/request_logging.py`

| Symbol | Change |
|--------|--------|
| `_log_request_end(response)` | sets `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: geolocation=(), microphone=(), camera=()` (all via `setdefault`, so per-route overrides still win). |

### `backend/config/app_config.py` + `backend/app_factory.py`

| Symbol | Change |
|--------|--------|
| `BaseConfig.MAX_CONTENT_LENGTH` | new field, default `10 * 1024 * 1024`, overridable via env `MAX_CONTENT_LENGTH`. |
| `_apply_config(app, cfg)` | propagates `MAX_CONTENT_LENGTH` onto `app.config` so Flask rejects oversized request bodies before any blueprint runs. |
