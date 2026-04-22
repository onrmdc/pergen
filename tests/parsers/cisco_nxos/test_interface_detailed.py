"""Unit tests for ``backend.parsers.cisco_nxos.interface_detailed``."""

from __future__ import annotations

from backend.parsers.cisco_nxos.interface_detailed import _parse_cisco_interface_detailed


class TestParseCiscoInterfaceDetailed:
    def test_basic_row(self) -> None:
        raw = {
            "TABLE_interface": {
                "ROW_interface": [
                    {
                        "interface": "Ethernet1/1",
                        "state": "eth-up",
                        "eth_link_flapped": "00:01:00",
                        "eth_reset_cntr": "5",
                        "eth_crc": "3",
                        "eth_inerr": "12",
                        "desc": "uplink",
                    }
                ]
            }
        }
        out = _parse_cisco_interface_detailed(raw)
        assert len(out["interface_flapped_rows"]) == 1
        row = out["interface_flapped_rows"][0]
        assert row["interface"] == "Ethernet1/1"
        assert row["last_link_flapped"] == "00:01:00"
        assert row["flap_counter"] == "5"
        assert row["crc_count"] == "3"
        assert row["in_errors"] == "12"
        assert row["description"] == "uplink"

    def test_skips_rows_with_no_relevant_fields(self) -> None:
        raw = {
            "TABLE_interface": {
                "ROW_interface": [{"interface": "Ethernet1/1"}]  # no flap/reset/crc/inerr
            }
        }
        out = _parse_cisco_interface_detailed(raw)
        assert out["interface_flapped_rows"] == []

    def test_skips_blank_interface(self) -> None:
        raw = {"TABLE_interface": {"ROW_interface": [{"eth_link_flapped": "00:00:30"}]}}
        out = _parse_cisco_interface_detailed(raw)
        assert out["interface_flapped_rows"] == []

    def test_empty_returns_empty(self) -> None:
        assert _parse_cisco_interface_detailed({}) == {"interface_flapped_rows": []}
        assert _parse_cisco_interface_detailed(None) == {"interface_flapped_rows": []}

    def test_dict_row_promoted_to_list(self) -> None:
        raw = {
            "TABLE_interface": {
                "ROW_interface": {"interface": "Eth1", "eth_link_flapped": "00:00:30"}
            }
        }
        out = _parse_cisco_interface_detailed(raw)
        assert len(out["interface_flapped_rows"]) == 1
