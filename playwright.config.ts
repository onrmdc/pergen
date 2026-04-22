import { defineConfig, devices } from "@playwright/test";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

// Audit fix (E2E gap analysis 2026-04-22): give the webServer a per-run
// instance directory + inventory CSV so flow specs do not pollute the
// operator's real `instance/` and `inventory.csv`. Reuses the existing
// real files when reuseExistingServer kicks in (server already up).
const _e2eRoot = fs.mkdtempSync(path.join(os.tmpdir(), "pergen-e2e-"));
const _instanceDir = path.join(_e2eRoot, "instance");
const _inventoryCsv = path.join(_e2eRoot, "inventory.csv");
fs.mkdirSync(_instanceDir, { recursive: true });
// Seed two devices so list/render specs have something to look at.
fs.writeFileSync(
  _inventoryCsv,
  "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n" +
    "leaf-e2e-01,10.0.0.1,FAB1,Mars,Hall-1,Arista,EOS,Leaf,leaf-search,test-cred\n" +
    "leaf-e2e-02,10.0.0.2,FAB1,Mars,Hall-1,Cisco,NX-OS,Leaf,,test-cred\n",
  "utf-8",
);

/**
 * Playwright config for the Pergen E2E suite.
 *
 * The Flask app is started by Playwright via `webServer` so `npm run e2e`
 * is a single command. If the server is already up on port 5000 we
 * reuse it (faster local iteration).
 */
export default defineConfig({
  testDir: "./tests/e2e/specs",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 1,
  workers: process.env.CI ? 2 : undefined,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
    ["junit", { outputFile: "test-results/junit.xml" }],
  ],
  timeout: 30_000,
  expect: { timeout: 5_000 },
  use: {
    baseURL: "http://127.0.0.1:5000",
    headless: true,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "on-first-retry",
    actionTimeout: 5_000,
    navigationTimeout: 10_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "./run.sh",
    url: "http://127.0.0.1:5000/api/health",
    reuseExistingServer: true,
    stdout: "ignore",
    stderr: "pipe",
    timeout: 30_000,
    env: {
      FLASK_RUN_HOST: "127.0.0.1",
      FLASK_RUN_PORT: "5000",
      FLASK_CONFIG: "development",
      // Hermetic per-run state — see audit-fix block above.
      PERGEN_INSTANCE_DIR: _instanceDir,
      PERGEN_INVENTORY_PATH: _inventoryCsv,
    },
  },
});
