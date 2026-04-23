"""
Wave-7.9 follow-up — pin that ``backend.credential_store`` honours
``PERGEN_INSTANCE_DIR``.

The wave-7.9 fix added ``_instance_dir()`` so both ``_db_path()``
(legacy SHA-256 / Fernet store) and ``_v2_db_path()`` (the wave-7
fall-through bridge to the PBKDF2 + AES-CBC+HMAC store) resolve to
the operator's configured instance directory instead of the
hardcoded ``backend/instance``.

Without these tests, a future refactor could re-introduce the
hardcoded path. The existing
``tests/test_security_credential_v2_fallthrough.py`` monkeypatches
``_v2_db_path`` directly, so it never exercises the env-var path —
this file fills that gap.

The bug being pinned was real: any deployment that overrode
``PERGEN_INSTANCE_DIR`` (Playwright e2e suite, anyone with a custom
layout, every pytest test) silently lost the v2 bridge — credentials
written through ``CredentialService`` were unreachable. It also
masked test isolation: tests that asserted "no credential" behaviour
were accidentally finding the operator's REAL credentials in
``backend/instance/credentials_v2.db`` because the bridge looked
there regardless of any tmp-dir override.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.security, pytest.mark.unit]


# --------------------------------------------------------------------------- #
# Module-eviction helper                                                      #
# --------------------------------------------------------------------------- #
#
# ``backend.credential_store`` is a stateless module today (no module-level
# caches), but its helpers read ``os.environ`` live, so we don't need to
# re-import it between tests. We DO re-import once per test to be defensive
# against any future caching that might be added: importing fresh ensures
# we always exercise the latest module state under the new env.


def _fresh_credential_store():
    """Return a freshly-imported ``backend.credential_store`` module.

    Ensures any future module-level caching cannot mask a regression of
    the wave-7.9 env-respect fix.
    """
    sys.modules.pop("backend.credential_store", None)
    return importlib.import_module("backend.credential_store")


# --------------------------------------------------------------------------- #
# _instance_dir / _v2_db_path / _db_path env-var honour                       #
# --------------------------------------------------------------------------- #


class TestInstanceDirEnv:
    def test_instance_dir_uses_pergen_instance_dir_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        custom = tmp_path / "ops-custom-layout"
        monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(custom))
        cs = _fresh_credential_store()
        assert cs._instance_dir() == str(custom), (
            "wave-7.9 regression: _instance_dir() ignored PERGEN_INSTANCE_DIR"
        )

    def test_instance_dir_falls_back_to_backend_instance_when_env_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without the env var, the helper must return the historic
        ``backend/instance`` default — backward compatibility for
        operators who never set the env.
        """
        monkeypatch.delenv("PERGEN_INSTANCE_DIR", raising=False)
        cs = _fresh_credential_store()
        resolved = cs._instance_dir()
        # Must end with backend/instance (path separator is OS-dependent).
        assert resolved.replace("\\", "/").endswith("/backend/instance"), (
            f"unexpected default instance dir: {resolved!r}"
        )

    def test_instance_dir_treats_blank_env_as_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Operators sometimes leave ``PERGEN_INSTANCE_DIR=`` in .env
        files. Whitespace-only must NOT shadow the default — otherwise
        the empty string becomes a relative cwd, silently scattering
        credential files across whatever directory the worker started in.
        """
        monkeypatch.setenv("PERGEN_INSTANCE_DIR", "   ")
        cs = _fresh_credential_store()
        resolved = cs._instance_dir()
        assert resolved.replace("\\", "/").endswith("/backend/instance"), (
            f"blank env must fall back to default; got {resolved!r}"
        )


class TestDbPathHelpers:
    def test_v2_db_path_uses_pergen_instance_dir_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        custom = tmp_path / "instance"
        monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(custom))
        cs = _fresh_credential_store()
        assert cs._v2_db_path() == str(custom / "credentials_v2.db"), (
            "wave-7.9 regression: _v2_db_path() ignored PERGEN_INSTANCE_DIR"
        )

    def test_db_path_uses_pergen_instance_dir_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        custom = tmp_path / "instance"
        monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(custom))
        cs = _fresh_credential_store()
        # _db_path() also creates the parent dir as a side effect; we
        # tolerate that and just assert the path itself.
        assert cs._db_path() == str(custom / "credentials.db"), (
            "wave-7.9 regression: _db_path() ignored PERGEN_INSTANCE_DIR"
        )

    def test_v2_db_path_does_not_leak_to_backend_instance(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Defence-in-depth: even if a future change adds caching, the
        v2 path under PERGEN_INSTANCE_DIR must NEVER coincide with the
        operator's real ``backend/instance/credentials_v2.db`` (which
        was the exact masking bug wave-7.9 closed).
        """
        custom = tmp_path / "isolated"
        monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(custom))
        cs = _fresh_credential_store()
        v2 = cs._v2_db_path()
        assert "/backend/instance/" not in v2.replace("\\", "/"), (
            f"v2 path leaked to backend/instance: {v2!r}"
        )


# --------------------------------------------------------------------------- #
# End-to-end: get_credential bridge honours the env                           #
# --------------------------------------------------------------------------- #


class TestBridgeEndToEndUsesEnvDir:
    def test_get_credential_bridge_reads_from_env_instance_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """End-to-end: write a credential through ``CredentialRepository``
        into the env-configured instance dir, then call the legacy
        ``credential_store.get_credential(...)`` and assert the v2
        fall-through bridge returns the row.

        This is the test that would have caught the wave-7.9 bug from
        end to end — without it, the path-helper unit tests above could
        all pass while the bridge itself silently looked elsewhere.
        """
        from backend.repositories.credential_repository import (
            CredentialRepository,
        )
        from backend.security.encryption import EncryptionService

        secret = "wave-7-9-instance-dir-env-test"
        custom = tmp_path / "ops-instance"
        custom.mkdir()
        monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(custom))

        # Seed the v2 store at the env-configured path.
        v2_path = custom / "credentials_v2.db"
        enc = EncryptionService.from_secret(secret)
        repo = CredentialRepository(str(v2_path), enc)
        repo.create_schema()
        repo.set("device-cred", method="basic", username="alice", password="hunter2")
        assert v2_path.exists(), "test setup failed: v2 db not created"

        # Make the legacy DB present-but-empty so the lookup must
        # actually go through the bridge (not just fall through because
        # there's no legacy DB at all).
        cs = _fresh_credential_store()
        cs.init_db(secret)  # creates empty backend/instance/credentials.db
        # Note: init_db respects _instance_dir() too, so the empty
        # legacy DB lands at <custom>/credentials.db — exactly the
        # scenario a fresh-install operator hits.

        payload = cs.get_credential("device-cred", secret)
        assert payload is not None, (
            "wave-7.9 regression: bridge could not find credential at "
            "PERGEN_INSTANCE_DIR location"
        )
        assert payload.get("name") == "device-cred"
        assert payload.get("method") == "basic"
        assert payload.get("username") == "alice"
        assert payload.get("password") == "hunter2"

    def test_bridge_returns_none_when_env_dir_has_neither_db(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Sanity: pointing the env var at an empty directory must
        surface "not found" cleanly, not raise. Catches a regression
        where the bridge might raise on a missing v2 DB instead of
        returning None.
        """
        empty = tmp_path / "empty-instance"
        empty.mkdir()
        monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(empty))

        cs = _fresh_credential_store()
        # init_db creates an empty legacy schema; the v2 DB does not
        # exist. Lookup must return None, not raise.
        cs.init_db("any-secret")
        assert cs.get_credential("missing", "any-secret") is None
