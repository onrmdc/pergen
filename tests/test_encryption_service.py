"""
TDD tests for ``backend.security.encryption.EncryptionService``.

Hardened encryption layer.  Two backends:

1. Primary: Fernet (cryptography) — if installed.
2. Fallback: AES-128-CBC + HMAC-SHA256 (encrypt-then-MAC, PBKDF2 key
   derivation, random IV per message).

Both backends:
* derive keys via PBKDF2-HMAC-SHA256 with ≥100k iterations,
* round-trip arbitrary bytes,
* tamper-detect (any flipped bit raises ``EncryptionError``),
* never expose the key in error messages.
"""
from __future__ import annotations

import secrets

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]


SECRET = "test-secret-key-1234567890"


# --------------------------------------------------------------------------- #
# Generic round-trip                                                          #
# --------------------------------------------------------------------------- #


def test_encrypt_decrypt_round_trip():
    from backend.security.encryption import EncryptionService

    svc = EncryptionService.from_secret(SECRET)
    plaintext = "hunter2!"
    token = svc.encrypt(plaintext)
    assert isinstance(token, str)
    assert SECRET not in token
    assert plaintext not in token
    assert svc.decrypt(token) == plaintext


def test_encrypt_produces_different_ciphertexts_for_same_input():
    """Random IV/nonce per call MUST yield different ciphertexts."""
    from backend.security.encryption import EncryptionService

    svc = EncryptionService.from_secret(SECRET)
    a = svc.encrypt("same")
    b = svc.encrypt("same")
    assert a != b


def test_decrypt_with_wrong_secret_raises():
    from backend.security.encryption import EncryptionError, EncryptionService

    a = EncryptionService.from_secret(SECRET)
    b = EncryptionService.from_secret("a-different-secret-XXXXXXXXXX")
    token = a.encrypt("hi")
    with pytest.raises(EncryptionError):
        b.decrypt(token)


def test_decrypt_tampered_token_raises():
    from backend.security.encryption import EncryptionError, EncryptionService

    svc = EncryptionService.from_secret(SECRET)
    token = svc.encrypt("data")
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    with pytest.raises(EncryptionError):
        svc.decrypt(tampered)


def test_decrypt_garbage_raises():
    from backend.security.encryption import EncryptionError, EncryptionService

    svc = EncryptionService.from_secret(SECRET)
    with pytest.raises(EncryptionError):
        svc.decrypt("not-a-valid-token")


def test_encrypt_handles_unicode_and_long_input():
    from backend.security.encryption import EncryptionService

    svc = EncryptionService.from_secret(SECRET)
    payload = "passw0rd " + "אבג" * 200
    assert svc.decrypt(svc.encrypt(payload)) == payload


# --------------------------------------------------------------------------- #
# Fallback backend (always available)                                          #
# --------------------------------------------------------------------------- #


def test_aes_fallback_round_trip_explicitly():
    """Even when Fernet is available, the AES fallback class itself must work."""
    from backend.security.encryption import AesCbcHmacBackend

    backend = AesCbcHmacBackend.from_secret(SECRET)
    token = backend.encrypt("hi")
    assert backend.decrypt(token) == "hi"


def test_aes_fallback_tamper_detection():
    from backend.security.encryption import AesCbcHmacBackend, EncryptionError

    backend = AesCbcHmacBackend.from_secret(SECRET)
    token = backend.encrypt("hi")
    # Flip one byte in the middle of the base64 token.
    raw = bytearray(token, "ascii")
    raw[len(raw) // 2] = ord("A") if raw[len(raw) // 2] != ord("A") else ord("B")
    with pytest.raises(EncryptionError):
        backend.decrypt(raw.decode("ascii"))


def test_aes_fallback_key_derivation_is_deterministic():
    """Same secret + same salt → same key (PBKDF2 is deterministic)."""
    from backend.security.encryption import AesCbcHmacBackend

    a = AesCbcHmacBackend.from_secret(SECRET)
    b = AesCbcHmacBackend.from_secret(SECRET)
    # Round-trip across instances must work (proves keys match).
    assert b.decrypt(a.encrypt("x")) == "x"


def test_aes_fallback_uses_random_iv():
    from backend.security.encryption import AesCbcHmacBackend

    backend = AesCbcHmacBackend.from_secret(SECRET)
    seen = {backend.encrypt("same") for _ in range(5)}
    assert len(seen) == 5  # all distinct


def test_encryption_service_secret_required():
    """from_secret('') must raise ValueError, not silently use empty key."""
    from backend.security.encryption import EncryptionService

    with pytest.raises(ValueError):
        EncryptionService.from_secret("")


# --------------------------------------------------------------------------- #
# Light fuzz                                                                  #
# --------------------------------------------------------------------------- #


def test_encrypt_round_trip_fuzz():
    from backend.security.encryption import EncryptionService

    svc = EncryptionService.from_secret(SECRET)
    for _ in range(50):
        s = secrets.token_urlsafe(secrets.choice(range(0, 256)))
        assert svc.decrypt(svc.encrypt(s)) == s
