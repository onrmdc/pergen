# DONE — Implementation Plan: AuditLogger Helper + Coverage Closure

> **Status:** Plan only — no code changes.
> **Scope:** Close audit-log gaps in `inventory_bp`, `notepad_bp`, `runs_bp`, `reports_bp`
> by introducing a single `AuditLogger` helper that owns event shape, then integrating
> it into all four blueprints behind a TDD loop.

---

## Requirements Restatement

The README (line 97) and patch_notes (line 1032) both promise that the `app.audit`
log channel records `actor=<name>` on every destructive / mutating operation.
Today this is only honoured by `transceiver_bp` (4 events) and `credentials_bp`
(2 events). `tests/test_security_audit_log_coverage.py` already documents the
gap with 4 `xfail` tests covering:

1. `POST /api/inventory/device` → `inventory.add`
2. `PUT  /api/notepad`          → `notepad.save`
3. `POST /api/run/pre`          → `run.pre`
4. `DELETE /api/reports/<id>`   → `report.delete`

The patch-notes flag for this work item is explicit:

> *"Larger uniform pattern — should land alongside an `AuditLogger` helper,
> not as ad-hoc logger calls."*

So the requirements are:

- **R1.** Introduce a reusable `AuditLogger` helper class (single source of
  truth for audit-event shape, severity mapping, actor resolution, redaction).
- **R2.** Define a canonical, mandatory event schema enforced by the helper
  (no free-form `f"{event} actor=… detail=…"` strings).
- **R3.** Replace existing ad-hoc `_log.info("audit credential.set actor=…")`
  call-sites in `transceiver_bp` + `credentials_bp` with `AuditLogger`
  (eat our own dog food, prevent drift).
- **R4.** Add coverage to all 4 currently-uncovered modules and **all** their
  mutating endpoints — not just the ones the xfail tests check (delete,
  update, import; pre-create, pre-restore, post, post-complete; reports
  delete; etc.).
- **R5.** Lock the schema with a unit-level test against the helper and assert
  coverage with route-level tests (the existing xfail tests should flip to
  passing without `xfail`).
- **R6.** Document retention / PII / log-volume implications.

Out of scope (explicitly deferred):

- DB-backed `EventLog` model — `request_logging.py` line 142 already calls this
  out as Phase 5 work. The helper's API must be **forward-compatible** with a
  DB sink, but this PR keeps stdout/file logging.
- Per-tenant audit segregation, SIEM forwarding, signed log chains.

---

## Current State Analysis

### Audit-log infrastructure (already built)

| File | Lines | Purpose |
|---|---|---|
| `backend/logging_config.py` | 36–46 | `_SENSITIVE_KEYS` redaction set |
| `backend/logging_config.py` | 100–125 | `JsonFormatter` — auto-redacts `extra=` keys |
| `backend/logging_config.py` | 220–224 | `app.audit` logger configured (level=INFO, propagates) |
| `backend/request_logging.py` | 33–34 | `_audit_logger = logging.getLogger("app.audit")` |
| `backend/request_logging.py` | 119–157 | Existing `audit_log(event, actor, detail, severity, **extra)` free function |

**Important:** `request_logging.py:audit_log` already exists, but it formats
the message as `f"{event} actor={actor} detail={detail}"` — a *string*, not a
structured event. It is also not used by any blueprint. The new `AuditLogger`
class should subsume this function (the function can become a thin
back-compat wrapper or be removed once tests are updated).

### Existing call-sites (the patterns to unify)

| File | Line | Current call |
|---|---|---|
| `backend/blueprints/credentials_bp.py` | 93 | `_log.info("audit credential.set actor=%s name=%s method=%s", _actor(), name, method)` |
| `backend/blueprints/credentials_bp.py` | 109 | `_log.info("audit credential.delete actor=%s name=%s", _actor(), name)` |
| `backend/blueprints/transceiver_bp.py` | 224–230 | `_log.info("audit transceiver.recover ok actor=%s host=%s ip=%s vendor=cisco interfaces=%s", …)` |
| `backend/blueprints/transceiver_bp.py` | 255–261 | same, vendor=arista |
| `backend/blueprints/transceiver_bp.py` | 364–370 | `audit transceiver.clear_counters ok actor=…` (cisco) |
| `backend/blueprints/transceiver_bp.py` | 399–405 | same (arista) |

Notes on the **actor resolution pattern**: every blueprint defines a private
`_actor()` helper that pulls from `flask.g.actor` with `"anonymous"` fallback.
This must move into the helper.

