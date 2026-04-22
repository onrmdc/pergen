"""Unit tests for ``backend.parsers.cisco_nxos.interface_status``."""

from __future__ import annotations

from backend.parsers.cisco_nxos.interface_status import _parse_cisco_interface_status


class TestParseCiscoInterfaceStatus:
    def test_basic_row(self) -> None:
        raw = {
            "TABLE_interface": {
                "ROW_interface": [
                    {
                        "interface": "Ethernet1/1",
                        "state": "up",
                        "last_link_flapped": "00:01:00",
                        "eth_inerr": "0",
                        "eth_crc": "0",
                        "mtu": "9216",
                        "reset_cntr": "5",
                    }
                ]
            }
        }
        out = _parse_cisco_interface_status(raw)
        assert len(out["interface_status_rows"]) == 1
        row = out["interface_status_rows"][0]
        assert row["interface"] == "Ethernet1/1"
        assert row["state"] == "up"
        assert row["last_link_flapped"] == "00:01:00"
        assert row["mtu"] == "9216"
        assert "last_status_change_epoch" in row

    def test_dash_for_missing_fields(self) -> None:
        raw = {"TABLE_interface": {"ROW_interface": [{"interface": "Eth1"}]}}
        out = _parse_cisco_interface_status(raw)
        row = out["interface_status_rows"][0]
        assert row["state"] == "-"
        assert row["last_link_flapped"] == "-"
        assert row["mtu"] == "-"

    def test_skips_blank_interface(self) -> None:
        raw = {"TABLE_interface": {"ROW_interface": [{"state": "up"}]}}
        out = _parse_cisco_interface_status(raw)
        assert out["interface_status_rows"] == []

    def test_dict_row_promoted_to_list(self) -> None:
        raw = {"TABLE_interface": {"ROW_interface": {"interface": "Eth1", "state": "up"}}}
        out = _parse_cisco_interface_status(raw)
        assert len(out["interface_status_rows"]) == 1

    def test_empty_returns_empty(self) -> None:
        assert _parse_cisco_interface_status({}) == {"interface_status_rows": []}
        assert _parse_cisco_interface_status(None) == {"interface_status_rows": []}

    def test_body_string_unwrap(self) -> None:
        import json
        body = json.dumps({"TABLE_interface": {"ROW_interface": [{"interface": "Eth1", "state": "up"}]}})
        raw = {"body": body}
        out = _parse_cisco_interface_status(raw)
        assert len(out["interface_status_rows"]) == 1

    def test_result_envelope_unwrap(self) -> None:
        raw = {"result": [{"TABLE_interface": {"ROW_interface": [{"interface": "Eth1", "state": "up"}]}}]}
        out = _parse_cisco_interface_status(raw)
        assert out["interface_status_rows"][0]["interface"] == "Eth1"

    def test_smt_alt_keys(self) -> None:
        raw = {
            "TABLE_interface": {
                "ROW_interface": [
                    {
                        "interface": "Ethernet1/1",
                        "smt_if_last_link_flapped": "00:00:30",
                        "smt_if_mtu": "1500",
                    }
                ]
            }
        }
        out = _parse_cisco_interface_status(raw)
        row = out["interface_status_rows"][0]
        assert row["last_link_flapped"] == "00:00:30"
        assert row["mtu"] == "1500"
