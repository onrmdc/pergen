"""Unit tests for ``backend.nat_lookup.palo_alto.api``.

Covers the NAT-policy-match and rule-config HTTP helpers plus the inventory
predicates extracted from the legacy ``nat_lookup`` god-module:

* ``build_nat_policy_match_cmd`` / ``build_rule_config_xpath`` — pure
  template + XPath escaping (audit H7).
* ``call_nat_policy_match`` / ``call_nat_rule_config`` — single-shot HTTP
  exchanges with the X-PAN-KEY header contract (Phase 13 / A02).
* ``is_palo_alto`` / ``filter_palo_alto_firewalls`` — inventory predicates.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.nat_lookup.palo_alto.api import (
    NAT_POLICY_MATCH_CMD_TEMPLATE,
    build_nat_policy_match_cmd,
    build_rule_config_xpath,
    call_nat_policy_match,
    call_nat_rule_config,
    filter_palo_alto_firewalls,
    is_palo_alto,
)


# --------------------------------------------------------------------------- #
# build_nat_policy_match_cmd                                                   #
# --------------------------------------------------------------------------- #


class TestBuildNatPolicyMatchCmd:
    def test_template_substitution(self) -> None:
        cmd = build_nat_policy_match_cmd("10.1.1.1", "8.8.8.8")
        assert "<source>10.1.1.1</source>" in cmd
        assert "<destination>8.8.8.8</destination>" in cmd
        assert "<protocol>6</protocol>" in cmd
        assert "<destination-port>443</destination-port>" in cmd

    def test_template_constant_unchanged(self) -> None:
        # Sanity check for the template constant itself (it's part of the API).
        assert "{src_ip}" in NAT_POLICY_MATCH_CMD_TEMPLATE
        assert "{dest_ip}" in NAT_POLICY_MATCH_CMD_TEMPLATE


# --------------------------------------------------------------------------- #
# build_rule_config_xpath                                                      #
# --------------------------------------------------------------------------- #


class TestBuildRuleConfigXpath:
    def test_default_double_quote_wrap(self) -> None:
        x = build_rule_config_xpath("My-Rule")
        assert '[@name="My-Rule"]' in x
        assert "/config/devices/" in x
        assert "rulebase/nat/rules/entry" in x

    def test_uses_single_quote_when_name_has_double(self) -> None:
        x = build_rule_config_xpath('R"name')
        assert "[@name='R\"name']" in x

    def test_returns_none_when_both_quote_types_present(self) -> None:
        # Audit H7: refuse to build a broken xpath.
        assert build_rule_config_xpath("R'with\"both") is None

    def test_empty_rule_name(self) -> None:
        x = build_rule_config_xpath("")
        assert '[@name=""]' in x


# --------------------------------------------------------------------------- #
# call_nat_policy_match                                                        #
# --------------------------------------------------------------------------- #


def _make_requests_mock(text="<ok/>", raise_exc: Exception | None = None):
    """Build a fake ``requests``-like module."""
    mod = MagicMock()
    if raise_exc is None:
        resp = MagicMock()
        resp.text = text
        resp.raise_for_status = MagicMock()
        mod.get.return_value = resp
    else:
        # Make the .get() raise exc; the helper catches RequestException.
        mod.get.side_effect = raise_exc
    # Build an ``exceptions.RequestException`` namespace that the helper
    # can use to filter for "expected" errors.
    mod.exceptions = MagicMock()
    mod.exceptions.RequestException = Exception  # broad enough for tests
    return mod


class TestCallNatPolicyMatch:
    def test_success_returns_body_and_no_exc(self) -> None:
        mod = _make_requests_mock(text="<response>ok</response>")
        body, exc = call_nat_policy_match(
            mod, "https://fw/api/", "<cmd/>", "APIKEY", tls_verify=True, timeout=15
        )
        assert body == "<response>ok</response>"
        assert exc is None

    def test_passes_api_key_via_header_not_url(self) -> None:
        mod = _make_requests_mock()
        call_nat_policy_match(
            mod, "https://fw/api/", "<cmd/>", "MYKEY", tls_verify=False, timeout=10
        )
        _, kwargs = mod.get.call_args
        # Phase 13 / A02 — key must travel in X-PAN-KEY header, never URL.
        assert kwargs["headers"] == {"X-PAN-KEY": "MYKEY"}
        assert "key" not in (kwargs.get("params") or {})
        assert kwargs["params"] == {"type": "op", "cmd": "<cmd/>"}
        assert kwargs["verify"] is False
        assert kwargs["timeout"] == 10

    def test_returns_exc_on_request_exception(self) -> None:
        boom = Exception("connection refused")
        mod = _make_requests_mock(raise_exc=boom)
        body, exc = call_nat_policy_match(
            mod, "https://fw/api/", "<cmd/>", "K", tls_verify=True, timeout=5
        )
        assert body is None
        assert exc is boom

    def test_propagates_raise_for_status_failure(self) -> None:
        mod = _make_requests_mock()
        # Wire raise_for_status to raise; helper should catch via exceptions tree.
        err = Exception("403")
        mod.get.return_value.raise_for_status.side_effect = err
        body, exc = call_nat_policy_match(
            mod, "https://fw/api/", "<cmd/>", "K", tls_verify=True, timeout=5
        )
        assert body is None
        assert exc is err


# --------------------------------------------------------------------------- #
# call_nat_rule_config                                                         #
# --------------------------------------------------------------------------- #


class TestCallNatRuleConfig:
    def test_success_returns_body(self) -> None:
        mod = _make_requests_mock(text="<entry>x</entry>")
        body, exc = call_nat_rule_config(
            mod, "https://fw/api/", "/xpath", "K", tls_verify=True, timeout=15
        )
        assert body == "<entry>x</entry>"
        assert exc is None

    def test_passes_xpath_in_params_and_key_in_header(self) -> None:
        mod = _make_requests_mock()
        call_nat_rule_config(
            mod,
            "https://fw/api/",
            "/some/xpath",
            "MYKEY",
            tls_verify=True,
            timeout=15,
        )
        _, kwargs = mod.get.call_args
        assert kwargs["params"] == {
            "type": "config",
            "action": "get",
            "xpath": "/some/xpath",
        }
        assert kwargs["headers"] == {"X-PAN-KEY": "MYKEY"}

    def test_returns_exc_on_request_exception(self) -> None:
        err = Exception("net err")
        mod = _make_requests_mock(raise_exc=err)
        body, exc = call_nat_rule_config(
            mod, "https://fw/api/", "/xp", "K", tls_verify=True, timeout=10
        )
        assert body is None
        assert exc is err


# --------------------------------------------------------------------------- #
# is_palo_alto                                                                 #
# --------------------------------------------------------------------------- #


class TestIsPaloAlto:
    @pytest.mark.parametrize(
        "vendor",
        ["palo-alto", "Palo Alto", "PALO-ALTO", "panos", "  palo alto  "],
    )
    def test_vendor_matches(self, vendor) -> None:
        assert is_palo_alto({"vendor": vendor, "model": ""}) is True

    def test_panos_model_matches(self) -> None:
        assert is_palo_alto({"vendor": "other", "model": "panos"}) is True

    @pytest.mark.parametrize(
        "vendor,model",
        [("cisco", "asa"), ("arista", "eos"), ("", ""), ("juniper", "srx")],
    )
    def test_non_matches(self, vendor, model) -> None:
        assert is_palo_alto({"vendor": vendor, "model": model}) is False


# --------------------------------------------------------------------------- #
# filter_palo_alto_firewalls                                                   #
# --------------------------------------------------------------------------- #


class TestFilterPaloAltoFirewalls:
    @pytest.fixture
    def devices(self) -> list:
        return [
            {"vendor": "palo-alto", "fabric": "F1", "site": "Mars", "model": ""},
            {"vendor": "panos", "fabric": "F1", "site": "Venus", "model": ""},
            {"vendor": "cisco", "fabric": "F1", "site": "Mars", "model": "asa"},
            {"vendor": "other", "fabric": "F1", "site": "Mars", "model": "panos"},
            {"vendor": "palo-alto", "fabric": "F2", "site": "Mars", "model": ""},
        ]

    def test_filters_to_fabric_site_and_palo_alto(self, devices) -> None:
        out = filter_palo_alto_firewalls(devices, "F1", "Mars")
        # Should keep palo-alto + panos-model devices in F1/Mars only.
        assert len(out) == 2
        for d in out:
            assert d["fabric"] == "F1"
            assert d["site"] == "Mars"

    def test_case_insensitive_match(self, devices) -> None:
        out = filter_palo_alto_firewalls(devices, "f1", "MARS")
        assert len(out) == 2

    def test_no_matches_returns_empty(self, devices) -> None:
        out = filter_palo_alto_firewalls(devices, "F99", "Pluto")
        assert out == []

    def test_empty_input_returns_empty(self) -> None:
        assert filter_palo_alto_firewalls([], "F1", "Mars") == []
