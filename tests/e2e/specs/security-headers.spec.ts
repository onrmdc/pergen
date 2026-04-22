import { expect, test } from "@playwright/test";

const REQUIRED_HEADERS = [
  "content-security-policy",
  "strict-transport-security",
  "x-frame-options",
  "x-content-type-options",
  "referrer-policy",
] as const;

test.describe("Security headers", () => {
  test("homepage carries all required defence-in-depth headers", async ({
    request,
  }) => {
    const res = await request.get("/");
    expect(res.status()).toBe(200);
    const headers = res.headers();
    for (const h of REQUIRED_HEADERS) {
      expect(headers[h], `missing header: ${h}`).toBeTruthy();
    }
    expect(headers["x-frame-options"]?.toUpperCase()).toBe("DENY");
    expect(headers["x-content-type-options"]?.toLowerCase()).toBe("nosniff");
    expect(headers["content-security-policy"]).toContain("default-src 'self'");
    expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
  });

  test("API responses also carry the security headers", async ({ request }) => {
    const res = await request.get("/api/health");
    const headers = res.headers();
    for (const h of REQUIRED_HEADERS) {
      expect(headers[h], `missing header on /api/health: ${h}`).toBeTruthy();
    }
  });
});
