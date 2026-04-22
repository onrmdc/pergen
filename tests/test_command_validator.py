r"""
TDD tests for ``backend.security.validator.CommandValidator``.

Contract:
* Only ``str`` accepted; max length 512.
* Must start with ``show `` or ``dir `` (case-insensitive).
* Reject if it contains: ``conf t``, ``configure terminal``, ``| write``,
  ``write mem``, ``copy run start``, ``;``, ``&&``, ``||``, ``\``` (backtick),
  ``$(``.
* Returns ``(True, "")`` on accept, ``(False, reason)`` on reject.
* Logs WARNING on every rejection.
"""
from __future__ import annotations

import logging

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]


# --------------------------------------------------------------------------- #
# Accept paths                                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "cmd",
    [
        "show version",
        "SHOW running-config",
        "show ip route",
        "dir flash:",
        "  show interfaces  ",
        "show ip bgp neighbors 10.0.0.1 advertised-routes",
    ],
)
def test_validate_accepts_show_and_dir(cmd: str):
    from backend.security.validator import CommandValidator

    ok, reason = CommandValidator.validate(cmd)
    assert ok is True, reason
    assert reason == ""


# --------------------------------------------------------------------------- #
# Type / size                                                                 #
# --------------------------------------------------------------------------- #


def test_validate_rejects_non_string():
    from backend.security.validator import CommandValidator

    ok, msg = CommandValidator.validate(123)  # type: ignore[arg-type]
    assert ok is False
    assert "string" in msg.lower() or "type" in msg.lower()


def test_validate_rejects_too_long():
    from backend.security.validator import CommandValidator

    ok, msg = CommandValidator.validate("show " + ("x" * 1000))
    assert ok is False
    assert "length" in msg.lower() or "long" in msg.lower()


def test_validate_rejects_empty():
    from backend.security.validator import CommandValidator

    ok, _ = CommandValidator.validate("")
    assert ok is False


# --------------------------------------------------------------------------- #
# Prefix                                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "cmd",
    [
        "configure terminal",
        "no shutdown",
        "interface Eth1/1",
        "reload",
        "ping 8.8.8.8",
        "telnet 10.0.0.1",
    ],
)
def test_validate_rejects_non_show_prefix(cmd: str):
    from backend.security.validator import CommandValidator

    ok, _ = CommandValidator.validate(cmd)
    assert ok is False


# --------------------------------------------------------------------------- #
# Blocklist (defence in depth — even when prefix passes)                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "cmd",
    [
        "show version; conf t",
        "show running | write",
        "show run && copy run start",
        "show interfaces || reload",
        "show version `whoami`",
        "show version $(whoami)",
        "show conf t",
        "show running write mem",
        "show vlan ; reload",
    ],
)
def test_validate_rejects_blocklisted_substrings(cmd: str):
    from backend.security.validator import CommandValidator

    ok, _ = CommandValidator.validate(cmd)
    assert ok is False


# --------------------------------------------------------------------------- #
# Logging                                                                     #
# --------------------------------------------------------------------------- #


def test_validate_logs_warning_on_rejection(caplog):
    from backend.security.validator import CommandValidator

    with caplog.at_level(logging.WARNING):
        CommandValidator.validate("configure terminal")
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)
