"""M-01 — RIPEStat / PeeringDB outbound calls have no redirect or IP allow-list.

Without `allow_redirects=False`, a 302 from the upstream could send the
client to an internal IP (e.g. `169.254.169.254` cloud metadata). The
existing host-pin test (`test_security_bgp_routes_pin_ripestat_host.py`)
covers the constant but not the live request behaviour.

Audit reference: ``docs/security/audit_2026-04-22.md`` §3.2 M-01.

Desired contract: redirect responses are not followed. XFAIL until the
`_safe_get` helper lands.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.security]


@pytest.mark.xfail(
    reason="audit M-01 — bgp_looking_glass.requests.get follows redirects by default",
    strict=True,
)
def test_ripestat_call_does_not_follow_redirects() -> None:
    """A 302 from RIPEStat must not be auto-followed to an internal endpoint."""
    from backend import bgp_looking_glass as lg

    captured: dict = {}

    def _fake_get(url, *args, **kwargs):
        captured["url"] = url
        captured["allow_redirects"] = kwargs.get("allow_redirects", True)

        class _R:
            status_code = 302
            headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
            text = ""

            def json(self):
                return {}

        return _R()

    with patch.object(lg.requests, "get", _fake_get):
        try:
            lg.get_bgp_status("AS13335")  # public RIPEStat lookup
        except Exception:
            pass  # internal handling is fine — we care about the request shape

    assert captured.get("allow_redirects") is False, (
        "bgp_looking_glass must call requests.get with allow_redirects=False "
        "to avoid SSRF via 302 to internal IPs"
    )
