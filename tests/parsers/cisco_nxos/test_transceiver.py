"""Unit tests for ``backend.parsers.cisco_nxos.transceiver``."""

from __future__ import annotations

from backend.parsers.cisco_nxos.transceiver import (
    _cisco_find_tx_rx_in_dict,
    _cisco_transceiver_tx_rx_from_row,
    _parse_cisco_nxos_transceiver,
)


class TestCiscoFindTxRxInDict:
    def test_finds_tx_pwr_rx_pwr_at_top(self) -> None:
        assert _cisco_find_tx_rx_in_dict({"tx_pwr": -2.5, "rx_pwr": -3.5}) == (-2.5, -3.5)

    def test_finds_lc_tx_pwr_lc_rx_pwr(self) -> None:
        assert _cisco_find_tx_rx_in_dict({"lc_tx_pwr": 1.0, "lc_rx_pwr": 2.0}) == (1.0, 2.0)

    def test_recurses_into_nested(self) -> None:
        raw = {"outer": {"inner": {"tx_power": 5.0, "rx_power": 6.0}}}
        assert _cisco_find_tx_rx_in_dict(raw) == (5.0, 6.0)

    def test_recurses_into_lists(self) -> None:
        raw = {"items": [{"tx_pwr": 7.0, "rx_pwr": 8.0}]}
        assert _cisco_find_tx_rx_in_dict(raw) == (7.0, 8.0)

    def test_returns_none_none_for_no_match(self) -> None:
        assert _cisco_find_tx_rx_in_dict({"unrelated": 1}) == (None, None)

    def test_non_dict_returns_none_none(self) -> None:
        assert _cisco_find_tx_rx_in_dict(None) == (None, None)
        assert _cisco_find_tx_rx_in_dict([1, 2]) == (None, None)

    def test_handles_circular_reference(self) -> None:
        a = {"x": 1}
        a["self"] = a
        # must not blow the stack
        assert _cisco_find_tx_rx_in_dict(a) == (None, None)


class TestCiscoTransceiverTxRxFromRow:
    def test_dash_dash_for_empty_row(self) -> None:
        assert _cisco_transceiver_tx_rx_from_row({}) == ("-", "-")
        assert _cisco_transceiver_tx_rx_from_row(None) == ("-", "-")

    def test_table_lane_row_lane_first_lane(self) -> None:
        row = {"TABLE_lane": {"ROW_lane": [{"tx_pwr": 1.5, "rx_pwr": 2.5}]}}
        assert _cisco_transceiver_tx_rx_from_row(row) == ("1.50", "2.50")

    def test_top_level_tx_pwr(self) -> None:
        assert _cisco_transceiver_tx_rx_from_row({"tx_pwr": 1.5, "rx_pwr": 2.5}) == ("1.50", "2.50")

    def test_alternate_keys(self) -> None:
        row = {"tx_power": 3.0, "rx_power": 4.0}
        assert _cisco_transceiver_tx_rx_from_row(row) == ("3.00", "4.00")

    def test_lc_alt_keys(self) -> None:
        row = {"lc_tx_pwr": 5.0, "lc_rx_pwr": 6.0}
        assert _cisco_transceiver_tx_rx_from_row(row) == ("5.00", "6.00")

    def test_recursive_fallback(self) -> None:
        row = {"deep": {"tx_pwr": 7.0, "rx_pwr": 8.0}}
        assert _cisco_transceiver_tx_rx_from_row(row) == ("7.00", "8.00")

    def test_table_lane_dict_not_list(self) -> None:
        row = {"TABLE_lane": {"ROW_lane": {"tx_pwr": 9.0, "rx_pwr": 10.0}}}
        assert _cisco_transceiver_tx_rx_from_row(row) == ("9.00", "10.00")


class TestParseCiscoNxosTransceiver:
    def test_two_interfaces(self) -> None:
        raw = {
            "TABLE_interface": {
                "ROW_interface": [
                    {
                        "interface": "Ethernet1/1",
                        "tx_pwr": 1.0,
                        "rx_pwr": 2.0,
                        "serial_number": "SN1",
                        "type": "QSFP28",
                        "manufacturer": "ACME",
                        "temperature": 35,
                    },
                    {
                        "interface": "Ethernet1/2",
                        "tx_pwr": 3.0,
                        "rx_pwr": 4.0,
                        "serial_number": "SN2",
                        "type": "SFP",
                        "manufacturer": "BCorp",
                        "temperature": 40,
                    },
                ]
            }
        }
        out = _parse_cisco_nxos_transceiver(raw)
        assert len(out["transceiver_rows"]) == 2
        assert out["transceiver_rows"][0]["interface"] == "Ethernet1/1"
        assert out["transceiver_rows"][0]["tx_power"] == "1.00"

    def test_single_dict_row(self) -> None:
        raw = {
            "TABLE_interface": {
                "ROW_interface": {"interface": "Eth1", "tx_pwr": 5.0, "rx_pwr": 6.0}
            }
        }
        out = _parse_cisco_nxos_transceiver(raw)
        assert out["transceiver_rows"][0]["interface"] == "Eth1"

    def test_empty_returns_empty(self) -> None:
        assert _parse_cisco_nxos_transceiver({}) == {"transceiver_rows": []}
        assert _parse_cisco_nxos_transceiver(None) == {"transceiver_rows": []}

    def test_alternative_table_name(self) -> None:
        raw = {
            "TABLE_transceiver": {
                "ROW_transceiver": [
                    {"interface": "Eth1", "tx_pwr": 1.0, "rx_pwr": 2.0}
                ]
            }
        }
        out = _parse_cisco_nxos_transceiver(raw)
        assert out["transceiver_rows"][0]["interface"] == "Eth1"

    def test_body_string_unwrap(self) -> None:
        import json
        body = json.dumps(
            {"TABLE_interface": {"ROW_interface": [{"interface": "E1", "tx_pwr": 1.0, "rx_pwr": 2.0}]}}
        )
        raw = {"body": body}
        out = _parse_cisco_nxos_transceiver(raw)
        assert len(out["transceiver_rows"]) == 1

    def test_result_envelope_unwrap(self) -> None:
        raw = {"result": [{"TABLE_interface": {"ROW_interface": [{"interface": "E1", "tx_pwr": 1, "rx_pwr": 2}]}}]}
        out = _parse_cisco_nxos_transceiver(raw)
        assert out["transceiver_rows"][0]["interface"] == "E1"

    def test_skips_non_dict_rows(self) -> None:
        raw = {"TABLE_interface": {"ROW_interface": ["scalar", {"interface": "Eth1", "tx_pwr": 1, "rx_pwr": 2}]}}
        out = _parse_cisco_nxos_transceiver(raw)
        assert len(out["transceiver_rows"]) == 1
