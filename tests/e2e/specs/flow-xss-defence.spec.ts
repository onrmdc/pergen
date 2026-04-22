import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * Regression test for audit findings H-01 / H-02.
 *
 * Mocks `/api/find-leaf-check-device` so it returns a payload containing
 * an `<img onerror>` HTML injection. The SPA must not execute the JS or
 * insert the `<img>` element into the DOM.
 *
 * Wave-3 Phase 2 landed the escapeHtml() fix in the result-row builder
 * (app.js:4061), so this test now pins the safe behaviour.
 */

test.describe("XSS defence in result tables (audit H-02)", () => {
  test("find-leaf result must not execute or render injected HTML", async ({ page }) => {
    const xssPayload = "<img src=x onerror='window.__xss_landed=1'>";

    await page.route("**/api/find-leaf-check-device**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          found: true,
          leaf_hostname: xssPayload,
          leaf_ip: "10.0.0.99",
          fabric: "FAB1",
          site: "S1",
          hall: "H1",
          interface: "Ethernet1/1",
          checked_hostname: "h1",
        }),
      }),
    );
    await page.route("**/api/find-leaf**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          devices: [{ hostname: "h1", ip: "10.0.0.5" }],
        }),
      }),
    );

    const app = new AppShell(page);
    await app.gotoHash("findleaf");

    const ipInput = page.locator("#findLeafIp, input[type=text]").first();
    await ipInput.fill("10.0.0.99");
    const btn = page.locator("button:has-text('Find'), #findLeafBtn").first();
    if (await btn.isVisible().catch(() => false)) {
      await btn.click();
    } else {
      await ipInput.press("Enter");
    }
    await page.waitForTimeout(800);

    // No <img src=x> element should ever appear.
    const imgCount = await page.locator("img[src='x']").count();
    expect(imgCount).toBe(0);

    // The XSS payload must not have set window.__xss_landed.
    const flag = await page.evaluate(() => (window as { __xss_landed?: number }).__xss_landed);
    expect(flag).toBeUndefined();
  });
});
