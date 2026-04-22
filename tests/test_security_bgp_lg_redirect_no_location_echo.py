"""W4-M-05 — `_get_json` redirect error envelope echoes upstream `Location`.

Wave-4 audit §3.2 W4-M-05. The ``_get_json`` helper in
``backend/bgp_looking_glass/http_client.py`` returns:

    {"_error": f"refused redirect from {url} → {r.headers.get('Location')!r}"}

The ``Location`` header is attacker-controllable in any MITM /
DNS-spoof / cache-poison scenario. While the realistic exploit
chain requires compromising the upstream RIPEStat HTTPS, the
defence-in-depth fix is to NOT echo the header.

This is the contract pin: a redirect response must produce an
opaque error envelope that does not include the upstream Location.
Marked xfail until the helper drops the {Location!r} interpolation.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.security]


def test_get_json_redirect_error_does_not_echo_location() -> None:
    """The Location header value must not appear in the response body."""
    from backend.bgp_looking_glass import http_client

    poison = "https://attacker.example/path?xss=<script>"

    class _Resp:
        status_code = 302
        headers = {"Location": poison}

        def raise_for_status(self):  # pragma: no cover - never called
            pass

        def json(self):  # pragma: no cover - never called
            return {}

    with patch.object(http_client.requests, "get", return_value=_Resp()):
        out = http_client._get_json("https://stat.ripe.net/data/x")

    assert isinstance(out, dict)
    err = out.get("_error", "")
    assert "attacker.example" not in err, (
        f"upstream Location echoed in error envelope — see W4-M-05: {err!r}"
    )
    assert "<script>" not in err
