---
status: draft
---

# Implementation Plan: Cloudflare Provider

Details for every phase are in [architecture.md](./architecture.md). Every phase must leave all checks green (`uv run ./checks.sh --agent-mode`).

## PR 1: Provider Support

- [ ] Phase 1: Backend and required web plumbing. Add the `cloudflare` enum value, the three config properties, the LiteLLM wiring (`is_custom`, the Cloudflare URL and header helpers, the core config case), the provider name and warnings, and `connect_cloudflare` and disconnect in `provider_api.py`. Web plumbing that the new enum value forces: regenerate `api_schema.d.ts`, add the `stores.ts` name map entry, add the `provider_image.ts` entry, and add the cleaned, cropped `cloudflare.svg`. Include all core and server tests, including the `respx` wiring and rate-limit tests.
- [ ] Phase 2: Connect-screen UI. Add the Cloudflare card in `connect_providers.svelte` with the approved strings from [ui_design.md](./ui_design.md), the status entry, connected-state detection, and `connect_providers.test.ts` coverage.

## PR 2: Models and Skills (after a client release that includes PR 1)

- [ ] Phase 3: Add the 10 `ml_model_list.py` entries, with per-model flags set by the maintain-models skill's per-model tests, and the prerelease whitelist entry. Add Cloudflare support to `provider_utils.py` and the deprecation-check script, and update the maintain-models, deprecation-check and prerelease-check skill docs.
