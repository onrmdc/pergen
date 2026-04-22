"""
Commands & Parsers Blueprint.

Phase-4 deliverable. Replaces the legacy ``api_commands``,
``api_parsers_fields``, and ``api_parser`` routes from
``backend/app.py``.

These three routes are pure pass-throughs to ``commands_loader`` —
no service or repository is required, so the blueprint is the
thinnest possible OOD layer (just transport translation).
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from backend.config import commands_loader as cmd_loader

commands_bp = Blueprint("commands", __name__)


@commands_bp.route("/api/commands", methods=["GET"])
def api_commands():
    """Commands applicable to a device. Query: ``vendor``, ``model``, ``role``."""
    vendor = (request.args.get("vendor") or "").strip()
    model = (request.args.get("model") or "").strip()
    role = (request.args.get("role") or "").strip()
    return jsonify({"commands": cmd_loader.get_commands_for_device(vendor, model, role)})


@commands_bp.route("/api/parsers/fields", methods=["GET"])
def api_parsers_fields():
    """All parser field names (for dynamic table columns)."""
    return jsonify({"fields": cmd_loader.get_all_parser_field_names()})


@commands_bp.route("/api/parsers/<command_id>", methods=["GET"])
def api_parser(command_id: str):
    """Parser config for a command id; 404 when unknown."""
    cfg = cmd_loader.get_parser(command_id)
    if cfg is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(cfg)
