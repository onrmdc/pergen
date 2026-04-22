"""
Interface-status normalisation and trace helpers.

Phase-2 deliverable — extracted verbatim from ``backend/app.py``.
The trace helpers take a parser result and produce a UI-friendly
"what ran / what came back" diagnostic; the merge helper folds Cisco
NX-OS detailed flap data into an Arista-style status map; the lookup
helper does case-fold + whitespace-tolerant interface name matching.

Pure functions; no Flask dependency.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any

from backend.config import commands_loader as cmd_loader


def iface_status_lookup(status_by_interface: Mapping, iface: str) -> Any:
    """Look up ``iface`` in ``status_by_interface`` with two fallbacks.

    1. Direct key match — value returned as-is (may be a non-dict; the
       legacy contract preserves whatever the caller stored).
    2. Case-fold or whitespace-stripped key match — value returned only
       if it is a dict, otherwise an empty dict.
    3. Returns ``{}`` when the interface is unknown.
    """
    if iface in status_by_interface:
        return status_by_interface[iface]
    i_low = iface.lower()
    i_compact = iface.replace(" ", "")
    for k, v in status_by_interface.items():
        if k.lower() == i_low or k.replace(" ", "") == i_compact:
            return v if isinstance(v, dict) else {}
    return {}


def merge_cisco_detailed_flap(
    status_by_interface: MutableMapping,
    flap_rows: list,
) -> None:
    """Merge ``interface_flapped_rows`` into ``status_by_interface``.

    For each flap row, find or create a canonical entry (case-fold +
    whitespace-tolerant) and overlay flap-time / counters / epoch.
    Empty / dash sentinels (``""`` / ``"-"``) are intentionally
    skipped to avoid clobbering real values from the status command.
    Non-dict rows and rows without an ``interface`` key are dropped.
    """
    for fr in flap_rows:
        if not isinstance(fr, dict):
            continue
        iface = str(fr.get("interface") or "").strip()
        if not iface:
            continue
        canon = None
        if iface in status_by_interface:
            canon = iface
        else:
            for k in list(status_by_interface.keys()):
                if k.lower() == iface.lower() or k.replace(" ", "") == iface.replace(" ", ""):
                    canon = k
                    break
        if canon is None:
            canon = iface
        b = status_by_interface.setdefault(canon, {})
        lf = fr.get("last_link_flapped")
        if lf is not None and str(lf).strip() not in ("", "-"):
            b["last_link_flapped"] = str(lf).strip()
        fc = fr.get("flap_counter")
        if fc is not None and str(fc).strip() not in ("", "-"):
            b["flap_count"] = str(fc).strip()
        crc = fr.get("crc_count")
        if crc is not None and str(crc).strip() not in ("", "-"):
            b["crc_count"] = str(crc).strip()
        ine = fr.get("in_errors")
        if ine is not None and str(ine).strip() not in ("", "-"):
            b["in_errors"] = str(ine).strip()
        ep = fr.get("last_status_change_epoch")
        if isinstance(ep, (int, float)) and ep > 0:
            b["last_status_change_epoch"] = ep


def interface_status_trace(status_result: Mapping) -> list:
    """Explain which ``*_interface_status`` commands ran (UI / debug)."""
    out: list = []
    for entry in status_result.get("commands") or []:
        cid = (entry.get("command_id") or "").strip()
        if "interface_status" not in cid.lower():
            continue
        pcfg = cmd_loader.get_parser(cid) or {}
        parser_name = pcfg.get("custom_parser") or "(yaml fields only)"
        parsed = entry.get("parsed") or {}
        rows = parsed.get("interface_status_rows") or []
        sample_ifaces = [
            str(r.get("interface") or "").strip()
            for r in rows[:12]
            if isinstance(r, dict)
        ]
        raw = entry.get("raw")
        raw_keys: list = []
        if isinstance(raw, dict):
            raw_keys = list(raw.keys())[:16]
        elif isinstance(raw, list) and raw and isinstance(raw[0], dict):
            raw_keys = list(raw[0].keys())[:16]
        sample_flap: list = []
        for r in rows[:8]:
            if not isinstance(r, dict):
                continue
            sample_flap.append(
                {
                    "interface": str(r.get("interface") or "").strip(),
                    "flap_count": r.get("flap_count"),
                    "last_link_flapped": r.get("last_link_flapped"),
                }
            )
        out.append(
            {
                "command_id": cid,
                "cli_commands": cmd_loader.get_command_cli_commands(cid),
                "parser": parser_name,
                "command_error": entry.get("error"),
                "parsed_row_count": len(rows),
                "sample_interfaces": sample_ifaces,
                "sample_flap_fields": sample_flap,
                "raw_top_level_keys": raw_keys,
            }
        )
    return out


def cisco_interface_detailed_trace(detailed_result: Mapping) -> list:
    """Trace for ``cisco_nxos_show_interface`` (flap/reset from detailed JSON)."""
    out: list = []
    for entry in detailed_result.get("commands") or []:
        cid = (entry.get("command_id") or "").strip()
        if cid != "cisco_nxos_show_interface":
            continue
        pcfg = cmd_loader.get_parser(cid) or {}
        parser_name = pcfg.get("custom_parser") or "(yaml fields only)"
        parsed = entry.get("parsed") or {}
        rows = parsed.get("interface_flapped_rows") or []
        raw = entry.get("raw")
        raw_keys: list = []
        if isinstance(raw, dict):
            raw_keys = list(raw.keys())[:16]
        elif isinstance(raw, list) and raw and isinstance(raw[0], dict):
            raw_keys = list(raw[0].keys())[:16]
        sample: list = []
        for r in rows[:8]:
            if not isinstance(r, dict):
                continue
            sample.append(
                {
                    "interface": str(r.get("interface") or "").strip(),
                    "flap_counter": r.get("flap_counter"),
                    "last_link_flapped": r.get("last_link_flapped"),
                    "crc_count": r.get("crc_count"),
                    "in_errors": r.get("in_errors"),
                }
            )
        out.append(
            {
                "command_id": cid,
                "cli_commands": cmd_loader.get_command_cli_commands(cid),
                "parser": parser_name,
                "command_error": entry.get("error"),
                "parsed_flap_row_count": len(rows),
                "sample_flap_from_detailed": sample,
                "raw_top_level_keys": raw_keys,
            }
        )
    return out
