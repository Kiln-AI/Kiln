---
status: complete
---

# Phase 1: Convert all three fetch() calls to typed client

## Overview

Replace three raw `fetch()` calls with the typed `openapi-fetch` client to get compile-time path checking.

## Steps

1. **connect_providers.svelte — submit_api_key (~line 652):** Replace `fetch(base_url + "/api/provider/connect_api_key", ...)` with `client.POST("/api/provider/connect_api_key", { body: { provider, key_data } })`. Change error check from `res.status !== 200` to `if (error)`, accessing `error.message`.

2. **connect_providers.svelte — check_existing_providers (~line 703):** Replace `fetch(base_url + "/api/settings")` with `client.GET("/api/settings")`. Use `data` directly from destructured return. On error, set `initial_load_failure = true`.

3. **connect_providers.svelte — import cleanup:** Remove `base_url` from the import since it is no longer used in this file.

4. **connect_kiln_copilot_steps.svelte — submitApiKey (~line 102):** Replace `fetch(base_url + "/api/provider/connect_api_key", ...)` with `client.POST(...)`. Change error check from `!res.ok` to `if (error)`, accessing `error.message || error.detail`. Update import from `base_url` to `client`.

## Tests

- No new tests needed — this is a 1:1 behavioral replacement with existing coverage
