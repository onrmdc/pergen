"""
Arista EOS eAPI: POST https://ip/command-api with runCmds.

TLS verification is unconditionally disabled for device traffic. Arista
switches in this fleet present self-signed eAPI certificates with no public
CA path. The shared posture lives in ``backend.runners._http`` so all device
runners agree and the ``InsecureRequestWarning`` is suppressed exactly once.
"""
from __future__ import annotations

from typing import Any

import requests

from backend.runners._http import DEVICE_TLS_VERIFY


def run_commands(ip: str, username: str, password: str, commands: list[str], timeout: int = 30) -> tuple[list[Any], str | None]:
    """
    Run commands via eAPI. Returns (list of results per command, error_message or None).
    Each result can be dict (JSON) or str.
    """
    url = f"https://{ip}/command-api"
    body = {
        "jsonrpc": "2.0",
        "method": "runCmds",
        "params": {"format": "json", "version": 1, "cmds": commands},
        "version": 1,
        "id": 1,
    }
    try:
        r = requests.post(
            url,
            auth=(username, password or ""),
            json=body,
            verify=DEVICE_TLS_VERIFY,
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            return [], data["error"].get("message", str(data["error"]))
        results = data.get("result") or []
        return results, None
    except (requests.exceptions.RequestException, ValueError) as e:
        # ValueError covers r.json() decode failures.
        return [], str(e)


def run_cmds(
    ip: str,
    username: str,
    password: str,
    cmds: list[Any],
    timeout: int = 60,
    *,
    timestamps: bool = False,
    auto_complete: bool = False,
    expand_aliases: bool = False,
    stop_on_error: bool = True,
    streaming: bool = False,
    include_error_detail: bool = False,
) -> tuple[list[Any], str | None]:
    """
    Run arbitrary runCmds eAPI request. cmds can be strings or dicts (e.g. {"cmd": "enable", "input": "..."}).
    Caller must substitute enable password into cmd dicts before calling.
    Returns (result list, error_message or None).
    """
    url = f"https://{ip}/command-api"
    body = {
        "jsonrpc": "2.0",
        "method": "runCmds",
        "params": {
            "version": 1,
            "cmds": cmds,
            "format": "json",
            "timestamps": timestamps,
            "autoComplete": auto_complete,
            "expandAliases": expand_aliases,
            "stopOnError": stop_on_error,
            "streaming": streaming,
            "includeErrorDetail": include_error_detail,
        },
        "id": "EapiExplorer-1",
    }
    try:
        r = requests.post(
            url,
            auth=(username, password or ""),
            json=body,
            verify=DEVICE_TLS_VERIFY,
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            return [], data["error"].get("message", str(data["error"]))
        results = data.get("result") or []
        return results, None
    except (requests.exceptions.RequestException, ValueError) as e:
        # ValueError covers r.json() decode failures.
        return [], str(e)
