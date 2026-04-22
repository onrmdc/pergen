"""Unit tests for ``backend.nat_lookup.service._try_one_firewall``.

The orchestration layer was extracted into ``service.py`` in wave-3 phase 8.
``_try_one_firewall`` is the per-firewall HTTP loop: it invokes the
``op`` request, parses the rule name, then invokes the ``config`` request
to extract translated IPs.

The function uses late-bound module references (``_shim.requests``,
``_shim.DEVICE_TLS_VERIFY``) so all patches target the
``backend.nat_lookup`` shim namespace.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.nat_lookup.service import _try_one_firewall


@pytest.fixture
def fw() -> dict:
    return {
        "hostname": "fw-1",
        "ip": "192.168.99.1",
        "credential": "fwcred",
        "vendor": "palo-alto",
        "fabric": "F1",
        "site": "Mars",
    }


@pytest.fixture
def out() -> dict:
    """Fresh empty out envelope to mutate."""
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


def _patch_creds(api_key: str = "the-key"):
    """Patch _get_credentials so the function-level lookup returns ``("", api_key)``."""
    return patch(
        "backend.nat_lookup.service._get_credentials",
        return_value=("", api_key),
    )


class TestTryOneFirewallNoCredential:
    def test_skips_when_api_key_blank(self, fw, out) -> None:
        with _patch_creds(api_key=""):
            handled, should_return = _try_one_firewall(
                fw, "10.0.0.1", "8.8.8.8", "secret", MagicMock(), 15, False, out
            )
        # No credential → caller continues to next firewall.
        assert handled is False
        assert should_return is False
        # No mutation to out.
        assert out["rule_name"] == ""
        assert out["error"] is None


class TestTryOneFirewallPolicyMatchConnectionFailure:
    def test_connection_exception_sets_error_returns_skip(self, fw, out) -> None:
        boom = ConnectionError("net down")
        with _patch_creds(), patch(
            "backend.nat_lookup.service.call_nat_policy_match",
            return_value=(None, boom),
        ):
            handled, should_return = _try_one_firewall(
                fw, "10.0.0.1", "8.8.8.8", "secret", MagicMock(), 15, False, out
            )
        assert handled is False
        assert should_return is False
        assert "connection failed" in out["error"]
        assert "192.168.99.1" in out["error"]
        assert out["debug"] is None  # debug=False

    def test_connection_exception_with_debug_records_error_type(self, fw, out) -> None:
        boom = ConnectionError("net down")
        with _patch_creds(), patch(
            "backend.nat_lookup.service.call_nat_policy_match",
            return_value=(None, boom),
        ):
            _try_one_firewall(
                fw, "10.0.0.1", "8.8.8.8", "secret", MagicMock(), 15, True, out
            )
        assert out["debug"] is not None
        assert out["debug"]["nat_policy_match_error"] == "ConnectionError"
        # Underlying message must NOT leak into debug payload (Phase 13).
        assert "net down" not in str(out["debug"])


class TestTryOneFirewallNoRuleMatch:
    def test_response_with_rules_envelope_sets_no_match_error(self, fw, out) -> None:
        body = "<response><result><rules></rules></result></response>"
        with _patch_creds(), patch(
            "backend.nat_lookup.service.call_nat_policy_match",
            return_value=(body, None),
        ), patch(
            "backend.nat_lookup.service._find_nat_rule_name_in_response",
            return_value=None,
        ):
            handled, should_return = _try_one_firewall(
                fw, "10.0.0.1", "8.8.8.8", "secret", MagicMock(), 15, False, out
            )
        assert handled is False
        assert should_return is False
        assert "no NAT rule matched" in out["error"]

    def test_unparseable_response_sets_parse_error(self, fw, out) -> None:
        body = "junk-without-rules-tags"
        with _patch_creds(), patch(
            "backend.nat_lookup.service.call_nat_policy_match",
            return_value=(body, None),
        ), patch(
            "backend.nat_lookup.service._find_nat_rule_name_in_response",
            return_value=None,
        ):
            handled, should_return = _try_one_firewall(
                fw, "10.0.0.1", "8.8.8.8", "secret", MagicMock(), 15, False, out
            )
        assert handled is False
        assert "could not parse NAT rule" in out["error"]

    def test_debug_mode_returns_should_return_true(self, fw, out) -> None:
        body = "junk"
        with _patch_creds(), patch(
            "backend.nat_lookup.service.call_nat_policy_match",
            return_value=(body, None),
        ), patch(
            "backend.nat_lookup.service._find_nat_rule_name_in_response",
            return_value=None,
        ):
            handled, should_return = _try_one_firewall(
                fw, "10.0.0.1", "8.8.8.8", "secret", MagicMock(), 15, True, out
            )
        # Debug-mode early return after parse failure.
        assert handled is False
        assert should_return is True
        assert out["debug"] is not None
        assert "nat_policy_match" in out["debug"]


class TestTryOneFirewallRuleNameWithBadXpath:
    def test_quote_collision_returns_handled_with_error(self, fw, out) -> None:
        rule = "name'with\"both"
        with _patch_creds(), patch(
            "backend.nat_lookup.service.call_nat_policy_match",
            return_value=("<resp/>", None),
        ), patch(
            "backend.nat_lookup.service._find_nat_rule_name_in_response",
            return_value=rule,
        ):
            handled, should_return = _try_one_firewall(
                fw, "10.0.0.1", "8.8.8.8", "secret", MagicMock(), 15, False, out
            )
        # build_rule_config_xpath returns None → handled=True, should_return=True.
        assert handled is True
        assert should_return is True
        assert "both quote types" in out["error"]
        # rule_name was set before the xpath check fails.
        assert out["rule_name"] == rule


class TestTryOneFirewallHappyPath:
    def test_full_success_extracts_rule_and_ips(self, fw, out) -> None:
        with _patch_creds(), patch(
            "backend.nat_lookup.service.call_nat_policy_match",
            return_value=("<match/>", None),
        ), patch(
            "backend.nat_lookup.service._find_nat_rule_name_in_response",
            return_value="MyRule",
        ), patch(
            "backend.nat_lookup.service.call_nat_rule_config",
            return_value=("<cfg/>", None),
        ), patch(
            "backend.nat_lookup.service._find_translated_ips_in_rule_config",
            return_value=["10.0.0.5", "10.0.0.6"],
        ):
            handled, should_return = _try_one_firewall(
                fw, "10.0.0.1", "8.8.8.8", "secret", MagicMock(), 15, False, out
            )

        assert handled is True
        assert should_return is True
        assert out["ok"] is True
        assert out["rule_name"] == "MyRule"
        assert out["translated_ips"] == ["10.0.0.5", "10.0.0.6"]
        assert out["firewall_hostname"] == "fw-1"
        assert out["firewall_ip"] == "192.168.99.1"

    def test_success_without_translated_ips(self, fw, out) -> None:
        with _patch_creds(), patch(
            "backend.nat_lookup.service.call_nat_policy_match",
            return_value=("<match/>", None),
        ), patch(
            "backend.nat_lookup.service._find_nat_rule_name_in_response",
            return_value="RuleX",
        ), patch(
            "backend.nat_lookup.service.call_nat_rule_config",
            return_value=("<cfg/>", None),
        ), patch(
            "backend.nat_lookup.service._find_translated_ips_in_rule_config",
            return_value=[],
        ):
            handled, should_return = _try_one_firewall(
                fw, "10.0.0.1", "8.8.8.8", "secret", MagicMock(), 15, False, out
            )
        assert handled is True
        assert should_return is True
        assert out["ok"] is True
        assert out["translated_ips"] == []  # nothing to populate

    def test_rule_config_exception_still_returns_ok(self, fw, out) -> None:
        # If the rule-config call fails we still got a rule_name → ok=True.
        with _patch_creds(), patch(
            "backend.nat_lookup.service.call_nat_policy_match",
            return_value=("<match/>", None),
        ), patch(
            "backend.nat_lookup.service._find_nat_rule_name_in_response",
            return_value="RuleY",
        ), patch(
            "backend.nat_lookup.service.call_nat_rule_config",
            return_value=(None, ConnectionError("rule fetch failed")),
        ):
            handled, should_return = _try_one_firewall(
                fw, "10.0.0.1", "8.8.8.8", "secret", MagicMock(), 15, False, out
            )
        assert out["ok"] is True
        assert out["rule_name"] == "RuleY"
        assert out["translated_ips"] == []

    def test_debug_envelope_populated_on_success(self, fw, out) -> None:
        with _patch_creds(), patch(
            "backend.nat_lookup.service.call_nat_policy_match",
            return_value=("<resp>match</resp>", None),
        ), patch(
            "backend.nat_lookup.service._find_nat_rule_name_in_response",
            return_value="RuleD",
        ), patch(
            "backend.nat_lookup.service.call_nat_rule_config",
            return_value=("<cfg/>", None),
        ), patch(
            "backend.nat_lookup.service._find_translated_ips_in_rule_config",
            return_value=["1.2.3.4"],
        ):
            _try_one_firewall(
                fw, "10.0.0.1", "8.8.8.8", "secret", MagicMock(), 15, True, out
            )
        assert out["debug"] is not None
        assert "nat_policy_match" in out["debug"]
        assert "nat_rule_config" in out["debug"]
