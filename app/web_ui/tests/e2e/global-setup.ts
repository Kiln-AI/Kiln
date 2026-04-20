import { request } from "@playwright/test"
import { BACKEND_URL, FRONTEND_URL } from "./ports"

const POLL_TIMEOUT_MS = 60_000
const POLL_INTERVAL_MS = 250
const STABLE_SUCCESSES = 3

async function waitFor(
  label: string,
  url: string,
  check: (status: number, bodySample: string) => boolean,
): Promise<void> {
  const ctx = await request.newContext()
  try {
    const deadline = Date.now() + POLL_TIMEOUT_MS
    let lastError = "never responded"
    let successes = 0

    while (Date.now() < deadline) {
      try {
        const resp = await ctx.get(url, { timeout: 2_000 })
        const body = await resp.text().catch(() => "")
        if (check(resp.status(), body)) {
          successes += 1
          if (successes >= STABLE_SUCCESSES) return
        } else {
          successes = 0
          lastError = `status=${resp.status()} body=${body.slice(0, 120)}`
        }
      } catch (e) {
        successes = 0
        lastError = e instanceof Error ? e.message : String(e)
      }
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
    }
    throw new Error(
      `[global-setup] ${label} not ready after ${POLL_TIMEOUT_MS}ms (${url}): ${lastError}`,
    )
  } finally {
    await ctx.dispose()
  }
}

export default async function globalSetup() {
  await Promise.all([
    waitFor(
      "backend",
      `${BACKEND_URL}/api/projects`,
      (status) => status === 200,
    ),
    waitFor(
      "frontend",
      `${FRONTEND_URL}/`,
      (status, body) =>
        status === 200 && body.toLowerCase().includes("<!doctype html"),
    ),
  ])
}
