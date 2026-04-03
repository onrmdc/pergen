"""
Apply parser config (from parsers.yaml) to command raw output.
Supports json_path (dot-separated or first result) and regex for text.
"""
import re
import json
import time
from datetime import datetime
from typing import Any


def _get_path(data: Any, path: str) -> Any:
    """Get value from dict/list by dot path. Handles list: take first element."""
    if not path or data is None:
        return None
    parts = path.strip().split(".")
    for p in parts:
        if data is None:
            return None
        if isinstance(data, list):
            data = data[0] if data else None
        if isinstance(data, dict):
            data = data.get(p)
        else:
            return None
    return data


def _flatten_nested_list(
    data: Any, path: str, inner_path: str | list[str]
) -> list:
    """Get list at path; for each item get inner_path (dot-separated or list of paths) and flatten.
    If inner_path is a list (e.g. [TABLE_vrf.ROW_vrf, TABLE_process_adj.ROW_process_adj]), flatten through multiple levels."""
    val = _get_path(data, path)
    if not isinstance(val, list):
        return []
    if isinstance(inner_path, list):
        levels = inner_path
        if not levels:
            return val
        out = []
        for item in val:
            if not isinstance(item, dict):
                continue
            level_vals = [_get_path(item, levels[0])]
            for level in levels[1:]:
                next_vals = []
                for v in level_vals:
                    if isinstance(v, list):
                        for elem in v:
                            if isinstance(elem, dict):
                                next_vals.append(_get_path(elem, level))
                    elif isinstance(v, dict):
                        next_vals.append(_get_path(v, level))
                level_vals = [x for x in next_vals if x is not None]
            for v in level_vals:
                if isinstance(v, list):
                    out.extend(v)
                elif v is not None:
                    out.append(v)
        return out
    out = []
    for item in val:
        if not isinstance(item, dict):
            continue
        inner = _get_path(item, inner_path)
        if isinstance(inner, list):
            out.extend(inner)
        elif inner is not None:
            out.append(inner)
    return out


def _count_from_json(data: Any, path: str, flatten_inner_path: str | None = None) -> int:
    """Get list/dict at path and return length or count of items.
    If flatten_inner_path is set, path must be a list; each item's inner_path is flattened and counted."""
    if flatten_inner_path:
        val = _flatten_nested_list(data, path, flatten_inner_path)
        return len(val)
    val = _get_path(data, path)
    if isinstance(val, list):
        return len(val)
    if isinstance(val, dict):
        return len(val)
    if isinstance(val, (int, float)):
        return int(val)
    return 0


def _count_where(
    data: Any,
    path: str,
    where: dict,
    key_prefix: str | None = None,
    key_prefix_exclude: str | None = None,
    flatten_inner_path: str | None = None,
) -> int:
    """Get list or dict at path; count items where each key in where matches item.get(key).
    If value is a dict (e.g. Arista interface name -> props), iterate over .values().
    key_prefix: only count entries whose key starts with this.
    key_prefix_exclude: exclude entries whose key starts with this (e.g. exclude Management from total).
    flatten_inner_path: if set, path is list of dicts; flatten each item's inner_path to one list, then count_where."""
    if flatten_inner_path:
        val = _flatten_nested_list(data, path, flatten_inner_path)
    else:
        val = _get_path(data, path)
    if isinstance(val, dict):
        if key_prefix:
            val = [v for k, v in val.items() if isinstance(k, str) and k.startswith(key_prefix)]
        elif key_prefix_exclude:
            val = [v for k, v in val.items() if not (isinstance(k, str) and k.startswith(key_prefix_exclude))]
        else:
            val = list(val.values())
    if not isinstance(val, list):
        return 0
    n = 0
    for item in val:
        if not isinstance(item, dict):
            continue
        match = all(str(item.get(k)) == str(v) for k, v in where.items())
        if match:
            n += 1
    return n


def _get_from_dict_by_key_prefix(
    data: Any, path: str, key_prefix: str, value_key: str, divisor: float = 1
) -> Any:
    """Get dict at path, find first key that startswith key_prefix, return item[value_key] / divisor."""
    val = _get_path(data, path)
    if not isinstance(val, dict) or not key_prefix:
        return None
    for k, item in val.items():
        if isinstance(k, str) and k.startswith(key_prefix) and isinstance(item, dict):
            v = item.get(value_key)
            if v is not None and divisor and divisor != 0:
                try:
                    return float(v) / float(divisor)
                except (TypeError, ValueError):
                    return v
            return v
    return None


def _extract_regex(text: str, pattern: str) -> str | None:
    """First capture group from regex, or None."""
    if not text or not pattern:
        return None
    try:
        m = re.search(pattern, text, re.MULTILINE | re.DOTALL)
        return m.group(1).strip() if m and m.lastindex else None
    except Exception:
        return None


