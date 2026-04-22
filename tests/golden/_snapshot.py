"""
Tiny self-recording snapshot helper for characterization (golden) tests.

Why
---
Phase 1 of the OOD + TDD refactor must lock in current behaviour before any
code is moved.  Hand-writing expected outputs for ~20 parsers and ~60 routes
is error-prone, so we let the *current* implementation produce them once and
freeze the result on disk.

How it works
------------
* Every snapshot is a JSON file under ``tests/fixtures/golden/<name>.json``.
* On first run (or whenever ``PERGEN_REGEN_GOLDEN=1``), the helper writes the
  observed payload and the test passes — that file is then committed to the
  repo and becomes the "frozen" expectation.
* On subsequent runs, the helper deep-compares the observed payload to the
  on-disk snapshot and fails on any drift.

Refactor workflow
-----------------
1. Run the test suite once on the *current* code with ``PERGEN_REGEN_GOLDEN=1``
   to generate snapshots — they get committed in this same Phase 1 commit.
2. From Phase 2 onward, ``PERGEN_REGEN_GOLDEN`` stays unset so any behavioural
   drift caused by the refactor surfaces as a snapshot diff.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

GOLDEN_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "golden"
_REGEN_FLAG = "PERGEN_REGEN_GOLDEN"


def _path(name: str) -> Path:
    safe = name.replace("/", "__").replace("\\", "__")
    if not safe.endswith(".json"):
        safe += ".json"
    return GOLDEN_ROOT / safe


def _normalize(value: Any) -> Any:
    """Recursively convert sets, tuples, and bytes into JSON-friendly forms.

    Order matters for snapshots, so dict keys are NOT sorted (the parsers
    currently rely on insertion order)."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, set):
        return sorted(_normalize(v) for v in value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return repr(value)


def assert_matches_snapshot(name: str, payload: Any) -> None:
    """Assert *payload* equals the snapshot at ``tests/fixtures/golden/<name>.json``.

    Auto-creates the snapshot the first time, or whenever the env flag is set.
    Use a hierarchical name (``parsers/arista_uptime``) — slashes become
    folder separators when written, but stay readable in failure messages."""
    snap_path = _path(name)
    observed = _normalize(payload)
    serialised = json.dumps(observed, indent=2, ensure_ascii=False)

    regen = os.environ.get(_REGEN_FLAG) == "1"
    if not snap_path.exists() or regen:
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text(serialised + "\n", encoding="utf-8")
        return

    expected_text = snap_path.read_text(encoding="utf-8").rstrip("\n")
    if expected_text != serialised:
        raise AssertionError(
            f"Snapshot mismatch for {name!r}\n"
            f"  file: {snap_path}\n"
            f"--- expected ---\n{expected_text}\n"
            f"--- observed ---\n{serialised}\n"
            f"Re-run with {_REGEN_FLAG}=1 if the change is intentional."
        )
