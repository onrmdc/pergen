"""
NAT-lookup orchestration: leaf-resolution → firewall scoping → per-FW API loop.

Behaviour is preserved verbatim from the original
``backend/nat_lookup.py::nat_lookup``. The orchestrator looks up
``find_leaf_module``, ``load_inventory``, ``get_devices_by_tag`` and
``requests`` through the ``backend.nat_lookup`` package shim at call time,
so existing test patches like
``unittest.mock.patch("backend.nat_lookup.find_leaf_module.find_leaf", ...)``
or ``patch.object(nl.requests, "get", ...)`` reach the orchestration code
in this module unchanged after the god-module split.
"""

from __future__ import annotations

from typing import Any

from backend.nat_lookup.ip_helpers import _is_valid_ip
from backend.nat_lookup.palo_alto.api import (
    build_nat_policy_match_cmd,
    build_rule_config_xpath,
    call_nat_policy_match,
    call_nat_rule_config,
    filter_palo_alto_firewalls,
)
from backend.nat_lookup.xml_helpers import (
    _find_nat_rule_name_in_response,
    _find_translated_ips_in_rule_config,
    _format_first_nat_rule_response,
    _format_translated_address_response,
)
from backend.runners.runner import _get_credentials

__all__ = ["nat_lookup"]


