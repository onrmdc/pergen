"""Wave-6 Phase F: SPA fetch wrapper static-grep lint.

Asserts that ``backend/static/js/app.js`` exposes a single
``pergenFetch`` wrapper and that EXACTLY ONE raw ``fetch(``
call survives in the file (the wrapper's own implementation).

This is a static-grep lint, not a runtime test, so it has no
dependency on jsdom / Vitest / Playwright. Adding a new raw
``fetch(API + ...)`` call site without funneling it through
``pergenFetch`` will fail this test and remind the author that
the SPA's auth path expects every backend call to flow through
the wrapper (CSRF header, 401 redirect, session cookie).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.security]

_APP_JS = Path(__file__).resolve().parent.parent / "backend" / "static" / "js" / "app.js"


def _source() -> str:
    return _APP_JS.read_text(encoding="utf-8")


def test_app_js_exists() -> None:
    """Smoke: the SPA file exists at the expected path."""
    assert _APP_JS.is_file(), f"{_APP_JS} missing"


def test_pergen_fetch_wrapper_is_defined() -> None:
    """The wrapper symbol must exist and be exposed on `window`."""
    src = _source()
    assert "function pergenFetch(" in src, "pergenFetch wrapper missing"
    assert "window.pergenFetch = pergenFetch" in src, (
        "pergenFetch must be exposed on window for ad-hoc operator console use "
        "+ static-grep audit"
    )


def test_only_one_raw_fetch_call_survives() -> None:
    """Only the wrapper itself may call `fetch(` directly.

    Every other API call site must use `pergenFetch(...)`. A new
    `fetch(...)` outside the wrapper is treated as a regression so the
    CSRF header injection and 401 redirect logic remain centralised.
    """
    src = _source()
    matches = re.findall(r"\bfetch\(", src)
    assert len(matches) == 1, (
        f"Expected exactly one raw fetch( call (the pergenFetch wrapper), "
        f"found {len(matches)}. Convert new sites to pergenFetch(...). "
        f"Lines:\n"
        + "\n".join(
            f"  {i + 1}: {line}"
            for i, line in enumerate(src.splitlines())
            if "fetch(" in line and "pergenFetch(" not in line
        )
    )


def test_no_fetch_with_api_prefix_survives() -> None:
    """A `fetch(API + ...)` site should never appear — it indicates a missed conversion."""
    src = _source()
    matches = re.findall(r"\bfetch\(\s*API\s*\+", src)
    assert not matches, (
        f"Found {len(matches)} `fetch(API + ...)` site(s); convert them to "
        f"`pergenFetch(\"...\")` (the wrapper prepends API itself)."
    )


def test_pergen_fetch_call_sites_present() -> None:
    """Sanity floor: at least 50 pergenFetch sites should exist post-conversion."""
    src = _source()
    sites = re.findall(r"\bpergenFetch\(", src)
    assert len(sites) >= 50, (
        f"Only {len(sites)} pergenFetch call sites found; expected ≥50 "
        f"after the F.1 mass conversion"
    )
