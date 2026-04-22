import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

test.describe("NAT Lookup page", () => {
  test("renders source/dest IP inputs and Lookup button", async ({ page }) => {
    const app = new AppShell(page);
    await app.gotoHash("nat");

    await expect(page.locator("#natSrcIp")).toBeVisible();
    await expect(page.locator("#natDestIp")).toBeVisible();
    await expect(page.locator("#natLookupBtn")).toBeVisible();
    // default destination IP is prefilled
    await expect(page.locator("#natDestIp")).toHaveValue("8.8.8.8");
  });

  test("submitting an empty/invalid source IP surfaces a status (no crash)", async ({
    page,
  }) => {
    const app = new AppShell(page);
    await app.gotoHash("nat");

    await page.locator("#natSrcIp").fill("not-an-ip");
    await page.locator("#natLookupBtn").click();

    // The page must keep responding; the status line is the user-visible
    // signal whether validation rejected it or the backend did.
    await expect(page.locator("#natLookupStatus")).toBeVisible();
    await expect(page.locator("#page-nat")).toHaveClass(/active/);
  });
});
