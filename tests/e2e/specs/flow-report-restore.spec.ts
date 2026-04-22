import { expect, test } from "@playwright/test";
import { AppShell } from "../pages/AppShell";

/**
 * Wave-4 P0 — POST /api/reports/<id>/restore happy path
 *
 * Closes one of the 3 P0 gaps surfaced by the wave-4 e2e gap analysis.
 * The wave-3 Phase 4 fix moved restore from GET ?restore=1 to POST
 * /restore; this spec exercises the SPA-side flow that calls the new
 * endpoint when the user opens an old report from the Reports page.
 *
 * Verifies:
 *   - GET /api/reports loads the report list (legacy read path)
 *   - GET /api/reports/<id> reads a single report (legacy)
 *   - POST /api/reports/<id>/restore (the wave-3 new endpoint)
 *
 * Note: the W4-M-01 cross-actor refusal contract is pinned at the
 * unit-test layer by test_security_report_restore_actor_scoping.py
 * (currently strict-xfail).
 */
test("Reports page restore flow calls POST /api/reports/<id>/restore", async ({
  page,
}) => {
  const reportRid = `e2e-restore-${Date.now()}`;

  // Reports list endpoint
  await page.route("**/api/reports", (route) => {
    if (route.request().method() === "GET") {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          reports: [
            {
              run_id: reportRid,
              name: "wave4-e2e-restore",
              created_at: "2026-04-22T00:00:00Z",
              post_created_at: null,
            },
          ],
        }),
      });
    } else {
      route.fallback();
    }
  });

  // Single-report fetch
  await page.route(`**/api/reports/${reportRid}`, (route) => {
    if (route.request().method() === "GET") {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          run_id: reportRid,
          name: "wave4-e2e-restore",
          created_at: "2026-04-22T00:00:00Z",
          devices: [{ hostname: "leaf-restore-01", ip: "10.70.0.1" }],
          device_results: [
            { hostname: "leaf-restore-01", ok: true, parsed_flat: { Version: "4.30.0F" } },
          ],
        }),
      });
    } else {
      route.fallback();
    }
  });

  // The new POST /restore endpoint
  let restoreCalled = false;
  let restoreMethod = "";
  await page.route(`**/api/reports/${reportRid}/restore`, (route) => {
    restoreCalled = true;
    restoreMethod = route.request().method();
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, run_id: reportRid }),
    });
  });

  const app = new AppShell(page);
  await app.gotoHash("prepost");
  // Scroll to the reports listing on the prepost page (it lives there).
  await page.locator("#savedReportsDetails").scrollIntoViewIfNeeded();
  await page.locator("#savedReportsDetails").click({ force: true });

  // Click the report row — the SPA fetches the full report + restores it.
  const row = page.locator("#savedReportsList li", { hasText: "wave4-e2e-restore" });
  await expect(row).toBeVisible({ timeout: 5_000 });
  await row.click();

  // The SPA may show a confirmation dialog before restore — accept any.
  page.on("dialog", (d) => d.accept());

  // Wait for the restore call to land. The SPA may need a button click first.
  // The wave-3 flow uses GET → then POST /restore as a separate call.
  await expect
    .poll(() => restoreCalled, { timeout: 8_000 })
    .toBe(true);

  // Method must be POST (audit M-03).
  expect(restoreMethod).toBe("POST");
});
