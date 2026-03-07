"""
Load single inventory CSV and provide hierarchical filters.
Columns: hostname, ip, fabric, site, hall, vendor, model, role, tag, credential.
Site/role normalized for consistent filtering (e.g. mars -> Mars).
Device lists are always returned sorted by IP address.
"""
import csv
import os
from typing import Optional


def _ip_sort_key(d: dict) -> tuple:
    """Sort key for device by IP (dotted-decimal order). Empty/invalid IPs last."""
    ip = (d.get("ip") or "").strip()
    if not ip:
        return (999, 999, 999, 999)
    parts = ip.split(".")
    try:
        return tuple(min(255, max(0, int(x))) for x in parts[:4])
    except (ValueError, TypeError):
        return (999, 999, 999, 999)

def _default_inventory_path():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "inventory", "inventory.csv")
    example = os.path.join(base, "inventory", "example_inventory.csv")
    if not os.path.isfile(path) and os.path.isfile(example):
        return example
    return path


def _normalize_site(s: str) -> str:
    if not s:
        return ""
    return (s.strip() or "").title()


def _normalize_role(s: str) -> str:
    if not s:
        return ""
    r = (s.strip() or "").strip()
    if r == "Border-":
        return "Border-Leaf"
    return r


def load_inventory(path: Optional[str] = None) -> list[dict]:
    """Load CSV; return list of device dicts with normalized site/role. Keys lowercase."""
    p = path or _default_inventory_path()
    if not os.path.isfile(p):
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            r = {k.strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
            if not r.get("hostname"):
                continue
            r["site"] = _normalize_site(r.get("site") or "")
            r["role"] = _normalize_role(r.get("role") or "")
            rows.append(r)
    rows.sort(key=_ip_sort_key)
    return rows


def get_fabrics(devices: Optional[list[dict]] = None) -> list[str]:
    devices = devices or load_inventory()
    fabrics = sorted({d["fabric"] for d in devices if d.get("fabric")})
    return fabrics


def get_sites(fabric: str, devices: Optional[list[dict]] = None) -> list[str]:
    devices = devices or load_inventory()
    sites = sorted({d["site"] for d in devices if d.get("fabric") == fabric and d.get("site")})
    return sites


def get_halls(fabric: str, site: str, devices: Optional[list[dict]] = None) -> list[str]:
    devices = devices or load_inventory()
    if site:
        subset = [d for d in devices if d.get("fabric") == fabric and d.get("site") == site]
    else:
        subset = [d for d in devices if d.get("fabric") == fabric]
    halls = sorted({(d.get("hall") or "").strip() for d in subset if (d.get("hall") or "").strip()})
    return halls


def get_roles(fabric: str, site: str, hall: Optional[str] = None, devices: Optional[list[dict]] = None) -> list[str]:
    devices = devices or load_inventory()
    if site:
        subset = [d for d in devices if d.get("fabric") == fabric and d.get("site") == site]
    else:
        subset = [d for d in devices if d.get("fabric") == fabric]
    if hall:
        subset = [d for d in subset if (d.get("hall") or "") == hall]
    roles = sorted({d["role"] for d in subset if d.get("role")})
    return roles


def get_devices(
    fabric: str,
    site: str,
    role: Optional[str] = None,
    hall: Optional[str] = None,
    devices: Optional[list[dict]] = None,
) -> list[dict]:
    """Return devices for fabric/site (site empty = all sites), optionally filtered by role and hall."""
    devices = devices or load_inventory()
    if site:
        subset = [d for d in devices if d.get("fabric") == fabric and d.get("site") == site]
    else:
        subset = [d for d in devices if d.get("fabric") == fabric]
    if hall:
        subset = [d for d in subset if (d.get("hall") or "") == hall]
    if role:
        subset = [d for d in subset if d.get("role") == role]
    subset.sort(key=_ip_sort_key)
    return subset


def get_devices_by_tag(tag: str, devices: Optional[list[dict]] = None) -> list[dict]:
    """Return devices whose tag (case-insensitive) equals the given tag."""
    devices = devices or load_inventory()
    tag_lower = (tag or "").strip().lower()
    out = [d for d in devices if (d.get("tag") or "").strip().lower() == tag_lower]
    out.sort(key=_ip_sort_key)
    return out


INVENTORY_HEADER = ["hostname", "ip", "fabric", "site", "hall", "vendor", "model", "role", "tag", "credential"]


def save_inventory(devices: list[dict], path: Optional[str] = None) -> None:
    """Write devices to CSV. path must be the full path to inventory.csv (not example)."""
    p = path or _default_inventory_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INVENTORY_HEADER, extrasaction="ignore")
        writer.writeheader()
        for d in devices:
            row = {k: (d.get(k) if isinstance(d.get(k), str) else (d.get(k) or "")) for k in INVENTORY_HEADER}
            row["site"] = _normalize_site(row.get("site") or "")
            row["role"] = _normalize_role(row.get("role") or "")
            writer.writerow(row)
