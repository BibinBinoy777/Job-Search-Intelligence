import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  outputDir: "test-results-live",
  testDir: "./live-e2e",
  workers: 1,
  retries: 0,
  timeout: 60000,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:5173", ...devices["Desktop Chrome"] },
});
