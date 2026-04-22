"""
``CommandValidator`` — defence-in-depth check for any command sent to a
network device by Pergen.

Phase-3 deliverable.

Pipeline
--------
1. Type / length / non-empty.
2. Read-only prefix: must start with ``show `` or ``dir `` (case-insensitive).
3. Blocklist scan for shell/CLI escapes that would let an attacker pivot from
   "read-only" to "destructive" (`;`, `&&`, `||`, backticks, ``$(``,
   ``conf t``, ``configure terminal``, ``write mem``, ``copy run start``,
   ``| write``).

Every rejection is logged at WARNING for SIEM consumption.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Final

_log = logging.getLogger("app.security.validator")

_MAX_LEN: Final[int] = 512
# Anchored: no leading whitespace (caller-stripped), exactly ``show ``/``dir ``
# followed by something.  Phase 13 hardening — was ``^\s*(show|dir)\s+`` which
# accepted leading whitespace and made the blocklist substring scan brittle.
_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^(show|dir)\s+", re.IGNORECASE)

# Substrings that MUST NEVER appear anywhere in the command string.
_BLOCKLIST: Final[tuple[str, ...]] = (
    ";",
    "&&",
    "||",
    "`",
    "$(",
    "conf t",
    "configure terminal",
    "| write",
    "write mem",
    "copy run start",
    "copy running-config startup-config",
)


def _reject(reason: str, command: object) -> tuple[bool, str]:
    _log.warning("CommandValidator rejected: %s value=%r", reason, command)
    return False, reason


class CommandValidator:
    """Stateless static class.  ``validate(cmd)`` is the only public entry."""

    @staticmethod
    def validate(command: object) -> tuple[bool, str]:
        """
        Validate a CLI command against the read-only allowlist + blocklist.

        Inputs
        ------
        command : the command string to send to a device.

        Outputs
        -------
        (True, "")            on accept.
        (False, reason)       on reject.

        Security
        --------
        Even when the prefix passes, the blocklist catches shell-escape
        attempts (e.g. ``show version; reload``).  Failing closed prevents
        an attacker who can post arbitrary command strings from triggering
        configuration changes or remote code execution on the device.
        """
        if not isinstance(command, str):
            return _reject("command must be a string", command)
        # Phase 13: NFKC-normalise to defeat unicode-homoglyph bypasses
        # (Cyrillic ѕhow, fullwidth ｓｈｏｗ, compatibility ligatures …).
        # Then strip leading/trailing whitespace and reject embedded
        # newlines / carriage returns which can split into multiple
        # device commands once the runner concatenates them.
        normalised = unicodedata.normalize("NFKC", command).strip()
        if "\n" in normalised or "\r" in normalised:
            return _reject("command contains embedded newline", command)
        if len(normalised) == 0:
            return _reject("command is empty", command)
        if len(normalised) > _MAX_LEN:
            return _reject(f"command exceeds max length ({_MAX_LEN})", command)
        if not _PREFIX_RE.match(normalised):
            return _reject("command must start with 'show' or 'dir'", command)
        lowered = normalised.lower()
        for needle in _BLOCKLIST:
            if needle in lowered:
                return _reject(f"command contains blocked substring: {needle!r}", command)
        return True, ""
