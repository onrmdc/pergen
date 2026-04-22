"""Cisco NX-OS 'show interface status' parser.

Extracted verbatim from ``backend/parse_output.py``.
"""

from __future__ import annotations

import time
from typing import Any

from backend.parsers.common.duration import (
    _parse_hhmmss_to_seconds,
    _parse_relative_seconds_ago,
)
from backend.parsers.common.cisco_envelope import cisco_unwrap_body
from backend.parsers.common.json_path import (
    _find_key,
    _find_key_containing,
    _find_list,
)


def _parse_cisco_interface_status(raw_output: Any) -> dict[str, Any]:
    """Parse Cisco NX-API 'show interface status'. Returns interface_status_rows: list of { interface, state, last_link_flapped, in_errors, last_status_change_epoch }."""
    out_rows: list[dict[str, Any]] = []
    data = cisco_unwrap_body(raw_output)
    if not isinstance(data, dict):
        return {"interface_status_rows": out_rows}
    rows = _find_list(data, "ROW_interface") or _find_list(data, "ROW_inter")
    if not rows:
        tbl = data.get("TABLE_interface") or data.get("table_interface") or _find_key_containing(data, "TABLE_intf")
        if isinstance(tbl, dict):
            rows = (
                tbl.get("ROW_interface")
                or tbl.get("row_interface")
                or tbl.get("ROW_intf")
                or tbl.get("row_intf")
                or _find_list(tbl, "ROW")
            )
    if not rows:
        # Fallback: any list of dicts with "interface" in first item's keys
        for v in data.values() if isinstance(data, dict) else []:
            if isinstance(v, list) and v and isinstance(v[0], dict):
                if any("interface" in str(x).lower() for x in v[0].keys()):
                    rows = v
                    break
    if not rows:
        return {"interface_status_rows": out_rows}
    if isinstance(rows, dict):
        rows = [rows]
    for r in rows:
        if not isinstance(r, dict):
            continue
        intf = _find_key(r, "interface")
        if not intf:
            continue
        state = (_find_key(r, "state") or "").strip() or "-"
        # NX-API can use different key names: last_link_flapped, smt_if_last_link_flapped, last_status_change, etc.
        last_flap_candidates = [
            _find_key(r, "last_link_flapped"),
            _find_key(r, "last_status_change"),
            _find_key(r, "smt_if_last_link_flapped"),
            _find_key(r, "last_stated_change"),
            _find_key(r, "last_link_stated"),
            _find_key_containing(r, "flapped"),
            _find_key_containing(r, "last_link"),
        ]
        last_flap = ""
        for c in last_flap_candidates:
            if c is not None and not isinstance(c, (dict, list)) and str(c).strip():
                last_flap = str(c).strip()
                break
        last_flap = last_flap or "-"
        in_err = (
            _find_key(r, "eth_inerr")
            or _find_key(r, "input_errors")
            or _find_key(r, "in_errors")
            or _find_key(r, "input_err")
        )
        in_errors = str(in_err).strip() if in_err is not None else "-"
        crc_raw = _find_key(r, "eth_crc") or _find_key(r, "fcs_errors")
        crc_str = str(crc_raw).strip() if crc_raw is not None else "-"
        mtu_raw = _find_key(r, "mtu") or _find_key(r, "smt_if_mtu") or _find_key(r, "if_mtu")
        mtu_str = str(mtu_raw).strip() if mtu_raw is not None else "-"
        reset_raw = (
            _find_key(r, "reset_cntr")
            or _find_key(r, "eth_reset_cntr")
            or _find_key(r, "link_flap_cntr")
            or _find_key_containing(r, "reset_cntr")
        )
        flap_count = str(reset_raw).strip() if reset_raw is not None else "-"
        row_c: dict[str, Any] = {
            "interface": str(intf).strip(),
            "state": state,
            "last_link_flapped": last_flap,
            "in_errors": in_errors,
            "crc_count": crc_str,
            "mtu": mtu_str,
            "flap_count": flap_count,
        }
        seconds_ago = _parse_relative_seconds_ago(last_flap)
        if seconds_ago is None:
            seconds_ago = _parse_hhmmss_to_seconds(last_flap)
        if seconds_ago is not None:
            row_c["last_status_change_epoch"] = time.time() - seconds_ago
        out_rows.append(row_c)
    return {"interface_status_rows": out_rows}


__all__ = ["_parse_cisco_interface_status"]
