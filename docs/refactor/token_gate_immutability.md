# Refactor Plan: Token-Gate Immutability

> **Status:** Planning only. No code changes in this document.
> **Owner:** TBD
> **Audit reference:** `patch_notes.md:1431` — *"Token-gate immutability (re-read `PERGEN_API_TOKEN(S)` on every request)"*
> **Related test (xfail today):** `tests/test_security_token_gate_immutable.py`
> **Related code:** `backend/app_factory.py:163-266` (`_install_api_token_gate`)

---

## Requirements Restatement

Pergen's API authentication gate currently re-reads `PERGEN_API_TOKEN` and `PERGEN_API_TOKENS` from `os.environ` (and `app.config`) on **every request** via the closure `_resolve_tokens()` (`backend/app_factory.py:202-217`). The audit recommends:

1. **Resolve tokens once at `create_app()` time**, then bind the resolved set into the app as an immutable snapshot.
2. **Per-request handler must consult only that snapshot** — never `os.environ`, never live `app.config`.
3. The snapshot must be **frozen** (immutable / read-only) so a misbehaving extension or middleware cannot widen access at runtime.
4. **Token comparison stays constant-time** (`hmac.compare_digest`) — this is already correct and must not regress.
5. **Rotation requires an explicit, observable action** (process restart or a documented admin reload), never an implicit env edit picked up silently by the next request.

### Why this matters (threat model)

- **Timing surface (small but real):** every request performs an `os.environ.get()` + `dict.get()` lookup before the constant-time compare. Differences in env-dict bucket placement, GC behaviour, or interpreter state can leak nanosecond-scale signal that aggregates over many probes.
- **Runtime tamper window:** any code path holding a reference to `os.environ` (a 3rd-party lib, a test helper, a future feature) can mutate the gate's effective config mid-process without restart and without leaving an audit trail.
- **Init-system race:** if a supervisor scrubs/rewrites env between `create_app()` and the first request (e.g., `systemd EnvironmentFile=` reload), the gate silently switches behaviour mid-flight.
- **Operator surprise:** the current behaviour means `unset PERGEN_API_TOKEN; kill -HUP` *can* downgrade a running worker to OPEN without a deploy. This is documented nowhere and contradicts the C-1 fail-closed posture.

---

## Current State Analysis

### Token-gate implementation

| File | Lines | Concern |
| --- | --- | --- |
| `backend/app_factory.py` | `163-266` | `_install_api_token_gate(app)` — installs `before_request` hook |
| `backend/app_factory.py` | `202-217` | `_resolve_tokens()` closure — **re-reads `os.environ` + `app.config` on every call** |
| `backend/app_factory.py` | `219-235` | Production fail-closed validation — calls `_resolve_tokens()` once at boot already (good) |
| `backend/app_factory.py` | `237-264` | `@app.before_request _enforce_api_token` — calls `_resolve_tokens()` every request (bad) |
| `backend/app_factory.py` | `258-260` | Constant-time compare via `hmac.compare_digest` — **already correct** |
| `backend/app_factory.py` | `143-160` | `_parse_actor_tokens(raw)` — pure, side-effect-free parser; reusable as-is |
| `backend/app_factory.py` | `58` | `_MIN_API_TOKEN_LENGTH = 32` — single source of truth for the floor |

### Call sites that read `PERGEN_API_TOKEN(S)` from env at runtime

After `grep -n PERGEN_API_TOKEN backend/`:

- `backend/app_factory.py:204-205` — `os.environ.get("PERGEN_API_TOKENS")`
- `backend/app_factory.py:211` — `os.environ.get("PERGEN_API_TOKEN")`
- `backend/app_factory.py:206, 212` — `app.config.get(...)` fallback for both

**No other module reads these env vars.** Refactor scope is contained to `app_factory.py`.

### Token comparison policy (today)

Already constant-time. `backend/app_factory.py:258-260`:

```text
for actor, token in tokens.items():
    if hmac.compare_digest(supplied, token):
        matched_actor = matched_actor or actor
```

**Note the existing intentional design:** the loop continues even after a match so the timing leaks only the *count* of configured actors, not *which one* matched. This invariant must be preserved by the refactor.

