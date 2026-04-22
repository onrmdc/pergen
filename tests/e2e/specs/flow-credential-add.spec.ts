import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * Happy path: add a basic credential through the UI, see it in the
 * list, then delete it. Uses a unique-per-run name so parallel runs
 * never clobber each other.
 */
test("add then delete a credential round-trips through the UI", async ({ page }) => {
  const credName = `e2e-cred-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;

  // Auto-accept the browser-native confirm() the SPA shows on delete.
  page.on("dialog", (d) => d.accept());

  const app = new AppShell(page);
  await app.gotoHash("credential");

  // Create
  await page.locator("#credName").fill(credName);
  await page.locator("#credMethod").selectOption("basic");
  await page.locator("#credUsername").fill("e2e-user");
  await page.locator("#credPassword").fill("e2e-pass");

  const createPost = page.waitForResponse(
    (r) => r.url().endsWith("/api/credentials") && r.request().method() === "POST",
  );
  await page.locator("#credSubmit").click();
  const createRes = await createPost;
  expect(createRes.status()).toBeLessThan(400);

  // Verify the new row appears
  const row = page.locator("#credListBody tr", { hasText: credName });
  await expect(row).toBeVisible();

  // Delete
  const deleteReq = page.waitForResponse(
    (r) =>
      r.url().includes(`/api/credentials/${encodeURIComponent(credName)}`) &&
      r.request().method() === "DELETE",
  );
  await row.locator(".cred-delete").click();
  const delRes = await deleteReq;
  expect(delRes.status()).toBeLessThan(400);

  await expect(
    page.locator("#credListBody tr", { hasText: credName }),
  ).toHaveCount(0);
});
