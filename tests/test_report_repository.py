"""
TDD tests for ``backend.repositories.report_repository.ReportRepository``.

The repository owns the gzipped pre/post check reports and the
JSON index file under ``<instance_path>/reports/``.

Contract
--------
* ``ReportRepository(reports_dir)`` — explicit directory injection.
* ``repo.save(run_id, name, created_at, devices, device_results, ...)``
  writes ``<reports_dir>/<safe-id>.json.gz`` and updates the index.
* ``repo.load(run_id)`` returns the full payload dict or None.
* ``repo.delete(run_id)`` removes both file and index entry, returning
  True/False.
* ``repo.list()`` returns the index list (newest first), capped at 200.
* ``run_id`` is sanitised — slashes/backslashes become underscores; an
  empty id falls back to ``"default"``.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture()
def repo(tmp_path):
    from backend.repositories.report_repository import ReportRepository

    return ReportRepository(reports_dir=str(tmp_path / "reports"))


def test_save_then_load_round_trip(repo):
    repo.save(
        run_id="run-1",
        name="my report",
        created_at="2026-01-01T00:00:00Z",
        devices=[{"hostname": "leaf-1"}],
        device_results=[{"hostname": "leaf-1", "ok": True}],
    )
    payload = repo.load("run-1")
    assert payload["run_id"] == "run-1"
    assert payload["name"] == "my report"
    assert payload["devices"][0]["hostname"] == "leaf-1"
    assert payload["device_results"][0]["ok"] is True
    assert payload["post_created_at"] is None
    assert payload["post_device_results"] is None
    assert payload["comparison"] is None


def test_load_returns_none_for_missing(repo):
    assert repo.load("never-existed") is None


def test_save_with_post_data(repo):
    repo.save(
        run_id="run-2",
        name="post run",
        created_at="t1",
        devices=[],
        device_results=[],
        post_created_at="t2",
        post_device_results=[{"x": 1}],
        comparison={"diff": "added"},
    )
    payload = repo.load("run-2")
    assert payload["post_created_at"] == "t2"
    assert payload["post_device_results"] == [{"x": 1}]
    assert payload["comparison"] == {"diff": "added"}


def test_list_returns_newest_first(repo):
    repo.save(run_id="a", name="a", created_at="t-a", devices=[], device_results=[])
    repo.save(run_id="b", name="b", created_at="t-b", devices=[], device_results=[])
    entries = repo.list()
    assert [e["run_id"] for e in entries[:2]] == ["b", "a"]


def test_list_caps_at_200(tmp_path):
    from backend.repositories.report_repository import ReportRepository

    repo = ReportRepository(reports_dir=str(tmp_path / "r"))
    for i in range(220):
        repo.save(run_id=f"r{i}", name="n", created_at="t", devices=[], device_results=[])
    assert len(repo.list()) == 200


def test_delete_removes_file_and_index(repo):
    repo.save(run_id="del", name="x", created_at="t", devices=[], device_results=[])
    assert repo.load("del") is not None
    assert repo.delete("del") is True
    assert repo.load("del") is None
    assert all(e["run_id"] != "del" for e in repo.list())


def test_delete_returns_false_when_missing(repo):
    # Deleting a non-existent run should simply report False (no error).
    assert repo.delete("nope") is False


def test_run_id_is_sanitised(repo):
    repo.save(run_id="bad/id\\name", name="n", created_at="t", devices=[], device_results=[])
    payload = repo.load("bad/id\\name")
    assert payload is not None
    assert payload["run_id"] == "bad/id\\name"
    files = os.listdir(repo.reports_dir)
    assert "bad_id_name.json.gz" in files


def test_save_overwrites_existing_index_entry(repo):
    repo.save(run_id="x", name="first", created_at="t1", devices=[], device_results=[])
    repo.save(run_id="x", name="second", created_at="t2", devices=[], device_results=[])
    entries = [e for e in repo.list() if e["run_id"] == "x"]
    assert len(entries) == 1
    assert entries[0]["name"] == "second"
