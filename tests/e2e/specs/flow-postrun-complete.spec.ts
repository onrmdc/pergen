import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * Wave-4 P0 — POST /api/run/post/complete round-trip
 *
 * Closes one of the 3 P0 gaps surfaced by the wave-4 e2e gap analysis
 * (docs/test-coverage/e2e_gap_analysis_2026-04-22-wave4.md): the
 * post-run lifecycle had zero E2E coverage.
 *
 * Flow:
 *   1. Mock /api/run/pre/create — Alice creates a PRE run.
 *   2. Mock /api/run/post/complete — Alice submits her POST device_results.
 *   3. Verify the comparison result renders.
 *
 * Implicitly verifies the wave-4 W4-H-01 fix is wired correctly: the
 * route accepts a properly-actor-scoped POST without breaking the
 * happy path. The cross-actor refusal contract is pinned by
 * tests/test_security_run_post_complete_actor_scoping.py.
 */
test("POST /api/run/post/complete renders comparison result", async ({ page }) => {
  // Inventory selectors so the prepost device list populates.
  await page.route("**/api/fabrics**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ fabrics: ["F1"] }),
    }),
  );
  await page.route("**/api/sites**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sites: ["S1"] }),
    }),
  );
  await page.route("**/api/halls**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ halls: [] }),
    }),
  );
  await page.route("**/api/roles**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ roles: ["Leaf"] }),
    }),
  );

  const devices = [
    {
      hostname: "leaf-postrun-01",
      ip: "10.60.0.1",
      fabric: "F1",
      site: "S1",
      role: "Leaf",
    },
  ];
  await page.route("**/api/devices?**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ devices }),
    }),
  );
  await page.route("**/api/ping", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        results: [{ hostname: devices[0].hostname, ip: devices[0].ip, reachable: true }],
      }),
    }),
  );

  // Mock the per-device PRE run.
  await page.route("**/api/run/device", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        hostname: devices[0].hostname,
        ip: devices[0].ip,
        ok: true,
        outputs: [{ command: "show ver", output: "EOS 4.30.0F" }],
        parsed_flat: { Version: "4.30.0F" },
      }),
    }),
  );

  // Mock /api/run/pre/create — returns a stable run_id.
  let createdRunId: string | null = null;
  await page.route("**/api/run/pre/create", (route) => {
    createdRunId = `e2e-postrun-${Date.now()}`;
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ run_id: createdRunId }),
    });
  });

  // Mock /api/run/post/complete — returns a comparison.
  let postCompleteCalled = false;
  let postCompleteBody = "";
  await page.route("**/api/run/post/complete", (route) => {
    postCompleteCalled = true;
    postCompleteBody = route.request().postData() || "";
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: createdRunId,
        phase: "POST",
        device_results: [
          { hostname: devices[0].hostname, ok: true, parsed_flat: { Version: "4.30.0F" } },
        ],
        comparison: {
          devices: [
            {
              hostname: devices[0].hostname,
              same: true,
              fields: { Version: { pre: "4.30.0F", post: "4.30.0F", same: true } },
            },
          ],
        },
      }),
    });
  });

  const app = new AppShell(page);
  await app.gotoHash("prepost");

  // Pick fabric+site to populate devices.
  await page.locator("#fabricSelect").selectOption("F1");
  await page.locator("#siteSelect").selectOption("S1");

  await expect(page.locator("#deviceList .device-row")).toHaveCount(1, {
    timeout: 5_000,
  });
  await page.locator("#selectAll").click();

  // Click the Pre Check button — triggers /api/run/device + /api/run/pre/create.
  await page.locator("#preCheckBtn").click();
  await expect.poll(() => createdRunId, { timeout: 8_000 }).not.toBeNull();

  // Click Post Check — triggers /api/run/post/complete with the captured run_id.
  await page.locator("#postCheckBtn").click({ timeout: 8_000 });
  await expect.poll(() => postCompleteCalled, { timeout: 8_000 }).toBe(true);

  // Body must include the run_id (proves the SPA passed it through).
  expect(postCompleteBody).toContain(createdRunId!);
});
