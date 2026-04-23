"""
Phase-5 tests — ping & SPA fallback move from ``backend/app.py`` to
``backend/blueprints/network_ops_bp.py``.

The blueprint preserves the legacy contract verbatim, including the
Phase-13 hardening:

* ``InputSanitizer.sanitize_ip`` short-circuits invalid IPs.
* ``MAX_PING_DEVICES`` cap on the request payload size.
* Each device gets up to 5 ping attempts; first success wins.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest as _pytest_for_marker  # noqa: F401

pytestmark = [_pytest_for_marker.mark.integration]


def test_ping_rejects_non_list_devices(client):
    r = client.post("/api/ping", json={"devices": "not-a-list"})
    assert r.status_code == 400
    assert "list" in r.get_json()["error"].lower()


def test_ping_rejects_oversized_payload(client):
    devices = [{"hostname": f"h{i}", "ip": "10.0.0.1"} for i in range(65)]
    r = client.post("/api/ping", json={"devices": devices})
    assert r.status_code == 400
    assert "capped" in r.get_json()["error"].lower() or "64" in r.get_json()["error"]


def test_ping_short_circuits_invalid_ip(client):
    r = client.post(
        "/api/ping",
        json={"devices": [{"hostname": "bad", "ip": "not-an-ip"}]},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["results"][0]["reachable"] is False


def test_ping_returns_reachable_true_when_single_ping_succeeds(client, monkeypatch):
    """``single_ping`` is monkey-patched to short-circuit success.

    Wave-7 follow-up: default-allow on internal addresses; no env var
    needed for RFC1918 targets to reach ``single_ping``.
    """
    monkeypatch.delenv("PERGEN_BLOCK_INTERNAL_PING", raising=False)
    with patch("backend.utils.ping.single_ping", return_value=True):
        r = client.post(
            "/api/ping",
            json={"devices": [{"hostname": "h1", "ip": "10.0.0.1"}]},
        )
    assert r.status_code == 200
    assert r.get_json()["results"][0]["reachable"] is True


def test_ping_returns_reachable_false_on_repeated_failures(client, monkeypatch):
    monkeypatch.delenv("PERGEN_BLOCK_INTERNAL_PING", raising=False)
    with patch("backend.utils.ping.single_ping", return_value=False):
        r = client.post(
            "/api/ping",
            json={"devices": [{"hostname": "h1", "ip": "10.0.0.1"}]},
        )
    assert r.status_code == 200
    assert r.get_json()["results"][0]["reachable"] is False


def test_index_route_returns_json_when_static_missing(client):
    r = client.get("/")
    # Either JSON fallback (no static) or HTML (static present); both 200
    assert r.status_code == 200


def test_network_ops_routes_owned_by_blueprint(flask_app):
    expected = {
        ("POST", "/api/ping"),
        ("GET", "/"),
    }
    seen = set()
    for rule in flask_app.url_map.iter_rules():
        for method in rule.methods or ():
            if (method, rule.rule) in expected:
                view = flask_app.view_functions[rule.endpoint]
                assert view.__module__ == "backend.blueprints.network_ops_bp", (
                    f"{method} {rule.rule} dispatches to {view.__module__}"
                )
                seen.add((method, rule.rule))
    assert seen == expected, f"missing: {expected - seen}"
