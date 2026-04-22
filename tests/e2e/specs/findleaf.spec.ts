import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

test.describe("Find Leaf page", () => {
  test("renders IP input and Search button", async ({ page }) => {
    const app = new AppShell(page);
    await app.gotoHash("findleaf");

    await expect(page.locator("#findLeafIp")).toBeVisible();
    await expect(page.locator("#findLeafBtn")).toBeVisible();
  });

  test("clicking Search with no IP keeps the page alive and shows status", async ({
    page,
  }) => {
    const app = new AppShell(page);
    await app.gotoHash("findleaf");

    await page.locator("#findLeafBtn").click();
    await expect(page.locator("#findLeafStatus")).toBeVisible();
    await expect(page.locator("#page-findleaf")).toHaveClass(/active/);
  });
});
