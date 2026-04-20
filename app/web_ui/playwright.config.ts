import { defineConfig, devices } from "@playwright/test"
import { dirname, resolve } from "path"
import { fileURLToPath } from "url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const TEST_HOME = resolve(__dirname, ".e2e_home")

/**
 * Read environment variables from file.
 * https://github.com/motdotla/dotenv
 */
// import dotenv from 'dotenv';
// import path from 'path';
// dotenv.config({ path: path.resolve(__dirname, '.env') });

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  /* Wait until both backend + frontend actually respond to real requests before tests run.
     The webServer `url` checks below are one-shot 200 probes — globalSetup adds a real
     readiness poll so a page load's own fetches don't race a still-warming service. */
  globalSetup: "./tests/e2e/global-setup.ts",
  /* Tests share one backend (protected by HOME isolation). Run serial to avoid state collisions. */
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: "html",
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    baseURL: "http://localhost:6534",
    trace: "on-first-retry",
  },

  /* Configure projects for major browsers */
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },

    // {
    //   name: 'firefox',
    //   use: { ...devices['Desktop Firefox'] },
    // },

    // {
    //   name: 'webkit',
    //   use: { ...devices['Desktop Safari'] },
    // },

    /* Test against mobile viewports. */
    // {
    //   name: 'Mobile Chrome',
    //   use: { ...devices['Pixel 5'] },
    // },
    // {
    //   name: 'Mobile Safari',
    //   use: { ...devices['iPhone 12'] },
    // },

    /* Test against branded browsers. */
    // {
    //   name: 'Microsoft Edge',
    //   use: { ...devices['Desktop Edge'], channel: 'msedge' },
    // },
    // {
    //   name: 'Google Chrome',
    //   use: { ...devices['Desktop Chrome'], channel: 'chrome' },
    // },
  ],

  webServer: [
    {
      command: `rm -rf "${TEST_HOME}" && mkdir -p "${TEST_HOME}" && uv run python -m app.desktop.dev_server`,
      cwd: "../..",
      env: {
        KILN_PORT: "6535",
        KILN_FRONTEND_PORT: "6534",
        HOME: TEST_HOME,
      },
      url: "http://localhost:6535/openapi.json",
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: "npm run dev -- --port 6534 --strictPort",
      env: { VITE_API_PORT: "6535", VITE_BRANCH_NAME: "" },
      url: "http://localhost:6534",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
})
