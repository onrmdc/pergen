import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

test.describe("REST API page", () => {
  test("renders selectors, command examples, request textarea, and Submit", async ({
    page,
  }) => {
    const app = new AppShell(page);
    await app.gotoHash("restapi");

    await expect(page.locator("#restapiFabric")).toBeVisible();
    await expect(page.locator("#restapiSite")).toBeVisible();
    await expect(page.locator("#restapiRole")).toBeVisible();
    await expect(page.locator("#restapiRequestInput")).toBeVisible();
    await expect(page.locator("#restapiSubmitBtn")).toBeVisible();

    // The example command picker (3 buttons) should be wired up
    const examples = page.locator(".restapi-example-btn");
    await expect(examples).toHaveCount(3);
  });

  test("clicking an example button populates the request textarea", async ({
    page,
  }) => {
    const app = new AppShell(page);
    await app.gotoHash("restapi");

    const before = await page.locator("#restapiRequestInput").inputValue();
    await page.locator('.restapi-example-btn[data-example="version"]').click();
    const after = await page.locator("#restapiRequestInput").inputValue();
    expect(after).not.toBe(before);
    expect(after.trim().length).toBeGreaterThan(0);
  });
});