### Missing call-sites (the gap)

| Blueprint | Route | Mutating? | Audit needed? |
|---|---|---|---|
| `inventory_bp.py:154` | `POST   /api/inventory/device` | ✅ add | **YES** (`inventory.add`) |
| `inventory_bp.py:162` | `PUT    /api/inventory/device` | ✅ update | **YES** (`inventory.update`) |
| `inventory_bp.py:171` | `DELETE /api/inventory/device` | ✅ delete | **YES** (`inventory.delete`) |
| `inventory_bp.py:181` | `POST   /api/inventory/import` | ✅ bulk add | **YES** (`inventory.import`) |
| `notepad_bp.py:43` | `PUT/POST /api/notepad` | ✅ overwrite | **YES** (`notepad.save`) |
| `runs_bp.py:104` | `POST /api/run/device` | ⚠️ executes commands on device | **YES** (`run.device`) |
| `runs_bp.py:128` | `POST /api/run/pre` | ✅ runs PRE | **YES** (`run.pre`) |
| `runs_bp.py:172` | `POST /api/run/pre/create` | ✅ persists report | **YES** (`run.pre.create`) |
| `runs_bp.py:205` | `POST /api/run/pre/restore` | ✅ restores state | **YES** (`run.pre.restore`) |
| `runs_bp.py:236` | `POST /api/run/post` | ✅ runs POST | **YES** (`run.post`) |
| `runs_bp.py:271` | `POST /api/run/post/complete` | ✅ persists report | **YES** (`run.post.complete`) |
| `reports_bp.py:73` | `DELETE /api/reports/<run_id>` | ✅ deletes from disk | **YES** (`report.delete`) |
| `reports_bp.py:45` (with `?restore=1`) | `GET /api/reports/<id>?restore=1` | ⚠️ side-effect (state mutation) | **YES** (`report.restore`) |
| Read-only GETs (lists, fetch) | various | ❌ | NO (would be access-log noise) |

### Existing test surface

| File | Lines | Status |
|---|---|---|
| `tests/test_security_audit_log_coverage.py` | 32–119 | 4 `xfail` tests — flip to pass after integration |
| `tests/test_security_audit_batch4.py` | 501–515 | Asserts `credential.set` audit line — must keep passing |
| `tests/test_request_logging.py` | 81–89 | Asserts `audit_log()` free-function shape — keep or update if replaced |
| `tests/test_logging_config.py` | 142 | Asserts `app.audit` logger exists |

### Storage backend

There is **no DB-backed audit storage today**. `EventLog` is mentioned in
`request_logging.py:142` as a future Phase-5 item. Audit events ride the same
JSON stdout/file handlers as everything else, with `app.audit` as the logger
name acting as the channel discriminator. The plan must keep a clean seam so
a future `AuditSink` can be plugged in without touching call-sites.

---

## AuditLogger API Design

### File layout

```
backend/audit/
    __init__.py          # re-exports AuditLogger, AuditEvent, default singleton
    logger.py            # AuditLogger class
    events.py            # AuditEvent dataclass + Action / Outcome enums
    sinks.py             # AuditSink protocol + LoggingSink (default)
```

Rationale: a dedicated package, not a single module under `backend/`, because
(a) we expect a `DBSink` and possibly a `SiemSink` to land later, and (b) it
keeps `request_logging.py` focused on per-request middleware.

### Class shape (Python signatures, NOT implementation)

```python
# backend/audit/events.py
class Outcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED  = "denied"   # auth/policy refused

@dataclass(frozen=True)   # immutable per repo coding rule
class AuditEvent:
    action:        str          # dotted, e.g. "inventory.add"
    actor:         str          # never empty; "anonymous" allowed
    resource_type: str          # "device" | "notepad" | "run" | "report" | "credential"
    resource_id:   str | None   # hostname, run_id, credential name, etc.
    outcome:       Outcome
    request_id:    str | None   # flask.g.request_id when available
    timestamp:     str          # ISO-8601 UTC, set by helper
    context:       dict[str, Any]  # extra fields, redaction-aware
```

```python
# backend/audit/sinks.py
class AuditSink(Protocol):
    def emit(self, event: AuditEvent) -> None: ...

class LoggingSink:
    """Default sink — writes one structured INFO record to app.audit."""
    def __init__(self, logger_name: str = "app.audit") -> None: ...
    def emit(self, event: AuditEvent) -> None: ...
```

