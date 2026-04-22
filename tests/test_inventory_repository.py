"""
TDD tests for ``backend.repositories.inventory_repository.InventoryRepository``.

The repository is the OOD home for inventory CSV access.  It wraps the
existing pure-function loader (``backend/inventory/loader.py``) behind a
class so services and routes can depend on an injectable interface
rather than module-level globals.

Contract
--------
* ``InventoryRepository(csv_path)`` — explicit path injection.
* ``repo.load()`` returns the same list-of-dicts the legacy loader does
  (sorted by IP, normalized site/role, lowercase keys).
* ``repo.fabrics()`` / ``sites(fabric)`` / ``halls(fabric, site)`` /
  ``roles(fabric, site, hall)`` / ``devices(fabric, site, role, hall)``
  / ``devices_by_tag(tag)`` mirror the legacy helper signatures.
* ``repo.save(devices)`` writes the CSV with the canonical header.
* The repository never caches across calls (each ``load`` reads the
  file fresh) — keeps tests deterministic and matches existing behaviour.
"""
from __future__ import annotations

import csv

import pytest

pytestmark = pytest.mark.unit


_SAMPLE_HEADER = [
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


def _write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_SAMPLE_HEADER)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in _SAMPLE_HEADER})


@pytest.fixture()
def inv_csv(tmp_path):
    p = tmp_path / "inv.csv"
    _write_csv(
        p,
        [
            {
                "hostname": "leaf-2",
                "ip": "10.0.0.2",
                "fabric": "F1",
                "site": "mars",
                "hall": "h1",
                "vendor": "Arista",
                "model": "EOS",
                "role": "Leaf",
                "tag": "prod",
                "credential": "c1",
            },
            {
                "hostname": "leaf-1",
                "ip": "10.0.0.1",
                "fabric": "F1",
                "site": "mars",
                "hall": "h1",
                "vendor": "Arista",
                "model": "EOS",
                "role": "Leaf",
                "tag": "prod",
                "credential": "c1",
            },
            {
                "hostname": "spine-1",
                "ip": "10.0.0.10",
                "fabric": "F1",
                "site": "venus",
                "hall": "h2",
                "vendor": "Arista",
                "model": "EOS",
                "role": "Spine",
                "tag": "core",
                "credential": "c1",
            },
        ],
    )
    return p


@pytest.fixture()
def repo(inv_csv):
    from backend.repositories.inventory_repository import InventoryRepository

    return InventoryRepository(csv_path=str(inv_csv))


def test_load_returns_devices_sorted_by_ip(repo):
    devs = repo.load()
    assert [d["hostname"] for d in devs] == ["leaf-1", "leaf-2", "spine-1"]


def test_load_normalizes_site_to_titlecase(repo):
    devs = repo.load()
    assert {d["site"] for d in devs} == {"Mars", "Venus"}


def test_load_lowercases_keys(repo):
    devs = repo.load()
    for d in devs:
        for key in d:
            assert key == key.lower()


def test_fabrics_returns_unique_sorted(repo):
    assert repo.fabrics() == ["F1"]


def test_sites_filters_by_fabric(repo):
    assert repo.sites("F1") == ["Mars", "Venus"]


def test_halls_filters_by_fabric_and_site(repo):
    assert repo.halls("F1", "Mars") == ["h1"]
    assert repo.halls("F1", "") == ["h1", "h2"]


def test_roles_filters_correctly(repo):
    assert repo.roles("F1", "") == ["Leaf", "Spine"]
    assert repo.roles("F1", "Venus") == ["Spine"]


def test_devices_filters_and_sorts(repo):
    out = repo.devices("F1", "Mars", role="Leaf")
    assert [d["hostname"] for d in out] == ["leaf-1", "leaf-2"]


def test_devices_by_tag_case_insensitive(repo):
    out = repo.devices_by_tag("PROD")
    assert {d["hostname"] for d in out} == {"leaf-1", "leaf-2"}


def test_save_round_trip(tmp_path):
    from backend.repositories.inventory_repository import InventoryRepository

    p = tmp_path / "out.csv"
    repo = InventoryRepository(csv_path=str(p))
    repo.save(
        [
            {
                "hostname": "h1",
                "ip": "10.0.0.5",
                "fabric": "F2",
                "site": "earth",
                "hall": "h3",
                "vendor": "Cisco",
                "model": "NX-OS",
                "role": "Leaf",
                "tag": "lab",
                "credential": "c2",
            }
        ]
    )
    devs = repo.load()
    assert len(devs) == 1
    assert devs[0]["hostname"] == "h1"
    assert devs[0]["site"] == "Earth"


def test_load_returns_empty_for_missing_file(tmp_path):
    from backend.repositories.inventory_repository import InventoryRepository

    repo = InventoryRepository(csv_path=str(tmp_path / "missing.csv"))
    assert repo.load() == []
