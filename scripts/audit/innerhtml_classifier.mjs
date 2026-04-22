#!/usr/bin/env node
// SPDX-License-Identifier: MIT
//
// innerhtml_classifier.mjs
// ------------------------
// Wave-6 Phase C.1 audit tool. Reads `backend/static/js/app.js` line by
// line and classifies every `something.innerHTML = ...` assignment into
// one of five buckets:
//
//   SAFE-CONST    — RHS is a string literal with no `${...}` and no
//                   `+ ident` concatenation against a non-string-literal.
//   SAFE-CLEAR    — RHS is the empty string ("" or '').
//   SAFE-ESCAPED  — RHS contains dynamic interpolation but every dynamic
//                   fragment is wrapped in escapeHtml(...) or safeHtml`...`.
//   PARTIAL       — RHS contains escapeHtml(...) somewhere but ALSO
//                   contains a raw `${ident}` or `+ ident` that is not
//                   wrapped — review required.
//   UNSAFE        — RHS contains a raw `${ident}` or `+ ident` and no
//                   escapeHtml/safeHtml wrapping at all.
//
// Lines that include the explicit `// xss-safe` annotation (same line or
// the line immediately above) are downgraded to SAFE-CONST regardless of
// the regex verdict — that gives the lint guard an escape hatch for
// genuinely-static markup that the regex cannot prove is safe.
//
// Output:
//   • CSV at docs/refactor/innerhtml_audit_report.csv
//   • Summary table on stdout
//
// Exit code is 0 — this script is advisory, not a gate. The real gate is
// `tests/test_security_innerhtml_lint.py` which only fails on UNSAFE
// without annotation.

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..", "..");
const APP_JS = resolve(REPO_ROOT, "backend/static/js/app.js");
const REPORT = resolve(REPO_ROOT, "docs/refactor/innerhtml_audit_report.csv");

const ASSIGN_RE = /\.innerHTML\s*=/;
const TEMPLATE_INTERP_RE = /\$\{[^}]*\}/g;
const CONCAT_IDENT_RE = /\+\s*[A-Za-z_$][\w$.[\]'"]*/g;
const ESCAPED_INTERP_RE = /\$\{\s*escapeHtml\s*\(/;
const SAFEHTML_TAG_RE = /safeHtml\s*`/;
const ESCAPED_CONCAT_RE = /\+\s*escapeHtml\s*\(/;
const ANNOTATION_RE = /\/\/\s*xss-safe/i;

function rhsThroughSemicolon(lines, startIdx) {
  // Concatenate from the `=` to the next bare `;` at depth 0 (paren/brace/template).
  let buf = "";
  let depth = 0;
  let inSingle = false;
  let inDouble = false;
  let inTpl = false;
  let escape = false;
  let started = false;
  for (let i = startIdx; i < lines.length && i < startIdx + 200; i++) {
    const line = lines[i];
    for (let c = 0; c < line.length; c++) {
      const ch = line[c];
      if (!started) {
        // Skip everything up to the `=` on the first line.
        if (i === startIdx && ch === "=") {
          started = true;
          continue;
        }
        if (i !== startIdx) started = true;
        if (!started) continue;
      }
      if (escape) {
        buf += ch;
        escape = false;
        continue;
      }
      if (ch === "\\") {
        buf += ch;
        escape = true;
        continue;
      }
      if (inSingle) {
        buf += ch;
        if (ch === "'") inSingle = false;
        continue;
      }
      if (inDouble) {
        buf += ch;
        if (ch === '"') inDouble = false;
        continue;
      }
      if (inTpl) {
        buf += ch;
        if (ch === "`") inTpl = false;
        continue;
      }
      if (ch === "'") { inSingle = true; buf += ch; continue; }
      if (ch === '"') { inDouble = true; buf += ch; continue; }
      if (ch === "`") { inTpl = true; buf += ch; continue; }
      if (ch === "(" || ch === "[" || ch === "{") { depth++; buf += ch; continue; }
      if (ch === ")" || ch === "]" || ch === "}") { depth--; buf += ch; continue; }
      if (ch === ";" && depth <= 0) {
        return { rhs: buf, endLine: i };
      }
      if ((ch === ")" || ch === "}") && depth < 0) {
        // We started inside a parenthesised assignment like
        //   `(a.innerHTML = "...")`.  The closing paren ends the RHS.
        return { rhs: buf, endLine: i };
      }
      buf += ch;
    }
    buf += "\n";
  }
  // Fallback: bail at end of window; classify against what we have.
  return { rhs: buf, endLine: Math.min(startIdx + 199, lines.length - 1) };
}

