# Refactor: `backend/parse_output.py` → `backend/parsers/` package

**Status:** Phase 0 (baseline established, no production code changes yet)
**Plan:** see this document — the 8-phase plan is captured below.
**Owner:** opencode session (Claude Opus 4.7) — see git log for incremental commits.

---

## Goal

Split the 1,552-line `backend/parse_output.py` god-module into a cohesive,
vendor- and domain-organised `backend/parsers/` package while preserving
**byte-identical** parser output (28 golden snapshots) and **100%** of the
existing public + private import surface (back-compat shim).

## Non-Goals

- No behavior changes (snapshot diffs are STOP-and-investigate signals).
- No new third-party dependencies.
- No re-baselining of existing golden fixtures.
- Other deferred items (credential_store, token_gate, /health, /router-devices,
  audit logger, CSP/HSTS, SPA auth, XSS sweep) are tracked in sibling docs in
  this directory and explicitly out of scope here.

---

## Phase 0 — Baseline (this commit)

### Test baseline

| Suite                                       | Tests | Status |
|---------------------------------------------|-------|--------|
| `tests/golden/test_parsers_golden.py`       | 22    | PASS   |
| `tests/test_legacy_coverage_parse_output.py`| 43    | PASS   |
| `tests/test_parse_arista_interface_status.py`| 3    | PASS   |
| `tests/test_parse_cisco_interface_detailed.py`| 1   | PASS   |
| `tests/test_parser_engine.py`               | 10    | PASS   |
| **Parser-touching total**                   | **79**| **PASS**|
| **Full suite (`pytest -q`)**                | **852 + 9 xfail** | **PASS** |

### Coverage baseline (lock — must not regress)

| Module                          | Stmts | Cover |
|---------------------------------|-------|-------|
| `backend/parse_output.py`       | 1222  | **53%**|
| `backend/parsers/engine.py`     |   33  | 90%   |
| `backend/parsers/__init__.py`   |    2  | 100%  |
| **Total parser surface**        | 1257  | **54%**|

> **Acceptance criterion** for every subsequent phase: running the same
> 5 suites must yield 79 passes and combined parser-surface coverage ≥ 54%.

### Function inventory (49 symbols to relocate)

Captured by `grep -n '^def \|^class ' backend/parse_output.py`. Full mapping
to target modules is below in **Target Layout**.

### Import-site audit

| Caller                                          | Symbols imported (private + public)                            |
|-------------------------------------------------|----------------------------------------------------------------|
| `backend/runners/runner.py:6`                   | whole module (`as parse_output_module`)                        |
| `backend/find_leaf.py:9`                        | whole module                                                   |
| `backend/parsers/engine.py:26`                  | `parse_output as _legacy_parse_output`                         |
| `backend/runners/interface_recovery.py:84`      | **private**: `_parse_arista_interface_status`                  |
| `tests/golden/test_parsers_golden.py`           | 18 private parsers + `parse_output`                            |
| `tests/test_legacy_coverage_parse_output.py`    | `parse_output`, 5 public arp/bgp/suppression fns, 3 private helpers (`_count_from_json`, `_get_path`, `_extract_regex`) |
| `tests/test_parse_arista_interface_status.py`   | `_parse_arista_interface_status`, `_parse_relative_seconds_ago`|
| `tests/test_parse_cisco_interface_detailed.py`  | `_parse_cisco_interface_detailed`                              |

**Total external import sites:** 8 files, 73 import statements.
**Conclusion:** the back-compat shim must preserve at minimum these 30
symbols (18 private parsers + 3 private helpers + 5 public functions +
`parse_output` + ~3 internal helpers used by tests indirectly).

### Public API to preserve (must remain importable from `backend.parse_output`)

```
parse_output
parse_arista_bgp_evpn_next_hop
parse_arista_arp_interface_for_ip
parse_arp_suppression_for_ip
parse_arp_suppression_asci
parse_cisco_arp_interface_for_ip
```

### Private API to preserve (used by tests / `interface_recovery.py`)

```
_parse_arista_uptime         _parse_cisco_system_uptime
_parse_arista_cpu            _parse_cisco_isis_interface_brief
_parse_arista_disk           _parse_cisco_power
_parse_arista_power          _parse_cisco_nxos_transceiver
_parse_arista_isis_adjacency _parse_cisco_interface_status
_parse_arista_transceiver    _parse_cisco_interface_show_mtu
_parse_arista_interface_status     _parse_cisco_interface_detailed
_parse_arista_interface_description _parse_cisco_interface_description
_parse_relative_seconds_ago  _count_from_json   _get_path   _extract_regex
```

---

## Target Layout (delivered across Phases 1–7)

