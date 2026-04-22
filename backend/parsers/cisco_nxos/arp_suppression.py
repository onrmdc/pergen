"""Cisco NX-OS ARP-suppression-cache parser.

Extracted verbatim from ``backend/parse_output.py``. The ASCII parser
``parse_arp_suppression_asci`` is co-located here because
``parse_arp_suppression_for_ip`` falls back to it for non-JSON inputs.
"""

from __future__ import annotations

import re
from typing import Any

from backend.parsers.common.json_path import _find_key, _find_list


def _get_arp_suppression_entries_list(obj: Any) -> list | None:
    """From NX-API response return list of entry dicts with ip-addr, or None."""
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict) and (_find_key(obj[0], "ip-addr") or _find_key(obj[0], "ip_addr")):
            return obj
        for item in obj:
            found = _get_arp_suppression_entries_list(item)
            if found:
                return found
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "entries" in k.lower() and isinstance(v, list) and v and isinstance(v[0], dict):
                if _find_key(v[0], "ip-addr") or _find_key(v[0], "ip_addr"):
                    return v
        for k, v in obj.items():
            found = _get_arp_suppression_entries_list(v)
            if found:
                return found
    return None


def parse_arp_suppression_for_ip(res: Any, search_ip: str) -> dict[str, str] | None:
    """
    Parse NX-API or ASCII of 'show ip arp suppression-cache detail' for the given IP.
    Returns None if not found, else {"flag": "L"|"R", "physical_iod": str, "remote_vtep_addr": str}.
    """
    search_ip = (search_ip or "").strip()
    if not search_ip:
        return None
    if isinstance(res, dict):
        entries_list = _get_arp_suppression_entries_list(res)
        if entries_list:
            for r in entries_list:
                ip_val = _find_key(r, "ip-addr") or _find_key(r, "ip_addr")
                if not ip_val or str(ip_val).strip() != search_ip:
                    continue
                flag = (_find_key(r, "flag") or "").strip().upper() or "L"
                phys = _find_key(r, "physical-iod") or _find_key(r, "physical_iod") or ""
                phys = str(phys).strip() if phys is not None else ""
                remote = _find_key(r, "remote-vtep-addr") or _find_key(r, "remote_vtep_addr") or ""
                remote = str(remote).strip() if remote is not None else ""
                return {"flag": flag[0] if flag else "L", "physical_iod": phys, "remote_vtep_addr": remote}
            return None
        rows = _find_list(res, "ROW")
        if not rows and _find_key(res, "body"):
            body = _find_key(res, "body")
            if isinstance(body, str):
                return parse_arp_suppression_asci(body, search_ip)
        if isinstance(rows, dict):
            rows = [rows]
        for r in (rows or []):
            if not isinstance(r, dict):
                continue
            ip_val = _find_key(r, "ip-addr") or _find_key(r, "ip_addr")
            if not ip_val or str(ip_val).strip() != search_ip:
                continue
            flag = (_find_key(r, "flag") or "").strip().upper() or "L"
            phys = _find_key(r, "physical-iod") or _find_key(r, "physical_iod") or ""
            phys = str(phys).strip() if phys is not None else ""
            remote = _find_key(r, "remote-vtep-addr") or _find_key(r, "remote_vtep_addr") or ""
            remote = str(remote).strip() if remote is not None else ""
            return {"flag": flag[0] if flag else "L", "physical_iod": phys, "remote_vtep_addr": remote}
        return None
    if isinstance(res, str):
        return parse_arp_suppression_asci(res, search_ip)
    return None


def parse_arp_suppression_asci(text: str, search_ip: str) -> dict[str, str] | None:
    """Parse ASCII output for one IP. Returns dict or None."""
    if not text or not search_ip:
        return None
    for line in text.splitlines():
        if search_ip not in line:
            continue
        flag = "L"
        for m in re.finditer(r'["\']flag["\']\s*:\s*["\']?([LR])', line, re.I):
            flag = m.group(1).upper()
            break
        phys = ""
        for m in re.finditer(r'["\']physical-iod["\']\s*:\s*["\']([^"\']*)["\']', line, re.I):
            phys = m.group(1).strip()
            break
        if not phys and "physical" in line.lower():
            for m in re.finditer(r'physical[_-]?iod["\']?\s*:\s*["\']?\(?([^)"\']*)', line, re.I):
                phys = m.group(1).strip()
                break
        remote = ""
        for m in re.finditer(r'["\']remote-vtep-addr["\']\s*:\s*["\']([^"\']*)["\']', line, re.I):
            remote = m.group(1).strip()
            break
        return {"flag": flag, "physical_iod": phys, "remote_vtep_addr": remote}
    return None


__all__ = [
    "parse_arp_suppression_for_ip",
    "parse_arp_suppression_asci",
    "_get_arp_suppression_entries_list",
]