def _count_regex_lines(text: str, pattern: str) -> int:
    """Count lines matching regex (no capture needed)."""
    if not text or not pattern:
        return 0
    try:
        return len(re.findall(pattern, text, re.MULTILINE))
    except Exception:
        return 0


def _apply_value_subtract_and_suffix(f: dict, val: Any, result: dict, name: str) -> None:
    """Set result[name] from val; apply value_subtract_from (e.g. 100 - idle) and value_suffix (e.g. ' %')."""
    if val is None:
        result[name] = None
        return
    num = None
    if isinstance(val, (int, float)):
        num = val
    else:
        try:
            num = float(val)
        except (TypeError, ValueError):
            result[name] = str(val)
            return
    subtract = f.get("value_subtract_from")
    if subtract is not None:
        try:
            num = float(subtract) - num
        except (TypeError, ValueError):
            pass
    suffix = f.get("value_suffix")
    if suffix:
        result[name] = (str(int(num)) if num == int(num) else str(round(num, 2))) + suffix
    else:
        result[name] = num if isinstance(num, (int, float)) else str(num)


def _find_isis_interface_brief_rows(data: Any) -> list:
    """Find list of row dicts from NX-API 'show isis interface brief' JSON."""
    if not data or not isinstance(data, dict):
        return []
    for key, val in data.items():
        if isinstance(val, list) and val and isinstance(val[0], dict):
            keys0 = list((val[0] or {}).keys())
            if any("intfb-name-out" in str(k) for k in keys0):
                return val
        if isinstance(val, dict):
            out = _find_isis_interface_brief_rows(val)
            if out:
                return out
        if isinstance(val, list) and val and isinstance(val[0], dict):
            keys0 = list((val[0] or {}).keys())
            if any("intfb-ready-state-out" in str(k) for k in keys0):
                return val
    return []


def _find_arista_isis_adjacency_list(data: Any) -> list:
    """Find list of adjacency entries from Arista 'show isis adjacency | json'."""
    if not data or not isinstance(data, dict):
        return []
    for key in ("adjacencyTable", "adjacencies", "adjacency"):
        val = data.get(key)
        if isinstance(val, list):
            return val
    for v in data.values():
        if isinstance(v, dict):
            out = _find_arista_isis_adjacency_list(v)
            if out:
                return out
        if isinstance(v, list) and v and isinstance(v[0], dict):
            if any("interface" in str(k).lower() or "intf" in str(k).lower() for k in (v[0] or {})):
                return v
    return []


def _parse_arista_isis_adjacency(raw_output: Any) -> dict[str, Any]:
    """Parse Arista 'show isis adjacency | json'. Returns isis_adjacency_count, isis_adjacency_rows (interface, state)."""
    obj = _arista_result_obj(raw_output, 0)
    inner = _arista_result_to_dict(obj) if isinstance(obj, dict) else None
    if not isinstance(inner, dict):
        return {"isis_adjacency_count": 0, "isis_adjacency_rows": [], "ISIS": "0"}
    rows: list[dict[str, Any]] = []
    adj_list = _find_arista_isis_adjacency_list(inner)
    for r in adj_list or []:
        if not isinstance(r, dict):
            continue
        intf = (
            r.get("interface") or r.get("interfaceName") or r.get("intf") or r.get("port")
            or next((r.get(k) for k in r if "interface" in str(k).lower() or "intf" in str(k).lower()), "")
        )
        state = (
            r.get("state") or r.get("adjacencyState") or r.get("status")
            or next((r.get(k) for k in r if "state" in str(k).lower() or "status" in str(k).lower()), "Unknown")
        )
        intf = str(intf).strip() if intf else ""
        if intf:
            rows.append({"interface": intf, "state": str(state).strip() or "Unknown"})
    count = len(rows)
    return {"ISIS": str(count), "isis_adjacency_rows": rows}


def _parse_cisco_isis_interface_brief(raw_output: Any) -> dict[str, Any]:
    """Parse 'show isis interface brief' NX-API JSON. Returns isis_ready_count, isis_up_count, isis_interface_rows."""
    data = raw_output
    if isinstance(raw_output, str) and raw_output.strip().startswith("{"):
        try:
            data = json.loads(raw_output)
        except Exception:
            data = {}
    rows = _find_isis_interface_brief_rows(data)
    ready_count = 0
    up_count = 0
    isis_interface_rows: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        name_key = next(
            (k for k in r if "intfb-name-out" in str(k).lower() or "intfb_name_out" in str(k).lower()),
            None,
        )
        state_key = next(
            (k for k in r if "intfb-state-out" in str(k).lower() or "intfb_state_out" in str(k).lower()),
            None,
        )
        ready_key = next(
            (k for k in r if "intfb-ready-state-out" in str(k).lower() or "intfb_ready_state_out" in str(k).lower()),
            None,
        )
        if not name_key or not ready_key:
            continue
        ready_val = (r.get(ready_key) or "").strip()
        intf_name = (r.get(name_key) or "").strip()
        if not intf_name.startswith("Ethernet") or "loopback" in intf_name.lower():
            continue
        state_out = (r.get(state_key) or "").strip() if state_key else "Down"
        isis_interface_rows.append({"interface": intf_name, "state": "Up" if state_out.lower() == "up" else "Down"})
        if ready_val != "Ready":
            continue
        ready_count += 1
        if state_out.lower() == "up":
            up_count += 1
    return {"ISIS": f"{up_count}/{ready_count}", "isis_interface_rows": isis_interface_rows}


