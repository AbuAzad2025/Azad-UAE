import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    coverage: {
      provider: "v8",
      include: ["static/js/**/*.js"],
      exclude: ["static/js/**/*.min.js", "**/node_modules/**"],
      reporter: ["text", "html", "clover"],
      reportsDirectory: "coverage-frontend",
      thresholds: { lines: 0, functions: 0 },
    },
  },
});
