"""
SSH runner: run single command via Paramiko.

Audit H1 hardening
------------------
Default behaviour preserved for backwards compatibility (operators
who already have ``AutoAddPolicy`` working with their gear shouldn't
break on upgrade), but two opt-in environment knobs are now available:

* ``PERGEN_SSH_STRICT_HOST_KEY=1`` — flip from ``AutoAddPolicy`` to
  ``RejectPolicy``. Combined with a populated ``known_hosts`` file
  this gives full SSH MITM protection.
* ``PERGEN_SSH_KNOWN_HOSTS=/path/to/known_hosts`` — explicit
  ``known_hosts`` path. When set, the runner loads it before connecting.

Without either knob the runner remains compatible with the historical
deployment (auto-add new keys, log a warning).
"""
from __future__ import annotations

import logging
import os
from typing import Any

try:
    import paramiko
except ImportError:
    paramiko = None  # type: ignore[assignment]

_log = logging.getLogger("app.runner.ssh")


# Audit visibility — tests check this constant to confirm the chosen
# policy reflects the current env.
_HOST_KEY_POLICY_NAME = (
    "RejectPolicy"
    if os.environ.get("PERGEN_SSH_STRICT_HOST_KEY") == "1"
    else "AutoAddPolicy"
)


def _build_client():  # type: ignore[no-untyped-def]
    """Construct an ``SSHClient`` with the configured host-key policy."""
    if paramiko is None:
        return None
    client = paramiko.SSHClient()
    if _HOST_KEY_POLICY_NAME == "RejectPolicy":
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # WARN once per process when running insecure default.
        _log.warning(
            "ssh_runner using AutoAddPolicy (audit H1) — "
            "set PERGEN_SSH_STRICT_HOST_KEY=1 for SSH MITM protection"
        )
    known_hosts = os.environ.get("PERGEN_SSH_KNOWN_HOSTS")
    if known_hosts and os.path.isfile(known_hosts):
        try:
            client.load_host_keys(known_hosts)
        except OSError as exc:  # pragma: no cover — best effort
            _log.warning("failed to load known_hosts %s: %s", known_hosts, exc)
    return client


def _classify_ssh_error(exc: BaseException) -> str:
    """Map a paramiko / network exception to a controlled vocabulary.

    Audit M-11: returning ``str(exc)`` to the caller risked leaking
    usernames, passwords, or environment details if a future paramiko
    upgrade widened the exception text. Server-side log keeps the
    original repr; the operator sees only the bucket name.
    """
    name = type(exc).__name__
    if paramiko is not None and isinstance(exc, paramiko.AuthenticationException):
        return "auth_failed"
    if paramiko is not None and isinstance(exc, paramiko.BadHostKeyException):
        return "host_key_mismatch"
    if paramiko is not None and isinstance(exc, paramiko.ssh_exception.NoValidConnectionsError):
        return "network"
    # paramiko.SSHException covers banner, channel, protocol, etc.
    if paramiko is not None and isinstance(exc, paramiko.SSHException):
        return "ssh_protocol"
    # Built-in network failures.
    if isinstance(exc, (TimeoutError,)):
        return "timeout"
    if isinstance(exc, (OSError, ConnectionError)):
        return "network"
    return f"other:{name}"


def run_command(
    ip: str,
    username: str,
    password: str,
    command: str,
    timeout: int = 25,
) -> tuple[str | None, str | None]:
    """Run one command over SSH. Returns ``(output_text, error_message_or_None)``."""
    if paramiko is None:
        return None, "paramiko not installed"
    try:
        client = _build_client()
        if client is None:
            return None, "paramiko not installed"
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
    except Exception as exc:  # noqa: BLE001 — network errors must not crash routes
        # Audit M-11: log the full repr server-side, return only the
        # controlled label to the caller — never leak user/pass/host
        # details that might be in the exception text.
        bucket = _classify_ssh_error(exc)
        _log.warning("ssh_runner.run_command failed (%s): %r", bucket, exc)
        return None, bucket


def run_config_lines_pty(
    ip: str,
    username: str,
    password: str,
    lines: list[str],
    timeout: int = 120,
) -> tuple[str | None, str | None]:
    """Run config lines over SSH with a PTY (NX-OS / IOS-style CLI)."""
    if paramiko is None:
        return None, "paramiko not installed"
    if not lines:
        return None, "no configuration lines"
    script = "\n".join(lines) + "\n"
    try:
        client = _build_client()
        if client is None:
            return None, "paramiko not installed"
        client.connect(
            ip,
            username=username,
            password=password or "",
            timeout=min(30, timeout),
            allow_agent=False,
            look_for_keys=False,
        )
        _, stdout, stderr = client.exec_command(script, timeout=timeout, get_pty=True)
        out = (stdout.read().decode("utf-8", errors="replace") or "").strip()
        err = (stderr.read().decode("utf-8", errors="replace") or "").strip()
        client.close()
        if err and not out:
            return None, err
        return out, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def run_commands(
    ip: str,
    username: str,
    password: str,
    commands: list[str],
    timeout: int = 25,
) -> tuple[list[Any], str | None]:
    """Run multiple commands; returns ``(list of output strings, error_or_None)``."""
    results: list = []
    for cmd in commands:
        out, err = run_command(ip, username, password, cmd, timeout)
        if err:
            return results, err
        results.append(out or "")
    return results, None
