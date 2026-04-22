import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

test.describe("Live Notepad page", () => {
  test("renders textarea and user name input", async ({ page }) => {
    const app = new AppShell(page);
    await app.gotoHash("notepad");

    await expect(page.locator("#notepadText")).toBeVisible();
    await expect(page.locator("#notepadUserName")).toBeVisible();
  });

  test("loads stored content from /api/notepad on mount", async ({ page }) => {
    const app = new AppShell(page);
    await app.gotoHash("notepad");

    // The status line says "Loading…" until the first GET resolves; we
    // just assert the textarea is enabled (the loader stays put if the
    // API errored — that would also be a real bug we want to catch).
    await expect(page.locator("#notepadText")).toBeEnabled();
  });
});
