"""
Shared pytest fixtures.

Goals
-----
* Make ``backend`` importable from any test file (the repo is not pip-installed).
* Provide a hermetic instance dir (no real ``backend/instance/`` writes during tests).
* Provide a stable ``SECRET_KEY`` so credential-store tests do not depend on env state.
* Provide a curated mock inventory so route tests do not depend on the operator's CSV.
* Expose a Flask test client without spinning up a real server.

These fixtures are deliberately kept small and side-effect free so individual
unit tests can opt into only what they need (no implicit network or filesystem
state).  Phase 2+ replaces the global ``backend.app`` import with the proper
App Factory; until then we work with the existing module-level ``app`` object.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Make the project importable as ``backend.*`` regardless of cwd.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# --------------------------------------------------------------------------- #
# Environment isolation                                                       #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session", autouse=True)
def _stable_secret_key() -> Iterator[None]:
    """Pin SECRET_KEY for the whole test session.

    Several modules read ``os.environ["SECRET_KEY"]`` at import time.  Pinning
    a deterministic, non-default value at session start makes credential
    encryption / decryption reproducible across processes.
    """
    previous = os.environ.get("SECRET_KEY")
    os.environ["SECRET_KEY"] = "pergen-test-secret-key-deterministic"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SECRET_KEY", None)
        else:
            os.environ["SECRET_KEY"] = previous


@pytest.fixture()
def isolated_instance_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``PERGEN_INSTANCE_DIR`` to a per-test temporary directory.

    Most credential / report / notepad code paths fall back to
    ``backend/instance/`` when the env var is missing.  Forcing the variable
    keeps test runs fully isolated and parallel-safe.
    """
    instance = tmp_path / "instance"
    instance.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(instance))
    return instance


@pytest.fixture()
def mock_inventory_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a small inventory CSV and point ``PERGEN_INVENTORY_PATH`` at it.

    Two leaf devices, one Arista + one Cisco, in a single fabric/site/hall.
    Sufficient for fabric/site/role/hall hierarchy tests without coupling to
    the operator's real CSV.
    """
    csv_path = tmp_path / "inventory.csv"
    csv_path.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "leaf-01,10.0.0.1,FAB1,Mars,Hall-1,Arista,EOS,Leaf,leaf-search,test-cred\n"
        "leaf-02,10.0.0.2,FAB1,Mars,Hall-1,Cisco,NX-OS,Leaf,,test-cred\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PERGEN_INVENTORY_PATH", str(csv_path))
    return csv_path


# --------------------------------------------------------------------------- #
# Flask client                                                                #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def flask_app(isolated_instance_dir: Path, mock_inventory_csv: Path):
    """Return a fresh ``create_app("testing")`` Flask instance.

    Phase 9 switched the fixture from a bare ``backend.app:app`` import
    to the proper App Factory so per-domain Blueprints (registered by
    ``_register_blueprints``) are mounted exactly like in production.

    Module eviction below ensures ``SECRET_KEY``, ``PERGEN_INVENTORY_PATH``
    and ``PERGEN_INSTANCE_DIR`` are honoured: the legacy ``backend.app``
    module reads ``settings.INVENTORY_PATH`` / ``settings.INSTANCE_DIR``
    at import time, so a fresh import is required when the env vars
    change between tests.
    """
    import importlib

    for mod in [
        "backend.app",
        "backend.app_factory",
        "backend.blueprints",
        "backend.blueprints.bgp_bp",
        "backend.blueprints.commands_bp",
        "backend.blueprints.credentials_bp",
        "backend.blueprints.device_commands_bp",
        "backend.blueprints.health_bp",
        "backend.blueprints.inventory_bp",
        "backend.blueprints.network_lookup_bp",
        "backend.blueprints.network_ops_bp",
        "backend.blueprints.notepad_bp",
        "backend.blueprints.reports_bp",
        "backend.blueprints.runs_bp",
        "backend.blueprints.transceiver_bp",
        # Phase 3: ``backend.config`` itself caches a reference to
        # ``settings`` at package-init time, so popping only the
        # ``settings`` submodule leaves ``backend.config.settings``
        # bound to the stale module. Pop the package too so the
        # re-import inside ``_register_services`` resolves the fresh
        # env-var-driven ``INVENTORY_PATH`` / ``INSTANCE_DIR``.
        "backend.config",
        "backend.config.settings",
        "backend.config.commands_loader",
        "backend.config.app_config",
        "backend.inventory.loader",
        "backend.credential_store",
    ]:
        sys.modules.pop(mod, None)

    factory_mod = importlib.import_module("backend.app_factory")
    app = factory_mod.create_app("testing")
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    return app


@pytest.fixture()
def client(flask_app):
    """Flask test client, ready for ``client.get(...)`` / ``.post(...)``."""
    return flask_app.test_client()


# --------------------------------------------------------------------------- #
# Convenience                                                                 #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def fixture_dir() -> Path:
    """Path to the static fixtures directory (``tests/fixtures``)."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture()
def make_tempdir() -> Iterator[Path]:
    """Yield a fresh temp directory and unconditionally clean it afterwards."""
    path = Path(tempfile.mkdtemp(prefix="pergen-test-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