```
backend/parsers/
├── __init__.py                  # public re-exports
├── engine.py                    # ParserEngine (already exists)
├── dispatcher.py                # NEW — replaces parse_output() if/elif ladder
├── common/
│   ├── __init__.py
│   ├── json_path.py             # _get_path, _flatten_nested_list, _find_key,
│   │                            # _find_key_containing, _find_list, _get_val
│   ├── counters.py              # _count_from_json, _count_where,
│   │                            # _get_from_dict_by_key_prefix
│   ├── regex_helpers.py         # _extract_regex, _count_regex_lines
│   ├── formatting.py            # _apply_value_subtract_and_suffix,
│   │                            # _format_power_two_decimals
│   ├── duration.py              # _parse_relative_seconds_ago,
│   │                            # _parse_hhmmss_to_seconds
│   └── arista_envelope.py       # _arista_result_obj, _arista_result_to_dict
├── arista/
│   ├── __init__.py
│   ├── uptime.py                # _parse_arista_uptime
│   ├── cpu.py                   # _parse_arista_cpu
│   ├── disk.py                  # _parse_arista_disk
│   ├── power.py                 # _parse_arista_power
│   ├── transceiver.py           # _parse_arista_transceiver
│   ├── interface_status.py      # _parse_arista_interface_status (+
│   │                            # _parse_arista_interface_status_from_table,
│   │                            # _arista_get_interface_counters_dict,
│   │                            # _arista_in_and_crc_from_counters)
│   ├── interface_description.py # _parse_arista_interface_description
│   ├── isis.py                  # _parse_arista_isis_adjacency,
│   │                            # _find_arista_isis_adjacency_list
│   ├── arp.py                   # parse_arista_arp_interface_for_ip
│   └── bgp.py                   # parse_arista_bgp_evpn_next_hop
├── cisco_nxos/
│   ├── __init__.py
│   ├── system_uptime.py         # _parse_cisco_system_uptime
│   ├── power.py                 # _parse_cisco_power
│   ├── transceiver.py           # _parse_cisco_nxos_transceiver (+
│   │                            # _cisco_find_tx_rx_in_dict,
│   │                            # _cisco_transceiver_tx_rx_from_row)
│   ├── interface_status.py      # _parse_cisco_interface_status
│   ├── interface_detailed.py    # _parse_cisco_interface_detailed
│   ├── interface_mtu.py         # _parse_cisco_interface_show_mtu
│   ├── interface_description.py # _parse_cisco_interface_description
│   ├── isis_brief.py            # _parse_cisco_isis_interface_brief,
│   │                            # _find_isis_interface_brief_rows
│   ├── arp.py                   # parse_cisco_arp_interface_for_ip,
│   │                            # _get_cisco_arp_rows,
│   │                            # _parse_cisco_arp_ascii_for_ip
│   └── arp_suppression.py       # parse_arp_suppression_for_ip,
│                                # parse_arp_suppression_asci,
│                                # _get_arp_suppression_entries_list
└── generic/
    └── field_engine.py          # the "fields" loop from parse_output()
```

`backend/parse_output.py` will shrink to a **~50-line shim** with explicit
re-exports preserving every name in the public + private API tables above.

---

## Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Snapshot drift (any subtle dict-ordering / int-vs-float / None-vs-"" diff) | **HIGH** | Never edit a parser body during the move. Copy verbatim, run snapshots, only refactor with snapshots green. |
| Hidden cross-function coupling (`parse_arp_suppression_for_ip` calls `parse_arp_suppression_asci`; `_parse_arista_interface_status` calls helpers) | **HIGH** | Co-locate tightly-coupled helpers in the same submodule. |
| Test patch targets break (any `monkeypatch.setattr("backend.parse_output._foo", ...)` site) | **MEDIUM** | Shim contract test (`tests/test_parse_output_shim.py`) imports + asserts every legacy symbol resolves to the **moved** implementation. |
| Private import from `interface_recovery.py:84` | **MEDIUM** | Pinned in shim contract test. |
| Circular imports (`engine.py` ↔ `dispatcher.py` post-Phase 6) | **MEDIUM** | Dispatcher must not import engine; engine constructs its own dispatcher. |
| Test discovery for `tests/parsers/` subtree | **LOW** | `pytest.ini` already has `testpaths = tests`; new `__init__.py` files added per phase. |

---

## Phase Map

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Baseline + import audit + shim contract test | **DONE** |
| 1 | Common utilities (json_path, counters, regex, duration, formatting, arista_envelope) | **DONE** |
| 2 | Arista vendor parsers (10 modules) | **DONE** |
| 3 | Cisco NX-OS vendor parsers (10 modules) | **DONE** |
| 4 | Generic field engine extraction | **DONE** |
| 5 | Vendor-routed dispatcher (registry pattern) | **DONE** |
| 6 | `ParserEngine` integration update | **DONE** |
| 7 | Final shim shrink | **DONE** (151 LOC) |
| 8 | Verification + final docs update | **DONE** (this commit) |

---

## Final Metrics

### LOC

