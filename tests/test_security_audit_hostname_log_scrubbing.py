"""Audit GAP #10 (M-12) — caller-supplied hostnames in audit logs.

Pattern: blueprints (``inventory_bp``, ``transceiver_bp``) interpolate
operator-supplied ``hostname`` into structured audit lines:

    _audit.info("audit inventory.delete actor=%s hostname=%s ip=%s", ...)

If a caller smuggles ``\\r\\n`` into the hostname, log post-processors
(SIEM, journald, plain-text grep pipelines) see a *forged* extra audit
line — classic log injection.

Two layers of defence are possible:
  1. Reject the payload at the ``InputSanitizer.sanitize_hostname``
     boundary (current behaviour for inventory mutations) — no audit
     line is ever emitted.
  2. Scrub control bytes inside the audit helper itself so even a
     bypass cannot smuggle a newline.

Audit reference: ``backend/blueprints/inventory_bp.py`` lines 172-206 +
``docs/security/audit_2026-04-22.md`` M-12.

This module pins the *outcome* (no literal newline in any audit line
that mentions a hostname-shaped key) regardless of which layer
provides the defence. If the M-12 hardening adds layer 2, these tests
keep working; if only layer 1 is in place (today), the tests still
pass because the malicious request is rejected pre-audit.
"""
from __future__ import annotations

import logging

import pytest

pytestmark = [pytest.mark.security]


def _attach_caplog(caplog) -> None:
    """Re-attach pytest's caplog handler — see test_security_login_username_enum.

    ``LoggingConfig.configure`` strips every root handler when the app is
    built; pytest's caplog handler is collateral damage.
    """
    root = logging.getLogger()
    if caplog.handler not in root.handlers:
        root.addHandler(caplog.handler)


@pytest.mark.parametrize(
    "evil_hostname",
    [
        "evil\r\nFAKE LINE actor=root",
        "evil\nFORGED audit log line",
        "leg\r\nit",
        "host\x00null",
    ],
)
def test_inventory_add_audit_line_has_no_literal_newline(
    flask_app, client, caplog, evil_hostname: str
) -> None:
    """A POST with a CRLF-laden hostname must not produce a multi-line audit entry.

    Two acceptable outcomes:
      * 400 from the sanitizer → no audit line emitted at all.
      * 200 from the route AND the audit line has no embedded ``\\n``/``\\r``.
    """
    _attach_caplog(caplog)
    caplog.set_level(logging.DEBUG, logger="app.audit")

    r = client.post(
        "/api/inventory/device",
        json={"hostname": evil_hostname, "ip": "10.99.0.99"},
    )
    # Route may accept or reject; we only forbid the hostname showing up
    # verbatim in any audit line.
    audit_lines = [
        rec.getMessage()
        for rec in caplog.records
        if rec.name == "app.audit"
    ]
    for line in audit_lines:
        assert "\n" not in line, (
            f"audit line {line!r} contains a literal newline — log "
            f"injection vector (M-12)"
        )
        assert "\r" not in line, (
            f"audit line {line!r} contains a literal carriage return — "
            f"log injection vector (M-12)"
        )
        assert "\x00" not in line, (
            f"audit line {line!r} contains a null byte — log injection "
            f"vector (M-12)"
        )

    # Belt-and-suspenders: regardless of whether the route accepted the
    # request, status must be 200 (sanitised) or 400 (rejected) — never
    # 500. A 500 means the malformed hostname blew up downstream code.
    assert r.status_code in (200, 400), (
        f"unexpected status {r.status_code} for hostname={evil_hostname!r}; "
        f"body={r.get_data(as_text=True)!r}"
    )


def test_inventory_delete_audit_line_has_no_literal_newline(
    flask_app, client, caplog
) -> None:
    """Same contract for the DELETE path — query-arg hostname.

    DELETE accepts ``hostname`` via the query string, which historically
    was not run through the same sanitiser as the JSON body. If gap #10
    is unfixed this is the easier route to exploit.
    """
    _attach_caplog(caplog)
    caplog.set_level(logging.DEBUG, logger="app.audit")

    evil = "evil\r\nFAKE actor=root ip=1.2.3.4"
    r = client.delete(f"/api/inventory/device?hostname={evil}")
    # Per the audit contract, the route MAY 404 (device not found), 400
    # (sanitiser rejection), or 200 (deleted). We do not constrain that
    # — only the audit-line shape.
    audit_lines = [
        rec.getMessage()
        for rec in caplog.records
        if rec.name == "app.audit"
    ]
    for line in audit_lines:
        assert "\n" not in line, (
            f"DELETE audit line {line!r} contains literal newline — "
            f"log injection vector (M-12)"
        )
        assert "\r" not in line, (
            f"DELETE audit line {line!r} contains literal CR — "
            f"log injection vector (M-12)"
        )
    # A 500 here would indicate the malformed hostname crashed the route.
    assert r.status_code != 500, (
        f"DELETE with control-byte hostname must not 500; got "
        f"{r.status_code} body={r.get_data(as_text=True)!r}"
    )


def test_audit_logger_records_present_for_legit_inventory_add(
    flask_app, client, caplog
) -> None:
    """Sanity / counter-test: a legitimate add still produces an audit line.

    This guards against a future regression where the audit logger is
    accidentally muted (which would make the tests above vacuously
    pass).
    """
    _attach_caplog(caplog)
    caplog.set_level(logging.DEBUG, logger="app.audit")

    r = client.post(
        "/api/inventory/device",
        json={"hostname": "legit-host-01", "ip": "10.99.0.42"},
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    audit_lines = [
        rec.getMessage()
        for rec in caplog.records
        if rec.name == "app.audit" and "inventory.add" in rec.getMessage()
    ]
    assert audit_lines, (
        "expected an inventory.add audit line for a legit POST; got none. "
        "If this fails, the test infrastructure (caplog re-attach) is "
        "broken — fix the harness, not the assertion."
    )
    # And the legit hostname must appear verbatim — no over-zealous scrubbing.
    assert any("legit-host-01" in line for line in audit_lines)
