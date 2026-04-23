import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * P0 — full inventory add → edit → delete round-trip through the UI.
 *
 * E2E gap analysis 2026-04-22 flagged that #inventory had ZERO specs
 * despite being a primary mutating page. This spec exercises the modal
 * open → save (POST), the row appearance, the edit modal (PUT), and the
 * delete flow (DELETE). Uses unique-per-run hostname so parallel
 * workers cannot collide.
 */
test.describe("inventory CRUD round-trip", () => {
  test("add → edit → delete an inventory device through the UI", async ({ page }) => {
    const stamp = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
    const hostname = `e2e-leaf-${stamp}`;
    const ip = "10.99.99." + (Math.floor(Math.random() * 250) + 2);

    // Auto-accept the browser-native confirm() that the SPA shows on delete.
    page.on("dialog", (d) => d.accept());

    const app = new AppShell(page);
    await app.gotoHash("inventory");

    // --- ADD --------------------------------------------------------- //
    await page.locator("#invAddBtn").click();
    await expect(page.locator("#invModal")).toBeVisible();
    await page.locator("#invFormHostname").fill(hostname);
    await page.locator("#invFormIp").fill(ip);
    await page.locator("#invFormFabric").fill("E2E-FAB");
    await page.locator("#invFormSite").fill("E2E-Site");
    await page.locator("#invFormHall").fill("E2E-Hall");
    await page.locator("#invFormVendor").fill("Arista");
    await page.locator("#invFormRole").fill("Leaf");

    const addPost = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/inventory/device") &&
        r.request().method() === "POST",
    );
    await page.locator("#invModalSave").click();
    const addRes = await addPost;
    expect(addRes.status()).toBeLessThan(400);

    // Modal closes; the new row appears in the table.
    await expect(page.locator("#invModal")).toBeHidden();
    const row = page.locator("#invTbody tr", { hasText: hostname });
    await expect(row).toBeVisible();
    await expect(row).toContainText(ip);

    // --- EDIT -------------------------------------------------------- //
    // Selection is driven by the per-row .inv-row-cb checkbox (app.js:
    // invSelectedHostnames is a Set toggled on cb change), NOT by
    // clicking the <tr>. The Edit button is enabled when exactly one
    // checkbox is checked.
    await row.locator("input.inv-row-cb").check();
    await expect(page.locator("#invEditBtn")).toBeEnabled();
    await page.locator("#invEditBtn").click();
    await expect(page.locator("#invModal")).toBeVisible();
    await page.locator("#invFormRole").fill("Spine");

    const editPut = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/inventory/device") &&
        r.request().method() === "PUT",
    );
    await page.locator("#invModalSave").click();
    const editRes = await editPut;
    expect(editRes.status()).toBeLessThan(400);
    await expect(page.locator("#invModal")).toBeHidden();

    // --- DELETE ------------------------------------------------------ //
    // Re-locate the row (re-rendered after edit) and open the modal again
    // so the Delete button (only shown in edit mode) is reachable.
    const refreshedRow = page.locator("#invTbody tr", { hasText: hostname });
    await refreshedRow.locator("input.inv-row-cb").check();
    await expect(page.locator("#invEditBtn")).toBeEnabled();
    await page.locator("#invEditBtn").click();
    await expect(page.locator("#invModal")).toBeVisible();

    // DELETE is a query-string call: /api/inventory/device?hostname=...
    // (app.js:4008), so endsWith("/device") is wrong — match the path
    // segment instead.
    const deleteReq = page.waitForResponse(
      (r) =>
        r.url().includes("/api/inventory/device") &&
        r.request().method() === "DELETE",
    );
    await page.locator("#invModalDelete").click();
    const delRes = await deleteReq;
    expect(delRes.status()).toBeLessThan(400);

    // Row gone.
    await expect(
      page.locator("#invTbody tr", { hasText: hostname }),
    ).toHaveCount(0);
  });
});
