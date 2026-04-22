"""
Interface bounce recovery: configure terminal + interface + shutdown + no shutdown.
Used only by /api/transceiver/recover (explicit operator action).
Imports are lazy inside functions to avoid loading API clients when only validating names.
"""
import re
from typing import Any

# Safe interface names (EOS / NX-OS): Ethernet1/1, Port-Channel1, etc.
INTERFACE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.:\-]{0,127}$")


def build_cisco_nxos_recovery_lines(interfaces: list[str]) -> list[str]:
    """CLI lines sent over SSH PTY for NX-OS interface bounce."""
    lines = ["configure terminal"]
    for iface in interfaces:
        lines.extend([f"interface {iface}", "shutdown", "no shutdown"])
    lines.append("end")
    return lines


def build_arista_recovery_commands(interfaces: list[str]) -> list[str]:
    """eAPI command strings for Arista EOS interface bounce."""
    cmds: list[str] = ["configure"]
    for iface in interfaces:
        cmds.extend([f"interface {iface}", "shutdown", "no shutdown"])
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


def recover_interfaces_cisco_nxos(ip: str, username: str, password: str, interfaces: list[str]) -> tuple[str | None, str | None]:
    """NX-OS: SSH PTY with configure terminal; per interface shutdown / no shutdown; end."""
    from backend.runners import ssh_runner

    lines = build_cisco_nxos_recovery_lines(interfaces)
    return ssh_runner.run_config_lines_pty(ip, username, password, lines, timeout=180)


def recover_interfaces_arista_eos(ip: str, username: str, password: str, interfaces: list[str]) -> tuple[list[Any] | None, str | None]:
    """Arista: eAPI runCmds in one batch (configure mode across cmds)."""
    from backend.runners import arista_eapi

    cmds = build_arista_recovery_commands(interfaces)
    return arista_eapi.run_commands(ip, username, password, cmds, timeout=180)


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
