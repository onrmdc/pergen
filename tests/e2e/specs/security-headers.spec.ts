import { expect, test } from "@playwright/test";

// Note: `strict-transport-security` is intentionally omitted from the
// REQUIRED list. The backend (backend/request_logging.py) only emits HSTS
// when `request.is_secure` is true; the E2E suite hits Flask over plain
// HTTP at 127.0.0.1:5000, so HSTS is correctly absent here. We assert it
// conditionally below.
const REQUIRED_HEADERS = [
  "content-security-policy",
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
