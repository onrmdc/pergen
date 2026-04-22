"""
BGP looking-glass helpers must only call pinned upstream hosts.

``backend/bgp_looking_glass.py`` is the only network-egress surface
that talks to a third-party API on behalf of an unauthenticated
SPA caller. A regression here (e.g. accepting a user-supplied URL,
or switching to a different upstream) widens the SSRF surface.

This test patches ``requests.get`` at the module's import site,
exercises every public helper, and asserts every URL passed to
``requests.get`` belongs to ``stat.ripe.net`` or ``www.peeringdb.com``.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import pytest

import backend.bgp_looking_glass as blg

pytestmark = [pytest.mark.security]

_ALLOWED_HOSTS = {"stat.ripe.net", "www.peeringdb.com"}


def _capture_urls(monkeypatched_get: MagicMock) -> list[str]:
    return [call.args[0] for call in monkeypatched_get.call_args_list]


def test_bgp_helpers_only_call_pinned_upstream_hosts() -> None:
    fake_resp = MagicMock()
    fake_resp.status_code = 200  # audit M-01: helper now checks for redirects
    fake_resp.json.return_value = {"data": {}}
    fake_resp.raise_for_status.return_value = None

    with patch.object(blg.requests, "get", return_value=fake_resp) as mock_get:
        # Exercise every helper that hits the network.
        blg.get_bgp_status("1.1.1.0/24")
        blg.get_bgp_history("1.1.1.0/24")
        blg.get_bgp_visibility("1.1.1.0/24")
        blg.get_bgp_looking_glass("1.1.1.0/24")
        blg.get_bgp_play("1.1.1.0/24")
        blg.get_bgp_as_info("13335")
        blg.get_bgp_announced_prefixes("13335")

    urls = _capture_urls(mock_get)
    assert urls, "expected at least one outbound request from BGP helpers"
    offenders = [u for u in urls if urlparse(u).hostname not in _ALLOWED_HOSTS]
    assert not offenders, (
        f"BGP helpers must only call {_ALLOWED_HOSTS}; offenders: {offenders!r}"
    )
