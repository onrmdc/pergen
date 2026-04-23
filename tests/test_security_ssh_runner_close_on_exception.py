"""Python review C-4 / C-5 — ssh_runner FD-leak + error-bucket regression.

Audit references: ``backend/runners/ssh_runner.py`` lines 100-140 and
160-195.

Two related hardenings, pinned together because they live in the same
``finally``-protected exception path:

C-5 — FD leak on exception
--------------------------
``run_command`` and ``run_config_lines_pty`` now build the
``paramiko.SSHClient`` BEFORE entering ``try:``, then close it in a
``finally:`` block. Without this, a ``connect()`` exception leaks the
underlying socket / source-port slot — sustained device-side
flakiness used to drain the FD limit on the controller.

C-4 — controlled error vocabulary
---------------------------------
``run_config_lines_pty`` now classifies exceptions through
``_classify_ssh_error`` (e.g. ``"auth_failed"``, ``"timeout"``,
``"network"``) instead of returning ``str(exc)``. The raw exception
text could carry usernames, passwords, or environment details;
returning it to the SPA was a credential-leak vector on the
interface-recovery path.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.security]

# Allowed error buckets — must match _classify_ssh_error in the runner.
_ALLOWED_BUCKETS = {
    "auth_failed",
    "host_key_mismatch",
    "network",
    "ssh_protocol",
    "timeout",
}


def _make_failing_client(exc_factory):
    """Return a MagicMock SSHClient whose ``connect`` raises ``exc_factory()``."""
    client = MagicMock()
    client.connect.side_effect = exc_factory
    return client


# --------------------------------------------------------------------------- #
# C-5: client.close() must run on every exception path                        #
# --------------------------------------------------------------------------- #


def test_run_command_closes_client_on_auth_exception() -> None:
    """``connect()`` raising AuthenticationException must still close the client."""
    import paramiko

    from backend.runners import ssh_runner

    fake_client = _make_failing_client(
        lambda *a, **k: paramiko.AuthenticationException("nope")
    )
    with patch.object(ssh_runner, "_build_client", return_value=fake_client):
        out, err = ssh_runner.run_command("1.2.3.4", "alice", "pw", "show ver")

    assert out is None
    assert err is not None
    fake_client.close.assert_called(), (
        "ssh_runner.run_command must close the SSHClient even when "
        "connect() raises (audit Python review C-5)"
    )


def test_run_command_closes_client_on_network_exception() -> None:
    """An OSError during connect must still trigger ``close()``."""
    from backend.runners import ssh_runner

    fake_client = _make_failing_client(
        lambda *a, **k: OSError("ECONNREFUSED")
    )
    with patch.object(ssh_runner, "_build_client", return_value=fake_client):
        out, err = ssh_runner.run_command("1.2.3.4", "alice", "pw", "show ver")

    assert out is None
    assert err is not None
    fake_client.close.assert_called()


def test_run_config_lines_pty_closes_client_on_exception() -> None:
    """Same FD-leak guarantee for the config-push path."""
    import paramiko

    from backend.runners import ssh_runner

    fake_client = _make_failing_client(
        lambda *a, **k: paramiko.AuthenticationException("nope")
    )
    with patch.object(ssh_runner, "_build_client", return_value=fake_client):
        out, err = ssh_runner.run_config_lines_pty(
            "1.2.3.4", "alice", "pw", ["interface Ethernet1/1", "no shutdown"]
        )

    assert out is None
    assert err is not None
    fake_client.close.assert_called(), (
        "ssh_runner.run_config_lines_pty must close the SSHClient on "
        "exception (audit Python review C-5)"
    )


def test_run_command_closes_client_on_happy_path() -> None:
    """Symmetric contract: ``close()`` also runs when connect succeeds."""
    from backend.runners import ssh_runner

    fake_client = MagicMock()
    fake_stdout = MagicMock()
    fake_stdout.read.return_value = b"hello"
    fake_stderr = MagicMock()
    fake_stderr.read.return_value = b""
    fake_client.exec_command.return_value = (None, fake_stdout, fake_stderr)
    fake_client.connect.return_value = None

    with patch.object(ssh_runner, "_build_client", return_value=fake_client):
        out, err = ssh_runner.run_command("1.2.3.4", "alice", "pw", "show ver")

    assert err is None
    assert out == "hello"
    fake_client.close.assert_called()


# --------------------------------------------------------------------------- #
# C-4: run_config_lines_pty must return a controlled bucket, not str(exc)     #
# --------------------------------------------------------------------------- #


def test_run_config_lines_pty_returns_bucket_on_auth_failure() -> None:
    """Auth failure → bucket ``auth_failed``, not the raw exception text."""
    import paramiko

    from backend.runners import ssh_runner

    secret = "rotated-password-DO-NOT-LEAK"
    user = "alice"

    def _raise(*_a, **kw):
        # Worst case — paramiko widens the exception to include user/pass.
        raise paramiko.AuthenticationException(
            f"auth failed user={kw.get('username')} pass={kw.get('password')}"
        )

    with patch.object(paramiko.SSHClient, "connect", _raise):
        out, err = ssh_runner.run_config_lines_pty(
            "1.2.3.4", user, secret, ["interface Ethernet1/1", "no shutdown"]
        )

    assert out is None
    assert err == "auth_failed", (
        f"run_config_lines_pty must return the controlled bucket "
        f"'auth_failed' on AuthenticationException, got {err!r}"
    )
    # Defence in depth: the raw secret / username must not appear in the
    # error string under any circumstance.
    assert secret not in (err or "")
    assert user not in (err or "")


def test_run_config_lines_pty_returns_bucket_on_timeout() -> None:
    """TimeoutError → bucket ``timeout``."""
    from backend.runners import ssh_runner

    def _raise(*_a, **__):
        raise TimeoutError("connection timed out after 30s on 1.2.3.4")

    import paramiko

    with patch.object(paramiko.SSHClient, "connect", _raise):
        out, err = ssh_runner.run_config_lines_pty(
            "1.2.3.4", "alice", "pw", ["interface Ethernet1/1", "no shutdown"]
        )

    assert out is None
    assert err == "timeout", (
        f"run_config_lines_pty must bucket TimeoutError as 'timeout', got {err!r}"
    )


def test_run_config_lines_pty_returns_bucket_on_network_error() -> None:
    """OSError / network → bucket ``network``."""
    from backend.runners import ssh_runner

    def _raise(*_a, **__):
        raise OSError(111, "Connection refused on host 1.2.3.4 port 22")

    import paramiko

    with patch.object(paramiko.SSHClient, "connect", _raise):
        out, err = ssh_runner.run_config_lines_pty(
            "1.2.3.4", "alice", "pw", ["interface Ethernet1/1", "no shutdown"]
        )

    assert out is None
    assert err == "network", (
        f"run_config_lines_pty must bucket OSError as 'network', got {err!r}"
    )


def test_run_config_lines_pty_bucket_is_in_allowed_vocabulary() -> None:
    """Pin the controlled vocabulary — any bucket returned must be in
    the documented allow-list (or an ``other:<name>`` fallback). This
    catches future regressions that re-introduce ``str(exc)`` returns.
    """
    import paramiko

    from backend.runners import ssh_runner

    def _raise(*_a, **__):
        raise paramiko.SSHException("banner exchange failed")

    with patch.object(paramiko.SSHClient, "connect", _raise):
        out, err = ssh_runner.run_config_lines_pty(
            "1.2.3.4", "alice", "pw", ["foo"]
        )

    assert out is None
    assert err is not None
    assert err in _ALLOWED_BUCKETS or err.startswith("other:"), (
        f"runner returned uncontrolled error {err!r}; must be in "
        f"{sorted(_ALLOWED_BUCKETS)} or 'other:<class_name>'"
    )
