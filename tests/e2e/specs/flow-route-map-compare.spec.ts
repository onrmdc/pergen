import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * P0 — DCI / WAN Routers route-map compare.
 *
 * Pick a scope, the SPA loads /api/router-devices, the operator selects
 * routers + clicks Compare, which posts /api/route-map/run. We mock
 * both so the result table renders without real device access.
 */
test("route-map Compare renders the result table from mocked /api/route-map/run", async ({
  page,
}) => {
  await page.route("**/api/router-devices?**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        devices: [
          { hostname: "rtr-mock-01", ip: "10.20.0.1" },
          { hostname: "rtr-mock-02", ip: "10.20.0.2" },
        ],
      }),
    }),
  );

  let runCalled = false;
  await page.route("**/api/route-map/run", (route) => {
    runCalled = true;
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        rows: [
          {
            peer_group: "wan-peer",
            route_map_in: "RM-IN-01",
            route_map_out: "RM-OUT-01",
            devices: ["rtr-mock-01", "rtr-mock-02"],
            hierarchy_in: [],
            hierarchy_out: [],
          },
          {
            peer_group: "dci-peer",
            route_map_in: "RM-IN-02",
            route_map_out: "RM-OUT-02",
            devices: ["rtr-mock-01"],
            hierarchy_in: [],
            hierarchy_out: [],
          },
        ],
        errors: [],
      }),
    });
  });

  const app = new AppShell(page);
  await app.gotoHash("routemap");

  // Pick a scope — triggers loadRouterDevices().
  await page.locator("#routerScope").selectOption("dci");
  await expect(page.locator("#routerDeviceList .device-row")).toHaveCount(2, {
    timeout: 5_000,
  });

  // Select both devices.
  await page.locator("#routerSelectAll").click();

  // Compare button enables once devices are loaded.
  const compareBtn = page.locator("#routerCompareBtn");
  await expect(compareBtn).toBeEnabled();
  await compareBtn.click();

  await expect.poll(() => runCalled, { timeout: 5_000 }).toBe(true);

  // Result table visible with 2 rows (one per peer_group).
  await expect(page.locator("#routerTableWrap")).toBeVisible({ timeout: 5_000 });
  await expect(page.locator("#routerTableBody tr")).toHaveCount(2);
  await expect(page.locator("#routerTableBody")).toContainText("RM-IN-01");
  await expect(page.locator("#routerTableBody")).toContainText("dci-peer");
});
