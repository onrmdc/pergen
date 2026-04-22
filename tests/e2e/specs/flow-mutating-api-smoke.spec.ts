import { expect, test } from "@playwright/test";

/**
 * P1 — POST/PUT/DELETE smoke for mutating routes not covered by other
 * flow specs.
 *
 * Goal: catch crashes and 500s from blueprint wiring / schema drift on
 * the write side, without depending on real device reachability. We
 * accept any non-5xx status (the route may legitimately 4xx on bad
 * input — that's better than a 500 stack trace).
 *
 * Each call uses a unique-per-run identifier where state could collide
 * with parallel workers or other specs.
 */
test.describe("Mutating API smoke", () => {
  test("POST /api/credentials with junk body does not 500", async ({ request }) => {
    const stamp = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
    const res = await request.post("/api/credentials", {
      data: {
        name: `e2e-smoke-${stamp}`,
        method: "basic",
        username: "x",
        password: "y",
      },
    });
    expect(res.status(), `body: ${await res.text()}`).toBeLessThan(500);

    // Best-effort cleanup. Ignore status; if the POST 4xx'd above this
    // is a no-op against the store.
    await request.delete(`/api/credentials/e2e-smoke-${stamp}`);
  });

  test("POST /api/diff with simple input does not 500", async ({ request }) => {
    const res = await request.post("/api/diff", {
      data: { pre: "alpha\nbeta\n", post: "alpha\nbeta-new\n" },
    });
    expect(res.status(), `body: ${await res.text()}`).toBeLessThan(500);
  });

  test("PUT /api/notepad with plain text does not 500", async ({ request }) => {
    const res = await request.put("/api/notepad", {
      data: { content: `e2e-smoke-${Date.now()}` },
    });
    expect(res.status(), `body: ${await res.text()}`).toBeLessThan(500);
  });

  test("POST /api/inventory/import with empty rows does not 500", async ({
    request,
  }) => {
    const res = await request.post("/api/inventory/import", {
      data: { rows: [] },
    });
    expect(res.status(), `body: ${await res.text()}`).toBeLessThan(500);
  });

  test("DELETE /api/credentials/<unknown> does not 500", async ({ request }) => {
    const res = await request.delete(
      `/api/credentials/does-not-exist-${Date.now()}`,
    );
    // 404 is fine; only crashes are flagged here.
    expect(res.status(), `body: ${await res.text()}`).toBeLessThan(500);
  });
});
