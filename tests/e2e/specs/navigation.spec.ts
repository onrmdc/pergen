import { expect, test } from "@playwright/test";
import { AppShell, NAV_HASHES } from "../pages/AppShell";

test.describe("Hash router", () => {
  for (const hash of NAV_HASHES) {
    test(`#${hash} activates page-${hash}`, async ({ page }) => {
      const app = new AppShell(page);
      await app.gotoHash(hash);

      await expect(page.locator(`#page-${hash}`)).toHaveClass(/active/);
      // exactly one page should be .active at a time
      const activeCount = await page.locator(".page.active").count();
      expect(activeCount).toBe(1);
      expect(await app.currentHash()).toBe(`#${hash}`);
    });
  }

  test("changing hash updates active section", async ({ page }) => {
    const app = new AppShell(page);
    await app.gotoHash("home");
    await app.navigateTo("diff");
    await expect(page.locator("#page-diff")).toHaveClass(/active/);
    await expect(page.locator("#page-home")).not.toHaveClass(/(^|\s)active(\s|$)/);
  });
});
