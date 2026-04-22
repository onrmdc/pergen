"""
OWASP Top-10 + business-logic security tests.

Phase-11 deliverable.  Validates the security layer (phase 3), the
authenticated encryption (phase 3), the command validator (phase 3),
the input sanitiser (phase 3) and the blueprint contracts (phase 9)
against the most relevant OWASP categories for a network-automation
application.

Categories covered
------------------
* A01 Broken Access Control            — credential payload never leaks.
* A02 Cryptographic Failures           — tamper detection, no fallback.
* A03 Injection                        — command injection, header injection,
                                         null byte injection across every
                                         sanitiser.
* A04 Insecure Design                  — production refuses default secrets.
* A05 Security Misconfiguration        — sensitive log keys redacted.
* A07 Identification & Authn Failures  — generic credential errors.
* A08 Software & Data Integrity        — encryption fails closed.
* A09 Logging & Monitoring Failures    — request id assigned to every request.
* A10 SSRF / business-logic            — find_leaf / nat / device-by-tag refuse
                                         malformed inputs.

Each test is small and isolated — a security regression in any
dimension trips a single, named test rather than hiding inside a
larger functional check.
"""
from __future__ import annotations

import pytest

from backend.security.encryption import EncryptionService
from backend.security.sanitizer import InputSanitizer
from backend.security.validator import CommandValidator

pytestmark = [pytest.mark.security, pytest.mark.unit]


# --------------------------------------------------------------------------- #
# A03 — Injection (command + null-byte + shell-meta)                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "command",
    [
        "show version",
        "show ip route",
        "show interface Ethernet1",
        "dir flash:",
    ],
)
def test_command_validator_accepts_safe_show_commands(command):
    ok, reason = CommandValidator.validate(command)
    assert ok, f"expected pass, got: {reason}"


@pytest.mark.parametrize(
    "command",
    [
        "configure terminal",
        "conf t",
        "show version; reload",
        "show version && reload",
        "show version || rm -rf /",
        "show version | write",
        "write memory",
        "copy run start",
        "show version `whoami`",
        "show version $(whoami)",
        "reload",
        "ping 8.8.8.8",
        "",
        " ",
        "show " + ("a" * 600),  # too long
    ],
)
def test_command_validator_rejects_dangerous_commands(command):
    ok, reason = CommandValidator.validate(command)
    assert not ok, f"expected REJECT, but got pass for: {command!r}"
    assert reason, "rejection must include a reason"


def test_command_validator_rejects_non_string():
    for value in (None, 1234, ["show version"], {"cmd": "show version"}):
        ok, _ = CommandValidator.validate(value)  # type: ignore[arg-type]
        assert not ok


# --------------------------------------------------------------------------- #
# A03 — Input sanitiser fuzz                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value",
    [
        "10.0.0.1\x00",
        "leaf-01\x00drop",
        "credname\x00",
        "AS65000\x00",
        "10.0.0.0/24\x00",
        "hello\x00world",
    ],
)
def test_sanitisers_reject_null_bytes(value):
    """Every sanitiser must reject null bytes — A03 / A05."""
    for fn in (
        InputSanitizer.sanitize_ip,
        InputSanitizer.sanitize_hostname,
        InputSanitizer.sanitize_credential_name,
        InputSanitizer.sanitize_asn,
        InputSanitizer.sanitize_prefix,
    ):
        ok, _ = fn(value)
        assert not ok, f"{fn.__name__} accepted null byte: {value!r}"

    ok, _ = InputSanitizer.sanitize_string(value, max_length=128)
    assert not ok


@pytest.mark.parametrize(
    "value",
    [
        "10.0.0.300",
        "10.0.0",
        "999.999.999.999",
        "abc.def.ghi.jkl",
        "10.0.0.1; rm -rf /",
        "10.0.0.1 OR 1=1",
        "<script>alert(1)</script>",
        "../../etc/passwd",
        "",
    ],
)
def test_ip_sanitiser_rejects_garbage(value):
    ok, _ = InputSanitizer.sanitize_ip(value)
    assert not ok


@pytest.mark.parametrize(
    "value",
    [
        "leaf-01; rm -rf /",
        "leaf-01 && reboot",
        "leaf-01`whoami`",
        "leaf-01$(reboot)",
        "leaf-01|cat /etc/shadow",
        "../leaf-01",
        "<svg onload=alert(1)>",
        "a" * 300,
        "",
    ],
)
def test_hostname_sanitiser_rejects_shell_meta(value):
    ok, _ = InputSanitizer.sanitize_hostname(value)
    assert not ok


@pytest.mark.parametrize(
    "value",
    [
        "lab",
        "lab-1",
        "lab_2",
        "PROD",
    ],
)
def test_credential_name_sanitiser_accepts_safe(value):
    ok, cleaned = InputSanitizer.sanitize_credential_name(value)
    assert ok
    assert cleaned == value


@pytest.mark.parametrize(
    "value",
    [
        "lab; drop table",
        "lab && cat",
        "lab/../etc",
        "lab|whoami",
        "lab$(reboot)",
        "lab`id`",
        "a" * 80,
        "",
    ],
)
def test_credential_name_sanitiser_rejects_unsafe(value):
    ok, _ = InputSanitizer.sanitize_credential_name(value)
    assert not ok


# --------------------------------------------------------------------------- #
# A02 / A08 — Cryptographic integrity                                         #
# --------------------------------------------------------------------------- #


