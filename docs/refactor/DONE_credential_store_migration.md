# DONE — Refactor Plan — Migrate `backend/credential_store.py` → `security/encryption.py` + `services/credential_service.py`

> **Status:** PLAN ONLY. No code changes. Awaiting review alongside 6 sibling plans. Executes after the `parse_output.py` refactor lands.
>
> **Owner:** TBD &nbsp;•&nbsp; **Estimated effort:** 1.5 – 2.5 dev-days &nbsp;•&nbsp; **Risk:** MEDIUM (data-bearing migration, multiple call sites)

---

## Requirements Restatement

1. **Eliminate** the legacy module-level helpers in `backend/credential_store.py` as a runtime dependency for application code.
2. **Route all** credential reads/writes through `CredentialService` → `CredentialRepository` → `EncryptionService` (which already exist).
3. **Round-trip every existing credential** from the legacy SQLite store (`instance/credentials.db`, single SHA-256 → Fernet) into the new store (`instance/credentials_v2.db`, PBKDF2-HMAC-SHA256 600k → Fernet) **without data loss** and **without operator intervention** beyond a single migration command.
4. **Provide rollback** if migration fails partway through (no half-migrated state, no destroyed legacy rows until cut-over is verified).
5. **Document key management** explicitly: where `SECRET_KEY` comes from today, what changes (nothing, by design), and what an operator must do on rotation.
6. **Preserve `/api/credentials/*` HTTP contract** byte-for-byte — no client change required.
7. **Keep the deprecation test** (`tests/test_security_legacy_credstore_deprecation.py`) flipping from `xfail` → `pass` as the proof the legacy module is correctly marked dead.

---

## Current State Analysis

### The split is already partially done

Despite the task framing ("migrate to a new split"), **`backend/security/encryption.py` and `backend/services/credential_service.py` already exist** and are wired through `app_factory._register_services`. The actual remaining work is a **read-path cut-over plus an operator data migration**, not a greenfield split.

| Layer | File | Status |
|---|---|---|
| Encryption primitive | `backend/security/encryption.py` (410 lines) | ✅ Built (PBKDF2 600k + Fernet/AES-CBC-HMAC) |
| Repository | `backend/repositories/credential_repository.py` (229 lines) | ✅ Built (writes `credentials_v2.db`) |
| Service façade | `backend/services/credential_service.py` (59 lines) | ✅ Built (sanitises name, delegates to repo) |
| DI wiring | `backend/app_factory.py:367-383` | ✅ Wired via `app.extensions["credential_service"]` |
| HTTP routes | `backend/blueprints/credentials_bp.py` | ✅ Already on `CredentialService` (CRUD + /validate) |
| Legacy module | `backend/credential_store.py` (142 lines) | ⚠️ Still imported by 6 files; backs `credentials.db` |
| Deprecation test | `tests/test_security_legacy_credstore_deprecation.py` | ⏳ `xfail`, waiting for migration to land |

### Two stores coexist (the real problem)

- **Legacy** `instance/credentials.db` — written/read by `backend.credential_store._fernet()` using `SHA256(SECRET_KEY) → Fernet key`. (`credential_store.py:35-47`)
- **New** `instance/credentials_v2.db` — written/read by `CredentialRepository` using `PBKDF2-HMAC-SHA256(SECRET_KEY, salt="pergen.security.encryption.v1", iters=600_000) → Fernet/AES key`. (`encryption.py:54-83`, `app_factory.py:367-383`)

The new store is intentionally a **separate file** (`app_factory.py:364-366` comment: *"isolated DB to avoid mismatches with the legacy `backend.credential_store` Fernet blob during the migration window"*). **Today, every credential exists only in the store the route happened to write it through.** Operators who have used both code paths have **bifurcated data**.

### Remaining legacy call sites (read paths)

