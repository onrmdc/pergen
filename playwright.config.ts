import { defineConfig, devices } from "@playwright/test";

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
    },
  },
});