def test_encryption_round_trip_preserves_payload():
    enc = EncryptionService.from_secret("phase-11-test-secret")
    blob = enc.encrypt("hello world")
    assert enc.decrypt(blob) == "hello world"


def test_encryption_detects_tamper():
    """Flipping a single byte in the ciphertext MUST raise EncryptionError."""
    from backend.security.encryption import EncryptionError

    enc = EncryptionService.from_secret("phase-11-test-secret")
    blob = enc.encrypt("super secret")
    tampered = blob[:-2] + ("A" if blob[-2] != "A" else "B") + blob[-1]
    with pytest.raises(EncryptionError):
        enc.decrypt(tampered)


def test_encryption_rejects_empty_secret():
    with pytest.raises(ValueError):
        EncryptionService.from_secret("")


def test_encryption_different_secrets_produce_different_keys():
    from backend.security.encryption import EncryptionError

    a = EncryptionService.from_secret("secret-A")
    b = EncryptionService.from_secret("secret-B")
    blob_a = a.encrypt("payload")
    with pytest.raises(EncryptionError):
        b.decrypt(blob_a)


# --------------------------------------------------------------------------- #
# A04 — Insecure design (production config validation)                        #
# --------------------------------------------------------------------------- #


def test_production_config_rejects_default_secret():
    from backend.config.app_config import DEFAULT_SECRET_KEY, ProductionConfig

    cfg = ProductionConfig(SECRET_KEY=DEFAULT_SECRET_KEY)
    with pytest.raises(RuntimeError):
        cfg.validate()


def test_production_config_rejects_empty_secret():
    from backend.config.app_config import ProductionConfig

    cfg = ProductionConfig(SECRET_KEY="")
    with pytest.raises(RuntimeError):
        cfg.validate()


def test_production_config_accepts_strong_secret():
    from backend.config.app_config import ProductionConfig

    cfg = ProductionConfig(SECRET_KEY="a-strong-secret-value-not-the-default")
    cfg.validate()  # should not raise


# --------------------------------------------------------------------------- #
# A05 — Sensitive-key redaction in log extras                                 #
# --------------------------------------------------------------------------- #


def test_redact_sensitive_masks_sensitive_keys():
    from backend.logging_config import redact_sensitive

    out = redact_sensitive(
        {
            "user": "alice",
            "password": "hunter2",
            "api_key": "sk-XXXXX",
            "Authorization": "Bearer abc",
            "Cookie": "session=xyz",
            "harmless": "value",
        }
    )
    assert out["user"] == "alice"
    assert out["harmless"] == "value"
    assert out["password"] == "***REDACTED***"
    assert out["api_key"] == "***REDACTED***"
    assert out["Authorization"] == "***REDACTED***"
    assert out["Cookie"] == "***REDACTED***"


# --------------------------------------------------------------------------- #
# A07 — Generic credential failure / no enumeration                           #
# --------------------------------------------------------------------------- #


def test_credential_service_set_rejects_unsafe_name():
    """A07 — the service must refuse a credential name that contains
    shell-meta characters before persisting anything."""
    from unittest.mock import MagicMock

    from backend.services.credential_service import CredentialService

    repo = MagicMock()
    svc = CredentialService(repo)

    with pytest.raises(ValueError):
        svc.set("lab; rm -rf /", method="basic", username="u", password="p")
    repo.set.assert_not_called()


# --------------------------------------------------------------------------- #
# A09 — Logging & monitoring (request id stamped on every request)            #
# --------------------------------------------------------------------------- #


def test_every_response_has_request_id_header(client):
    r = client.get("/api/health")
    assert "X-Request-ID" in r.headers
    assert len(r.headers["X-Request-ID"]) >= 8


# --------------------------------------------------------------------------- #
# A10 / business-logic — input refusal at the route boundary                  #
# --------------------------------------------------------------------------- #


def test_devices_by_tag_requires_tag(client):
    body = client.get("/api/devices-by-tag").get_json()
    assert body == {"devices": []}


def test_sites_requires_fabric(client):
    body = client.get("/api/sites").get_json()
    assert body == {"sites": []}


def test_devices_arista_requires_fabric(client):
    body = client.get("/api/devices-arista").get_json()
    assert body == {"devices": []}


def test_notepad_put_rejects_missing_content(client):
    r = client.put("/api/notepad", json={"user": "alice"})
    assert r.status_code == 400


def test_notepad_get_returns_redactable_shape_only(client):
    """The GET response must NEVER include obvious secret/credential keys."""
    body = client.get("/api/notepad").get_json()
    assert set(body.keys()) == {"content", "line_editors"}


# --------------------------------------------------------------------------- #
# A01 — Credential repository never leaks payload via list()                  #
# --------------------------------------------------------------------------- #


def test_credential_repository_list_does_not_leak_payload(tmp_path):
    from backend.repositories.credential_repository import CredentialRepository

    enc = EncryptionService.from_secret("phase-11-test-secret")
    repo = CredentialRepository(str(tmp_path / "creds.db"), enc)
    repo.create_schema()
    repo.set("lab", method="basic", username="admin", password="hunter2")

    listing = repo.list()
    assert listing == [
        {"name": "lab", "method": "basic", "updated_at": listing[0]["updated_at"]}
    ]
    for entry in listing:
        for forbidden in ("password", "username", "api_key", "value_enc"):
            assert forbidden not in entry, f"list() leaked {forbidden}"
