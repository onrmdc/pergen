import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * P0 — Pre/Post Check page: PRE run round-trip.
 *
 * The Pre/Post page (#prepost) is the operator's main mutation surface
 * for taking device snapshots. The wave-3 E2E gap analysis flagged that
 * NO spec actually exercised the run button + per-device fetch + report
 * creation chain end-to-end.
 *
 * We mock the entire device-touching surface (devices list, ping,
 * per-device run, pre-create) so the test runs deterministically with
 * zero real network reachability requirements.
 */
test("PRE run completes and creates a saved report (mocked devices)", async ({
  page,
}) => {
  const stamp = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  const runId = `e2e-run-${stamp}`;

  // /api/fabrics → return one fabric so the dropdown populates.
  await page.route("**/api/fabrics**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ fabrics: ["E2E-FAB"] }),
    }),
  );

  // /api/sites — return one site for the chosen fabric.
  await page.route("**/api/sites**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sites: ["E2E-Site"] }),
    }),
  );

  // /api/halls + /api/roles — empty is fine for this flow.
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

  // /api/devices — return two canned devices.
  const devices = [
    { hostname: "leaf-mock-01", ip: "10.0.0.1", fabric: "E2E-FAB", site: "E2E-Site", role: "Leaf" },
    { hostname: "leaf-mock-02", ip: "10.0.0.2", fabric: "E2E-FAB", site: "E2E-Site", role: "Leaf" },
  ];
  await page.route("**/api/devices?**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ devices }),
    }),
  );

  // /api/ping — mark both as reachable.
  await page.route("**/api/ping", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        results: devices.map((d) => ({ hostname: d.hostname, ip: d.ip, reachable: true })),
      }),
    }),
  );

  // /api/run/device — return a canned device_result per call.
  await page.route("**/api/run/device", (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    const dev = body.device || {};
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        device_result: {
          hostname: dev.hostname,
          ip: dev.ip,
          vendor: "Arista",
          model: "EOS",
          uptime: "1d",
          version: "4.30.0F",
        },
      }),
    });
  });

  // /api/run/pre/create — pretend a report was created.
  let preCreateCalled = false;
  await page.route("**/api/run/pre/create", (route) => {
    preCreateCalled = true;
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: runId,
        run_created_at: new Date().toISOString(),
      }),
    });
  });

  const app = new AppShell(page);
  await app.gotoHash("prepost");

  // Wait for fabric to populate, pick it (selectOption fires change).
  // Cascade: fabric → site → hall → role → devices. loadDevices is wired
  // to the Role select's change event (app.js:2224), so we must select a
  // role before the device list renders.
  const fabric = page.locator("#fabric");
  await expect.poll(async () => fabric.locator("option").count(), { timeout: 5_000 }).toBeGreaterThan(1);
  await fabric.selectOption("E2E-FAB");
  const site = page.locator("#site");
  await expect.poll(async () => site.locator("option").count(), { timeout: 5_000 }).toBeGreaterThan(1);
  await site.selectOption("E2E-Site");
  const role = page.locator("#role");
  await expect.poll(async () => role.locator("option").count(), { timeout: 5_000 }).toBeGreaterThan(1);
  await role.selectOption("Leaf");

  // Devices render after fabric/site/role selection. Wait for our mock rows.
  await expect(page.locator("#deviceList .device-row")).toHaveCount(2, { timeout: 5_000 });

  // Select all and click Run.
  await page.locator("#selectAll").click();
  await page.locator("#runBtn").click();

  // Wait for the pre/create POST to fire.
  await expect.poll(() => preCreateCalled, { timeout: 10_000 }).toBe(true);

  // Status text shows the success summary.
  await expect(page.locator("#runStatus")).toContainText(/PRE completed/i, { timeout: 5_000 });
});
