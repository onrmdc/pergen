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
 * HTML-escape a string so it is safe to interpolate into innerHTML.
 *
 * Uses the DOM's textContent → innerHTML round-trip to delegate to the
 * browser's authoritative escaping rules. Returns an empty string for
 * null/undefined.
 */
export function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  const div = (typeof document !== "undefined" ? document : null)?.createElement("div");
  if (!div) {
    // Fallback for environments without a DOM (rare — both jsdom and a
    // real browser provide one).
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
  div.textContent = String(s);
  return div.innerHTML;
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
