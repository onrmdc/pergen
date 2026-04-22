"""
``TransceiverService`` — orchestrates the per-device transceiver +
status + description + MTU + Cisco-detailed merge.

Phase-9 deliverable. Replaces the 110-line ``api_transceiver`` route
body in ``backend/app.py`` with a focused service object whose
single ``collect_rows()`` entry point is unit-testable in isolation
(no Flask, no real network traffic — just inject a stub
``run_device_commands``).

Inputs
------
``devices`` : list of inventory device dicts (must include ``hostname``,
              ``ip``, ``vendor``, ``role``, ``credential``).

Outputs
-------
``(rows, errors, interface_status_trace)`` tuple where:
* ``rows``   — flat list of one dict per transceiver row, with
               status / flap / errors merged in.
* ``errors`` — list of ``{hostname, error}`` for devices that failed
               or returned no transceiver data.
* ``interface_status_trace`` — debug payload mirroring the legacy
               ``/api/transceiver`` ``interface_status_trace`` field.
"""
from __future__ import annotations

from typing import Any

from backend.runners.runner import run_device_commands
from backend.utils.interface_status import (
    cisco_interface_detailed_trace,
    iface_status_lookup,
    interface_status_trace,
    merge_cisco_detailed_flap,
)
from backend.utils.transceiver_display import (
    transceiver_errors_display,
    transceiver_last_flap_display,
)