```python
# backend/audit/logger.py
class AuditLogger:
    """
    Single source of truth for audit events.
    Resolves actor + request_id from flask.g, builds AuditEvent, dispatches to sink.
    """

    def __init__(self, sink: AuditSink | None = None) -> None: ...

    # Primary method — called from blueprints.
    def log(
        self,
        action:        str,
        *,
        resource_type: str,
        resource_id:   str | None = None,
        outcome:       Outcome = Outcome.SUCCESS,
        actor:         str | None = None,        # override; else flask.g.actor
        **context: Any,                          # ride-along, redaction-aware
    ) -> None: ...

    # Convenience helpers (thin wrappers, named for grep-ability).
    def success(self, action: str, **kw: Any) -> None: ...
    def failure(self, action: str, **kw: Any) -> None: ...
    def denied(self,  action: str, **kw: Any) -> None: ...
```

### Module-level singleton

A module-level `audit = AuditLogger()` in `backend/audit/__init__.py` is the
default import target so blueprints stay one-liners:

```python
from backend.audit import audit
audit.log("inventory.add", resource_type="device", resource_id=hostname)
```

For tests, the singleton's `_sink` is swappable via a `with_sink()`
context-manager helper or via dependency injection through `app.extensions`.

### Backwards compatibility

`backend.request_logging.audit_log` becomes a thin shim:

```python
def audit_log(event, actor, detail="", severity="info", **extra):
    # back-compat wrapper — emits via the new AuditLogger; deprecated.
    audit.log(event, resource_type="legacy", actor=actor,
              outcome=Outcome.SUCCESS if severity=="info" else Outcome.FAILURE,
              detail=detail, **extra)
```

This keeps `tests/test_request_logging.py:81` green without rewriting it now.

---

## Canonical Event Schema

Every audit log record has **mandatory** keys (enforced by `AuditEvent` being
a frozen dataclass with required fields) and **optional** context keys.

### Mandatory fields

| Field | Type | Source | Notes |
|---|---|---|---|
| `action`        | str (dotted) | call-site | e.g. `inventory.add`, `run.post`, `report.delete` |
| `actor`         | str | `flask.g.actor` or override | `"anonymous"` allowed; never `""`/`None` |
| `resource_type` | str | call-site | enum-like: `device`, `notepad`, `run`, `report`, `credential`, `interface` |
| `resource_id`   | str \| None | call-site | hostname, run_id, credential name, etc.; `None` for bulk ops |
| `outcome`       | enum | call-site | `success` \| `failure` \| `denied` |
| `request_id`    | str \| None | `flask.g.request_id` | tied to per-request middleware |
| `timestamp`     | ISO-8601 UTC | helper | set in `AuditLogger.log` |

### JSON shape on the wire (via `JsonFormatter`)

```json
{
  "ts":         "2026-04-22T15:42:11.018Z",
  "level":      "INFO",
  "logger":     "app.audit",
  "msg":        "audit inventory.add success actor=alice resource=device:leaf-99",
  "action":     "inventory.add",
  "actor":      "alice",
  "resource_type": "device",
  "resource_id": "leaf-99",
  "outcome":    "success",
  "request_id": "8f4a-…",
  "context":    { "fabric": "FAB1", "site": "Mars" }
}
```

The human-readable `msg` is preserved so `grep audit` still works on TTY logs.
The structured fields ride `extra=` so the `JsonFormatter` redactor catches
any sensitive keys someone slips into `context`.

### Action vocabulary (closed set, validated at call-time only via lint)

Initial vocabulary — extend deliberately, not ad-hoc:

```
credential.set, credential.delete, credential.validate
inventory.add, inventory.update, inventory.delete, inventory.import
notepad.save
run.device, run.pre, run.pre.create, run.pre.restore,
run.post, run.post.complete
report.delete, report.restore
transceiver.recover, transceiver.clear_counters
```

### PII / redaction rules

- **Never put** raw notepad content, command outputs, password fields, or
  request bodies in `context`.
- The `JsonFormatter` auto-redacts any context key matching
  `_SENSITIVE_KEYS` (`logging_config.py:36`), which already covers
  `password`, `token`, `api_key`, etc. Keep using these names — don't be
  cute (e.g. avoid `pwd_field`).
- For notepad save, log only `bytes=<len(content)>`, not the content.
- For run.* events, log device count + hostname list (≤10 names; truncate),
  never command outputs.

---

## Implementation Phases