### Test coverage today

| Test file | Lines | What it asserts |
| --- | --- | --- |
| `tests/test_security_token_gate_immutable.py` | full file (74 lines), `xfail` | Env-scrub-after-boot must NOT downgrade gate. **This is the test we are graduating from xfail → green.** |
| `tests/test_security_token_gate_parsing.py` | full file | `_parse_actor_tokens` syntactic invariants |
| `tests/test_security_audit_batch3.py:20-51` | C-1 unit tests | Sets `flask_app.config["PERGEN_API_TOKEN"] = "..."` *after* `create_app()` and expects the gate to honour it. **THIS IS A BREAKING-CHANGE HOTSPOT — see Risks.** |
| `tests/test_security_audit_batch4.py:51-97` | C-1 fail-closed | Subprocess tests that `create_app("production")` raises when env is unset/short. Already snapshots at boot. Unaffected. |
| `tests/test_security_audit_batch4.py:106-142` | C-2 actor routing | Sets `flask_app.config["PERGEN_API_TOKENS"] = "..."` *after* `create_app()`. **Same hotspot.** |
| `tests/test_security_health_disclosure.py:51` | sets `PERGEN_API_TOKEN` env then calls `create_app` | Already env-at-boot. Unaffected. |
| `tests/conftest.py:96-146` | `flask_app` fixture | Calls `create_app("testing")`. Tests then mutate `flask_app.config[...]` to enable the gate. |

The `flask_app` fixture build-then-mutate pattern is the **single biggest constraint** on the refactor design: a naive "snapshot at boot, ignore everything else" implementation would break ~6 existing tests. The fix needs an explicit, narrow re-snapshot API.

---

## Target Architecture

### Snapshot data structure

A frozen, immutable snapshot bound to the app at `create_app()` time:

```text
TokenGateSnapshot:
    actors:        Mapping[str, str]   # frozen / read-only mapping {actor: token}
    min_length:    int                  # captured _MIN_API_TOKEN_LENGTH at boot
    config_name:   str                  # "production" | "testing" | ...
    snapshot_at:   datetime             # for /api/_admin observability + audit logs
    source_summary: str                 # e.g. "env:PERGEN_API_TOKENS,actors=2" — never logs values
```

**Implementation choice — recommended:** `@dataclass(frozen=True, slots=True)` with `actors: types.MappingProxyType[str, str]` so both the dataclass and its inner mapping are read-only. Module location: `backend/security/token_gate.py` (new file). This mirrors the existing `backend/security/encryption.py` boundary and keeps `app_factory.py` smaller.

**Alternative considered — rejected:**

- *Module-level global* (`_TOKEN_SNAPSHOT = ...`): breaks multi-app-instance test isolation; the test suite builds a fresh app per fixture. Rejected.
- *Plain `app.config["TOKEN_SNAPSHOT"]` dict*: mutable; defeats the entire point. Rejected.
- *Stash on `app.extensions["pergen"]["token_snapshot"]`*: acceptable as the **storage location** for a frozen dataclass, but the dataclass itself must own the immutability. Adopted as the binding mechanism.

### Binding & resolution flow

```text
create_app(config_name)
  └─ _install_api_token_gate(app)
       ├─ snapshot = _build_token_snapshot(app)        # NEW — pure function
       │     ├─ raw_multi = os.environ.get(...) or app.config.get(...) or ""
       │     ├─ raw_single = os.environ.get(...) or app.config.get(...) or ""
       │     ├─ parsed = _parse_actor_tokens(raw_multi)
       │     ├─ if raw_single and "shared" not in parsed: parsed["shared"] = raw_single
       │     └─ return TokenGateSnapshot(actors=MappingProxyType(parsed), ...)
       │
       ├─ _validate_production_snapshot(snapshot)      # raises RuntimeError on fail-closed misses
       │
       ├─ app.extensions["pergen"]["token_snapshot"] = snapshot
       │
       └─ @app.before_request _enforce_api_token():
             snapshot = app.extensions["pergen"]["token_snapshot"]   # read once per request, no env access
             ... constant-time compare against snapshot.actors ...
```

