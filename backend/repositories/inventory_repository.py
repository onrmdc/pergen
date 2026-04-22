"""
``InventoryRepository`` — class wrapper around the inventory CSV.

Behaviour is identical to the pure-function helpers in
``backend/inventory/loader.py`` (sort by IP, normalise site/role,
lowercase keys).  The class form makes the dependency injectable so
services and Blueprints can be unit-tested without touching the real
``backend/inventory/inventory.csv`` file.
"""
from __future__ import annotations

import csv
import logging
import os
import threading

_log = logging.getLogger("app.repository.inventory")


_HEADER = [
    "hostname",
    "ip",
    "fabric",
    "site",
    "hall",
    "vendor",
    "model",
    "role",
    "tag",
    "credential",
]


def _ip_sort_key(d: dict) -> tuple:
    """Stable 4-octet IP sort key.

    Phase 13: enforce ``len(parts) == 4`` so a malformed CSV row like
    ``ip="10.0"`` cannot collide with valid 4-octet addresses and shuffle
    the sort order non-deterministically.
    """
    ip = (d.get("ip") or "").strip()
    if not ip:
        return (999, 999, 999, 999)
    parts = ip.split(".")
    if len(parts) != 4:
        return (999, 999, 999, 999)
    try:
        return tuple(min(255, max(0, int(x))) for x in parts)
    except (ValueError, TypeError):
        return (999, 999, 999, 999)


def _normalize_site(s: str) -> str:
    return ((s or "").strip()).title()


def _normalize_role(s: str) -> str:
    r = (s or "").strip()
    if r == "Border-":
        return "Border-Leaf"
    return r


class InventoryRepository:
    """File-backed repository for the device inventory CSV."""

    HEADER = tuple(_HEADER)

    def __init__(self, csv_path: str) -> None:
        """
        Inputs
        ------
        csv_path : full path to the inventory CSV file.

        Outputs
        -------
        ``InventoryRepository`` instance.  No file is opened until
        ``load`` / ``save`` is called.

        Security
        --------
        ``csv_path`` is treated as trusted operator-supplied input.
        Per-cell content is *not* sanitised here — callers that surface
        inventory values to network devices MUST run them through
        ``InputSanitizer`` (e.g. ``sanitize_ip``, ``sanitize_hostname``).
        """
        self._csv_path = csv_path
        self._lock = threading.Lock()

    @property
    def csv_path(self) -> str:
        """Filesystem path of the inventory CSV (read-only public API).

        Audit H1 fix: replaces direct ``repo._csv_path`` access from the
        factory and ``network_lookup_bp``. The attribute is read-only —
        services that need a different path must construct a new
        repository.
        """
        return self._csv_path

    # ------------------------------------------------------------------ #
    # IO
    # ------------------------------------------------------------------ #
    def load(self) -> list[dict]:
        """Read the CSV and return the device list (sorted by IP)."""
        if not os.path.isfile(self._csv_path):
            return []
        rows = []
        with open(self._csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                r = {
                    k.strip().lower(): (v.strip() if isinstance(v, str) else v)
                    for k, v in row.items()
                    if k
                }
                if not r.get("hostname"):
                    continue
                r["site"] = _normalize_site(r.get("site") or "")
                r["role"] = _normalize_role(r.get("role") or "")
                rows.append(r)
        rows.sort(key=_ip_sort_key)
        return rows

    def save(self, devices: list[dict]) -> None:
        """Write devices to CSV using the canonical header (atomic-ish)."""
        os.makedirs(os.path.dirname(self._csv_path) or ".", exist_ok=True)
        with self._lock, open(self._csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_HEADER, extrasaction="ignore")
            writer.writeheader()
            for d in devices:
                row = {
                    k: (d.get(k) if isinstance(d.get(k), str) else (d.get(k) or ""))
                    for k in _HEADER
                }
                row["site"] = _normalize_site(row.get("site") or "")
                row["role"] = _normalize_role(row.get("role") or "")
                writer.writerow(row)

    # ------------------------------------------------------------------ #
    # filters (parity with backend/inventory/loader.py)
    # ------------------------------------------------------------------ #
    def fabrics(self, devices: list[dict] | None = None) -> list[str]:
        devs = devices if devices is not None else self.load()
        return sorted({d["fabric"] for d in devs if d.get("fabric")})

    def sites(self, fabric: str, devices: list[dict] | None = None) -> list[str]:
        devs = devices if devices is not None else self.load()
        return sorted(
            {d["site"] for d in devs if d.get("fabric") == fabric and d.get("site")}
        )

    def halls(
        self, fabric: str, site: str, devices: list[dict] | None = None
    ) -> list[str]:
        devs = devices if devices is not None else self.load()
        if site:
            subset = [d for d in devs if d.get("fabric") == fabric and d.get("site") == site]
        else:
            subset = [d for d in devs if d.get("fabric") == fabric]
        return sorted(
            {(d.get("hall") or "").strip() for d in subset if (d.get("hall") or "").strip()}
        )

    def roles(
        self,
        fabric: str,
        site: str,
        hall: str | None = None,
        devices: list[dict] | None = None,
    ) -> list[str]:
        devs = devices if devices is not None else self.load()
        if site:
            subset = [d for d in devs if d.get("fabric") == fabric and d.get("site") == site]
        else:
            subset = [d for d in devs if d.get("fabric") == fabric]
        if hall:
            subset = [d for d in subset if (d.get("hall") or "") == hall]
        return sorted({d["role"] for d in subset if d.get("role")})

    def devices(
        self,
        fabric: str,
        site: str,
        role: str | None = None,
        hall: str | None = None,
        devices: list[dict] | None = None,
    ) -> list[dict]:
        devs = devices if devices is not None else self.load()
        if site:
            subset = [d for d in devs if d.get("fabric") == fabric and d.get("site") == site]
        else:
            subset = [d for d in devs if d.get("fabric") == fabric]
        if hall:
            subset = [d for d in subset if (d.get("hall") or "") == hall]
        if role:
            subset = [d for d in subset if d.get("role") == role]
        subset.sort(key=_ip_sort_key)
        return subset

    def devices_by_tag(
        self, tag: str, devices: list[dict] | None = None
    ) -> list[dict]:
        devs = devices if devices is not None else self.load()
        tag_lower = (tag or "").strip().lower()
        out = [d for d in devs if (d.get("tag") or "").strip().lower() == tag_lower]
        out.sort(key=_ip_sort_key)
        return out
