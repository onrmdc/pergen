import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * P0 — Inventory CSV import + export round-trip.
 *
 * Inventory mutating flows had no E2E coverage of Import / Export. This
 * spec uploads a small CSV via the file input, mocks the /api/inventory
 * surface so the import POST returns a deterministic result without
 * touching the real on-disk inventory, then triggers Export and asserts
 * the downloaded CSV body.
 */
test("inventory CSV import then export round-trips through the UI", async ({
  page,
}) => {
  const stamp = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  const importHostname = `e2e-import-${stamp}`;

  // The SPA shows alert() on success; auto-accept so the run does not block.
  page.on("dialog", (d) => d.accept());

  // Mock /api/inventory list so the page renders our chosen device set
  // (used both as the post-import state and as the export source).
  const mockInventory = [
    {
      hostname: importHostname,
      ip: "10.55.55.1",
      fabric: "IMP-FAB",
      site: "IMP-Site",
      hall: "IMP-Hall",
      vendor: "Arista",
      model: "EOS",
      role: "Leaf",
      tag: "",
      credential: "test-cred",
    },
  ];
  await page.route("**/api/inventory", (route) => {
    if (route.request().method() === "GET") {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ inventory: mockInventory }),
      });
    } else {
      route.fallback();
    }
  });

  let importCalled = false;
  await page.route("**/api/inventory/import", (route) => {
    importCalled = true;
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ added: 1, skipped: [] }),
    });
  });

  const app = new AppShell(page);
  await app.gotoHash("inventory");

  // --- IMPORT ------------------------------------------------------ //
  // The Import button proxies a click to the hidden #invFileInput.
  // We can set files directly on that file input; that fires `change`
  // which calls invImportCsv(file).
  const csv =
    "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n" +
    `${importHostname},10.55.55.1,IMP-FAB,IMP-Site,IMP-Hall,Arista,EOS,Leaf,,test-cred\n`;

  await page.locator("#invFileInput").setInputFiles({
    name: "inventory_e2e.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv, "utf-8"),
  });

  await expect.poll(() => importCalled, { timeout: 5_000 }).toBe(true);

  // The mocked inventory list should now be visible.
  await expect(page.locator("#invTbody tr", { hasText: importHostname })).toBeVisible({
    timeout: 5_000,
  });

  // --- EXPORT ------------------------------------------------------ //
  // The Export button builds a CSV client-side and triggers a download
  // via an in-memory anchor click. We capture the download event to
  // read the resulting CSV body.
  const downloadPromise = page.waitForEvent("download");
  await page.locator("#invExportBtn").click();
  const download = await downloadPromise;

  expect(download.suggestedFilename()).toBe("inventory_export.csv");

  const path = await download.path();
  expect(path).toBeTruthy();
  const fs = await import("node:fs");
  const exportedCsv = fs.readFileSync(path!, "utf-8");
  expect(exportedCsv).toContain("hostname");
  expect(exportedCsv).toContain(importHostname);
  expect(exportedCsv).toContain("10.55.55.1");
});
