"""
Baseline tests for ``backend.inventory.loader``.

The inventory loader normalises CSV columns (site casing, role aliases) and
applies an IP-based sort.  These tests pin those rules so the upcoming
``InventoryRepository`` class refactor cannot drift.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.golden


def _write_csv(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "inv.csv"
    p.write_text(body, encoding="utf-8")
    return p


HEADER = "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"


def test_load_inventory_normalises_site_to_title_case(tmp_path):
    from backend.inventory.loader import load_inventory

    csv = _write_csv(
        tmp_path,
        HEADER + "leaf-01,10.0.0.1,FAB1,mars,Hall-1,Arista,EOS,Leaf,,c\n",
    )
    rows = load_inventory(str(csv))
    assert rows[0]["site"] == "Mars"


def test_load_inventory_normalises_truncated_role_alias(tmp_path):
    from backend.inventory.loader import load_inventory

    csv = _write_csv(
        tmp_path,
        HEADER + "bl-01,10.0.0.5,FAB1,Mars,Hall-1,Arista,EOS,Border-,,c\n",
    )
    rows = load_inventory(str(csv))
    assert rows[0]["role"] == "Border-Leaf"


def test_load_inventory_sorts_devices_by_ip_octet(tmp_path):
    from backend.inventory.loader import load_inventory

    csv = _write_csv(
        tmp_path,
        HEADER
        + "z,10.0.0.10,FAB1,Mars,Hall-1,Arista,EOS,Leaf,,c\n"
        + "a,10.0.0.2,FAB1,Mars,Hall-1,Arista,EOS,Leaf,,c\n"
        + "m,10.0.0.5,FAB1,Mars,Hall-1,Arista,EOS,Leaf,,c\n",
    )
    rows = load_inventory(str(csv))
    assert [r["hostname"] for r in rows] == ["a", "m", "z"]


def test_load_inventory_empty_path_returns_empty_list(tmp_path):
    from backend.inventory.loader import load_inventory

    assert load_inventory(str(tmp_path / "missing.csv")) == []


def test_load_inventory_skips_rows_without_hostname(tmp_path):
    from backend.inventory.loader import load_inventory

    csv = _write_csv(
        tmp_path,
        HEADER
        + ",10.0.0.99,FAB1,Mars,Hall-1,Arista,EOS,Leaf,,c\n"
        + "ok,10.0.0.1,FAB1,Mars,Hall-1,Arista,EOS,Leaf,,c\n",
    )
    rows = load_inventory(str(csv))
    assert len(rows) == 1
    assert rows[0]["hostname"] == "ok"


def test_get_devices_filters_by_role_and_hall(tmp_path):
    from backend.inventory.loader import get_devices, load_inventory

    csv = _write_csv(
        tmp_path,
        HEADER
        + "l1,10.0.0.1,FAB1,Mars,Hall-1,Arista,EOS,Leaf,,c\n"
        + "l2,10.0.0.2,FAB1,Mars,Hall-2,Arista,EOS,Leaf,,c\n"
        + "s1,10.0.0.3,FAB1,Mars,Hall-1,Arista,EOS,Spine,,c\n",
    )
    devs = load_inventory(str(csv))
    assert [d["hostname"] for d in get_devices("FAB1", "Mars", devices=devs)] == ["l1", "l2", "s1"]
    assert [
        d["hostname"]
        for d in get_devices("FAB1", "Mars", role="Leaf", hall="Hall-1", devices=devs)
    ] == ["l1"]


def test_get_devices_by_tag_case_insensitive(tmp_path):
    from backend.inventory.loader import get_devices_by_tag, load_inventory

    csv = _write_csv(
        tmp_path,
        HEADER
        + "l1,10.0.0.1,FAB1,Mars,Hall-1,Arista,EOS,Leaf,LEAF-search,c\n"
        + "l2,10.0.0.2,FAB1,Mars,Hall-1,Arista,EOS,Leaf,other,c\n",
    )
    devs = load_inventory(str(csv))
    matched = get_devices_by_tag("leaf-search", devices=devs)
    assert [d["hostname"] for d in matched] == ["l1"]


def test_get_fabrics_returns_unique_sorted(tmp_path):
    from backend.inventory.loader import get_fabrics, load_inventory

    csv = _write_csv(
        tmp_path,
        HEADER
        + "a,10.0.0.1,FAB2,Mars,Hall-1,Arista,EOS,Leaf,,c\n"
        + "b,10.0.0.2,FAB1,Mars,Hall-1,Arista,EOS,Leaf,,c\n"
        + "c,10.0.0.3,FAB1,Mars,Hall-1,Arista,EOS,Leaf,,c\n",
    )
    devs = load_inventory(str(csv))
    assert get_fabrics(devs) == ["FAB1", "FAB2"]
