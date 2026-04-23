import { describe, expect, it } from "vitest";

import {
  escapeHtml,
  formatBytes,
  isHostPortEthernet1to48,
  isValidIPv4,
  parseHash,
  safeHtml,
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

  it("escapes double-quote so attribute-context interpolation is safe", () => {
    // Wave-6 Phase C: attribute-injection regression. Without this
    // encoding, `data-x="${escapeHtml(v)}"` would break out of the
    // attribute when v contains `"`.
    const out = escapeHtml('a"b');
    expect(out).toBe("a&quot;b");
  });

  it("escapes single-quote so attribute-context interpolation is safe", () => {
    expect(escapeHtml("o'clock")).toBe("o&#39;clock");
  });
});

describe("safeHtml", () => {
  it("interpolates plain values with full HTML escaping", () => {
    const name = "<img src=x onerror=alert(1)>";
    const out = safeHtml`<span>${name}</span>`;
    expect(out).not.toContain("<img");
    expect(out).toContain("&lt;img");
    expect(out).toMatch(/^<span>/);
    expect(out).toMatch(/<\/span>$/);
  });

  it("escapes attribute-context double-quotes", () => {
    const v = 'a"b';
    const out = safeHtml`<div title="${v}">x</div>`;
    expect(out).toBe('<div title="a&quot;b">x</div>');
  });

  it("supports multiple interpolations and preserves literal segments", () => {
    const out = safeHtml`<tr><td>${"a&b"}</td><td>${"<x>"}</td></tr>`;
    expect(out).toBe("<tr><td>a&amp;b</td><td>&lt;x&gt;</td></tr>");
  });

  it("returns the literal template when there are no interpolations", () => {
    const out = safeHtml`<hr/>`;
    expect(out).toBe("<hr/>");
  });

  it("coerces null/undefined values to empty string", () => {
    const out = safeHtml`<p>${null}|${undefined}</p>`;
    expect(out).toBe("<p>|</p>");
  });

  it("neutralises the canonical audit XSS payload", () => {
    const payload = "<img src=x onerror='window.__xss=1'>";
    const out = safeHtml`<td>${payload}</td>`;
    expect(out).not.toMatch(/<img/);
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

// --------------------------------------------------------------------------- //
// Wave-7.6 (frontend twin) — host-port classifier for transceiver actions     //
// --------------------------------------------------------------------------- //
// Mirrors backend/transceiver_recovery_policy.py::is_ethernet_module1_host_port
// so the SPA renders the recover / clear-counters buttons for both Cisco's
// `Ethernet1/X` form AND Arista's bare `EthernetX` form. Operator-reported
// bug 2026-04-23: Arista buttons never appeared because the JS twin only
// accepted the slash form.

describe("isHostPortEthernet1to48 — Cisco NX-OS form", () => {
  it("accepts Ethernet1/1 .. Ethernet1/48 (ports in range)", () => {
    expect(isHostPortEthernet1to48("Ethernet1/1")).toBe(true);
    expect(isHostPortEthernet1to48("Ethernet1/15")).toBe(true);
    expect(isHostPortEthernet1to48("Ethernet1/48")).toBe(true);
  });

  it("accepts case-insensitive + short forms", () => {
    expect(isHostPortEthernet1to48("ethernet1/24")).toBe(true);
    expect(isHostPortEthernet1to48("Eth1/24")).toBe(true);
    expect(isHostPortEthernet1to48("Et1/24")).toBe(true);
    expect(isHostPortEthernet1to48("1/24")).toBe(true);
  });

  it("rejects out-of-range and non-module-1 ports", () => {
    expect(isHostPortEthernet1to48("Ethernet1/0")).toBe(false);
    expect(isHostPortEthernet1to48("Ethernet1/49")).toBe(false);
    expect(isHostPortEthernet1to48("Ethernet1/64")).toBe(false);
    expect(isHostPortEthernet1to48("Ethernet2/1")).toBe(false);
    expect(isHostPortEthernet1to48("Ethernet3/15")).toBe(false);
  });
});

describe("isHostPortEthernet1to48 — Arista EOS bare form (wave-7.6)", () => {
  it("accepts bare EthernetN where 1 <= N <= 48", () => {
    expect(isHostPortEthernet1to48("Ethernet1")).toBe(true);
    expect(isHostPortEthernet1to48("Ethernet8")).toBe(true);
    expect(isHostPortEthernet1to48("Ethernet9")).toBe(true);
    expect(isHostPortEthernet1to48("Ethernet24")).toBe(true);
    expect(isHostPortEthernet1to48("Ethernet48")).toBe(true);
  });

  it("accepts case-insensitive + short Arista forms", () => {
    expect(isHostPortEthernet1to48("ethernet9")).toBe(true);
    expect(isHostPortEthernet1to48("Eth9")).toBe(true);
    expect(isHostPortEthernet1to48("Et9")).toBe(true);
  });

  it("rejects out-of-range bare Ethernet (uplinks etc.)", () => {
    expect(isHostPortEthernet1to48("Ethernet0")).toBe(false);
    expect(isHostPortEthernet1to48("Ethernet49")).toBe(false);
    expect(isHostPortEthernet1to48("Ethernet64")).toBe(false);
    expect(isHostPortEthernet1to48("Ethernet96")).toBe(false);
  });
});

describe("isHostPortEthernet1to48 — non-host-port forms", () => {
  it("rejects management / loopback / port-channel / vlan / tunnel", () => {
    expect(isHostPortEthernet1to48("Management1")).toBe(false);
    expect(isHostPortEthernet1to48("Loopback0")).toBe(false);
    expect(isHostPortEthernet1to48("Port-Channel1")).toBe(false);
    expect(isHostPortEthernet1to48("Vlan100")).toBe(false);
    expect(isHostPortEthernet1to48("Tunnel1")).toBe(false);
  });

  it("rejects sub-interfaces and injection attempts", () => {
    expect(isHostPortEthernet1to48("Ethernet1/1.100")).toBe(false);
    expect(isHostPortEthernet1to48("Ethernet1.100")).toBe(false);
    expect(isHostPortEthernet1to48("Ethernet1; reload")).toBe(false);
    expect(isHostPortEthernet1to48("Ethernet 1")).toBe(false);
  });

  it("rejects empty / null / non-string input", () => {
    expect(isHostPortEthernet1to48("")).toBe(false);
    expect(isHostPortEthernet1to48(null as unknown as string)).toBe(false);
    expect(isHostPortEthernet1to48(undefined as unknown as string)).toBe(false);
    expect(isHostPortEthernet1to48(15 as unknown as string)).toBe(false);
  });
});