| File | Lines | What it does |
|---|---|---|
| `backend/runners/runner.py:27-54` | `_get_credentials(name, secret_key, cred_store_module)` — accepts the legacy module as a positional arg, calls `cred_store_module.get_credential(...)`. |
| `backend/blueprints/runs_bp.py:30,96,119` | Imports `creds`, passes module to `run_device_commands`. |
| `backend/blueprints/device_commands_bp.py:22,85,185,256` | Same pattern; also calls `_get_credentials(..., creds)` directly. |
| `backend/blueprints/network_lookup_bp.py:25,61,118,176` | Same pattern. |
| `backend/blueprints/bgp_bp.py:26,164` | Same pattern. |
| `backend/blueprints/transceiver_bp.py:31,49,160,336` | Two direct `creds.get_credential(...)` calls + module passed to `TransceiverService`. |
| `backend/services/transceiver_service.py:46-48,68-72` | Holds `credential_store` as a constructor arg, forwards to runner. |
| `backend/blueprints/credentials_bp.py:153` | `/validate` endpoint imports legacy module purely to satisfy the runner's "creds module" contract. |
| `backend/app.py:27,75` | Top-level import + `creds.init_db(SECRET_KEY)` call (legacy entry-point shim). |
| `backend/app_factory.py:131-137` | Re-init `creds.init_db(...)` after config resolution. |

### Tests touching the legacy module

- `tests/test_security_legacy_credstore_deprecation.py` — `xfail`, will flip when migration lands.
- `tests/test_legacy_coverage_runners.py:321-` — exercises legacy paths (will need parametrisation across both modules during transition, then deletion of legacy half).
- `tests/test_security_audit_batch4.py:149-` — `test_credential_store_requires_cryptography_at_import_time` — must keep passing during transition; can be removed once module is deleted.
- `tests/test_credentials_bp_phase6.py`, `tests/test_credential_repository.py`, `tests/test_app_factory.py`, `tests/conftest.py:139`, `tests/golden/test_routes_baseline.py:294`, `tests/test_coverage_push.py`, `tests/test_security_audit_findings.py`, `tests/test_transceiver_bp_phase9.py` — reference the legacy module; will need audit + update.

### Schema (both stores are identical)

```sql
CREATE TABLE IF NOT EXISTS credentials (
    name       TEXT PRIMARY KEY,
    method     TEXT NOT NULL,           -- 'api_key' | 'basic'
    value_enc  TEXT NOT NULL,           -- ciphertext (base64-url)
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```
Same DDL in `credential_store.py:53-60` and `credential_repository.py:86-95`. **No schema changes needed** — only the *content* of `value_enc` differs (legacy SHA-256-Fernet vs new PBKDF2-Fernet).

---

## Target Architecture

```
┌───────────────────────── HTTP layer ─────────────────────────┐
│ credentials_bp │ runs_bp │ device_commands_bp │ network_… │ … │
└──────────────────────────┬───────────────────────────────────┘
                           │ all read/write paths
                           ▼
        ┌──────────────────────────────────────────┐
        │  CredentialService  (services/)          │  ← name sanitisation, audit
        └──────────────────────┬───────────────────┘
                               ▼
        ┌──────────────────────────────────────────┐
        │  CredentialRepository  (repositories/)   │  ← SQLite I/O, JSON marshal
        └──────────────────────┬───────────────────┘
                               ▼
        ┌──────────────────────────────────────────┐
        │  EncryptionService  (security/)          │  ← PBKDF2 600k + Fernet/AES-HMAC
        └──────────────────────────────────────────┘
                               ▼
                    instance/credentials_v2.db
                    (chmod 0o600, secure_delete=ON)
```

Runner contract change: `_get_credentials(name, secret_key, cred_store_module)` becomes `_get_credentials(name, credential_service)` — the runner stops caring about the encryption mechanism. `secret_key` is no longer threaded through the runner since the service was built from it at app-factory time.

After migration:
- `backend/credential_store.py` → **deleted** (or reduced to a 3-line `DeprecationWarning` shim if any out-of-tree consumer is suspected; see Phase 5 decision gate).
- `instance/credentials.db` → **archived** to `instance/credentials.legacy.bak` (kept for one release; deleted in the follow-up release).
- `instance/credentials_v2.db` → **renamed** to `instance/credentials.db` (canonical name reclaimed; see Phase 4).

---

## Migration Strategy

**Chosen:** **Versioned-file migration with verified cut-over** (NOT in-place, NOT dual-write).

