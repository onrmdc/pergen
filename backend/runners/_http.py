"""
Shared HTTP posture for device-facing requests.

All HTTPS traffic to **network devices** (Arista eAPI, Cisco NX-API, Palo Alto
XML API, etc.) is sent with TLS verification disabled because devices ship
local self-signed certificates that have no path to a public CA.

This module is the single source of truth for that posture so every device
runner uses the same constant and the ``InsecureRequestWarning`` chatter is
suppressed exactly once at import time.

DO NOT use ``DEVICE_TLS_VERIFY`` for calls to public APIs (e.g. RIPE,
PeeringDB). Those endpoints have valid CA-signed certificates and MUST keep
default ``verify=True``.
"""
from __future__ import annotations

# Public constant: device HTTPS calls intentionally skip TLS verification.
# Network devices in this fleet present self-signed certificates.
DEVICE_TLS_VERIFY: bool = False

# Suppress urllib3's InsecureRequestWarning exactly once. Any module that
# imports DEVICE_TLS_VERIFY also picks up this side effect, so individual
# runners don't need their own try/except blocks.
try:
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:  # pragma: no cover - urllib3 always present via requests
    pass
