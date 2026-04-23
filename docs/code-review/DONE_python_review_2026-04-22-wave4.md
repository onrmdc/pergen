# DONE — Pergen Backend — Python Code Review (Wave 4)

**Date:** 2026-04-22
**Reviewer:** python-reviewer (Claude Opus 4.7, opencode session)
**Scope:** NEW issues introduced or surfaced after the wave-3 close-out
**Baseline:** `docs/code-review/python_review_2026-04-22.md` (graded the parser refactor A−)
**Mode:** Pure review — **no code modified**

---

## Executive Summary

Wave-3 split four more god modules (`find_leaf`, `nat_lookup`, `bgp_looking_glass`,
`route_map_analysis`) using the same playbook the parsers received in wave-2.
**Behaviour is preserved verbatim**: every package is a back-compat shim that
re-exports the legacy private surface, and the late-binding-through-shim pattern
keeps every existing `unittest.mock.patch("backend.<module>.<symbol>", ...)`
landing on the live call site. Documentation discipline (docstrings citing audit
IDs, "verbatim from legacy" annotations, dedicated `cisco_envelope.py` extracted
per HIGH-3) is solid.

There is **one HIGH-severity finding** worth flagging: a missing `actor=` argument
on `store.get(run_id)` at `runs_bp.py:312` (api_run_post_complete) bypasses the
M-02 IDOR scoping that the rest of the same blueprint enforces. This is an
**actual security regression** introduced when `RunStateStore` grew the optional
`actor` parameter — three of the four call sites adopted it; one was missed.

The remaining findings are MEDIUM polish items (naming inconsistency between
`_actor()` and `_current_actor()` across blueprints; two new bare
`except Exception: pass` blocks in `find_leaf/` without `noqa: BLE001` markers;
zero logging in any of the four new packages despite the parser pack moving
toward observable failure modes), LOW carry-overs from the previous review that
were explicitly out-of-scope per `wave3_roadmap.md` (LOW-3 private
`_get_credentials` reach-through; HIGH-6 `("", "")` ambiguity), and a handful of
NIT items.

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 1 |
| MEDIUM   | 7 |
| LOW      | 5 |
| NIT      | 4 |

**Verdict:** Approve with one HIGH fix (HIGH-1 below — single-line patch). Refactor
grades for the four new packages: see "Package Grades" section.

---

## Top 5 Most Impactful Suggestions

1. **Add `actor=_current_actor()` to `runs_bp.py:312`** (HIGH-1, security
   regression) — `api_run_post_complete` calls `store.get(run_id)` without the
   actor argument that every other state-store read in the same file passes. As a
   result an attacker holding any other operator's `run_id` can complete their
   PRE run via POST. The fix is a one-character change. The same handler also
   calls `store.update(...)` with no actor preservation contract — `update()`
   does not accept `actor`, but it does silently overwrite the
   `_created_by_actor` key if a caller patches it via `**fields`. Worth
   hardening either the caller or the API.

2. **Add a per-call logger to the four new packages** (MED-1) — ZERO logging in
   `find_leaf/`, `nat_lookup/`, `bgp_looking_glass/`, `route_map_analysis/`.
   Two NEW bare `except Exception: pass` blocks were ported verbatim from the
   legacy modules without `# noqa: BLE001` markers and without the `_log.debug(...,
   exc_info=True)` observability that wave-2 added in `parsers/engine.py:128`.
   Every silent swallow is a hidden incident-triage failure. Same shape as the
   original HIGH-1: either narrow the catch or log + re-raise.

3. **Remove the duplicated `_actor()` helper across five blueprints** (MED-3) —
   `notepad_bp`, `transceiver_bp`, `credentials_bp`, `reports_bp`, `inventory_bp`
   each define their own `_actor() -> str` returning `"anonymous"` for missing,
   while `runs_bp` defines `_current_actor() -> str | None` returning `None` for
   missing. Reports_bp re-implements the M-02 logic inline at lines 102-111 with
   a defensive try/except. Promote one shared helper into
   `backend/blueprints/_actor_helpers.py` (or `backend/request_logging.py` —
   already exposes `_audit_logger`). The current divergence is what produced the
   HIGH-1 oversight — when a blueprint author looks at the wrong template, they
   skip the `actor=` argument.

4. **Document or remove the `_created_by_actor` reserved key from
   `RunStateStore.update()`** (MED-2) — `update(**fields)` accepts arbitrary
   kwargs that get merged into the stored dict. Nothing prevents a caller from
   passing `_created_by_actor="someone-else"` and silently rewriting the IDOR
   ownership marker. Either prefix the key with double underscore (Python
   name-mangling does not help here, but convention does), or filter
   `_created_by_actor` out of the `**fields` mapping in `update()` so the
   ownership invariant is enforced at the store boundary, not at every caller.