| Option considered | Verdict |
|---|---|
| In-place re-encrypt (mutate rows in `credentials.db`) | ❌ Loses rollback. A crash mid-loop leaves a mixed-cipher file with no marker per row. |
| Dual-write (every set/delete hits both DBs) | ❌ Doubles the failure surface, requires temporary code in production, and we're not running both code paths in production today (new path is already canonical for HTTP CRUD). |
| **Versioned files + one-shot migrate command + verify + cut-over** | ✅ Atomic at the file level. Trivial rollback (point back at the old file). Already aligned with the existing `credentials.db` ↔ `credentials_v2.db` split. |

### Migration script: `scripts/migrate_credentials_v1_to_v2.py`

Pseudocode (not committed yet — Phase 3 deliverable):

```text
1. Resolve SECRET_KEY from env (same source the app uses).
2. Open legacy DB read-only via the legacy decryption helper
   (import backend.credential_store with deprecation suppressed).
3. Build EncryptionService.from_secret(SECRET_KEY).
4. Open or create credentials_v2.db via CredentialRepository.
5. For each row in legacy DB:
     - decrypt with legacy Fernet
     - re-encrypt with new EncryptionService
     - INSERT OR REPLACE into v2 DB
     - log {name, method, ok|error} (no payload)
6. Verify: SELECT COUNT(*) match, then for each name in v2:
     - service.get(name) returns the same {method, payload} as legacy.get_credential(name).
7. Atomically rename:
     credentials.db        -> credentials.legacy.bak
     credentials_v2.db     -> credentials.db
8. Update app_factory CREDENTIAL_DB_PATH default to "credentials.db"
   (this is a code change, not a runtime migration step).
9. Print summary: {migrated: N, failed: 0, backup: <path>}.
```

The script must be **idempotent**: re-running it on an already-migrated DB is a no-op (detect by checking that v2 already has all v1 names with matching method).

### Cut-over sequencing (per-call-site, smallest-blast-radius first)

1. `backend/runners/runner.py` — change `_get_credentials` signature to accept a `CredentialService` (or pass through `current_app.extensions["credential_service"]`). Provide a thin **adapter** (`_LegacyCredsModuleAdapter`) so existing call sites can be updated mechanically without changing test fixtures in the same PR.
2. `backend/blueprints/credentials_bp.py:153` — drop the legacy import, use the service for `/validate`.
3. `backend/blueprints/transceiver_bp.py:160,336` — replace `creds.get_credential(...)` with `current_app.extensions["credential_service"].get(...)`.
4. `backend/services/transceiver_service.py:46-48` — change constructor to accept `credential_service` instead of a `credential_store` module. Update `app_factory` wiring + 4 test files.
5. `backend/blueprints/runs_bp.py`, `device_commands_bp.py`, `network_lookup_bp.py`, `bgp_bp.py` — drop `from backend import credential_store as creds` import, update each `run_device_commands(d, secret_key, creds)` call to the new signature.
6. `backend/app.py:27,75` and `backend/app_factory.py:131-137` — drop the `creds.init_db(...)` calls (the repo creates its own schema in Phase 5).
7. `backend/credential_store.py` — replace contents with a `DeprecationWarning` shim that re-exports the legacy public API but raises on first attribute access. This flips `tests/test_security_legacy_credstore_deprecation.py` from `xfail` to `pass`.
8. After one release with the shim in place, **delete** `backend/credential_store.py` entirely.

---

## Rollback Plan

The migration must be reversible at every phase boundary.

