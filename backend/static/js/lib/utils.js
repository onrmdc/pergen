// SPDX-License-Identifier: MIT
//
// Pure helpers shared by the SPA. Imported by both ``app.js`` (via a
// `<script>` tag — see below) and the Vitest unit tests under
// ``tests/frontend/unit/``.
//
// IMPORTANT: this file MUST stay framework-free and side-effect-free so
// the same source can be loaded by a browser (no module bundler in
// production) and by Vitest's jsdom environment for tests.
//
// To wire these helpers into ``app.js`` add `<script src="/static/js/lib/utils.js"></script>`
// before the inline IIFE in ``index.html`` and remove the duplicate
// definitions from ``app.js``. The current refactor commit only ships the
// helper file + tests; the cut-over to consume it from app.js is a
// separate, low-risk change captured in the docs.

/**
 * HTML-escape a string so it is safe to interpolate into innerHTML in
 * BOTH text-content and attribute-value contexts.
 *
 * Wave-6 Phase C update: previously this function used the DOM's
 * `textContent → innerHTML` round-trip. That delegation is incorrect
 * for attribute contexts because the browser only encodes `<`, `>`,
 * `&` on the way out — `"` and `'` are emitted verbatim. A value such
 * as `a"b` interpolated into `data-x="${escapeHtml(v)}"` would break
 * out of the attribute. The full manual replacement closes that hole
 * and keeps text-content safety. Returns an empty string for
 * null/undefined.
 */
export function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Tagged-template helper that auto-escapes every interpolation through
 * {@link escapeHtml}. Use this when building markup with multiple
 * dynamic fragments — it removes the need to remember `escapeHtml(...)`
 * around each `${...}` and is safe in both text-content and attribute
 * contexts (because escapeHtml encodes quotes too).
 *
 * @example
 *   const html = safeHtml`<tr><td>${row.name}</td><td>${row.ip}</td></tr>`;
 *   tbody.innerHTML = html;
 */
export function safeHtml(strings, ...values) {
  let out = strings[0];
  for (let i = 0; i < values.length; i++) {
    out += escapeHtml(values[i]) + strings[i + 1];
  }
  return out;
}

/**
 * Format an integer byte count as a short human-readable string (KB/MB/GB).
 * Returns "-" for null/undefined/invalid input. Note that Number(null) === 0
 * in JS, so we explicitly screen for null/undefined first.
 */
export function formatBytes(n) {
  if (n === null || n === undefined) return "-";
  const v = Number(n);
  if (!Number.isFinite(v) || v < 0) return "-";
  if (v < 1024) return `${v} B`;
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
  if (v < 1024 * 1024 * 1024) return `${(v / 1024 / 1024).toFixed(1)} MB`;
  return `${(v / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

/**
 * Strict IPv4 dotted-quad validator. No CIDR, no leading zeros, no
 * trailing whitespace.
 */
export function isValidIPv4(s) {
  if (typeof s !== "string") return false;
  const m = s.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (!m) return false;
  return m.slice(1).every((part) => {
    const n = Number(part);
    return n >= 0 && n <= 255 && String(n) === part;
  });
}

/**
 * Compute the active hash route name from a window.location.hash string.
 * Strips the leading '#' and returns the empty string for the home page.
 */
export function parseHash(hash) {
  if (typeof hash !== "string") return "";
  return hash.replace(/^#/, "").trim();
}