> Hard rule: **TDD throughout.** Every phase starts with a failing test,
> proceeds to minimal green, refactors. No phase merges without 80%+
> coverage on the touched files.

### Phase 1 — Build the helper (no behaviour change anywhere yet)

Goal: ship `backend/audit/` with full unit tests. Nothing else changes.

| Step | File | Action | Risk |
|---|---|---|---|
| 1.1 | `tests/audit/test_audit_event_shape.py` (new) | Write failing tests asserting `AuditEvent` mandatory fields, frozen-ness, ISO-8601 timestamp format, JSON-serialisable shape. | Low |
| 1.2 | `tests/audit/test_audit_logger.py` (new) | Failing tests: `AuditLogger.log` (a) emits exactly one record on `app.audit`, (b) sets `actor` from `flask.g.actor`, (c) falls back to `"anonymous"`, (d) attaches `request_id` from `flask.g.request_id`, (e) records `outcome` correctly for success/failure/denied, (f) survives missing flask context (background workers), (g) redacts `password=` in context. | Low |
| 1.3 | `tests/audit/test_audit_sinks.py` (new) | Failing test: `LoggingSink` writes to `app.audit` with INFO level; sink protocol allows custom sinks (use a fake list-sink). | Low |
| 1.4 | `backend/audit/events.py` (new) | Implement `Outcome` enum + `AuditEvent` dataclass. | Low |
| 1.5 | `backend/audit/sinks.py` (new) | Implement `AuditSink` protocol + `LoggingSink`. | Low |
| 1.6 | `backend/audit/logger.py` (new) | Implement `AuditLogger` + module singleton. | Low |
| 1.7 | `backend/audit/__init__.py` (new) | Re-export `audit`, `AuditLogger`, `AuditEvent`, `Outcome`. | Low |
| 1.8 | `backend/request_logging.py:119` | Replace body of `audit_log()` with shim that delegates to new helper; keep signature; mark deprecated in docstring. Verify `tests/test_request_logging.py:81-89` still green. | Med — back-compat |

**Exit gate:** All new unit tests green; existing `test_request_logging.py`,
`test_logging_config.py`, `test_security_audit_batch4.py` still green; no
blueprints touched yet.

### Phase 2 — Migrate existing call-sites (eat our own dog food)

Goal: replace ad-hoc `_log.info("audit …")` in `credentials_bp` +
`transceiver_bp` so we have **one** pattern. No new audit events yet.

| Step | File | Action | Risk |
|---|---|---|---|
| 2.1 | `tests/test_security_audit_batch4.py` (and any sibling) | Tighten existing assertions: instead of substring match on `"credential.set"`, assert the *structured* fields (`action == "credential.set"`, `actor == "…"`, `resource_type == "credential"`). These should still pass against the old code thanks to the shim, but document the new shape. | Med — risk of breaking |
| 2.2 | `backend/blueprints/credentials_bp.py:93,109` | Replace `_log.info("audit credential.set …")` with `audit.log("credential.set", resource_type="credential", resource_id=name, method=method)`. Delete `_log` import (or keep for `app.blueprints.credentials` error logger). Drop `_actor()` helper. | Low |
| 2.3 | `backend/blueprints/transceiver_bp.py:224,255,364,399` | Same migration for the 4 emissions. Action names: `transceiver.recover`, `transceiver.clear_counters`. `resource_type="interface"`, `resource_id=hostname`, context: `vendor`, `interfaces` / `interface`. | Low |
| 2.4 | Run full suite | `pytest -q` — confirm `tests/test_security_audit_log_coverage.py` xfails are still **xfail** (not unexpectedly passing — those are still gaps), and migrated emissions still match assertions. | Low |

**Exit gate:** Zero `logging.getLogger("app.audit")` direct calls anywhere
except inside `backend/audit/`. Add a CI-friendly grep check (or ruff/regex
lint) to enforce.

### Phase 3 — Inventory coverage

| Step | File | Action | Risk |
|---|---|---|---|
| 3.1 | `tests/test_security_audit_log_coverage.py:32-56` | Remove `xfail` from `test_inventory_add_emits_audit_log`; tighten assertion to check `action == "inventory.add"`, `resource_type == "device"`, `resource_id == "leaf-99"`. Test must FAIL. | Low |
| 3.2 | New tests for `inventory.update`, `inventory.delete`, `inventory.import` (success + failure outcomes). | Low |
| 3.3 | `backend/blueprints/inventory_bp.py:154-191` | Add `audit.log(...)` call in each of the 4 mutating routes: emit `outcome=success` on the success branch, `outcome=failure` on the validation-failure branch (so `xfail`-style attacks are visible). For `import`, log once with `count=len(rows)`, plus `skipped_count`. | Med — must thread through service return-value tuple |
| 3.4 | Run suite. | Low |

