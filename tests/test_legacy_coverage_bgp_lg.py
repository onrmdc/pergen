"""
Coverage push for ``backend/bgp_looking_glass.py``.

Mocks ``requests.get`` at the module boundary so every RIPEStat /
PeeringDB / RPKI Validator call is deterministic.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


def _resp(json_payload, status=200):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = json_payload
    m.raise_for_status = MagicMock()
    if status >= 400:
        m.raise_for_status.side_effect = Exception(f"http {status}")
    return m


# --------------------------------------------------------------------------- #
# normalize_resource                                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw,expected_kind,expected_value",
    [
        ("13335", "asn", "AS13335"),
        ("AS13335", "asn", "AS13335"),
        ("as13335", "asn", "AS13335"),
        ("1.1.1.0/24", "prefix", "1.1.1.0/24"),
        ("AS9121", "asn", "AS9121"),
    ],
)
def test_normalize_resource(raw, expected_kind, expected_value):
    from backend.bgp_looking_glass import normalize_resource

    # Implementation returns (resource, kind), not (kind, resource)
    resource, kind = normalize_resource(raw)
    assert kind == expected_kind
    assert resource == expected_value


def test_normalize_resource_bare_ipv4_gets_default_prefix():
    from backend.bgp_looking_glass import normalize_resource

    resource, kind = normalize_resource("1.1.1.0")
    assert kind == "prefix"
    assert resource == "1.1.1.0/24"


def test_normalize_resource_passes_through_unknown():
    from backend.bgp_looking_glass import normalize_resource

    resource, kind = normalize_resource("garbage")
    assert kind == "prefix"  # pass-through; API will reject


# --------------------------------------------------------------------------- #
# get_bgp_status                                                              #
# --------------------------------------------------------------------------- #


def test_get_bgp_status_returns_full_envelope_for_prefix():
    from backend import bgp_looking_glass as bgp_lg

    routing_status = {"data": {"announced": True, "first_seen": {"time": "2020-01-01"}}}
    rpki = {"data": {"validating_roas": [{"asn": "AS13335", "max_length": 24}]}}
    asoverview = {"data": {"holder": "CLOUDFLARE", "is_less_specific": False}}
    pdb = {
        "data": [
            {"name": "Cloudflare Inc.", "website": "https://cloudflare.com"}
        ]
    }
    routing_history = {"data": {"by_origin": []}}

    def fake_get(url, params=None, timeout=None, **_):
        if "routing-status" in url:
            return _resp(routing_status)
        if "rpki-validation" in url:
            return _resp(rpki)
        if "as-overview" in url:
            return _resp(asoverview)
        if "peeringdb" in url or "net" in url:
            return _resp(pdb)
        if "routing-history" in url:
            return _resp(routing_history)
        return _resp({"data": {}})

    with patch("backend.bgp_looking_glass.requests.get", side_effect=fake_get):
        out = bgp_lg.get_bgp_status("1.1.1.0/24")
    assert "announced" in out
    assert isinstance(out, dict)


def test_get_bgp_status_handles_failure_gracefully():
    import requests

    from backend import bgp_looking_glass as bgp_lg

    with patch(
        "backend.bgp_looking_glass.requests.get",
        side_effect=requests.RequestException("connection refused"),
    ):
        out = bgp_lg.get_bgp_status("AS13335")
    # Function must return a dict envelope even when upstream fails.
    assert isinstance(out, dict)


def test_get_bgp_status_invalid_resource_short_circuits():
    from backend import bgp_looking_glass as bgp_lg

    out = bgp_lg.get_bgp_status("not-a-real-resource")
    assert "error" in out or "resource" in out


# --------------------------------------------------------------------------- #
# get_bgp_history / visibility / looking_glass                                 #
# --------------------------------------------------------------------------- #


def test_get_bgp_history_returns_dict():
    from backend import bgp_looking_glass as bgp_lg

    payload = {"data": {"by_origin": [{"origin": "13335", "timelines": []}]}}
    with patch(
        "backend.bgp_looking_glass.requests.get", return_value=_resp(payload)
    ):
        out = bgp_lg.get_bgp_history("AS13335")
    assert isinstance(out, dict)


def test_get_bgp_visibility_returns_dict():
    from backend import bgp_looking_glass as bgp_lg

    payload = {"data": {"sources": [{"id": "rrc00", "rrc": "rrc00"}]}}
    with patch(
        "backend.bgp_looking_glass.requests.get", return_value=_resp(payload)
    ):
        out = bgp_lg.get_bgp_visibility("1.1.1.0/24")
    assert isinstance(out, dict)


def test_get_bgp_looking_glass_returns_dict():
    from backend import bgp_looking_glass as bgp_lg

    payload = {
        "data": {
            "rrcs": [
                {"rrc": "rrc00", "peers": [{"asn_origin": "13335"}]}
            ]
        }
    }
    with patch(
        "backend.bgp_looking_glass.requests.get", return_value=_resp(payload)
    ):
        out = bgp_lg.get_bgp_looking_glass("1.1.1.0/24")
    assert isinstance(out, dict)


def test_get_bgp_looking_glass_handles_invalid_response():
    from backend import bgp_looking_glass as bgp_lg

    with patch(
        "backend.bgp_looking_glass.requests.get",
        return_value=_resp({"data": {}}),
    ):
        out = bgp_lg.get_bgp_looking_glass("AS13335")
    assert isinstance(out, dict)


# --------------------------------------------------------------------------- #
# get_bgp_play                                                                 #
# --------------------------------------------------------------------------- #


def test_get_bgp_play_no_time_window():
    from backend import bgp_looking_glass as bgp_lg

    payload = {"data": {"events": []}}
    with patch(
        "backend.bgp_looking_glass.requests.get", return_value=_resp(payload)
    ):
        out = bgp_lg.get_bgp_play("1.1.1.0/24")
    assert isinstance(out, dict)


def test_get_bgp_play_with_iso_times():
    from backend import bgp_looking_glass as bgp_lg

    with patch(
        "backend.bgp_looking_glass.requests.get",
        return_value=_resp({"data": {"events": []}}),
    ):
        out = bgp_lg.get_bgp_play(
            "1.1.1.0/24", starttime="2024-01-01T00:00:00", endtime="2024-01-02T00:00:00"
        )
    assert isinstance(out, dict)


def test_get_bgp_play_with_unix_times():
    from backend import bgp_looking_glass as bgp_lg

    with patch(
        "backend.bgp_looking_glass.requests.get",
        return_value=_resp({"data": {"events": []}}),
    ):
        out = bgp_lg.get_bgp_play("AS13335", starttime="1700000000", endtime="1700100000")
    assert isinstance(out, dict)


def test_get_bgp_play_handles_failure():
    import requests

    from backend import bgp_looking_glass as bgp_lg

    with patch(
        "backend.bgp_looking_glass.requests.get",
        side_effect=requests.RequestException("timeout"),
    ):
        out = bgp_lg.get_bgp_play("AS13335")
    assert isinstance(out, dict)


# --------------------------------------------------------------------------- #
# get_bgp_as_info / announced_prefixes                                         #
# --------------------------------------------------------------------------- #


def test_get_bgp_as_info_returns_dict():
    from backend import bgp_looking_glass as bgp_lg

    pdb = {"data": [{"name": "Cloudflare", "website": "https://cloudflare.com"}]}
    asoverview = {"data": {"holder": "CLOUDFLARE", "is_less_specific": False}}

    def fake(url, params=None, timeout=None, **_):
        if "peeringdb" in url:
            return _resp(pdb)
        return _resp(asoverview)

    with patch("backend.bgp_looking_glass.requests.get", side_effect=fake):
        out = bgp_lg.get_bgp_as_info("13335")
    assert isinstance(out, dict)


def test_get_bgp_announced_prefixes_returns_dict():
    from backend import bgp_looking_glass as bgp_lg

    payload = {"data": {"prefixes": [{"prefix": "1.1.1.0/24"}]}}
    with patch(
        "backend.bgp_looking_glass.requests.get", return_value=_resp(payload)
    ):
        out = bgp_lg.get_bgp_announced_prefixes("13335")
    assert isinstance(out, dict)


def test_get_bgp_announced_prefixes_handles_failure():
    import requests

    from backend import bgp_looking_glass as bgp_lg

    with patch(
        "backend.bgp_looking_glass.requests.get",
        side_effect=requests.RequestException("boom"),
    ):
        out = bgp_lg.get_bgp_announced_prefixes("13335")
    assert isinstance(out, dict)


# --------------------------------------------------------------------------- #
# Internal helper edge cases                                                   #
# --------------------------------------------------------------------------- #


def test_normalize_resource_handles_whitespace():
    from backend.bgp_looking_glass import normalize_resource

    resource, kind = normalize_resource("   13335  ")
    assert kind == "asn"
    assert resource == "AS13335"


def test_normalize_resource_empty_input():
    from backend.bgp_looking_glass import normalize_resource

    resource, kind = normalize_resource("")
    assert resource == ""
    assert kind == ""


def test_get_bgp_status_with_asn_input():
    from backend import bgp_looking_glass as bgp_lg

    with patch(
        "backend.bgp_looking_glass.requests.get",
        return_value=_resp({"data": {}}),
    ):
        out = bgp_lg.get_bgp_status("AS13335")
    assert isinstance(out, dict)
