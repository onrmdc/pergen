"""
Cisco NX-OS ARP-suppression leaf-search strategy.

Two callables, mirroring the original god-module structure:

* :func:`_query_cisco_leaf_search` — issues ``show ip arp suppression-cache detail``
  on a single leaf-search device and parses the suppression entry for
  ``search_ip``. Returns either a hit dict (consumed by
  :func:`_complete_cisco_hit`) or ``None`` when the device has no credentials,
  the NX-API call fails, or the IP is not present in the suppression cache.
* :func:`_complete_cisco_hit` — given a hit, resolves the remote VTEP into a
  leaf device in the inventory, fetches the ARP table from that leaf, and
  parses the interface serving ``search_ip`` (falling back to the parsed
  ``physical_iod`` when the ARP fetch fails).

Behaviour is preserved verbatim from the original
``backend/find_leaf.py::_query_one_leaf_search`` (Cisco branch) and
``_complete_find_leaf_from_hit`` (Cisco branch).
"""

from __future__ import annotations

from typing import Any

from backend import parse_output
from backend.find_leaf.ip_helpers import _leaf_ip_from_remote
from backend.runners.runner import _get_credentials

__all__ = ["_query_cisco_leaf_search", "_complete_cisco_hit"]


def _query_cisco_leaf_search(
    dev: dict,
    search_ip: str,
    secret_key: str,
    cred_store_module: Any,
) -> dict | None:
    """Run the Cisco NX-OS ARP-suppression lookup on a single leaf-search device."""
    hostname = (dev.get("hostname") or "").strip()
    ip = (dev.get("ip") or "").strip()
    cred_name = (dev.get("credential") or "").strip()
    username, password = _get_credentials(cred_name, secret_key, cred_store_module)
    if not username and not password:
        return None

    from backend.runners import cisco_nxapi

    cmd_arp = "show ip arp suppression-cache detail"
    results, err = cisco_nxapi.run_commands(ip, username, password, [cmd_arp])
    if err:
        return None
    raw = results[0] if results else None
    parsed = (
        parse_output.parse_arp_suppression_for_ip(raw, search_ip) if raw is not None else None
    )
    if not parsed:
        return None
    return {
        "vendor": "cisco",
        "spine_ip": ip,
        "spine_hostname": hostname,
        "parsed": parsed,
        "username": username,
        "password": password,
        "dev": dev,
    }


def _complete_cisco_hit(
    hit: dict,
    search_ip: str,
    devices: list,
    secret_key: str,
    cred_store_module: Any,
) -> dict[str, Any]:
    """Resolve a Cisco hit into a leaf hostname / IP / interface."""
    from backend.runners import cisco_nxapi

    def device_by_ip(ip_str: str) -> dict | None:
        ip_str = (ip_str or "").strip()
        for d in devices:
            if (d.get("ip") or "").strip() == ip_str:
                return d
        return None

    out = {
        "found": True,
        "error": None,
        "leaf_hostname": "",
        "leaf_ip": "",
        "interface": "",
        "vendor": "",
        "fabric": "",
        "hall": "",
        "site": "",
        "remote_vtep_addr": "",
        "physical_iod": "",
    }

    ip = hit["spine_ip"]
    hostname = hit["spine_hostname"]
    parsed = hit["parsed"]
    remote_vtep = (parsed.get("remote_vtep_addr") or "").strip()
    out["remote_vtep_addr"] = remote_vtep
    out["physical_iod"] = parsed.get("physical_iod") or ""
    leaf_ip = _leaf_ip_from_remote(ip, remote_vtep) if remote_vtep else ip
    if not leaf_ip:
        leaf_ip = remote_vtep or ip
    leaf_dev = device_by_ip(leaf_ip) if leaf_ip else None
    out["leaf_hostname"] = (
        (leaf_dev.get("hostname") or "").strip() if leaf_dev else (remote_vtep or hostname)
    )
    out["leaf_ip"] = leaf_ip
    out["fabric"] = (leaf_dev.get("fabric") or "").strip() if leaf_dev else ""
    out["hall"] = (leaf_dev.get("hall") or "").strip() if leaf_dev else ""
    out["site"] = (leaf_dev.get("site") or "").strip() if leaf_dev else ""
    iface = parsed.get("physical_iod") or ""
    luser, lpass = hit["username"], hit["password"]
    if leaf_dev:
        lcred = (leaf_dev.get("credential") or "").strip()
        luser, lpass = _get_credentials(lcred, secret_key, cred_store_module) or (
            hit["username"],
            hit["password"],
        )
    if leaf_ip and (luser or lpass):
        try:
            arp_results, arp_err = cisco_nxapi.run_commands(
                leaf_ip, luser, lpass, ["show ip arp"], timeout=10
            )
            if not arp_err and arp_results:
                parsed_iface = parse_output.parse_cisco_arp_interface_for_ip(
                    arp_results, search_ip, 0
                )
                if parsed_iface:
                    iface = parsed_iface
        except Exception:
            pass
    out["interface"] = (iface or "").strip()
    out["vendor"] = "cisco"
    return out