5. **Promote `_get_credentials` to a public API** (MED-7, ratifying LOW-3 from
   previous review) — wave-3 doubled the number of importers of the private
   `_get_credentials` symbol from `backend.runners.runner` (was 3, now 6:
   `bgp_bp`, `device_commands_bp`, `nat_lookup/__init__`, `nat_lookup/service`,
   `find_leaf/strategies/cisco`, `find_leaf/strategies/arista`). This is the
   second wave that preserved the legacy private name to avoid touching the
   call-site test patches. Rename to `get_credentials_from_store` and provide a
   one-line backwards-compat alias `_get_credentials = get_credentials_from_store`
   so the existing patches keep working through the shim.

---

## HIGH-1 Verification: Did wave-3's parser bare-except fix hold?

**YES — the parser fix is intact.** Grepping `backend/parsers/` for
`except Exception` returns exactly **one hit**:

```
backend/parsers/engine.py:128:    except Exception as exc:  # pragma: no cover - defensive
```

…which is the documented dispatcher fallback (with `# pragma: no cover`).
Every other previously-flagged catch (16 modules listed in HIGH-1 of
`python_review_2026-04-22.md`) is now narrowed to a specific exception tuple
with the `# narrow audit HIGH-1` marker:

```
backend/parsers/arista/disk.py:31: except (TypeError, ValueError, KeyError, AttributeError):  # narrow audit HIGH-1
backend/parsers/arista/bgp.py:34:  except (TypeError, ValueError, KeyError, AttributeError):  # narrow audit HIGH-1
…
backend/parsers/common/regex_helpers.py:19,29: except (re.error, AttributeError, TypeError):  # narrow audit HIGH-1
backend/parsers/generic/field_engine.py:60:    except (json.JSONDecodeError, ValueError, TypeError):  # narrow audit HIGH-1
```

**HIGH-3 (Cisco envelope unwrap)** is also fully applied: the new
`backend/parsers/common/cisco_envelope.py:cisco_unwrap_body` is imported by
all 5 NX-OS parsers (`interface_status`, `interface_detailed`,
`interface_description`, `interface_mtu`, `transceiver`), and each call site
collapses to a single `data = cisco_unwrap_body(raw_output)` line.

However: **two NEW bare `except Exception:` blocks were introduced in
`find_leaf/`** when the legacy module was split:

```
backend/find_leaf/service.py:158:           except Exception:
backend/find_leaf/strategies/cisco.py:136:  except Exception:
```

Neither has a `# noqa: BLE001` marker, neither logs, neither narrows. They are
ports of identical legacy code (audit M-09 — first-hit-wins parallel cancel —
is documented as deferred), so behaviour-preservation justifies the carry-over,
but the ergonomic regression is real and should be tracked. See MED-1 below.

---

## Files > 800 Lines

**None.** Largest file in the backend is `app_factory.py` at 500 LOC, well
under the 800-line block threshold. The full top-10:

| Rank | File | LOC |
|------|------|-----|
| 1 | `backend/app_factory.py` | 500 |
| 2 | `backend/bgp_looking_glass/ripestat.py` | 440 |
| 3 | `backend/blueprints/runs_bp.py` | 427 |
| 4 | `backend/blueprints/transceiver_bp.py` | 424 |
| 5 | `backend/security/encryption.py` | 410 |
| 6 | `backend/blueprints/device_commands_bp.py` | 285 |
| 7 | `backend/nat_lookup/service.py` | 277 |
| 8 | `backend/services/inventory_service.py` | 258 |
| 9 | `backend/services/transceiver_service.py` | 254 |
| 10 | `backend/repositories/credential_repository.py` | 229 |

Wave-3 reduced the largest "god module" file from 447 LOC
(`bgp_looking_glass.py`) to 440 LOC (`bgp_looking_glass/ripestat.py`); the
total package is 6 files / 842 LOC, but the responsibility per file is now
focused. `ripestat.py` is large because it owns 8 RIPEStat endpoints, each
~50 LOC of request-shaping + response-parsing — splitting per-endpoint would
trade 1 file at 440 LOC for 8 files at ~55 LOC, which is the same call as the
parser pack. Track as a NIT-only follow-up if endpoint-level isolation
becomes useful for testing.

---

## Late-Binding Pattern Spot-Check

Wave-3 uses a documented late-binding pattern in three of the new packages:

```python
# In backend/find_leaf/service.py, backend/nat_lookup/service.py,
# backend/bgp_looking_glass/{peeringdb,ripestat}.py
def find_leaf(...):
    # Late binding so test patches on the shim land here.
    from backend import find_leaf as _shim
    ...
    hit = _shim._query_one_leaf_search(dev, ...)
```

### Spot-check 1 — `backend/find_leaf/service.py`

The shim resolution at lines 40 and 109 is **correctly placed inside each
public function** (not at module level) and **only routes through `_shim` for
the two symbols (`_query_one_leaf_search`, `_complete_find_leaf_from_hit`)
that legacy tests patch**. Internal helpers (`_is_valid_ip`,
`_leaf_ip_from_remote`) are imported directly. This is the right call —
late-binding has measurable cost (one dict lookup + module-attr access per
call) and adding it to non-patched symbols would be cargo-culting.

The pattern is documented in the module docstring (lines 1-15) and the
`__init__.py` shim docstring (lines 16-19). The `from backend import
find_leaf as _shim` import inside each function is annotated with
`# Late binding so test patches on the shim land here.` at every call site.

**Verdict:** Pattern is appropriate and well-documented.

### Spot-check 2 — `backend/bgp_looking_glass/ripestat.py`

Different shape: `ripestat.py` defines a `_shim_get_json(url, params, timeout)`
proxy at lines 32-43 and uses it from every fetch helper. This is **better
than `find_leaf`'s pattern** for two reasons:

* The proxy localises the late-binding cost to one function (instead of
  re-importing `_shim` in every public entrypoint).
* The proxy gives a single grep-able call site for any future audit of the
  network boundary — useful because `_get_json` enforces audit M-01
  (`allow_redirects=False`).

Compare `peeringdb.py` (line 32-34) which inlines the late-binding pattern:

```python
from backend import bgp_looking_glass as _shim
pdb = _shim._get_json(PEERINGDB_NET, {"asn": asn_clean})
```

Both work, both are documented. The `_shim_get_json` proxy is the cleaner
shape and would be worth adopting in `find_leaf/service.py` too if the file
ever grows past its current two call sites. NIT-only.

**Verdict:** `ripestat.py` `_shim_get_json` proxy is the cleanest of the
three; `peeringdb.py` and `find_leaf/service.py` use a slightly more verbose
shape but all three are correct, documented, and reach the test-patched
symbols. The pattern smell is real (a non-Python reader has to chase the
`_shim.foo` indirection through the package `__init__`) but it is the
**right tradeoff** for preserving 1128 tests' patch targets.

---

## Package Grades

### `backend/find_leaf/` — Grade: **B+**

**Strengths.** Clean 6-file split (1 `__init__` shim + `service` orchestrator + 1
`ip_helpers` + 2 vendor strategies under `strategies/`). The vendor strategy
boundary is the right one — adding a Juniper strategy would be one new file in
`strategies/`, one elif in `__init__.py`. Docstrings cite the wave-3 roadmap
and document audit M-09 deferral. `from __future__ import annotations` is
applied consistently. Tests for the legacy private surface
(`test_legacy_coverage_find_leaf_nat.py`) continue to pass byte-for-byte.

**Why not A.**
* Two new bare `except Exception: pass` blocks (service.py:158,
  strategies/cisco.py:136) ported verbatim from legacy with no `noqa: BLE001`
  marker and no logging. Both are documented as audit M-09 deferrals in
  service.py's docstring, but the marker discipline used elsewhere in the
  codebase was not applied (MED-1, MED-6).
* The `__init__.py` shim's `_query_one_leaf_search` and
  `_complete_find_leaf_from_hit` re-implement the dispatch in 12 lines of
  if/elif — moving them into `strategies/__init__.py` (or a tiny
  `strategies/dispatch.py`) would let the package shim be pure re-exports.
* `_get_credentials` reach-through into both strategies (LOW-3 carry-over).

### `backend/nat_lookup/` — Grade: **A−**

**Strengths.** Best-organised of the four new packages. Six files cleanly
separated by responsibility (`ip_helpers` → IP validator, `xml_helpers` →
defusedxml parse/format, `palo_alto/api` → HTTP client + xpath builder,
`service` → orchestration). Audit H-1 is preserved with a forced literal
import + docstring + dedicated test pin
(`tests/test_security_audit_batch4.py::test_nat_lookup_imports_defusedxml_unconditionally`).
Audit H7 (XPath escaping) is correctly localised to
`build_rule_config_xpath` with a documented refusal path for ambiguous names.
The orchestrator was split into three small helpers (`_empty_result`,
`_resolve_fabric_site`, `_try_one_firewall`) and reads top-to-bottom — a
clear win over the 186-line legacy `nat_lookup` function.

