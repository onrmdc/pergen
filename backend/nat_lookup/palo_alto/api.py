"""
Palo Alto Panorama / firewall API helpers for NAT-lookup.

Encapsulates the two per-firewall HTTP exchanges that the NAT-lookup
orchestrator performs:

1. ``op`` request — ``test nat-policy-match`` to discover the matched rule
   name for a ``src_ip -> dest_ip`` flow.
2. ``config`` request — ``get`` on the rule's xpath to extract the
   ``source-translation -> translated-address -> member`` IP list.

Both helpers accept the ``requests`` module as a parameter so that the
``backend.nat_lookup.service`` orchestrator can resolve it through the
package shim at call time. This keeps
``unittest.mock.patch.object(backend.nat_lookup.requests, "get", ...)``
working unchanged after the god-module split.

Audit notes preserved verbatim from the legacy module:

* Phase 13 / A02 (TEST_RESULTS.md): the API key MUST travel in the
  ``X-PAN-KEY`` header, never the URL query string. Otherwise it leaks
  into connection-error messages, debug envelopes, and request logs.
* Audit H7 (python-review): XPath escaping. XPath 1.0 has no quote
  escape, so we alternate quote styles. Names containing BOTH quote
  types are rejected rather than building a broken xpath.
"""

from __future__ import annotations

from typing import Any, Callable

NAT_POLICY_MATCH_CMD_TEMPLATE = (
    "<test><nat-policy-match>"
    "<source>{src_ip}</source><destination>{dest_ip}</destination>"
    "<protocol>6</protocol><destination-port>443</destination-port>"
    "</nat-policy-match></test>"
)


def build_nat_policy_match_cmd(src_ip: str, dest_ip: str) -> str:
    """Build the ``test nat-policy-match`` op-command XML payload."""
    return NAT_POLICY_MATCH_CMD_TEMPLATE.format(src_ip=src_ip, dest_ip=dest_ip)


def build_rule_config_xpath(rule_name: str) -> str | None:
    """Build a Panorama xpath for fetching a NAT rule's config.

    Returns ``None`` if ``rule_name`` contains both single and double
    quotes — XPath 1.0 has no quote-escape, and rather than emit a
    broken expression we refuse to build one (audit H7).
    """
    if '"' in (rule_name or "") and "'" in (rule_name or ""):
        return None
    quote = "'" if '"' in (rule_name or "") else '"'
    return (
        "/config/devices/entry[@name='localhost.localdomain']"
        "/vsys/entry[@name='vsys1']/rulebase/nat/rules/entry"
        f"[@name={quote}{rule_name}{quote}]"
    )


def call_nat_policy_match(
    requests_module: Any,
    base_url: str,
    cmd: str,
    api_key: str,
    *,
    tls_verify: bool,
    timeout: int,
) -> tuple[str | None, Exception | None]:
    """Execute the NAT-policy-match op request.

    Returns ``(body, None)`` on success or ``(None, exc)`` on a requests
    exception. The API key travels in the ``X-PAN-KEY`` header, never
    the URL (Phase 13 / A02).
    """
    params = {"type": "op", "cmd": cmd}
    headers = {"X-PAN-KEY": api_key}
    try:
        r = requests_module.get(
            base_url, params=params, headers=headers, verify=tls_verify, timeout=timeout
        )
        r.raise_for_status()
        return r.text, None
    except requests_module.exceptions.RequestException as e:
        return None, e


def call_nat_rule_config(
    requests_module: Any,
    base_url: str,
    xpath: str,
    api_key: str,
    *,
    tls_verify: bool,
    timeout: int,
) -> tuple[str | None, Exception | None]:
    """Execute the NAT rule-config ``get`` request.

    Returns ``(body, None)`` on success or ``(None, exc)`` on a requests
    exception. Same X-PAN-KEY-header contract as
    :func:`call_nat_policy_match`.
    """
    params = {"type": "config", "action": "get", "xpath": xpath}
    headers = {"X-PAN-KEY": api_key}
    try:
        r = requests_module.get(
            base_url, params=params, headers=headers, verify=tls_verify, timeout=timeout
        )
        r.raise_for_status()
        return r.text, None
    except requests_module.exceptions.RequestException as e:
        return None, e


def is_palo_alto(d: dict) -> bool:
    """Inventory predicate — vendor is palo-alto / palo alto, or model is panos."""
    v = (d.get("vendor") or "").strip().lower()
    m = (d.get("model") or "").strip().lower()
    return v in ("palo-alto", "palo alto", "panos") or m == "panos"


def filter_palo_alto_firewalls(
    nat_devices: list[dict],
    fabric: str,
    site: str,
) -> list[dict]:
    """Return Palo Alto firewalls in inventory matching ``fabric`` + ``site``."""
    fabric_lower = fabric.lower()
    site_lower = site.lower()
    return [
        d
        for d in nat_devices
        if (d.get("fabric") or "").strip().lower() == fabric_lower
        and (d.get("site") or "").strip().lower() == site_lower
        and is_palo_alto(d)
    ]


__all__ = [
    "NAT_POLICY_MATCH_CMD_TEMPLATE",
    "build_nat_policy_match_cmd",
    "build_rule_config_xpath",
    "call_nat_policy_match",
    "call_nat_rule_config",
    "is_palo_alto",
    "filter_palo_alto_firewalls",
]


# --------------------------------------------------------------------------- #
# Convenience: fully-typed callable signatures for the service layer.         #
# --------------------------------------------------------------------------- #

CallNatPolicyMatch = Callable[..., tuple[str | None, Exception | None]]
CallNatRuleConfig = Callable[..., tuple[str | None, Exception | None]]