### Constant-time comparison policy (mandatory invariants)

These are non-negotiable; the refactor must preserve all four:

1. **Always use `hmac.compare_digest`** for the supplied-token-vs-stored-token compare. Never `==`, never `in`, never substring.
2. **Always loop over every configured token even after a match** (current behaviour at `app_factory.py:258-260`). Do not short-circuit on hit.
3. **Compare against `bytes` of equal length** when feasible — `hmac.compare_digest` handles unequal-length strings safely but the docs note that *length itself* is not protected. Acceptable for our threat model (tokens are uniform random ≥32 chars), but document the assumption in a code comment.
4. **No early `return` based on snapshot emptiness inside the matching loop** — the empty-snapshot path is a single branch above the loop and emits the WARN exactly as today.

### Re-snapshot API (test/runtime narrow door)

Introduce one explicit function:

```text
backend.security.token_gate.rebuild_snapshot(app) -> TokenGateSnapshot
```

- Re-reads env + `app.config`, builds a fresh frozen snapshot, **replaces** the binding in `app.extensions["pergen"]["token_snapshot"]`.
- Used by:
  - `tests/conftest.py` `flask_app` fixture *only when* a test mutates `flask_app.config["PERGEN_API_TOKEN(S)"]`. Wrapped in a tiny test helper (`_set_test_tokens(app, ...)`) so test files don't touch internals directly.
  - Optional future `/api/_admin/reload-tokens` endpoint (out of scope here — see *Token Rotation* below).
- **Not** called from `before_request`. **Not** called automatically. **Not** triggered by config events.

This preserves the "immutable to the request path" invariant while keeping a single, auditable mutation point for tests and future operator tooling.

---

## Implementation Phases (TDD-first)

### Phase 0 — Pre-work (no code)

- [ ] Confirm with maintainer: are operators currently relying on the env-edit-then-no-restart behaviour? If yes, a deprecation window is required (see *Token Rotation*).
- [ ] Confirm gunicorn worker model (sync? gthread? `--preload`?). Affects worker-restart guidance.
- [ ] Confirm presence of any env-var hot-reloader (e.g., `python-dotenv` watch mode). `requirements.txt` should be checked but is not expected to contain one.

### Phase 1 — RED: graduate the existing xfail test

**File:** `tests/test_security_token_gate_immutable.py`

- [ ] Remove the `@pytest.mark.xfail(...)` decorator (lines 26-29).
- [ ] Run `pytest tests/test_security_token_gate_immutable.py -x` — must **fail** with the current implementation. This is the RED step.
- [ ] **Add a second test** in the same file to assert the snapshot is exposed and immutable:
  - `test_token_snapshot_is_frozen_dataclass_on_app_extensions` — asserts `app.extensions["pergen"]["token_snapshot"]` exists, is a `TokenGateSnapshot`, and `snapshot.actors` is a `MappingProxyType`.
  - `test_token_snapshot_actors_cannot_be_mutated` — asserts `snapshot.actors["x"] = "y"` raises `TypeError`, and `dataclasses.replace(snapshot, actors={})` is the only legal mutation path.
- [ ] **Add a third test** to lock the constant-time loop behaviour:
  - `test_token_compare_loops_over_all_actors_even_after_match` — uses `unittest.mock.patch` on `hmac.compare_digest` with a counting wrapper; asserts call-count == `len(snapshot.actors)` for both hit and miss paths.

### Phase 2 — GREEN: introduce `TokenGateSnapshot` and wire it in

**New file:** `backend/security/token_gate.py`

- [ ] Define `@dataclass(frozen=True, slots=True) class TokenGateSnapshot` with fields listed in *Target Architecture*.
- [ ] Define `def build_snapshot(app: Flask) -> TokenGateSnapshot` — the only function that touches `os.environ`/`app.config` for token resolution.
- [ ] Define `def rebuild_snapshot(app: Flask) -> TokenGateSnapshot` — re-runs `build_snapshot` and re-binds it on `app.extensions["pergen"]["token_snapshot"]`.
- [ ] Re-export `_MIN_API_TOKEN_LENGTH` from `app_factory` or move the constant into the new module and have `app_factory` import it back (preferred — avoids circular imports later).

