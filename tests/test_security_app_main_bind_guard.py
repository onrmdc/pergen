"""H-3 — ``backend/app.py`` ``__main__`` bind guard regression test.

Audit (Security review H-3): the legacy ``backend/app`` shim no longer
registers any routes, so a ``python -m backend.app`` invocation used to
bind ``0.0.0.0`` with zero routes AND bypass the API token gate (which
is mounted by ``create_app``). That created a latent foot-gun: a future
contributor restoring ``from backend.blueprints import …`` here would
expose every route publicly without auth.

The fix:
  * default bind is ``127.0.0.1`` (controlled by
    ``PERGEN_DEV_BIND_HOST``);
  * any non-loopback host requires the explicit
    ``PERGEN_DEV_ALLOW_PUBLIC_BIND=1`` opt-in;
  * otherwise the ``__main__`` branch raises ``SystemExit``.

This test pins the source-level invariants. We assert via
``inspect.getsource`` so a future refactor that drops the guard and
restores ``host="0.0.0.0"`` lights up immediately.
"""
from __future__ import annotations

import inspect
import os
import subprocess
import sys

import pytest

pytestmark = [pytest.mark.security]


def _app_source() -> str:
    """Return the source of ``backend/app.py`` as a string."""
    import backend.app as app_mod

    return inspect.getsource(app_mod)


def test_app_main_does_not_hardcode_zero_bind() -> None:
    """The literal ``host="0.0.0.0"`` must not appear in backend/app.py."""
    src = _app_source()
    assert 'host="0.0.0.0"' not in src, (
        "backend/app.py must not hardcode host='0.0.0.0'; the __main__ "
        "branch must default to 127.0.0.1 and require an opt-in env var "
        "for any other interface."
    )
    assert "host='0.0.0.0'" not in src, (
        "single-quoted form of host='0.0.0.0' is also forbidden"
    )


def test_app_main_uses_loopback_default() -> None:
    """Default bind host must be ``127.0.0.1``."""
    src = _app_source()
    assert 'PERGEN_DEV_BIND_HOST", "127.0.0.1"' in src or \
           "PERGEN_DEV_BIND_HOST', '127.0.0.1'" in src, (
        "backend/app.py __main__ must default PERGEN_DEV_BIND_HOST to 127.0.0.1"
    )


def test_app_main_requires_public_bind_opt_in() -> None:
    """Non-loopback bind requires ``PERGEN_DEV_ALLOW_PUBLIC_BIND=1``."""
    src = _app_source()
    assert "PERGEN_DEV_ALLOW_PUBLIC_BIND" in src, (
        "backend/app.py __main__ guard must reference "
        "PERGEN_DEV_ALLOW_PUBLIC_BIND so a public bind is gated on an "
        "explicit operator opt-in."
    )
    # The guard must call SystemExit (or raise it) when the opt-in is missing.
    assert "SystemExit" in src, (
        "backend/app.py __main__ guard must SystemExit when a non-loopback "
        "host is requested without the opt-in env var."
    )


def test_app_main_subprocess_refuses_public_bind_without_opt_in() -> None:
    """End-to-end: invoking the module with a public host must exit non-zero.

    We simulate the operator footgun: ``python -m backend.app`` with
    ``PERGEN_DEV_BIND_HOST=0.0.0.0`` and no opt-in. The subprocess must
    exit with a non-zero status before binding anything.
    """
    env = os.environ.copy()
    env["PERGEN_DEV_BIND_HOST"] = "0.0.0.0"  # noqa: S104 - test must simulate this
    env.pop("PERGEN_DEV_ALLOW_PUBLIC_BIND", None)
    # Provide a token so the dev-open-API guard does not preempt our test.
    env["PERGEN_API_TOKEN"] = "x" * 64
    # PORT=0 would be ideal but we never reach app.run(); SystemExit fires first.
    proc = subprocess.run(
        [sys.executable, "-m", "backend.app"],
        env=env,
        capture_output=True,
        timeout=15,
    )
    assert proc.returncode != 0, (
        "backend.app __main__ should refuse to start with a non-loopback "
        f"PERGEN_DEV_BIND_HOST and no opt-in (returncode={proc.returncode}, "
        f"stderr={proc.stderr.decode('utf-8', 'replace')!r})"
    )
    # Stderr/stdout should mention the offending env var so the operator
    # can self-diagnose.
    combined = (proc.stdout + proc.stderr).decode("utf-8", "replace")
    assert "PERGEN_DEV_ALLOW_PUBLIC_BIND" in combined, (
        f"the error message must name PERGEN_DEV_ALLOW_PUBLIC_BIND so the "
        f"operator knows how to opt in. Got: {combined!r}"
    )