**Why not A.**
* `_try_one_firewall` returns a `tuple[bool, bool]` — the
  `(handled, should_return)` semantics are documented in the docstring but
  the call site (`if handled or should_return:`) makes the distinction look
  like dead code. A small `Enum` or named tuple would be clearer (MED-4).
* `out["error"]` is overwritten on every loop iteration in
  `nat_lookup` (line 269-274), so on multi-firewall rejection only the last
  firewall's error message survives. Behaviour preserved from legacy.
* `__init__.py` carries 8 `# noqa: F401` markers for re-exports. They're all
  legitimate (each is a documented test-patch target), but the volume hints
  the shim is doing more than just re-export — it's also smuggling
  `requests` and `find_leaf_module` as module attributes. NIT.

### `backend/bgp_looking_glass/` — Grade: **A−**

**Strengths.** The cleanest separation of HTTP boundary (`http_client.py`,
56 LOC) from request-shaping (`ripestat.py`, 440 LOC) from public
orchestration (`service.py`, 170 LOC). Audit M-01 (`allow_redirects=False`)
is preserved verbatim with a dedicated test pin
(`tests/test_security_ripestat_redirect_guard.py`). The `_shim_get_json`
proxy in `ripestat.py:32-43` is the best implementation of the late-binding
pattern across the four new packages. Pure-function `normalize.py` (53 LOC)
is correctly isolated from the I/O layer.

**Why not A.**
* `ripestat.py:198-207` carries over MED-11 from the previous review verbatim
  — the `d.get("peers_seeing") or d.get("visibility", {}).get("peers_seeing")
  if isinstance(d.get("visibility"), dict) else None` chain. The wave-3
  refactor was the right time to fix it; it was preserved instead.
* `normalize.py:30-33` carries over LOW-5 (dead branch — both arms of the
  ASN range check return the identical tuple).
* `ripestat.py:290` `import time as _time` inside function body — NIT-10
  carry-over from the previous review.
* Module is 440 LOC, second-largest in the backend after `app_factory.py`.
  Per-endpoint isolation under `ripestat/` would let each fetcher be tested
  in isolation against a recorded fixture.

### `backend/route_map_analysis/` — Grade: **A−**

**Strengths.** Tightest of the four packages — 3 files / 344 LOC. Clean
parser/comparator boundary: `parser.py` knows about Arista
`show running-config | json` shape; `comparator.py` knows about cross-device
peer-group merging. Both are pure functions (no I/O). The DCI vrf-block
handling in `_extract_bgp` is correctly preserved with the same nested
`_process_bgp_cmd_list` inner function the legacy module used.

**Why not A.**
* `parser.py:124-127` carries over MED-14 from the previous review (regex
  matched twice when it could be a walrus).
* No vendor sub-package — if a Cisco / Junos route-map parser is ever added,
  `parser.py` will need to grow vendor branching. The current single-file
  shape is fine for Arista-only, but the parser pack's `arista/` /
  `cisco_nxos/` precedent suggests `route_map_analysis/arista/parser.py`
  would have been the consistent layout.
* Comparator's `build_unified_bgp_full_table` is 90 lines of nested
  comprehensions inside a `defaultdict(lambda: defaultdict(dict))` — the
  legacy code's complexity carried over verbatim. A `_DeviceGroupState`
  dataclass would help future maintainers.
* No tests of `comparator.py` against an inventory mix where N01 is missing
  but N02 is present (the `_device_order_key` (1, h) branch). Not a refactor
  finding per se, but the legacy coverage tests document this gap.

---

## Findings (Severity-Ranked)

### HIGH

#### HIGH-1 — IDOR scoping bypass in `api_run_post_complete`

**File.** `backend/blueprints/runs_bp.py:312`.

```python
@runs_bp.route("/api/run/post/complete", methods=["POST"])
def api_run_post_complete():
    data = request.get_json(silent=True) or {}
    run_id = (data.get("run_id") or "").strip()
    device_results = data.get("device_results") or []
    store = _state_store()
    pre_run = store.get(run_id)             # ← MISSING actor=_current_actor()
    if not run_id or pre_run is None:
        return jsonify({"error": "run_id not found or expired"}), 404
```

The other three state-store reads in the same file all pass
`actor=_current_actor()`:

```
runs_bp.py:174 _state_store().set(...,  actor=_current_actor())
runs_bp.py:216 _state_store().set(...,  actor=_current_actor())
runs_bp.py:251 _state_store().set(...,  actor=_current_actor())
runs_bp.py:276 store.get(run_id, actor=_current_actor())
runs_bp.py:312 store.get(run_id)             ← BUG
runs_bp.py:422 _state_store().get(run_id, actor=_current_actor())
```

