"""
Rules for transceiver interface recovery / clear-counters: Leaf host ports only (Ethernet1/1-1/48).
"""
import re
from typing import Any

_HOST_PORT_RE = re.compile(r"^(?:Ethernet|Eth|Et)(\d+)/(\d+)$", re.I)
_SHORT_PORT_RE = re.compile(r"^(\d+)/(\d+)$")


def is_ethernet_module1_host_port(interface: str) -> bool:
    """
    First linecard, ports 1-48: Ethernet1/1 … Ethernet1/48, Eth1/x, Et1/x, or short 1/1 … 1/48.
    """
    s = (interface or "").strip()
    if not s:
        return False
    m = _HOST_PORT_RE.match(s)
    if m:
        mod, port = int(m.group(1)), int(m.group(2))
        return mod == 1 and 1 <= port <= 48
    m = _SHORT_PORT_RE.match(s)
    if m:
        mod, port = int(m.group(1)), int(m.group(2))
        return mod == 1 and 1 <= port <= 48
    return False


def is_transceiver_recovery_allowed(device: dict[str, Any], interface: str) -> bool:
    """Recovery allowed only when device role is Leaf and interface is a module-1 host port (1-48)."""
    role = (device.get("role") or "").strip().lower()
    if role != "leaf":
        return False
    return is_ethernet_module1_host_port(interface)
