import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * Round-trip: type into the notepad → wait for the PUT → reload → see
 * the same text. The notepad is shared global state on the server, so
 * every run uses a unique marker line and only asserts that marker.
 */
test("notepad text persists across a page reload", async ({ page }) => {
  const marker = `e2e-notepad-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;

  const app = new AppShell(page);
  await app.gotoHash("notepad");

  // Provide a name (the SPA refuses to save without one).
  await page.locator("#notepadUserName").fill("e2e-runner");

  // Read current contents, append our marker, then save by blurring.
  const ta = page.locator("#notepadText");
  await ta.click();
  const original = await ta.inputValue();
  const next = `${original}${original.endsWith("\n") || original === "" ? "" : "\n"}${marker}\n`;

  const savePut = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/notepad") &&
      (r.request().method() === "PUT" || r.request().method() === "POST"),
  );
  await ta.fill(next);
  await ta.blur();
  const res = await savePut;
  expect(res.status()).toBeLessThan(400);

  // Reload and confirm the marker is in the textarea. We use
  // toHaveValue (not toContainText) because the SPA writes the loaded
  // notepad to `textarea.value` — which doesn't reflect into
  // `textContent`, so toContainText would always see "".
  await page.reload();
  await app.waitForActive("notepad");
  await expect(page.locator("#notepadText")).toHaveValue(new RegExp(marker));
});
