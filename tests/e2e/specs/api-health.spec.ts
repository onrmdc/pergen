import { expect, test } from "@playwright/test";

test.describe("Health endpoints", () => {
  test("/api/health returns {status: 'ok'}", async ({ request }) => {
    const res = await request.get("/api/health");
    expect(res.status()).toBe(200);
    expect(await res.json()).toEqual({ status: "ok" });
  });

  test("/api/v2/health returns the rich liveness payload", async ({ request }) => {
    const res = await request.get("/api/v2/health");
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toMatchObject({
      service: "pergen",
      status: "ok",
    });
    expect(typeof body.timestamp).toBe("string");
    expect(body.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(typeof body.request_id).toBe("string");
    expect(body.request_id.length).toBeGreaterThan(0);
  });
});
