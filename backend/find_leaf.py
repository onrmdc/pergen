"""
Find Leaf: given an IP, search on leaf-search devices (BGP EVPN / ARP suppression), then resolve leaf and interface.
Queries all leaf-search devices in parallel for speed.
"""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from backend.inventory.loader import load_inventory, get_devices_by_tag
from backend.runners.runner import _get_credentials
from backend import parse_output


# Simple IPv4 validation
_IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.){3}"
    r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])$"
)


def _is_valid_ip(ip: str) -> bool:
    return bool((ip or "").strip() and _IPV4_RE.match((ip or "").strip()))


def _leaf_ip_from_remote(current_ip: str, remote_vtep: str) -> str | None:
    """
    Build leaf IP: first 3 octets from current device (leaf-search), last octet from remote_vtep.
    Returns None if either IP is invalid.
    """
    current_ip = (current_ip or "").strip()
    remote_vtep = (remote_vtep or "").strip()
    if not _is_valid_ip(current_ip) or not _is_valid_ip(remote_vtep):
        return None
    parts_cur = current_ip.split(".")
    parts_rem = remote_vtep.split(".")
    if len(parts_cur) != 4 or len(parts_rem) != 4:
        return None
    return f"{parts_cur[0]}.{parts_cur[1]}.{parts_cur[2]}.{parts_rem[3]}"


def _query_one_leaf_search(
    dev: dict,
    search_ip: str,
    secret_key: str,
    cred_store_module: Any,
) -> dict | None:
    """
    Query a single leaf-search device. Returns None if no cred, or IP not found on this device.
    Returns a hit dict with vendor, spine info, and data to complete the result (next_hop or parsed).
    """
    hostname = (dev.get("hostname") or "").strip()
    ip = (dev.get("ip") or "").strip()
    vendor = (dev.get("vendor") or "").strip().lower()
    cred_name = (dev.get("credential") or "").strip()
    username, password = _get_credentials(cred_name, secret_key, cred_store_module)
    if not username and not password:
        return None

    if vendor == "arista":
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

    if vendor == "cisco":
        from backend.runners import cisco_nxapi
        cmd_arp = "show ip arp suppression-cache detail"
        results, err = cisco_nxapi.run_commands(ip, username, password, [cmd_arp])
        if err:
            return None
        raw = results[0] if results else None
        parsed = parse_output.parse_arp_suppression_for_ip(raw, search_ip) if raw is not None else None
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
    return None


def _complete_find_leaf_from_hit(
    hit: dict,
    search_ip: str,
    devices: list,
    secret_key: str,
    cred_store_module: Any,
) -> dict[str, Any]:
    """Given a hit from _query_one_leaf_search, complete the result (connect to leaf, get port)."""
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
    if hit["vendor"] == "arista":
        from backend.runners import arista_eapi
        ip = hit["spine_ip"]
        next_hop = hit["next_hop"]
        lip = _leaf_ip_from_remote(ip, next_hop) if next_hop else None
        if not lip:
            lip = next_hop
        leaf_dev = device_by_ip(lip)
        if leaf_dev:
            lip = (leaf_dev.get("ip") or "").strip() or lip
            lcred = (leaf_dev.get("credential") or "").strip()
            luser, lpass = _get_credentials(lcred, secret_key, cred_store_module) or (hit["username"], hit["password"])
        else:
            luser, lpass = hit["username"], hit["password"]
        iface = None
        if luser or lpass:
            arp_results, arp_err = arista_eapi.run_commands(lip, luser, lpass, ["show ip arp vrf all | json"])
            if not arp_err and arp_results:
                iface = parse_output.parse_arista_arp_interface_for_ip(arp_results, search_ip, 0)
        out["leaf_hostname"] = (leaf_dev.get("hostname") or "").strip() if leaf_dev else (lip or next_hop)
        out["leaf_ip"] = lip
        out["fabric"] = (leaf_dev.get("fabric") or "").strip() if leaf_dev else ""
        out["hall"] = (leaf_dev.get("hall") or "").strip() if leaf_dev else ""
        out["site"] = (leaf_dev.get("site") or "").strip() if leaf_dev else ""
        out["interface"] = (iface or "").strip()
        out["vendor"] = "arista"
        return out
    if hit["vendor"] == "cisco":
        from backend.runners import cisco_nxapi
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
        out["leaf_hostname"] = (leaf_dev.get("hostname") or "").strip() if leaf_dev else (remote_vtep or hostname)
        out["leaf_ip"] = leaf_ip
        out["fabric"] = (leaf_dev.get("fabric") or "").strip() if leaf_dev else ""
        out["hall"] = (leaf_dev.get("hall") or "").strip() if leaf_dev else ""
        out["site"] = (leaf_dev.get("site") or "").strip() if leaf_dev else ""
        iface = parsed.get("physical_iod") or ""
        luser, lpass = hit["username"], hit["password"]
        if leaf_dev:
            lcred = (leaf_dev.get("credential") or "").strip()
            luser, lpass = _get_credentials(lcred, secret_key, cred_store_module) or (hit["username"], hit["password"])
        if leaf_ip and (luser or lpass):
            try:
                arp_results, arp_err = cisco_nxapi.run_commands(
                    leaf_ip, luser, lpass, ["show ip arp"], timeout=10
                )
                if not arp_err and arp_results:
                    parsed_iface = parse_output.parse_cisco_arp_interface_for_ip(arp_results, search_ip, 0)
                    if parsed_iface:
                        iface = parsed_iface
            except Exception:
                pass
        out["interface"] = (iface or "").strip()
        out["vendor"] = "cisco"
        return out
    return out


