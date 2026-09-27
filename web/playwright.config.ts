import { defineConfig, devices } from "@playwright/test";

/*
  End-to-end smoke test: the production build, served by the BFF (127.0.0.1:8090) with the
  development identity, in front of the stand-in admin API (127.0.0.1:8001). Build first:
  `npm run build && npm run e2e`. PYTHON is the interpreter with the BFF's requirements.
*/
const python = process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://127.0.0.1:8090",
    trace: "retain-on-failure",
    // Every /bff call needs this header; the SPA sends it, and so do these tests' own requests.
    extraHTTPHeaders: { "X-Requested-With": "admin" },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: {
    command: `${python} ../scripts/dev.py`,
    url: "http://127.0.0.1:8090/healthz",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: { STUB_LIVE_EVENTS: "1", STUB_LIVE_INTERVAL: "2" },
  },
});
