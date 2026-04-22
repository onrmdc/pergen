import { expect, test } from "@playwright/test";

/**
 * Wave-6 Phase F: cookie-auth surface smoke.
 *
 * The default Playwright fixture runs with the token gate OPEN
 * (`PERGEN_DEV_OPEN_API=1`) and the cookie path disabled, so we can't
 * exercise the full login → CSRF-protected POST loop end-to-end without
 * spinning a second webServer. Instead this spec verifies the new
 * surface area is reachable and CSP-clean:
 *
 * - `GET /login` returns 200 with the login form HTML.
 * - The login form is CSP-compliant (no inline `<script>` / `<style>`).
 * - `GET /api/auth/whoami` returns `{actor: null}` for an unauthenticated
 *   browser (no session cookie present).
 * - `POST /api/auth/logout` is idempotent (always 200).
 * - Submitting bad credentials to `POST /api/auth/login` returns 401
 *   without a Set-Cookie carrying a session.
 *
 * The full login → CSRF round-trip lives in `tests/test_auth_login_flow.py`
 * (pytest, against the Flask test client) where the env vars can be
 * flipped per-test.
 */
test.describe("Cookie auth surface (Phase F)", () => {
  test("GET /login renders the CSP-clean login form", async ({ request }) => {
    const res = await request.get("/login");
    expect(res.status()).toBe(200);
    const html = await res.text();
    expect(html).toContain("<form");
    expect(html).toContain('id="loginForm"');
    expect(html).toContain('id="loginNext"');
    // CSP: no inline scripts / styles.
    expect(html).not.toMatch(/<script(?![^>]*\bsrc=)/);
    expect(html).not.toMatch(/<style\b/);
    // External login.css + login.js are referenced.
    expect(html).toContain("/static/css/login.css");
    expect(html).toContain("/static/js/login.js");
  });

  test("GET /api/auth/whoami returns null for an unauthenticated browser", async ({
    request,
  }) => {
    const res = await request.get("/api/auth/whoami");
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toEqual({ actor: null });
  });

  test("POST /api/auth/logout is idempotent", async ({ request }) => {
    const res = await request.post("/api/auth/logout");
    expect(res.status()).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
  });

  test("POST /api/auth/login with bad creds returns 401, no session cookie", async ({
    request,
  }) => {
    const res = await request.post("/api/auth/login", {
      data: { username: "nobody", password: "definitely-wrong" },
    });
    expect(res.status()).toBe(401);
    const body = await res.json();
    expect(body).toHaveProperty("error");
    // No Set-Cookie header should announce a logged-in pergen_session.
    const setCookie = res.headers()["set-cookie"] || "";
    expect(setCookie).not.toMatch(/pergen_session=[^;]+\.[^;]+\./);
  });

  test("GET /login escapes a malicious next= param", async ({ request }) => {
    const res = await request.get('/login?next="><script>alert(1)</script>');
    expect(res.status()).toBe(200);
    const html = await res.text();
    expect(html).not.toContain('"><script>alert(1)</script>');
  });
});
