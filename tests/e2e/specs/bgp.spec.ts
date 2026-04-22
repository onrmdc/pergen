import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

test.describe("BGP / Looking Glass page", () => {
  test("renders prefix input, expected-origin field, and Lookup button", async ({
    page,
  }) => {
    const app = new AppShell(page);
    await app.gotoHash("bgp");

    await expect(page.locator("#bgpResourceInput")).toBeVisible();
    await expect(page.locator("#bgpExpectedOrigin")).toBeVisible();
    await expect(page.locator("#bgpLookupBtn")).toBeVisible();
    await expect(page.locator("#bgpFavouritesWrap")).toBeVisible();
  });

  test("Lookup with an empty resource keeps the page alive", async ({ page }) => {
    const app = new AppShell(page);
    await app.gotoHash("bgp");

    await page.locator("#bgpLookupBtn").click();
    await expect(page.locator("#page-bgp")).toHaveClass(/active/);
    // status element exists either way; just confirm DOM didn't blow up
    await expect(page.locator("#bgpLookupStatus")).toBeAttached();
  });
});
