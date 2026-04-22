"""Arista transceiver (optic power / serial) parser.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

from typing import Any

from backend.parsers.common.arista_envelope import (
    _arista_result_obj,
    _arista_result_to_dict,
)
from backend.parsers.common.formatting import _format_power_two_decimals


def _parse_arista_transceiver(raw_output: Any) -> dict[str, Any]:
    """Parse Arista 'show interfaces transceiver | json'. Returns transceiver_rows list with tx/rx."""
    rows: list[dict[str, Any]] = []
    data = _arista_result_obj(raw_output, 0)
    inner = _arista_result_to_dict(data) if isinstance(data, dict) else None
    if not isinstance(inner, dict):
        return {"transceiver_rows": rows}
    ifaces = inner.get("interfaces")
    if not isinstance(ifaces, dict):
        return {"transceiver_rows": rows}
    for iface, info in ifaces.items():
        if not isinstance(info, dict):
            continue
        tx = info.get("txPower")
        rx = info.get("rxPower")
        tx_str = _format_power_two_decimals(tx)
        rx_str = _format_power_two_decimals(rx)
        row = {
            "interface": str(iface),
            "serial": str(info.get("serialNumber") or info.get("serial") or "").strip(),
            "type": str(info.get("partNumber") or info.get("type") or "").strip(),
            "manufacturer": str(info.get("manufacturer") or "").strip(),
            "temp": str(info.get("temperature") or info.get("temp") or "").strip(),
            "tx_power": tx_str,
            "rx_power": rx_str,
        }
        rows.append(row)
    return {"transceiver_rows": rows}


__all__ = ["_parse_arista_transceiver"]