**Modify:** `backend/app_factory.py:163-266`

- [ ] Replace the closure `_resolve_tokens()` with a single call to `build_snapshot(app)` at boot.
- [ ] Bind the result on `app.extensions["pergen"]["token_snapshot"]`.
- [ ] Production fail-closed validation now operates on `snapshot.actors` (cleaner, no second env read).
- [ ] `@app.before_request _enforce_api_token` reads the snapshot from `app.extensions["pergen"]["token_snapshot"]` exactly once per request and never consults env or `app.config`.
- [ ] Preserve: exempt paths set, `/api/*` prefix check, WARN-once log on empty-snapshot dev path, `g.actor` assignment semantics (including `"anonymous"` and `"shared"` defaults).

### Phase 3 — Test fixture migration

**Modify:** `tests/conftest.py`

- [ ] Add a small helper exposed via the `flask_app` fixture or as a separate fixture:
  - `set_api_tokens(app, *, single=None, multi=None)` — sets `app.config["PERGEN_API_TOKEN(S)"]` then calls `rebuild_snapshot(app)`.
- [ ] Document in the fixture docstring that direct `app.config["PERGEN_API_TOKEN"] = ...` no longer activates the gate.

**Modify call sites:**

- [ ] `tests/test_security_audit_batch3.py:20-51` — replace `flask_app.config["PERGEN_API_TOKEN"] = "..."` with `set_api_tokens(flask_app, single="...")`.
- [ ] `tests/test_security_audit_batch4.py:106-142` — replace `flask_app.config["PERGEN_API_TOKENS"] = "..."` with `set_api_tokens(flask_app, multi="...")`.
- [ ] `tests/test_security_audit_batch4.py:468` — same treatment.
- [ ] Any other test surfaced by `grep -nE 'config\[\"PERGEN_API_TOKEN' tests/`.

**Tests must remain GREEN after this phase. Coverage of `_install_api_token_gate` should not drop.**

### Phase 4 — REFACTOR: cleanup & documentation

- [ ] Remove the now-dead `_resolve_tokens` symbol if nothing else references it.
- [ ] Tighten typing: `TokenGateSnapshot.actors: Mapping[str, str]` annotated as `MappingProxyType[str, str]` for IDE clarity.
- [ ] Add module docstring to `backend/security/token_gate.py` referencing audit C-1 / C-2 and this plan.
- [ ] Update `ARCHITECTURE.md:417` row to note "snapshot at boot; rebuild via `rebuild_snapshot(app)`".
- [ ] Update `HOWTOUSE.md:53-84` operator section to clarify rotation requires worker restart.
- [ ] Add a short entry to `patch_notes.md` documenting the immutability fix and the test-fixture API change.

### Phase 5 — Verification loop

- [ ] `pytest -m security -x` — full security suite green.
- [ ] `pytest --cov=backend.app_factory --cov=backend.security.token_gate --cov-report=term-missing` — coverage ≥ existing baseline (no regressions on auth-gate lines).
- [ ] `ruff check backend/ tests/`.
- [ ] Manual smoke: `FLASK_CONFIG=development ./run.sh` with and without `PERGEN_API_TOKEN` set; confirm WARN-once and 401 paths still behave.
- [ ] Subprocess test (`tests/test_security_audit_batch4.py:51-97`) still passes — fail-closed in production preserved.
- [ ] Run the reactivated `test_security_token_gate_immutable.py` and confirm it is green (was xfail → now green; documents the fix).

---

## Token Rotation Operator Story

Snapshotting at boot makes rotation an **explicit operational event**. This is the desired behaviour, but operators must have a documented playbook.

### Recommended rotation playbook (post-refactor)

For a single-shared-token deployment (`PERGEN_API_TOKEN`):

1. Generate the new token: `openssl rand -hex 32`.
2. Update the secret store / `EnvironmentFile=` / `.env`.
3. Restart workers: `systemctl reload pergen` (which `kill -HUP`s gunicorn → graceful worker recycle).
4. Distribute the new token to API consumers.
5. Confirm via a probe request with the new token (200) and a probe with the old token (401).

