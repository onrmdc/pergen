import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * P0 — Transceiver Check: per-row "Clear counters" action.
 *
 * The error-state action surface had no E2E coverage. To expose the
 * Clear Counters button we have to:
 *   1. drive a Run that returns at least one row whose status contains
 *      "err" (case-insensitive) so renderTransceiverErrTableBody emits
 *      the action cell;
 *   2. ensure that row is on a Leaf device, Ethernet1/1-1/48 host port
 *      (transceiverIsLeafHostRecoverablePort gates the button).
 *
 * Then we click the per-row clear-counters button and assert the SPA
 * shows the success status emitted by transceiverCallClearCounters.
 */
test("Clear Counters per-row action posts and shows success status", async ({
  page,
}) => {
  await page.route("**/api/fabrics**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ fabrics: ["CC-FAB"] }),
    }),
  );
  await page.route("**/api/sites**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sites: ["CC-Site"] }),
    }),
  );
  await page.route("**/api/halls**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ halls: ["CC-Hall"] }),
    }),
  );
  await page.route("**/api/roles**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ roles: ["Leaf"] }),
    }),
  );

  // Single Leaf device so transceiverDeviceMap can resolve role=leaf.
  const devices = [
    {
      hostname: "leaf-cc-01",
      ip: "10.40.0.1",
      fabric: "CC-FAB",
      site: "CC-Site",
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
        results: devices.map((d) => ({
          hostname: d.hostname,
          ip: d.ip,
          reachable: true,
        })),
      }),
    }),
  );

  // /api/transceiver — return one row in errdisabled state so the
  // Clear Counters button renders.
  await page.route("**/api/transceiver", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        rows: [
          {
            hostname: "leaf-cc-01",
            interface: "Ethernet1/1",
            description: "host port",
            status: "errdisabled",
            tx_power: "-2.0",
            rx_power: "-3.0",
            flap_count: "5",
            last_flap: "1d",
            crc_count: "12",
            in_errors: "3",
          },
        ],
        errors: [],
      }),
    }),
  );

  // /api/transceiver/clear-counters — accept and return ok.
  let clearCalled = false;
  await page.route("**/api/transceiver/clear-counters", (route) => {
    clearCalled = true;
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        commands: ["clear counters interface Ethernet1/1"],
        output: "cleared",
      }),
    });
  });

  const app = new AppShell(page);
  await app.gotoHash("transceiver");

  // Cascade: fabric → loadSites; site change → loadHalls; hall change
  // → loadRoles; role change → loadDevices (app.js:997-1000). Roles
  // never populate without picking a hall first, so we mock one hall
  // and walk the full chain.
  const fabricSel = page.locator("#transceiverFabric");
  await expect.poll(async () => fabricSel.locator("option").count(), { timeout: 5_000 }).toBeGreaterThan(1);
  await fabricSel.selectOption("CC-FAB");
  const siteSel = page.locator("#transceiverSite");
  await expect.poll(async () => siteSel.locator("option").count(), { timeout: 5_000 }).toBeGreaterThan(1);
  await siteSel.selectOption("CC-Site");
  const hallSel = page.locator("#transceiverHall");
  await expect.poll(async () => hallSel.locator("option").count(), { timeout: 5_000 }).toBeGreaterThan(1);
  await hallSel.selectOption("CC-Hall");
  const roleSel = page.locator("#transceiverRole");
  await expect.poll(async () => roleSel.locator("option").count(), { timeout: 5_000 }).toBeGreaterThan(1);
  await roleSel.selectOption("Leaf");

  await expect(page.locator("#transceiverDeviceList .device-row")).toHaveCount(1, {
    timeout: 5_000,
  });
  await page.locator("#transceiverSelectAll").click();
  await page.locator("#transceiverRunBtn").click();

  // Error wrap + per-row action button visible.
  await expect(page.locator("#transceiverErrWrap")).toBeVisible({ timeout: 10_000 });
  const clearBtn = page
    .locator('#transceiverErrTbody tr[data-interface="Ethernet1/1"] .btn-clear-counters-one')
    .first();
  await expect(clearBtn).toBeVisible();

  await clearBtn.click();

  await expect.poll(() => clearCalled, { timeout: 5_000 }).toBe(true);
  await expect(page.locator("#transceiverRecoverStatus")).toContainText(
    /OK: clear counters Ethernet1\/1/i,
    { timeout: 5_000 },
  );
});
