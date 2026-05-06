import { defineConfig, devices } from "@playwright/test"
import { dirname, resolve } from "path"
import { fileURLToPath } from "url"
import {
  BACKEND_PORT,
  BACKEND_URL,
  FRONTEND_PORT,
  FRONTEND_URL,
  KILN_SERVER_MOCK_PORT,
  KILN_SERVER_MOCK_URL,
  MOCK_PROVIDER_PORT,
  MOCK_PROVIDER_URL,
} from "./tests/e2e/ports"

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
    baseURL: FRONTEND_URL,
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
        KILN_PORT: String(BACKEND_PORT),
        KILN_FRONTEND_PORT: String(FRONTEND_PORT),
        HOME: TEST_HOME,
        // Route the generated kiln_ai_server_client (api.kiln.tech) to the
        // localhost mock so copilot/spec/entitlement flows never hit the
        // real hosted server during e2e tests.
        KILN_SERVER_BASE_URL: KILN_SERVER_MOCK_URL,
      },
      url: `${BACKEND_URL}/openapi.json`,
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
      env: {
        VITE_API_PORT: String(BACKEND_PORT),
        VITE_BRANCH_NAME: "",
      },
      url: FRONTEND_URL,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      // Run via plain `node` — Node 22.6+ strips TS types natively, so no extra
      // dep (tsx/ts-node) is needed. Avoids tsx's per-process IPC pipe.
      command: `node ./tests/e2e/mock_provider/server.ts`,
      env: {
        MOCK_PROVIDER_PORT: String(MOCK_PROVIDER_PORT),
      },
      url: `${MOCK_PROVIDER_URL}/__state`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: `node ./tests/e2e/mock_kiln_server/server.ts`,
      env: {
        KILN_SERVER_MOCK_PORT: String(KILN_SERVER_MOCK_PORT),
      },
      url: `${KILN_SERVER_MOCK_URL}/ping`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
})
