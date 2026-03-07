"""
SSH runner: run single command via Paramiko.
"""
from typing import Any

try:
    import paramiko
except ImportError:
    paramiko = None


def run_command(ip: str, username: str, password: str, command: str, timeout: int = 25) -> tuple[str | None, str | None]:
    """
    Run one command over SSH. Returns (output_text, error_message or None).
    """
    if not paramiko:
        return None, "paramiko not installed"
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            ip,
            username=username,
            password=password or "",
            timeout=timeout,
            allow_agent=False,
            look_for_keys=False,
        )
        _, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = (stdout.read().decode("utf-8", errors="replace") or "").strip()
        err = (stderr.read().decode("utf-8", errors="replace") or "").strip()
        client.close()
        if err and not out:
            return None, err
        return out, None
    except Exception as e:
        return None, str(e)


def run_commands(ip: str, username: str, password: str, commands: list[str], timeout: int = 25) -> tuple[list[Any], str | None]:
    """Run multiple commands; returns (list of output strings, error or None)."""
    results = []
    for cmd in commands:
        out, err = run_command(ip, username, password, cmd, timeout)
        if err:
            return results, err
        results.append(out or "")
    return results, None
