import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * P0 — NAT Lookup happy path.
 *
 * The NAT lookup is a 3-step pipeline:
 *   1) GET  /api/devices-by-tag?tag=leaf-search  (which leaves to query)
 *   2) POST /api/find-leaf-check-device          (locate the source IP)
 *   3) GET  /api/devices-by-tag?tag=natlookup&...(firewalls in same site)
 *      then POST /api/nat-lookup                 (translation lookup)
 * After that the SPA also fires a /api/bgp/looking-glass for the
 * translated IP — we mock that as a no-op so the result table renders
 * cleanly without depending on RIPEStat.
 *
 * NB: the page has no "fabric/site selectors" — the ticket's wording is
 * slightly inaccurate; the page derives fabric/site from the find-leaf
 * answer for the source IP. We mock all four endpoints to drive a
 * clean success path.
 */
test("NAT Lookup renders translation result table on mocked happy path", async ({
  page,
}) => {
  // Step 1 + 3 share the same /api/devices-by-tag endpoint with
  // different ?tag= values. We branch on the URL.
  await page.route("**/api/devices-by-tag**", (route) => {
    const url = new URL(route.request().url());
    const tag = url.searchParams.get("tag") || "";
    if (tag === "leaf-search") {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          devices: [{ hostname: "leaf-nat-01", ip: "10.11.0.1" }],
        }),
      });
    } else if (tag === "natlookup") {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          devices: [{ hostname: "fw-nat-01", ip: "10.11.99.1" }],
        }),
      });
    } else {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ devices: [] }),
      });
    }
  });

  // Step 2: leaf check returns found + fabric/site so the firewall step
  // can fire.
  await page.route("**/api/find-leaf-check-device", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        found: true,
        checked_hostname: "leaf-nat-01",
        leaf_hostname: "leaf-nat-01",
        leaf_ip: "10.11.0.1",
        fabric: "NAT-FAB",
        site: "NAT-Site",
        hall: "NAT-Hall",
        interface: "Ethernet1/3",
      }),
    }),
  );

  let natCalled = false;
  await page.route("**/api/nat-lookup", (route) => {
    natCalled = true;
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        fabric: "NAT-FAB",
        site: "NAT-Site",
        rule_name: "RULE-INTERNET",
        translated_ips: ["8.8.8.8"],
        firewall_hostname: "fw-nat-01",
        firewall_ip: "10.11.99.1",
      }),
    });
  });

  // The SPA also calls /api/bgp/looking-glass for the translated IP —
  // mock so the BGP-path enrichment cell does not hit RIPEStat.
  await page.route("**/api/bgp/looking-glass**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ peers: [{ as_path: ["13335", "15169"] }] }),
    }),
  );

  const app = new AppShell(page);
  await app.gotoHash("nat");

  await page.locator("#natSrcIp").fill("10.11.0.42");
  // #natDestIp defaults to 8.8.8.8 — leave as-is.
  await page.locator("#natLookupBtn").click();

  await expect.poll(() => natCalled, { timeout: 5_000 }).toBe(true);

  await expect(page.locator("#natLookupResult")).toBeVisible({ timeout: 5_000 });
  await expect(page.locator("#natLookupResultBody")).toContainText("RULE-INTERNET");
  await expect(page.locator("#natLookupResultBody")).toContainText("8.8.8.8");
  await expect(page.locator("#natLookupResultBody")).toContainText("NAT-FAB");
});
