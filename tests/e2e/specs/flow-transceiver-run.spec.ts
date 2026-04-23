import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * P0 — Transceiver Check page: select fabric/site, click Run, assert
 * the result rows render.
 *
 * Endpoint note: the SPA calls /api/transceiver (per-device), not
 * /api/transceiver/run. The wave-3 ticket called the old route name; we
 * mock the actual one so the UI surface is exercised end-to-end.
 */
test("transceiver Run renders mocked rows", async ({ page }) => {
  // Inventory selectors: one fabric, one site, one role, two devices.
  await page.route("**/api/fabrics**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ fabrics: ["TX-FAB"] }),
    }),
  );
  await page.route("**/api/sites**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sites: ["TX-Site"] }),
    }),
  );
  await page.route("**/api/halls**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ halls: ["TX-Hall"] }),
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
    { hostname: "tx-mock-01", ip: "10.30.0.1", fabric: "TX-FAB", site: "TX-Site", role: "Leaf" },
    { hostname: "tx-mock-02", ip: "10.30.0.2", fabric: "TX-FAB", site: "TX-Site", role: "Leaf" },
  ];
  await page.route("**/api/devices?**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ devices }),
    }),
  );

  // /api/ping — the transceiver page does not gate on ping, but other
  // pages do; harmless to mock.
  await page.route("**/api/ping", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        results: devices.map((d) => ({ hostname: d.hostname, ip: d.ip, reachable: true })),
      }),
    }),
  );

  // /api/transceiver — return one transceiver row per device call.
  await page.route("**/api/transceiver", (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    const dev = (body.devices && body.devices[0]) || {};
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        rows: [
          {
            hostname: dev.hostname,
            interface: "Ethernet1/1",
            description: "uplink",
            mtu: "9214",
            serial: "SN12345",
            type: "100GBASE-SR4",
            manufacturer: "Arista",
            temp: "35.0",
            tx_power: "-2.5",
            rx_power: "-3.1",
            status: "connected",
            last_flap: "never",
            flap_count: "0",
            crc_count: "0",
            in_errors: "0",
          },
        ],
        errors: [],
      }),
    });
  });

  const app = new AppShell(page);
  await app.gotoHash("transceiver");

  // Cascade: fabric → loadSites; site change → loadHalls; hall change
  // → loadRoles; role change → loadDevices (app.js:997-1000). So we
  // MUST pick a real hall to make roles populate, and a role to make
  // devices populate. The earlier version mocked halls=[] which left
  // the role select empty forever.
  const fabric = page.locator("#transceiverFabric");
  await expect.poll(async () => fabric.locator("option").count(), { timeout: 5_000 }).toBeGreaterThan(1);
  await fabric.selectOption("TX-FAB");
  const site = page.locator("#transceiverSite");
  await expect.poll(async () => site.locator("option").count(), { timeout: 5_000 }).toBeGreaterThan(1);
  await site.selectOption("TX-Site");
  const hall = page.locator("#transceiverHall");
  await expect.poll(async () => hall.locator("option").count(), { timeout: 5_000 }).toBeGreaterThan(1);
  await hall.selectOption("TX-Hall");
  const role = page.locator("#transceiverRole");
  await expect.poll(async () => role.locator("option").count(), { timeout: 5_000 }).toBeGreaterThan(1);
  await role.selectOption("Leaf");

  // Wait for device rows to render.
  await expect(page.locator("#transceiverDeviceList .device-row")).toHaveCount(2, {
    timeout: 5_000,
  });

  // Select all and Run.
  await page.locator("#transceiverSelectAll").click();
  await page.locator("#transceiverRunBtn").click();

  // Result table should appear with 2 rows (one per mocked device).
  await expect(page.locator("#transceiverTableWrap")).toBeVisible({ timeout: 10_000 });
  await expect(page.locator("#transceiverTbody tr")).toHaveCount(2);
  await expect(page.locator("#transceiverTbody")).toContainText("tx-mock-01");
  await expect(page.locator("#transceiverTbody")).toContainText("tx-mock-02");
});
