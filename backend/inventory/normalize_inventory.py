#!/usr/bin/env python3
"""
Normalize inventory CSV: fill missing columns from hostname using rules.
- Role: S...→Spine, L...→Leaf, BL...→Border-Leaf, BG...→Border-Gateway,
        WANEDGESW/WANEDGE→Wan-Edge, DCFW→Firewall (LSW in name → Leaf for H13-EXTEND-LSW)
- Site: ES in hostname→Venus, IL in hostname→Mars
- Vendor/Model: ES→Cisco/NX-OS, IL→Arista/EOS; DCFW+IL→Palo-Alto/PANOS, DCFW+ES→Cisco/PANOS
- Fabric: TYC, TGO, SEC, 3RD, WED from hostname segments
- Hall: H2,H4,H6,H9,H13,H14 → Hall-2, Hall-4, ...
- credential: fabric lowercase
- tag: do-not-search (default)
"""
import csv
import os
import re
import sys

HEADER = ["hostname", "ip", "fabric", "site", "hall", "vendor", "model", "role", "tag", "credential"]
FABRIC_TOKENS = {"TYC", "TGO", "SEC", "3RD", "WED"}
HALL_RE = re.compile(r"^H(\d+)$", re.I)


def _parts(h: str):
    return [p.strip() for p in (h or "").split("-") if p.strip()]


def _role_from_hostname(hostname: str) -> str:
    h = (hostname or "").upper()
    p = _parts(hostname)
    if any(s == "DCFW" for s in p) or h.startswith("DCFW"):
        return "Firewall"
    if h.startswith("WANEDGESW") or h.startswith("WANEDGE"):
        return "Wan-Edge"
    if h.startswith("BGSW"):
        return "Border-Gateway"
    if h.startswith("BLSW"):
        return "Border-Leaf"
    if h.startswith("SSW") or (h.startswith("S") and not h.startswith("BL") and not h.startswith("BG")):
        return "Spine"
    if h.startswith("LSW") or "LSW" in p:
        return "Leaf"
    return ""


def _site_from_hostname(hostname: str) -> str:
    h = hostname or ""
    if "ES" in h.upper() and "-ES-" in h.upper() or h.upper().startswith("ES-") or _parts(h)[:5] and "ES" in _parts(h):
        return "Venus"
    if "IL" in h.upper():
        return "Mars"
    return ""


def _vendor_model_from_hostname(hostname: str) -> tuple[str, str]:
    h = (hostname or "").upper()
    p = _parts(hostname)
    is_dcfw = "DCFW" in p or h.startswith("DCFW")
    has_es = "ES" in p or "-ES-" in h
    has_il = any(x.startswith("IL") for x in p) or "-IL" in h
    if is_dcfw:
        if has_il:
            return "Palo-Alto", "PANOS"
        return "Cisco", "PANOS"
    if has_es:
        return "Cisco", "NX-OS"
    if has_il:
        return "Arista", "EOS"
    return "", ""


def _fabric_from_hostname(hostname: str) -> str:
    p = _parts(hostname)
    for seg in p:
        if seg.upper() in FABRIC_TOKENS:
            return seg.upper() if seg == "3RD" else seg.upper()
    if len(p) > 4:
        return p[4]
    return ""


def _hall_from_hostname(hostname: str) -> str:
    p = _parts(hostname)
    for seg in p:
        m = HALL_RE.match(seg)
        if m:
            return "Hall-" + m.group(1)
    return ""


def normalize_row(row: list) -> list:
    while len(row) < len(HEADER):
        row.append("")
    row = row[: len(HEADER)]
    hostname = (row[0] or "").strip()
    ip = (row[1] or "").strip()
    if not hostname:
        return row
    fabric = (row[2] or "").strip() or _fabric_from_hostname(hostname)
    site = (row[3] or "").strip() or _site_from_hostname(hostname)
    hall = (row[4] or "").strip() or _hall_from_hostname(hostname)
    vendor = (row[5] or "").strip()
    model = (row[6] or "").strip()
    if not vendor or not model:
        v, m = _vendor_model_from_hostname(hostname)
        if not vendor:
            vendor = v
        if not model:
            model = m
    role = (row[7] or "").strip() or _role_from_hostname(hostname)
    tag = (row[8] or "").strip() or "do-not-search"
    credential = (row[9] or "").strip() or (fabric.lower() if fabric else "")

    # Normalize casing to match existing style
    if site:
        site = "Venus" if site.upper() == "VENUS" else "Mars" if site.upper() == "MARS" else site.title()
    if hall:
        m = re.match(r"^HALL-(\d+)$", hall, re.I)
        if m:
            hall = "Hall-" + m.group(1)
        else:
            m = re.match(r"^H(\d+)$", hall, re.I)
            if m:
                hall = "Hall-" + m.group(1)
            elif hall.isdigit():
                hall = "Hall-" + hall
    if vendor:
        vendor = "Cisco" if vendor.upper() == "CISCO" else "Arista" if vendor.upper() == "ARISTA" else "Palo-Alto" if "palo" in vendor.lower() else vendor
    if model:
        model = "NX-OS" if "nx-os" in model.lower() or model.upper() == "NX-OS" else "EOS" if model.upper() == "EOS" else "PANOS" if "panos" in model.lower() else model
    if role:
        role = role.replace("_", "-")
        if role.lower() == "leaf":
            role = "Leaf"
        elif role.lower() == "spine":
            role = "Spine"
        elif role.lower() in ("border-leaf", "borderleaf"):
            role = "Border-Leaf"
        elif role.lower() in ("border-gateway", "bordergateway"):
            role = "Border-Gateway"
        elif role.lower() in ("wan-edge", "wanedge"):
            role = "Wan-Edge"
        elif role.lower() == "firewall":
            role = "Firewall"
        else:
            role = role.title()
    if fabric:
        fabric = fabric.lower()
    if credential:
        credential = credential.lower()

    # Hostname as-is; all other columns lowercase
    out = [hostname, ip, fabric, site, hall, vendor, model, role, tag, credential]
    return [out[0]] + [str(x).lower() for x in out[1:]]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else ""
    if not path:
        path = os.path.join(os.path.dirname(__file__), "example_inventory.csv")
    if not os.path.isfile(path):
        print("File not found:", path, file=sys.stderr)
        sys.exit(1)
    data_rows = []
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    start = 0
    if lines and lines[0].strip().lower().startswith("hostname"):
        start = 1
    for i in range(start, len(lines)):
        line = lines[i].rstrip("\n\r")
        if not line.strip():
            continue
        row = [c.strip() for c in line.split(",")]
        data_rows.append(normalize_row(row))
    # Remove duplicate rows (keep first occurrence)
    n_before = len(data_rows)
    seen = set()
    unique_rows = []
    for r in data_rows:
        key = tuple(r)
        if key not in seen:
            seen.add(key)
            unique_rows.append(r)
    data_rows = unique_rows
    n_removed = n_before - len(data_rows)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        for r in data_rows:
            writer.writerow(r)
    print("Normalized", len(data_rows), "rows to", path, end="")
    if n_removed:
        print(" (removed", n_removed, "duplicate(s))")
    else:
        print()


if __name__ == "__main__":
    main()
