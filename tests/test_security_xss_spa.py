"""
SPA lint-style XSS regression tests.

Each test reads a static SPA asset (``backend/static/js/app.js`` or
``backend/static/index.html``) as text and asserts a hardening rule
holds at the source level. A failure here indicates an unescaped
interpolation regressed in the SPA.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.security]

_ROOT = Path(__file__).resolve().parent.parent
_APP_JS = _ROOT / "backend" / "static" / "js" / "app.js"
_INDEX_HTML = _ROOT / "backend" / "static" / "index.html"


def _app_js_text() -> str:
    return _APP_JS.read_text(encoding="utf-8")


def _function_body(src: str, name: str) -> str:
    """Return the body of a top-level ``function name(...) { ... }`` block.

    Brace-balanced scan starting at the function's opening ``{``.
    """
    m = re.search(rf"function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{", src)
    assert m is not None, f"function {name!r} not found in app.js"
    start = m.end() - 1  # the opening "{"
    depth = 0
    for i in range(start, len(src)):
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    raise AssertionError(f"unbalanced braces while scanning {name!r}")


def test_app_js_event_popup_renderer_uses_escapeHtml():
    body = _function_body(_app_js_text(), "renderEventPopupList")
    assert "escapeHtml(e.hostname" in body, (
        "renderEventPopupList must escape e.hostname before HTML interpolation"
    )
    assert "escapeHtml(e.message" in body, (
        "renderEventPopupList must escape e.message before HTML interpolation"
    )


def test_app_js_router_devices_listing_escapes_hostname_and_ip():
    src = _app_js_text()
    # Locate the routerDevicesCache.map(...) block and capture the inline
    # callback body (the line that builds the <div class="device-row"> string).
    m = re.search(
        r"routerDevicesCache\.map\(function\([^)]*\)\s*\{(?P<body>.*?)\}\)\.join",
        src,
        re.DOTALL,
    )
    assert m is not None, "routerDevicesCache.map block not found"
    body = m.group("body")
    # Every d.hostname / d.ip interpolation in this block must be wrapped in
    # escapeHtml(...). We do that by scanning every occurrence and checking
    # the immediately preceding token.
    for field in ("d.hostname", "d.ip"):
        for occ in re.finditer(re.escape(field), body):
            head = body[max(0, occ.start() - 32) : occ.start()]
            assert "escapeHtml(" in head, (
                f"{field} interpolation in routerDevicesCache.map "
                f"is not wrapped in escapeHtml(...): context={head!r}"
            )


def test_app_js_bgp_hijack_banner_uses_textContent_or_escape():
    src = _app_js_text()
    idx = src.find("HIJACK DETECTED")
    assert idx != -1, "HIJACK DETECTED banner not found in app.js"
    # Inspect a window of source around the banner construction.
    window = src[max(0, idx - 600) : idx + 600]
    uses_text_content = ".textContent" in window or "createTextNode" in window
    # Fallback: every variable interpolation in the window is wrapped in
    # escapeHtml(...) — accept if there are no bare ``+ var +`` HTML
    # concatenations (i.e. no interpolations at all means trivially safe).
    has_unescaped_concat = False
    for m in re.finditer(r"\+\s*([A-Za-z_$][\w$]*)", window):
        ident = m.group(1)
        if ident in {"escapeHtml", "encodeURIComponent", "String"}:
            continue
        head = window[max(0, m.start() - 16) : m.start()]
        if "escapeHtml(" in head:
            continue
        has_unescaped_concat = True
        break
    assert uses_text_content or not has_unescaped_concat, (
        "HIJACK banner construction must use textContent/createTextNode "
        "or wrap every interpolated variable in escapeHtml(...)"
    )


def test_app_js_no_inline_event_handlers_in_index_html():
    html = _INDEX_HTML.read_text(encoding="utf-8")
    matches = re.findall(r"\son[a-zA-Z]+\s*=\s*\"[^\"]*\"", html)
    assert not matches, (
        f"index.html must not contain inline event handlers; found: {matches[:5]}"
    )