**Exit gate:** All inventory tests green; the inventory `xfail` flips to
real pass.

### Phase 4 — Notepad coverage

| Step | File | Action | Risk |
|---|---|---|---|
| 4.1 | `tests/test_security_audit_log_coverage.py:60-72` | Remove `xfail` on `test_notepad_save_emits_audit_log`; assert `action == "notepad.save"`, `resource_type == "notepad"`, `resource_id is None`, context contains `bytes=<int>` (NOT raw content). | Low |
| 4.2 | Add test asserting **content is NOT in the audit record** (PII guard). | Low |
| 4.3 | `backend/blueprints/notepad_bp.py:43-67` | Emit `audit.log("notepad.save", resource_type="notepad", bytes=len(content), user=user)` after successful `_svc().update`. On exception path (line 62), emit `outcome=failure`. | Low |

**Exit gate:** Notepad xfail flips to real pass; PII guard test green.

### Phase 5 — Runs coverage

This is the largest module — 6 mutating routes. Do them in sub-phases to keep
PRs reviewable.

| Step | File | Action | Risk |
|---|---|---|---|
| 5.1 | Tests for `run.pre` (remove xfail), `run.pre.create`, `run.pre.restore`, `run.post`, `run.post.complete`, `run.device`. Each asserts `resource_type == "run"`, `resource_id == run_id`, context includes `device_count` and **truncated hostnames** (≤10). | Med — many devices in fixtures |
| 5.2 | `backend/blueprints/runs_bp.py:104,128,172,205,236,271` | Add audit calls. For `run.pre`: log AFTER `_run_devices_inline` returns, with `outcome=success` if no rejected devices, `outcome=failure` otherwise. For `run.post*`: include `pre_run_id` in context. | Med — branchy code |
| 5.3 | Add test asserting **command outputs are NOT in audit context** (PII guard). | Low |

**Exit gate:** `run.pre` xfail flips to real pass; all 6 run routes covered.

### Phase 6 — Reports coverage

| Step | File | Action | Risk |
|---|---|---|---|
| 6.1 | `tests/test_security_audit_log_coverage.py:106-119` | Remove `xfail`; assert `action == "report.delete"`, `resource_type == "report"`, `resource_id == run_id`. | Low |
| 6.2 | New test for `report.restore` (the `?restore=1` GET side-effect). | Low |
| 6.3 | `backend/blueprints/reports_bp.py:73,57` | Emit `audit.log("report.delete", …)` after `_service().delete()` (and on the exception branch with `outcome=failure`). Emit `audit.log("report.restore", …)` only in the `restore=1` branch of `api_report_get`. | Low |

**Exit gate:** Reports xfail flips to real pass; **all 4 original xfails are
now real passes** — remove `pytestmark` xfail leftovers from the file.

### Phase 7 — Lint guard + docs

| Step | File | Action | Risk |
|---|---|---|---|
| 7.1 | `pyproject.toml` (ruff config) or a small `tests/test_audit_logger_only.py` | Add a static check that asserts no module under `backend/blueprints/` calls `logging.getLogger("app.audit")` directly — only `from backend.audit import audit` is allowed. | Low |
| 7.2 | `FUNCTIONS_EXPLANATIONS.md:52` | Update entry; document new `AuditLogger.log` signature; mark old `audit_log()` deprecated. | Low |
| 7.3 | `README.md:97` (A09 row) | Update to reflect 4 new modules covered. | Low |
| 7.4 | `patch_notes.md:1434` | Mark this follow-up item DONE; link to the new doc. | Low |

---

## Dependencies

- Flask ≥ 2 (already used) — for `flask.g` resolution.
- Stdlib `dataclasses`, `enum`, `typing` (no new pip dependency).
- `JsonFormatter` (already exists in `backend/logging_config.py`) — must stay
  the configured formatter for `app.audit` for structured fields to land.
- Phase 1 must complete before any other phase. Phases 2–6 are
  **parallelisable** (each touches a different blueprint).
- A future `EventLog` DB-backed sink is **not** a dependency of this work,
  but the `AuditSink` protocol must not assume stdout-only.

