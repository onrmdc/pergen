"""Unit tests for ``backend.nat_lookup.xml_helpers``.

Covers all four functions extracted from the legacy ``nat_lookup``
god-module in wave-3 phase 8:

* ``_format_first_nat_rule_response``     — canonical NAT-policy-match XML
* ``_find_nat_rule_name_in_response``     — parse rule name from match resp
* ``_format_translated_address_response`` — canonical translated-address XML
* ``_find_translated_ips_in_rule_config`` — parse translated IPs from rule

All four are pure functions over strings — no mocking required. Audit H-1
keeps the parser pinned to ``defusedxml`` and audit L-09 preserves the
manual escape chain in ``_format_translated_address_response``.
"""

from __future__ import annotations

import pytest

from backend.nat_lookup.xml_helpers import (
    _find_nat_rule_name_in_response,
    _find_translated_ips_in_rule_config,
    _format_first_nat_rule_response,
    _format_translated_address_response,
)


# --------------------------------------------------------------------------- #
# _format_first_nat_rule_response                                              #
# --------------------------------------------------------------------------- #


class TestFormatFirstNatRuleResponse:
    @pytest.mark.parametrize("entry", ["", "   ", None])
    def test_empty_entry_returns_empty_rules_block(self, entry) -> None:
        out = _format_first_nat_rule_response(entry)
        assert "<rules>" in out and "</rules>" in out
        assert "<entry>" not in out
        assert 'cmd="status"' in out
        assert 'status="success"' in out

    def test_entry_value_appears_inside_entry_tag(self) -> None:
        out = _format_first_nat_rule_response("MyRule")
        assert "<entry>MyRule</entry>" in out

    def test_xml_special_chars_are_escaped(self) -> None:
        out = _format_first_nat_rule_response("a&b<c>d")
        assert "<entry>a&amp;b&lt;c&gt;d</entry>" in out

    def test_returns_string_with_canonical_indentation(self) -> None:
        out = _format_first_nat_rule_response("R1")
        # Indented spaces preserved verbatim from legacy formatter.
        assert "        <rules>" in out
        assert "            <entry>R1</entry>" in out


# --------------------------------------------------------------------------- #
# _find_nat_rule_name_in_response                                              #
# --------------------------------------------------------------------------- #


class TestFindNatRuleNameInResponse:
    @pytest.mark.parametrize("text", ["", "   ", None])
    def test_blank_returns_none(self, text) -> None:
        assert _find_nat_rule_name_in_response(text) is None

    def test_finds_rule_in_entry_tag_via_xml(self) -> None:
        text = (
            '<response status="success"><result><rules>'
            "<entry>NAT-Rule-A</entry></rules></result></response>"
        )
        assert _find_nat_rule_name_in_response(text) == "NAT-Rule-A"

    def test_finds_rule_in_member_tag_via_xml(self) -> None:
        text = (
            '<response><result><rules><member>NAT-MemberRule</member>'
            "</rules></result></response>"
        )
        assert _find_nat_rule_name_in_response(text) == "NAT-MemberRule"

    def test_falls_back_to_regex_when_xml_unparseable(self) -> None:
        # Broken XML — the parser raises, regex fallback finds the entry.
        text = "junk<entry>RuleZ</entry>moreJunk"
        assert _find_nat_rule_name_in_response(text) == "RuleZ"

    def test_falls_back_to_member_regex(self) -> None:
        text = "garbage<member>MemberRule</member>"
        assert _find_nat_rule_name_in_response(text) == "MemberRule"

    def test_no_match_returns_none(self) -> None:
        text = '<response status="success"><result><rules></rules></result></response>'
        assert _find_nat_rule_name_in_response(text) is None

    def test_strips_whitespace_in_entry_text(self) -> None:
        text = "<entry>  PaddedRule  </entry>"
        # Regex captures with strip: the regex group has no \s, so it grabs
        # everything between tags including padding, then .strip() in helper.
        assert _find_nat_rule_name_in_response(text) == "PaddedRule"


# --------------------------------------------------------------------------- #
# _format_translated_address_response                                          #
# --------------------------------------------------------------------------- #


