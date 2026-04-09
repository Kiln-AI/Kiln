---
status: complete
---

# Functional Spec: Typed Client Migration

## Goal

Replace three raw `fetch()` calls with the typed `openapi-fetch` client (`client` from `$lib/api_client`). This provides compile-time path checking so TypeScript errors surface if API routes are renamed or removed.

## Scope

### In Scope

- Convert the three identified `fetch()` calls to use the typed client
- Preserve existing error handling behavior (messages, UI state, posthog tracking)
- Preserve existing request/response handling logic

### Out of Scope

- Improving the backend type definitions (the `dict` params/returns that produce loose schema types)
- Changing error handling patterns or UX
- Refactoring surrounding code

## Calls to Convert

### Call 1: connect_providers.svelte — submit_api_key

- **Endpoint:** `POST /api/provider/connect_api_key`
- **Request body:** `{ provider: string, key_data: dict }`
- **Current error check:** `res.status !== 200` → show `data.message`
- **Side effects on success:** posthog capture, update provider status, clear model caches
- **Typed client equivalent:** `client.POST("/api/provider/connect_api_key", { body: { provider, key_data } })`
- **Error mapping:** The typed client returns `{ data, error }`. On error, extract message from `error.message`. On network failure, the client throws, caught by existing try/catch.

### Call 2: connect_providers.svelte — check_existing_providers

- **Endpoint:** `GET /api/settings`
- **Request:** No body
- **Current handling:** Parse response JSON, check individual keys for provider connection status
- **Typed client equivalent:** `client.GET("/api/settings")`
- **Error mapping:** On error, set `initial_load_failure = true` (same as current catch block)

### Call 3: connect_kiln_copilot_steps.svelte — submitApiKey

- **Endpoint:** `POST /api/provider/connect_api_key`
- **Request body:** `{ provider: "kiln_copilot", key_data: { "API Key": apiKey } }`
- **Current error check:** `!res.ok` → show `data.message || data.detail`
- **Side effects on success:** posthog capture, call `onSuccess()`
- **Typed client equivalent:** Same as Call 1
- **Error mapping:** Same pattern — extract from `error.message` or `error.detail`

## Error Handling Behavior

The typed client (`openapi-fetch`) returns `{ data, error, response }`:
- **HTTP errors (4xx/5xx):** `error` is populated with the parsed response body, `data` is undefined
- **Network errors:** The client throws an exception (caught by existing try/catch blocks)

Current fetch patterns check `res.status !== 200` or `!res.ok`. The typed client equivalent is checking whether `error` is truthy.

The `error` object from the typed client will contain the JSON body of the error response. Since these endpoints return `{ "message": "..." }` on error, we access `error.message`. For connect_kiln_copilot_steps which also checks `data.detail`, we check `error.detail` (FastAPI's default validation error format).
