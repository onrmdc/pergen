import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * P1 — Subnet Divide Calculator: divide a /24 → 2 × /25 rows.
 *
 * Pure client-side feature, no backend mocking needed. We type a known
 * network, click Update, then click the first row's "Divide" link and
 * assert the table now shows two rows with /25 prefixes.
 */
test("Subnet calculator divides one /24 into two /25 rows", async ({
  page,
}) => {
  const app = new AppShell(page);
  await app.gotoHash("subnet");

  // The subnet page initialises with 192.168.0.0/16 (HTML defaults), so
  // changing the mask from /16 to /24 fires a confirm() dialog asking to
  // reset the divisions. Auto-accept it so the new base network sticks.
  page.on("dialog", (d) => d.accept());

  // Use a smaller network than the 192.168.0.0/16 default so the table
  // stays one row wide and the test is fast.
  await page.locator("#subnetNetwork").fill("10.0.0.0");
  await page.locator("#subnetMask").fill("24");
  await page.locator("#subnetUpdateBtn").click();

  // One initial row showing 10.0.0.0/24.
  const body = page.locator("#subnetCalcBody");
  await expect(body.locator("tr")).toHaveCount(1);
  await expect(body).toContainText("10.0.0.0/24");

  // Click the Divide link on that row.
  await body.locator("tr").first().locator("a", { hasText: "Divide" }).click();

  // Now we expect 2 rows: 10.0.0.0/25 and 10.0.0.128/25.
  await expect(body.locator("tr")).toHaveCount(2);
  await expect(body).toContainText("10.0.0.0/25");
  await expect(body).toContainText("10.0.0.128/25");
});