def _parse_cisco_system_uptime(raw_output: Any) -> dict[str, Any]:
    """Parse 'show system uptime' NX-API JSON. Returns Uptime as 'Xd Xh Xm Xs'."""
    data = raw_output
    if isinstance(raw_output, str) and raw_output.strip().startswith("{"):
        try:
            data = json.loads(raw_output)
        except Exception:
            data = {}
    if not isinstance(data, dict):
        return {"Uptime": ""}
    d = str(data.get("sys_up_days") or "0").strip()
    h = str(data.get("sys_up_hrs") or "0").strip()
    m = str(data.get("sys_up_mins") or "0").strip()
    s = str(data.get("sys_up_secs") or "0").strip()
    return {"Uptime": f"{d}d {h}h {m}m {s}s"}


def _format_power_two_decimals(val: Any) -> str:
    """Format TX/RX power value to at most 2 decimal places. Non-numeric values returned as-is or '-'."""
    if val is None:
        return "-"
    s = str(val).strip()
    if not s or s == "-":
        return "-"
    try:
        f = float(s.replace(",", "."))
        return f"{f:.2f}"
    except ValueError:
        return s


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
        now_epoch = time.time()
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


def _parse_relative_seconds_ago(s: str) -> float | None:
    """Parse Cisco-style relative time like '1d02h', '23h', '30m', '14week(s) 2day(s)', 'never'. Returns seconds ago or None."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip().lower()
    if s == "never" or s == "-" or s == "":
        return None
    total = 0.0
    for m in re.finditer(r"(\d+)\s*week\(s\)", s):
        try:
            total += float(m.group(1)) * 7 * 86400
        except (ValueError, TypeError):
            pass
    for m in re.finditer(r"(\d+)\s*day\(s\)", s):
        try:
            total += float(m.group(1)) * 86400
        except (ValueError, TypeError):
            pass
    for m in re.finditer(r"(\d+)\s*hour\(s\)", s):
        try:
            total += float(m.group(1)) * 3600
        except (ValueError, TypeError):
            pass
    for m in re.finditer(r"(\d+)\s*minute\(s\)", s):
        try:
            total += float(m.group(1)) * 60
        except (ValueError, TypeError):
            pass
    # Strip word forms so "2day(s)" does not also match as compact "2d"
    s_rest = s
    for token in (
        r"\d+\s*week\(s\)",
        r"\d+\s*day\(s\)",
        r"\d+\s*hour\(s\)",
        r"\d+\s*minute\(s\)",
    ):
        s_rest = re.sub(token, " ", s_rest, flags=re.IGNORECASE)
    s_rest = re.sub(r"\s+", " ", s_rest).strip()
    # Compact Cisco-style: 1d02h, 23h, 30m (remaining after word forms removed)
    for part in re.findall(r"(\d+)\s*([dhms])", s_rest):
        try:
            n = float(part[0])
        except (TypeError, ValueError):
            continue
        unit = part[1]
        if unit == "d":
            total += n * 86400
        elif unit == "h":
            total += n * 3600
        elif unit == "m":
            total += n * 60
        elif unit == "s":
            total += n
    if total <= 0:
        return None
    return total


def _parse_hhmmss_to_seconds(s: str) -> float | None:
    """Parse duration HH:MM:SS (e.g. '00:41:55' = 41 min 55 sec ago). Returns seconds or None."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s or s.lower() in ("never", "-", "n/a"):
        return None
    # HH:MM:SS or H:MM:SS
    m = re.match(r"^(\d+):(\d{1,2}):(\d{1,2})$", s)
    if m:
        try:
            h, mn, sec = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return h * 3600 + mn * 60 + sec
        except (ValueError, TypeError):
            return None
    return None


def _parse_cisco_interface_status(raw_output: Any) -> dict[str, Any]:
    """Parse Cisco NX-API 'show interface status'. Returns interface_status_rows: list of { interface, state, last_link_flapped, in_errors, last_status_change_epoch }."""
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


