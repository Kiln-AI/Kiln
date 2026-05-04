import { readFileSync } from "node:fs"
import { sentrySvelteKit } from "@sentry/sveltekit"
import { sveltekit } from "@sveltejs/kit/vite"
import { defineConfig } from "vitest/config"

// The Sentry release name must match the value sent at runtime from
// hooks.client.ts so uploaded source maps map back to incoming events.
// CI overrides VITE_KILN_SENTRY_RELEASE for non-release builds (commit SHA);
// for releases and local builds we fall back to the app version, which is
// also imported by src/lib/utils/update.ts so both stay in sync.
const appVersion = readFileSync("./src/lib/version", "utf-8").trim()
const sentryRelease =
  process.env.VITE_KILN_SENTRY_RELEASE || `kiln-studio-web@${appVersion}`

const sentryPlugin = process.env.SENTRY_AUTH_TOKEN
  ? sentrySvelteKit({
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      authToken: process.env.SENTRY_AUTH_TOKEN,
      release: { name: sentryRelease },
    })
  : null

export default defineConfig({
  plugins: [...(sentryPlugin ? [sentryPlugin] : []), sveltekit()],
  test: {
    include: ["src/**/*.{test,spec}.{js,ts}"],
  },
})
