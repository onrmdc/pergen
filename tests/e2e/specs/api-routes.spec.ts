import { expect, test } from "@playwright/test";

/**
 * Backend smoke: every read-only API endpoint the SPA hits during page
 * load should answer with a non-5xx status. We intentionally only
 * exercise GET endpoints — POST/PUT/DELETE belong to dedicated flow
 * specs because they mutate state.
 *
 * If the SPA later wires a new GET endpoint, add it here so the smoke
 * suite catches obvious regressions (broken blueprint registration,
 * import failures, schema crashes, etc.).
 */
const READ_ONLY_ROUTES = [
  "/api/health",
  "/api/v2/health",
  "/api/inventory",
  "/api/fabrics",
  "/api/sites",
  "/api/halls",
  "/api/roles",
  "/api/devices",
  "/api/devices-arista",
  "/api/credentials",
  "/api/commands",
  "/api/parsers/fields",
  "/api/notepad",
  "/api/reports",
  "/api/router-devices",
];

test.describe("Backend API smoke", () => {
  for (const route of READ_ONLY_ROUTES) {
    test(`GET ${route} responds without 5xx`, async ({ request }) => {
      const res = await request.get(route);
      expect(res.status(), `unexpected ${res.status()} from ${route}`).toBeLessThan(
        500,
      );
    });
  }
});
