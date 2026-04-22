"""
``InventoryService`` — façade over the inventory repository.

Phase 9 introduced the read-side use-case API consumed by
``inventory_bp``. Phase 3 of the app.py decomposition extends the
service with the *write*-side use cases (add / update / delete /
import) so the blueprint can stay a thin transport layer.
"""
from __future__ import annotations

from typing import Any

from backend.inventory.loader import INVENTORY_HEADER
from backend.repositories import InventoryRepository


class InventoryService:
    """High-level inventory operations (read + write)."""

    def __init__(self, inventory_repo: InventoryRepository) -> None:
        self._repo = inventory_repo

    @property
    def csv_path(self) -> str:
        """Public read-only path of the underlying inventory CSV.

        Audit H1 fix: replaces ``svc._repo._csv_path`` access from
        ``network_lookup_bp`` and the factory's path-aware re-binding.
        """
        return self._repo.csv_path

    # ------------------------------------------------------------------ #
    # Read API                                                           #
    # ------------------------------------------------------------------ #
    def all(self) -> list[dict]:
        """Return every device in the inventory (sorted by IP)."""
        return self._repo.load()

    def fabrics(self) -> list[str]:
        return self._repo.fabrics()

    def sites(self, fabric: str) -> list[str]:
        return self._repo.sites(fabric)

    def halls(self, fabric: str, site: str) -> list[str]:
        return self._repo.halls(fabric, site)

    def roles(self, fabric: str, site: str, hall: str | None = None) -> list[str]:
        return self._repo.roles(fabric, site, hall)

    def devices(
        self,
        *,
        fabric: str,
        site: str,
        role: str | None = None,
        hall: str | None = None,
    ) -> list[dict]:
        return self._repo.devices(fabric=fabric, site=site, role=role, hall=hall)

    def devices_by_tag(self, tag: str) -> list[dict]:
        return self._repo.devices_by_tag(tag=tag)

    def save(self, devices: list[dict]) -> None:
        self._repo.save(devices)

    # ------------------------------------------------------------------ #
    # Normalisation (was app.py:_device_row)                             #
    # ------------------------------------------------------------------ #
    # Audit H4: every inventory request must use one of these column
    # names (plus the special-case ``current_hostname`` for updates).
    # Anything else is mass-assignment and gets rejected.
    _ALLOWED_FIELDS = frozenset({*INVENTORY_HEADER, "current_hostname"})

    @staticmethod
    def normalise_device_row(d: Any) -> dict | None:
        """Coerce a raw request body into one canonical inventory row.

        Returns ``None`` when the input is missing or not a mapping.
        Every column from ``INVENTORY_HEADER`` is present in the output;
        string values are stripped, ``None`` becomes ``""``.

        This is the LOW-LEVEL normaliser. Call ``validate_device_row``
        for input that came from an untrusted client.
        """
        if not d or not isinstance(d, dict):
            return None
        row: dict = {}
        for k in INVENTORY_HEADER:
            v = d.get(k) or ""
            row[k] = v.strip() if isinstance(v, str) else (v if v is not None else "")
        return row

    @classmethod
    def validate_device_row(cls, d: Any) -> tuple[dict | None, str | None]:
        """Sanitise + reject mass-assignment for an untrusted device payload.

        Audit H4: applies ``InputSanitizer`` per-column and rejects any
        unknown top-level key. Returns ``(row, None)`` on success or
        ``(None, error_message)`` on failure.

        Note on empty payloads: an empty dict ``{}`` is treated as
        "no fields supplied" — the caller's `add_device` / `update_device`
        will then return the legacy "hostname is required" message,
        preserving the historical contract.
        """
        from backend.security import InputSanitizer

        if d is None or not isinstance(d, dict):
            return None, "device payload must be an object"

        # Mass-assignment guard: reject any keys outside the allow-list.
        unknown = set(d.keys()) - cls._ALLOWED_FIELDS
        if unknown:
            return None, f"unknown field(s): {sorted(unknown)!r}"

        row = cls.normalise_device_row(d) or {k: "" for k in INVENTORY_HEADER}

        # Per-column validation. Empty strings are allowed (some columns
        # are optional in the legacy contract); only validate non-empty.
        ip = (row.get("ip") or "").strip()
        if ip:
            ok, _reason = InputSanitizer.sanitize_ip(ip)
            if not ok:
                return None, f"invalid ip: {ip!r}"

        host = (row.get("hostname") or "").strip()
        if host:
            ok, _reason = InputSanitizer.sanitize_hostname(host)
            if not ok:
                return None, f"invalid hostname: {host!r}"

        cred = (row.get("credential") or "").strip()
        if cred:
            ok, _reason = InputSanitizer.sanitize_credential_name(cred)
            if not ok:
                return None, f"invalid credential name: {cred!r}"

        return row, None

    # ------------------------------------------------------------------ #
    # Write API                                                          #
    # ------------------------------------------------------------------ #
    def add_device(self, payload: Any) -> tuple[bool, dict]:
        """Add a single device (uniqueness on hostname + ip).

        Audit H4: validates per-field and rejects unknown fields before
        any IO. Returns ``(True, {"ok": True, "device": row})`` on
        success or ``(False, {"error": "<message>"})`` for any validation
        failure. Status-code mapping is the blueprint's responsibility.
        """
        row, err = self.validate_device_row(payload)
        if err:
            return False, {"error": err}
        if not row or not (row.get("hostname") or "").strip():
            return False, {"error": "hostname is required"}
        hostname = (row.get("hostname") or "").strip()
        ip = (row.get("ip") or "").strip()
        devs = self._repo.load()
        if any((d.get("hostname") or "").strip().lower() == hostname.lower() for d in devs):
            return False, {"error": "hostname already exists"}
        if ip and any((d.get("ip") or "").strip() == ip for d in devs):
            return False, {"error": "IP address already exists"}
        devs.append(row)
        self._repo.save(devs)
        return True, {"ok": True, "device": row}

    def update_device(self, payload: Any) -> tuple[bool, dict, int]:
        """Update one device identified by ``current_hostname``.

        Returns ``(ok, body, status)`` so the route can issue 200 / 400 / 404.
        """
        if not isinstance(payload, dict):
            return False, {"error": "current_hostname is required"}, 400
        current = (payload.get("current_hostname") or "").strip()
        if not current:
            return False, {"error": "current_hostname is required"}, 400
        row, err = self.validate_device_row(payload)
        if err:
            return False, {"error": err}, 400
        if not row or not (row.get("hostname") or "").strip():
            return False, {"error": "hostname is required"}, 400
        hostname = (row.get("hostname") or "").strip()
        ip = (row.get("ip") or "").strip()
        devs = self._repo.load()
        idx = next(
            (i for i, d in enumerate(devs) if (d.get("hostname") or "").strip() == current),
            None,
        )
        if idx is None:
            return False, {"error": "device not found"}, 404
        if hostname.lower() != current.lower() and any(
            (d.get("hostname") or "").strip().lower() == hostname.lower() for d in devs
        ):
            return False, {"error": "hostname already exists"}, 400
        if ip and any(
            (d.get("ip") or "").strip() == ip for i, d in enumerate(devs) if i != idx
        ):
            return False, {"error": "IP address already exists"}, 400
        devs[idx] = row
        self._repo.save(devs)
        return True, {"ok": True, "device": row}, 200

    def delete_device(self, hostname: str = "", ip: str = "") -> tuple[bool, dict, int]:
        """Delete by hostname or ip query arg.

        ``(ok, body, status)`` — 400 if neither key supplied, 404 if no
        matching row, 200 on success.
        """
        hostname = (hostname or "").strip()
        ip = (ip or "").strip()
        if not hostname and not ip:
            return False, {"error": "hostname or ip required"}, 400
        before = self._repo.load()
        if hostname:
            after = [d for d in before if (d.get("hostname") or "").strip() != hostname]
        else:
            after = [d for d in before if (d.get("ip") or "").strip() != ip]
        if len(after) == len(before):
            return False, {"error": "device not found"}, 404
        self._repo.save(after)
        return True, {"ok": True}, 200

    def import_devices(self, rows: Any) -> tuple[bool, dict, int]:
        """Bulk-append ``rows``; dedupe against existing hostname / ip.

        Mirrors the legacy contract: returns ``{ok, added, skipped[]}``
        where each skipped entry has ``{row, reason}``.
        """
        if not isinstance(rows, list):
            return False, {"error": "rows array required"}, 400
        devs = self._repo.load()
        existing_hostnames = {(d.get("hostname") or "").strip().lower() for d in devs}
        existing_ips = {(d.get("ip") or "").strip() for d in devs if (d.get("ip") or "").strip()}
        added = 0
        skipped: list[dict] = []
        for r in rows:
            row, err = self.validate_device_row(r)
            if err:
                skipped.append({"row": r, "reason": err})
                continue
            if not row or not (row.get("hostname") or "").strip():
                skipped.append({"row": r, "reason": "missing hostname"})
                continue
            hostname = (row.get("hostname") or "").strip()
            ip = (row.get("ip") or "").strip()
            if hostname.lower() in existing_hostnames:
                skipped.append({"row": row, "reason": "hostname already exists"})
                continue
            if ip and ip in existing_ips:
                skipped.append({"row": row, "reason": "IP already exists"})
                continue
            devs.append(row)
            existing_hostnames.add(hostname.lower())
            existing_ips.add(ip)
            added += 1
        self._repo.save(devs)
        return True, {"ok": True, "added": added, "skipped": skipped}, 200
