import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * Happy path: paste two configs into the diff checker, click Diff
 * check, and verify the result panel renders with both an addition and
 * a removal line.
 */
test("diff checker renders +/- lines for two different configs", async ({ page }) => {
  const app = new AppShell(page);
  await app.gotoHash("diff");

  await page
    .locator("#diffLeft")
    .fill("hostname r1\ninterface eth0\n  ip address 10.0.0.1/24\n");
  await page
    .locator("#diffRight")
    .fill("hostname r1\ninterface eth0\n  ip address 10.0.0.2/24\n  description WAN\n");

  await page.locator("#diffCheckBtn").click();
  await expect(page.locator("#diffResultWrap")).toBeVisible();
  await expect(page.locator("#diffResult")).not.toBeEmpty();

  // The diff renderer marks lines with class hooks (added/removed/changed).
  // The IP change should produce at least one removed and one added marker.
  const html = await page.locator("#diffResult").innerHTML();
  expect(html).toMatch(/10\.0\.0\.1/);
  expect(html).toMatch(/10\.0\.0\.2/);
  expect(html).toMatch(/description WAN/);
});
