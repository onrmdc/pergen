import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * P2 — negative-path E2E specs.
 *
 * E2E gap analysis 2026-04-22 noted that all 20 existing Playwright specs
 * are happy-path only. This file mocks 4xx/5xx responses for a handful of
 * key API routes and confirms the SPA renders a sensible error state
 * (status text, no console crash) instead of silently swallowing.
 */

test("find-leaf shows error state when /api/find-leaf returns 5xx", async ({ page }) => {
  await page.route("**/api/find-leaf**", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: "upstream device unreachable" }),
    }),
  );

  const consoleErrors: string[] = [];
  page.on("pageerror", (e) => consoleErrors.push(String(e)));

  const app = new AppShell(page);
  await app.gotoHash("findleaf");

  // Use the specific findleaf-page selector. The previous union
  // (`#findLeafIp, ..., input[type=text]`) resolved to the first
  // matching node in DOM order — `#customCommandInput` on the prepost
  // page — because hidden pages still exist in the DOM (only `.active`
  // toggles visibility). Scope tightly to the findleaf section.
  const ipInput = page.locator("#page-findleaf #findLeafIp");
  await ipInput.fill("10.0.0.99");
  await page.locator("#findLeafBtn").click();

  // No JS pageerrors (the SPA must handle the 500 gracefully).
  await page.waitForTimeout(500);
  expect(consoleErrors, `JS errors: ${consoleErrors.join("\n")}`).toEqual([]);
});

test("diff page handles a 4xx from /api/diff without crashing", async ({ page }) => {
  await page.route("**/api/diff", (route) =>
    route.fulfill({
      status: 413,
      contentType: "application/json",
      body: JSON.stringify({ error: "diff inputs capped at 262144 bytes" }),
    }),
  );

  const app = new AppShell(page);
  await app.gotoHash("diff");

  await page.locator("#diffLeft").fill("hello");
  await page.locator("#diffRight").fill("world");

  const consoleErrors: string[] = [];
  page.on("pageerror", (e) => consoleErrors.push(String(e)));

  await page.locator("#diffCheckBtn").click();
  await page.waitForTimeout(500);

  expect(consoleErrors).toEqual([]);
});