| Failure point | Rollback action | Time to restore |
|---|---|---|
| Phase 1–2 (refactor only, no data touched) | `git revert <pr>`. No data risk. | minutes |
| Migration script crashes mid-loop | The script writes to `credentials_v2.db` (new file). Legacy `credentials.db` is untouched. Delete the partial v2 file and re-run after fixing the bug. | minutes |
| Verify step (step 6) fails for any row | Script aborts BEFORE the rename. Operator inspects logs (which row, what error), fixes (e.g. wrong `SECRET_KEY`), re-runs. | minutes |
| After file rename, app crashes on boot or loses creds at runtime | `mv instance/credentials.db instance/credentials_v2.db && mv instance/credentials.legacy.bak instance/credentials.db`. Revert the `CREDENTIAL_DB_PATH` default change in `app_factory`. Restart. | < 5 minutes |
| Several days post-migration: a credential is reported missing | The `credentials.legacy.bak` file is preserved for one full release cycle. Operator can `sqlite3 credentials.legacy.bak "SELECT name FROM credentials"` to confirm and re-create the credential through the UI. | hours |
| Deprecation shim (Phase 5) breaks an unknown out-of-tree caller | The shim raises `DeprecationWarning` on import but still functions. If an operator hits a hard `AttributeError`, `git revert` of the shim PR restores the full legacy module without touching data. | minutes |

**Hard rule:** the legacy `credentials.db` file is **renamed, not deleted**, by the migration script. Deletion happens in a follow-up cleanup PR after one full release (1–2 weeks of production soak).

---

## Encryption Key Management

### Today
- Source: `SECRET_KEY` env var → `BaseConfig.SECRET_KEY` (`config/app_config.py:114`) → passed to `EncryptionService.from_secret(...)` at app-factory time (`app_factory.py:380`).
- Default: `DEFAULT_SECRET_KEY` constant in `config/app_config.py` (intentional dev-only fallback; production config should reject empty/default — verified by `BaseConfig.validate()` hook at line 133).
- KDF: PBKDF2-HMAC-SHA256, 200k → 600k iterations (audit M-10), application-wide salt `b"pergen.security.encryption.v1"` (`encryption.py:54-55`). Per-record uniqueness comes from random IV (`encryption.py:301`).
- Storage: env var only. No KMS integration.

### Migration's effect on key management
**No change.** Both old and new schemes derive from the same `SECRET_KEY`. The migration script reuses the running app's `SECRET_KEY`. **If the operator does not know `SECRET_KEY`, they cannot migrate** — this is correct behaviour (they also could not have read the legacy DB).

### Operator runbook (to be added to `HOWTOUSE.md` in Phase 4)

```text
1. Confirm SECRET_KEY is set in your env (the same one the running app uses).
2. Stop the Pergen process (or put it in maintenance mode — no writes during migration).
3. Run:    python scripts/migrate_credentials_v1_to_v2.py
4. Verify the printed summary shows N migrated, 0 failed.
5. Restart Pergen.
6. Smoke test: GET /api/credentials → list matches what you had.
7. Smoke test: POST /api/credentials/<one>/validate → returns ok.
8. Keep instance/credentials.legacy.bak for at least one release.
```

### Key rotation (out of scope for this PR, but flagged as follow-up)
The current design has **no rotation primitive**. Rotating `SECRET_KEY` requires the same migrate-and-re-encrypt dance. A future PR should generalise the migration script into `scripts/rotate_credential_key.py` that takes `--old-key` and `--new-key` flags. **Not a blocker for this migration**, but logged in "Out of Scope" below.

### KMS integration (explicitly out of scope)
No KMS / Vault / AWS-Secrets-Manager work in this PR. The PBKDF2-from-env-secret model is the conscious choice for a self-hosted ops tool. A future RFC can layer KMS-backed `SECRET_KEY` resolution under `BaseConfig`, transparent to `EncryptionService`.

---

## Implementation Phases (TDD-first)

Each phase is a separate PR. Phases 1–3 are pure code refactor with no data-bearing changes; Phase 4 is the data migration; Phase 5 is deprecation; Phase 6 is deletion (separate release).

### Phase 1 — Runner contract change (no data touched)

| Step | TDD discipline | Files |
|---|---|---|
| 1.1 Write failing test: `runner.run_device_commands(device, credential_service)` resolves `(username, password)` for a credential present in the in-memory `CredentialService`. | RED | new `tests/test_runner_credential_service.py` |
| 1.2 Add `_get_credentials_via_service(name, credential_service)` alongside the existing `_get_credentials(name, secret_key, cred_store_module)`. Old function untouched. | GREEN | `backend/runners/runner.py` |
| 1.3 Add `run_device_commands_v2(device, credential_service, …)` that calls 1.2. Old function untouched (delegates internally if you prefer). | GREEN | `backend/runners/runner.py` |
| 1.4 Test for parity: same device dict produces identical output through old and new functions when both stores hold the same credential. | GREEN | `tests/test_runner_credential_service.py` |
| 1.5 Refactor: extract shared `InputSanitizer` + dispatch logic so old and new functions share one body. | REFACTOR | `backend/runners/runner.py` |

