"""
Rules for transceiver interface recovery / clear-counters: Leaf host
ports only. Two naming conventions are accepted:

* **Cisco NX-OS** uses ``Ethernet<module>/<port>`` (e.g. ``Ethernet1/15``).
  Allowed: module 1, ports 1-48. Short forms ``Eth1/x`` / ``Et1/x`` /
  ``1/x`` accepted.
* **Arista EOS** uses bare ``Ethernet<port>`` (e.g. ``Ethernet8``).
  Allowed: ports 1-48. Short forms ``Eth8`` / ``Et8`` accepted.

In both cases the range mirrors the Cisco "module-1 host ports" range
so operators have one mental model. Uplinks (49+ on most Arista
leaves; module 2+ on Cisco) are NOT allowed for recovery — bouncing
them risks isolating the device.

Wave-7.6 (2026-04-23): added the bare ``EthernetN`` form so Arista
device recovery actually works. Operator feedback: every Arista
recover request was being rejected by the policy gate before it
reached the eAPI dispatch, because the legacy regex required the
``Ethernet<m>/<p>`` form.
"""
import re
from typing import Any

# Cisco NX-OS form: Ethernet1/15, Eth1/15, Et1/15
_HOST_PORT_RE = re.compile(r"^(?:Ethernet|Eth|Et)(\d+)/(\d+)$", re.I)
# Short: 1/15
_SHORT_PORT_RE = re.compile(r"^(\d+)/(\d+)$")
# Arista EOS form: Ethernet8, Eth8, Et8 (no slash, no module)
_ARISTA_HOST_PORT_RE = re.compile(r"^(?:Ethernet|Eth|Et)(\d+)$", re.I)

_HOST_PORT_MAX = 48
_HOST_PORT_MIN = 1


def is_ethernet_module1_host_port(interface: str) -> bool:
    """Return True if ``interface`` names a front-panel host port that
    transceiver recovery is allowed to bounce.

    Accepts:

    * ``Ethernet1/X`` (Cisco NX-OS), 1 <= X <= 48
    * ``EthernetX`` (Arista EOS), 1 <= X <= 48
    * Short forms: ``Eth1/X``, ``Et1/X``, ``1/X``, ``EthX``, ``EtX``
    * Case-insensitive

    Rejects everything else (uplinks, sub-interfaces, port-channels,
    management ports, anything with shell metacharacters, etc.).
    """
    s = (interface or "").strip()
    if not s:
        return False
    # Cisco NX-OS form: Ethernet<m>/<p>
    m = _HOST_PORT_RE.match(s)
    if m:
        mod, port = int(m.group(1)), int(m.group(2))
        return mod == 1 and _HOST_PORT_MIN <= port <= _HOST_PORT_MAX
    # Short form: <m>/<p>
    m = _SHORT_PORT_RE.match(s)
    if m:
        mod, port = int(m.group(1)), int(m.group(2))
        return mod == 1 and _HOST_PORT_MIN <= port <= _HOST_PORT_MAX
    # Arista EOS form: Ethernet<p> (no module slash)
    m = _ARISTA_HOST_PORT_RE.match(s)
    if m:
        port = int(m.group(1))
        return _HOST_PORT_MIN <= port <= _HOST_PORT_MAX
    return False


def is_transceiver_recovery_allowed(device: dict[str, Any], interface: str) -> bool:
    """Recovery allowed only when device role is Leaf and interface is
    a recognised front-panel host port (see ``is_ethernet_module1_host_port``).
    """
    role = (device.get("role") or "").strip().lower()
    if role != "leaf":
        return False
    return is_ethernet_module1_host_port(interface)
