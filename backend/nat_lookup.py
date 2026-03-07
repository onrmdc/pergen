"""
NAT Lookup: find which NAT rule matches src_ip -> dest_ip and to which IP(s) it translates.
Uses Find Leaf (first step) to get fabric/site of the source IP, then queries only
Palo Alto firewalls with tag 'natlookup' in the same fabric and site.
"""
import re
import xml.etree.ElementTree as ET
from typing import Any
import requests

from backend.inventory.loader import load_inventory, get_devices_by_tag
from backend.runners.runner import _get_credentials
from backend import find_leaf as find_leaf_module

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

_IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.){3}"
    r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])$"
)


def _is_valid_ip(ip: str) -> bool:
    return bool((ip or "").strip() and _IPV4_RE.match((ip or "").strip()))


def _format_first_nat_rule_response(entry_value: str | None) -> str:
    """Format first NAT rule name as canonical XML response. Use entry_value=None for empty <rules/>."""
    if not (entry_value or "").strip():
        return (
            '<response cmd="status" status="success">\n'
            "    <result>\n"
            "        <rules>\n"
            "        </rules>\n"
            "    </result>\n"
            "</response>"
        )
    entry_escaped = (entry_value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<response cmd="status" status="success">\n'
        "    <result>\n"
        "        <rules>\n"
        f"            <entry>{entry_escaped}</entry>\n"
        "        </rules>\n"
        "    </result>\n"
        "</response>"
    )


def _find_nat_rule_name_in_response(text: str) -> str | None:
    """Parse Palo Alto nat-policy-match op response; return matched rule name or None.
    Matches pre-post: <result><rules><entry>RuleName</entry> or <member>RuleName</member>."""
    if not (text or "").strip():
        return None
    try:
        root = ET.fromstring(text)
        for tag in ("entry", "member"):
            el = root.find(f".//{tag}")
            if el is not None and el.text and el.text.strip():
                return el.text.strip()
        for e in root.iter():
            local = e.tag.split("}")[-1] if "}" in str(e.tag) else e.tag
            if e.text and local in ("entry", "member", "rule"):
                t = (e.text or "").strip()
                if t:
                    return t
    except ET.ParseError:
        pass
    # Regex fallbacks (same as pre-post)
    m = re.search(r"<entry>([^<]+)</entry>", text)
    if m and m.group(1).strip():
        return m.group(1).strip()
    m = re.search(r"<member>([^<]+)</member>", text)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return None


def _format_translated_address_response(rule_name: str, member_ips: list[str]) -> str:
    """Format translated-address member IP(s) as canonical XML (1 or 2 IPs)."""
    def esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    name_attr = esc(rule_name)
    members_xml = "\n".join(f"                        <member>{esc(ip)}</member>" for ip in (member_ips or []))
    return (
        '<response status="success" code="19">\n'
        '    <result total-count="1" count="1">\n'
        f'        <entry name="{name_attr}">\n'
        "            <source-translation>\n"
        "                <dynamic-ip-and-port>\n"
        "                    <translated-address>\n"
        f"{members_xml}\n"
        "                    </translated-address>\n"
        "                </dynamic-ip-and-port>\n"
        "            </source-translation>\n"
        "        </entry>\n"
        "    </result>\n"
        "</response>"
    )