def find_leaf_check_device(
    search_ip: str,
    device_identifier: str,
    secret_key: str,
    cred_store_module: Any,
    inventory_path: str | None = None,
) -> dict[str, Any]:
    """
    Check a single leaf-search device for the IP. device_identifier is hostname or IP.
    Returns { "found": bool, "checked_hostname": str, ... } with full find_leaf result when found.
    """
    search_ip = (search_ip or "").strip()
    device_identifier = (device_identifier or "").strip()
    out = {
        "found": False,
        "error": None,
        "checked_hostname": "",
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
    if not _is_valid_ip(search_ip):
        out["error"] = "only IP format is allowed"
        return out
    if not device_identifier:
        out["error"] = "device_identifier (hostname or IP) is required"
        return out

    devices = load_inventory(inventory_path)
    leaf_search = get_devices_by_tag("leaf-search", devices)
    dev = None
    for d in leaf_search:
        h = (d.get("hostname") or "").strip()
        i = (d.get("ip") or "").strip()
        if h == device_identifier or i == device_identifier:
            dev = d
            break
    if not dev:
        out["error"] = f"device '{device_identifier}' not found in leaf-search"
        return out
    out["checked_hostname"] = (dev.get("hostname") or dev.get("ip") or "").strip()

    hit = _query_one_leaf_search(dev, search_ip, secret_key, cred_store_module)
    if hit is None:
        return out
    completed = _complete_find_leaf_from_hit(hit, search_ip, devices, secret_key, cred_store_module)
    completed["checked_hostname"] = out["checked_hostname"]
    return completed


def find_leaf(
    search_ip: str,
    secret_key: str,
    cred_store_module,
    inventory_path: str | None = None,
) -> dict[str, Any]:
    """
    Search for the leaf and interface/port for the given IP.
    - Only IP format is accepted.
    - First runs on devices with tag "leaf-search" (BGP EVPN for Arista, ARP suppression for Cisco).
    - For Arista: parses nextHop from BGP EVPN mac-ip, then finds that switch in inventory and runs ARP to get interface.
    - For Cisco: parses ARP suppression cache for the IP; the device where it is found is the leaf.
    Returns:
      { "found": bool, "error": str | null, "leaf_hostname": str, "leaf_ip": str, "interface": str,
        "vendor": str, "remote_vtep_addr": str (Cisco only), "physical_iod": str (Cisco only) }
    """
    search_ip = (search_ip or "").strip()
    out = {
        "found": False,
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
        "checked_devices": [],
    }
    if not _is_valid_ip(search_ip):
        out["error"] = "only IP format is allowed"
        return out

    devices = load_inventory(inventory_path)
    leaf_search = get_devices_by_tag("leaf-search", devices)
    if not leaf_search:
        out["error"] = "no devices with tag 'leaf-search' in inventory"
        return out
    out["checked_devices"] = [
        {"hostname": (d.get("hostname") or "").strip(), "ip": (d.get("ip") or "").strip()}
        for d in leaf_search
    ]

    def device_by_ip(ip_str: str) -> dict | None:
        ip_str = (ip_str or "").strip()
        for d in devices:
            if (d.get("ip") or "").strip() == ip_str:
                return d
        return None

    # Query all leaf-search devices in parallel; use first hit
    hit = None
    max_workers = min(len(leaf_search), 32)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_query_one_leaf_search, dev, search_ip, secret_key, cred_store_module): dev
            for dev in leaf_search
        }
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    hit = result
                    break
            except Exception:
                pass

    if hit is None:
        out["error"] = "IP not found on any leaf-search device"
        return out

    completed = _complete_find_leaf_from_hit(hit, search_ip, devices, secret_key, cred_store_module)
    out.update(completed)
    return out