def _parse_cisco_interface_show_mtu(raw_output: Any) -> dict[str, Any]:
    """
    Parse Cisco NX-API 'show interface' JSON: TABLE_interface.ROW_interface[].eth_mtu per interface.
    """
    mtu_map: dict[str, str] = {}
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
        return {"interface_mtu_map": {}}
    tbl = data.get("TABLE_interface") or data.get("table_interface")
    rows = None
    if isinstance(tbl, dict):
        rows = tbl.get("ROW_interface") or tbl.get("row_interface")
    if not rows:
        rows = _find_list(data, "ROW_interface") or _find_list(data, "ROW_inter")
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return {"interface_mtu_map": {}}
    for r in rows:
        if not isinstance(r, dict):
            continue
        intf = r.get("interface") or _find_key(r, "interface")
        if not intf:
            continue
        eth_mtu = r.get("eth_mtu") or _find_key(r, "eth_mtu")
        mtu_map[str(intf).strip()] = str(eth_mtu).strip() if eth_mtu is not None else "-"
    return {"interface_mtu_map": mtu_map}


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


def _parse_arista_interface_description(raw_output: Any) -> dict[str, Any]:
    """Parse Arista 'show interfaces description | json'. Returns interface_descriptions: dict interface -> description."""
    obj = _arista_result_obj(raw_output, 0)
    inner = _arista_result_to_dict(obj) if isinstance(obj, dict) else None
    if not isinstance(inner, dict):
        return {"interface_descriptions": {}}
    descs = inner.get("interfaceDescriptions")
    if not isinstance(descs, dict):
        return {"interface_descriptions": {}}
    out_desc: dict[str, str] = {}
    for k, v in descs.items():
        key = str(k).strip()
        if isinstance(v, dict) and v.get("description") is not None:
            out_desc[key] = str(v["description"]).strip()
        elif v is not None:
            out_desc[key] = str(v).strip()
        else:
            out_desc[key] = ""
    return {"interface_descriptions": out_desc}


def _parse_cisco_interface_description(raw_output: Any) -> dict[str, Any]:
    """Parse Cisco NX-API 'show interface description'. Returns interface_descriptions: dict interface -> description."""
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
        return {"interface_descriptions": {}}
    out: dict[str, str] = {}
    rows = _find_list(data, "ROW_inter")
    if not rows:
        tbl = data.get("TABLE_interface") or data.get("table_interface")
        if isinstance(tbl, dict):
            rows = tbl.get("ROW_interface") or tbl.get("row_interface")
    if isinstance(rows, dict):
        rows = [rows]
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        intf = _find_key(r, "interface")
        desc = _find_key(r, "description") or _find_key(r, "desc") or _find_key(r, "port_desc")
        if intf:
            out[str(intf).strip()] = str(desc).strip() if desc else ""
    return {"interface_descriptions": out}


def _parse_arista_uptime(raw_output: Any) -> dict[str, Any]:
    """Parse Arista 'show uptime | json'. upTime is in seconds; convert to Xd Xh Xm Xs like Cisco."""
    data = raw_output
    if isinstance(raw_output, str) and raw_output.strip().startswith("{"):
        try:
            data = json.loads(raw_output)
        except Exception:
            data = {}
    if not isinstance(data, dict):
        return {"Uptime": ""}
    try:
        total_secs = float(data.get("upTime") or 0)
    except (TypeError, ValueError):
        return {"Uptime": ""}
    total_secs = int(total_secs)
    days = total_secs // 86400
    rest = total_secs % 86400
    hours = rest // 3600
    rest = rest % 3600
    mins = rest // 60
    secs = rest % 60
    return {"Uptime": f"{days}d {hours}h {mins}m {secs}s"}


def _arista_result_obj(raw_output: Any, index: int = 0) -> dict | None:
    """Get dict from Arista eAPI result (single object or list of results)."""
    if isinstance(raw_output, list) and raw_output:
        raw_output = raw_output[index] if index < len(raw_output) else raw_output[0]
    if isinstance(raw_output, dict):
        return raw_output
    return None


def _arista_result_to_dict(obj: Any) -> dict | None:
    """Unwrap Arista result to the actual data dict (e.g. output or result key)."""
    if not isinstance(obj, dict):
        return None
    if "output" in obj and isinstance(obj["output"], dict):
        return obj["output"]
    if "result" in obj:
        r = obj["result"]
        if isinstance(r, dict):
            return r
        if isinstance(r, list) and r and isinstance(r[0], dict):
            return r[0]
    return obj


def _parse_arista_cpu(raw_output: Any) -> dict[str, Any]:
    """Parse Arista 'show processes top once | json'. cpuInfo['%Cpu(s)'].idle -> CPU usage = 100 - idle."""
    obj = _arista_result_obj(raw_output)
    if obj is None:
        return {"CPU usage": ""}
    try:
        cpu_info = obj.get("cpuInfo") or {}
        if not isinstance(cpu_info, dict):
            return {"CPU usage": ""}
        pct = cpu_info.get("%Cpu(s)")
        if isinstance(pct, dict):
            idle = pct.get("idle")
            if idle is not None:
                try:
                    used = round(100.0 - float(idle), 1)
                    return {"CPU usage": f"{used} %"}
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    return {"CPU usage": ""}


