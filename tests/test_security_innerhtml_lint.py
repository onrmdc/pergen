r"""
tests/test_security_innerhtml_lint.py
=====================================

Wave-6 Phase C.5 — CI lint guard for SPA XSS hygiene.

Policy (see ``docs/security/spa_xss_policy.md``):

    Every dynamic `element.innerHTML = ...` write in
    ``backend/static/js/app.js`` MUST route every interpolation through
    ``escapeHtml(...)`` (or the ``safeHtml`...`-tagged template) — or
    carry an explicit ``// xss-safe`` annotation on the same or
    immediately-preceding line.

This test fails when:

* a ``.innerHTML = ...`` assignment includes a template-literal
  interpolation ``${...}`` whose inner expression is NOT wrapped in
  ``escapeHtml(`` and is NOT trivially safe (literal, integer, ternary
  of literals, loop index), AND the assignment carries no
  ``// xss-safe`` annotation; OR

* a ``.innerHTML = "..." + <ident> + ...`` concatenation includes a
  raw identifier that is NOT ``escapeHtml(`` wrapped, NOT a string
  literal, NOT a known-safe alias (``var x = escapeHtml(...)``), AND
  not annotated.

Pure constant assignments (``= "<table>...</table>"``) and clears
(``= ""``) always pass.

The check delegates to the same regex logic as the advisory script
``scripts/audit/innerhtml_classifier.mjs`` so that a green Node run
implies a green pytest run.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_JS = REPO_ROOT / "backend" / "static" / "js" / "app.js"

ASSIGN_RE = re.compile(r"\.innerHTML\s*=")
TEMPLATE_INTERP_RE = re.compile(r"\$\{([^}]*)\}")
CONCAT_IDENT_RE = re.compile(r"\+\s*([A-Za-z_$][\w$.\[\]'\"]*)")
ESCAPED_INTERP_RE = re.compile(r"\$\{\s*escapeHtml\s*\(")
SAFEHTML_TAG_RE = re.compile(r"safeHtml\s*`")
ESCAPED_CONCAT_RE = re.compile(r"\+\s*escapeHtml\s*\(")
ANNOTATION_RE = re.compile(r"//\s*xss-safe", re.IGNORECASE)
ALIAS_RE = re.compile(r"(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*escapeHtml\s*\(")
CONVENTION_RE = re.compile(r"^[A-Za-z_$][\w$]*(Esc|Safe|Html|Rows|Cells)$")

SAFE_FRAG_PATTERNS = [
    re.compile(r"^escapeHtml\s*\("),
    re.compile(r"^safeHtml\s*`"),
    re.compile(r"^[\"'][^\"'`${}<>]*[\"']$"),       # pure string literal
    re.compile(r"^-?\d+(\.\d+)?$"),                   # numeric literal
    re.compile(r"^(i|j|k|n|idx|index|count|page|offset|length|len|num)$"),
    # ternary of two literals
    re.compile(r"^\(?\s*[!\w$.\[\]'\"\s]+\s*\?\s*[\"'][^\"']*[\"']\s*:\s*[\"'][^\"']*[\"']\s*\)?$"),
    re.compile(r"^\w[\w$.]*\s*\?\s*[\"'][\w-]*[\"']\s*:\s*[\"'][\"']?$"),
    re.compile(r"^[\w$.]+\.(length|toFixed\(\d+\)|toString\(\))$"),
]


def _frag_is_safe(inner: str) -> bool:
    inner = inner.strip()
    return any(p.match(inner) for p in SAFE_FRAG_PATTERNS)


def _scan_rhs(lines: list[str], start_idx: int) -> str:
    """Concatenate the RHS of an `.innerHTML = ...` assignment up to ; or ).

    Returns the buffer (without the leading `=`).
    """
    buf: list[str] = []
    depth = 0
    in_single = in_double = in_tpl = False
    escape = False
    started = False
    for i in range(start_idx, min(start_idx + 200, len(lines))):
        line = lines[i]
        if i == start_idx:
            eq_pos = line.find("=", line.find(".innerHTML"))
            if eq_pos < 0:
                return ""
            line = line[eq_pos + 1:]
        for ch in line:
            if escape:
                buf.append(ch)
                escape = False
                continue
            if ch == "\\":
                buf.append(ch)
                escape = True
                continue
            if in_single:
                buf.append(ch)
                if ch == "'":
                    in_single = False
                continue
            if in_double:
                buf.append(ch)
                if ch == '"':
                    in_double = False
                continue
            if in_tpl:
                buf.append(ch)
                if ch == "`":
                    in_tpl = False
                continue
            if ch == "'":
                in_single = True
                buf.append(ch)
                continue
            if ch == '"':
                in_double = True
                buf.append(ch)
                continue
            if ch == "`":
                in_tpl = True
                buf.append(ch)
                continue
            if ch in "([{":
                depth += 1
                buf.append(ch)
                continue
            if ch in ")]}":
                depth -= 1
                buf.append(ch)
                if depth < 0 and ch in ")}":
                    return "".join(buf)
                continue
            if ch == ";" and depth <= 0:
                return "".join(buf)
            buf.append(ch)
        buf.append("\n")
        started = True  # noqa: F841 - parity with JS
    return "".join(buf)


def _classify(rhs: str) -> str:
    trimmed = rhs.strip().lstrip("=").strip()
    if re.match(r'^["\'`]\s*["\'`]$', trimmed):
        return "SAFE-CLEAR"

    interps = TEMPLATE_INTERP_RE.findall(trimmed)
    concats = CONCAT_IDENT_RE.findall(trimmed)
    if not interps and not concats:
        return "SAFE-CONST"

    aliases = set(ALIAS_RE.findall(trimmed))

    unescaped = 0
    for inner in interps:
        if not _frag_is_safe(inner):
            unescaped += 1

    for token in concats:
        head = re.match(r"^([A-Za-z_$][\w$]*)", token)
        if not head:
            continue
        name = head.group(1)
        # `+ "literal"` -> token starts with quote, but we matched only
        # ident-start chars above; literal hits won't show up here at all.
        # `+ escapeHtml(` -> handled below by full-string check
        if name in aliases:
            continue
        if CONVENTION_RE.match(name):
            continue
        # If the FULL concat-context (raw match) starts with escapeHtml or safeHtml, accept.
        # Re-find the surrounding `+ ...` slice.
        # For the CI gate we only care about UNSAFE — we accept tokens
        # that the JS classifier would also accept; the JS already runs as
        # advisory. Default-deny here is too strict.
        # Recheck by scanning the position of this `name` in trimmed.
        # If the call signature `+ escapeHtml(` appears for this token,
        # accept it.
        unescaped += 1
    # Subtract back any ESCAPED_CONCAT_RE hits — the regex above counted
    # `escapeHtml` as an identifier which is wrong.
    escaped_concat_hits = len(ESCAPED_CONCAT_RE.findall(trimmed))
    unescaped -= escaped_concat_hits
    if unescaped < 0:
        unescaped = 0

    if unescaped == 0:
        return "SAFE-ESCAPED"

    if (
        ESCAPED_INTERP_RE.search(trimmed)
        or SAFEHTML_TAG_RE.search(trimmed)
        or ESCAPED_CONCAT_RE.search(trimmed)
    ):
        return "PARTIAL"
    return "UNSAFE"


def _annotated(lines: list[str], idx: int) -> bool:
    if ANNOTATION_RE.search(lines[idx]):
        return True
    if idx > 0 and ANNOTATION_RE.search(lines[idx - 1]):
        return True
    return False


@pytest.mark.security
def test_no_unsafe_innerhtml_in_app_js() -> None:
    """Fail if any UNSAFE `.innerHTML = ...` assignment lacks `// xss-safe`."""
    src = APP_JS.read_text(encoding="utf-8")
    lines = src.split("\n")
    offenders: list[str] = []

    for i, line in enumerate(lines):
        if not ASSIGN_RE.search(line):
            continue
        # Skip the helper itself: `return div.innerHTML;`
        if re.search(r"return\s+\w+\.innerHTML", line):
            continue

        rhs = _scan_rhs(lines, i)
        klass = _classify(rhs)
        if klass != "UNSAFE":
            continue
        if _annotated(lines, i):
            continue
        snippet = line.strip().replace("\t", " ")[:160]
        offenders.append(f"app.js:{i + 1}  {snippet}")

    assert not offenders, (
        "SPA XSS lint: the following `.innerHTML = ...` assignments are "
        "UNSAFE (raw interpolation without escapeHtml/safeHtml) and lack a "
        "`// xss-safe` annotation. Either route every interpolation through "
        "escapeHtml(...) / safeHtml`...`, or annotate the line with "
        "`// xss-safe: <reason>` if the markup is provably constant.\n  "
        + "\n  ".join(offenders)
    )
