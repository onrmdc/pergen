"""
Phase-4 tests — commands & parsers blueprint extraction.

Routes ``/api/commands``, ``/api/parsers/fields``, ``/api/parsers/<id>``
move from ``backend/app.py`` into ``backend/blueprints/commands_bp.py``.
The blueprint is a thin pass-through to ``backend.config.commands_loader``
so no service is required.
"""
from __future__ import annotations

import pytest as _pytest_for_marker  # noqa: F401

pytestmark = [_pytest_for_marker.mark.integration]


def test_commands_route_returns_list(client):
    r = client.get("/api/commands?vendor=arista&model=eos&role=Leaf")
    assert r.status_code == 200
    body = r.get_json()
    assert "commands" in body
    assert isinstance(body["commands"], list)


def test_commands_route_works_without_filters(client):
    r = client.get("/api/commands")
    assert r.status_code == 200
    assert isinstance(r.get_json()["commands"], list)


def test_parsers_fields_returns_dict(client):
    r = client.get("/api/parsers/fields")
    assert r.status_code == 200
    body = r.get_json()
    assert "fields" in body


def test_parser_returns_404_for_unknown_command_id(client):
    r = client.get("/api/parsers/__no_such_command_id__")
    assert r.status_code == 404
    assert "not found" in r.get_json()["error"].lower()


def test_parser_returns_known_command(client):
    """Any known parser id returns its config (200) or 404 — never 5xx."""
    from backend.config import commands_loader as cmd_loader

    all_cmds = cmd_loader.get_commands_for_device("arista", "eos", "Leaf")
    if not all_cmds:
        return  # nothing to probe in this environment
    cmd = all_cmds[0]
    cid = cmd.get("command_id") or cmd.get("id") or next(iter(cmd.values()), None)
    if not isinstance(cid, str):
        return
    r = client.get(f"/api/parsers/{cid}")
    assert r.status_code in (200, 404)


def test_commands_routes_owned_by_commands_blueprint(flask_app):
    expected = {
        ("GET", "/api/commands"),
        ("GET", "/api/parsers/fields"),
        ("GET", "/api/parsers/<command_id>"),
    }
    seen = set()
    for rule in flask_app.url_map.iter_rules():
        for method in rule.methods or ():
            if (method, rule.rule) in expected:
                view = flask_app.view_functions[rule.endpoint]
                assert view.__module__ == "backend.blueprints.commands_bp", (
                    f"{method} {rule.rule} dispatches to {view.__module__}"
                )
                seen.add((method, rule.rule))
    assert seen == expected, f"missing: {expected - seen}"
