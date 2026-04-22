import { describe, expect, it } from "vitest";

import {
  escapeHtml,
  formatBytes,
  isValidIPv4,
  parseHash,
} from "../../../backend/static/js/lib/utils.js";

describe("escapeHtml", () => {
  it("escapes <, >, & for innerHTML safety", () => {
    expect(escapeHtml("<img src=x>")).not.toContain("<img");
    expect(escapeHtml("<img src=x>")).toContain("&lt;img");
  });

  it("escapes ampersand", () => {
    expect(escapeHtml("a & b")).toBe("a &amp; b");
  });

  it("returns empty string for null/undefined", () => {
    expect(escapeHtml(null)).toBe("");
    expect(escapeHtml(undefined)).toBe("");
  });

  it("coerces numbers to strings", () => {
    expect(escapeHtml(42)).toBe("42");
  });

  it("neutralises the audit H-02 payload (no live tag, no live attribute)", () => {
    // Audit doc: docs/security/audit_2026-04-22.md H-02
    const payload = "<img src=x onerror='window.__xss=1'>";
    const out = escapeHtml(payload);
    // The angle brackets are gone — browsers can no longer parse it as a tag.
    expect(out).not.toMatch(/<img/);
    expect(out).not.toMatch(/<\//);
    // The escaped form contains &lt;img — text content, not an HTML element.
    expect(out).toContain("&lt;img");
  });
});

describe("formatBytes", () => {
  it("returns dash for invalid input", () => {
    expect(formatBytes(null)).toBe("-");
    expect(formatBytes(undefined)).toBe("-");
    expect(formatBytes("not a number")).toBe("-");
    expect(formatBytes(-1)).toBe("-");
  });

  it("formats bytes as B", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1023)).toBe("1023 B");
  });

  it("formats KB / MB / GB with one decimal", () => {
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(2 * 1024 * 1024)).toBe("2.0 MB");
    expect(formatBytes(3 * 1024 * 1024 * 1024)).toBe("3.0 GB");
  });
});

describe("isValidIPv4", () => {
  it("accepts canonical IPv4 addresses", () => {
    expect(isValidIPv4("0.0.0.0")).toBe(true);
    expect(isValidIPv4("127.0.0.1")).toBe(true);
    expect(isValidIPv4("255.255.255.255")).toBe(true);
  });

  it("rejects non-strings", () => {
    expect(isValidIPv4(null as unknown as string)).toBe(false);
    expect(isValidIPv4(123 as unknown as string)).toBe(false);
  });

  it("rejects out-of-range octets", () => {
    expect(isValidIPv4("256.0.0.1")).toBe(false);
    expect(isValidIPv4("1.2.3.999")).toBe(false);
  });

  it("rejects leading zeros (ambiguous octal)", () => {
    expect(isValidIPv4("01.0.0.1")).toBe(false);
  });

  it("rejects malformed strings", () => {
    expect(isValidIPv4("1.2.3")).toBe(false);
    expect(isValidIPv4("1.2.3.4.5")).toBe(false);
    expect(isValidIPv4("hello")).toBe(false);
    expect(isValidIPv4(" 1.2.3.4")).toBe(false);
  });
});

describe("parseHash", () => {
  it("strips leading hash", () => {
    expect(parseHash("#inventory")).toBe("inventory");
    expect(parseHash("#home")).toBe("home");
  });

  it("returns empty string for non-strings or empty input", () => {
    expect(parseHash("")).toBe("");
    expect(parseHash(null as unknown as string)).toBe("");
    expect(parseHash(undefined as unknown as string)).toBe("");
  });

  it("trims surrounding whitespace", () => {
    expect(parseHash("#  diff  ")).toBe("diff");
  });
});
