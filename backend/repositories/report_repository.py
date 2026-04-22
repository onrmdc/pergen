"""
``ReportRepository`` — persistence for pre/post check reports.

Each report is a gzipped JSON document under
``<reports_dir>/<safe-id>.json.gz`` and an entry in
``<reports_dir>/index.json`` (newest-first, capped at 200 entries).

Behaviour mirrors the ``_persist_report`` / ``_load_report`` /
``_delete_report`` helpers currently in ``backend/app.py`` so phase-9
service extraction is a no-op for callers.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import threading
from typing import Any

_log = logging.getLogger("app.repository.report")

_INDEX_CAP = 200


class ReportRepository:
    """File-backed repository for pre/post check reports."""

    def __init__(self, reports_dir: str) -> None:
        """
        Inputs
        ------
        reports_dir : directory that holds ``<id>.json.gz`` and
            ``index.json``.  Created lazily on first write.

        Outputs
        -------
        ``ReportRepository`` instance.

        Security
        --------
        ``run_id`` is sanitised on every operation — slashes/backslashes
        become underscores so attackers cannot escape ``reports_dir``.
        """
        self._reports_dir = reports_dir
        self._lock = threading.Lock()

    @property
    def reports_dir(self) -> str:
        return self._reports_dir

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    def save(
        self,
        run_id: str,
        name: str,
        created_at: str,
        devices: list[dict],
        device_results: list[dict],
        post_created_at: str | None = None,
        post_device_results: list[dict] | None = None,
        comparison: dict | None = None,
    ) -> None:
        """Persist the report payload and update the index."""
        self._ensure_dir()
        path = self._report_path(run_id)
        payload: dict[str, Any] = {
            "run_id": run_id,
            "name": name or "pre_report",
            "created_at": created_at,
            "devices": devices,
            "device_results": device_results,
            "post_created_at": post_created_at,
            "post_device_results": post_device_results,
            "comparison": comparison,
        }
        with self._lock:
            with gzip.open(path, "wt", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            self._upsert_index(
                {
                    "run_id": run_id,
                    "name": name or "pre_report",
                    "created_at": created_at,
                    "post_created_at": post_created_at,
                }
            )

    def load(self, run_id: str) -> dict | None:
        """Return the full payload dict or None if no such report exists."""
        path = self._report_path(run_id)
        if not os.path.isfile(path):
            return None
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:  # pragma: no cover - defensive
            _log.warning("failed to load report %s: %s", run_id, exc)
            return None

    def delete(self, run_id: str) -> bool:
        """Remove the report file and its index entry.  Returns True iff
        the file existed (parity with old ``_delete_report`` behaviour)."""
        path = self._report_path(run_id)
        existed = os.path.isfile(path)
        with self._lock:
            if existed:
                try:
                    os.remove(path)
                except OSError as exc:  # pragma: no cover - defensive
                    _log.warning("failed to remove report %s: %s", run_id, exc)
            entries = self._load_index()
            new_entries = [e for e in entries if (e.get("run_id") or "") != (run_id or "")]
            if new_entries != entries:
                self._save_index(new_entries)
        return existed

    def list(self) -> list[dict]:
        """Return the report index (newest first, capped at 200)."""
        return self._load_index()[:_INDEX_CAP]

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _ensure_dir(self) -> None:
        os.makedirs(self._reports_dir, exist_ok=True)

    def _safe_id(self, run_id: str) -> str:
        # Phase 13 hardening: belt-and-suspenders — strip path separators,
        # NUL bytes, and leading dots so that even after URL-decoding the
        # resulting filename cannot escape ``self._reports_dir`` via
        # ``..`` traversal sequences.
        #
        # Audit M-05: refuse empty/whitespace ``run_id`` instead of
        # silently coercing to literal "default" — two distinct callers
        # passing an empty id would otherwise overwrite the same file.
        if not (run_id or "").strip():
            raise ValueError("run_id is required and must be non-empty")
        safe = (
            run_id.replace("/", "_")
            .replace("\\", "_")
            .replace("\x00", "_")
            .lstrip(".")
        )
        # If the entire id collapses to dots/separators after sanitisation,
        # treat that as invalid too (e.g. ``run_id="..."`` → "" → reject).
        if not safe:
            raise ValueError(f"run_id sanitised to empty string (got {run_id!r})")
        return safe

    def _report_path(self, run_id: str) -> str:
        from pathlib import Path

        path = os.path.join(self._reports_dir, self._safe_id(run_id) + ".json.gz")
        # Audit H9 (post-Phase-13): replace string-prefix check with
        # ``pathlib.Path.is_relative_to`` so the guard is correct on
        # Windows (mixed / and \\ separators) as well as POSIX.
        # ``_safe_id`` already neuters path separators; this is the
        # belt-and-suspenders escape detector.
        abs_path = Path(path).resolve(strict=False)
        abs_root = Path(self._reports_dir).resolve(strict=False)
        try:
            if not abs_path.is_relative_to(abs_root):
                raise ValueError(
                    f"refusing report path outside reports_dir: {run_id!r}"
                )
        except AttributeError:  # pragma: no cover — Python < 3.9 fallback
            if not str(abs_path).startswith(str(abs_root) + os.sep) and abs_path != abs_root:
                raise ValueError(
                    f"refusing report path outside reports_dir: {run_id!r}"
                ) from None
        return path

    def _index_path(self) -> str:
        return os.path.join(self._reports_dir, "index.json")

    def _load_index(self) -> list[dict]:
        path = self._index_path()
        if not os.path.isfile(path):
            return []
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:  # pragma: no cover - defensive
            return []

    def _save_index(self, entries: list[dict]) -> None:
        self._ensure_dir()
        with open(self._index_path(), "w", encoding="utf-8") as f:
            json.dump(entries[:_INDEX_CAP], f, ensure_ascii=False)

    def _upsert_index(self, meta: dict) -> None:
        entries = self._load_index()
        by_id = {e.get("run_id"): i for i, e in enumerate(entries)}
        if meta["run_id"] in by_id:
            entries[by_id[meta["run_id"]]] = meta
        else:
            entries.insert(0, meta)
        self._save_index(entries)
