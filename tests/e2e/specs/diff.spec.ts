import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

test.describe("Diff Checker page", () => {
  test("renders left/right textareas and Diff check button", async ({ page }) => {
    const app = new AppShell(page);
    await app.gotoHash("diff");

    await expect(page.locator("#diffLeft")).toBeVisible();
    await expect(page.locator("#diffRight")).toBeVisible();
    await expect(page.locator("#diffCheckBtn")).toBeVisible();
    await expect(page.locator("#diffResultWrap")).toBeHidden();
  });

  test("clicking Diff check on identical text still renders a result", async ({
    page,
  }) => {
    const app = new AppShell(page);
    await app.gotoHash("diff");

    await page.locator("#diffLeft").fill("alpha\nbeta\ngamma\n");
    await page.locator("#diffRight").fill("alpha\nbeta\ngamma\n");
    await page.locator("#diffCheckBtn").click();

    await expect(page.locator("#diffResultWrap")).toBeVisible();
    await expect(page.locator("#diffResult")).not.toBeEmpty();
  });
});
