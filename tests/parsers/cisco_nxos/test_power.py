"""Unit tests for ``backend.parsers.cisco_nxos.power``."""

from __future__ import annotations

from backend.parsers.cisco_nxos.power import _parse_cisco_power


class TestParseCiscoPower:
    def test_two_ok_supplies(self) -> None:
        raw = {
            "powersup": {
                "TABLE_psinfo": {
                    "ROW_psinfo": [
                        {"ps_status": "Ok"},
                        {"ps_status": "Ok"},
                        {"ps_status": "Failed"},
                    ]
                }
            }
        }
        assert _parse_cisco_power(raw) == {"Power supplies": 2}

    def test_single_dict_row(self) -> None:
        raw = {
            "powersup": {
                "TABLE_psinfo": {"ROW_psinfo": {"ps_status": "Ok"}}
            }
        }
        assert _parse_cisco_power(raw) == {"Power supplies": 1}

    def test_string_with_brace_parsed_as_json(self) -> None:
        raw = '{"powersup":{"TABLE_psinfo":{"ROW_psinfo":[{"ps_status":"Ok"}]}}}'
        assert _parse_cisco_power(raw) == {"Power supplies": 1}

    def test_missing_powersup_returns_blank(self) -> None:
        assert _parse_cisco_power({}) == {"Power supplies": ""}

    def test_powersup_in_body_string(self) -> None:
        # NX-API sometimes wraps the JSON in a body string
        import json
        body = json.dumps({"powersup": {"TABLE_psinfo": {"ROW_psinfo": [{"ps_status": "Ok"}]}}})
        raw = {"body": body}
        assert _parse_cisco_power(raw) == {"Power supplies": 1}

    def test_invalid_body_string_returns_blank(self) -> None:
        raw = {"body": "not-json"}
        assert _parse_cisco_power(raw) == {"Power supplies": ""}

    def test_no_psinfo_returns_blank(self) -> None:
        raw = {"powersup": {"other_key": "x"}}
        assert _parse_cisco_power(raw) == {"Power supplies": ""}

    def test_skips_non_dict_rows(self) -> None:
        raw = {
            "powersup": {
                "TABLE_psinfo": {"ROW_psinfo": ["scalar", {"ps_status": "Ok"}]}
            }
        }
        assert _parse_cisco_power(raw) == {"Power supplies": 1}

    def test_status_must_be_exactly_Ok(self) -> None:
        # Case-sensitive: "ok" / "OK" don't match (matches Cisco convention)
        raw = {
            "powersup": {
                "TABLE_psinfo": {"ROW_psinfo": [{"ps_status": "ok"}, {"ps_status": "OK"}]}
            }
        }
        assert _parse_cisco_power(raw) == {"Power supplies": 0}
