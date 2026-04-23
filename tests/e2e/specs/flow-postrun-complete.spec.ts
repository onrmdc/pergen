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

  // Mock the per-device PRE run. The SPA reads `d.device_result` from
  // the response (app.js:1316/1388); a flat shape is treated as the
  // error path and the PRE create never fires.
  await page.route("**/api/run/device", (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    const dev = body.device || {};
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        device_result: {
          hostname: dev.hostname || devices[0].hostname,
          ip: dev.ip || devices[0].ip,
          vendor: "Arista",
          model: "EOS",
          version: "4.30.0F",
        },
      }),
    });
  });

  // Mock /api/run/pre/create — returns a stable run_id. Note app.js
  // wraps the response inside a richer shape; we keep it minimal here
  // because runPhase only consumes run_id + run_created_at.
  let createdRunId: string | null = null;
  await page.route("**/api/run/pre/create", (route) => {
    createdRunId = `e2e-postrun-${Date.now()}`;
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: createdRunId,
        run_created_at: new Date().toISOString(),
      }),
    });
  });

  // Mock /api/run/result/<run_id> — the POST phase fetches this first
  // to discover which devices were originally part of the PRE run
  // (app.js:1288). Without it the POST phase short-circuits with a
  // "Run not found" error and never calls /api/run/post/complete.
  await page.route("**/api/run/result/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: createdRunId,
        devices,
      }),
    }),
  );

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

  // Pick fabric / site / role — the device list is populated by the
  // role select's change handler (app.js:2224). Selectors per
  // backend/static/index.html: #fabric, #site, #role (not #fabricSelect).
  const fabric = page.locator("#fabric");
  await expect.poll(async () => fabric.locator("option").count(), { timeout: 5_000 }).toBeGreaterThan(1);
  await fabric.selectOption("F1");
  const site = page.locator("#site");
  await expect.poll(async () => site.locator("option").count(), { timeout: 5_000 }).toBeGreaterThan(1);
  await site.selectOption("S1");
  const role = page.locator("#role");
  await expect.poll(async () => role.locator("option").count(), { timeout: 5_000 }).toBeGreaterThan(1);
  await role.selectOption("Leaf");

  await expect(page.locator("#deviceList .device-row")).toHaveCount(1, {
    timeout: 5_000,
  });
  await page.locator("#selectAll").click();

  // The PRE/POST flow lives behind the single Run button: Phase=PRE +
  // Run triggers /api/run/device + /api/run/pre/create, then Phase=POST
  // + Run triggers the per-device run + /api/run/post/complete with the
  // saved run_id. There is no #preCheckBtn/#postCheckBtn pair (those
  // were a doc-time fiction in the original spec).
  await page.locator("#phase").selectOption("PRE");
  await page.locator("#runBtn").click();
  await expect.poll(() => createdRunId, { timeout: 10_000 }).not.toBeNull();

  // Wait for the Run button to re-enable (PRE phase finished).
  await expect(page.locator("#runBtn")).toBeEnabled({ timeout: 10_000 });

  // Switch to POST and click Run again.
  await page.locator("#phase").selectOption("POST");
  await page.locator("#runBtn").click();
  await expect.poll(() => postCompleteCalled, { timeout: 10_000 }).toBe(true);

  // Body must include the run_id (proves the SPA passed it through).
  expect(postCompleteBody).toContain(createdRunId!);
});
