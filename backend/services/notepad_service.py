"""
``NotepadService`` — façade over the notepad repository.
"""
from __future__ import annotations

from backend.repositories import NotepadRepository


class NotepadService:
    """Shared-notepad operations."""

    def __init__(self, notepad_repo: NotepadRepository) -> None:
        self._repo = notepad_repo

    def get(self) -> dict:
        return self._repo.load()

    def update(self, content: str, user: str) -> dict:
        return self._repo.update(content, user)
