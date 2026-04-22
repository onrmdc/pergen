"""Cisco NX-OS transceiver (optic power / serial) parser.

Extracted verbatim from ``backend/parse_output.py``. The two helpers
``_cisco_find_tx_rx_in_dict`` and ``_cisco_transceiver_tx_rx_from_row``
are co-located here because they are only consumed by
``_parse_cisco_nxos_transceiver``.
"""

from __future__ import annotations

import json
from typing import Any

from backend.parsers.common.formatting import _format_power_two_decimals


def _cisco_find_tx_rx_in_dict(obj: Any, seen: set | None = None) -> tuple[Any, Any]:
    """Recursively find first tx and rx values in nested dict (any key like tx_pwr, rx_pwr, tx_power, lc_tx_pwr, etc.)."""
    if seen is None:
        seen = set()
    if id(obj) in seen:
        return None, None
    if not isinstance(obj, dict):
        return None, None
    seen.add(id(obj))
    tx, rx = None, None
    for k, v in obj.items():
        if v is None:
            continue
        klo = str(k).lower()
        if "tx" in klo and ("pwr" in klo or "power" in klo):
            tx = v
        if "rx" in klo and ("pwr" in klo or "power" in klo):
            rx = v
        if tx is not None and rx is not None:
            break
    if tx is not None and rx is not None:
        return tx, rx
    for v in obj.values():
        if isinstance(v, dict):
            t, r = _cisco_find_tx_rx_in_dict(v, seen)
            if t is not None or r is not None:
                if tx is None:
                    tx = t
                if rx is None:
                    rx = r
                if tx is not None and rx is not None:
                    return tx, rx
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    t, r = _cisco_find_tx_rx_in_dict(item, seen)
                    if t is not None or r is not None:
                        if tx is None:
                            tx = t
                        if rx is None:
                            rx = r
                        if tx is not None and rx is not None:
                            return tx, rx
    return tx, rx


def _cisco_transceiver_tx_rx_from_row(row: dict) -> tuple[str, str]:
    """Extract tx and rx from one Cisco ROW (TABLE_lane/ROW_lane, top-level, or recursive search). Returns (tx_str, rx_str)."""
    if not row or not isinstance(row, dict):
        return "-", "-"
    table_lane = row.get("TABLE_lane") or row.get("table_lane")
    if table_lane and isinstance(table_lane, dict):
        lanes = table_lane.get("ROW_lane") or table_lane.get("row_lane")
        if isinstance(lanes, dict):
            lanes = [lanes]
        if lanes and isinstance(lanes, list) and lanes:
            first = lanes[0]
            if isinstance(first, dict):
                tx, rx = first.get("tx_pwr"), first.get("rx_pwr")
                if tx is not None or rx is not None:
                    return _format_power_two_decimals(tx), _format_power_two_decimals(rx)
    tx = row.get("tx_pwr") or row.get("tx_power") or row.get("txpower") or row.get("lc_tx_pwr")
    rx = row.get("rx_pwr") or row.get("rx_power") or row.get("rxpower") or row.get("lc_rx_pwr")
    if tx is not None or rx is not None:
        return _format_power_two_decimals(tx), _format_power_two_decimals(rx)
    tx, rx = _cisco_find_tx_rx_in_dict(row)
    return _format_power_two_decimals(tx), _format_power_two_decimals(rx)


def _parse_cisco_nxos_transceiver(raw_output: Any) -> dict[str, Any]:
    """Parse Cisco NX-OS 'show interface transceiver' (NX-API JSON). Returns transceiver_rows with tx/rx from TABLE_lane when present."""
    rows: list[dict[str, Any]] = []
    data = raw_output
    if isinstance(raw_output, list) and raw_output:
        data = raw_output[0] if isinstance(raw_output[0], dict) else raw_output
    if isinstance(raw_output, dict) and "result" in raw_output:
        r = raw_output["result"]
        data = r[0] if isinstance(r, list) and r else r
    body = data.get("body") if isinstance(data, dict) else None
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            body = None
    if body is not None and isinstance(body, dict):
        data = body
    if not isinstance(data, dict):
        return {"transceiver_rows": rows}
    table = data.get("TABLE_interface") or data.get("TABLE_transceiver")
    if isinstance(table, dict):
        row_list = table.get("ROW_interface") or table.get("ROW_transceiver")
        if isinstance(row_list, dict):
            row_list = [row_list]
        if isinstance(row_list, list):
            for r in row_list:
                if not isinstance(r, dict):
                    continue
                iface = str(r.get("interface") or r.get("iface") or r.get("port") or "").strip()
                tx_str, rx_str = _cisco_transceiver_tx_rx_from_row(r)
                rows.append({
                    "interface": iface,
                    "serial": str(r.get("serial_number") or r.get("serialnum") or r.get("serial") or "").strip(),
                    "type": str(r.get("type") or r.get("part_number") or r.get("partnum") or "").strip(),
                    "manufacturer": str(r.get("manufacturer") or r.get("vendor") or "").strip(),
                    "temp": str(r.get("temperature") or r.get("temp") or "").strip(),
                    "tx_power": tx_str,
                    "rx_power": rx_str,
                })
    return {"transceiver_rows": rows}


__all__ = [
    "_parse_cisco_nxos_transceiver",
    "_cisco_find_tx_rx_in_dict",
    "_cisco_transceiver_tx_rx_from_row",
]
