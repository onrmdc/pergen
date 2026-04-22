import { defineConfig } from "vitest/config";

/**
 * Vitest config for Pergen frontend unit tests.
 *
 * Scope (today): the small set of pure helpers extracted into
 * ``backend/static/js/lib/*.js``. The bulk of the SPA still lives in
 * the ``app.js`` IIFE and is exercised end-to-end by the Playwright
 * suite under ``tests/e2e/``.
 *
 * Once helpers are migrated out of the IIFE, point ``include`` at the
 * matching unit-test files.
 */
export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    include: ["tests/frontend/unit/**/*.spec.ts", "tests/frontend/unit/**/*.spec.js"],
    coverage: {
      reporter: ["text", "html"],
      include: ["backend/static/js/lib/**/*.js"],
      thresholds: {
        statements: 80,
        branches: 80,
        functions: 80,
        lines: 80,
      },
    },
  },
});
