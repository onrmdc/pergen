import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

test.describe("Transceiver Check page", () => {
  test("renders fabric/site/role selectors and Run button", async ({ page }) => {
    const app = new AppShell(page);
    await app.gotoHash("transceiver");

    await expect(page.locator("#transceiverFabric")).toBeVisible();
    await expect(page.locator("#transceiverSite")).toBeVisible();
    await expect(page.locator("#transceiverRole")).toBeVisible();
    await expect(page.locator("#transceiverRunBtn")).toBeVisible();
    await expect(page.locator("#transceiverDeviceList")).toBeAttached();
  });

  test("Recovery-all button is hidden until error rows appear", async ({ page }) => {
    const app = new AppShell(page);
    await app.gotoHash("transceiver");

    // The error wrap is hidden by default until a run produces err* statuses.
    await expect(page.locator("#transceiverErrWrap")).toBeHidden();
    await expect(page.locator("#transceiverRecoverAllBtn")).toBeHidden();
  });
});