**Risk:** LOW. Pure additive change. No call site moved yet. Coverage on the new path must hit 80%+.

### Phase 2 — Cut over read-path call sites to `CredentialService`

| Step | TDD discipline | Files |
|---|---|---|
| 2.1 Write integration test: `POST /api/credentials/<name>/validate` works with **only** the new store populated (legacy DB empty). Currently `xfail`-able if the route still hard-imports the legacy module. | RED | `tests/test_credentials_bp_phase6.py` (extend) |
| 2.2 Update `credentials_bp.py:153` `/validate` to pass the service to `run_device_commands_v2` instead of the legacy module. | GREEN | `backend/blueprints/credentials_bp.py` |
| 2.3 Repeat for each of the 4 other blueprints (`runs_bp`, `device_commands_bp`, `network_lookup_bp`, `bgp_bp`) — write a "no legacy import" test per blueprint, then delete the import + update each call site. | RED → GREEN per file | 4 blueprint files + 4 test files |
| 2.4 Update `TransceiverService` constructor: accept `credential_service` instead of `credential_store` module. Update `app_factory.py` wiring. Update **all 7 test files** that construct `TransceiverService(secret_key="x", credential_store=...)`. | GREEN | `services/transceiver_service.py`, `app_factory.py`, 7 test files |
| 2.5 Update `transceiver_bp.py:160,336` direct `creds.get_credential(...)` calls to `current_app.extensions["credential_service"].get(...)`. | GREEN | `backend/blueprints/transceiver_bp.py` |
| 2.6 Grep verify: `grep -r "from backend import credential_store" backend/` returns **only** `backend/app.py`, `backend/app_factory.py` (the bootstrap shims, removed in Phase 4). | REFACTOR / verify | repo-wide |

**Risk:** MEDIUM. Touches 5 blueprints + 1 service + ~10 test files. Mitigation: one PR per blueprint; the shared adapter from Phase 1.3 means each PR is small.

### Phase 3 — Migration script + tests (no data touched yet)

| Step | TDD discipline | Files |
|---|---|---|
| 3.1 Write failing test: given a temp legacy DB with 3 credentials (1 api_key, 2 basic), running `migrate_credentials_v1_to_v2(secret_key, src, dst)` produces a v2 DB whose `CredentialService.get(name)` returns identical payloads. | RED | new `tests/test_credential_migration.py` |
| 3.2 Implement the migration as a **library function** in `backend/repositories/credential_migration.py` (testable in-process, no subprocess). | GREEN | new `backend/repositories/credential_migration.py` |
| 3.3 Write the CLI wrapper `scripts/migrate_credentials_v1_to_v2.py` that resolves `SECRET_KEY` from env and shells out to the library function. | GREEN | new `scripts/migrate_credentials_v1_to_v2.py` |
| 3.4 Test idempotency: running migrate twice in a row produces the same v2 contents on the second run as on the first. | RED → GREEN | `tests/test_credential_migration.py` |
| 3.5 Test rollback: simulate a decrypt failure on row 2 of 3; assert the function raises BEFORE the file rename and the legacy DB is untouched. | RED → GREEN | `tests/test_credential_migration.py` |
| 3.6 Test "wrong SECRET_KEY" path: assert a clear error message, no partial v2 DB written. | RED → GREEN | `tests/test_credential_migration.py` |
| 3.7 Coverage target on `credential_migration.py`: **95%+** (data-bearing code, deserves higher bar than 80%). | REFACTOR / verify | — |

**Risk:** MEDIUM. The script is the most security-sensitive code in this refactor. Mitigation: very high test coverage, dry-run flag (`--dry-run` prints the plan without writing), `--verbose` logs each row's `(name, method, ok)` tuple to stderr.

