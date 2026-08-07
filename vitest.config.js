import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./tests/vitest/setup.js"],
    exclude: ["**/node_modules/**"],
    coverage: {
      provider: "v8",
      include: ["static/js/**/*.js"],
      exclude: ["static/js/**/*.min.js", "**/node_modules/**", "**/tests/**"],
      reporter: ["text", "html", "json-summary"],
      reportsDirectory: "coverage-frontend",
      thresholds: { lines: 8, functions: 40 },
    },
  },
});
