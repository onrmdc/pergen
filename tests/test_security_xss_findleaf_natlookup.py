"""H-02 — XSS via find-leaf and NAT lookup result tables.

`backend/static/js/app.js:4055, 4135, 4232, 4248` build result-table rows
via `innerHTML` from device-controlled values (Palo Alto NAT rule names,
firewall hostnames, inventory leaf names). A hostile firewall can plant
HTML in a rule name and execute JS in any operator's browser.

Audit reference: ``docs/security/audit_2026-04-22.md`` §3.1 H-02.

Static-source assertion against `app.js`: pin that the result-table
builders use `escapeHtml(...)` instead of raw concatenation. XFAIL until
the audit_innerhtml plan lands.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.security]

_APP_JS = Path(__file__).resolve().parent.parent / "backend" / "static" / "js" / "app.js"


def _read_app_js() -> str:
    return _APP_JS.read_text(encoding="utf-8")


@pytest.mark.xfail(
    reason="audit H-02 — find-leaf / NAT-lookup result tables interpolate without escape",
    strict=True,
)
def test_findleaf_result_row_uses_escapehtml() -> None:
    """The find-leaf result table assembly at app.js:~4055 should escape `r[1]`."""
    src = _read_app_js()
    # Find the suspect block (the audit references line ~4055; we use a
    # text marker rather than a line number so renames stay green).
    needle = 'resultBody.innerHTML = rows.map'
    if needle not in src:
        pytest.skip("find-leaf result-row builder not located by marker — refactored?")
    start = src.index(needle)
    window = src[start : start + 800]
    assert "escapeHtml(" in window, (
        "find-leaf result row builder concatenates row[1] into HTML without "
        "escapeHtml(); see docs/security/audit_2026-04-22.md H-02"
    )


@pytest.mark.xfail(
    reason="audit H-02 — NAT-lookup translated_ips list interpolates without escape",
    strict=True,
)
def test_nat_lookup_translated_ips_uses_escapehtml() -> None:
    """NAT translated IPs are rendered into innerHTML via map+join — must escape."""
    src = _read_app_js()
    # Common pattern is `translated_ips.map` followed by template-literal interpolation.
    if "translated_ips" not in src:
        pytest.skip("translated_ips reference not found in app.js — UI refactored")
    # Find any region that interpolates translated_ips and assert escapeHtml is nearby.
    pos = src.index("translated_ips")
    # Walk forward in 200-char chunks looking for innerHTML and escapeHtml proximity.
    window = src[pos : pos + 1500]
    assert "innerHTML" in window, (
        "translated_ips appears in app.js but no innerHTML write found in window — "
        "investigate"
    )
    assert "escapeHtml(" in window, (
        "translated_ips interpolated into innerHTML without escapeHtml(); "
        "see docs/security/audit_2026-04-22.md H-02"
    )
