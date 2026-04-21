import { test, expect } from "./fixtures"
import { COPILOT_TEST_API_KEY } from "./mock_kiln_server/client"

/* @act
## Goals
Sanity-check the kiln-server mock (api.kiln.tech stand-in). With a copilot API
key seeded into Config and KILN_SERVER_BASE_URL pointed at the mock, calling
the backend's /api/check_entitlements endpoint should route through the mock,
carry the seeded key in an Authorization: Bearer header, and return the mock's
default entitlements payload.

This test verifies the full plumbing of Phase 2 kiln-server mocking:
  1. KILN_SERVER_BASE_URL env var overrides the generated client's base URL
     (set by playwright.config.ts on the backend webServer).
  2. seededCopilotKey fixture: POST /api/settings persists kiln_copilot_api_key,
     so the backend can call get_copilot_api_key() without OAuth.
  3. mockKilnServer fixture: queue/reset against the mock admin surface.
  4. The backend's get_authenticated_client() wires the key as a bearer token
     that the mock actually receives.

Future test authors extend mock_kiln_server/server.ts with the endpoints their
tests need; this sanity test only exercises auth + a single entitlement call.

## Fixtures
- seededCopilotKey
- mockKilnServer

## Assertions
- GET /api/check_entitlements?feature_codes=act-ping returns 200 with
  { "act-ping": true }.
- The mock received exactly one GET /v1/check_entitlements.
- That request's Authorization header was "Bearer <seeded key>".
*/
test("kiln-server mock: /api/check_entitlements round-trips auth + default response", async ({
  apiRequest,
  seededCopilotKey,
  mockKilnServer,
}) => {
  void seededCopilotKey

  const resp = await apiRequest.get(
    "/api/check_entitlements?feature_codes=act-ping",
  )
  expect(
    resp.ok(),
    `GET /api/check_entitlements failed: ${resp.status()} ${await resp.text()}`,
  ).toBeTruthy()
  const body = (await resp.json()) as Record<string, boolean>
  expect(body["act-ping"]).toBe(true)

  const state = await mockKilnServer.state()
  const calls = state.requests.filter(
    (r) => r.method === "GET" && r.path === "/v1/check_entitlements",
  )
  expect(calls.length, "mock saw exactly one entitlements call").toBe(1)
  expect(calls[0].authorization).toBe(`Bearer ${COPILOT_TEST_API_KEY}`)
})
