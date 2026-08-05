import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./tests/vitest/setup.js"],
    exclude: ["**/node_modules/**", "**/tests/vitest/{base_helpers,form_validation,notifications}.test.js"],
    coverage: {
      provider: "v8",
      include: ["static/js/**/*.js"],
      exclude: ["static/js/**/*.min.js", "**/node_modules/**", "**/tests/**"],
      reporter: ["text", "html", "json-summary"],
      reportsDirectory: "coverage-frontend",
      thresholds: { lines: 0, functions: 0 },
    },
  },
});
