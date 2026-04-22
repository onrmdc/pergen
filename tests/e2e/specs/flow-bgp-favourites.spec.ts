import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * P1 — BGP favourites: add → reload → verify persistence in localStorage.
 *
 * The add-favourite button only appears after a successful lookup, so
 * we mock the 5 lookup endpoints to return canned data. After that
 * bgpAddFavBtn becomes visible; clicking it pushes the prefix into
 * localStorage["bgp_favourites"]. We then reload the page and confirm
 * the favourite persists in both localStorage and the UI list.
 */
test("BGP favourite persists in localStorage and re-renders after reload", async ({
  page,
}) => {
  const prefix = "203.0.113.0/24";

  await page.route("**/api/bgp/status**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        announced: true,
        withdrawn: false,
        origin_as: "AS64512",
        as_name: "TEST-NET",
        rpki_status: "valid",
      }),
    }),
  );
  await page.route("**/api/bgp/history**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ current: "64512", previous: "" }),
    }),
  );
  await page.route("**/api/bgp/visibility**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ percentage: 95, probes_seeing: 95, total_probes: 100 }),
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
  await page.route("**/api/bgp/wan-rtr-match**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ devices: [] }),
    }),
  );

  const app = new AppShell(page);
  await app.gotoHash("bgp");

  // Clear any stale favourites from a prior test sharing the origin.
  await page.evaluate(() => localStorage.removeItem("bgp_favourites"));

  await page.locator("#bgpResourceInput").fill(prefix);
  await page.locator("#bgpLookupBtn").click();

  // Wait for the lookup to complete: status cards should appear.
  await expect(page.locator("#bgpStatusCards")).toBeVisible({ timeout: 5_000 });

  // Now the Add favourite button should be visible.
  const addFav = page.locator("#bgpAddFavBtn");
  await expect(addFav).toBeVisible({ timeout: 5_000 });
  await addFav.click();

  // localStorage entry written.
  const stored = await page.evaluate(() => localStorage.getItem("bgp_favourites"));
  expect(stored).toContain(prefix);

  // Reload page and confirm the favourite is still rendered.
  await app.gotoHash("bgp");
  const renderedFavs = page.locator("#bgpFavouritesList");
  await expect(renderedFavs).toContainText(prefix, { timeout: 5_000 });

  // Cleanup so other tests don't see this favourite.
  await page.evaluate(() => localStorage.removeItem("bgp_favourites"));
});
