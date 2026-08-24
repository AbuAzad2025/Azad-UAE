import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./tests/vitest/setup.js"],
    exclude: ["**/node_modules/**", "tests/e2e/**"],
    testTimeout: 10000,
    coverage: {
      provider: "v8",
      include: ["static/js/**/*.js"],
      exclude: [
        "static/js/**/*.min.js",
        "**/node_modules/**",
        "**/tests/**",
        "static/js/pos/cashier-logic.js",
      ],
      reporter: ["text", "html", "json-summary"],
      reportsDirectory: "coverage-frontend",
      thresholds: { lines: 50, functions: 60 },
    },
  },
});