class TransceiverService:
    """Per-device transceiver/status orchestration."""

    def __init__(self, secret_key: str, credential_store: Any) -> None:
        self._secret_key = secret_key
        self._creds = credential_store

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #
    def collect_rows(
        self, devices: list[dict]
    ) -> tuple[list[dict], list[dict], list[dict]]:
        """Run the four-stage pipeline for each device and merge results."""
        all_rows: list[dict] = []
        errors: list[dict] = []
        trace: list[dict] = []

        for device in devices:
            hostname = (
                device.get("hostname") or device.get("ip") or "unknown"
            ).strip()
            vendor_l = (device.get("vendor") or "").strip().lower()

            # Stage 1: transceiver inventory
            result = run_device_commands(
                device,
                self._secret_key,
                self._creds,
                command_id_filter="transceiver",
            )
            if result.get("error"):
                errors.append({"hostname": hostname, "error": result["error"]})
                continue
            flat = result.get("parsed_flat") or {}
            transceiver_rows = flat.get("transceiver_rows")

            # Stage 2: interface_status (canonical) + raw runner result for trace.
            #
            # Returning a tuple here (instead of stashing on ``self._last_status_result``)
            # keeps the service reentrant — multiple devices in one ``collect_rows``
            # call cannot shred each other's state, and the service is now safe
            # to cache across requests / threads.
            status_by_interface, status_result = self._collect_status(device)

            # Stage 3: descriptions
            description_by_interface = self._collect_descriptions(device)

            # Stage 4: Cisco-only MTU map
            cisco_mtu_map = self._collect_cisco_mtu_map(device, vendor_l)

            # Stage 5: Cisco-only detailed flap merge
            detailed_result = None
            if "cisco" in vendor_l and not status_result.get("error"):
                detailed_result = run_device_commands(
                    device,
                    self._secret_key,
                    self._creds,
                    command_id_exact="cisco_nxos_show_interface",
                )
                if not detailed_result.get("error"):
                    dflat = detailed_result.get("parsed_flat") or {}
                    flap_rows = dflat.get("interface_flapped_rows") or []
                    merge_cisco_detailed_flap(status_by_interface, flap_rows)

            trace.append(
                {
                    "hostname": hostname,
                    "ip": (device.get("ip") or "").strip(),
                    "vendor": (device.get("vendor") or "").strip(),
                    "status_run_error": status_result.get("error"),
                    "entries": interface_status_trace(status_result),
                    "cisco_show_interface_detailed": (
                        cisco_interface_detailed_trace(detailed_result)
                        if detailed_result is not None
                        else []
                    ),
                }
            )

            if isinstance(transceiver_rows, list):
                for row in transceiver_rows:
                    if not isinstance(row, dict):
                        continue
                    all_rows.append(
                        self._build_row(
                            row=row,
                            device=device,
                            result=result,
                            hostname=hostname,
                            status_by_interface=status_by_interface,
                            description_by_interface=description_by_interface,
                            cisco_mtu_map=cisco_mtu_map,
                        )
                    )

            if not transceiver_rows and not result.get("error"):
                errors.append(
                    {
                        "hostname": hostname,
                        "error": "no transceiver data (unsupported or no optics)",
                    }
                )

        return all_rows, errors, trace

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #
    def _collect_status(self, device: dict) -> tuple[dict, dict]:
        """Return ``(status_by_interface, raw_runner_result)``.

        The raw runner result is needed by ``collect_rows`` for the
        Cisco-detailed trace and the per-device trace payload.
        """
        status_result = run_device_commands(
            device,
            self._secret_key,
            self._creds,
            command_id_filter="interface_status",
        )
        out: dict = {}
        if status_result.get("error"):
            return out, status_result
        status_flat = status_result.get("parsed_flat") or {}
        for s in status_flat.get("interface_status_rows") or []:
            if isinstance(s, dict) and s.get("interface"):
                out[str(s["interface"]).strip()] = {
                    "state": s.get("state") or "-",
                    "last_link_flapped": s.get("last_link_flapped") or "-",
                    "last_status_change_epoch": s.get("last_status_change_epoch"),
                    "in_errors": s.get("in_errors") or "-",
                    "crc_count": s.get("crc_count") or "-",
                    "mtu": s.get("mtu") or "-",
                    "flap_count": s.get("flap_count") or "-",
                }
        return out, status_result

    def _collect_descriptions(self, device: dict) -> dict:
        desc_result = run_device_commands(
            device,
            self._secret_key,
            self._creds,
            command_id_filter="interface_description",
        )
        if desc_result.get("error"):
            return {}
        desc_flat = desc_result.get("parsed_flat") or {}
        out = desc_flat.get("interface_descriptions") or {}
        return out if isinstance(out, dict) else {}

    def _collect_cisco_mtu_map(self, device: dict, vendor_l: str) -> dict:
        if "cisco" not in vendor_l:
            return {}
        mtu_result = run_device_commands(
            device,
            self._secret_key,
            self._creds,
            command_id_filter="interface_mtu",
        )
        if mtu_result.get("error"):
            return {}
        mtu_flat = mtu_result.get("parsed_flat") or {}
        out = mtu_flat.get("interface_mtu_map") or {}
        return out if isinstance(out, dict) else {}

    @staticmethod
    def _build_row(
        *,
        row: dict,
        device: dict,
        result: dict,
        hostname: str,
        status_by_interface: dict,
        description_by_interface: dict,
        cisco_mtu_map: dict,
    ) -> dict:
        iface = str(row.get("interface") or "").strip()
        st = iface_status_lookup(status_by_interface, iface) or {}
        if not isinstance(st, dict):
            st = {}
        desc = (
            description_by_interface.get(iface)
            if isinstance(description_by_interface, dict)
            else ""
        )
        mtu_val = cisco_mtu_map.get(iface) if cisco_mtu_map else None
        if mtu_val is None and cisco_mtu_map:
            mtu_val = cisco_mtu_map.get(iface.replace(" ", ""))
        if mtu_val is None:
            mtu_val = st.get("mtu") or "-"
        return {
            "hostname": result.get("hostname") or hostname,
            "ip": result.get("ip") or device.get("ip") or "",
            "device_role": (device.get("role") or "").strip(),
            "vendor": (device.get("vendor") or "").strip(),
            "interface": iface,
            "description": desc if desc else "-",
            "mtu": mtu_val,
            "serial": row.get("serial") or "",
            "type": row.get("type") or "",
            "manufacturer": row.get("manufacturer") or "",
            "temp": row.get("temp") or "",
            "tx_power": row.get("tx_power") or "",
            "rx_power": row.get("rx_power") or "",
            "status": st.get("state") or "-",
            "last_flap": transceiver_last_flap_display(st),
            "in_errors": st.get("in_errors") or "-",
            "crc_count": st.get("crc_count") or "-",
            "errors": transceiver_errors_display(st),
            "flap_count": st.get("flap_count") or "-",
        }
