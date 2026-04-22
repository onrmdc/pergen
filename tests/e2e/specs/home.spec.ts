import { expect, test } from "@playwright/test";

test.describe("Home page", () => {
  test("loads with all 12 home cards visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("#page-home")).toHaveClass(/active/);

    const cards = page.locator(".home-cards .home-card");
    await expect(cards).toHaveCount(12);

    // Sanity: every card has a non-empty title and an href starting with #
    const count = await cards.count();
    for (let i = 0; i < count; i++) {
      const card = cards.nth(i);
      await expect(card).toBeVisible();
      const href = await card.getAttribute("href");
      expect(href).toMatch(/^#[a-z-]+$/);
      await expect(card.locator(".home-card-title")).not.toBeEmpty();
    }
  });

  test("clicking a home card navigates to that hash", async ({ page }) => {
    await page.goto("/");
    await page.locator('.home-card[href="#diff"]').click();
    await expect(page.locator("#page-diff")).toHaveClass(/active/);
    expect(await page.evaluate(() => window.location.hash)).toBe("#diff");
  });
});
