"""
TDD tests for ``backend.security.sanitizer.InputSanitizer``.

Every method MUST:
* return ``(True, cleaned)`` on accept,
* return ``(False, reason)`` on reject,
* reject ``\\x00`` null-bytes,
* be deterministic and side-effect free.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]


# --------------------------------------------------------------------------- #
# IP                                                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("ip", ["10.0.0.1", "192.168.0.1", "8.8.8.8", "255.255.255.255", "0.0.0.0"])  # noqa: S104
def test_sanitize_ip_accepts_valid(ip: str):
    from backend.security.sanitizer import InputSanitizer

    ok, val = InputSanitizer.sanitize_ip(ip)
    assert ok is True
    assert val == ip


@pytest.mark.parametrize(
    "bad",
    [
        "256.0.0.1",     # octet too large
        "10.0.0",        # too few octets
        "10.0.0.1.5",    # too many
        "abc.def.ghi.jk",
        "",
        " 10.0.0.1",     # leading whitespace
        "10.0.0.1 ",     # trailing whitespace
        "10.0.0.1\x00",  # null byte
        "127.0.0.1; rm -rf /",
        "1234567890123456",
    ],
)
def test_sanitize_ip_rejects_invalid(bad: str):
    from backend.security.sanitizer import InputSanitizer

    ok, msg = InputSanitizer.sanitize_ip(bad)
    assert ok is False
    assert isinstance(msg, str) and msg


def test_sanitize_ip_rejects_non_string():
    from backend.security.sanitizer import InputSanitizer

    ok, _ = InputSanitizer.sanitize_ip(12345)  # type: ignore[arg-type]
    assert ok is False


# --------------------------------------------------------------------------- #
# Hostname                                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("h", ["leaf01", "leaf-01.dc1.local", "spine_03", "router1.example.com"])
def test_sanitize_hostname_accepts_valid(h: str):
    from backend.security.sanitizer import InputSanitizer

    ok, val = InputSanitizer.sanitize_hostname(h)
    assert ok is True
    assert val == h


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "-leadingdash",
        "trailingdash-",
        "x" * 300,         # too long
        "host name",       # space
        "host;rm -rf /",
        "host\x00name",
        "../etc/passwd",
    ],
)
def test_sanitize_hostname_rejects_invalid(bad: str):
    from backend.security.sanitizer import InputSanitizer

    ok, _ = InputSanitizer.sanitize_hostname(bad)
    assert ok is False


# --------------------------------------------------------------------------- #
# Credential name                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("n", ["arista_admin", "cisco-prod", "default", "edge.svc"])
def test_sanitize_credential_name_accepts_valid(n: str):
    from backend.security.sanitizer import InputSanitizer

    ok, val = InputSanitizer.sanitize_credential_name(n)
    assert ok is True
    assert val == n


@pytest.mark.parametrize("bad", ["", "x" * 100, "with space", "name;rm", "n\x00ame", "../etc"])
def test_sanitize_credential_name_rejects_invalid(bad: str):
    from backend.security.sanitizer import InputSanitizer

    ok, _ = InputSanitizer.sanitize_credential_name(bad)
    assert ok is False


# --------------------------------------------------------------------------- #
# ASN                                                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "asn,expected",
    [("1", 1), ("65000", 65000), ("AS65000", 65000), ("4294967295", 4294967295), ("as 65000", 65000)],
)
def test_sanitize_asn_accepts_valid(asn: str, expected: int):
    from backend.security.sanitizer import InputSanitizer

    ok, val = InputSanitizer.sanitize_asn(asn)
    assert ok is True
    assert val == expected


@pytest.mark.parametrize("bad", ["0", "-1", "4294967296", "abcd", "", "AS\x00", "65000;ls"])
def test_sanitize_asn_rejects_invalid(bad: str):
    from backend.security.sanitizer import InputSanitizer

    ok, _ = InputSanitizer.sanitize_asn(bad)
    assert ok is False


# --------------------------------------------------------------------------- #
# Prefix                                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("p", ["10.0.0.0/24", "192.168.0.0/16", "0.0.0.0/0", "8.8.8.8/32"])
def test_sanitize_prefix_accepts_valid(p: str):
    from backend.security.sanitizer import InputSanitizer

    ok, val = InputSanitizer.sanitize_prefix(p)
    assert ok is True
    assert val == p


@pytest.mark.parametrize(
    "bad",
    ["", "10.0.0.0", "10.0.0.0/33", "300.0.0.0/24", "10.0.0.0/abc", "10.0.0.0/-1", "10.0.0.0/24\x00"],
)
def test_sanitize_prefix_rejects_invalid(bad: str):
    from backend.security.sanitizer import InputSanitizer

    ok, _ = InputSanitizer.sanitize_prefix(bad)
    assert ok is False


# --------------------------------------------------------------------------- #
# Generic string                                                              #
# --------------------------------------------------------------------------- #


def test_sanitize_string_accepts_normal():
    from backend.security.sanitizer import InputSanitizer

    ok, val = InputSanitizer.sanitize_string("hello", max_length=64)
    assert ok is True
    assert val == "hello"


def test_sanitize_string_rejects_too_long():
    from backend.security.sanitizer import InputSanitizer

    ok, _ = InputSanitizer.sanitize_string("x" * 100, max_length=64)
    assert ok is False


def test_sanitize_string_rejects_null_byte():
    from backend.security.sanitizer import InputSanitizer

    ok, _ = InputSanitizer.sanitize_string("hi\x00there")
    assert ok is False


# --------------------------------------------------------------------------- #
# OWASP-style fuzz round-trip                                                 #
# --------------------------------------------------------------------------- #


def test_sanitizers_never_raise_on_random_payloads():
    """All sanitizers must return a (bool,str) tuple — never raise — for any input."""
    import random
    import string

    from backend.security.sanitizer import InputSanitizer

    rng = random.Random(0xC0FFEE)
    methods = [
        InputSanitizer.sanitize_ip,
        InputSanitizer.sanitize_hostname,
        InputSanitizer.sanitize_credential_name,
        InputSanitizer.sanitize_asn,
        InputSanitizer.sanitize_prefix,
        InputSanitizer.sanitize_string,
    ]
    pool = string.printable + "\x00\x01" + "אバ漢字"
    for _ in range(200):
        s = "".join(rng.choices(pool, k=rng.randint(0, 80)))
        for m in methods:
            ok, _ = m(s)
            assert isinstance(ok, bool)
