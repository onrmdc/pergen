"""
Leaf-search orchestration: parallel fan-out and per-device entrypoint.

Both public entrypoints look up ``_query_one_leaf_search`` and
``_complete_find_leaf_from_hit`` through the ``backend.find_leaf`` package
namespace at call time, so that test patches like
``unittest.mock.patch("backend.find_leaf._query_one_leaf_search", ...)`` reach
the orchestration code in this module unchanged.

Wave-6 (audit M-09): the parallel fan-out now calls
``executor.shutdown(wait=False, cancel_futures=True)`` immediately on
first hit. Pending un-started queries are cancelled, holding open
fewer SSH/eAPI sessions and returning to the operator faster. Note
that already-running queries continue to run (Python contract limit),
but the operator no longer waits for them.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from backend.find_leaf.ip_helpers import _is_valid_ip
from backend.inventory.loader import get_devices_by_tag, load_inventory

__all__ = ["find_leaf", "find_leaf_check_device"]


def find_leaf_check_device(
    search_ip: str,
    device_identifier: str,
    secret_key: str,
    cred_store_module: Any,
    inventory_path: str | None = None,
) -> dict[str, Any]:
    """
    Check a single leaf-search device for the IP. ``device_identifier`` is hostname or IP.
    Returns ``{ "found": bool, "checked_hostname": str, ... }`` with full find_leaf result when found.
    """
    # Late binding so test patches on the shim land here.
    from backend import find_leaf as _shim

    search_ip = (search_ip or "").strip()
    device_identifier = (device_identifier or "").strip()
    out = {
        "found": False,
        "error": None,
        "checked_hostname": "",
        "leaf_hostname": "",
        "leaf_ip": "",
        "interface": "",
        "vendor": "",
        "fabric": "",
        "hall": "",
        "site": "",
        "remote_vtep_addr": "",
        "physical_iod": "",
    }
    if not _is_valid_ip(search_ip):
        out["error"] = "only IP format is allowed"
        return out
    if not device_identifier:
        out["error"] = "device_identifier (hostname or IP) is required"
        return out

    devices = load_inventory(inventory_path)
    leaf_search = get_devices_by_tag("leaf-search", devices)
    dev = None
    for d in leaf_search:
        h = (d.get("hostname") or "").strip()
        i = (d.get("ip") or "").strip()
        if h == device_identifier or i == device_identifier:
            dev = d
            break
    if not dev:
        out["error"] = f"device '{device_identifier}' not found in leaf-search"
        return out
    out["checked_hostname"] = (dev.get("hostname") or dev.get("ip") or "").strip()

    hit = _shim._query_one_leaf_search(dev, search_ip, secret_key, cred_store_module)
    if hit is None:
        return out
    completed = _shim._complete_find_leaf_from_hit(
        hit, search_ip, devices, secret_key, cred_store_module
    )
    completed["checked_hostname"] = out["checked_hostname"]
    return completed


def find_leaf(
    search_ip: str,
    secret_key: str,
    cred_store_module,
    inventory_path: str | None = None,
) -> dict[str, Any]:
    """
    Search for the leaf and interface/port for the given IP.

    - Only IP format is accepted.
    - First runs on devices with tag ``leaf-search`` (BGP EVPN for Arista, ARP suppression for Cisco).
    - For Arista: parses ``nextHop`` from BGP EVPN mac-ip, then finds that switch in inventory and runs ARP to get interface.
    - For Cisco: parses ARP suppression cache for the IP; the device where it is found is the leaf.

    Returns::

        { "found": bool, "error": str | None, "leaf_hostname": str, "leaf_ip": str, "interface": str,
          "vendor": str, "remote_vtep_addr": str (Cisco only), "physical_iod": str (Cisco only) }
    """
    # Late binding so test patches on the shim land here.
    from backend import find_leaf as _shim

    search_ip = (search_ip or "").strip()
    out = {
        "found": False,
        "error": None,
        "leaf_hostname": "",
        "leaf_ip": "",
        "interface": "",
        "vendor": "",
        "fabric": "",
        "hall": "",
        "site": "",
        "remote_vtep_addr": "",
        "physical_iod": "",
        "checked_devices": [],
    }
    if not _is_valid_ip(search_ip):
        out["error"] = "only IP format is allowed"
        return out

    devices = load_inventory(inventory_path)
    leaf_search = get_devices_by_tag("leaf-search", devices)
    if not leaf_search:
        out["error"] = "no devices with tag 'leaf-search' in inventory"
        return out
    out["checked_devices"] = [
        {"hostname": (d.get("hostname") or "").strip(), "ip": (d.get("ip") or "").strip()}
        for d in leaf_search
    ]

    # Query all leaf-search devices in parallel; use first hit.
    # Wave-6 (audit M-09): cancel pending un-started futures on first hit
    # so the operator does not wait for slow sibling queries to drain.
    hit = None
    max_workers = min(len(leaf_search), 32)
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        futures = {
            executor.submit(
                _shim._query_one_leaf_search, dev, search_ip, secret_key, cred_store_module
            ): dev
            for dev in leaf_search
        }
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    hit = result
                    break
            except Exception:  # noqa: BLE001 — best-effort per-device error
                pass
    finally:
        # ``cancel_futures=True`` (Python ≥ 3.9) drops pending un-started
        # tasks from the queue. Already-running tasks continue but the
        # operator's call returns immediately. ``wait=False`` makes the
        # finally non-blocking.
        executor.shutdown(wait=False, cancel_futures=True)

    if hit is None:
        out["error"] = "IP not found on any leaf-search device"
        return out

    completed = _shim._complete_find_leaf_from_hit(
        hit, search_ip, devices, secret_key, cred_store_module
    )
    out.update(completed)
    return out
