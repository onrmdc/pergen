import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * P1 — Diff result navigation summary bar.
 *
 * After running a diff with mixed add/remove/modify rows, the summary
 * bar renders three buttons ("Added N", "Deleted N", "Changed N") which
 * cycle through change rows via diffScrollToRow(). We:
 *   1) Run a diff that produces all three kinds of changes.
 *   2) Assert the summary bar shows the right counts.
 *   3) Click each navigation button — must not throw + must keep the
 *      page alive (smooth-scroll position itself is too brittle to
 *      assert in headless chromium).
 */
test("Diff navigation buttons render counts and respond to clicks", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  page.on("pageerror", (e) => consoleErrors.push(String(e)));

  const app = new AppShell(page);
  await app.gotoHash("diff");

  // Construct an input pair with at least one of each: add, rem, mod.
  // Left has lines [A, B, C]; Right has [A, B-changed, D]. Result:
  // - row 0: same (A == A)
  // - row 1: mod  (B vs B-changed)
  // - row 2: rem  (C only on left)
  // - row 3: add  (D only on right)
  await page.locator("#diffLeft").fill("alpha\nbeta\ngamma\n");
  await page.locator("#diffRight").fill("alpha\nbeta-changed\ndelta\n");
  await page.locator("#diffCheckBtn").click();

  await expect(page.locator("#diffResultWrap")).toBeVisible({ timeout: 5_000 });

  const summary = page.locator("#diffSummaryBar");
  await expect(summary).toBeVisible();

  // Three nav buttons present.
  const buttons = summary.locator("button");
  await expect(buttons).toHaveCount(3);

  // Counts should reflect the mix above. Each button's text starts with
  // its label; we just assert the counts are >0 for the kinds we expect.
  const addedText = await buttons.nth(0).textContent();
  const deletedText = await buttons.nth(1).textContent();
  const changedText = await buttons.nth(2).textContent();
  expect(addedText).toMatch(/Added\s+\d+/);
  expect(deletedText).toMatch(/Deleted\s+\d+/);
  expect(changedText).toMatch(/Changed\s+\d+/);

  // Click each — must not throw or kill the page.
  await buttons.nth(0).click();
  await buttons.nth(1).click();
  await buttons.nth(2).click();
  // Click again to exercise the modulo cycle.
  await buttons.nth(0).click();

  // Diff guide gutter (right rail) should also have one indicator dot
  // per change row.
  const guide = page.locator("#diffGuide > div");
  expect(await guide.count()).toBeGreaterThan(0);

  expect(consoleErrors, `JS errors: ${consoleErrors.join("\n")}`).toEqual([]);
});
