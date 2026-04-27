---
status: complete
---

# Phase 2: Backfill agentInfo.set() Calls + CI Coverage Test

## Overview

Add `agentInfo.set()` calls to all 87 `+page.svelte` files under `src/routes/` so every page provides name and description context for the chat agent. Add a CI coverage test that scans all page files and asserts each contains an `agentInfo.set(` or `agentInfo.update(` call.

## Steps

1. Add `import { agentInfo } from "$lib/agent"` and an `agentInfo.set({ name, description })` call to every `+page.svelte` file under `src/routes/`.
   - Static pages get a fixed name/description.
   - Dynamic pages include relevant IDs and entity names from route params or loaded data.
   - The `agentInfo.set()` call goes in the `<script>` block, typically near the top after imports and reactive declarations.
   - For pages with route params, use reactive statements so the description updates when params change.

2. Create `app/web_ui/src/lib/agent_coverage.test.ts` that:
   - Uses `fs` and `path` to glob all `+page.svelte` files under `src/routes/`.
   - Reads each file's contents.
   - Asserts it contains `agentInfo.set(` or `agentInfo.update(`.

## Tests

- `all +page.svelte files contain agentInfo.set or agentInfo.update`: scans filesystem, asserts coverage
