"""Cisco NX-OS ARP table interface lookup.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

import re
from typing import Any

from backend.parsers.common.json_path import _get_val


def _get_cisco_arp_rows(data: Any) -> list:
    """From NX-API 'show ip arp' response get list of ARP row dicts (ip-addr-out, intf-out)."""
    if not isinstance(data, dict):
        return []
    for key, val in data.items():
        if isinstance(val, dict):
            if "TABLE_adj" in val or "TABLE_arp" in val:
                tbl = val.get("TABLE_adj") or val.get("TABLE_arp") or {}
            else:
                tbl = val
            rows = tbl.get("ROW_adj") or tbl.get("ROW_arp")
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                return rows
            if isinstance(rows, dict) and _get_val(rows, "ip-addr-out", "ip_addr_out"):
                return [rows]
            inner = _get_cisco_arp_rows(val)
            if inner:
                return inner
        elif isinstance(val, list) and val and isinstance(val[0], dict):
            if _get_val(val[0], "ip-addr-out", "ip_addr_out") or _get_val(val[0], "intf-out", "intf_out"):
                return val
    return []


def _parse_cisco_arp_ascii_for_ip(text: str, search_ip: str) -> str | None:
    """Parse ASCII 'show ip arp' output: find line with search_ip, return interface (last column or Ethernetx/y)."""
    if not text or not (search_ip or "").strip():
        return None
    search_ip = search_ip.strip()
    for line in text.splitlines():
        if search_ip not in line:
            continue
        parts = line.split()
        for i, p in enumerate(parts):
            if p == search_ip and i + 1 < len(parts):
                # Interface often last column or after MAC (Ethernet1/2, Eth1/2, etc.)
                for j in range(i + 1, len(parts)):
                    if re.match(r"^(Ethernet|Eth|Po)\d", parts[j], re.I):
                        return parts[j]
                if parts[-1] and not re.match(r"^\d{2}:\d{2}:\d{2}$", parts[-1]):
                    return parts[-1]
                break
    return None


def parse_cisco_arp_interface_for_ip(response: Any, search_ip: str, index: int = 0) -> str | None:
    """
    Parse Cisco NX-API 'show ip arp' (or detail) response. Return interface for search_ip, or None.
    Handles TABLE_vrf.TABLE_adj.ROW_adj with ip-addr-out / intf-out or phy-intf. Falls back to ASCII.
    """
    search_ip = (search_ip or "").strip()
    if not search_ip:
        return None
    data = response
    if isinstance(response, list) and len(response) > index:
        data = response[index]
    if isinstance(data, dict) and "body" in data:
        body = data["body"]
        if isinstance(body, str):
            return _parse_cisco_arp_ascii_for_ip(body, search_ip)
        data = body
    elif isinstance(data, str):
        return _parse_cisco_arp_ascii_for_ip(data, search_ip)
    if not isinstance(data, dict):
        return None
    # Walk TABLE_vrf -> TABLE_adj -> ROW_adj
    vrfs = data.get("TABLE_vrf") or data.get("TABLE_arp")
    if isinstance(vrfs, dict):
        vrfs = [vrfs]
    if isinstance(vrfs, list):
        for vrf in vrfs:
            if not isinstance(vrf, dict):
                continue
            adj = vrf.get("TABLE_adj") or vrf.get("TABLE_arp")
            if not isinstance(adj, dict):
                continue
            rows = adj.get("ROW_adj") or adj.get("ROW_arp")
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list):
                continue
            for r in rows:
                if not isinstance(r, dict):
                    continue
                ip_val = _get_val(r, "ip-addr-out", "ip_addr_out", "ip-addr", "ip_addr")
                if ip_val != search_ip:
                    continue
                iface = _get_val(r, "intf-out", "intf_out", "phy-intf", "phy_intf", "interface")
                if iface:
                    return iface
    # Fallback: flat list of rows
    for r in _get_cisco_arp_rows(data):
        ip_val = _get_val(r, "ip-addr-out", "ip_addr_out", "ip-addr", "ip_addr")
        if ip_val == search_ip:
            iface = _get_val(r, "intf-out", "intf_out", "phy-intf", "phy_intf", "interface")
            if iface:
                return iface
    return None


__all__ = [
    "parse_cisco_arp_interface_for_ip",
    "_get_cisco_arp_rows",
    "_parse_cisco_arp_ascii_for_ip",
]
