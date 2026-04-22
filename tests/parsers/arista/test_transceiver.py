"""Unit tests for ``backend.parsers.arista.transceiver``."""

from __future__ import annotations

from backend.parsers.arista.transceiver import _parse_arista_transceiver


class TestParseAristaTransceiver:
    def test_two_interfaces(self) -> None:
        raw = {
            "interfaces": {
                "Ethernet1/1": {
                    "txPower": -2.34,
                    "rxPower": -3.21,
                    "serialNumber": "SN001",
                    "partNumber": "QSFP28",
                    "manufacturer": "ACME",
                    "temperature": 35.0,
                },
                "Ethernet1/2": {
                    "txPower": "1.0",
                    "rxPower": "1.5",
                    "serial": "SN002",
                    "type": "SFP",
                    "manufacturer": "BCorp",
                    "temp": "40",
                },
            }
        }
        out = _parse_arista_transceiver(raw)
        assert len(out["transceiver_rows"]) == 2
        first = out["transceiver_rows"][0]
        assert first["interface"] == "Ethernet1/1"
        assert first["serial"] == "SN001"
        assert first["tx_power"] == "-2.34"
        assert first["rx_power"] == "-3.21"

    def test_missing_interfaces_dict_returns_empty(self) -> None:
        assert _parse_arista_transceiver({}) == {"transceiver_rows": []}

    def test_non_dict_returns_empty(self) -> None:
        assert _parse_arista_transceiver(None) == {"transceiver_rows": []}

    def test_skips_non_dict_iface_info(self) -> None:
        raw = {"interfaces": {"Ethernet1/1": "scalar"}}
        assert _parse_arista_transceiver(raw) == {"transceiver_rows": []}

    def test_missing_power_returns_dash(self) -> None:
        raw = {"interfaces": {"Eth1/1": {"serialNumber": "X"}}}
        out = _parse_arista_transceiver(raw)
        assert out["transceiver_rows"][0]["tx_power"] == "-"
        assert out["transceiver_rows"][0]["rx_power"] == "-"

    def test_list_wrapped(self) -> None:
        raw = [{"interfaces": {"Eth1": {"txPower": 1.0, "rxPower": 2.0}}}]
        out = _parse_arista_transceiver(raw)
        assert out["transceiver_rows"][0]["tx_power"] == "1.00"