**Impact.** An attacker holding any other operator's `run_id` can complete
their PRE run by calling `/api/run/post/complete` — the response leaks the
PRE `device_results` (which contains BGP routing tables, interface state,
etc.) and persists the attacker-supplied POST `device_results` against the
victim's run. M-02 documents the threat model; this handler was missed.

**Fix.** One-line change:

```python
pre_run = store.get(run_id, actor=_current_actor())
```

Then add a regression test under `tests/` pinning that `bob`'s
`/api/run/post/complete` against `alice`'s `run_id` returns 404, mirroring
the test that already exists for `/api/run/post`.

---

### MEDIUM

#### MED-1 — Two NEW bare `except Exception: pass` introduced in `find_leaf/`

**Files.**
* `backend/find_leaf/service.py:158`
* `backend/find_leaf/strategies/cisco.py:136`

Both ported verbatim from `backend/find_leaf.py` (legacy). Neither has a
`# noqa: BLE001` marker (the codebase convention for documented broad
catches), neither logs the swallowed exception, neither narrows.

```python
# service.py:152-159
for future in as_completed(futures):
    try:
        result = future.result()
        if result is not None:
            hit = result
            break
    except Exception:        # ← no noqa, no log, no narrow
        pass
```

```python
# strategies/cisco.py:126-137
if leaf_ip and (luser or lpass):
    try:
        arp_results, arp_err = cisco_nxapi.run_commands(...)
        if not arp_err and arp_results:
            ...
    except Exception:        # ← no noqa, no log, no narrow
        pass
```

**Fix.** Two acceptable shapes — the same options offered for HIGH-1 in the
previous review:

```python
# Option A — narrow:
except (RuntimeError, OSError, ConnectionError, ValueError):
    continue

# Option B — keep broad but observable:
import logging
_log = logging.getLogger("app.find_leaf")
...
except Exception:  # noqa: BLE001 — preserve legacy first-hit-wins semantics
    _log.warning(
        "leaf-search query failed for %s",
        (dev.get("hostname") or dev.get("ip") or "?"),
        exc_info=True,
    )
    continue
```

Wave-3 was the right time to do this; it was deferred to "audit M-09".
Track explicitly so the next wave doesn't ship without it.

#### MED-2 — `RunStateStore.update(**fields)` allows ownership-key spoofing

**File.** `backend/services/run_state_store.py:94-108`.

```python
def update(self, run_id: str, **fields: Any) -> dict | None:
    with self._lock:
        ...
        new_value = copy.deepcopy(value)
        new_value.update(fields)        # ← unfiltered merge
```

If a caller passes `_created_by_actor="..."` in `**fields`, the merge
silently overwrites the IDOR ownership marker. No call site does this today
(I grepped), but the API surface allows it.

**Fix.** Either filter at the boundary:

```python
fields.pop("_created_by_actor", None)  # actor is set-once at create time
new_value.update(fields)
```

…or accept an explicit `actor: str | None = None` argument the way `set()`
does, and refuse to update if the supplied actor doesn't match the stored
owner.

#### MED-3 — Five blueprints define their own `_actor()`; one inlines a sixth

**Files.**
* `backend/blueprints/notepad_bp.py:26`
* `backend/blueprints/transceiver_bp.py:41`
* `backend/blueprints/credentials_bp.py:35`
* `backend/blueprints/reports_bp.py:25` (returns `"anonymous"` for missing)
* `backend/blueprints/inventory_bp.py:32`
* `backend/blueprints/runs_bp.py:36` (`_current_actor()` — returns `None`)
* `backend/blueprints/reports_bp.py:102-111` (inlined try/except defensive
  re-implementation)

**Fix.** Promote one shared helper. The `None`-vs-`"anonymous"` divergence
is what produced HIGH-1 above (when a blueprint author uses `_actor()` for
audit logging, they pass `"anonymous"`; when they use `_current_actor()` for
run-state scoping, they pass `None` to disable scoping). Standardising both
behaviours in one helper makes the IDOR pattern visible.

```python
# backend/blueprints/_actor_helpers.py
from flask import g

def actor_for_audit() -> str:
    """Return the authenticated actor, or 'anonymous' for log lines."""
    return str(getattr(g, "actor", None) or "anonymous")

def actor_for_scoping() -> str | None:
    """Return the authenticated actor, or None to disable IDOR scoping."""
    actor = getattr(g, "actor", None)
    if not actor or actor == "anonymous":
        return None
    return str(actor)
```

