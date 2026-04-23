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
import re
import time
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


# --------------------------------------------------------------------------- #
# Wave-7.4 — interactive shell config dispatch                                #
# --------------------------------------------------------------------------- #
#
# ``run_config_lines_pty`` (above) calls ``client.exec_command`` with the
# entire config script as a single argument. NX-OS's SSH ``exec_command``
# channel does NOT run multi-line config scripts the way an interactive
# shell does — it interprets only the first line as the command and
# subsequent lines arrive on the channel input but are not acted on.
# Confirmed against ``LSW-IL2-H2-R509-VENUSTEST-P1-N04`` 2026-04-23: the
# bounce returned 200 ok in ~1 second per stanza but the device's
# interface state never changed.
#
# ``run_config_lines_shell`` opens a real interactive PTY via
# ``client.invoke_shell()``, waits for the device prompt before sending
# each line, and reads the response back so the caller can surface
# what NX-OS actually said.

# Prompt detection. NX-OS / IOS prompts look like:
#   hostname#                       (exec)
#   hostname(config)#               (config mode)
#   hostname(config-if)#            (interface config)
#   hostname(config-if-Ethernet1/15)# (some platforms)
#
# We require '# ' at end (with optional trailing space/CR/LF), preceded
# by a word and an optional '(...)' segment. Constrain the leading word
# to legitimate hostname chars (alnum + '-' + '_' + '.') so a stray '#'
# in command output (e.g. comment lines) does not fool us.
_CONFIG_PROMPT_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}(?:\([A-Za-z0-9_\-/\.]+\))?#\s*$",
    re.MULTILINE,
)

# NX-OS / IOS error markers. Any line starting with '%' that isn't just
# a banner '%' is a syntax / semantic error.
_DEVICE_ERROR_RE = re.compile(
    r"^%\s*(invalid|incomplete|ambiguous|cannot|error)",
    re.MULTILINE | re.IGNORECASE,
)


def _open_shell_channel(  # type: ignore[no-untyped-def]
    ip: str, username: str, password: str, timeout: int
):
    """Connect, ``invoke_shell()``, and return the channel.

    Extracted as a separate helper so tests can monkey-patch it without
    touching paramiko itself. On failure returns ``None`` and a bucketed
    error string via raising — callers should wrap in try/except.

    Wave-7.5: ``chan.settimeout(0.5)`` for **non-blocking polling**.
    Earlier 30-second blocking recv meant a single idle window blocked
    the runner for the full session timeout — operator log evidence
    2026-04-23: NX-OS sent the MOTD banner but no prompt, runner sat
    blocked for 60 seconds, then returned timeout.
    """
    if paramiko is None:
        raise RuntimeError("paramiko not installed")
    client = _build_client()
    if client is None:
        raise RuntimeError("paramiko not installed")
    client.connect(
        ip,
        username=username,
        password=password or "",
        timeout=min(30, timeout),
        allow_agent=False,
        look_for_keys=False,
    )
    chan = client.invoke_shell(width=200, height=50)
    # Short polling timeout — _read_until_prompt loops until its own
    # deadline. The recv side just needs to not block forever.
    chan.settimeout(0.5)
    # Stash the client on the channel so the caller can close both.
    chan._pergen_client = client  # type: ignore[attr-defined]
    return chan


def _read_until_prompt(  # type: ignore[no-untyped-def]
    chan, deadline: float, *, idle_grace_s: float = 0.3
) -> tuple[str, bool]:
    """Read from ``chan`` until a config prompt arrives or ``deadline``.

    Returns ``(accumulated_text, prompt_seen)``. ``prompt_seen`` is
    False on timeout — the caller decides whether to surface that as
    an error or continue.

    ``idle_grace_s`` is a small extra wait after the prompt is
    detected, in case the device is still flushing output past the
    prompt (some NX-OS releases double-print).

    Wave-7.5: relies on the channel having a SHORT recv timeout
    (~0.5s) set in ``_open_shell_channel`` so each ``recv()`` call
    polls and returns quickly. Earlier 30-second blocking recv could
    block the whole timeout window on a single empty read.
    """
    buf = bytearray()
    prompt_seen = False
    while time.time() < deadline:
        try:
            chunk = chan.recv(4096)
        except Exception:  # noqa: BLE001 — paramiko throws socket.timeout
            chunk = b""
        if chunk:
            buf.extend(chunk)
            text = buf.decode("utf-8", errors="replace")
            if _CONFIG_PROMPT_RE.search(text):
                prompt_seen = True
                # One short grace period for trailing bytes.
                grace_end = time.time() + idle_grace_s
                while time.time() < grace_end:
                    try:
                        more = chan.recv(4096)
                    except Exception:  # noqa: BLE001
                        more = b""
                    if more:
                        buf.extend(more)
                    else:
                        time.sleep(0.05)
                break
        else:
            # No data this poll — short sleep then re-check. We do NOT
            # bail on idle; the operator might just have a slow
            # device. We rely solely on the deadline.
            time.sleep(0.05)
    return buf.decode("utf-8", errors="replace"), prompt_seen


