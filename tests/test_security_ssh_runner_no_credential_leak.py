"""M-11 — `ssh_runner.run_command` returns `str(e)` to the caller.

Connection exceptions can include the username (and historically the
password tail). The response is echoed back to the operator UI via
device-commands and BGP routes, so a future paramiko upgrade widening
the exception text would leak immediately.

Audit reference: ``docs/security/audit_2026-04-22.md`` §3.2 M-11.

Desired contract: error map to a controlled vocabulary; the username and
password must never appear in the returned `err` field. XFAIL until the
mapping lands.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.security]


def test_ssh_runner_error_does_not_echo_credential_substring() -> None:
    """If paramiko leaks user/pass into its exception, the runner must scrub it."""
    import paramiko

    from backend.runners import ssh_runner

    secret = "super-secret-password"
    user = "alice"

    def _raise(*_a, **kw):
        # Simulate the paramiko widened-exception future regression.
        raise paramiko.SSHException(
            f"auth failed for user={kw.get('username')} password={kw.get('password')}"
        )

    with patch.object(paramiko.SSHClient, "connect", _raise):
        out, err = ssh_runner.run_command("1.2.3.4", user, secret, "show ver")

    assert err is not None
    assert secret not in (err or ""), "ssh_runner leaks password tail in error"
    assert user not in (err or ""), "ssh_runner leaks username in error"