### Phase 4 — Production migration (operator runs the script once)

This phase is **operational, not code-shipping**. The PR for this phase ships:
- `HOWTOUSE.md` runbook section.
- `Makefile` target `make migrate-credentials` (wraps `scripts/migrate_credentials_v1_to_v2.py`).
- A change to `app_factory.py:368-369` and `config/app_config.py:117-119` so the **default** `CREDENTIAL_DB_PATH` becomes `credentials.db` (not `credentials_v2.db`). Operators who already set `PERGEN_CREDENTIAL_DB` are unaffected.
- Removal of `backend/app.py:27,75` and `backend/app_factory.py:131-137` legacy `creds.init_db(...)` calls.

| Step | Verification |
|---|---|
| 4.1 Operator stops Pergen. | `ps` confirms no process. |
| 4.2 Operator runs `make migrate-credentials`. | Script prints `migrated: N, failed: 0, backup: instance/credentials.legacy.bak`. |
| 4.3 Operator restarts Pergen. | App boots; `/api/health` 200. |
| 4.4 Operator hits `GET /api/credentials`. | Response matches pre-migration list. |
| 4.5 Operator runs `/validate` on one credential. | Returns `ok: true` with uptime. |

**Risk:** MEDIUM. Real data movement. Mitigation: `instance/credentials.legacy.bak` retained for one release; rollback steps documented above.

### Phase 5 — Deprecate the legacy module

| Step | TDD discipline | Files |
|---|---|---|
| 5.1 Replace `backend/credential_store.py` body with a `DeprecationWarning`-emitting shim that re-exports the legacy public API names (`init_db`, `get_credential`, `list_credentials`, `set_credential`, `delete_credential`) but raises `RuntimeError("backend.credential_store is removed; use backend.services.credential_service.CredentialService")` if any function is actually called. | GREEN | `backend/credential_store.py` |
| 5.2 Set `__deprecated__ = True` on the module so the existing `tests/test_security_legacy_credstore_deprecation.py` flips from `xfail` → `pass`. | GREEN | `backend/credential_store.py` + remove `xfail` marker. |
| 5.3 Audit `tests/test_legacy_coverage_runners.py:321-` and `tests/test_security_audit_batch4.py:149-`: either delete (they covered the legacy implementation that no longer exists) or rewrite to assert the shim's deprecation behaviour. | RED → GREEN | both test files |
| 5.4 Update `tests/conftest.py:139` and `tests/test_app_factory.py:39` to drop the legacy module from the `sys.modules` reset list. | GREEN | both test files |

**Risk:** LOW. Pure cleanup; the data is already in the new store as of Phase 4.

### Phase 6 — Delete legacy module + legacy DB file (separate release)

Ship one release after Phase 5. If no out-of-tree consumers have complained:

| Step | Files |
|---|---|
| 6.1 `git rm backend/credential_store.py`. |
| 6.2 Delete `tests/test_security_legacy_credstore_deprecation.py` (it asserts a module that no longer exists). |
| 6.3 Operator deletes `instance/credentials.legacy.bak` (documented in release notes). |
| 6.4 Update `ARCHITECTURE.md`, `comparison_from_original.md`, `HOWTOUSE.md`, `README.md`, `FUNCTIONS_EXPLANATIONS.md`, `patch_notes.md` to remove the "legacy module still present" wording. |

**Risk:** LOW.

---

## Dependencies

### Hard prerequisites (must merge first)
1. **`parse_output.py` refactor** (per task framing — this plan executes after that lands).

### No external library changes
- `cryptography` is already a hard dependency (audit C-3).
- No new packages needed.

### Cross-plan coordination
- If any of the 6 sibling plans touch `backend/runners/runner.py`, `backend/services/transceiver_service.py`, or any of the 5 blueprints listed above, **this plan must rebase last** to absorb their changes. Coordinator should sequence accordingly.

---

## Risks

