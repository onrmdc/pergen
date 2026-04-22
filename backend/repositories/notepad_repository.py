"""
``NotepadRepository`` — shared notepad persistence.

Owns ``<notepad_dir>/notepad.json`` (and falls back to a legacy
``notepad.txt`` if only the flat-text version exists).  Mirrors the
``_load_notepad_data`` / ``_save_notepad_data`` / PUT-update logic from
``backend/app.py`` so phase-9 service extraction is a no-op.
"""
from __future__ import annotations

import json
import logging
import os
import threading

_log = logging.getLogger("app.repository.notepad")

_DEFAULT_USER = "—"


class NotepadRepository:
    """File-backed repository for the shared notepad."""

    def __init__(self, notepad_dir: str) -> None:
        """
        Inputs
        ------
        notepad_dir : directory containing ``notepad.json``
            (and optionally a legacy ``notepad.txt``).

        Outputs
        -------
        ``NotepadRepository`` instance.

        Security
        --------
        Notepad text is treated as user-supplied content and is *not*
        sanitised here — sanitisation belongs at the route boundary.
        """
        self._dir = notepad_dir
        # Audit M-06: RLock (not Lock) lets a future contributor wire
        # ``_save_unlocked`` back to ``save()`` without hard-deadlocking
        # the worker. Re-entry on the same thread costs ~1 ns extra but
        # eliminates a sharp edge nobody wants to debug at 3am.
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # paths
    # ------------------------------------------------------------------ #
    def _ensure_dir(self) -> None:
        os.makedirs(self._dir, exist_ok=True)

    def _json_path(self) -> str:
        return os.path.join(self._dir, "notepad.json")

    def _txt_path(self) -> str:
        return os.path.join(self._dir, "notepad.txt")

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    def load(self) -> dict:
        """Return ``{"content": str, "line_editors": [str, ...]}``."""
        jpath = self._json_path()
        tpath = self._txt_path()

        if os.path.isfile(jpath):
            try:
                with open(jpath, encoding="utf-8") as f:
                    data = json.load(f)
                content = (data.get("content") or "").replace("\r\n", "\n").replace("\r", "\n")
                editors = data.get("line_editors")
                if not isinstance(editors, list):
                    editors = []
                lines = content.split("\n")
                while len(editors) < len(lines):
                    editors.append("")
                return {"content": content, "line_editors": editors[: len(lines)]}
            except Exception as exc:  # pragma: no cover - defensive
                _log.warning("notepad.json unreadable, falling back: %s", exc)

        if os.path.isfile(tpath):
            try:
                with open(tpath, encoding="utf-8") as f:
                    content = f.read().replace("\r\n", "\n").replace("\r", "\n")
                lines = content.split("\n")
                return {"content": content, "line_editors": [""] * len(lines)}
            except Exception as exc:  # pragma: no cover - defensive
                _log.warning("notepad.txt unreadable: %s", exc)

        return {"content": "", "line_editors": []}

    def save(self, content: str, line_editors: list[str]) -> None:
        """Persist content + per-line editors (LF-normalised, padded).

        Note: callers that already hold ``self._lock`` (e.g. ``update``)
        re-acquire safely because this method only opens a file under the
        lock.  See ``_save_unlocked`` for the lock-free variant used by
        ``update``.
        """
        with self._lock:
            self._save_unlocked(content, line_editors)

    def _save_unlocked(self, content: str, line_editors: list[str]) -> None:
        content = (content or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = content.split("\n")
        editors = list(line_editors or [])[: len(lines)]
        while len(editors) < len(lines):
            editors.append("")

        self._ensure_dir()
        with open(self._json_path(), "w", encoding="utf-8") as f:
            json.dump({"content": content, "line_editors": editors}, f, ensure_ascii=False)

    def update(self, content: str, user: str) -> dict:
        """
        Apply an edit, attributing changed/added lines to ``user``.

        Inputs
        ------
        content : new full notepad text.
        user : display name of the editor (``"—"`` if blank).

        Outputs
        -------
        ``{"content": str, "line_editors": [str, ...]}`` — the freshly
        persisted state.

        Security
        --------
        ``user`` is whitespace-stripped; empty values fall back to the
        ``"—"`` sentinel so the audit column is never blank.
        """
        content = (content or "").replace("\r\n", "\n").replace("\r", "\n")
        editor = (user or "").strip() or _DEFAULT_USER

        # Phase 13: lock the entire load → diff → save cycle to close the
        # TOCTOU race two concurrent PUT /api/notepad calls used to expose.
        # Previously a second writer could read state between the first
        # writer's load() and save(), losing per-line editor attribution.
        with self._lock:
            old = self.load()
            old_lines = (old["content"] or "").split("\n")
            old_editors = list(old["line_editors"] or [])

            new_lines = content.split("\n")
            new_editors: list[str] = []
            for i, new_line in enumerate(new_lines):
                if i < len(old_lines) and old_lines[i] == new_line and i < len(old_editors):
                    new_editors.append(old_editors[i] or "")
                else:
                    new_editors.append(editor)
            self._save_unlocked(content, new_editors)
        return {"content": content, "line_editors": new_editors}
