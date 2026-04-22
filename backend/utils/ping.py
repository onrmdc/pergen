"""
ICMP ping utility — single-host probe with bounded fan-out.

Phase-2 deliverable — extracted verbatim from ``backend/app.py``.
Lives here so blueprints (``network_ops_bp``) and any future scheduler
job can share the same primitive without coupling to the Flask layer.

The ``MAX_PING_DEVICES`` constant is the request-time fan-out cap — the
``/api/ping`` route uses it to short-circuit oversized payloads before
touching ``subprocess``. It also bounds worst-case execution time.
"""
from __future__ import annotations

import platform
import subprocess

MAX_PING_DEVICES = 64


def single_ping(ip: str, timeout_sec: int = 2) -> bool:
    """Send one ICMP echo to ``ip``; return ``True`` iff reply received.

    Uses the system ``ping`` binary so we honour OS-level routing,
    ARP, and (importantly) source-interface selection without
    re-implementing it in Python. Catches all exceptions and returns
    ``False`` — this primitive must never raise.
    """
    # Caller is responsible for validating ``ip`` (see
    # ``InputSanitizer.sanitize_ip`` in /api/ping). The system ``ping``
    # binary is intentionally invoked by partial path so the OS resolves
    # it from $PATH (different on Linux / macOS / Windows).
    try:
        if platform.system().lower() == "windows":
            argv = ["ping", "-n", "1", "-w", str(timeout_sec * 1000), ip]  # noqa: S607
        else:
            argv = ["ping", "-c", "1", "-W", str(timeout_sec), ip]  # noqa: S607
        out = subprocess.run(  # noqa: S603 - argv built from validated ip + literals
            argv,
            capture_output=True,
            timeout=timeout_sec + 1,
        )
        return out.returncode == 0
    except Exception:  # noqa: BLE001 - any failure must yield False
        return False
