"""W4-M-04 — Log-injection via `notepad.save` `claimed_user` field.

Wave-4 audit §3.2 W4-M-04. ``data.get("user")`` is unvalidated
(no length cap, no control-char strip) and lands inside an
``_audit.info("...claimed_user=%s...", user, ...)`` call.

In JSON-mode logs (``LOG_FORMAT=json``, the production default),
``json.dumps`` escapes ``\\n`` to ``\\\\n`` inside the ``msg`` field
— JSON mode is safe.

In text-mode logs (``LOG_FORMAT=text``, default for development on
a TTY), the ``ColourFormatter`` writes ``record.getMessage()`` via
string concatenation with no escaping. A ``\\n`` in ``user`` then
splits the audit line into two records, the second indistinguishable
from a real audit event.

Marked xfail until the route layer strips control characters and
caps the field length.
"""

from __future__ import annotations

import logging

import pytest

pytestmark = [pytest.mark.security]


def test_notepad_save_user_field_does_not_inject_log_lines(
    client, caplog
) -> None:
    """W4-M-04 — \\n in user must not split the audit log entry."""
    caplog.set_level(logging.INFO, logger="app.audit")
    payload = {
        "content": "x",
        "user": "alice\nINFO audit credential.set actor=root name=admin",
    }
    r = client.put("/api/notepad", json=payload)
    assert r.status_code in (200, 500)

    audit_records = [r for r in caplog.records if r.name == "app.audit"]
    # Forge would split into 2 records inside text-mode logs; guard says 1.
    assert len(audit_records) == 1, (
        f"audit log entry split by \\n in user field — see W4-M-04 "
        f"(got {len(audit_records)} records)"
    )
    msg = audit_records[0].getMessage()
    # The injected payload may APPEAR in the message (concatenated to
    # the safe value) but must not contain any newline / carriage-return /
    # tab control character that could split the line in any downstream
    # log handler. JSON mode escapes; text mode now passes through the
    # sanitised value.
    for ch in ("\n", "\r", "\t"):
        assert ch not in msg, (
            f"audit log entry contains control char {ch!r} — see W4-M-04: "
            f"{msg!r}"
        )