#### MED-4 — `_try_one_firewall` returns `tuple[bool, bool]` with un-obvious semantics

**File.** `backend/nat_lookup/service.py:89-202`.

```python
def _try_one_firewall(...) -> tuple[bool, bool]:
    """Try a single firewall. Returns ``(handled, should_return)``.
    * handled=True means we got a definitive answer ...
    * handled=False + should_return=False means try the next firewall ...
    * handled=False + should_return=True means a debug-mode early return ...
    """
```

The call site (`if handled or should_return:`) treats them identically, so
the second flag exists only to encode "debug mode early return after parse
failure". This is a behavioural bit smuggled through the return type.

**Fix.** Either an enum:

```python
class _FwOutcome(Enum):
    SUCCESS = "success"
    HARD_ERROR = "hard_error"      # was (True, True)
    DEBUG_EARLY_RETURN = "debug_early_return"  # was (False, True)
    TRY_NEXT = "try_next"          # was (False, False)
```

…or rename to `(success, stop_iteration)` so the call site reads
`if outcome.success or outcome.stop_iteration:`.

#### MED-5 — `nat_lookup/__init__.py` carries 8 `# noqa: F401` markers + module-level `import requests`

**File.** `backend/nat_lookup/__init__.py:46-65`.

The shim re-exports `requests` as a module attribute purely so that
`patch.object(backend.nat_lookup.requests, "get", ...)` works. This is
documented in the docstring (lines 50-53) but it's the heaviest of the four
shims and the only one that imports `requests` for re-export rather than
actual use.

**Fix.** Acceptable as-is — the late-binding pattern needs `requests` to be
a module attribute, and the docstring justifies it. Future cleanup (when
all `patch.object(nl.requests, ...)` tests migrate to `patch("requests.get")`
or use `responses` / `httpretty`) would let the shim drop ~8 LOC.

#### MED-6 — Zero logging in any of the four new packages

**Files.** All of `backend/find_leaf/`, `backend/nat_lookup/`,
`backend/bgp_looking_glass/`, `backend/route_map_analysis/`.

Grepping `import logging|getLogger|_log\.` returns **zero matches**. The
`bgp_looking_glass/http_client.py:_get_json` returns `{"_error": "..."}`
envelopes (LOW-4 from previous review, carried over). `nat_lookup/service.py`
returns `out["error"] = ...` strings. `find_leaf/service.py` swallows
exceptions silently.

**Fix.** Add `_log = logging.getLogger("app.<package>")` at the top of each
module that has a non-trivial failure mode (HTTP call, vendor API parse,
silent except). Use `_log.warning(...)` for operator-actionable errors,
`_log.debug(...)` for observable-on-demand parser failures.

#### MED-7 — Wave-3 doubled the importers of private `backend.runners.runner._get_credentials`

Carry-over from previous review's LOW-3, now MEDIUM because the count
doubled (3 → 6) and the new packages all reach in directly. See "Top 5"
item #5 for the rename suggestion. Track in
`docs/refactor/wave3_roadmap.md` follow-ups.

---

### LOW

#### LOW-1 — `find_leaf/__init__.py:38-74` re-implements vendor dispatch instead of moving it to `strategies/__init__.py`

**File.** `backend/find_leaf/__init__.py:38-74`.

The shim's `_query_one_leaf_search` and `_complete_find_leaf_from_hit`
wrappers do `if vendor == "arista": ... elif vendor == "cisco": ...`. This
is dispatch logic, not re-export. Moving them under `strategies/` would
keep the shim purely declarative.

#### LOW-2 — `bgp_looking_glass/normalize.py:30-33` dead branch carry-over (LOW-5 from previous review)

```python
if 1 <= num < 4200000000 and (num < 64512 or num > 65534):
    return (f"AS{num}", "asn")
return (f"AS{num}", "asn")  # still return, let API validate
```

Both branches return identical tuples. Carried over verbatim from legacy.
Wave-3 was the right time to drop the conditional.

#### LOW-3 — `bgp_looking_glass/ripestat.py:198-207` operator-precedence chain (MED-11 carry-over)

```python
seeing = (
    d.get("peers_seeing") or d.get("visibility", {}).get("peers_seeing")
    if isinstance(d.get("visibility"), dict)
    else None
)
```

Carried over verbatim. The fix from the previous review is unchanged:

```python
vis = d.get("visibility") if isinstance(d.get("visibility"), dict) else {}
seeing = d.get("peers_seeing") or vis.get("peers_seeing")
total = d.get("total_peers") or vis.get("total_peers")
```

