import { expect, test } from "@playwright/test";

/**
 * Regression test for the Phase-13 CSP fix.
 *
 * The shipped CSP is:
 *   script-src 'self'; style-src 'self' 'unsafe-inline'; ...
 *
 * That means ANY inline `<script>` block, inline event handler, or
 * `eval()` would trigger a console-level CSP violation when the
 * homepage loads. The SPA must boot cleanly — zero CSP violations.
 */
test("homepage produces zero CSP violations in the console", async ({ page }) => {
  const violations: string[] = [];

  page.on("console", (msg) => {
    const text = msg.text();
    if (
      msg.type() === "error" &&
      /Content Security Policy|Refused to (execute|apply|load)/i.test(text)
    ) {
      violations.push(text);
    }
  });
  page.on("pageerror", (err) => {
    if (/Content Security Policy/i.test(err.message)) {
      violations.push(err.message);
    }
  });

  await page.goto("/");
  await expect(page.locator("#page-home")).toHaveClass(/active/);
  // Give async chunks (theme-init, app.js) a beat to evaluate.
  await page.waitForLoadState("networkidle");

  expect(violations, violations.join("\n")).toEqual([]);
});
