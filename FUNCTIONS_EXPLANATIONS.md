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
| `create_app(config_name="default") -> Flask` | App Factory entry point.  Resolves config class from `CONFIG_MAP`, validates it, imports the legacy `backend.app` module (registers global routes), applies config onto `app.config`, configures structured logging, mounts the request-id middleware, registers the OOD service layer into `app.extensions`, mounts per-domain blueprints, re-inits the legacy credential store.  Returns a fully configured `Flask` instance.  Security: `ProductionConfig.validate()` raises before any side effects on a misconfigured deploy. |
| `_register_services(app)` | Builds `InventoryService`, `NotepadService`, `ReportService`, `CredentialService`, `DeviceService` and stores each in `app.extensions[...]`.  Idempotent.  Inventory CSV path resolution mirrors the legacy `_inventory_path` helper.  Credentials use `credentials_v2.db` to avoid clashing with the legacy Fernet blob format. |
| `_register_blueprints(app)` | Mounts `health_bp`, `inventory_bp`, `notepad_bp`.  Skips any blueprint already present in `app.blueprints` (idempotent across multiple `create_app` calls). |
| `_apply_config(app, cfg)` | Mirrors the dataclass attributes of the chosen config class onto `app.config`. |

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

### `ReportRepository`
| Method | Description |
|--------|-------------|
| `__init__(reports_dir)` | Stores the dir + lock. |
| `list() -> list[dict]` | Reads the gzipped index file. |
| `load(run_id) -> dict | None` | Returns the gzipped JSON report. |
| `save(*, run_id, name, created_at, devices, device_results, post_*, comparison)` | Persists a fresh report + index entry. |
| `delete(run_id) -> bool` | Removes report + index entry. |

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

---

## 10. `backend/parsers/engine.py`

| Symbol | Description |
|--------|-------------|
| `ParserEngine(registry=None)` | Constructor accepts a dict of `{command_id: parser_config}` or builds an empty registry. |
| `ParserEngine.from_yaml(path)` | Loads the registry from a YAML file (dict-of-dicts shape). |
| `parse(command_id, raw) -> dict` | Looks up the parser config; delegates to `backend.parse_output.parse_output`.  Unknown command ids return `{}` instead of crashing. |
| `known_command_ids() -> list[str]` | Sorted list of registered ids — useful for `/api/commands`. |

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

### `network_ops_bp` (Phase 5 + audit H3)
- `POST /api/ping` — ICMP-probe up to 64 devices. **Audit H3**: rejects
  loopback / link-local / multicast / private / reserved targets unless
  `PERGEN_ALLOW_INTERNAL_PING=1`.
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

### `reports_bp` (Phase 11)
- `GET /api/reports`, `/api/reports/<run_id>` (with optional `?restore=1`),
  `DELETE /api/reports/<run_id>`.

---

## 13. Phase-13 changed-signature reference

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

### `backend/nat_lookup.py`

| Symbol | Before | After |
|--------|--------|-------|
| `import xml.etree.ElementTree as ET` | stdlib parser | `from defusedxml import ElementTree as ET` (stdlib fallback + `_DefusedXmlException` stub). |
| `_find_nat_rule_name_in_response`, `_find_translated_ips_in_rule_config` | `except _ETParseError` | `except (_ETParseError, _DefusedXmlException)` so XXE/Billion-Laughs payloads are swallowed and the regex fallback runs. |
| Outbound `requests.get(...)` for nat-policy-match and rule-config | passed `params={"key": api_key, …}` | passes `headers=api_headers` (with `X-PAN-KEY`) and **omits** `key` from `params`; debug error responses contain only `type(e).__name__`. |

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
