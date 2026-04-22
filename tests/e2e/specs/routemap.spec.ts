import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

test.describe("DCI / WAN Routers (route-map) page", () => {
  test("renders prefix search, scope selector, and disabled Compare button", async ({
    page,
  }) => {
    const app = new AppShell(page);
    await app.gotoHash("routemap");

    await expect(page.locator("#routerPrefixInput")).toBeVisible();
    await expect(page.locator("#routerPrefixSearchBtn")).toBeVisible();
    await expect(page.locator("#routerScope")).toBeVisible();
    await expect(page.locator("#routerCompareBtn")).toBeDisabled();
    await expect(page.locator("#routerDeviceList")).toBeAttached();
  });

  test("scope dropdown offers DCI/WAN/all options", async ({ page }) => {
    const app = new AppShell(page);
    await app.gotoHash("routemap");

    const values = await page
      .locator("#routerScope option")
      .evaluateAll((opts) => opts.map((o) => (o as HTMLOptionElement).value));
    expect(values).toEqual(expect.arrayContaining(["", "dci", "wan", "all"]));
  });
});
