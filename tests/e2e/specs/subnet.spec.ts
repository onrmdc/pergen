import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

test.describe("Subnet Divide Calculator page", () => {
  test("renders network/mask inputs and Update/Reset buttons with defaults", async ({
    page,
  }) => {
    const app = new AppShell(page);
    await app.gotoHash("subnet");

    await expect(page.locator("#subnetNetwork")).toHaveValue("192.168.0.0");
    await expect(page.locator("#subnetMask")).toHaveValue("16");
    await expect(page.locator("#subnetUpdateBtn")).toBeVisible();
    await expect(page.locator("#subnetResetBtn")).toBeVisible();
  });

  test("clicking Update renders the calculation table", async ({ page }) => {
    const app = new AppShell(page);
    await app.gotoHash("subnet");

    await page.locator("#subnetUpdateBtn").click();
    await expect(page.locator("#subnetResultWrap")).toBeVisible();
    await expect(page.locator("#subnetCalcBody tr")).toHaveCount(1);
  });
});
