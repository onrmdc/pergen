"""
Cisco NX-API: POST https://ip/ins with cli method.

TLS verification is disabled for device traffic — Nexus switches present
self-signed certificates. Shared posture lives in ``backend.runners._http``.

Note on the (results, error) contract: NX-API issues one POST per command
(unlike Arista's batched runCmds), so a mid-list failure returns the
results collected so far paired with the error from the failing command.
Callers can rely on ``len(results)`` to identify which commands succeeded.
"""
from __future__ import annotations

from typing import Any

import requests

from backend.runners._http import DEVICE_TLS_VERIFY


def run_commands(
    ip: str,
    username: str,
    password: str,
    commands: list[str],
    timeout: int = 30,
) -> tuple[list[Any], str | None]:
    """Run commands via NX-API.

    Returns ``(results, error)`` where ``results`` contains the bodies of
    every command that succeeded *before* an error occurred (one per
    request, in the same order as ``commands``). On error, ``len(results)``
    is the index of the failing command.

    Each entry is either a ``dict`` (parsed JSON) or a ``str`` (CLI text).
    """
    url = f"https://{ip}/ins"
    results: list[Any] = []
    for cmd in commands:
        request_body = {
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cmd": cmd, "version": 1},
            "id": 1,
        }
        try:
            r = requests.post(
                url,
                auth=(username, password or ""),
                json=request_body,
                headers={"Content-Type": "application/json-rpc"},
                verify=DEVICE_TLS_VERIFY,
                timeout=timeout,
            )
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                return results, data["error"].get("message", str(data["error"]))
            # NX-API returns result with body (text or dict); sometimes result is list or nested
            out = data.get("result")
            if isinstance(out, list) and out:
                out = out[0] if isinstance(out[0], dict) else {"body": str(out[0])}
            if isinstance(out, dict):
                result_body = out.get("body") or out.get("output") or out.get("msg")
            else:
                result_body = str(out) if out is not None else ""
            # Keep dict as-is so parser can use json_path; string for text/JSON string
            if isinstance(result_body, (dict, str)):
                results.append(result_body)
            else:
                results.append(str(result_body) if result_body is not None else "")
        except (requests.exceptions.RequestException, ValueError) as e:
            # ValueError covers r.json() decode failures.
            return results, str(e)
    return results, None
