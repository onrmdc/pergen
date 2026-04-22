"""
Phase-11 tests — pre/post run + reports routes move from
``backend/app.py`` to ``backend/blueprints/runs_bp.py`` and
``backend/blueprints/reports_bp.py``.

Routes:
* runs_bp:    /api/run/device, /api/run/pre, /api/run/pre/create,
              /api/run/pre/restore, /api/run/post, /api/run/post/complete,
              /api/diff, /api/run/result/<run_id>
* reports_bp: /api/reports, /api/reports/<run_id> (GET/DELETE)

The in-memory ``_run_state`` dict moves into ``RunStateStore`` (default
in-memory impl). Diff computation moves into ``ReportService.compare_runs``.
"""
from __future__ import annotations

from unittest.mock import patch


# --------------------------------------------------------------------------- #
# /api/run/device — single device exec                                         #
# --------------------------------------------------------------------------- #


def test_run_device_requires_device_object(client):
    r = client.post("/api/run/device", json={})
    assert r.status_code == 400


def test_run_device_returns_device_result_envelope(client):
    with patch(
        "backend.blueprints.runs_bp.run_device_commands",
        return_value={"hostname": "leaf-1", "parsed_flat": {}, "commands": []},
    ):
        r = client.post(
            "/api/run/device",
            json={"device": {"hostname": "leaf-1", "ip": "10.0.0.1"}},
        )
    assert r.status_code == 200
    assert r.get_json()["device_result"]["hostname"] == "leaf-1"


# --------------------------------------------------------------------------- #
# /api/run/pre — full PRE pipeline                                             #
# --------------------------------------------------------------------------- #


def test_run_pre_requires_devices_list(client):
    r = client.post("/api/run/pre", json={"devices": []})
    assert r.status_code == 400


def test_run_pre_returns_run_id_and_results(client):
    """A successful PRE run yields a run_id, phase=PRE, and len(device_results)==len(devices)."""
    with patch(
        "backend.blueprints.runs_bp.run_device_commands",
        side_effect=lambda d, *_a, **_k: {
            "hostname": d["hostname"],
            "ip": d["ip"],
            "parsed_flat": {"Uptime": "1d"},
            "commands": [],
        },
    ):
        r = client.post(
            "/api/run/pre",
            json={
                "devices": [
                    {"hostname": "leaf-1", "ip": "10.0.0.1"},
                    {"hostname": "leaf-2", "ip": "10.0.0.2"},
                ]
            },
        )
    assert r.status_code == 200
    body = r.get_json()
    assert body["phase"] == "PRE"
    assert isinstance(body["run_id"], str)
    assert len(body["device_results"]) == 2


# --------------------------------------------------------------------------- #
# /api/run/pre/create + /api/run/post/complete — frontend-driven flow          #
# --------------------------------------------------------------------------- #


def test_run_pre_create_validates_device_results_length(client):
    r = client.post(
        "/api/run/pre/create",
        json={"devices": [{"hostname": "x", "ip": "1.1.1.1"}], "device_results": []},
    )
    assert r.status_code == 400


def test_run_pre_create_round_trip_then_post_complete(client):
    """End-to-end PRE-create → POST-complete diff comparison."""
    devices = [{"hostname": "leaf-1", "ip": "10.0.0.1"}]
    pre_results = [{"hostname": "leaf-1", "ip": "10.0.0.1", "parsed_flat": {"Uptime": "1d"}}]
    post_results = [{"hostname": "leaf-1", "ip": "10.0.0.1", "parsed_flat": {"Uptime": "2d"}}]

    r = client.post(
        "/api/run/pre/create",
        json={"devices": devices, "device_results": pre_results},
    )
    assert r.status_code == 200
    run_id = r.get_json()["run_id"]

    r2 = client.post(
        "/api/run/post/complete",
        json={"run_id": run_id, "device_results": post_results},
    )
    assert r2.status_code == 200
    body = r2.get_json()
    assert body["phase"] == "POST"
    diff = body["comparison"][0]["diff"]
    assert diff == {"Uptime": {"pre": "1d", "post": "2d"}}


def test_run_post_complete_404_for_unknown_run(client):
    r = client.post(
        "/api/run/post/complete",
        json={"run_id": "no-such-run", "device_results": [{}]},
    )
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# /api/run/pre/restore                                                         #
# --------------------------------------------------------------------------- #


def test_run_pre_restore_requires_run_id(client):
    r = client.post(
        "/api/run/pre/restore",
        json={"devices": [{"hostname": "x", "ip": "1.1.1.1"}], "device_results": [{}]},
    )
    assert r.status_code == 400


def test_run_pre_restore_validates_lengths_match(client):
    r = client.post(
        "/api/run/pre/restore",
        json={
            "run_id": "abc",
            "devices": [{"hostname": "x", "ip": "1.1.1.1"}, {"hostname": "y", "ip": "2.2.2.2"}],
            "device_results": [{}],
        },
    )
    assert r.status_code == 400


def test_run_pre_restore_succeeds_and_makes_run_lookupable(client):
    devices = [{"hostname": "leaf-1", "ip": "10.0.0.1"}]
    pre_results = [{"hostname": "leaf-1", "parsed_flat": {}}]
    r = client.post(
        "/api/run/pre/restore",
        json={"run_id": "restored-id", "devices": devices, "device_results": pre_results},
    )
    assert r.status_code == 200
    # The restored run should be retrievable
    r2 = client.get("/api/run/result/restored-id")
    assert r2.status_code == 200
    assert r2.get_json()["phase"] == "PRE"


