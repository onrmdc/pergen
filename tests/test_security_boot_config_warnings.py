"""
Wave-7.2 — boot-time configuration sanity warnings.

Catches operator-foot-gun configurations at startup that would
otherwise produce confusing runtime symptoms (e.g. every API call
returning 401 because both ``PERGEN_API_TOKEN`` AND
``PERGEN_DEV_OPEN_API=1`` are set — the gate enforces the token,
but the operator thought DEV_OPEN_API meant "no auth").

The original confusion was real: the H-05 boot guard reads
``PERGEN_DEV_OPEN_API`` only at create_app() time to decide
"don't refuse to start"; the runtime gate (``_enforce_api_token``)
ignores it entirely and always enforces tokens when any are
configured. Without a startup warning, the operator sees the WARN
banner-equivalent miss (because tokens are set) and an empty UI
with no obvious cause.
"""
from __future__ import annotations

import logging

import pytest

pytestmark = [pytest.mark.security]


def _attach_handler_to_factory(handler: logging.Handler) -> None:
    """Attach a logging handler directly to the ``app.factory`` logger
    so we can capture WARNs that fire DURING ``create_app()``.

    ``LoggingConfig.configure`` strips handlers from the root logger
    when the app is built — by which time pytest's ``caplog`` is
    already too late. Adding the handler directly to the named logger
    sidesteps that whole dance because the factory log call uses
    ``_log = logging.getLogger("app.factory")`` (named loggers
    propagate independently of root handler list).
    """
    factory_log = logging.getLogger("app.factory")
    if handler not in factory_log.handlers:
        factory_log.addHandler(handler)
    factory_log.setLevel(logging.DEBUG)


def _make_app(monkeypatch, *, token: str | None, dev_open: bool):
    """Build a fresh app with the requested env-var combination.

    Uses the same module-eviction pattern as ``tests/conftest.py``'s
    ``flask_app`` fixture — restricted to a small whitelist of modules
    that read env at import-time. We deliberately do NOT touch
    ``backend.security.encryption`` (and other modules) so that
    ``EncryptionError`` and other class identities stay stable across
    test runs (the rest of the suite imports those at collection time
    and breaks if their module identity changes mid-run).
    """
    import sys

    if token is None:
        monkeypatch.delenv("PERGEN_API_TOKEN", raising=False)
    else:
        monkeypatch.setenv("PERGEN_API_TOKEN", token)
    monkeypatch.delenv("PERGEN_API_TOKENS", raising=False)
    if dev_open:
        monkeypatch.setenv("PERGEN_DEV_OPEN_API", "1")
    else:
        monkeypatch.delenv("PERGEN_DEV_OPEN_API", raising=False)

    # Evict only the env-driven config / app_factory chain — NOT shared
    # primitives like backend.security.encryption (those export classes
    # that other test modules already imported by reference).
    _to_evict = [
        "backend.app_factory",
        "backend.app",
        "backend.config.settings",
        "backend.config.app_config",
    ]
    for mod in _to_evict:
        sys.modules.pop(mod, None)

    from backend.app_factory import create_app

    return create_app("development")


def test_warns_when_both_token_and_dev_open_api_are_set(caplog, monkeypatch):
    """Setting BOTH PERGEN_API_TOKEN and PERGEN_DEV_OPEN_API=1 is a
    contradictory configuration: the gate will enforce the token at
    runtime regardless of DEV_OPEN_API. The boot must emit a clear
    WARN so the operator does not waste time debugging "401 even
    though I set DEV_OPEN_API=1".
    """
    long_token = "x" * 32
    _attach_handler_to_factory(caplog.handler)

    _make_app(monkeypatch, token=long_token, dev_open=True)

    matched = [
        r for r in caplog.records
        if r.name == "app.factory"
        and r.levelno >= logging.WARNING
        and "PERGEN_DEV_OPEN_API" in r.getMessage()
        and "no effect" in r.getMessage().lower()
    ]
    assert matched, (
        "expected a WARN telling the operator that PERGEN_DEV_OPEN_API "
        "is ineffective when tokens are set; got: "
        f"{[r.getMessage() for r in caplog.records if r.name == 'app.factory']}"
    )


def test_no_warning_when_only_token_is_set(caplog, monkeypatch):
    """The opposite combination (token only) is the canonical
    authenticated dev/prod posture. Must not emit the contradictory-
    config warning.
    """
    long_token = "y" * 32
    _attach_handler_to_factory(caplog.handler)

    _make_app(monkeypatch, token=long_token, dev_open=False)

    matched = [
        r for r in caplog.records
        if r.name == "app.factory" and "no effect" in r.getMessage().lower()
    ]
    assert matched == [], (
        "must not warn about DEV_OPEN_API being ignored when DEV_OPEN_API "
        f"isn't set; got: {[r.getMessage() for r in matched]}"
    )


def test_no_warning_when_only_dev_open_api_is_set(caplog, monkeypatch):
    """The pure dev-open posture (no tokens) is also valid and
    explicitly opted into. Must not emit the contradictory-config
    warning.
    """
    _attach_handler_to_factory(caplog.handler)

    _make_app(monkeypatch, token=None, dev_open=True)

    matched = [
        r for r in caplog.records
        if r.name == "app.factory" and "no effect" in r.getMessage().lower()
    ]
    assert matched == [], (
        "must not warn about DEV_OPEN_API being ignored when no token is "
        f"set (dev-open is the active posture); got: {[r.getMessage() for r in matched]}"
    )
