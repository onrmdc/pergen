import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * P1 — REST API page submit using a built-in example.
 *
 * Complements flow-custom-command.spec.ts by exercising the
 * "Check version" example button (data-example="version") which fills
 * the textarea with a multi-line eAPI request, then submits to two
 * mocked devices and verifies both response rows render with the
 * device-specific payload.
 */
test("REST API example button + submit renders one row per device", async ({
  page,
}) => {
  await page.route("**/api/fabrics**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ fabrics: ["RA2-FAB"] }),
    }),
  );
  await page.route("**/api/sites**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sites: ["RA2-Site"] }),
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
    { hostname: "rest-eg-01", ip: "10.51.0.1", fabric: "RA2-FAB", site: "RA2-Site", role: "Leaf" },
    { hostname: "rest-eg-02", ip: "10.51.0.2", fabric: "RA2-FAB", site: "RA2-Site", role: "Leaf" },
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

  await page.route("**/api/arista/run-cmds", (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    const host = (body.device && body.device.hostname) || "unknown";
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        result: [{ modelName: "DCS-7050X3", hostname: host }],
        error: null,
      }),
    });
  });

  const app = new AppShell(page);
  await app.gotoHash("restapi");

  await page.locator("#restapiFabric").selectOption("RA2-FAB");
  await page.locator("#restapiSite").selectOption("RA2-Site");

  await expect(page.locator("#restapiDeviceList .device-row")).toHaveCount(2, {
    timeout: 5_000,
  });
  await page.locator("#restapiSelectAll").click();

  // Click the "Check version" example to populate the textarea.
  await page.locator('.restapi-example-btn[data-example="version"]').click();
  const reqValue = await page.locator("#restapiRequestInput").inputValue();
  expect(reqValue.trim().length).toBeGreaterThan(0);

  await page.locator("#restapiSubmitBtn").click();

  await expect(page.locator("#restapiResultWrap")).toBeVisible({ timeout: 5_000 });
  await expect(page.locator("#restapiResultsTable tbody tr")).toHaveCount(2);
  await expect(page.locator("#restapiResultsTable tbody")).toContainText("rest-eg-01");
  await expect(page.locator("#restapiResultsTable tbody")).toContainText("rest-eg-02");
});
