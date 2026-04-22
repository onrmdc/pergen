// SPDX-License-Identifier: MIT
//
// Pure subnet/CIDR math helpers extracted from the SPA IIFE so they
// are independently testable under Vitest's jsdom environment.
//
// Wave-3 Phase 13: extends the wave-2 utils.js scaffold (escapeHtml,
// formatBytes, isValidIPv4, parseHash) with the subnet calculator's
// 6 pure helpers. The IIFE in app.js still defines its own copies for
// now — a follow-up PR can switch the IIFE to a single
// `<script src="/static/js/lib/subnet.js"></script>` import and remove
// the duplication.

/**
 * Convert a dotted-quad IPv4 string to a 32-bit unsigned int.
 * Returns null for malformed input.
 */
export function ipToLong(ip) {
  const parts = String(ip ?? "").trim().split(".");
  if (parts.length !== 4) return null;
  let n = 0;
  for (let i = 0; i < 4; i++) {
    const p = parseInt(parts[i], 10);
    if (Number.isNaN(p) || p < 0 || p > 255 || String(p) !== parts[i]) return null;
    n = (n << 8) | p;
  }
  return n >>> 0;
}

/**
 * Convert a 32-bit unsigned int to a dotted-quad IPv4 string.
 * Always returns a string (caller is expected to pass a real number).
 */
export function longToIp(n) {
  const v = (n ?? 0) >>> 0;
  return (
    `${(v >>> 24) & 0xff}.${(v >>> 16) & 0xff}.${(v >>> 8) & 0xff}.${v & 0xff}`
  );
}

/**
 * Parse a CIDR string ("10.0.0.0/24") into ``{base, prefixLen}``.
 * Returns null for invalid input.
 */
export function parseCidr(str) {
  const s = String(str ?? "").trim();
  const idx = s.indexOf("/");
  if (idx < 0) return null;
  const ip = s.slice(0, idx);
  const plen = parseInt(s.slice(idx + 1), 10);
  if (Number.isNaN(plen) || plen < 0 || plen > 32) return null;
  const long = ipToLong(ip);
  if (long === null) return null;
  const mask = plen === 0 ? 0 : (0xffffffff << (32 - plen)) >>> 0;
  const base = (long & mask) >>> 0;
  return { base, prefixLen: plen };
}

/**
 * Apply a /mask to an IP (as long), returning the network address.
 */
export function networkAddress(ipLong, maskBits) {
  const m = maskBits === 0 ? 0 : (0xffffffff << (32 - maskBits)) >>> 0;
  return (ipLong & m) >>> 0;
}

/**
 * Number of addresses in a /mask subnet.
 * /32 → 1, /31 → 2, /24 → 256, /0 → 4 294 967 296.
 */
export function subnetAddresses(maskBits) {
  // ``1 << (32 - mask)`` overflows for /0; use Math.pow to stay safe.
  return Math.pow(2, 32 - maskBits);
}

/**
 * Last (broadcast) address of a subnet given (subnetLong, maskBits).
 */
export function subnetLastAddress(subnetLong, maskBits) {
  return (subnetLong + subnetAddresses(maskBits) - 1) >>> 0;
}