For per-actor tokens (`PERGEN_API_TOKENS=alice:tok1,bob:tok2`):

1. Add the new token alongside the old one for the rotated actor: `alice:newtok,alice_old:oldtok,bob:tok2`.
2. Restart workers (graceful).
3. Migrate consumers from `oldtok` → `newtok` over the rotation window.
4. Remove `alice_old` from env, restart again.

This is friendlier than today's "edit env, hope the next request picks it up" because:
- Behaviour is **deterministic** — the token in effect is whichever was bound at boot.
- The rotation window is **observable** — both tokens are listed and audit logs attribute requests to `alice` vs `alice_old`.
- The change is **traceable** — restart appears in `journalctl`, env edits don't.

### gunicorn-specific notes

- With `--workers N` (sync model, no `--preload`): each worker calls `create_app()` independently. After `kill -HUP <gunicorn_master>`, the master re-execs and spawns fresh workers — **all workers will pick up the new env**.
- With `--preload`: only the master imports the app. `kill -HUP` re-execs the master → workers get the new snapshot. **Same outcome**, but verify in the target environment.
- During the brief window where old workers are draining, **both old and new tokens may be temporarily valid** (different workers, different snapshots). This is expected and matches normal blue-green semantics. Document this in `HOWTOUSE.md`.

### Optional future enhancement (out of scope here)

Add `/api/_admin/reload-tokens` (POST, behind a separate admin token) that calls `rebuild_snapshot(app)`. This would allow zero-downtime rotation without a worker restart while preserving the "explicit operator action" property. **Tracked separately** — do not bundle with this refactor.

---

## Dependencies

### Hard dependencies

- None. Stdlib-only (`dataclasses`, `types.MappingProxyType`, `hmac`, `os`, `datetime`).

### Soft dependencies / coordination

- `tests/conftest.py` `flask_app` fixture must be updated atomically with the Phase-2 code change to keep CI green.
- Any branch in flight that adds new `flask_app.config["PERGEN_API_TOKEN(S)"] = ...` test code needs a rebase to use `set_api_tokens(...)` instead.

### Out-of-tree consumers

- Operator runbooks / wiki entries that document `unset PERGEN_API_TOKEN` as a "disable auth" trick (if any exist) must be updated. Currently no such doc found in-repo.

---

## Risks

### HIGH

- **R1 — Test-fixture breaking change.** Several existing tests mutate `flask_app.config["PERGEN_API_TOKEN(S)"]` after `create_app()` and expect the gate to honour the change. After the refactor, those mutations are inert. **Mitigation:** Phase 3 of the implementation plan migrates every such call site to `set_api_tokens(...)`. Pre-flight: `grep -rn "PERGEN_API_TOKEN" tests/` and patch every hit in the same PR. Failure mode if missed: a test silently downgrades to "gate disabled" and asserts 200 instead of 401, hiding real regressions.

- **R2 — Operator-relied-upon hot-reload behaviour.** If anyone in production currently flips `PERGEN_API_TOKEN` via env edit and a `kill -USR2`-style reload (without full process restart), this refactor removes that path. **Mitigation:** confirm with maintainer in Phase 0; if needed, ship the optional `/api/_admin/reload-tokens` endpoint *before* this refactor lands so rotation remains zero-restart.

### MEDIUM

