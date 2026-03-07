"""
Cisco NX-API: POST https://ip/ins with cli method.
"""
import requests
from typing import Any

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass


def run_commands(ip: str, username: str, password: str, commands: list[str], timeout: int = 30) -> tuple[list[Any], str | None]:
    """
    Run commands via NX-API. Returns (list of results per command, error_message or None).
    Each result is the CLI text output (body or output).
    """
    url = f"https://{ip}/ins"
    results = []
    for cmd in commands:
        body = {
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cmd": cmd, "version": 1},
            "id": 1,
        }
        try:
            r = requests.post(
                url,
                auth=(username, password or ""),
                json=body,
                headers={"Content-Type": "application/json-rpc"},
                verify=False,
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
                body = out.get("body") or out.get("output") or out.get("msg")
            else:
                body = str(out) if out is not None else ""
            # Keep dict as-is so parser can use json_path; string for text/JSON string
            if isinstance(body, dict):
                results.append(body)
            elif isinstance(body, str):
                results.append(body)
            else:
                results.append(str(body) if body is not None else "")
        except requests.exceptions.RequestException as e:
            return results, str(e)
        except Exception as e:
            return results, str(e)
    return results, None
