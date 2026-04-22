"""
Pergen service layer.

Phase-8 deliverable.  Each service composes one or more repositories
(phase 5), runners (phase 6), and the parser engine (phase 7) into the
use-case-shaped APIs that phase-9 routes will consume.

Services:

* ``InventoryService`` — wraps ``InventoryRepository``.
* ``CredentialService`` — wraps ``CredentialRepository`` with
  ``InputSanitizer`` validation on credential names.
* ``NotepadService`` — wraps ``NotepadRepository``.
* ``ReportService`` — wraps ``ReportRepository``.
* ``DeviceService`` — orchestrates credential lookup → runner →
  parser for one device.

All services are constructed via explicit dependency injection so
tests can supply ``MagicMock`` doubles for every collaborator.
"""
from backend.services.credential_service import CredentialService
from backend.services.device_service import DeviceService
from backend.services.inventory_service import InventoryService
from backend.services.notepad_service import NotepadService
from backend.services.report_service import ReportService
from backend.services.run_state_store import RunStateStore
from backend.services.transceiver_service import TransceiverService

__all__ = [
    "CredentialService",
    "DeviceService",
    "InventoryService",
    "NotepadService",
    "ReportService",
    "RunStateStore",
    "TransceiverService",
]
