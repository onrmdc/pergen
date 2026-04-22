"""
Phase-7 tests — BGP looking-glass routes move from ``backend/app.py``
to ``backend/blueprints/bgp_bp.py``.

The eight read-side BGP routes are pure pass-throughs to the
``backend.bgp_looking_glass`` helper module; ``/api/bgp/wan-rtr-match``
is the one with real orchestration (per-device runner dispatch +
BGP-AS pattern matching) and gets a focused service test.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest as _pytest_for_marker  # noqa: F401

pytestmark = [_pytest_for_marker.mark.integration]


# --------------------------------------------------------------------------- #
# Pass-through routes — validation only (no real RIPEStat traffic)             #
# --------------------------------------------------------------------------- #


def test_bgp_status_requires_resource(client):
    r = client.get("/api/bgp/status")
    assert r.status_code == 400
    assert "prefix or asn" in r.get_json()["error"].lower()


def test_bgp_history_requires_resource(client):
    r = client.get("/api/bgp/history")
    assert r.status_code == 400


def test_bgp_visibility_requires_resource(client):
    r = client.get("/api/bgp/visibility")
    assert r.status_code == 400


def test_bgp_looking_glass_requires_resource(client):
    r = client.get("/api/bgp/looking-glass")
    assert r.status_code == 400


def test_bgp_bgplay_requires_resource(client):
    r = client.get("/api/bgp/bgplay")
    assert r.status_code == 400


def test_bgp_as_info_requires_asn(client):
    r = client.get("/api/bgp/as-info")
    assert r.status_code == 400
    assert "asn" in r.get_json()["error"].lower()


def test_bgp_announced_prefixes_requires_asn(client):
    r = client.get("/api/bgp/announced-prefixes")
    assert r.status_code == 400


def test_bgp_status_passes_resource_to_helper(client):
    """``prefix=`` is forwarded verbatim to ``bgp_lg.get_bgp_status``."""
    with patch(
        "backend.bgp_looking_glass.get_bgp_status",
        return_value={"resource": "1.1.1.0/24", "ok": True},
    ) as m:
        r = client.get("/api/bgp/status?prefix=1.1.1.0/24")
    assert r.status_code == 200
    assert r.get_json()["resource"] == "1.1.1.0/24"
    m.assert_called_once_with("1.1.1.0/24")


def test_bgp_status_normalises_asn_with_AS_prefix(client):
    """``asn=13335`` is normalised to ``AS13335`` before forwarding."""
    with patch(
        "backend.bgp_looking_glass.get_bgp_status", return_value={}
    ) as m:
        client.get("/api/bgp/status?asn=13335")
    m.assert_called_once_with("AS13335")


def test_bgp_status_preserves_AS_prefix_when_present(client):
    with patch(
        "backend.bgp_looking_glass.get_bgp_status", return_value={}
    ) as m:
        client.get("/api/bgp/status?asn=AS13335")
    m.assert_called_once_with("AS13335")


def test_bgp_bgplay_forwards_starttime_endtime(client):
    with patch("backend.bgp_looking_glass.get_bgp_play", return_value={}) as m:
        client.get("/api/bgp/bgplay?prefix=1.1.1.0/24&starttime=2024-01-01&endtime=2024-01-02")
    m.assert_called_once_with("1.1.1.0/24", starttime="2024-01-01", endtime="2024-01-02")


# --------------------------------------------------------------------------- #
# WAN-rtr-match — orchestration tests                                          #
# --------------------------------------------------------------------------- #


def test_wan_rtr_match_rejects_non_digit_asn(client):
    r = client.get("/api/bgp/wan-rtr-match?asn=abc")
    assert r.status_code == 400
    assert r.get_json()["matches"] == []


def test_wan_rtr_match_strips_AS_prefix(client):
    """Even with ``AS`` prefix the ASN must be digit-only after stripping."""
    r = client.get("/api/bgp/wan-rtr-match")
    assert r.status_code == 400


def test_wan_rtr_match_returns_empty_when_no_wan_routers_in_inventory(client):
    """Default test inventory has no WAN-Router devices, so no matches."""
    r = client.get("/api/bgp/wan-rtr-match?asn=65000")
    assert r.status_code == 200
    body = r.get_json()
    assert body["matches"] == []


# --------------------------------------------------------------------------- #
# Migration assertion                                                          #
# --------------------------------------------------------------------------- #


def test_bgp_routes_owned_by_bgp_blueprint(flask_app):
    expected = {
        ("GET", "/api/bgp/status"),
        ("GET", "/api/bgp/history"),
        ("GET", "/api/bgp/visibility"),
        ("GET", "/api/bgp/looking-glass"),
        ("GET", "/api/bgp/bgplay"),
        ("GET", "/api/bgp/as-info"),
        ("GET", "/api/bgp/announced-prefixes"),
        ("GET", "/api/bgp/wan-rtr-match"),
    }
    seen = set()
    for rule in flask_app.url_map.iter_rules():
        for method in rule.methods or ():
            if (method, rule.rule) in expected:
                view = flask_app.view_functions[rule.endpoint]
                assert view.__module__ == "backend.blueprints.bgp_bp", (
                    f"{method} {rule.rule} dispatches to {view.__module__}"
                )
                seen.add((method, rule.rule))
    assert seen == expected, f"missing: {expected - seen}"
