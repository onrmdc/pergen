"""
SSRF-hardened HTTP fetcher for the BGP Looking Glass.

Audit M-01 (``allow_redirects=False``) is preserved verbatim from the original
``backend/bgp_looking_glass.py::_get_json``. Do not change the redirect-refusal
contract without re-running the security review (see
``docs/security/audit_2026-04-22.md`` §3.2 M-01 and
``tests/test_security_ripestat_redirect_guard.py``).

The hostname pin is enforced at the call-site by using only the hard-coded
``RIPESTAT_BASE`` / ``PEERINGDB_NET`` constants — there is no operator-supplied
URL path here.
"""

from __future__ import annotations

import requests

__all__ = [
    "RIPESTAT_BASE",
    "PEERINGDB_NET",
    "DEFAULT_TIMEOUT",
    "_get_json",
]

RIPESTAT_BASE = "https://stat.ripe.net/data"
PEERINGDB_NET = "https://www.peeringdb.com/api/net"
DEFAULT_TIMEOUT = 12


def _get_json(
    url: str, params: dict | None = None, timeout: int = DEFAULT_TIMEOUT
) -> dict | None:
    """Fetch JSON from a known LG endpoint with SSRF defences.

    Audit M-01: ``allow_redirects=False`` so a 302 from upstream cannot
    redirect us to an internal IP (e.g. cloud-metadata 169.254.169.254).
    The hostname pin is enforced at the call-site by using only the
    hard-coded RIPESTAT_BASE / PEERINGDB_BASE constants — there is no
    operator-supplied URL path here.
    """
    try:
        r = requests.get(
            url,
            params=params or {},
            timeout=timeout,
            allow_redirects=False,  # audit M-01 — SSRF-via-redirect defence
        )
        # Treat any redirect as a hard failure: a legitimate stat.ripe.net
        # / peeringdb.com response is always 200 with the JSON body inline.
        # Wave-4 W4-M-05: do NOT echo the upstream Location header — it is
        # attacker-controllable in any MITM/DNS-spoof scenario and could
        # land XSS payload in the JSON response body.
        if 300 <= r.status_code < 400:
            return {
                "_error": f"refused redirect from upstream (HTTP {r.status_code})"
            }
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as e:
        return {"_error": str(e)[:200]}