def run_config_lines_shell(
    ip: str,
    username: str,
    password: str,
    lines: list[str],
    timeout: int = 30,
) -> tuple[str | None, str | None]:
    """Run config lines via an interactive shell with per-line prompts.

    Wave-7.4 fix for transceiver recovery: dispatch each line via
    ``invoke_shell()`` and wait for the device prompt between commands.

    Wave-7.5 hardening (operator log evidence 2026-04-23): NX-OS sent
    its MOTD banner but no prompt — the runner blocked 60s waiting,
    nothing was ever sent to the device. Two failure modes addressed:

    1. **Banner pause**: NX-OS does not always emit a prompt right
       after the banner. Send a wake-up ``\\n`` immediately after
       ``invoke_shell()`` to nudge the device past the banner.
    2. **Paging**: NX-OS's default terminal length triggers
       ``--More--`` on multi-page output and waits for a key press.
       Send ``terminal length 0`` before any other command.

    Both are sent automatically before the operator's first line. They
    are NOT subject to the strict allowlist — those are runner-internal
    setup commands, not config lines from the caller. Operator-supplied
    lines still pass through ``_assert_lines_allowed`` upstream in
    ``interface_recovery``.

    Returns ``(combined_output_text, error_or_None)``.
    """
    if paramiko is None:
        return None, "paramiko not installed"
    if not lines:
        return None, "no configuration lines"

    chan = None
    client = None
    try:
        try:
            chan = _open_shell_channel(ip, username, password, timeout)
        except Exception as exc:  # noqa: BLE001
            bucket = _classify_ssh_error(exc)
            _log.warning(
                "ssh_runner.run_config_lines_shell connect failed (%s): %r",
                bucket,
                exc,
            )
            return None, bucket
        client = getattr(chan, "_pergen_client", None)

        deadline = time.time() + max(5, int(timeout))
        out_buf: list[str] = []

        # --- Wave-7.5 prelude: wake the prompt + disable paging ----- #
        # Step 1: send a bare newline to trigger the prompt past the
        # MOTD banner. We deliberately do NOT require a prompt to
        # match before this send — NX-OS may have sent the banner with
        # no prompt at all, and we'd block forever.
        try:
            chan.send(b"\n")
        except Exception as exc:  # noqa: BLE001
            bucket = _classify_ssh_error(exc)
            _log.warning(
                "ssh_runner: wake-newline failed (%s): %r", bucket, exc
            )
            return None, bucket
        wake_text, wake_ok = _read_until_prompt(chan, deadline)
        out_buf.append(wake_text)
        if not wake_ok:
            return "".join(out_buf), "timeout"

        # Step 2: disable paging. ``terminal length 0`` is exec-mode
        # only — must be sent BEFORE we enter configure terminal.
        chan.send(b"terminal length 0\n")
        page_text, page_ok = _read_until_prompt(chan, deadline)
        out_buf.append(page_text)
        if not page_ok:
            return "".join(out_buf), "timeout"

        # --- Operator's lines (already allowlist-vetted upstream) --- #
        for line in lines:
            payload = (line + "\n").encode("utf-8")
            chan.send(payload)
            text, prompt_ok = _read_until_prompt(chan, deadline)
            out_buf.append(text)
            if not prompt_ok:
                return "".join(out_buf), "timeout"
            if _DEVICE_ERROR_RE.search(text):
                return "".join(out_buf), f"device rejected line: {line!r}"

        return "".join(out_buf), None
    except Exception as exc:  # noqa: BLE001
        bucket = _classify_ssh_error(exc)
        _log.warning(
            "ssh_runner.run_config_lines_shell failed (%s): %r", bucket, exc
        )
        return None, bucket
    finally:
        if chan is not None:
            with contextlib.suppress(Exception):
                chan.close()
        if client is not None:
            with contextlib.suppress(Exception):
                client.close()