def _find_translated_ips_in_rule_config(text: str) -> list[str]:
    """Parse Palo Alto NAT rule config: source-translation -> translated-address -> member IPs.
    Matches pre-post: regex for <source-translation> block then <member>IP</member>; else XML walk."""
    nat_ips: list[str] = []
    if not (text or "").strip():
        return nat_ips
    ip_re = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
    # 1) Regex: source-translation block, then member IPs (same as pre-post)
    m_block = re.search(
        r"<source-translation>\s*(.*?)\s*</source-translation>",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if m_block:
        block = m_block.group(0)
        if "translated-address" in block.lower() and "dynamic-ip" in block.lower():
            for mm in re.finditer(r"<member>\s*([^<]+)\s*</member>", block, re.IGNORECASE):
                t = mm.group(1).strip()
                if ip_re.match(t) and t not in nat_ips:
                    nat_ips.append(t)
    # 2) Fallback: XML parse, source-translation -> translated-address -> member
    if not nat_ips:
        try:
            root = ET.fromstring(text)
            def local_name(tag: str) -> str:
                return tag.split("}")[-1] if "}" in str(tag) else tag
            for el in root.iter():
                if local_name(el.tag) != "source-translation":
                    continue
                for addr in el.iter():
                    if local_name(addr.tag) != "translated-address":
                        continue
                    for child in addr.iter():
                        if local_name(child.tag) == "member" and child.text:
                            t = (child.text or "").strip()
                            if ip_re.match(t) and t not in nat_ips:
                                nat_ips.append(t)
        except ET.ParseError:
            pass
    return nat_ips


def nat_lookup(
    src_ip: str,
    dest_ip: str,
    secret_key: str,
    cred_store_module: Any,
    inventory_path: str | None = None,
    timeout: int = 15,
    debug: bool = False,
    fabric: str | None = None,
    site: str | None = None,
    leaf_checked_devices: list | None = None,
) -> dict[str, Any]:
    """
    Find which NAT rule matches src_ip -> dest_ip on Palo Alto firewalls (tag natlookup)
    in the same fabric/site as the leaf that has src_ip. Returns rule name and translated IP(s).

    Returns:
      { "ok": bool, "error": str | None, "fabric": str, "site": str, "rule_name": str,
        "translated_ips": list[str], "firewall_hostname": str, "firewall_ip": str }
    """
    src_ip = (src_ip or "").strip()
    dest_ip = (dest_ip or "").strip() or "8.8.8.8"
    out = {
        "ok": False,
        "error": None,
        "fabric": "",
        "site": "",
        "rule_name": "",
        "translated_ips": [],
        "firewall_hostname": "",
        "firewall_ip": "",
        "leaf_checked_devices": [],
        "debug": None,
    }
    if not _is_valid_ip(src_ip):
        out["error"] = "invalid source IP"
        return out
    if not _is_valid_ip(dest_ip):
        out["error"] = "invalid destination IP"
        return out

    fabric = (fabric or "").strip()
    site = (site or "").strip()
    if not fabric or not site:
        # Step 1: Find leaf for src_ip to get fabric and site
        leaf_result = find_leaf_module.find_leaf(
            src_ip, secret_key, cred_store_module, inventory_path
        )
        out["leaf_checked_devices"] = leaf_result.get("checked_devices") or []
        if not leaf_result.get("found"):
            out["error"] = leaf_result.get("error") or "source IP not found on any leaf"
            return out
        fabric = (leaf_result.get("fabric") or "").strip()
        site = (leaf_result.get("site") or "").strip()
        if not fabric or not site:
            out["error"] = "leaf fabric/site could not be determined"
            return out
    else:
        out["leaf_checked_devices"] = leaf_checked_devices or []
    out["fabric"] = fabric
    out["site"] = site

    # Step 2: Get firewalls with tag natlookup, same fabric+site, Palo Alto (vendor palo-alto or model panos)
    devices = load_inventory(inventory_path)
    nat_devices = get_devices_by_tag("natlookup", devices)
    fabric_lower = fabric.lower()
    site_lower = site.lower()

    def _is_palo_alto(d: dict) -> bool:
        v = (d.get("vendor") or "").strip().lower()
        m = (d.get("model") or "").strip().lower()
        return v in ("palo-alto", "palo alto", "panos") or m == "panos"

    firewalls = [
        d
        for d in nat_devices
        if (d.get("fabric") or "").strip().lower() == fabric_lower
        and (d.get("site") or "").strip().lower() == site_lower
        and _is_palo_alto(d)
    ]
    if not firewalls:
        out["error"] = f"no Palo Alto firewall with tag 'natlookup' in fabric={fabric}, site={site}"
        return out

    # Step 3: NAT policy match (format same as pre-post: <source>IP</source><destination>IP</destination>)
    cmd_match = (
        "<test><nat-policy-match>"
        f"<source>{src_ip}</source><destination>{dest_ip}</destination>"
        "<protocol>6</protocol><destination-port>443</destination-port>"
        "</nat-policy-match></test>"
    )
    for fw in firewalls:
        fw_ip = (fw.get("ip") or "").strip()
        cred_name = (fw.get("credential") or "").strip()
        _, api_key = _get_credentials(cred_name, secret_key, cred_store_module)
        if not api_key:
            continue
        base = f"https://{fw_ip}/api/"
        params = {"type": "op", "key": api_key, "cmd": cmd_match}
        debug_responses = {}
        try:
            r = requests.get(
                base, params=params, verify=False, timeout=timeout
            )
            r.raise_for_status()
            body = r.text
            if debug:
                debug_responses["nat_policy_match"] = body
        except requests.exceptions.RequestException as e:
            out["error"] = f"firewall {fw_ip}: {e}"
            if debug:
                debug_responses["nat_policy_match_error"] = str(e)
                out["debug"] = debug_responses
            continue
        rule_name = _find_nat_rule_name_in_response(body)
        if not rule_name:
            out["error"] = (
                f"firewall {fw_ip}: no NAT rule matched for this flow"
                if ("<rules>" in body and "</rules>" in body)
                else f"firewall {fw_ip}: could not parse NAT rule from response"
            )
            if debug:
                debug_responses["nat_policy_match"] = _format_first_nat_rule_response(None)
            if debug and debug_responses:
                out["debug"] = debug_responses
                return out
            continue
        out["rule_name"] = rule_name
        if debug:
            debug_responses["nat_policy_match"] = _format_first_nat_rule_response(rule_name)
        out["firewall_hostname"] = (fw.get("hostname") or "").strip() or fw_ip
        out["firewall_ip"] = fw_ip

        # Step 4: Get rule config to find translated IP(s)
        safe_name = (rule_name or "").replace('"', '""')
        xpath = (
            "/config/devices/entry[@name='localhost.localdomain']"
            "/vsys/entry[@name='vsys1']/rulebase/nat/rules/entry[@name=\""
            + safe_name
            + "\"]"
        )
        params2 = {"type": "config", "action": "get", "key": api_key, "xpath": xpath}
        rule_config_body = ""
        try:
            r2 = requests.get(
                base, params=params2, verify=False, timeout=timeout
            )
            r2.raise_for_status()
            rule_config_body = r2.text
            ips = _find_translated_ips_in_rule_config(rule_config_body)
            if ips:
                out["translated_ips"] = ips
            if debug:
                debug_responses["nat_rule_config"] = _format_translated_address_response(rule_name, ips)
        except requests.exceptions.RequestException as e:
            if debug:
                debug_responses["nat_rule_config_error"] = str(e)
        if debug and debug_responses:
            out["debug"] = debug_responses
        out["ok"] = True
        return out

    out["error"] = out["error"] or "no firewall with valid API key in scope"
    return out
