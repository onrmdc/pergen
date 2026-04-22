import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * P1 — BGP lookup (read-side).
 *
 * The Lookup button fans out to 5 RIPEStat-backed endpoints in parallel:
 *   /api/bgp/status, /api/bgp/history, /api/bgp/visibility,
 *   /api/bgp/looking-glass, /api/bgp/bgplay.
 * We mock all of them so the test never depends on network reachability
 * to RIPEStat. Asserts the status cards render with our canned values.
 */
test("BGP Lookup renders status cards from mocked RIPEStat-side endpoints", async ({
  page,
}) => {
  await page.route("**/api/bgp/status**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        announced: true,
        withdrawn: false,
        origin_as: "AS13335",
        as_name: "CLOUDFLARENET",
        rpki_status: "valid",
        visibility_summary: { peers_seeing: 100, total_peers: 110 },
      }),
    }),
  );
  await page.route("**/api/bgp/history**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ current: "13335", previous: "" }),
    }),
  );
  await page.route("**/api/bgp/visibility**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ percentage: 91, probes_seeing: 100, total_probes: 110 }),
    }),
  );
  await page.route("**/api/bgp/looking-glass**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ peers: [] }),
    }),
  );
  await page.route("**/api/bgp/bgplay**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ events: [] }),
    }),
  );
  // wan-rtr-match fires only on AS lookups; harmless to mock too.
  await page.route("**/api/bgp/wan-rtr-match**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ devices: [] }),
    }),
  );

  const app = new AppShell(page);
  await app.gotoHash("bgp");

  await page.locator("#bgpResourceInput").fill("1.1.1.0/24");
  await page.locator("#bgpLookupBtn").click();

  // Status cards become visible with our mocked data.
  const cards = page.locator("#bgpStatusCards");
  await expect(cards).toBeVisible({ timeout: 5_000 });
  await expect(cards).toContainText("AS13335");
  await expect(cards).toContainText("CLOUDFLARENET");
  await expect(cards).toContainText("valid");
});
