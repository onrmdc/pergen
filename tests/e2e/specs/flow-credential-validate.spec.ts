import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * P1 — Credential row "Validate" action.
 *
 * Mocks /api/credentials so a known credential row renders (without
 * mutating the real instance/credentials store), then mocks
 * /api/credentials/<name>/validate and clicks the Validate button.
 * Asserts the SPA paints the credMsg block in the success state.
 */
test("Validate button posts /validate and renders success status", async ({
  page,
}) => {
  const credName = `e2e-validate-${Date.now()}`;

  // Return a single canned credential row.
  await page.route("**/api/credentials", (route) => {
    if (route.request().method() === "GET") {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          credentials: [{ name: credName, method: "basic" }],
        }),
      });
    } else {
      route.fallback();
    }
  });

  let validateCalled = false;
  await page.route(
    `**/api/credentials/${encodeURIComponent(credName)}/validate`,
    (route) => {
      validateCalled = true;
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          device: "leaf-mock-01",
          message: "Login success.",
          uptime: "1d 2h",
        }),
      });
    },
  );

  const app = new AppShell(page);
  await app.gotoHash("credential");

  // Wait for the row to render.
  const row = page.locator("#credListBody tr", { hasText: credName });
  await expect(row).toBeVisible({ timeout: 5_000 });

  await row.locator(".cred-validate").click();

  await expect.poll(() => validateCalled, { timeout: 5_000 }).toBe(true);

  // Success state: credential-msg has class "ok" and contains the
  // device/message text from the mocked response.
  const msg = page.locator("#credMsg");
  await expect(msg).toHaveClass(/ok/, { timeout: 5_000 });
  await expect(msg).toContainText("leaf-mock-01");
  await expect(msg).toContainText("Login success");
  await expect(msg).toContainText("1d 2h");
});
