import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * P0 — Custom command on the #restapi page.
 *
 * The Wave-3 ticket asked for "/api/run/custom"; the actual REST API
 * page calls /api/arista/run-cmds for free-form commands. We follow the
 * code, not the ticket name. The Pre/Post page also has a Custom
 * Command phase that calls /api/custom-command — separate flow, covered
 * by the prepost-run spec at the SPA-shell level.
 */
test("REST API page submit posts free-form command and renders response", async ({
  page,
}) => {
  // Inventory selector mocks so devices appear on the page.
  await page.route("**/api/fabrics**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ fabrics: ["RA-FAB"] }),
    }),
  );
  await page.route("**/api/sites**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sites: ["RA-Site"] }),
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
  // The restapi page may also fetch /api/devices-arista; route both.
  const devices = [
    { hostname: "rest-mock-01", ip: "10.50.0.1", fabric: "RA-FAB", site: "RA-Site", role: "Leaf" },
  ];
  const devsBody = JSON.stringify({ devices });
  await page.route("**/api/devices?**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: devsBody }),
  );
  await page.route("**/api/devices-arista**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: devsBody }),
  );
  await page.route("**/api/ping", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        results: devices.map((d) => ({ hostname: d.hostname, ip: d.ip, reachable: true })),
      }),
    }),
  );

  let submitCalled = false;
  let bodyText = "";
  await page.route("**/api/arista/run-cmds", (route) => {
    submitCalled = true;
    bodyText = route.request().postData() || "";
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        result: [{ modelName: "DCS-7050X3", version: "4.30.0F" }],
        error: null,
      }),
    });
  });

  const app = new AppShell(page);
  await app.gotoHash("restapi");

  // Pick fabric + site to populate the device list.
  const fabric = page.locator("#restapiFabric");
  await expect.poll(async () => fabric.locator("option").count(), { timeout: 5_000 }).toBeGreaterThan(1);
  await fabric.selectOption("RA-FAB");
  const site = page.locator("#restapiSite");
  await expect.poll(async () => site.locator("option").count(), { timeout: 5_000 }).toBeGreaterThan(1);
  await site.selectOption("RA-Site");

  await expect(page.locator("#restapiDeviceList .device-row")).toHaveCount(1, {
    timeout: 5_000,
  });
  await page.locator("#restapiSelectAll").click();

  // Free-form command + submit.
  await page.locator("#restapiRequestInput").fill("show version");
  await page.locator("#restapiSubmitBtn").click();

  await expect.poll(() => submitCalled, { timeout: 5_000 }).toBe(true);
  expect(bodyText).toContain("show version");

  // Result table renders with one row.
  await expect(page.locator("#restapiResultWrap")).toBeVisible({ timeout: 5_000 });
  await expect(page.locator("#restapiResultsTable tbody tr")).toHaveCount(1);
  await expect(page.locator("#restapiResultsTable tbody")).toContainText("DCS-7050X3");
});
