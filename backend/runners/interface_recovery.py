"""
Interface bounce recovery: configure terminal + interface + shutdown +
(wait) + no shutdown.

Used only by ``/api/transceiver/recover`` (explicit operator action).

Wave-7.3 (2026-04-23) bounce-delay fix
--------------------------------------
The legacy implementation sent ``shutdown`` and ``no shutdown`` in a
single config script. NX-OS schedules link-state changes
asynchronously and coalesces back-to-back commands, so the port
often never observed a real down→up transition and stayed
errdisabled / flapping. The audit log lied: the API returned
``200 ok`` even though nothing recovered.

Operator-validated CLI sequence:

    conf t
    interface <name>
    shutdown
    ! wait 5 seconds
    no shutdown
    end

This module now models the bounce as a **plan** (a list of stanzas
with per-stanza post-delays) and dispatches each stanza in its own
SSH/eAPI session, sleeping between them. Sequential per-interface
semantics: interface 1 fully bounced (shutdown → sleep → no shutdown)
before interface 2 starts.

Strict allowlist
----------------
The operator's hardening constraint: this code path must NEVER be
able to send anything beyond the canonical recovery commands. Every
generated line is matched against ``_ALLOWED_LINE_PATTERNS`` before
SSH/eAPI dispatch. Defensive caps: max one ``interface`` stanza per
script, max 4 lines per script (``configure`` + ``interface`` +
action + ``end``).

Imports of API clients are lazy inside functions to avoid loading
paramiko / requests when only validating names.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

_log = logging.getLogger("app.runner.interface_recovery")

# ---- Public regex (interface name validator) ---------------------------- #

# Safe interface names (EOS / NX-OS): Ethernet1/1, Port-Channel1, etc.
INTERFACE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.:\-]{0,127}$")

# ---- Wave-7.3 strict allowlist ------------------------------------------ #

# Each line emitted by build_*_recovery_plan() must match exactly one of
# these patterns. The patterns are deliberately tight — case-sensitive,
# no leading/trailing whitespace, no shell metachars. This is the
# defence-in-depth operator promised: even if a future caller mutates
# the input list, the most this code can send is a bounce.
_ALLOWED_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^configure terminal$"),  # NX-OS / IOS form
    re.compile(r"^configure$"),           # Arista EOS form
    # interface <name> — re-validates the name with the same rule as
    # validate_interface_names(); independent grep so a future change
    # to INTERFACE_NAME_RE does not silently widen this surface.
    re.compile(r"^interface [A-Za-z0-9][A-Za-z0-9/_.:\-]{0,127}$"),
    re.compile(r"^shutdown$"),
    re.compile(r"^no shutdown$"),
    re.compile(r"^end$"),
)

_MAX_LINES_PER_SCRIPT = 4
_MAX_INTERFACE_STANZAS_PER_SCRIPT = 1

# ---- Configurable bounce delay ------------------------------------------ #

_DEFAULT_BOUNCE_DELAY_SEC = 5
_BOUNCE_DELAY_MIN_SEC = 1
_BOUNCE_DELAY_MAX_SEC = 30


def _resolve_bounce_delay_sec() -> int:
    """Resolve the post-shutdown delay (in seconds) from env, with bounds.

    Env knob: ``PERGEN_RECOVERY_BOUNCE_DELAY_SEC``. Default 5s.
    Clamped to ``[1, 30]``. Garbage values fall back to default with
    no exception (operator-friendly).
    """
    raw = os.environ.get("PERGEN_RECOVERY_BOUNCE_DELAY_SEC", "").strip()
    if not raw:
        return _DEFAULT_BOUNCE_DELAY_SEC
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_BOUNCE_DELAY_SEC
    if value < _BOUNCE_DELAY_MIN_SEC:
        return _BOUNCE_DELAY_MIN_SEC
    if value > _BOUNCE_DELAY_MAX_SEC:
        return _BOUNCE_DELAY_MAX_SEC
    return value


def _assert_lines_allowed(lines: list[str]) -> None:
    """Raise ``ValueError`` if any line falls outside the canonical
    recovery allowlist OR violates the per-script defensive caps.

    This is the security gate the operator demanded: nothing else can
    ever travel through this code path to a device's config plane.
    """
    if not lines:
        raise ValueError("recovery script must not be empty")
    if len(lines) > _MAX_LINES_PER_SCRIPT:
        raise ValueError(
            f"recovery script exceeds {_MAX_LINES_PER_SCRIPT}-line cap "
            f"(got {len(lines)})"
        )
    iface_count = 0
    for line in lines:
        if not isinstance(line, str):
            raise ValueError(f"recovery line must be str, got {type(line).__name__}")
        if not any(pat.fullmatch(line) for pat in _ALLOWED_LINE_PATTERNS):
            # Redact long values in the error so we don't echo a wall
            # of attacker-controlled text into logs.
            redacted = (line[:32] + "…") if len(line) > 32 else line
            raise ValueError(f"recovery line not in allowlist: {redacted!r}")
        if line.startswith("interface "):
            iface_count += 1
    if iface_count > _MAX_INTERFACE_STANZAS_PER_SCRIPT:
        raise ValueError(
            f"recovery script must contain at most "
            f"{_MAX_INTERFACE_STANZAS_PER_SCRIPT} interface stanza "
            f"(got {iface_count})"
        )


# ---- Plan builders (wave-7.3) ------------------------------------------- #


def build_cisco_nxos_recovery_plan(interfaces: list[str]) -> list[dict[str, Any]]:
    """Build a per-interface bounce plan for NX-OS.

    Returns one ``{interface, phase, lines, post_delay_sec}`` dict per
    SSH session. For each interface the plan emits two stanzas:
    ``shutdown`` (with the bounce delay attached) and ``no_shutdown``
    (zero delay). Caller dispatches in order, sleeping ``post_delay_sec``
    between stanzas.
    """
    delay = _resolve_bounce_delay_sec()
    plan: list[dict[str, Any]] = []
    for iface in interfaces:
        plan.append(
            {
                "interface": iface,
                "phase": "shutdown",
                "lines": [
                    "configure terminal",
                    f"interface {iface}",
                    "shutdown",
                    "end",
                ],
                "post_delay_sec": delay,
            }
        )
        plan.append(
            {
                "interface": iface,
                "phase": "no_shutdown",
                "lines": [
                    "configure terminal",
                    f"interface {iface}",
                    "no shutdown",
                    "end",
                ],
                "post_delay_sec": 0,
            }
        )
    return plan


def build_arista_recovery_plan(interfaces: list[str]) -> list[dict[str, Any]]:
    """Mirror of ``build_cisco_nxos_recovery_plan`` for Arista eAPI."""
    delay = _resolve_bounce_delay_sec()
    plan: list[dict[str, Any]] = []
    for iface in interfaces:
        plan.append(
            {
                "interface": iface,
                "phase": "shutdown",
                "lines": [
                    "configure",
                    f"interface {iface}",
                    "shutdown",
                    "end",
                ],
                "post_delay_sec": delay,
            }
        )
        plan.append(
            {
                "interface": iface,
                "phase": "no_shutdown",
                "lines": [
                    "configure",
                    f"interface {iface}",
                    "no shutdown",
                    "end",
                ],
                "post_delay_sec": 0,
            }
        )
    return plan


# ---- Legacy line builders (deprecated; kept for SPA "commands" field) ---- #


def build_cisco_nxos_recovery_lines(interfaces: list[str]) -> list[str]:
    """Flat list of canonical lines for the SPA's "Command logs" panel.

    DEPRECATED for execution since wave-7.3 — the runner now uses
    ``build_cisco_nxos_recovery_plan`` to dispatch shutdown and
    no-shutdown in separate sessions. This function is preserved
    only so the SPA can show the operator the canonical CLI sequence
    that ran (with the wait inserted between).
    """
    delay = _resolve_bounce_delay_sec()
    lines = ["configure terminal"]
    for iface in interfaces:
        lines.extend(
            [
                f"interface {iface}",
                "shutdown",
                f"! wait {delay} seconds (operator-side)",
                "no shutdown",
            ]
        )
    lines.append("end")
    return lines


def build_arista_recovery_commands(interfaces: list[str]) -> list[str]:
    """Flat list of canonical eAPI cmds for the SPA's "Command logs" panel.

    DEPRECATED for execution since wave-7.3 — see
    ``build_cisco_nxos_recovery_lines`` docstring.
    """
    delay = _resolve_bounce_delay_sec()
    cmds: list[str] = ["configure"]
    for iface in interfaces:
        cmds.extend(
            [
                f"interface {iface}",
                "shutdown",
                f"! wait {delay} seconds (operator-side)",
                "no shutdown",
            ]
        )
    cmds.append("end")
    return cmds


def validate_interface_names(names: list[Any]) -> tuple[list[str], str | None]:
    out: list[str] = []
    for raw in names:
        n = str(raw or "").strip()
        if not n:
            continue
        if not INTERFACE_NAME_RE.match(n):
            return [], f"invalid interface name: {n!r}"
        out.append(n)
    if not out:
        return [], "no interfaces specified"
    return out, None


# ---- Recovery dispatch (wave-7.3) --------------------------------------- #


def recover_interfaces_cisco_nxos(
    ip: str, username: str, password: str, interfaces: list[str]
) -> tuple[str | None, str | None]:
    """NX-OS bounce: per interface, two SSH sessions with a sleep between.

    Sequential per-interface (interface 1 fully bounced before interface
    2 starts). Short-circuits on the first error to avoid leaving a
    port admin-down. Returns the concatenated output of all dispatches
    or the first error encountered.

    Wave-7.4: dispatches via ``run_config_lines_shell`` (invoke_shell +
    per-line prompt detection) instead of the old ``run_config_lines_pty``
    (single ``exec_command`` with the whole script). NX-OS's
    ``exec_command`` channel does not actually execute multi-line config
    scripts — it interpreted only the first line as the command and the
    rest never reached the parser. Confirmed against
    ``LSW-IL2-H2-R509-VENUSTEST-P1-N04`` 2026-04-23: the bounce returned
    200 ok in ~1 second per stanza but the device's interface state
    never changed.
    """
    from backend.runners import ssh_runner

    plan = build_cisco_nxos_recovery_plan(interfaces)
    outputs: list[str] = []
    for stanza in plan:
        _assert_lines_allowed(stanza["lines"])
        _log.info(
            "recovery: nxos %s ip=%s iface=%s phase=%s",
            "running",
            ip,
            stanza["interface"],
            stanza["phase"],
        )
        out, err = ssh_runner.run_config_lines_shell(
            ip, username, password, stanza["lines"], timeout=60
        )
        # Always log the device's actual response so the operator can
        # see what NX-OS said. Truncate at 800 chars to keep logs sane.
        if out:
            preview = out[:800].replace("\r\n", " ").replace("\n", " ")
            _log.info(
                "recovery: nxos device-response ip=%s iface=%s phase=%s: %s",
                ip,
                stanza["interface"],
                stanza["phase"],
                preview,
            )
        if err:
            _log.warning(
                "recovery: nxos failed ip=%s iface=%s phase=%s err=%s",
                ip,
                stanza["interface"],
                stanza["phase"],
                err,
            )
            return out, err
        if out:
            outputs.append(f"--- {stanza['interface']} {stanza['phase']} ---\n{out}")
        if stanza["post_delay_sec"] > 0:
            _log.info(
                "recovery: nxos sleeping %ds before no-shutdown of %s",
                stanza["post_delay_sec"],
                stanza["interface"],
            )
            time.sleep(stanza["post_delay_sec"])
    return ("\n\n".join(outputs) if outputs else "ok"), None


def recover_interfaces_arista_eos(
    ip: str, username: str, password: str, interfaces: list[str]
) -> tuple[list[Any] | None, str | None]:
    """Arista bounce: per interface, two eAPI batches with a sleep between."""
    from backend.runners import arista_eapi

    plan = build_arista_recovery_plan(interfaces)
    all_results: list[Any] = []
    for stanza in plan:
        _assert_lines_allowed(stanza["lines"])
        _log.info(
            "recovery: arista %s ip=%s iface=%s phase=%s",
            "running",
            ip,
            stanza["interface"],
            stanza["phase"],
        )
        results, err = arista_eapi.run_commands(
            ip, username, password, stanza["lines"], timeout=180
        )
        if err:
            _log.warning(
                "recovery: arista failed ip=%s iface=%s phase=%s err=%s",
                ip,
                stanza["interface"],
                stanza["phase"],
                err,
            )
            return results, err
        if results:
            all_results.extend(results)
        if stanza["post_delay_sec"] > 0:
            _log.info(
                "recovery: arista sleeping %ds before no-shutdown of %s",
                stanza["post_delay_sec"],
                stanza["interface"],
            )
            time.sleep(stanza["post_delay_sec"])
    return all_results, None


# ---- Status summary (unchanged from pre-7.3) ---------------------------- #


def _find_interface_status_row(rows: list[dict[str, Any]], want: str) -> dict[str, Any] | None:
    wl = want.strip().lower()
    if not wl:
        return None
    for row in rows:
        iface = str(row.get("interface") or "").strip()
        if iface.lower() == wl:
            return row
    for row in rows:
        iface = str(row.get("interface") or "").strip()
        il = iface.lower()
        if wl in il or il in wl:
            return row
    return None


def fetch_interface_status_summary_arista_eos(
    ip: str, username: str, password: str, interfaces: list[str],
) -> tuple[str | None, str | None]:
    """
    After recovery: run 'show interfaces | json' and return one line per requested interface
    (state, mtu, last_flap, in_errors) — used for Command logs output only.
    """
    from backend.parse_output import _parse_arista_interface_status
    from backend.runners import arista_eapi

    ok_names = [str(x).strip() for x in interfaces if str(x).strip()]
    if not ok_names:
        return None, "no interfaces specified"
    results, err = arista_eapi.run_commands(ip, username, password, ["show interfaces | json"], timeout=90)
    if err:
        return None, err
    if not results:
        return None, "empty eAPI result for show interfaces | json"
    parsed = _parse_arista_interface_status(results[0])
    rows: list[dict[str, Any]] = parsed.get("interface_status_rows") or []
    lines_out: list[str] = []
    for w in ok_names:
        row = _find_interface_status_row(rows, w)
        if row is None:
            lines_out.append(f"{w}: (not found in show interfaces | json)")
            continue
        lines_out.append(
            f"{row.get('interface')}: state={row.get('state')} mtu={row.get('mtu')} "
            f"last_flap={row.get('last_link_flapped')} in_errors={row.get('in_errors')}"
        )
    return "\n".join(lines_out), None


def fetch_interface_status_summary_cisco_nxos(
    ip: str, username: str, password: str, interfaces: list[str],
) -> tuple[str | None, str | None]:
    """After recovery: run 'show interface <name>' per interface; return short CLI snippets (status lines)."""
    from backend.runners import ssh_runner

    ok_names = [str(x).strip() for x in interfaces if str(x).strip()]
    if not ok_names:
        return None, "no interfaces specified"
    blocks: list[str] = []
    for iface in ok_names:
        out, err = ssh_runner.run_command(
            ip, username, password, f"show interface {iface}", timeout=60,
        )
        if err:
            blocks.append(f"--- {iface} ---\n(error: {err})")
            continue
        text = (out or "").strip()
        if not text:
            blocks.append(f"--- {iface} ---\n(no output)")
            continue
        lines = text.splitlines()
        blocks.append(f"--- {iface} ---\n" + "\n".join(lines[:16]))
    return "\n\n".join(blocks), None


def build_clear_counters_command(interface: str) -> str:
    """Privileged-exec command (not configure): clear counters for one interface."""
    iface = str(interface or "").strip()
    if not iface:
        return ""
    return f"clear counters interface {iface}"


def clear_counters_arista_eos(
    ip: str, username: str, password: str, interface: str,
) -> tuple[list[Any] | None, str | None]:
    """EOS: eAPI runCmds in exec mode (no configure)."""
    from backend.runners import arista_eapi

    cmd = build_clear_counters_command(interface)
    if not cmd:
        return None, "interface name required"
    return arista_eapi.run_commands(ip, username, password, [cmd], timeout=60)


def clear_counters_cisco_nxos(
    ip: str, username: str, password: str, interface: str,
) -> tuple[str | None, str | None]:
    """NX-OS: SSH exec (enable context)."""
    from backend.runners import ssh_runner

    cmd = build_clear_counters_command(interface)
    if not cmd:
        return None, "interface name required"
    return ssh_runner.run_command(ip, username, password, cmd, timeout=60)