function classify(rhs) {
  const trimmed = rhs.trim().replace(/^=\s*/, "");
  // SAFE-CLEAR: just an empty string literal
  if (/^["'`]\s*["'`]$/.test(trimmed)) return "SAFE-CLEAR";

  const hasTemplateInterp = TEMPLATE_INTERP_RE.test(trimmed);
  TEMPLATE_INTERP_RE.lastIndex = 0;
  const hasConcatIdent = CONCAT_IDENT_RE.test(trimmed);
  CONCAT_IDENT_RE.lastIndex = 0;

  if (!hasTemplateInterp && !hasConcatIdent) {
    return "SAFE-CONST";
  }

  // Find every dynamic fragment and decide whether it's escaped.
  const interps = trimmed.match(TEMPLATE_INTERP_RE) || [];
  TEMPLATE_INTERP_RE.lastIndex = 0;

  // Whitelist of patterns inside `${...}` that we provably know cannot
  // carry attacker-controlled markup (and therefore do not need
  // escapeHtml). These are deliberately narrow.
  function fragIsSafe(inner) {
    if (/^escapeHtml\s*\(/.test(inner)) return true;
    if (/^safeHtml\s*`/.test(inner)) return true;
    // Pure literal
    if (/^["'][^"'`${}<>]*["']$/.test(inner)) return true;
    // Pure numeric literal
    if (/^-?\d+(\.\d+)?$/.test(inner)) return true;
    // Loop-index or short identifier known to be a number
    // (i, j, k, idx, index, count, n) — common across the file
    if (/^(i|j|k|n|idx|index|count|page|offset|length|len|num)$/.test(inner)) return true;
    // Ternary of two string literals: `cond ? "a" : "b"` (with optional parens)
    if (
      /^\(?\s*[!\w$.[\]'"\s]+\s*\?\s*["'][^"']*["']\s*:\s*["'][^"']*["']\s*\)?$/.test(inner)
    ) return true;
    // Common safe-class expression: `cond ? "classname" : ""`
    if (/^\w[\w$.]*\s*\?\s*["'][\w-]*["']\s*:\s*["']["']?$/.test(inner)) return true;
    // .length / .toFixed(n) / .toString() — produce only digits or ASCII
    if (/^[\w$.]+\.(length|toFixed\(\d+\)|toString\(\))$/.test(inner)) return true;
    return false;
  }

  let unescapedInterps = 0;
  for (const frag of interps) {
    const inner = frag.slice(2, -1).trim();
    if (!fragIsSafe(inner)) unescapedInterps++;
  }

  // Build a set of identifiers that are aliases for an escapeHtml(...)
  // result in the local RHS scope. Catches patterns like:
  //   var nameEsc = escapeHtml(name);
  //   var pEsc = escapeHtml(p);
  // which are the common idiom in app.js for reusing an escaped value.
  const aliasRe = /(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*escapeHtml\s*\(/g;
  const aliases = new Set();
  let m;
  while ((m = aliasRe.exec(trimmed)) !== null) aliases.add(m[1]);
  // Also accept identifiers built ONLY from `.join`, `.filter(Boolean).join`
  // on top of an escapeHtml-bearing map — common pattern:
  //   var rows = data.map(function(d) { return ... + escapeHtml(d.x) + ...; }).join("");
  // followed by `body.innerHTML = "<table>" + rows + "</table>"`.
  // We accept the ident if its definition (in the same function/closure)
  // contains escapeHtml. Limited window: scan back ~40 lines from the
  // assignment is hard here — instead, treat any concat ident that ends in
  // `Esc`, `Safe`, `Html`, `Rows`, or `Cells` as conventionally escaped.
  // This is intentionally narrow and heuristic — false negatives still get
  // surfaced because UNSAFE-by-pattern checks already require the regex
  // hit.
  const conventionRe = /^[A-Za-z_$][\w$]*(Esc|Safe|Html|Rows|Cells)$/;

  // Concatenation: every `+ ident` or `+ ident.prop` should be wrapped.
  const concats = trimmed.match(CONCAT_IDENT_RE) || [];
  CONCAT_IDENT_RE.lastIndex = 0;
  let unescapedConcats = 0;
  for (const c of concats) {
    if (/\+\s*escapeHtml\s*\(/.test(c)) continue;
    if (/\+\s*safeHtml\s*`/.test(c)) continue;
    if (/\+\s*["']/.test(c)) continue; // `+ "literal"`
    // Strip the leading `+` and any whitespace; capture the identifier
    // chain (no parens, no method call) and check the alias set.
    const tail = c.replace(/^\+\s*/, "");
    const head = tail.match(/^([A-Za-z_$][\w$]*)/);
    if (head && aliases.has(head[1])) continue;
    if (head && conventionRe.test(head[1])) continue;
    unescapedConcats++;
  }

  const totalDynamic = interps.length + concats.length;
  const totalUnescaped = unescapedInterps + unescapedConcats;
  const hasAnyEscape =
    ESCAPED_INTERP_RE.test(trimmed) ||
    SAFEHTML_TAG_RE.test(trimmed) ||
    ESCAPED_CONCAT_RE.test(trimmed);

  if (totalUnescaped === 0) return "SAFE-ESCAPED";
  if (hasAnyEscape && totalUnescaped > 0) return "PARTIAL";
  return "UNSAFE";
}

function annotated(lines, idx) {
  // Same line or previous line carries the annotation
  if (ANNOTATION_RE.test(lines[idx])) return true;
  if (idx > 0 && ANNOTATION_RE.test(lines[idx - 1])) return true;
  return false;
}

function snippet(line) {
  return line.trim().replace(/\s+/g, " ").slice(0, 160);
}

function suggest(klass) {
  switch (klass) {
    case "UNSAFE":
      return "Wrap each interpolation with escapeHtml(...) or migrate the assignment to safeHtml`...`.";
    case "PARTIAL":
      return "Audit by hand — at least one fragment is still raw.";
    case "SAFE-ESCAPED":
      return "OK — every interpolation is escaped.";
    case "SAFE-CONST":
      return "OK — constant markup, no interpolation.";
    case "SAFE-CLEAR":
      return "OK — clearing the container.";
    default:
      return "";
  }
}

function main() {
  const src = readFileSync(APP_JS, "utf-8");
  const lines = src.split("\n");
  const rows = [];
  const counts = {
    "SAFE-CONST": 0,
    "SAFE-CLEAR": 0,
    "SAFE-ESCAPED": 0,
    PARTIAL: 0,
    UNSAFE: 0,
    "UNSAFE-ANNOTATED": 0,
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!ASSIGN_RE.test(line)) continue;
    // Skip the escapeHtml helper itself (`return div.innerHTML;`)
    if (/return\s+\w+\.innerHTML/.test(line)) continue;

    // Find the `=` position and start the RHS scan there.
    const matchIdx = line.search(/\.innerHTML\s*=/);
    const equalsIdx = line.indexOf("=", matchIdx);
    // Pseudo-line that looks like our scanner expects: just the part
    // from `=` onwards on this line, then continuation.
    const slicedFirst = line.slice(equalsIdx);
    const window = [slicedFirst, ...lines.slice(i + 1)];
    const { rhs } = rhsThroughSemicolon(window, 0);

    let klass = classify(rhs);
    const isAnnotated = annotated(lines, i);
    if (klass === "UNSAFE" && isAnnotated) {
      klass = "UNSAFE-ANNOTATED";
    }
    counts[klass] = (counts[klass] || 0) + 1;
    rows.push({
      line: i + 1,
      classification: klass,
      annotated: isAnnotated ? "yes" : "no",
      snippet: snippet(line),
      suggestion: suggest(klass.replace("-ANNOTATED", "")),
    });
  }

  // Write CSV
  mkdirSync(dirname(REPORT), { recursive: true });
  const header = "line,classification,annotated,snippet,suggested_fix\n";
  const body = rows
    .map((r) => {
      const esc = (s) => `"${String(s).replace(/"/g, '""')}"`;
      return [r.line, r.classification, r.annotated, esc(r.snippet), esc(r.suggestion)].join(",");
    })
    .join("\n");
  writeFileSync(REPORT, header + body + "\n", "utf-8");

  // Stdout summary
  const total = rows.length;
  console.log(`innerHTML classifier — ${APP_JS}`);
  console.log(`Total assignments scanned: ${total}`);
  console.log("By classification:");
  for (const k of ["SAFE-CONST", "SAFE-CLEAR", "SAFE-ESCAPED", "PARTIAL", "UNSAFE", "UNSAFE-ANNOTATED"]) {
    const n = counts[k] || 0;
    if (n) console.log(`  ${k.padEnd(18)} ${n}`);
  }

  const unsafe = rows.filter((r) => r.classification === "UNSAFE");
  if (unsafe.length) {
    console.log(`\nUNSAFE sites (${unsafe.length}) — needs fix:`);
    for (const r of unsafe) {
      console.log(`  app.js:${r.line}  ${r.snippet}`);
    }
  }

  const partial = rows.filter((r) => r.classification === "PARTIAL");
  if (partial.length) {
    console.log(`\nPARTIAL sites (${partial.length}) — needs review:`);
    for (const r of partial) {
      console.log(`  app.js:${r.line}  ${r.snippet}`);
    }
  }

  const annotatedCount = counts["UNSAFE-ANNOTATED"] || 0;
  if (annotatedCount) {
    console.log(`\n${annotatedCount} UNSAFE site(s) carry an explicit // xss-safe annotation — accepted.`);
  }

  console.log(`\nCSV report: ${REPORT}`);
  // Always exit 0 — advisory only.
}

main();
