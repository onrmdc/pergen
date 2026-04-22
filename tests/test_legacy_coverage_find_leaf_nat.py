"""
Coverage push for ``backend/find_leaf.py`` and ``backend/nat_lookup.py``.

Both modules orchestrate device runs; we mock at the runner / inventory
boundary so the tests are deterministic and fast.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest as _pytest_for_marker  # noqa: F401

pytestmark = [_pytest_for_marker.mark.integration]


# --------------------------------------------------------------------------- #
# find_leaf.find_leaf — entry-point happy + sad paths                          #
# --------------------------------------------------------------------------- #


def test_find_leaf_rejects_invalid_ip(tmp_path):
    """Non-dotted-quad must be rejected up front."""
    from backend.find_leaf import find_leaf

    out = find_leaf("not-an-ip", "secret", MagicMock())
    assert out["found"] is False
    assert "only IP" in out["error"] or "ip" in out["error"].lower()


def test_find_leaf_returns_envelope_when_no_leaf_search_devices(tmp_path):
    """Empty inventory → returns envelope with checked_devices=[]."""
    from backend.find_leaf import find_leaf

    csv = tmp_path / "empty.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n",
        encoding="utf-8",
    )
    out = find_leaf("10.0.0.99", "secret", MagicMock(), inventory_path=str(csv))
    assert out["found"] is False


def test_find_leaf_iterates_inventory_with_no_match(tmp_path):
    """Inventory has leaf-search devices but they all return None."""
    from backend.find_leaf import find_leaf

    csv = tmp_path / "inv.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "leaf-A,10.0.0.10,F1,Mars,Hall-1,Arista,EOS,Leaf,leaf-search,c1\n"
        "leaf-B,10.0.0.11,F1,Mars,Hall-1,Cisco,NX-OS,Leaf,leaf-search,c1\n",
        encoding="utf-8",
    )
    with patch("backend.find_leaf._query_one_leaf_search", return_value=None):
        out = find_leaf("10.0.0.99", "secret", MagicMock(), inventory_path=str(csv))
    assert out["found"] is False


def test_find_leaf_returns_match_when_hit_completes(tmp_path):
    """Happy path: a leaf-search device returns a hit, completion enriches it."""
    from backend.find_leaf import find_leaf

    csv = tmp_path / "inv.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "leaf-A,10.0.0.10,F1,Mars,Hall-1,Arista,EOS,Leaf,leaf-search,c1\n",
        encoding="utf-8",
    )
    hit = {
        "leaf_hostname": "leaf-A",
        "leaf_ip": "10.0.0.10",
        "interface": "Ethernet1/1",
        "vendor": "Arista",
        "remote_vtep_addr": "",
    }
    completed = {
        **hit,
        "found": True,
        "fabric": "F1",
        "hall": "Hall-1",
        "site": "Mars",
        "physical_iod": "Ethernet1/1",
        "checked_devices": [{"hostname": "leaf-A"}],
    }
    with patch("backend.find_leaf._query_one_leaf_search", return_value=hit), patch(
        "backend.find_leaf._complete_find_leaf_from_hit", return_value=completed
    ):
        out = find_leaf("10.0.0.99", "secret", MagicMock(), inventory_path=str(csv))
    assert out["found"] is True
    assert out["leaf_hostname"] == "leaf-A"


# --------------------------------------------------------------------------- #
# find_leaf.find_leaf_check_device                                             #
# --------------------------------------------------------------------------- #


def test_find_leaf_check_device_rejects_invalid_ip(tmp_path):
    from backend.find_leaf import find_leaf_check_device

    out = find_leaf_check_device(
        "garbage", "leaf-A", "secret", MagicMock()
    )
    assert out["found"] is False
    assert "ip" in (out.get("error") or "").lower()


def test_find_leaf_check_device_requires_identifier(tmp_path):
    from backend.find_leaf import find_leaf_check_device

    out = find_leaf_check_device("10.0.0.99", "", "secret", MagicMock())
    assert out["found"] is False
    assert out["error"]


def test_find_leaf_check_device_404_when_not_in_leaf_search(tmp_path):
    from backend.find_leaf import find_leaf_check_device

    csv = tmp_path / "inv.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "leaf-A,10.0.0.10,F1,Mars,Hall-1,Arista,EOS,Leaf,leaf-search,c1\n",
        encoding="utf-8",
    )
    out = find_leaf_check_device(
        "10.0.0.99", "no-such", "secret", MagicMock(), inventory_path=str(csv)
    )
    assert out["found"] is False
    assert "not found" in out["error"]


def test_find_leaf_check_device_no_hit(tmp_path):
    from backend.find_leaf import find_leaf_check_device

    csv = tmp_path / "inv.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "leaf-A,10.0.0.10,F1,Mars,Hall-1,Arista,EOS,Leaf,leaf-search,c1\n",
        encoding="utf-8",
    )
    with patch("backend.find_leaf._query_one_leaf_search", return_value=None):
        out = find_leaf_check_device(
            "10.0.0.99", "leaf-A", "secret", MagicMock(), inventory_path=str(csv)
        )
    assert out["found"] is False
    assert out["checked_hostname"] == "leaf-A"


def test_find_leaf_check_device_hit_succeeds(tmp_path):
    from backend.find_leaf import find_leaf_check_device

    csv = tmp_path / "inv.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "leaf-A,10.0.0.10,F1,Mars,Hall-1,Arista,EOS,Leaf,leaf-search,c1\n",
        encoding="utf-8",
    )
    hit = {"leaf_hostname": "leaf-A", "interface": "Eth1/1"}
    completed = {**hit, "found": True, "fabric": "F1"}
    with patch("backend.find_leaf._query_one_leaf_search", return_value=hit), patch(
        "backend.find_leaf._complete_find_leaf_from_hit", return_value=completed
    ):
        out = find_leaf_check_device(
            "10.0.0.99", "leaf-A", "secret", MagicMock(), inventory_path=str(csv)
        )
    assert out["found"] is True
    assert out["checked_hostname"] == "leaf-A"


def test_find_leaf_check_device_by_ip_identifier(tmp_path):
    """Identifier may be the device IP, not just hostname."""
    from backend.find_leaf import find_leaf_check_device

    csv = tmp_path / "inv.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "leaf-A,10.0.0.10,F1,Mars,Hall-1,Arista,EOS,Leaf,leaf-search,c1\n",
        encoding="utf-8",
    )
    with patch("backend.find_leaf._query_one_leaf_search", return_value=None):
        out = find_leaf_check_device(
            "10.0.0.99", "10.0.0.10", "secret", MagicMock(), inventory_path=str(csv)
        )
    # Found the device by IP, queried it, no match.
    assert out["found"] is False
    assert out["checked_hostname"] == "leaf-A"


# --------------------------------------------------------------------------- #
# nat_lookup.nat_lookup                                                        #
# --------------------------------------------------------------------------- #


def test_nat_lookup_no_firewalls_in_fabric(tmp_path):
    from backend.nat_lookup import nat_lookup

    csv = tmp_path / "inv.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "leaf-A,10.0.0.10,F1,Mars,Hall-1,Arista,EOS,Leaf,leaf-search,c1\n",
        encoding="utf-8",
    )
    out = nat_lookup(
        "10.0.0.99",
        "8.8.8.8",
        "secret",
        MagicMock(),
        inventory_path=str(csv),
        fabric="F1",
        site="Mars",
    )
    assert out["ok"] is False or "firewall" in (out.get("error") or "").lower()


def test_nat_lookup_with_no_leaf_resolution(tmp_path):
    """Without fabric/site (no leaf info), function returns 'not found' envelope."""
    from backend.nat_lookup import nat_lookup

    csv = tmp_path / "inv.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n",
        encoding="utf-8",
    )
    with patch("backend.nat_lookup.find_leaf_module.find_leaf", return_value={"found": False}):
        out = nat_lookup(
            "10.0.0.99", "8.8.8.8", "secret", MagicMock(), inventory_path=str(csv)
        )
    assert out["ok"] is False


def test_nat_lookup_uses_supplied_leaf_checked_devices(tmp_path):
    """When caller passes leaf_checked_devices, find_leaf is skipped."""
    from backend.nat_lookup import nat_lookup

    csv = tmp_path / "inv.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n",
        encoding="utf-8",
    )
    out = nat_lookup(
        "10.0.0.99",
        "8.8.8.8",
        "secret",
        MagicMock(),
        inventory_path=str(csv),
        fabric="F1",
        site="Mars",
        leaf_checked_devices=[{"hostname": "leaf-A"}],
    )
    # No firewalls in fabric F1 → still failure
    assert out["ok"] is False


def test_nat_lookup_with_debug_returns_debug_object(tmp_path):
    from backend.nat_lookup import nat_lookup

    csv = tmp_path / "inv.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n",
        encoding="utf-8",
    )
    out = nat_lookup(
        "10.0.0.99",
        "8.8.8.8",
        "secret",
        MagicMock(),
        inventory_path=str(csv),
        fabric="F1",
        site="Mars",
        debug=True,
    )
    assert "debug" in out