def _parse_arista_disk(raw_output: Any) -> dict[str, Any]:
    """Parse Arista 'show file systems | json'. flash: (size-free)/size*100."""
    obj = _arista_result_obj(raw_output)
    if obj is None:
        return {"Disk": ""}
    try:
        for fs in obj.get("fileSystems") or []:
            if not isinstance(fs, dict):
                continue
            if (fs.get("prefix") or "").strip().lower() == "flash:":
                try:
                    size = int(fs.get("size") or 0)
                    free = int(fs.get("free") or 0)
                    if size > 0:
                        pct = round(((size - free) / size) * 100, 1)
                        return {"Disk": f"{pct} %"}
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    return {"Disk": ""}


def _parse_arista_power(raw_output: Any) -> dict[str, Any]:
    """Parse Arista 'show environment power | json'. Count powerSupplies with state == 'ok'."""
    obj = _arista_result_obj(raw_output)
    if obj is None:
        return {"Power supplies": ""}
    try:
        supplies = obj.get("powerSupplies")
        if not isinstance(supplies, dict):
            return {"Power supplies": ""}
        count = sum(1 for v in supplies.values() if isinstance(v, dict) and (str(v.get("state") or "").strip().lower() == "ok"))
        return {"Power supplies": count}
    except Exception:
        return {"Power supplies": ""}


def _find_key(data: Any, key: str) -> Any:
    """Recursively find first value for key in nested dict."""
    if not isinstance(data, dict):
        return None
    if key in data:
        return data[key]
    for v in data.values():
        found = _find_key(v, key)
        if found is not None:
            return found
    return None


def _find_key_containing(data: Any, key_substr: str) -> Any:
    """Recursively find first value whose key contains key_substr (case-insensitive). Used for NX-API keys like smt_if_last_link_flapped."""
    if not isinstance(data, dict):
        return None
    sub = key_substr.lower()
    for k, v in data.items():
        if sub in str(k).lower():
            if v is not None and v != "" and (not isinstance(v, dict) or v):
                return v
        if isinstance(v, dict):
            found = _find_key_containing(v, key_substr)
            if found is not None:
                return found
        elif isinstance(v, list) and v:
            for item in v:
                if isinstance(item, dict):
                    found = _find_key_containing(item, key_substr)
                    if found is not None:
                        return found
    return None


def _find_list(data: Any, key_substr: str) -> list | None:
    """Find first list in nested dict whose key contains key_substr (e.g. 'ROW')."""
    if not isinstance(data, dict):
        return None
    for k, v in data.items():
        if key_substr.lower() in str(k).lower() and isinstance(v, list):
            return v
        found = _find_list(v, key_substr)
        if found is not None:
            return found
    return None


def parse_arista_bgp_evpn_next_hop(response: Any, index: int = 0) -> str | None:
    """Parse Arista 'show bgp evpn route-type mac-ip <ip> | json'. Returns nextHop IP or None."""
    obj = _arista_result_obj(response, index)
    if obj is None:
        return None
    try:
        data = _arista_result_to_dict(obj)
        if not data or not isinstance(data, dict):
            return None
        evpn_routes = data.get("evpnRoutes") or {}
        for route_data in evpn_routes.values():
            if not isinstance(route_data, dict):
                continue
            for p in route_data.get("evpnRoutePaths") or []:
                if isinstance(p, dict):
                    nh = (p.get("nextHop") or "").strip()
                    if nh:
                        return nh
    except Exception:
        pass
    return None


def parse_arista_arp_interface_for_ip(response: Any, search_ip: str, index: int = 0) -> str | None:
    """Parse Arista 'show ip arp vrf all | json'. Return interface for search_ip (skip Vxlan), or None."""
    search_ip = (search_ip or "").strip()
    if not search_ip:
        return None
    obj = _arista_result_obj(response, index)
    if obj is None:
        return None
    try:
        data = _arista_result_to_dict(obj)
        if not data or not isinstance(data, dict):
            return None
        vrfs = data.get("vrfs") or {}
        for vrf_data in vrfs.values():
            if not isinstance(vrf_data, dict):
                continue
            for n in vrf_data.get("ipV4Neighbors") or []:
                if not isinstance(n, dict):
                    continue
                addr = (n.get("address") or "").strip()
                if addr != search_ip:
                    continue
                iface = (n.get("interface") or "").strip()
                if not iface or "Vxlan" in iface or "Vxlan1" in iface:
                    continue
                return iface
    except Exception:
        pass
    return None


