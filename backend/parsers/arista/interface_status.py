"""Arista 'show interfaces' parser, including the NX-OS-style fallback table.

Extracted verbatim from ``backend/parse_output.py``. Three private helpers
are co-located here because they are only consumed by
``_parse_arista_interface_status``:

* ``_parse_arista_interface_status_from_table`` — NX-OS-style fallback
* ``_arista_get_interface_counters_dict`` — counters envelope
* ``_arista_in_and_crc_from_counters`` — per-EOS field-name handling
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from backend.parsers.common.arista_envelope import (
    _arista_result_obj,
    _arista_result_to_dict,
)
from backend.parsers.common.duration import (
    _parse_hhmmss_to_seconds,
    _parse_relative_seconds_ago,
)
from backend.parsers.common.json_path import (
    _find_key,
    _find_key_containing,
    _find_list,
)


def _parse_arista_interface_status_from_table(inner: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Parse NX-OS-style TABLE_interface / ROW_interface with eth_link_flapped, eth_reset_cntr.
    Some Arista eAPI builds return this shape instead of top-level 'interfaces'.
    """
    out_rows: list[dict[str, Any]] = []
    tbl = inner.get("TABLE_interface") or inner.get("table_interface")
    rows: Any = None
    if isinstance(tbl, dict):
        rows = tbl.get("ROW_interface") or tbl.get("row_interface")
    if rows is None:
        rows = _find_list(inner, "ROW_interface") or _find_list(inner, "ROW_inter")
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return out_rows
    now_epoch = time.time()
    for r in rows:
        if not isinstance(r, dict):
            continue
        intf = _find_key(r, "interface")
        if not intf:
            continue
        state = (_find_key(r, "state") or "").strip() or "-"
        eth_flap = _find_key(r, "eth_link_flapped") or _find_key_containing(r, "link_flapped")
        eth_reset = _find_key(r, "eth_reset_cntr") or _find_key_containing(r, "reset_cntr")
        last_flap_str = str(eth_flap).strip() if eth_flap is not None else "-"
        flap_cnt = str(eth_reset).strip() if eth_reset is not None else "-"
        in_err = _find_key(r, "eth_inerr") or _find_key(r, "in_errors") or _find_key(r, "input_errors")
        in_errors = str(in_err).strip() if in_err is not None else "-"
        crc_raw = _find_key(r, "eth_crc") or _find_key(r, "fcs_errors")
        crc_str = str(crc_raw).strip() if crc_raw is not None else "-"
        mtu_raw = _find_key(r, "eth_mtu") or _find_key(r, "mtu")
        mtu_str = str(mtu_raw).strip() if mtu_raw is not None else "-"
        row: dict[str, Any] = {
            "interface": str(intf).strip(),
            "state": state,
            "last_link_flapped": last_flap_str if last_flap_str else "-",
            "in_errors": in_errors,
            "crc_count": crc_str,
            "mtu": mtu_str,
            "flap_count": flap_cnt if flap_cnt else "-",
        }
        seconds_ago = _parse_hhmmss_to_seconds(last_flap_str)
        if seconds_ago is None and last_flap_str and last_flap_str not in ("-", "never", "n/a"):
            seconds_ago = _parse_relative_seconds_ago(last_flap_str)
        if seconds_ago is not None:
            row["last_status_change_epoch"] = now_epoch - seconds_ago
        out_rows.append(row)
    return out_rows


def _arista_get_interface_counters_dict(info: dict[str, Any]) -> dict[str, Any]:
    """Return Arista per-interface counter dict (camelCase or snake_case)."""
    if not isinstance(info, dict):
        return {}
    c = info.get("interfaceCounters")
    if isinstance(c, dict) and c:
        return c
    c = info.get("interface_counters")
    if isinstance(c, dict) and c:
        return c
    return {}


