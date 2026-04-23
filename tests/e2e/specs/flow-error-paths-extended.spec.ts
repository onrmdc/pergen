import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * Wave-4 P0 — Extended negative-path coverage
 *
 * Closes the third P0 gap from the wave-4 e2e gap analysis: the
 * existing flow-error-paths.spec.ts only covers find-leaf 5xx and
 * /api/diff 4xx. This file adds:
 *   - Network timeout / abort
 *   - Empty-shape JSON response
 *   - Backend 500 on a state-changing endpoint (credential POST)
 *
 * Each test asserts: SPA does not page-error; an error UI is rendered
 * (any visible toast / inline message / status text).
 */

test("credential POST 500 surfaces an error in the form, no JS crash", async ({ page }) => {
  await page.route("**/api/credentials", (route) => {
    if (route.request().method() === "POST") {
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: "encryption backend not available" }),
      });
    } else if (route.request().method() === "GET") {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ credentials: [] }),
      });
    } else {
      route.fallback();
    }
  });

  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  const app = new AppShell(page);
  await app.gotoHash("credential");

  await page.locator("#credName").fill(`e2e-err-${Date.now()}`);
  await page.locator("#credMethod").selectOption("basic");
  await page.locator("#credUsername").fill("u");
  await page.locator("#credPassword").fill("p");
  await page.locator("#credSubmit").click();

  // Wait briefly for the SPA to settle.
  await page.waitForTimeout(500);

  // Assert: no JS pageerror.
  expect(errors, `JS errors: ${errors.join("\n")}`).toEqual([]);

  // Assert: an error message is visible somewhere in the credential form.
  // The exact element ID may vary; we use a forgiving locator.
  const errorMsg = page.locator("#credMsg, .credential-form .error, [role='alert']");
  await expect(errorMsg.first()).toBeVisible({ timeout: 3_000 });
});

test("inventory list with empty response renders empty state, no JS crash", async ({
  page,
}) => {
  await page.route("**/api/inventory", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ devices: [] }),
    }),
  );
  await page.route("**/api/fabrics", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ fabrics: [] }),
    }),
  );

  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  const app = new AppShell(page);
  await app.gotoHash("inventory");
  await page.waitForTimeout(500);

  // No JS errors — the SPA must handle empty arrays without crashing.
  expect(errors, `JS errors: ${errors.join("\n")}`).toEqual([]);

  // The inventory table must exist (even if empty).
  await expect(page.locator("#invTable")).toBeVisible();
});

test("find-leaf with aborted request leaves the page in a sane state", async ({
  page,
}) => {
  // Defer the find-leaf response indefinitely so we can abort.
  await page.route("**/api/find-leaf", () => {
    // Never call route.fulfill — Playwright will hang the request until aborted.
  });

  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  const app = new AppShell(page);
  await app.gotoHash("findleaf");

  // Scope to the findleaf page section — the previous union selector
  // `#findLeafIp, input[type=text]` resolved to #customCommandInput on
  // the prepost page (still present in DOM, just hidden via .active).
  const ipInput = page.locator("#page-findleaf #findLeafIp");
  await ipInput.fill("10.99.99.99");
  await page.locator("#findLeafBtn").click();

  // Navigate away — should cancel the in-flight request without exception.
  await page.waitForTimeout(300);
  await app.gotoHash("home");
  await page.waitForTimeout(300);

  expect(errors, `JS errors: ${errors.join("\n")}`).toEqual([]);
});
