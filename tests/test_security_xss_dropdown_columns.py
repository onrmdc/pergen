"""H-01 — XSS via inventory `fabric/site/hall/role` columns.

The SPA writes inventory dropdown values into `<option>` HTML via raw
template literals (`backend/static/js/app.js:273, 284, 297, 311`). Combined
with H-05 (open inventory writes in dev/test), an attacker can plant a
payload that executes in any operator's browser.

Audit reference: ``docs/security/audit_2026-04-22.md`` §3.1 H-01.

Strategy: this is a static-source assertion against `app.js` (pin the use
of `escapeHtml(...)` inside the relevant builder functions). XFAIL until
the audit_innerhtml plan lands.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.security]

_APP_JS = Path(__file__).resolve().parent.parent / "backend" / "static" / "js" / "app.js"


def _read_app_js() -> str:
    return _APP_JS.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "builder_name",
    ["loadFabrics", "loadSites", "loadHalls", "loadRoles"],
)
def test_dropdown_builder_escapes_attacker_controlled_value(builder_name: str) -> None:
    """Each dropdown loader must wrap its iterator value in `escapeHtml(...)`.

    Static-source assertion: locate the function body and confirm an
    `escapeHtml(` call appears within ~20 lines of `innerHTML`.
    """
    src = _read_app_js()
    needle = f"function {builder_name}"
    # Some functions might be written `const X = (` — try both.
    if needle not in src:
        needle = f"{builder_name} = "
    assert needle in src, f"could not find {builder_name} in app.js"

    start = src.index(needle)
    # Look at a 1.5KB window — generous enough to span the function body.
    window = src[start : start + 1500]

    assert "innerHTML" in window, (
        f"{builder_name} doesn't appear to use innerHTML — investigate test"
    )
    assert "escapeHtml(" in window, (
        f"{builder_name}: interpolation into innerHTML without escapeHtml(); "
        f"see docs/security/audit_2026-04-22.md H-01"
    )


def test_escapeHtml_helper_exists() -> None:
    """Sanity guard: the helper everyone should call must exist."""
    src = _read_app_js()
    assert "function escapeHtml" in src or "escapeHtml = " in src
