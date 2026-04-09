---
status: complete
---

# Typed Client Migration

Migrate three remaining raw `fetch()` calls in the Svelte frontend to use the typed `openapi-fetch` client (`client` from `$lib/api_client`). This ensures compile-time path checking so that if API routes change, TypeScript catches the breakage rather than it silently failing at runtime.

## Calls to Migrate

1. **connect_providers.svelte ~line 652** — `POST /api/provider/connect_api_key` (submitting provider API keys)
2. **connect_providers.svelte ~line 703** — `GET /api/settings` (checking which providers are already connected)
3. **connect_kiln_copilot_steps.svelte ~line 102** — `POST /api/provider/connect_api_key` (submitting Kiln Copilot API key)

## Context

- The rest of the frontend already uses the typed client consistently.
- Both endpoints (`/api/provider/connect_api_key` and `/api/settings`) exist in the generated OpenAPI schema.
- The schema types for these endpoints are loose (`{ [key: string]: unknown }`) because the backend uses untyped `dict` params/returns, but the typed client still provides path-level compile-time safety.
