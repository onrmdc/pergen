import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

test.describe("Credential page", () => {
  test("renders the add form, method selector, and credentials table", async ({
    page,
  }) => {
    const app = new AppShell(page);
    await app.gotoHash("credential");

    await expect(page.locator("#credName")).toBeVisible();
    await expect(page.locator("#credMethod")).toBeVisible();
    await expect(page.locator("#credUsername")).toBeVisible();
    await expect(page.locator("#credPassword")).toBeVisible();
    await expect(page.locator("#credSubmit")).toBeVisible();
    await expect(page.locator("#credListBody")).toBeAttached();
  });

  test("switching method to API key swaps the visible field group", async ({
    page,
  }) => {
    const app = new AppShell(page);
    await app.gotoHash("credential");

    await expect(page.locator("#credBasicFields")).toBeVisible();
    await expect(page.locator("#credApiKeyFields")).toBeHidden();

    await page.locator("#credMethod").selectOption("api_key");
    await expect(page.locator("#credApiKeyFields")).toBeVisible();
    await expect(page.locator("#credBasicFields")).toBeHidden();
  });
});