### HIGH
- **Operator runs the migration script with the wrong `SECRET_KEY`.** Result: every decrypt fails, script aborts in Phase 6 of its loop, no v2 DB written, no harm — but the operator is now confused. **Mitigation:** the script's first action is to decrypt one canary row and surface a clear error: `"decryption failed — is SECRET_KEY the same as the running app?"`.
- **Operator forgets to stop the app, runs migration, then writes new credentials through the running app — to which DB?** During migration the app is still pointing at `credentials.db` (legacy). After rename, the app points at the new DB (which now lives at `credentials.db`). A write between migrate-end and app-restart could land in the renamed file at a stale path. **Mitigation:** runbook explicitly says stop the app first; script refuses to run if it can detect a live Pergen process listening on the configured port (best-effort check; not a hard guarantee).

### MEDIUM
- **`TransceiverService` constructor change is breaking.** 7 test files instantiate `TransceiverService(secret_key="x", credential_store=...)`. **Mitigation:** Phase 2.4 updates them all in one PR; CI catches anything missed.
- **Hidden caller out-of-tree.** Someone may have written a script that imports `backend.credential_store` directly. **Mitigation:** Phase 5 ships a deprecation shim (one release of grace), not a direct delete.
- **Migration script run twice (operator panic).** **Mitigation:** explicit idempotency test (Phase 3.4); script detects already-migrated DB and exits with `migrated: 0 (already up to date)`.
- **`credentials.legacy.bak` accidentally checked into git or copied to a less-secure location.** **Mitigation:** the script chmods the backup to `0o600` immediately after rename; runbook reminds operators it contains encrypted credentials.

### LOW
- **The new store already exists with conflicting names.** Today the new HTTP routes write to `credentials_v2.db`, so it's plausible an operator has different credential sets in each store. **Mitigation:** migration script uses `INSERT OR REPLACE` and logs every overwrite with `WARN: name=<X> existed in v2 with different method/ciphertext; legacy version wins`. Operator decides post-hoc.
- **Tests that import the legacy module break across phases.** **Mitigation:** Phase 5 audits `tests/conftest.py:139` and 9 referenced test files in one sweep.
- **Race against concurrent migration plans for the parse_output refactor.** **Mitigation:** sequence dependency above.

---

## Estimated Complexity

| Phase | Files touched | LoC delta | Test LoC added | Effort |
|---|---|---|---|---|
| 1 — Runner contract | 1 src + 1 test | +60 / 0 | ~120 | 0.5 day |
| 2 — Cut-over call sites | 6 src + ~7 tests | +40 / -25 | ~150 | 0.5 day |
| 3 — Migration script | 2 src + 1 test | +180 / 0 | ~250 | 0.5 day |
| 4 — Operational + bootstrap cleanup | 3 src + 1 doc | +20 / -30 | ~30 | 0.25 day (incl. operator coordination) |
| 5 — Deprecation shim | 1 src + 4 tests | +30 / -130 | ~40 | 0.25 day |
| 6 — Delete (next release) | 1 src + 6 docs | 0 / -160 | 0 / -40 | 0.25 day |
| **Total** | **~14 src + ~13 tests** | **net ≈ +50 LoC** | **~590** | **~2.25 dev-days** |

Coverage requirement: 80% baseline; 95% on `credential_migration.py` (data-bearing).

---

## Out of Scope

These are explicitly **not** part of this refactor and should be filed as separate follow-ups if desired:

1. **`SECRET_KEY` rotation primitive.** Generalising the migration script to `--old-key`/`--new-key` is a follow-up. Today, rotation requires manual re-creation of every credential.
2. **KMS / Vault / AWS-Secrets-Manager integration** for `SECRET_KEY` resolution.
3. **Per-credential salts** (the current PBKDF2 salt is application-wide; per-record uniqueness comes from the IV — see `encryption.py:32-34`). Adding per-credential KDF salts would require a v3 schema and is out of scope.
4. **Argon2id migration** (the current KDF is PBKDF2-HMAC-SHA256). Defensible per OWASP; upgrading to Argon2id is a separate RFC.
5. **Multi-tenant credential isolation** (today, all credentials live in one DB keyed only by name). No tenancy model exists in Pergen.
6. **Audit log for credential reads** (today only writes are audit-logged at `credentials_bp.py:93,109`). Read-side audit is a separate ask.
7. **Hardware-backed key storage** (TPM/Secure Enclave) — not relevant for a server-side ops tool.

