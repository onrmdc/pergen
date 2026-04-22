import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

test.describe("Pre/Post Check page", () => {
  test("renders form with phase, fabric, site, role selectors and run button", async ({
    page,
  }) => {
    const app = new AppShell(page);
    await app.gotoHash("prepost");

    await expect(page.locator("#phase")).toBeVisible();
    await expect(page.locator("#fabric")).toBeVisible();
    await expect(page.locator("#site")).toBeVisible();
    await expect(page.locator("#role")).toBeVisible();
    await expect(page.locator("#runBtn")).toBeVisible();
    await expect(page.locator("#savedReportsDetails")).toBeVisible();
  });

  test("fabric dropdown is populated from /api/fabrics", async ({ page }) => {
    const app = new AppShell(page);
    await app.gotoHash("prepost");

    // wait until at least the placeholder + at least 1 fabric option is loaded
    const fabric = page.locator("#fabric");
    await expect
      .poll(async () => await fabric.locator("option").count(), { timeout: 5_000 })
      .toBeGreaterThan(1);

    const optionTexts = await fabric.locator("option").allTextContents();
    expect(optionTexts.some((t) => t.trim().length > 0 && t.trim() !== "—")).toBe(true);
  });
});