- **R3 — Multi-worker snapshot drift during deploys.** Different gunicorn workers will hold different snapshots during a graceful restart window. **Mitigation:** documented as expected behaviour in *Token Rotation*; matches normal blue-green semantics; not a regression vs today (today's env-read-per-request would *also* see drift if env is updated mid-deploy).

- **R4 — Snapshot binding lookup cost in `before_request`.** Adds one `app.extensions["pergen"]["token_snapshot"]` dict lookup per request. **Mitigation:** negligible (~50ns); net win because we remove the `os.environ.get` per request which is comparable. Benchmark if challenged but no action expected.

- **R5 — `MappingProxyType` not picklable in some test contexts.** If any test uses `multiprocessing` to fork the app, the frozen mapping may need a custom `__reduce__`. **Mitigation:** none expected — `flask_app` fixture is in-process. Re-evaluate if a future test parallelises across processes.

### LOW

- **R6 — `_MIN_API_TOKEN_LENGTH` location move.** Cosmetic — if other modules import this constant, update imports. `grep -rn _MIN_API_TOKEN_LENGTH backend/ tests/` — currently only referenced in `backend/app_factory.py` and `tests/test_security_token_gate_parsing.py`. Both can be updated trivially.

- **R7 — Documentation drift.** `ARCHITECTURE.md`, `HOWTOUSE.md`, `README.md`, `comparison_from_original.md`, `patch_notes.md`, `FUNCTIONS_EXPLANATIONS.md` all reference the gate. **Mitigation:** Phase 4 explicitly updates `ARCHITECTURE.md` + `HOWTOUSE.md` + `patch_notes.md`. The other three describe behaviour at a level that survives the refactor unchanged.

- **R8 — Audit-batch-4 subprocess tests.** They build their own app via subprocess and don't touch `flask_app.config`; they already snapshot at boot via env. Unaffected. Verified by inspection.

---

## Estimated Complexity

| Dimension | Estimate |
| --- | --- |
| Net new lines | ~80 (new `backend/security/token_gate.py` module) |
| Net deleted lines | ~30 (old `_resolve_tokens` closure + duplicated env reads) |
| Net new tests | 2-3 (in addition to graduating the xfail) |
| Test files modified | 3 (`conftest.py`, `test_security_audit_batch3.py`, `test_security_audit_batch4.py`) |
| Doc files modified | 3 (`ARCHITECTURE.md`, `HOWTOUSE.md`, `patch_notes.md`) |
| Files in PR | ~7 |
| Reviewer time | 30-45 min (small, narrow, security-sensitive) |
| Engineer time | 0.5-1 day including doc updates |
| Risk-adjusted complexity | **Medium** — code change is small but touches the auth path; test fixture migration is mechanical but easy to miss a call site. |

---

## Out of Scope

The following are explicitly **not** part of this refactor and should be tracked separately:

- **Admin reload endpoint** (`POST /api/_admin/reload-tokens`). Mentioned as a future enhancement; would unblock zero-downtime rotation. Separate RFC.
- **Audit-log enrichment** to record `actor=...` on `before_request` denials (404/401 paths). Tangentially related; out of scope.
- **Per-route token scoping** (e.g., `alice` can call `/api/inventory` but not `/api/credentials`). Significant new feature; out of scope.
- **Token rotation history / audit trail** persisted to disk. Operational tooling; out of scope.
- **Rate limiting on auth failures.** Belongs in a separate hardening pass.
- **Switching from `X-API-Token` header to `Authorization: Bearer <token>`.** Behaviour change for clients; out of scope unless explicitly requested.
- **Removing the `app.config[...]` override path entirely** (env-only). Would simplify the snapshot but break the existing test fixture pattern more deeply. Defer until a follow-up that also rewrites the fixtures cleanly.
- **Hot-reload via SIGHUP handler in the app process.** Conflicts with gunicorn's own SIGHUP semantics; not worth the complexity.

---

## Appendix: File:line evidence index

- Current per-request re-read: `backend/app_factory.py:202-217, 239`
- Current production fail-closed (already at boot, keep): `backend/app_factory.py:219-235`
- Current constant-time compare (preserve): `backend/app_factory.py:258-260`
- Current parser (reuse as-is): `backend/app_factory.py:143-160`
- Min-length constant (move or re-export): `backend/app_factory.py:58`
- Test that documents the bug (graduate from xfail): `tests/test_security_token_gate_immutable.py:26-29`
- Test fixture that mutates config post-boot: `tests/conftest.py:96-146`
- Test call sites needing migration: `tests/test_security_audit_batch3.py:24, 35, 42`; `tests/test_security_audit_batch4.py:126, 468`
- Architecture doc to update: `ARCHITECTURE.md:417`
- Operator doc to update: `HOWTOUSE.md:53-84`
- Audit ledger entry: `patch_notes.md:1431`
