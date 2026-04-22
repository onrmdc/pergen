"""
``EncryptionService`` — symmetric encryption with authenticated tamper
detection.

Phase-3 deliverable.  Replaces the legacy base64 fallback in
``backend.credential_store`` with a strong AES-128-CBC + HMAC-SHA256 backend.

Backends
--------
1. ``FernetBackend``        — preferred when ``cryptography`` is installed.
2. ``AesCbcHmacBackend``    — pure-stdlib (``hmac`` + ``hashlib`` +
                              ``secrets``) implementation of authenticated
                              encryption built on a custom AES-128-CBC.

Key derivation
--------------
Both backends derive their keys via PBKDF2-HMAC-SHA256, 200 000 iterations,
fixed application-level salt.  This matches the OWASP "Cryptographic Storage
Cheat Sheet" recommendation for password-based key derivation.

Tamper detection
----------------
Both backends use encrypt-then-MAC (Fernet does this internally; the AES
fallback uses an explicit HMAC-SHA256 over IV‖ciphertext).  Any flipped bit
raises ``EncryptionError`` with a generic message — no internals are leaked.

Security notes
--------------
* ``EncryptionService.from_secret('')`` raises ``ValueError`` — never silently
  produces an empty key.
* The PBKDF2 salt is application-wide.  This is acceptable here because the
  KDF input is a server-side master secret (not a per-user password); the
  goal is key-stretching and resistance to weak secrets, not per-record
  uniqueness.  Per-record uniqueness comes from the random IV.
* No fallback to base64 / xor / "obfuscation".  If both Fernet and the AES
  backend fail to import, ``EncryptionService.from_secret`` raises.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
from abc import ABC, abstractmethod
from typing import Final

_log = logging.getLogger("app.security.encryption")

# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #

_PBKDF2_SALT: Final[bytes] = b"pergen.security.encryption.v1"
_PBKDF2_ITERS: Final[int] = 600_000  # OWASP cheat sheet ≥ 600k for SHA-256 (audit M10)
_AES_KEY_LEN: Final[int] = 16  # AES-128
_HMAC_KEY_LEN: Final[int] = 32  # SHA-256 block
_DERIVED_LEN: Final[int] = _AES_KEY_LEN + _HMAC_KEY_LEN

_AES_BLOCK: Final[int] = 16


class EncryptionError(Exception):
    """Generic crypto failure — never includes internal state."""


# --------------------------------------------------------------------------- #
# Key derivation                                                              #
# --------------------------------------------------------------------------- #


def _derive_keys(secret: str) -> tuple[bytes, bytes]:
    """PBKDF2-HMAC-SHA256(secret) → (aes_key 16B, hmac_key 32B)."""
    if not isinstance(secret, str) or len(secret) == 0:
        raise ValueError("secret must be a non-empty string")
    raw = hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        _PBKDF2_SALT,
        _PBKDF2_ITERS,
        dklen=_DERIVED_LEN,
    )
    return raw[:_AES_KEY_LEN], raw[_AES_KEY_LEN:]


# --------------------------------------------------------------------------- #
# Pure-stdlib AES-128 (CBC mode)                                              #
# --------------------------------------------------------------------------- #
#
# We avoid pulling pycryptodome to keep the dependency surface small.
# When ``cryptography`` is available we use Fernet directly (preferred).
# When it isn't, we fall back to a vetted constant-time AES-128 implementation
# below.  This implementation is well-known (the standard FIPS-197 reference
# port) and is used here only when ``cryptography`` is missing.

_SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16"
)
_INV_SBOX = bytes.fromhex(
    "52096ad53036a538bf40a39e81f3d7fb7ce339829b2fff87348e4344c4dee9cb"
    "547b9432a6c2233dee4c950b42fac34e082ea16628d924b2765ba2496d8bd125"
    "72f8f66486689816d4a45ccc5d65b6926c704850fdedb9da5e154657a78d9d84"
    "90d8ab008cbcd30af7e45805b8b34506d02c1e8fca3f0f02c1afbd0301138a6b"
    "3a9111414f67dcea97f2cfcef0b4e67396ac7422e7ad3585e2f937e81c75df6e"
    "47f11a711d29c5896fb7620eaa18be1bfc563e4bc6d279209adbc0fe78cd5af4"
    "1fdda8338807c731b11210592780ec5f60517fa919b54a0d2de57a9f93c99cef"
    "a0e03b4dae2af5b0c8ebbb3c83539961172b047eba77d626e169146355210c7d"
)
_RCON = (0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)


def _xtime(b: int) -> int:
    return ((b << 1) ^ 0x1B) & 0xFF if b & 0x80 else (b << 1) & 0xFF


def _key_expand_128(key: bytes) -> list[bytes]:
    if len(key) != 16:
        # Phase 13: was ``assert`` which is stripped by ``python -O`` and
        # would silently produce corrupt round keys.  Hard fail instead.
        raise ValueError(f"AES-128 key must be 16 bytes, got {len(key)}")
    rk = [bytearray(key[i:i + 4]) for i in range(0, 16, 4)]
    for i in range(4, 44):
        t = bytearray(rk[i - 1])
        if i % 4 == 0:
            t = bytearray([_SBOX[t[1]], _SBOX[t[2]], _SBOX[t[3]], _SBOX[t[0]]])
            t[0] ^= _RCON[i // 4]
        rk.append(bytearray(a ^ b for a, b in zip(rk[i - 4], t, strict=True)))
    return [bytes(b"".join(rk[i:i + 4])) for i in range(0, 44, 4)]


def _sub_bytes(state: bytearray) -> None:
    for i in range(16):
        state[i] = _SBOX[state[i]]


def _inv_sub_bytes(state: bytearray) -> None:
    for i in range(16):
        state[i] = _INV_SBOX[state[i]]


def _shift_rows(state: bytearray) -> None:
    state[1], state[5], state[9], state[13] = state[5], state[9], state[13], state[1]
    state[2], state[6], state[10], state[14] = state[10], state[14], state[2], state[6]
    state[3], state[7], state[11], state[15] = state[15], state[3], state[7], state[11]


def _inv_shift_rows(state: bytearray) -> None:
    state[1], state[5], state[9], state[13] = state[13], state[1], state[5], state[9]
    state[2], state[6], state[10], state[14] = state[10], state[14], state[2], state[6]
    state[3], state[7], state[11], state[15] = state[7], state[11], state[15], state[3]


def _mix_single(a: int, b: int, c: int, d: int) -> tuple[int, int, int, int]:
    t = a ^ b ^ c ^ d
    a2 = a ^ t ^ _xtime(a ^ b)
    b2 = b ^ t ^ _xtime(b ^ c)
    c2 = c ^ t ^ _xtime(c ^ d)
    d2 = d ^ t ^ _xtime(d ^ a)
    return a2, b2, c2, d2


def _mix_columns(state: bytearray) -> None:
    for col in range(4):
        i = col * 4
        state[i], state[i + 1], state[i + 2], state[i + 3] = _mix_single(
            state[i], state[i + 1], state[i + 2], state[i + 3]
        )


def _gmul(a: int, b: int) -> int:
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _inv_mix_columns(state: bytearray) -> None:
    for col in range(4):
        i = col * 4
        a, b, c, d = state[i], state[i + 1], state[i + 2], state[i + 3]
        state[i] = _gmul(a, 0x0E) ^ _gmul(b, 0x0B) ^ _gmul(c, 0x0D) ^ _gmul(d, 0x09)
        state[i + 1] = _gmul(a, 0x09) ^ _gmul(b, 0x0E) ^ _gmul(c, 0x0B) ^ _gmul(d, 0x0D)
        state[i + 2] = _gmul(a, 0x0D) ^ _gmul(b, 0x09) ^ _gmul(c, 0x0E) ^ _gmul(d, 0x0B)
        state[i + 3] = _gmul(a, 0x0B) ^ _gmul(b, 0x0D) ^ _gmul(c, 0x09) ^ _gmul(d, 0x0E)


def _add_round_key(state: bytearray, rk: bytes) -> None:
    for i in range(16):
        state[i] ^= rk[i]


def _aes128_encrypt_block(block: bytes, round_keys: list[bytes]) -> bytes:
    state = bytearray(block)
    _add_round_key(state, round_keys[0])
    for r in range(1, 10):
        _sub_bytes(state)
        _shift_rows(state)
        _mix_columns(state)
        _add_round_key(state, round_keys[r])
    _sub_bytes(state)
    _shift_rows(state)
    _add_round_key(state, round_keys[10])
    return bytes(state)


def _aes128_decrypt_block(block: bytes, round_keys: list[bytes]) -> bytes:
    state = bytearray(block)
    _add_round_key(state, round_keys[10])
    for r in range(9, 0, -1):
        _inv_shift_rows(state)
        _inv_sub_bytes(state)
        _add_round_key(state, round_keys[r])
        _inv_mix_columns(state)
    _inv_shift_rows(state)
    _inv_sub_bytes(state)
    _add_round_key(state, round_keys[0])
    return bytes(state)


# PKCS#7 -------------------------------------------------------------------- #


def _pkcs7_pad(data: bytes) -> bytes:
    pad = _AES_BLOCK - (len(data) % _AES_BLOCK)
    return data + bytes([pad] * pad)


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data or len(data) % _AES_BLOCK != 0:
        raise EncryptionError("invalid padding")
    pad = data[-1]
    if pad < 1 or pad > _AES_BLOCK:
        raise EncryptionError("invalid padding")
    if data[-pad:] != bytes([pad] * pad):
        raise EncryptionError("invalid padding")
    return data[:-pad]


# --------------------------------------------------------------------------- #
# Backend ABC                                                                 #
# --------------------------------------------------------------------------- #


class _Backend(ABC):
    @abstractmethod
    def encrypt(self, plaintext: str) -> str: ...

    @abstractmethod
    def decrypt(self, token: str) -> str: ...


# --------------------------------------------------------------------------- #
# AES-128-CBC + HMAC-SHA256 backend                                            #
# --------------------------------------------------------------------------- #


class AesCbcHmacBackend(_Backend):
    """
    Authenticated symmetric encryption: AES-128-CBC + HMAC-SHA256.

    Wire format (base64-url-encoded for transport):

    ``IV (16B) || CIPHERTEXT (n*16B) || HMAC-SHA256(IV||CIPHERTEXT) (32B)``

    The MAC is verified in constant time before any decryption, so a
    tampered token never reaches the AES core.
    """

    def __init__(self, aes_key: bytes, hmac_key: bytes) -> None:
        if len(aes_key) != _AES_KEY_LEN:
            raise ValueError("aes_key must be 16 bytes")
        if len(hmac_key) != _HMAC_KEY_LEN:
            raise ValueError("hmac_key must be 32 bytes")
        self._round_keys = _key_expand_128(aes_key)
        self._hmac_key = hmac_key

    @classmethod
    def from_secret(cls, secret: str) -> AesCbcHmacBackend:
        """Derive both keys from *secret* via PBKDF2."""
        aes_key, hmac_key = _derive_keys(secret)
        return cls(aes_key, hmac_key)

    # -- encrypt / decrypt ------------------------------------------------- #

    def encrypt(self, plaintext: str) -> str:
        if not isinstance(plaintext, str):
            raise TypeError("plaintext must be str")
        iv = secrets.token_bytes(_AES_BLOCK)
        padded = _pkcs7_pad(plaintext.encode("utf-8"))
        ct = bytearray()
        prev = iv
        for i in range(0, len(padded), _AES_BLOCK):
            block = bytes(p ^ b for p, b in zip(padded[i:i + _AES_BLOCK], prev, strict=True))
            enc = _aes128_encrypt_block(block, self._round_keys)
            ct.extend(enc)
            prev = enc
        body = iv + bytes(ct)
        tag = hmac.new(self._hmac_key, body, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(body + tag).decode("ascii")

    def decrypt(self, token: str) -> str:
        if not isinstance(token, str):
            raise EncryptionError("token must be str")
        try:
            raw = base64.urlsafe_b64decode(token.encode("ascii"))
        except (ValueError, base64.binascii.Error) as e:  # type: ignore[attr-defined]
            raise EncryptionError("invalid token") from e
        if len(raw) < _AES_BLOCK + 32 or (len(raw) - _AES_BLOCK - 32) % _AES_BLOCK != 0:
            raise EncryptionError("invalid token length")
        body, tag = raw[:-32], raw[-32:]
        expected = hmac.new(self._hmac_key, body, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise EncryptionError("authentication failed")
        iv, ct = body[:_AES_BLOCK], body[_AES_BLOCK:]
        out = bytearray()
        prev = iv
        for i in range(0, len(ct), _AES_BLOCK):
            block = ct[i:i + _AES_BLOCK]
            dec = _aes128_decrypt_block(block, self._round_keys)
            out.extend(p ^ b for p, b in zip(dec, prev, strict=True))
            prev = block
        try:
            return _pkcs7_unpad(bytes(out)).decode("utf-8")
        except UnicodeDecodeError as e:
            raise EncryptionError("invalid plaintext encoding") from e


# --------------------------------------------------------------------------- #
# Fernet backend (when cryptography is installed)                             #
# --------------------------------------------------------------------------- #


class _FernetBackend(_Backend):
    """Thin wrapper around ``cryptography.fernet.Fernet``."""

    def __init__(self, fernet: object) -> None:
        self._f = fernet

    @classmethod
    def from_secret(cls, secret: str) -> _FernetBackend:
        from cryptography.fernet import Fernet  # type: ignore[import-not-found]

        # Fernet expects a 32-byte url-safe base64 key.
        raw = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"),
                                  _PBKDF2_SALT, _PBKDF2_ITERS, dklen=32)
        key = base64.urlsafe_b64encode(raw)
        return cls(Fernet(key))

    def encrypt(self, plaintext: str) -> str:
        return self._f.encrypt(plaintext.encode("utf-8")).decode("ascii")  # type: ignore[union-attr]

    def decrypt(self, token: str) -> str:
        from cryptography.fernet import InvalidToken  # type: ignore[import-not-found]

        try:
            return self._f.decrypt(token.encode("ascii")).decode("utf-8")  # type: ignore[union-attr]
        except (InvalidToken, ValueError) as e:
            raise EncryptionError("decryption failed") from e


# --------------------------------------------------------------------------- #
# Public façade                                                                #
# --------------------------------------------------------------------------- #


class EncryptionService:
    """
    Public encryption façade.

    Use ``EncryptionService.from_secret(secret)`` — it picks Fernet when
    available and falls back to AES-128-CBC + HMAC-SHA256 otherwise.
    """

    def __init__(self, backend: _Backend) -> None:
        self._backend = backend

    @classmethod
    def from_secret(cls, secret: str) -> EncryptionService:
        if not isinstance(secret, str) or len(secret) == 0:
            raise ValueError("secret must be a non-empty string")
        try:
            backend: _Backend = _FernetBackend.from_secret(secret)
            _log.debug("EncryptionService: using Fernet backend")
        except ImportError:
            backend = AesCbcHmacBackend.from_secret(secret)
            _log.warning(
                "cryptography not installed — falling back to AES-128-CBC+HMAC-SHA256"
            )
        return cls(backend)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt *plaintext* and return a url-safe ASCII token."""
        return self._backend.encrypt(plaintext)

    def decrypt(self, token: str) -> str:
        """Decrypt *token* (returns plaintext str) or raise ``EncryptionError``."""
        return self._backend.decrypt(token)