def _get_arp_suppression_entries_list(obj: Any) -> list | None:
    """From NX-API response return list of entry dicts with ip-addr, or None."""
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict) and (_find_key(obj[0], "ip-addr") or _find_key(obj[0], "ip_addr")):
            return obj
        for item in obj:
            found = _get_arp_suppression_entries_list(item)
            if found:
                return found
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "entries" in k.lower() and isinstance(v, list) and v and isinstance(v[0], dict):
                if _find_key(v[0], "ip-addr") or _find_key(v[0], "ip_addr"):
                    return v
        for k, v in obj.items():
            found = _get_arp_suppression_entries_list(v)
            if found:
                return found
    return None


def _get_val(r: dict, *keys: str) -> str:
    """First matching key value from dict, stripped."""
    for k in keys:
        v = _find_key(r, k)
        if v is not None:
            return str(v).strip()
    return ""


def parse_arp_suppression_for_ip(res: Any, search_ip: str) -> dict[str, str] | None:
    """
    Parse NX-API or ASCII of 'show ip arp suppression-cache detail' for the given IP.
    Returns None if not found, else {"flag": "L"|"R", "physical_iod": str, "remote_vtep_addr": str}.
    """
    search_ip = (search_ip or "").strip()
    if not search_ip:
        return None
    if isinstance(res, dict):
        entries_list = _get_arp_suppression_entries_list(res)
        if entries_list:
            for r in entries_list:
                ip_val = _find_key(r, "ip-addr") or _find_key(r, "ip_addr")
                if not ip_val or str(ip_val).strip() != search_ip:
                    continue
                flag = (_find_key(r, "flag") or "").strip().upper() or "L"
                phys = _find_key(r, "physical-iod") or _find_key(r, "physical_iod") or ""
                phys = str(phys).strip() if phys is not None else ""
                remote = _find_key(r, "remote-vtep-addr") or _find_key(r, "remote_vtep_addr") or ""
                remote = str(remote).strip() if remote is not None else ""
                return {"flag": flag[0] if flag else "L", "physical_iod": phys, "remote_vtep_addr": remote}
            return None
        rows = _find_list(res, "ROW")
        if not rows and _find_key(res, "body"):
            body = _find_key(res, "body")
            if isinstance(body, str):
                return parse_arp_suppression_asci(body, search_ip)
        if isinstance(rows, dict):
            rows = [rows]
        for r in (rows or []):
            if not isinstance(r, dict):
                continue
            ip_val = _find_key(r, "ip-addr") or _find_key(r, "ip_addr")
            if not ip_val or str(ip_val).strip() != search_ip:
                continue
            flag = (_find_key(r, "flag") or "").strip().upper() or "L"
            phys = _find_key(r, "physical-iod") or _find_key(r, "physical_iod") or ""
            phys = str(phys).strip() if phys is not None else ""
            remote = _find_key(r, "remote-vtep-addr") or _find_key(r, "remote_vtep_addr") or ""
            remote = str(remote).strip() if remote is not None else ""
            return {"flag": flag[0] if flag else "L", "physical_iod": phys, "remote_vtep_addr": remote}
        return None
    if isinstance(res, str):
        return parse_arp_suppression_asci(res, search_ip)
    return None


def _get_cisco_arp_rows(data: Any) -> list:
    """From NX-API 'show ip arp' response get list of ARP row dicts (ip-addr-out, intf-out)."""
    if not isinstance(data, dict):
        return []
    for key, val in data.items():
        if isinstance(val, dict):
            if "TABLE_adj" in val or "TABLE_arp" in val:
                tbl = val.get("TABLE_adj") or val.get("TABLE_arp") or {}
            else:
                tbl = val
            rows = tbl.get("ROW_adj") or tbl.get("ROW_arp")
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                return rows
            if isinstance(rows, dict) and _get_val(rows, "ip-addr-out", "ip_addr_out"):
                return [rows]
            inner = _get_cisco_arp_rows(val)
            if inner:
                return inner
        elif isinstance(val, list) and val and isinstance(val[0], dict):
            if _get_val(val[0], "ip-addr-out", "ip_addr_out") or _get_val(val[0], "intf-out", "intf_out"):
                return val
    return []


def _parse_cisco_arp_ascii_for_ip(text: str, search_ip: str) -> str | None:
    """Parse ASCII 'show ip arp' output: find line with search_ip, return interface (last column or Ethernetx/y)."""
    if not text or not (search_ip or "").strip():
        return None
    search_ip = search_ip.strip()
    for line in text.splitlines():
        if search_ip not in line:
            continue
        parts = line.split()
        for i, p in enumerate(parts):
            if p == search_ip and i + 1 < len(parts):
                # Interface often last column or after MAC (Ethernet1/2, Eth1/2, etc.)
                for j in range(i + 1, len(parts)):
                    if re.match(r"^(Ethernet|Eth|Po)\d", parts[j], re.I):
                        return parts[j]
                if parts[-1] and not re.match(r"^\d{2}:\d{2}:\d{2}$", parts[-1]):
                    return parts[-1]
                break
    return None