# --------------------------------------------------------------------------- #
# /api/diff — text diff utility                                                #
# --------------------------------------------------------------------------- #


def test_diff_returns_unified_diff(client):
    r = client.post("/api/diff", json={"pre": "line1\nline2\n", "post": "line1\nLINE2\n"})
    assert r.status_code == 200
    body = r.get_json()
    assert "diff" in body
    assert "PRE" in body["diff"] and "POST" in body["diff"]


def test_diff_returns_empty_when_inputs_identical(client):
    r = client.post("/api/diff", json={"pre": "same\n", "post": "same\n"})
    assert r.status_code == 200
    assert r.get_json()["diff"] == ""


# --------------------------------------------------------------------------- #
# /api/run/result/<run_id>                                                     #
# --------------------------------------------------------------------------- #


def test_run_result_404_for_unknown(client):
    r = client.get("/api/run/result/__no_such__")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# /api/reports                                                                 #
# --------------------------------------------------------------------------- #


def test_reports_list_returns_array(client):
    r = client.get("/api/reports")
    assert r.status_code == 200
    body = r.get_json()
    assert isinstance(body["reports"], list)


def test_report_get_returns_404_for_unknown(client):
    r = client.get("/api/reports/__no_such_report__")
    assert r.status_code == 404


def test_report_get_after_pre_create_returns_payload(client):
    devices = [{"hostname": "leaf-1", "ip": "10.0.0.1"}]
    pre_results = [{"hostname": "leaf-1", "parsed_flat": {}}]
    r = client.post(
        "/api/run/pre/create",
        json={"devices": devices, "device_results": pre_results, "name": "audit-run-1"},
    )
    run_id = r.get_json()["run_id"]
    r2 = client.get(f"/api/reports/{run_id}")
    assert r2.status_code == 200
    body = r2.get_json()
    assert body["name"] == "audit-run-1"
    assert body["devices"] == devices


def test_report_delete_succeeds(client):
    devices = [{"hostname": "leaf-1", "ip": "10.0.0.1"}]
    pre_results = [{"hostname": "leaf-1", "parsed_flat": {}}]
    r = client.post(
        "/api/run/pre/create",
        json={"devices": devices, "device_results": pre_results},
    )
    run_id = r.get_json()["run_id"]
    r2 = client.delete(f"/api/reports/{run_id}")
    assert r2.status_code == 200
    assert r2.get_json()["ok"] is True


# --------------------------------------------------------------------------- #
# Service-layer unit test for compare_runs                                     #
# --------------------------------------------------------------------------- #


def test_report_service_compare_runs_emits_per_device_diff():
    from backend.repositories import ReportRepository
    from backend.services.report_service import ReportService

    svc = ReportService(ReportRepository("/tmp/_unused"))
    pre = [
        {"hostname": "leaf-1", "ip": "10.0.0.1", "parsed_flat": {"Uptime": "1d", "Load": "10"}}
    ]
    post = [
        {"hostname": "leaf-1", "ip": "10.0.0.1", "parsed_flat": {"Uptime": "2d", "Load": "10"}}
    ]
    out = svc.compare_runs(pre, post)
    assert len(out) == 1
    entry = out[0]
    assert entry["hostname"] == "leaf-1"
    assert entry["diff"] == {"Uptime": {"pre": "1d", "post": "2d"}}


# --------------------------------------------------------------------------- #
# Migration assertion                                                          #
# --------------------------------------------------------------------------- #


def test_runs_routes_owned_by_runs_blueprint(flask_app):
    expected = {
        ("POST", "/api/run/device"),
        ("POST", "/api/run/pre"),
        ("POST", "/api/run/pre/create"),
        ("POST", "/api/run/pre/restore"),
        ("POST", "/api/run/post"),
        ("POST", "/api/run/post/complete"),
        ("POST", "/api/diff"),
        ("GET", "/api/run/result/<run_id>"),
    }
    seen = set()
    for rule in flask_app.url_map.iter_rules():
        for method in rule.methods or ():
            if (method, rule.rule) in expected:
                view = flask_app.view_functions[rule.endpoint]
                assert view.__module__ == "backend.blueprints.runs_bp", (
                    f"{method} {rule.rule} dispatches to {view.__module__}"
                )
                seen.add((method, rule.rule))
    assert seen == expected, f"missing: {expected - seen}"


def test_reports_routes_owned_by_reports_blueprint(flask_app):
    expected = {
        ("GET", "/api/reports"),
        ("GET", "/api/reports/<run_id>"),
        ("DELETE", "/api/reports/<run_id>"),
    }
    seen = set()
    for rule in flask_app.url_map.iter_rules():
        for method in rule.methods or ():
            if (method, rule.rule) in expected:
                view = flask_app.view_functions[rule.endpoint]
                assert view.__module__ == "backend.blueprints.reports_bp", (
                    f"{method} {rule.rule} dispatches to {view.__module__}"
                )
                seen.add((method, rule.rule))
    assert seen == expected, f"missing: {expected - seen}"