---

## Risks

### HIGH

- **Audit-spam → log volume**. Adding ~12 new INFO emissions per request burst
  (e.g. an inventory import of 500 rows) can balloon log size. **Mitigation:**
  for `inventory.import`, emit ONE event with `count=N` and `skipped_count=M`,
  not N events. For `run.pre/post`, emit ONE event per run, not per device.
- **PII leakage via `context=`**. Notepad content, raw command outputs, and
  device passwords could end up in `extra=` if a future contributor is sloppy.
  **Mitigation:** (a) `JsonFormatter` already redacts known sensitive keys;
  (b) add an explicit `tests/audit/test_audit_no_pii.py` that calls each
  endpoint and asserts the audit record's serialised form does NOT contain
  marker strings (`"audit-coverage probe"`, raw command output snippets,
  password values); (c) document the PII rule in the helper docstring.

### MEDIUM

- **Test fragility — substring matching**. Existing tests
  (`test_security_audit_batch4.py:515`) match on `"credential.set"` substring.
  The new structured shape still includes that substring in `msg`, but if
  someone changes `msg` formatting later, those tests break. **Mitigation:**
  Phase 2.1 tightens these to assert structured `action` field.
- **Back-compat with `request_logging.audit_log`**. The free function is
  imported from `tests/test_request_logging.py:83`. **Mitigation:** keep
  it as a deprecated shim that delegates to the new helper; do not remove.
- **Retention policy is undefined**. `JsonFormatter` writes to `app.audit`
  which today rides the same `RotatingFileHandler` as everything else
  (`logging_config.py:208`). Audit events historically need longer retention
  than debug logs. **Mitigation:** out of scope for this PR, but flag in
  `patch_notes.md`: a future `audit.log` separate file handler with longer
  rotation should be added when DB-backed `EventLog` lands.

### LOW

- **Performance**. Audit emissions are synchronous I/O on the request path.
  At INFO-level JSON formatting, this is sub-millisecond per event and the
  helper adds ~one dataclass allocation. Negligible vs. SSH/eAPI runtime.
- **Background-worker context**. `flask.g` is unavailable outside a request.
  **Mitigation:** `AuditLogger.log` checks `has_request_context()` and
  defaults `actor="system"`, `request_id=None`. Test 1.2.f covers this.
- **Action-name typos**. No compile-time enforcement of the action vocabulary.
  **Mitigation:** keep the vocabulary list in `backend/audit/events.py` as a
  `KNOWN_ACTIONS: frozenset` and have `AuditLogger.log` warn (not raise)
  when an unknown action is used — strict in tests via a fixture.

---

## Success Criteria

- [ ] `backend/audit/` package exists with `AuditLogger`, `AuditEvent`,
      `Outcome`, `AuditSink`, `LoggingSink`.
- [ ] All 4 `xfail` tests in `tests/test_security_audit_log_coverage.py`
      flip to real `pass` (xfail markers removed).
- [ ] All 12 mutating routes across the 4 modules emit structured audit
      events with the canonical schema.
- [ ] `credentials_bp` + `transceiver_bp` migrated to use `AuditLogger`
      (no direct `getLogger("app.audit")` outside `backend/audit/`).
- [ ] PII-guard test green (no command outputs / notepad content / passwords
      in audit records).
- [ ] `tests/test_security_audit_batch4.py` and `tests/test_request_logging.py`
      still green (back-compat preserved).
- [ ] `FUNCTIONS_EXPLANATIONS.md`, `README.md`, `patch_notes.md` updated.
- [ ] Coverage on `backend/audit/` ≥ 90%; coverage on touched blueprint
      lines unchanged or improved.

---

## Estimated Complexity

| Phase | Complexity | Notes |
|---|---|---|
| Phase 1 — Helper + tests              | **M**   | New package, ~250 LOC + tests; no integration risk |
| Phase 2 — Migrate existing call-sites | **S**   | 6 call-sites, mechanical |
| Phase 3 — Inventory                   | **S**   | 4 routes, simple service contracts |
| Phase 4 — Notepad                     | **XS**  | 1 route |
| Phase 5 — Runs                        | **L**   | 6 routes, branchy state machine, biggest review |
| Phase 6 — Reports                     | **S**   | 2 emit sites |
| Phase 7 — Lint + docs                 | **XS**  | Cleanup |
| **Total**                             | **M**   | ~1–2 PRs if Phases 3–6 land in parallel; ~3 PRs if sequential |