def _arista_in_and_crc_from_counters(counters: dict[str, Any]) -> tuple[str, str]:
    """Extract input error and CRC/FCS counts from Arista interfaceCounters (field names vary by EOS)."""
    if not isinstance(counters, dict) or not counters:
        return "-", "-"
    in_err: Any = None
    if "inErrors" in counters:
        in_err = counters.get("inErrors")
    elif "totalInErrors" in counters:
        in_err = counters.get("totalInErrors")
    else:
        in_err = (
            counters.get("in_errors")
            or counters.get("inputErrors")
            or counters.get("ingressErrors")
        )
    crc_val: Any = None
    if "fcsErrors" in counters:
        crc_val = counters.get("fcsErrors")
    elif "frameErrors" in counters:
        crc_val = counters.get("frameErrors")
    else:
        crc_val = (
            counters.get("alignmentErrors")
            or counters.get("symbolErrors")
            or counters.get("fcs_errors")
            or counters.get("crcErrors")
        )
    in_s = str(in_err).strip() if in_err is not None else "-"
    crc_s = str(crc_val).strip() if crc_val is not None else "-"
    return in_s, crc_s


def _parse_arista_interface_status(raw_output: Any) -> dict[str, Any]:
    """Parse Arista 'show interfaces | json' (interfaces{} or TABLE_interface/ROW_interface with eth_* fields)."""
    out_rows: list[dict[str, Any]] = []
    obj = _arista_result_obj(raw_output, 0)
    inner = _arista_result_to_dict(obj) if isinstance(obj, dict) else None
    if not isinstance(inner, dict):
        return {"interface_status_rows": out_rows}

    table_rows = _parse_arista_interface_status_from_table(inner)
    table_by_iface = {str(r["interface"]).strip().lower(): r for r in table_rows}

    ifaces = inner.get("interfaces")
    if isinstance(ifaces, dict) and ifaces:
        for iface_name, info in ifaces.items():
            if not isinstance(info, dict):
                continue
            status = (info.get("interfaceStatus") or info.get("lineProtocolStatus") or "").strip() or "-"
            ts = info.get("lastStatusChangeTimestamp")
            last_flap = ""
            last_epoch: float | None = None
            if ts is not None:
                try:
                    ts_float = float(ts)
                    last_epoch = ts_float
                    last_flap = datetime.fromtimestamp(ts_float).strftime("%H:%M:%S")
                except (TypeError, ValueError):
                    last_flap = str(ts).strip() if ts else ""
            counters = _arista_get_interface_counters_dict(info)
            in_errors, crc_str = _arista_in_and_crc_from_counters(counters)
            link_changes = counters.get("linkStatusChanges") if isinstance(counters, dict) else None
            flap_count = str(link_changes).strip() if link_changes is not None else "-"
            mtu_val = info.get("mtu")
            if mtu_val is None:
                mtu_val = info.get("mtuSize") or info.get("mtu_size")
            mtu_str = str(mtu_val).strip() if mtu_val is not None else "-"
            row: dict[str, Any] = {
                "interface": str(iface_name).strip(),
                "state": status,
                "last_link_flapped": last_flap or "-",
                "in_errors": in_errors,
                "crc_count": crc_str,
                "mtu": mtu_str,
                "flap_count": flap_count,
            }
            if last_epoch is not None:
                row["last_status_change_epoch"] = last_epoch
            tr = table_by_iface.get(str(iface_name).strip().lower())
            if tr:
                tc = tr.get("flap_count")
                if tc not in (None, "", "-"):
                    row["flap_count"] = str(tc).strip()
                tl = tr.get("last_link_flapped")
                if tl not in (None, "", "-"):
                    row["last_link_flapped"] = str(tl).strip()
                te = tr.get("in_errors")
                if te not in (None, "", "-") and row.get("in_errors") in ("-", ""):
                    row["in_errors"] = str(te).strip()
                tcr = tr.get("crc_count")
                if tcr not in (None, "", "-") and row.get("crc_count") in ("-", ""):
                    row["crc_count"] = str(tcr).strip()
                tep = tr.get("last_status_change_epoch")
                if isinstance(tep, (int, float)) and tep > 0:
                    cur_ep = row.get("last_status_change_epoch")
                    if not isinstance(cur_ep, (int, float)) or cur_ep <= 0:
                        row["last_status_change_epoch"] = tep
            out_rows.append(row)
        return {"interface_status_rows": out_rows}

    if table_rows:
        return {"interface_status_rows": table_rows}
    return {"interface_status_rows": out_rows}


__all__ = [
    "_parse_arista_interface_status",
    "_parse_arista_interface_status_from_table",
    "_arista_get_interface_counters_dict",
    "_arista_in_and_crc_from_counters",
]