def parse_cisco_arp_interface_for_ip(response: Any, search_ip: str, index: int = 0) -> str | None:
    """
    Parse Cisco NX-API 'show ip arp' (or detail) response. Return interface for search_ip, or None.
    Handles TABLE_vrf.TABLE_adj.ROW_adj with ip-addr-out / intf-out or phy-intf. Falls back to ASCII.
    """
    search_ip = (search_ip or "").strip()
    if not search_ip:
        return None
    data = response
    if isinstance(response, list) and len(response) > index:
        data = response[index]
    if isinstance(data, dict) and "body" in data:
        body = data["body"]
        if isinstance(body, str):
            return _parse_cisco_arp_ascii_for_ip(body, search_ip)
        data = body
    elif isinstance(data, str):
        return _parse_cisco_arp_ascii_for_ip(data, search_ip)
    if not isinstance(data, dict):
        return None
    # Walk TABLE_vrf -> TABLE_adj -> ROW_adj
    vrfs = data.get("TABLE_vrf") or data.get("TABLE_arp")
    if isinstance(vrfs, dict):
        vrfs = [vrfs]
    if isinstance(vrfs, list):
        for vrf in vrfs:
            if not isinstance(vrf, dict):
                continue
            adj = vrf.get("TABLE_adj") or vrf.get("TABLE_arp")
            if not isinstance(adj, dict):
                continue
            rows = adj.get("ROW_adj") or adj.get("ROW_arp")
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list):
                continue
            for r in rows:
                if not isinstance(r, dict):
                    continue
                ip_val = _get_val(r, "ip-addr-out", "ip_addr_out", "ip-addr", "ip_addr")
                if ip_val != search_ip:
                    continue
                iface = _get_val(r, "intf-out", "intf_out", "phy-intf", "phy_intf", "interface")
                if iface:
                    return iface
    # Fallback: flat list of rows
    for r in _get_cisco_arp_rows(data):
        ip_val = _get_val(r, "ip-addr-out", "ip_addr_out", "ip-addr", "ip_addr")
        if ip_val == search_ip:
            iface = _get_val(r, "intf-out", "intf_out", "phy-intf", "phy_intf", "interface")
            if iface:
                return iface
    return None


def parse_arp_suppression_asci(text: str, search_ip: str) -> dict[str, str] | None:
    """Parse ASCII output for one IP. Returns dict or None."""
    if not text or not search_ip:
        return None
    for line in text.splitlines():
        if search_ip not in line:
            continue
        flag = "L"
        for m in re.finditer(r'["\']flag["\']\s*:\s*["\']?([LR])', line, re.I):
            flag = m.group(1).upper()
            break
        phys = ""
        for m in re.finditer(r'["\']physical-iod["\']\s*:\s*["\']([^"\']*)["\']', line, re.I):
            phys = m.group(1).strip()
            break
        if not phys and "physical" in line.lower():
            for m in re.finditer(r'physical[_-]?iod["\']?\s*:\s*["\']?\(?([^)"\']*)', line, re.I):
                phys = m.group(1).strip()
                break
        remote = ""
        for m in re.finditer(r'["\']remote-vtep-addr["\']\s*:\s*["\']([^"\']*)["\']', line, re.I):
            remote = m.group(1).strip()
            break
        return {"flag": flag, "physical_iod": phys, "remote_vtep_addr": remote}
    return None


def _parse_cisco_power(raw_output: Any) -> dict[str, Any]:
    """Parse Cisco 'show environment power'. powersup.TABLE_psinfo.ROW_psinfo, count ps_status == 'Ok'."""
    data = raw_output
    if isinstance(raw_output, str) and raw_output.strip().startswith("{"):
        try:
            data = json.loads(raw_output)
        except Exception:
            data = {}
    if not data:
        return {"Power supplies": ""}
    try:
        powersup = _find_key(data, "powersup")
        if not isinstance(powersup, dict):
            body = _find_key(data, "body")
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except Exception:
                    return {"Power supplies": ""}
            data = body if isinstance(body, dict) else data
            powersup = data.get("powersup") if isinstance(data, dict) else None
        if not isinstance(powersup, dict):
            return {"Power supplies": ""}
        table = powersup.get("TABLE_psinfo") or powersup.get("table_psinfo")
        if not isinstance(table, dict):
            return {"Power supplies": ""}
        rows = table.get("ROW_psinfo") or table.get("row_psinfo")
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            return {"Power supplies": ""}
        count = sum(1 for r in rows if isinstance(r, dict) and (str(r.get("ps_status") or "").strip() == "Ok"))
        return {"Power supplies": count}
    except Exception:
        return {"Power supplies": ""}