---

## Acceptance Criteria

- [ ] `grep -r "from backend import credential_store" backend/` returns 0 lines (after Phase 5).
- [ ] `tests/test_security_legacy_credstore_deprecation.py` passes without `xfail` (after Phase 5).
- [ ] All existing Pergen tests pass with ≥ 80% coverage; `credential_migration.py` ≥ 95%.
- [ ] `make migrate-credentials` is idempotent on an already-migrated store.
- [ ] Operator runbook section in `HOWTOUSE.md` is reviewed by at least one operator.
- [ ] One full release cycle (1–2 weeks) elapses between Phase 5 (deprecation shim) and Phase 6 (deletion).
- [ ] `instance/credentials.legacy.bak` file is preserved through the deprecation window.

---

## Wave-7 update: v2 fall-through bridge landed (2026-04-23)

The wave-6 `scripts/migrate_credentials_v1_to_v2.py` operator CLI is the
canonical data-move mechanism described above. **Wave-7 added an
in-process safety net** so that an operator who has not yet run the
migration script (or who has a fresh install with no legacy DB at all)
does not see broken device-exec routes:

### What landed

`backend/credential_store.py:111-168` gained two helpers:

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

`get_credential()` now calls `_read_from_v2(name, secret_key)` when the
legacy DB has no row — instead of returning `None` immediately.

### Why this matters for the migration plan

The migration plan above (Phases 1–6) cuts the **read path** over to
`CredentialService` step by step (Phase 2). Without the wave-7 bridge,
that cut-over **must** ship in lockstep with the migration script run,
or the fresh-install operator gets a broken device-exec path during the
window between "I added a credential through the new HTTP CRUD" and
"the operator pointed me at the v2 DB via Phase 4's `CREDENTIAL_DB_PATH`
default change".

With the wave-7 bridge in place, that lockstep constraint is **removed**.
The migration phases can now ship independently:

- **Phase 1** (runner contract change) — independent.
- **Phase 2** (cut-over read-path call sites) — independent. The legacy
  `get_credential()` is no longer the only read path; new code can
  bypass it entirely.
- **Phase 3** (migration script + tests) — **shipped in wave-6** as
  `scripts/migrate_credentials_v1_to_v2.py` and
  `backend/repositories/credential_migration.py` (97 % covered).
- **Phase 4** (operator runs the script + bootstrap cleanup) — operator-led,
  unchanged. The bridge means an operator who delays Phase 4 indefinitely
  still has a working app.
- **Phase 5** (deprecate the legacy module) — can ship independently;
  the bridge will be removed at the same time as the legacy module
  body, since the bridge is itself inside `credential_store.py`.
- **Phase 6** (delete legacy module + legacy DB file) — unchanged.

### What did NOT change

- The migration script remains the canonical operator action. The bridge
  is a safety net, not a replacement; it does **not** re-encrypt rows
  with the stronger PBKDF2 KDF, it just reads from whichever store has
  the row.
- The deprecation timeline (Phase 5 ships one release after Phase 4) is
  unchanged. Operators still need to run the migration before the
  legacy module's body is deleted.
- The acceptance criteria above are unchanged. The bridge is added
  alongside the migration plan, not as a substitute for it.

### Tests

The bridge is pinned by `tests/test_security_credential_v2_fallthrough.py`
(6 tests):

- v2-only credential read returns the payload (no legacy DB present).
- Legacy-only credential read still works (no v2 DB present).
- Both stores present, legacy-DB hit takes precedence (operator's
  manual `sqlite3` is the source of truth).
- Both stores present, v2-only credential found via fall-through.
- Wrong `secret_key` → bridge swallows the decrypt failure → returns None.
- v2 DB missing → bridge returns None without raising.

### Cross-reference

- Wave-7 audit: `docs/security/DONE_audit_2026-04-23-wave7.md` §4.1 (C-1 / H-4 fix).
- Wave-7 Python review: `docs/code-review/DONE_python_review_2026-04-23-wave7.md` §4.1.
- Wave-6 Phase E (migration script): `patch_notes.md` v0.7.0.

— end of update —
