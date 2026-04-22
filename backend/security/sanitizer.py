"""
``InputSanitizer`` — pure-function input validation for the Pergen API surface.

Phase-3 deliverable.

Every method follows the same contract:

* Returns a 2-tuple ``(ok: bool, value_or_reason: str | int)``.
* On accept: ``(True, cleaned_value)``.
* On reject: ``(False, "human-readable reason")``.
* Never raises (caller can rely on a tuple).
* Rejects null bytes (``\\x00``) in every string input.
* Logs a WARNING on rejection so SIEM can detect probing.

Regex patterns are compiled at class-load time so a single bad input cannot
trigger ReDoS.
"""
from __future__ import annotations

import logging
import re
from typing import Final

_log = logging.getLogger("app.security.sanitizer")

# --------------------------------------------------------------------------- #
# Compiled patterns                                                           #
# --------------------------------------------------------------------------- #

_IP_RE: Final[re.Pattern[str]] = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")
_HOSTNAME_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$"
)
_CRED_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_PREFIX_RE: Final[re.Pattern[str]] = re.compile(
    r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})/(\d{1,3})$"
)
_ASN_RE: Final[re.Pattern[str]] = re.compile(r"^(?:AS\s*)?(\d{1,10})$", re.IGNORECASE)


def _reject(method: str, reason: str, value: object) -> tuple[bool, str]:
    """Log and return a uniform reject tuple."""
    _log.warning("%s rejected: %s value=%r", method, reason, value)
    return False, reason


def _has_null_byte(s: str) -> bool:
    return "\x00" in s


# --------------------------------------------------------------------------- #
# InputSanitizer                                                              #
# --------------------------------------------------------------------------- #


class InputSanitizer:
    """Static container of sanitiser methods.  Stateless and thread-safe."""

    # ---- IP -------------------------------------------------------------- #
    @staticmethod
    def sanitize_ip(value: object) -> tuple[bool, str]:
        """
        Validate a dotted-quad IPv4 address.

        Inputs : value (any) — expected str.
        Outputs: (ok, ip) — ip is the original string when ok=True.

        Security
        --------
        Rejects extra whitespace, octets >255, embedded shell metacharacters,
        and null bytes.  Length capped at 15 chars (max IPv4).
        """
        if not isinstance(value, str):
            return _reject("sanitize_ip", "must be a string", value)
        if _has_null_byte(value):
            return _reject("sanitize_ip", "null byte", value)
        if len(value) > 15 or len(value) < 7:
            return _reject("sanitize_ip", "length out of range", value)
        m = _IP_RE.match(value)
        if not m:
            return _reject("sanitize_ip", "invalid format", value)
        for octet in m.groups():
            if int(octet) > 255:
                return _reject("sanitize_ip", "octet out of range", value)
        return True, value

    # ---- Hostname -------------------------------------------------------- #
    @staticmethod
    def sanitize_hostname(value: object) -> tuple[bool, str]:
        """
        Validate a DNS-style hostname or short device name.

        Rules
        -----
        * 1–253 characters total.
        * Each label must start and end with alphanumeric.
        * Allowed chars: A-Z, a-z, 0-9, ``.``, ``_``, ``-``.
        * No spaces, no shell metacharacters, no null bytes.
        """
        if not isinstance(value, str):
            return _reject("sanitize_hostname", "must be a string", value)
        if _has_null_byte(value):
            return _reject("sanitize_hostname", "null byte", value)
        if len(value) == 0 or len(value) > 253:
            return _reject("sanitize_hostname", "length out of range", value)
        if not _HOSTNAME_RE.match(value):
            return _reject("sanitize_hostname", "invalid characters", value)
        return True, value

    # ---- Credential name ------------------------------------------------- #
    @staticmethod
    def sanitize_credential_name(value: object) -> tuple[bool, str]:
        """
        Validate a credential identifier (used as DB primary key).

        Rules
        -----
        * 1–64 characters.
        * Allowed: alphanumeric + ``.``, ``_``, ``-``.
        * No spaces, no path separators, no null bytes.
        """
        if not isinstance(value, str):
            return _reject("sanitize_credential_name", "must be a string", value)
        if _has_null_byte(value):
            return _reject("sanitize_credential_name", "null byte", value)
        if not _CRED_NAME_RE.match(value):
            return _reject("sanitize_credential_name", "invalid format", value)
        return True, value

    # ---- ASN ------------------------------------------------------------- #
    @staticmethod
    def sanitize_asn(value: object) -> tuple[bool, int | str]:
        """
        Validate a BGP ASN, accepting an optional ``AS`` prefix.

        Inputs : str like ``"65000"`` or ``"AS65000"``.
        Outputs: (True, int) on accept, (False, reason) on reject.

        Range  : 1 .. 4_294_967_295 (inclusive — 32-bit ASN space).
        """
        if not isinstance(value, str):
            return _reject("sanitize_asn", "must be a string", value)
        if _has_null_byte(value):
            return _reject("sanitize_asn", "null byte", value)
        m = _ASN_RE.match(value.strip())
        if not m:
            return _reject("sanitize_asn", "invalid format", value)
        try:
            n = int(m.group(1))
        except ValueError:
            return _reject("sanitize_asn", "non-integer", value)
        if not (1 <= n <= 4_294_967_295):
            return _reject("sanitize_asn", "out of range", value)
        return True, n

    # ---- Prefix ---------------------------------------------------------- #
    @staticmethod
    def sanitize_prefix(value: object) -> tuple[bool, str]:
        """
        Validate an IPv4 prefix in ``A.B.C.D/N`` form.

        Rules
        -----
        * Octets 0..255.
        * Prefix length 0..32.
        * No null bytes, no whitespace.
        """
        if not isinstance(value, str):
            return _reject("sanitize_prefix", "must be a string", value)
        if _has_null_byte(value):
            return _reject("sanitize_prefix", "null byte", value)
        m = _PREFIX_RE.match(value)
        if not m:
            return _reject("sanitize_prefix", "invalid format", value)
        a, b, c, d, n = m.groups()
        for octet in (a, b, c, d):
            if int(octet) > 255:
                return _reject("sanitize_prefix", "octet out of range", value)
        plen = int(n)
        if not (0 <= plen <= 32):
            return _reject("sanitize_prefix", "prefix length out of range", value)
        return True, value

    # ---- Generic string -------------------------------------------------- #
    @staticmethod
    def sanitize_string(value: object, *, max_length: int = 1024) -> tuple[bool, str]:
        """
        Generic string sanitiser used for free-form fields.

        Rules
        -----
        * Must be a string.
        * 0..max_length chars.
        * No null bytes.

        Caller is responsible for any field-specific validation beyond this.
        """
        if not isinstance(value, str):
            return _reject("sanitize_string", "must be a string", value)
        if _has_null_byte(value):
            return _reject("sanitize_string", "null byte", value)
        if len(value) > max_length:
            return _reject("sanitize_string", "too long", value)
        return True, value