def _empty_result() -> dict[str, Any]:
    return {
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


def _resolve_fabric_site(
    out: dict[str, Any],
    src_ip: str,
    secret_key: str,
    cred_store_module: Any,
    inventory_path: str | None,
    fabric: str,
    site: str,
    leaf_checked_devices: list | None,
) -> tuple[str, str, bool]:
    """Resolve fabric+site for ``src_ip``. Returns ``(fabric, site, ok)``.

    When ``ok`` is False, ``out["error"]`` has been populated and the
    caller should return ``out`` immediately.
    """
    if fabric and site:
        out["leaf_checked_devices"] = leaf_checked_devices or []
        return fabric, site, True

    # Late binding so test patches on the shim land here.
    from backend import nat_lookup as _shim

    leaf_result = _shim.find_leaf_module.find_leaf(
        src_ip, secret_key, cred_store_module, inventory_path
    )
    out["leaf_checked_devices"] = leaf_result.get("checked_devices") or []
    if not leaf_result.get("found"):
        out["error"] = leaf_result.get("error") or "source IP not found on any leaf"
        return "", "", False
    fabric = (leaf_result.get("fabric") or "").strip()
    site = (leaf_result.get("site") or "").strip()
    if not fabric or not site:
        out["error"] = "leaf fabric/site could not be determined"
        return "", "", False
    return fabric, site, True


def _try_one_firewall(
    fw: dict,
    src_ip: str,
    dest_ip: str,
    secret_key: str,
    cred_store_module: Any,
    timeout: int,
    debug: bool,
    out: dict[str, Any],
) -> tuple[bool, bool]:
    """Try a single firewall. Returns ``(handled, should_return)``.

    * ``handled=True`` means we got a definitive answer (success or a
      hard error that should propagate). Caller should populate ``out``
      from the side effects already applied and return.
    * ``handled=False`` + ``should_return=False`` means try the next
      firewall (transient failure: bad creds / connection error /
      unparseable response in non-debug mode).
    * ``handled=False`` + ``should_return=True`` means a debug-mode
      early return after a parse failure (legacy semantics preserved).
    """
    # Late binding so test patches on the shim land here.
    from backend import nat_lookup as _shim

    fw_ip = (fw.get("ip") or "").strip()
    cred_name = (fw.get("credential") or "").strip()
    _, api_key = _get_credentials(cred_name, secret_key, cred_store_module)
    if not api_key:
        return False, False

    base = f"https://{fw_ip}/api/"
    debug_responses: dict[str, str] = {}

    cmd_match = build_nat_policy_match_cmd(src_ip, dest_ip)
    body, exc = call_nat_policy_match(
        _shim.requests,
        base,
        cmd_match,
        api_key,
        tls_verify=_shim.DEVICE_TLS_VERIFY,
        timeout=timeout,
    )
    if exc is not None:
        out["error"] = f"firewall {fw_ip}: connection failed"
        if debug:
            # Even in debug, scrub any incidental key occurrence and
            # never echo the underlying exception payload (which can
            # contain prepared-URL fragments on some requests/urllib3
            # versions).
            debug_responses["nat_policy_match_error"] = type(exc).__name__
            out["debug"] = debug_responses
        return False, False
    body = body or ""
    if debug:
        debug_responses["nat_policy_match"] = body

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
            return False, True
        return False, False

    out["rule_name"] = rule_name
    if debug:
        debug_responses["nat_policy_match"] = _format_first_nat_rule_response(rule_name)
    out["firewall_hostname"] = (fw.get("hostname") or "").strip() or fw_ip
    out["firewall_ip"] = fw_ip

    # Step 4: Get rule config to find translated IP(s)
    # Audit H7 (python-review): proper XPath escaping. XPath 1.0 has
    # no quote-escape, so we must alternate quote styles. Reject names
    # that contain BOTH quote types (no Palo Alto rule legitimately
    # does — and we'd rather refuse than build a broken xpath).
    xpath = build_rule_config_xpath(rule_name)
    if xpath is None:
        out["error"] = (
            f"firewall {fw_ip}: rule name {rule_name!r} contains both "
            "quote types and cannot be safely encoded in XPath"
        )
        if debug and debug_responses:
            out["debug"] = debug_responses
        return True, True

    rule_body, rule_exc = call_nat_rule_config(
        _shim.requests,
        base,
        xpath,
        api_key,
        tls_verify=_shim.DEVICE_TLS_VERIFY,
        timeout=timeout,
    )
    if rule_exc is not None:
        if debug:
            debug_responses["nat_rule_config_error"] = type(rule_exc).__name__
    else:
        ips = _find_translated_ips_in_rule_config(rule_body or "")
        if ips:
            out["translated_ips"] = ips
        if debug:
            debug_responses["nat_rule_config"] = _format_translated_address_response(
                rule_name, ips
            )
    if debug and debug_responses:
        out["debug"] = debug_responses
    out["ok"] = True
    return True, True


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
    # Late binding so test patches on the shim land here.
    from backend import nat_lookup as _shim

    src_ip = (src_ip or "").strip()
    dest_ip = (dest_ip or "").strip() or "8.8.8.8"
    out = _empty_result()

    if not _is_valid_ip(src_ip):
        out["error"] = "invalid source IP"
        return out
    if not _is_valid_ip(dest_ip):
        out["error"] = "invalid destination IP"
        return out

    fabric = (fabric or "").strip()
    site = (site or "").strip()
    fabric, site, ok = _resolve_fabric_site(
        out,
        src_ip,
        secret_key,
        cred_store_module,
        inventory_path,
        fabric,
        site,
        leaf_checked_devices,
    )
    if not ok:
        return out
    out["fabric"] = fabric
    out["site"] = site

    # Step 2: Get firewalls with tag natlookup, same fabric+site, Palo Alto
    # (vendor palo-alto or model panos). load_inventory + get_devices_by_tag
    # are looked up through the shim so test patches land correctly.
    devices = _shim.load_inventory(inventory_path)
    nat_devices = _shim.get_devices_by_tag("natlookup", devices)
    firewalls = filter_palo_alto_firewalls(nat_devices, fabric, site)
    if not firewalls:
        out["error"] = (
            f"no Palo Alto firewall with tag 'natlookup' in fabric={fabric}, site={site}"
        )
        return out

    # Step 3 + 4: per-firewall NAT policy match → rule config.
    for fw in firewalls:
        handled, should_return = _try_one_firewall(
            fw, src_ip, dest_ip, secret_key, cred_store_module, timeout, debug, out
        )
        if handled or should_return:
            return out

    out["error"] = out["error"] or "no firewall with valid API key in scope"
    return out
