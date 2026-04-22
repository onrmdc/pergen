"""
XML parse + format helpers for Palo Alto NAT lookup responses.

These four helpers were extracted verbatim from the legacy
``backend/nat_lookup.py`` (Phase 8 of the wave-3 refactor — see
``docs/refactor/wave3_roadmap.md``):

* :func:`_format_first_nat_rule_response`     — canonical NAT-policy-match XML
* :func:`_find_nat_rule_name_in_response`     — parse rule name from match resp
* :func:`_format_translated_address_response` — canonical translated-address XML
* :func:`_find_translated_ips_in_rule_config` — parse translated IPs from rule

Audit notes preserved:

* H-1: ``defusedxml`` is a HARD requirement. The previous try/except fallback
  to the stdlib ``xml.etree`` parser (vulnerable to billion-laughs / XXE) has
  been removed — a missing dependency now raises ``ImportError`` at import
  time instead of silently degrading the security posture.
* L-09: ``_format_translated_address_response`` still uses the manual
  ``.replace("&", "&amp;")…`` escape chain rather than
  ``xml.sax.saxutils.escape``. Behaviour-preserving refactor only — the
  paired test+code migration is deferred to a future PR.
"""

from __future__ import annotations

import re

# Audit H-1: ``defusedxml`` is a HARD requirement (declared in
# requirements.txt). Previously this import was wrapped in try/except and
# silently fell back to the stdlib xml.etree parser, which is vulnerable
# to billion-laughs / XXE attacks. The fallback was removed so a missing
# dependency raises ImportError at module-load time instead of degrading
# the security posture at runtime.
from defusedxml import ElementTree as ET  # type: ignore[import-not-found]
from defusedxml.common import DefusedXmlException as _DefusedXmlError
from defusedxml.ElementTree import ParseError as _ETParseError

# Backwards-compat alias — kept only for any external imports of the old name.
_DefusedXmlException = _DefusedXmlError


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
        root = ET.fromstring(text)  # noqa: S314 — ET is defusedxml.ElementTree (phase 13)
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
    except (_ETParseError, _DefusedXmlException):
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
    """Format translated-address member IP(s) as canonical XML (1 or 2 IPs).

    NOTE (audit L-09): the manual ``.replace`` escape chain below is preserved
    verbatim from the legacy module. Migrating to ``xml.sax.saxutils.escape``
    is a paired test+code change tracked separately and deliberately out of
    scope for the wave-3 god-module split.
    """
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
            root = ET.fromstring(text)  # noqa: S314 — ET is defusedxml.ElementTree (phase 13)
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
        except (_ETParseError, _DefusedXmlException):
            pass
    return nat_ips


__all__ = [
    "_DefusedXmlException",
    "_format_first_nat_rule_response",
    "_find_nat_rule_name_in_response",
    "_format_translated_address_response",
    "_find_translated_ips_in_rule_config",
]
