"""
Pergen repositories — persistence-only classes that own a single
data source and expose a tight interface for the service layer.

Each repository:

* Receives its dependencies via ``__init__`` (paths, encryption services,
  …) — no module-level globals, no implicit Flask-app coupling.
* Speaks in domain dicts (``device``, ``credential``, ``report``,
  ``notepad``) — never in raw SQL rows or open file handles.
* Is thread-safe at the file / DB level (file rewrite operations are
  guarded; SQLite uses a fresh connection per call).
* Holds no business logic — the service layer (phase 8) composes
  repositories with runners and parsers.
"""
from backend.repositories.credential_repository import CredentialRepository
from backend.repositories.inventory_repository import InventoryRepository
from backend.repositories.notepad_repository import NotepadRepository
from backend.repositories.report_repository import ReportRepository

__all__ = [
    "CredentialRepository",
    "InventoryRepository",
    "NotepadRepository",
    "ReportRepository",
]