#### LOW-4 — `route_map_analysis/parser.py:124-127` regex run twice (MED-14 carry-over)

```python
if group_override and re.match(r"neighbor\s+(\S+)\s+", k, re.I):
    m = re.match(r"neighbor\s+(\S+)\s+", k, re.I)
    if m:
        neighbor_to_group[m.group(1)] = group_override
```

Walrus consolidation:

```python
if group_override and (m := re.match(r"neighbor\s+(\S+)\s+", k, re.I)):
    neighbor_to_group[m.group(1)] = group_override
```

#### LOW-5 — `nat_lookup/service.py` `out["error"]` overwritten on every loop iteration

**File.** `backend/nat_lookup/service.py:147-274`.

When two firewalls both fail with different reasons (FW1: connection
failed, FW2: parse failed), the user sees only FW2's message. Carried over
from legacy. Worth either accumulating errors into a list or returning
the first error (which would mirror the parser-pack pattern of "first
diagnostic wins").

---

### NIT

#### NIT-1 — `transceiver_bp.py:35` uses `_log = logging.getLogger("app.audit")` instead of `_audit`

Every other blueprint that uses the audit channel names the logger
`_audit`; `transceiver_bp.py` calls it `_log` and reserves `_log_err` for
non-audit errors. The convention divergence makes a grep for "audit log
sites" miss this file.

#### NIT-2 — `bgp_looking_glass/ripestat.py:290` `import time as _time` inside function

NIT-10 carry-over. Pull to module level.

#### NIT-3 — Wave-3 shim docstrings use `Phase 8 of the wave-3 refactor` — refresh after migration completes

Cosmetic. Same suggestion as NIT-1 from the previous review for the parser
pack.

#### NIT-4 — `route_map_analysis/parser.py` is Arista-specific but the package name is vendor-agnostic

If a Cisco or Junos route-map parser is ever needed, the file will need
vendor branching. Track as a refactor follow-up; not actionable today.

---

## Test Seam Verification — `rebuild_token_snapshot`

**File.** `backend/app_factory.py:300-310`.

```python
def rebuild_token_snapshot(_app: Flask = app) -> None:
    """Re-resolve tokens from current env/config into a fresh frozen snapshot.

    Test-only seam: production code never calls this. ...
    """
    new_snap = _MappingProxyType(dict(_resolve_tokens()))
    _app.extensions["pergen"]["token_snapshot"] = new_snap

pergen_ext["rebuild_token_snapshot"] = rebuild_token_snapshot
```

**Verdict: production-safe.** The function:
* Has no parameters that an HTTP request can reach (the `_app` default-arg
  binds to the create_app `app` at definition time).
* Is only registered as an extension entry, NOT exposed via any blueprint
  route — grep confirms zero `request.get_json` or `route(...)` reference.
* The output snapshot is `MappingProxyType`-wrapped, preserving the H-06
  immutability invariant.
* The docstring says "Test-only seam: production code never calls this."

**One soft concern:** The function is a `pergen_ext["..."]` entry, which is
a loosely-typed dict. Any blueprint that imports
`current_app.extensions["pergen"]["rebuild_token_snapshot"]` and calls it
inside a request would re-read `os.environ`, defeating H-06. Today no
blueprint does this. Suggest renaming to `_rebuild_token_snapshot_for_tests`
(double-underscore not needed; single-leading-underscore + the docstring
make the intent explicit) so a future grep makes the misuse obvious.

NIT-grade improvement; not blocking.

---

## `RunStateStore.deepcopy` Performance

**File.** `backend/services/run_state_store.py`.

`get()`, `set()`, and `update()` each call `copy.deepcopy(value)` while
holding `self._lock`. The lock is an `RLock`, so re-entry is fine, but
deepcopy of a large `device_results` payload (e.g. 50 devices × 30 commands
× ~5KB raw output ≈ 7.5MB) blocks every other reader for the duration of
the copy.

Wave-3 did not change this — it's the same hot path the previous review
called out implicitly under H6. The new `actor` parameter does not change
the cost (the `_created_by_actor` key is a single string).

**Recommendation.** Out of scope for this review. Track in a separate
follow-up: either (a) shallow-copy the top-level dict and document that
nested values are owned by the store, or (b) move the deepcopy outside the
lock for read paths (`set()` must keep it inside). No NEW perf risk
introduced by wave-3.

---

## `pytest.ini` filterwarnings — credential_store deprecation

**File.** `pytest.ini:20-23`.

```ini
filterwarnings =
    ignore::DeprecationWarning:urllib3.*
    ignore::DeprecationWarning:paramiko.*
    ignore::ResourceWarning
    # Wave-3 Phase 6 — backend.credential_store is intentionally
    # deprecation-flagged for the migration window; ignore in tests so
    # CI doesn't see a noisy DeprecationWarning per import.
    ignore::DeprecationWarning:backend.credential_store
```

Verified: `backend/credential_store.py:36-43` emits the matching warning at
module-import time. The filter is correctly scoped to the `backend.credential_store`
module — ad-hoc tests that import `backend.credential_store` directly still
exercise the warning path; production callers (every blueprint and
`runner.py`) trigger it at first import, which is when the deprecation log
should fire (H-4 from the previous review tracks the migration).

**Note.** The deprecation suppression should be **time-limited**. Once
`docs/refactor/credential_store_migration.md` lands and all 7 caller sites
move to `app.extensions["credential_service"]`, the filter and the legacy
module both go away. Suggest annotating the `pytest.ini` line with a target
removal date or the PR number that will close the migration:

```ini
# Wave-3 Phase 6 — remove with PR closing credential_store_migration.md
ignore::DeprecationWarning:backend.credential_store
```

---

## Closing Notes

Wave-3 successfully replicated the wave-2 parser refactor playbook for four
more god modules. The discipline carried forward:

* **Phase 8 documentation** in every shim docstring naming the wave and
  pointing to `docs/refactor/wave3_roadmap.md`.
* **Verbatim behaviour preservation** — every legacy private symbol is
  re-exported, every `unittest.mock.patch("backend.<module>.<sym>", ...)`
  patch target keeps working through the shim.
* **Audit-ID annotations** — H-1, H-6, H7, M-01, M-02, M-09 all cited at
  the relevant code sites with one-line justifications.
* **Late-binding-through-shim pattern** is documented and used consistently
  across `find_leaf`, `nat_lookup`, `bgp_looking_glass`. The
  `_shim_get_json` proxy in `ripestat.py` is the cleanest implementation
  and a candidate template for the other two.
* **HIGH-3 (Cisco envelope unwrap)** was applied — the dedicated
  `parsers/common/cisco_envelope.py:cisco_unwrap_body` deduplicates 5
  identical 8-line preambles into a single import.
* **HIGH-1 (parser bare-except)** held — every previously-flagged
  `except Exception` in `backend/parsers/` is now narrowed.

The two structural concerns introduced by wave-3 are tractable:

1. **HIGH-1 (the IDOR bypass at `runs_bp.py:312`)** is a one-line fix and
   should land before the next release.
2. **MED-1 / MED-6 (zero logging + 2 new bare excepts in `find_leaf/`)**
   are paired follow-ups: when audit M-09 (parallel cancel) is addressed,
   add the missing logger at the same time.

Everything else is non-blocking polish or carry-over from the previous
review (LOW-3, LOW-5, MED-11, NIT-10) that wave-3 explicitly deferred per
`wave3_roadmap.md`.

**Approve with one HIGH fix.**

---

## Wave-7 follow-up (2026-04-23)

Wave-4 HIGH-1 (`api_run_post_complete` IDOR scoping bypass) closed in
wave-4 (`docs/refactor/DONE_wave4_followups.md`); the wave-7 review
re-confirmed the fix is intact via `tests/test_security_run_post_complete_actor_scoping.py`.

Wave-4 MEDIUM carry-overs **still open** in wave-7:

- **MED-1** — duplicated `_actor()` / `_current_actor()` across 6 blueprints. Promoted to wave-7 review's MED-1 (top-of-list).
- **MED-2** — `RunStateStore.update(**fields)` ownership-marker spoof. Wave-7 MED-2.
- **MED-1 + MED-6** — two NEW bare excepts in `find_leaf/` (no `noqa`, no log). Wave-7 MED-3.
- **MED-7** — private `_get_credentials` reach-through (now 6 importers). Wave-7 MED-7. The wave-7 v2 fall-through bridge in `credential_store.py` makes the rename to `get_credentials_from_store` a low-risk cleanup.

Wave-4 LOW carry-overs **still open** in wave-7 — see `DONE_python_review_2026-04-23-wave7.md` §3.4.

Wave-4 NIT carry-overs **still open** — same.

The wave-4 closing observation that the IDOR bypass was "exactly the
kind of finding the actor-scoping wave was designed to prevent" recurs
in wave-7 review's MED-1 — until the unified `_actor_helpers.py`
promotion lands, the same class of regression remains tractable for any
new blueprint route that follows the wrong template.

Cross-reference: `docs/code-review/DONE_python_review_2026-04-23-wave7.md`.

— end of follow-up note —