| Surface | Before | After | Delta |
|---------|--------|-------|-------|
| `backend/parse_output.py` | 1552 | **151** | **−90%** (now a back-compat shim) |
| `backend/parsers/common/` | 0 | 462 | new (6 modules) |
| `backend/parsers/arista/` | 0 | 584 | new (10 modules) |
| `backend/parsers/cisco_nxos/` | 0 | 852 | new (10 modules) |
| `backend/parsers/generic/` | 0 | 142 | new (1 module) |
| `backend/parsers/dispatcher.py` | 0 | 134 | new |
| `backend/parsers/engine.py` | 111 | 117 | +6 (lazy-import → direct dispatcher) |
| **Total parser surface** | 1663 | 2442 | +47% (mostly explanatory docstrings + smaller modules) |

The line-count expansion is intentional — every new file ships with
module-level docstrings and `__all__` exports that make the parser
surface self-documenting. Net **production-logic** LOC is essentially
flat; the legacy file simply concentrated everything in one place.

### Tests

| Suite | Before | After | Delta |
|-------|--------|-------|-------|
| Parser-touching | 79 | **355** | +276 (new unit tests for every utility + dispatcher + field engine) |
| Full repo (`pytest -q`) | 852 passing + 9 xfail | **1128 passing + 9 xfail** | +276 (no xfail flips, no regressions) |

### Coverage (parser surface)

| Module                                       | Cover Before | Cover After |
|----------------------------------------------|--------------|-------------|
| `backend/parse_output.py`                    | 53%          | **100%** (now a shim) |
| `backend/parsers/engine.py`                  | 90%          | 91%        |
| `backend/parsers/dispatcher.py`              | —            | **100%**   |
| `backend/parsers/common/*`                   | —            | 87–100%    |
| `backend/parsers/generic/field_engine.py`    | —            | 93%        |
| `backend/parsers/arista/*`                   | —            | 24–100% (golden-snapshot coverage) |
| `backend/parsers/cisco_nxos/*`               | —            | 17–77% (golden-snapshot coverage) |
| **Combined**                                 | 54%          | **67%** (+13 pp) |

The vendor-parser modules show varying coverage because the golden
snapshots stress-test the happy path; the lower-coverage branches are
the edge-case "find the field anywhere in this NX-API blob" recovery
paths. The shim contract test + unit tests for common helpers + parity
tests for the dispatcher cover the structural invariants.

### Risks Encountered & Mitigated

| Risk | Manifestation | Mitigation Applied |
|------|---------------|--------------------|
| Snapshot drift | None — all 28 golden snapshots byte-identical at every phase gate | "Copy verbatim, never edit" discipline held |
| Hidden cross-function coupling | `_parse_arista_interface_status` calls 3 helpers; ARP suppression `_for_ip` calls `_asci` | Co-located in same submodule per planner guidance |
| Test patch targets break | `tests/test_parser_engine.py` patches `_legacy_parse_output`; `tests/golden/...` patches `backend.parse_output.time.time` | Preserved both symbols in the shim/engine; lazy trampoline kept in `engine.py` |
| Circular import (`engine` ↔ `parse_output`) | Hit during Phase 2 when `parse_output` started importing from `backend.parsers.arista.*` | Moved engine→legacy import behind a lazy trampoline; broken in Phase 6 by routing engine to dispatcher directly |
| `interface_recovery.py` private import | None — pinned by shim contract test | `_parse_arista_interface_status` re-exported in shim |

---

## Migration Guide for New Code

After this refactor, prefer the new module paths:

```python
# OLD — still works via the back-compat shim
from backend.parse_output import _parse_arista_uptime, parse_output

# NEW — preferred
from backend.parsers.arista.uptime import _parse_arista_uptime
from backend.parsers.dispatcher import Dispatcher
result = Dispatcher().parse(command_id, raw_output, parser_config)
```

Adding a new vendor parser:

1. Create `backend/parsers/<vendor>/<domain>.py` with a
   `_parse_<vendor>_<domain>(raw_output) -> dict` callable.
2. Add an entry to `_DEFAULT_REGISTRY` in
   `backend/parsers/dispatcher.py:42`.
3. Add a unit test under `tests/parsers/<vendor>/` and (optionally) a
   golden snapshot under `tests/fixtures/golden/`.
4. The new parser is automatically reachable via
   `Dispatcher().parse()` and (transitively) via
   `backend.parse_output.parse_output()`.

## Shim Removal Schedule

The back-compat shim (`backend/parse_output.py`) is intended to remain
in place for at least one full release cycle, then be removed once
every in-tree caller has migrated. Tracking removal:

* [ ] Migrate `backend/runners/runner.py:6` to import from
      `backend.parsers.dispatcher`
* [ ] Migrate `backend/find_leaf.py:9` to import from
      `backend.parsers.cisco_nxos.arp_suppression` etc.
* [ ] Migrate `backend/runners/interface_recovery.py:84` to
      `backend.parsers.arista.interface_status`
* [ ] Migrate the 7 test files that import from `backend.parse_output`
      to import from the new locations
* [ ] Add `DeprecationWarning` to the shim
* [ ] One release cycle later: delete `backend/parse_output.py`

Each phase: write tests first (RED) → copy verbatim into new module (GREEN) →
update shim re-export (REFACTOR) → run full 5-suite gate → only then proceed.
