"""Cisco NX-OS 'show interface' (detailed) parser.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

import json
import time
from typing import Any

from backend.parsers.common.duration import (
    _parse_hhmmss_to_seconds,
    _parse_relative_seconds_ago,
)
from backend.parsers.common.json_path import (
    _find_key,
    _find_key_containing,
    _find_list,
)


def _parse_cisco_interface_detailed(raw_output: Any) -> dict[str, Any]:
    """
    Parse Cisco NX-API 'show interface' (detailed) with eth_link_flapped (HH:MM:SS) and eth_reset_cntr.
    Includes rows that have at least one of eth_link_flapped or eth_reset_cntr (missing field shown as '-').
    Output: interface_flapped_rows with interface, description, last_link_flapped, flap_counter,
    crc_count (eth_crc), in_errors (eth_inerr), last_status_change_epoch.
    """
    out_rows: list[dict[str, Any]] = []
    data = raw_output
    if isinstance(raw_output, dict) and "result" in raw_output:
        r = raw_output["result"]
        data = r[0] if isinstance(r, list) and r else r
    if isinstance(raw_output, list) and raw_output and isinstance(raw_output[0], dict):
        data = raw_output[0]
    body = data.get("body") if isinstance(data, dict) else None
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            body = None
    if body is not None and isinstance(body, dict):
        data = body
    if not isinstance(data, dict):
        return {"interface_flapped_rows": out_rows}
    rows = _find_list(data, "ROW_interface") or _find_list(data, "ROW_inter")
    if not rows:
        tbl = data.get("TABLE_interface") or data.get("table_interface")
        if isinstance(tbl, dict):
            rows = tbl.get("ROW_interface") or tbl.get("row_interface")
    if not rows:
        return {"interface_flapped_rows": out_rows}
    if isinstance(rows, dict):
        rows = [rows]
    now_epoch = time.time()
    for r in rows:
        if not isinstance(r, dict):
            continue
        intf = _find_key(r, "interface")
        if not intf:
            continue
        eth_flap = (
            _find_key(r, "eth_link_flapped")
            or _find_key_containing(r, "link_flapped")
        )
        eth_reset = (
            _find_key(r, "eth_reset_cntr")
            or _find_key_containing(r, "reset_cntr")
        )
        eth_crc = _find_key(r, "eth_crc")
        eth_inerr = _find_key(r, "eth_inerr") or _find_key(r, "in_errors") or _find_key(r, "input_errors")
        if eth_flap is None and eth_reset is None and eth_crc is None and eth_inerr is None:
            continue
        last_flap_str = str(eth_flap).strip() if eth_flap is not None else "-"
        flap_cnt = str(eth_reset).strip() if eth_reset is not None else "-"
        crc_str = str(eth_crc).strip() if eth_crc is not None else "-"
        inerr_str = str(eth_inerr).strip() if eth_inerr is not None else "-"
        desc = _find_key(r, "desc") or _find_key(r, "description") or ""
        desc = str(desc).strip() if desc else "-"
        state = (_find_key(r, "state") or "").strip() or "-"
        seconds_ago = _parse_hhmmss_to_seconds(last_flap_str) if last_flap_str and last_flap_str != "-" else None
        if seconds_ago is None and last_flap_str and last_flap_str != "-":
            seconds_ago = _parse_relative_seconds_ago(last_flap_str)
        row_out: dict[str, Any] = {
            "interface": str(intf).strip(),
            "state": state,
            "description": desc,
            "last_link_flapped": last_flap_str or "-",
            "flap_counter": flap_cnt,
            "crc_count": crc_str,
            "in_errors": inerr_str,
        }
        if seconds_ago is not None:
            row_out["last_status_change_epoch"] = now_epoch - seconds_ago
        out_rows.append(row_out)
    return {"interface_flapped_rows": out_rows}


__all__ = ["_parse_cisco_interface_detailed"]
