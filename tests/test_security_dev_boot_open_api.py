"""H-05 — Refuse to boot with an open API in non-production.

When neither `PERGEN_API_TOKEN` nor `PERGEN_API_TOKENS` is set, the gate
serves traffic openly. The current `run.sh` boots without these, leaving
every write route accessible to any process on the host.

Audit reference: ``docs/security/audit_2026-04-22.md`` §3.1 H-05.

Desired contract: in dev/test, refuse to boot open unless an explicit
`PERGEN_DEV_OPEN_API=1` env var is set. Production already fail-closes
(see `app_factory.py:222-235`).

XFAIL until the boot guard lands.
"""

from __future__ import annotations

import importlib
import sys

import pytest

pytestmark = [pytest.mark.security]


@pytest.mark.xfail(
    reason="audit H-05 — dev/test does not refuse to boot without explicit open flag",
    strict=True,
)
def test_dev_boot_without_token_and_without_open_flag_refuses(monkeypatch) -> None:
    """create_app('development') must raise without explicit override."""
    monkeypatch.delenv("PERGEN_API_TOKEN", raising=False)
    monkeypatch.delenv("PERGEN_API_TOKENS", raising=False)
    monkeypatch.delenv("PERGEN_DEV_OPEN_API", raising=False)

    # Force a fresh import so the module-level config is re-read.
    for mod in list(sys.modules):
        if mod.startswith("backend.app_factory") or mod == "backend.config":
            sys.modules.pop(mod, None)

    factory = importlib.import_module("backend.app_factory")
    with pytest.raises(RuntimeError, match="open API"):
        factory.create_app("development")


def test_dev_boot_with_explicit_open_flag_succeeds(monkeypatch) -> None:
    """The override path stays open for legitimate local dev work."""
    monkeypatch.delenv("PERGEN_API_TOKEN", raising=False)
    monkeypatch.delenv("PERGEN_API_TOKENS", raising=False)
    monkeypatch.setenv("PERGEN_DEV_OPEN_API", "1")

    for mod in list(sys.modules):
        if mod.startswith("backend.app_factory") or mod == "backend.config":
            sys.modules.pop(mod, None)

    factory = importlib.import_module("backend.app_factory")
    # Today this works (no boot guard at all). After H-05 lands it should
    # still work because the explicit flag is set.
    app = factory.create_app("development")
    assert app is not None


def test_dev_boot_with_token_set_succeeds(monkeypatch) -> None:
    """When a token is configured, boot must succeed (no open posture risk)."""
    monkeypatch.setenv("PERGEN_API_TOKEN", "x" * 32)
    monkeypatch.delenv("PERGEN_API_TOKENS", raising=False)
    monkeypatch.delenv("PERGEN_DEV_OPEN_API", raising=False)

    for mod in list(sys.modules):
        if mod.startswith("backend.app_factory") or mod == "backend.config":
            sys.modules.pop(mod, None)

    factory = importlib.import_module("backend.app_factory")
    app = factory.create_app("development")
    assert app is not None
