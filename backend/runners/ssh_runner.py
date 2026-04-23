"""
SSH runner: run single command via Paramiko.

Audit H1 + wave-7 follow-up
---------------------------
``AutoAddPolicy`` is the **intentional default** for an internal-only
deployment: operators enroll new leaves / spines into Pergen by
pointing it at the device and letting paramiko TOFU the host key on
first contact. The lock-down path is one env var away for any
deployment that does NOT trust the management network:

* ``PERGEN_SSH_STRICT_HOST_KEY=1`` — flip from ``AutoAddPolicy`` to
  ``RejectPolicy``. Combined with a populated ``known_hosts`` file
  this gives full SSH MITM protection.
* ``PERGEN_SSH_KNOWN_HOSTS=/path/to/known_hosts`` — explicit
  ``known_hosts`` path. When set, the runner loads it before connecting.

Wave-7 follow-up: the AutoAdd notice fires **once per process at
module import**, level INFO (not WARN per-call). The original
per-``_build_client`` WARN was creating audit-log noise during
multi-device runs (``/api/run/pre`` against a 50-device fleet would
emit 50 identical WARN lines). The notice is still discoverable via
``app.runner.ssh`` log filters; it just stops nagging.
"""
from __future__ import annotations

import contextlib
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

# Wave-7 follow-up: one-shot flag. The policy notice fires exactly
# once per process so multi-device runs don't drown the audit log in
# identical lines. Tests pin the existence of this flag so a future
# refactor can't silently regress to per-call logging.
_AUTOADD_NOTICE_EMITTED = False


def _emit_autoadd_notice_once() -> None:
    """Log the AutoAddPolicy notice at INFO level, exactly once.

    Wave-7 follow-up: the original implementation logged at WARN per
    ``_build_client()`` call which spammed every multi-device run.
    AutoAddPolicy is the intentional default for internal device
    enrollment — surface that decision in logs without nagging.
    """
    global _AUTOADD_NOTICE_EMITTED
    if _AUTOADD_NOTICE_EMITTED:
        return
    _AUTOADD_NOTICE_EMITTED = True
    _log.info(
        "ssh_runner using AutoAddPolicy (intentional default for internal "
        "device enrollment); set PERGEN_SSH_STRICT_HOST_KEY=1 + "
        "PERGEN_SSH_KNOWN_HOSTS=<path> to lock down for untrusted networks"
    )


# Fire the notice at module-import so it lands once, near the boot
# banner, instead of on first device contact (which could be minutes
# later or buried mid-run).
if _HOST_KEY_POLICY_NAME == "AutoAddPolicy" and paramiko is not None:
    _emit_autoadd_notice_once()


def _build_client():  # type: ignore[no-untyped-def]
    """Construct an ``SSHClient`` with the configured host-key policy."""
    if paramiko is None:
        return None
    client = paramiko.SSHClient()
    if _HOST_KEY_POLICY_NAME == "RejectPolicy":
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # No per-call log: the one-shot INFO at module import already
        # surfaced the policy choice. Re-logging here would defeat the
        # whole point of the wave-7 quiet-default fix.
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
    """Run one command over SSH. Returns ``(output_text, error_message_or_None)``.

    Audit (Python review C-5): the SSH transport is closed in a
    ``finally`` block so an exception between ``connect()`` and the
    explicit ``client.close()`` cannot leak the file descriptor /
    source-port slot. Sustained device-side flakiness used to
    drain the FD limit on the controller.
    """
    if paramiko is None:
        return None, "paramiko not installed"
    client = None
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
    finally:
        if client is not None:
            # close() must not mask the original error.
            with contextlib.suppress(Exception):
                client.close()


def run_config_lines_pty(
    ip: str,
    username: str,
    password: str,
    lines: list[str],
    timeout: int = 120,
) -> tuple[str | None, str | None]:
    """Run config lines over SSH with a PTY (NX-OS / IOS-style CLI).

    Audit (Python review C-4): exceptions are now bucketed via
    ``_classify_ssh_error`` instead of returning ``str(exc)`` —
    matching the hardening already applied to ``run_command``. This
    closes the credential-leak vector on the interface-recovery path.

    Audit (Python review C-5): the SSH transport is closed in a
    ``finally`` block to prevent FD leaks on exception paths.
    """
    if paramiko is None:
        return None, "paramiko not installed"
    if not lines:
        return None, "no configuration lines"
    script = "\n".join(lines) + "\n"
    client = None
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
        if err and not out:
            return None, err
        return out, None
    except Exception as exc:  # noqa: BLE001
        bucket = _classify_ssh_error(exc)
        _log.warning("ssh_runner.run_config_lines_pty failed (%s): %r", bucket, exc)
        return None, bucket
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                client.close()


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
