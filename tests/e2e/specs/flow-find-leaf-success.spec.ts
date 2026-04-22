import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * P0 — Find Leaf happy path: fill IP → Search → result table populates.
 *
 * The SPA fans out to /api/devices-by-tag?tag=leaf-search to discover
 * which devices to query, then per-device POSTs to
 * /api/find-leaf-check-device. The first device returning {found: true}
 * wins and showResult() renders the result table. We mock both legs so
 * the test is deterministic.
 */
test("Find Leaf renders the result table on a mocked successful match", async ({
  page,
}) => {
  await page.route("**/api/devices-by-tag**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        devices: [
          { hostname: "leaf-search-01", ip: "10.10.0.1" },
          { hostname: "leaf-search-02", ip: "10.10.0.2" },
        ],
      }),
    }),
  );

  // First device says not-found, second device wins.
  let callCount = 0;
  await page.route("**/api/find-leaf-check-device", (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    callCount += 1;
    const isWinner = body.hostname === "leaf-search-02";
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        found: isWinner,
        checked_hostname: body.hostname,
        ...(isWinner
          ? {
              leaf_hostname: "leaf-search-02",
              leaf_ip: "10.10.0.2",
              fabric: "FL-FAB",
              site: "FL-Site",
              hall: "FL-Hall",
              interface: "Ethernet1/5",
            }
          : {}),
      }),
    });
  });

  const app = new AppShell(page);
  await app.gotoHash("findleaf");

  await page.locator("#findLeafIp").fill("10.99.0.42");
  await page.locator("#findLeafBtn").click();

  // Result table populates with the winning device's fields.
  await expect(page.locator("#findLeafResult")).toBeVisible({ timeout: 5_000 });
  await expect(page.locator("#findLeafResultBody")).toContainText("leaf-search-02");
  await expect(page.locator("#findLeafResultBody")).toContainText("FL-FAB");
  await expect(page.locator("#findLeafResultBody")).toContainText("Ethernet1/5");
  expect(callCount).toBeGreaterThan(0);
});