def parse_output(command_id: str, raw_output: Any, parser_config: dict) -> dict[str, Any]:
    """
    Apply parser_config to raw_output. raw_output can be dict (API JSON) or str (SSH text).
    Returns dict of field_name -> value (string or number).
    """
    if parser_config is None:
        return {}
    fields = parser_config.get("fields") or []
    result = {}
    # Normalize: if raw_output is str, try parse as JSON for json_path
    data = raw_output
    text = raw_output if isinstance(raw_output, str) else ""
    if isinstance(raw_output, str) and raw_output.strip().startswith("{"):
        try:
            data = json.loads(raw_output)
        except Exception:
            pass
    custom_parser = parser_config.get("custom_parser")
    if custom_parser == "cisco_isis_interface_brief":
        result = _parse_cisco_isis_interface_brief(raw_output)
    elif custom_parser == "arista_isis_adjacency":
        result = _parse_arista_isis_adjacency(raw_output)
    elif custom_parser == "cisco_system_uptime":
        result = _parse_cisco_system_uptime(raw_output)
    elif custom_parser == "arista_uptime":
        result = _parse_arista_uptime(raw_output)
    elif custom_parser == "arista_cpu":
        result = _parse_arista_cpu(raw_output)
    elif custom_parser == "arista_disk":
        result = _parse_arista_disk(raw_output)
    elif custom_parser == "arista_power":
        result = _parse_arista_power(raw_output)
    elif custom_parser == "cisco_power":
        result = _parse_cisco_power(raw_output)
    elif custom_parser == "arista_transceiver":
        result = _parse_arista_transceiver(raw_output)
    elif custom_parser == "cisco_nxos_transceiver":
        result = _parse_cisco_nxos_transceiver(raw_output)
    elif custom_parser == "arista_interface_status":
        result = _parse_arista_interface_status(raw_output)
    elif custom_parser == "cisco_interface_status":
        result = _parse_cisco_interface_status(raw_output)
    elif custom_parser == "arista_interface_description":
        result = _parse_arista_interface_description(raw_output)
    elif custom_parser == "cisco_interface_description":
        result = _parse_cisco_interface_description(raw_output)
    elif custom_parser == "cisco_interface_detailed":
        result = _parse_cisco_interface_detailed(raw_output)
    elif custom_parser == "cisco_interface_show_mtu":
        result = _parse_cisco_interface_show_mtu(raw_output)
    else:
        for f in fields:
            name = (f.get("name") or "").strip()
            if not name:
                continue
            if f.get("format_template") and f.get("format_fields"):
                continue  # applied after loop
            if f.get("json_path"):
                count_where = f.get("count_where")
                key_prefix = f.get("key_prefix") or f.get("count_key_prefix")
                if f.get("count"):
                    flatten_inner = f.get("flatten_inner_path")
                    if isinstance(count_where, dict) and count_where:
                        result[name] = _count_where(
                            data,
                            f["json_path"],
                            count_where,
                            key_prefix=key_prefix,
                            key_prefix_exclude=f.get("count_key_prefix_exclude"),
                            flatten_inner_path=flatten_inner,
                        )
                    else:
                        result[name] = _count_from_json(data, f["json_path"], flatten_inner_path=flatten_inner)
                elif f.get("key_prefix") and f.get("value_key"):
                    div = f.get("value_divide") or f.get("value_divisor") or 1
                    val = _get_from_dict_by_key_prefix(
                        data, f["json_path"], f["key_prefix"], f["value_key"], divisor=div
                    )
                    if val is None:
                        result[name] = None
                    elif f.get("value_suffix"):
                        num = float(val) if not isinstance(val, (int, float)) else val
                        result[name] = (str(int(num)) if num == int(num) else str(round(num, 2))) + f.get("value_suffix")
                    else:
                        result[name] = val if isinstance(val, (int, float)) else str(val)
                else:
                    val = _get_path(data, f["json_path"])
                    _apply_value_subtract_and_suffix(f, val, result, name)
            elif f.get("regex"):
                if f.get("count"):
                    result[name] = _count_regex_lines(text, f["regex"])
                else:
                    result[name] = _extract_regex(text, f["regex"]) or ""
    # Apply format_template fields (e.g. ISIS "up/ready", BGP "est/total")
    for f in fields:
        if not f.get("format_template") or not f.get("format_fields"):
            continue
        name = (f.get("name") or "").strip()
        if not name:
            continue
        fmt_fields = f["format_fields"]
        try:
            result[name] = f["format_template"].format(**{k: result.get(k, "") for k in fmt_fields})
        except (KeyError, ValueError):
            result[name] = ""
    return result
