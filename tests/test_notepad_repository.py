"""
TDD tests for ``backend.repositories.notepad_repository.NotepadRepository``.

The repository owns the shared notepad JSON file that lives in
``<instance_path>/notepad.json``.  Behaviour mirrors the
``_load_notepad_data`` / ``_save_notepad_data`` helpers in
``backend/app.py`` (kept untouched until phase 9).

Contract
--------
* ``NotepadRepository(notepad_dir)`` — explicit directory injection.
* ``repo.load()`` returns ``{"content": str, "line_editors": [str, ...]}``.
* ``repo.save(content, line_editors)`` writes JSON, normalises CRLF/CR
  to LF, and pads the line-editor list to match the line count.
* ``repo.update(content, user)`` is the editor-tracking PUT operation:
  unchanged lines keep the previous editor; new/changed lines record
  the supplied user.  Returns the new ``{content, line_editors}``.
* If neither ``notepad.json`` nor ``notepad.txt`` exist, ``load()``
  returns the empty default ``{"content": "", "line_editors": []}``.
* If ``notepad.txt`` exists (legacy flat-text store) but no JSON file
  exists, the txt file is read and editors default to empty strings.
"""
from __future__ import annotations

import json
import os

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture()
def repo(tmp_path):
    from backend.repositories.notepad_repository import NotepadRepository

    return NotepadRepository(notepad_dir=str(tmp_path))


def test_load_returns_default_when_no_files(repo):
    assert repo.load() == {"content": "", "line_editors": []}


def test_save_then_load_round_trip(repo):
    repo.save("line1\nline2", ["alice", "bob"])
    data = repo.load()
    assert data["content"] == "line1\nline2"
    assert data["line_editors"] == ["alice", "bob"]


def test_save_normalises_crlf(repo):
    repo.save("a\r\nb\rc", ["x", "y", "z"])
    data = repo.load()
    assert data["content"] == "a\nb\nc"


def test_save_pads_editors_to_line_count(repo):
    repo.save("a\nb\nc\nd", ["only-one"])
    data = repo.load()
    assert data["line_editors"] == ["only-one", "", "", ""]


def test_load_falls_back_to_legacy_txt(tmp_path):
    from backend.repositories.notepad_repository import NotepadRepository

    txt = tmp_path / "notepad.txt"
    txt.write_text("hello\nworld", encoding="utf-8")
    repo = NotepadRepository(notepad_dir=str(tmp_path))
    data = repo.load()
    assert data["content"] == "hello\nworld"
    assert data["line_editors"] == ["", ""]


def test_update_marks_changed_lines_with_user(repo):
    repo.save("a\nb\nc", ["u1", "u1", "u1"])
    new = repo.update("a\nB\nc", "u2")
    assert new["content"] == "a\nB\nc"
    assert new["line_editors"] == ["u1", "u2", "u1"]


def test_update_handles_added_lines(repo):
    repo.save("a", ["u1"])
    new = repo.update("a\nb", "u2")
    assert new["content"] == "a\nb"
    assert new["line_editors"] == ["u1", "u2"]


def test_update_handles_empty_user(repo):
    """Empty user falls back to the dash sentinel — same behaviour as the
    legacy /api/notepad PUT helper."""
    new = repo.update("hello", "")
    assert new["line_editors"] == ["—"]


def test_save_writes_valid_json(tmp_path):
    from backend.repositories.notepad_repository import NotepadRepository

    repo = NotepadRepository(notepad_dir=str(tmp_path))
    repo.save("a\nb", ["u", "v"])
    raw = json.loads((tmp_path / "notepad.json").read_text(encoding="utf-8"))
    assert raw["content"] == "a\nb"
    assert raw["line_editors"] == ["u", "v"]


def test_load_creates_directory_if_needed(tmp_path):
    from backend.repositories.notepad_repository import NotepadRepository

    nested = tmp_path / "instance" / "deep"
    repo = NotepadRepository(notepad_dir=str(nested))
    repo.save("a", ["u"])
    assert os.path.isdir(nested)
    assert repo.load()["content"] == "a"
