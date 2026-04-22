"""
Arista BGP-EVPN leaf-search strategy.

Two callables, mirroring the original god-module structure:

* :func:`_query_arista_leaf_search` — issues ``show bgp evpn route-type mac-ip <ip> | json``
  on a single leaf-search device and parses the next-hop. Returns either a
  hit dict (consumed by :func:`_complete_arista_hit`) or ``None`` when the
  device has no credentials, the eAPI call fails, or the IP is not present.
* :func:`_complete_arista_hit` — given a hit, resolves the leaf device in the
  inventory, fetches the ARP table from the leaf, and parses the interface
  serving ``search_ip``.

Behaviour is preserved verbatim from the original
``backend/find_leaf.py::_query_one_leaf_search`` (Arista branch) and
``_complete_find_leaf_from_hit`` (Arista branch).
"""

from __future__ import annotations

from typing import Any

from backend import parse_output
from backend.find_leaf.ip_helpers import _leaf_ip_from_remote
from backend.runners.runner import _get_credentials

__all__ = ["_query_arista_leaf_search", "_complete_arista_hit"]


def _query_arista_leaf_search(
    dev: dict,
    search_ip: str,
    secret_key: str,
    cred_store_module: Any,
) -> dict | None:
    """Run the Arista BGP-EVPN mac-ip lookup on a single leaf-search device."""
    hostname = (dev.get("hostname") or "").strip()
    ip = (dev.get("ip") or "").strip()
    cred_name = (dev.get("credential") or "").strip()
    username, password = _get_credentials(cred_name, secret_key, cred_store_module)
    if not username and not password:
        return None

    from backend.runners import arista_eapi

    cmd_bgp = f"show bgp evpn route-type mac-ip {search_ip} | json"
    results, err = arista_eapi.run_commands(ip, username, password, [cmd_bgp])
    if err or not results:
        return None
    next_hop = parse_output.parse_arista_bgp_evpn_next_hop(results, 0)
    if not next_hop:
        return None
    next_hop = next_hop.strip()
    return {
        "vendor": "arista",
        "spine_ip": ip,
        "spine_hostname": hostname,
        "next_hop": next_hop,
        "username": username,
        "password": password,
        "dev": dev,
    }


def _complete_arista_hit(
    hit: dict,
    search_ip: str,
    devices: list,
    secret_key: str,
    cred_store_module: Any,
) -> dict[str, Any]:
    """Resolve an Arista hit into a leaf hostname / IP / interface."""
    from backend.runners import arista_eapi

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
    next_hop = hit["next_hop"]
    lip = _leaf_ip_from_remote(ip, next_hop) if next_hop else None
    if not lip:
        lip = next_hop
    leaf_dev = device_by_ip(lip)
    if leaf_dev:
        lip = (leaf_dev.get("ip") or "").strip() or lip
        lcred = (leaf_dev.get("credential") or "").strip()
        luser, lpass = _get_credentials(lcred, secret_key, cred_store_module) or (
            hit["username"],
            hit["password"],
        )
    else:
        luser, lpass = hit["username"], hit["password"]
    iface = None
    if luser or lpass:
        arp_results, arp_err = arista_eapi.run_commands(
            lip, luser, lpass, ["show ip arp vrf all | json"]
        )
        if not arp_err and arp_results:
            iface = parse_output.parse_arista_arp_interface_for_ip(arp_results, search_ip, 0)
    out["leaf_hostname"] = (
        (leaf_dev.get("hostname") or "").strip() if leaf_dev else (lip or next_hop)
    )
    out["leaf_ip"] = lip
    out["fabric"] = (leaf_dev.get("fabric") or "").strip() if leaf_dev else ""
    out["hall"] = (leaf_dev.get("hall") or "").strip() if leaf_dev else ""
    out["site"] = (leaf_dev.get("site") or "").strip() if leaf_dev else ""
    out["interface"] = (iface or "").strip()
    out["vendor"] = "arista"
    return out