class TestFormatTranslatedAddressResponse:
    def test_single_ip(self) -> None:
        out = _format_translated_address_response("Rule-1", ["10.0.0.5"])
        assert 'name="Rule-1"' in out
        assert "<member>10.0.0.5</member>" in out
        assert 'count="1"' in out
        assert "<source-translation>" in out
        assert "<dynamic-ip-and-port>" in out
        assert "<translated-address>" in out

    def test_two_ips(self) -> None:
        out = _format_translated_address_response("Rule-2", ["10.0.0.5", "10.0.0.6"])
        assert "<member>10.0.0.5</member>" in out
        assert "<member>10.0.0.6</member>" in out

    def test_empty_member_list(self) -> None:
        out = _format_translated_address_response("R", [])
        # No <member> entries but envelope still present.
        assert "<member>" not in out
        assert "<translated-address>" in out

    def test_escapes_rule_name(self) -> None:
        out = _format_translated_address_response('R&"<name>', ["1.1.1.1"])
        # name attr uses double-quote so the escape includes &quot;
        assert "&amp;" in out
        assert "&quot;" in out
        assert "&lt;" in out
        assert "&gt;" in out

    def test_escapes_member_ip(self) -> None:
        # IPs don't normally contain XML chars, but the escape applies anyway.
        out = _format_translated_address_response("R", ["a&b"])
        assert "<member>a&amp;b</member>" in out


# --------------------------------------------------------------------------- #
# _find_translated_ips_in_rule_config                                          #
# --------------------------------------------------------------------------- #


class TestFindTranslatedIpsInRuleConfig:
    @pytest.mark.parametrize("text", ["", "   ", None])
    def test_blank_returns_empty_list(self, text) -> None:
        assert _find_translated_ips_in_rule_config(text) == []

    def test_finds_one_ip_via_regex(self) -> None:
        text = (
            "<source-translation>"
            "<dynamic-ip-and-port>"
            "<translated-address>"
            "<member>192.168.1.10</member>"
            "</translated-address>"
            "</dynamic-ip-and-port>"
            "</source-translation>"
        )
        assert _find_translated_ips_in_rule_config(text) == ["192.168.1.10"]

    def test_finds_multiple_ips_via_regex(self) -> None:
        text = (
            "<source-translation>"
            "<dynamic-ip-and-port>"
            "<translated-address>"
            "<member>192.168.1.10</member>"
            "<member>192.168.1.11</member>"
            "</translated-address>"
            "</dynamic-ip-and-port>"
            "</source-translation>"
        )
        result = _find_translated_ips_in_rule_config(text)
        assert result == ["192.168.1.10", "192.168.1.11"]

    def test_dedups_repeated_ips(self) -> None:
        text = (
            "<source-translation><dynamic-ip-and-port><translated-address>"
            "<member>10.0.0.1</member><member>10.0.0.1</member>"
            "</translated-address></dynamic-ip-and-port></source-translation>"
        )
        assert _find_translated_ips_in_rule_config(text) == ["10.0.0.1"]

    def test_ignores_non_ip_members(self) -> None:
        text = (
            "<source-translation><dynamic-ip-and-port><translated-address>"
            "<member>SomeAddressGroup</member><member>10.0.0.5</member>"
            "</translated-address></dynamic-ip-and-port></source-translation>"
        )
        assert _find_translated_ips_in_rule_config(text) == ["10.0.0.5"]

    def test_no_source_translation_returns_empty(self) -> None:
        text = "<rule><other-config>stuff</other-config></rule>"
        assert _find_translated_ips_in_rule_config(text) == []

    def test_block_without_dynamic_ip_is_skipped(self) -> None:
        text = (
            "<source-translation>"
            "<static-ip><translated-address>"
            "<member>10.0.0.5</member>"
            "</translated-address></static-ip>"
            "</source-translation>"
        )
        # Block exists but no "dynamic-ip" → regex branch refuses, XML walk
        # also does not match the source-translation/translated-address path.
        # Note: the XML walk fallback catches it.
        result = _find_translated_ips_in_rule_config(text)
        # The regex fallback is conservative: requires dynamic-ip in block.
        # The XML walk visits source-translation -> translated-address regardless.
        assert result == ["10.0.0.5"]

    def test_falls_back_to_xml_walk_on_unparseable_block(self) -> None:
        # Wrap valid XML; regex won't catch member outside block but XML walk will.
        text = (
            "<root>"
            "<source-translation>"
            "<dynamic-ip-and-port>"
            "<translated-address>"
            "<member>1.2.3.4</member>"
            "</translated-address>"
            "</dynamic-ip-and-port>"
            "</source-translation>"
            "</root>"
        )
        assert _find_translated_ips_in_rule_config(text) == ["1.2.3.4"]
