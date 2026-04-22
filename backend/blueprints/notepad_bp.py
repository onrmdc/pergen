"""
Notepad Blueprint — replaces the legacy ``/api/notepad`` GET / PUT / POST
routes from ``backend/app.py``.

The Blueprint is a pure pass-through to ``NotepadService`` (registered
into ``app.extensions["notepad_service"]`` by the factory).  No file IO
or line-attribution logic lives here — the service / repository pair
owns persistence.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from flask import Blueprint, current_app, jsonify, request

if TYPE_CHECKING:  # pragma: no cover
    from backend.services.notepad_service import NotepadService

notepad_bp = Blueprint("notepad", __name__)
_log = logging.getLogger("app.blueprints.notepad")

# Phase 13: hard cap on a single notepad write.  At ~512 KB any legitimate
# operator note is well within scope; anything beyond that is either a
# misuse or a denial-of-service attempt.
_MAX_NOTEPAD_BYTES: Final[int] = 512_000


def _svc() -> NotepadService:
    svc = current_app.extensions.get("notepad_service")
    if svc is None:
        raise RuntimeError("notepad_service not registered; call create_app first")
    return svc


@notepad_bp.route("/api/notepad", methods=["GET"])
def api_notepad_get():
    """Return shared notepad: ``{content, line_editors}``."""
    data = _svc().get()
    return jsonify({"content": data["content"], "line_editors": data["line_editors"]})


@notepad_bp.route("/api/notepad", methods=["PUT", "POST"])
def api_notepad_put():
    """Update notepad. Body: ``{content, user}``.

    Tracks last editor per line via :class:`NotepadService.update`.
    Returns the freshly persisted state (same shape as GET).
    """
    data = request.get_json(silent=True) or {}
    content = data.get("content")
    user = (data.get("user") or "").strip() or "—"
    if content is None:
        return jsonify({"error": "content required"}), 400
    if not isinstance(content, str):
        content = str(content)
    if len(content) > _MAX_NOTEPAD_BYTES:
        # Phase 13: bound payload size to prevent disk-fill DoS.
        return jsonify({"error": "content exceeds maximum size"}), 413
    try:
        result = _svc().update(content, user)
    except (OSError, ValueError):
        _log.exception("notepad update failed")
        return jsonify({"error": "failed to save"}), 500
    return jsonify(
        {"content": result["content"], "line_editors": result["line_editors"]}
    )
