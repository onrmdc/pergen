import { describe, expect, it } from "vitest";

import {
  ipToLong,
  longToIp,
  networkAddress,
  parseCidr,
  subnetAddresses,
  subnetLastAddress,
} from "../../../backend/static/js/lib/subnet.js";

describe("ipToLong", () => {
  it("converts canonical IPv4 to 32-bit unsigned int", () => {
    expect(ipToLong("0.0.0.0")).toBe(0);
    expect(ipToLong("127.0.0.1")).toBe(0x7f000001);
    expect(ipToLong("255.255.255.255")).toBe(0xffffffff);
    expect(ipToLong("192.168.1.1")).toBe(0xc0a80101);
  });

  it("strips surrounding whitespace", () => {
    expect(ipToLong("  10.0.0.1  ")).toBe(0x0a000001);
  });

  it("returns null for malformed input", () => {
    expect(ipToLong(null as unknown as string)).toBeNull();
    expect(ipToLong("")).toBeNull();
    expect(ipToLong("1.2.3")).toBeNull();
    expect(ipToLong("1.2.3.4.5")).toBeNull();
    expect(ipToLong("256.0.0.1")).toBeNull();
    expect(ipToLong("1.2.3.999")).toBeNull();
    expect(ipToLong("hello")).toBeNull();
  });

  it("rejects octets with leading zeros (ambiguous octal)", () => {
    expect(ipToLong("01.0.0.1")).toBeNull();
  });
});

describe("longToIp", () => {
  it("round-trips with ipToLong", () => {
    for (const ip of ["0.0.0.0", "127.0.0.1", "255.255.255.255", "10.20.30.40"]) {
      expect(longToIp(ipToLong(ip)!)).toBe(ip);
    }
  });

  it("handles null/undefined as 0.0.0.0", () => {
    expect(longToIp(null as unknown as number)).toBe("0.0.0.0");
    expect(longToIp(undefined as unknown as number)).toBe("0.0.0.0");
  });

  it("handles full 32-bit range", () => {
    expect(longToIp(0xffffffff)).toBe("255.255.255.255");
  });
});

describe("parseCidr", () => {
  it("parses canonical CIDR strings", () => {
    expect(parseCidr("10.0.0.0/8")).toEqual({ base: 0x0a000000, prefixLen: 8 });
    expect(parseCidr("192.168.1.0/24")).toEqual({ base: 0xc0a80100, prefixLen: 24 });
    expect(parseCidr("0.0.0.0/0")).toEqual({ base: 0, prefixLen: 0 });
    expect(parseCidr("255.255.255.255/32")).toEqual({
      base: 0xffffffff,
      prefixLen: 32,
    });
  });

  it("masks the IP to the network address", () => {
    // 10.0.0.5/24 → base = 10.0.0.0
    expect(parseCidr("10.0.0.5/24")).toEqual({ base: 0x0a000000, prefixLen: 24 });
  });

  it("returns null for invalid input", () => {
    expect(parseCidr(null as unknown as string)).toBeNull();
    expect(parseCidr("")).toBeNull();
    expect(parseCidr("10.0.0.0")).toBeNull(); // no slash
    expect(parseCidr("10.0.0.0/")).toBeNull();
    expect(parseCidr("10.0.0.0/33")).toBeNull(); // > 32
    expect(parseCidr("10.0.0.0/-1")).toBeNull();
    expect(parseCidr("hello/24")).toBeNull();
  });
});

describe("networkAddress", () => {
  it("masks to the /N network", () => {
    expect(networkAddress(0x0a000005, 24)).toBe(0x0a000000);
    expect(networkAddress(0xc0a80101, 16)).toBe(0xc0a80000);
  });

  it("/0 returns 0", () => {
    expect(networkAddress(0xffffffff, 0)).toBe(0);
  });

  it("/32 returns the ip unchanged", () => {
    expect(networkAddress(0x0a000005, 32)).toBe(0x0a000005);
  });
});

describe("subnetAddresses", () => {
  it("returns 1 for /32", () => {
    expect(subnetAddresses(32)).toBe(1);
  });

  it("returns 2 for /31", () => {
    expect(subnetAddresses(31)).toBe(2);
  });

  it("returns 256 for /24", () => {
    expect(subnetAddresses(24)).toBe(256);
  });

  it("returns 65536 for /16", () => {
    expect(subnetAddresses(16)).toBe(65536);
  });

  it("returns 4294967296 for /0 without overflow", () => {
    expect(subnetAddresses(0)).toBe(4294967296);
  });
});

describe("subnetLastAddress", () => {
  it("returns broadcast for /24", () => {
    // 10.0.0.0/24 → broadcast 10.0.0.255
    expect(longToIp(subnetLastAddress(0x0a000000, 24))).toBe("10.0.0.255");
  });

  it("returns same address for /32", () => {
    expect(subnetLastAddress(0x0a000005, 32)).toBe(0x0a000005);
  });

  it("returns 255.255.255.255 for /0", () => {
    expect(longToIp(subnetLastAddress(0, 0))).toBe("255.255.255.255");
  });
});
