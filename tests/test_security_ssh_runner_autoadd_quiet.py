"""
Wave-7 follow-up: ``ssh_runner._build_client()`` must NOT spam a WARN
on every call when the default ``AutoAddPolicy`` is in use.

Pergen is an internal-only operator tool — operators run ``/api/run/pre``
and ``/api/transceiver/recover`` against dozens of devices in a single
session, and the original WARN-per-build_client behaviour was making
every audit log line drown in policy noise.

The wave-7 fix: emit the policy notice ONCE per process at module
import time (level INFO, not WARN), so it stays discoverable in
``app.runner.ssh`` log filters without spamming. The lock-down path
(``PERGEN_SSH_STRICT_HOST_KEY=1`` → ``RejectPolicy``) is unchanged
and continues to be the right answer for any deployment that doesn't
trust the management network.

Audit reference: ``docs/security/DONE_audit_2026-04-23-wave7.md``,
"intentional posture: AutoAddPolicy default for internal device
enrollment".
"""
from __future__ import annotations

import logging

import pytest

pytestmark = [pytest.mark.security]


def test_build_client_does_not_log_warn_on_each_call(caplog):
    """Calling ``_build_client()`` 10× must produce zero new WARN
    records on the ``app.runner.ssh`` channel.

    The one-shot module-import notice is emitted at INFO level and
    fires before this test runs, so we don't expect to see it here.
    """
    from backend.runners import ssh_runner

    # Ensure paramiko is importable in the test environment; if not,
    # _build_client returns None and the test is a no-op.
    if ssh_runner.paramiko is None:
        pytest.skip("paramiko not installed in this environment")

    with caplog.at_level(logging.WARNING, logger="app.runner.ssh"):
        for _ in range(10):
            client = ssh_runner._build_client()
            # Don't actually connect; just exercise the construction path.
            del client

    warn_records = [
        r for r in caplog.records
        if r.name == "app.runner.ssh" and r.levelno >= logging.WARNING
    ]
    assert warn_records == [], (
        "ssh_runner._build_client() must not log WARN per call; "
        f"saw {len(warn_records)} WARN records: {[r.getMessage() for r in warn_records]}"
    )


def test_module_announces_policy_once_at_import_level_info(caplog):
    """Wave-7: the AutoAddPolicy notice should be discoverable at INFO,
    not WARN. We can't easily re-trigger the import-time log here, but
    we CAN assert that the module exposes a one-shot flag so a future
    refactor can't silently regress to per-call logging.
    """
    from backend.runners import ssh_runner

    # The wave-7 implementation uses a module-level flag to fire the
    # notice exactly once. Pin its existence so accidental removal is
    # caught by the test suite.
    assert hasattr(ssh_runner, "_AUTOADD_NOTICE_EMITTED"), (
        "ssh_runner must track the one-shot AutoAdd notice via a "
        "module-level flag (_AUTOADD_NOTICE_EMITTED)"
    )


def test_strict_host_key_path_remains_lockable(monkeypatch):
    """Wave-7 must not break the lock-down path.

    Setting ``PERGEN_SSH_STRICT_HOST_KEY=1`` (with a fresh module
    re-import) still flips the policy to RejectPolicy. This pins the
    audit-H1 control: operators who don't trust the management
    network can still lock the runner down.
    """
    import importlib

    monkeypatch.setenv("PERGEN_SSH_STRICT_HOST_KEY", "1")
    import backend.runners.ssh_runner as ssh_runner

    importlib.reload(ssh_runner)
    try:
        assert ssh_runner._HOST_KEY_POLICY_NAME == "RejectPolicy"
    finally:
        # Restore the default so other tests don't see the strict policy.
        monkeypatch.delenv("PERGEN_SSH_STRICT_HOST_KEY", raising=False)
        importlib.reload(ssh_runner)
