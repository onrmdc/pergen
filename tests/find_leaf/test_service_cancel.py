"""Wave-6 Phase B — find-leaf parallel-cancel (audit M-09).

The original ``find_leaf`` implementation submitted N device queries
in parallel, broke out of the ``as_completed`` loop on first hit,
but did NOT cancel the still-pending futures. Slow Cisco/Arista API
calls would continue to drain in the background, holding open SSH
sessions and burning thread time.

This wave-6 fix calls ``executor.shutdown(wait=False, cancel_futures=True)``
the moment a hit lands, so pending un-started queries are cancelled
and the function returns promptly.

The contract pinned here:

1. The function returns within ~1 second of the first hit, even when
   sibling queries are slow (5+ second sleeps in this test).
2. Pending un-started futures are cancelled — the slow ``_query_one_leaf_search``
   that never gets to run is observably absent from the side-effect counter.

Note on the test design
-----------------------
``cancel_futures=True`` only cancels futures that have NOT YET STARTED.
Already-running queries continue to run — that's a Python contract
limit, not a bug. The test sleeps long enough that with ``max_workers=2``
on a 4-device fan-out, at least 2 queries are guaranteed to be queued
and therefore cancellable.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit]


def test_find_leaf_cancels_pending_queries_on_first_hit(monkeypatch, tmp_path) -> None:
    """First hit returns fast; queued (un-started) queries are cancelled."""
    # Build a 4-device inventory so a max_workers=2 executor queues 2.
    csv = tmp_path / "inv.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "leaf-1,10.0.0.1,F1,S1,H1,Arista,EOS,Leaf,leaf-search,c1\n"
        "leaf-2,10.0.0.2,F1,S1,H1,Cisco,NX-OS,Leaf,leaf-search,c1\n"
        "leaf-3,10.0.0.3,F1,S1,H1,Cisco,NX-OS,Leaf,leaf-search,c1\n"
        "leaf-4,10.0.0.4,F1,S1,H1,Cisco,NX-OS,Leaf,leaf-search,c1\n",
        encoding="utf-8",
    )

    started_hosts: list[str] = []
    counter_lock = threading.Lock()

    def fake_query(dev, search_ip, secret_key, cred_store_module):
        with counter_lock:
            started_hosts.append(dev["hostname"])
        if dev["hostname"] == "leaf-1":
            # Fast-path hit
            return {"vendor": "arista", "spine_ip": dev["ip"], "spine_hostname": dev["hostname"],
                    "next_hop": "10.0.0.99", "username": "u", "password": "p", "dev": dev}
        # Slow query that should be cancelled before it starts
        time.sleep(5)
        return None

    def fake_complete(hit, search_ip, devices, secret_key, cred_store_module):
        return {
            "found": True, "leaf_hostname": "leaf-99", "leaf_ip": "10.0.0.99",
            "fabric": "F1", "site": "S1", "hall": "H1", "interface": "Ethernet1/1",
            "vendor": "arista", "remote_vtep_addr": "", "physical_iod": "",
        }

    # Force max_workers=2 so 2 of 4 queries are queued and cancellable.
    with patch(
        "backend.find_leaf.service.ThreadPoolExecutor",
        side_effect=lambda max_workers=None: __import__("concurrent.futures").futures.ThreadPoolExecutor(max_workers=2),
    ), patch("backend.find_leaf._query_one_leaf_search", side_effect=fake_query), patch(
        "backend.find_leaf._complete_find_leaf_from_hit", side_effect=fake_complete
    ):
        from backend.find_leaf import find_leaf

        start = time.perf_counter()
        out = find_leaf(
            "10.0.0.99",
            secret_key="x",
            cred_store_module=None,
            inventory_path=str(csv),
        )
        elapsed = time.perf_counter() - start

    # Found the leaf via the fast-path hit on leaf-1.
    assert out["found"] is True
    assert out["leaf_hostname"] == "leaf-99"

    # Wave-6 contract: returned promptly, far less than the 5-second slow path.
    assert elapsed < 2.0, (
        f"find_leaf took {elapsed:.2f}s after first hit — pending futures "
        f"were not cancelled (audit M-09). Started hosts: {started_hosts}"
    )

    # Wave-6 contract: at least 1 query was cancelled before starting.
    # With max_workers=2 and 4 devices, exactly 2 should have started.
    assert len(started_hosts) < 4, (
        f"all {len(started_hosts)}/4 queries started — cancel_futures=True "
        f"should have prevented at least one. Started: {started_hosts}"
    )
