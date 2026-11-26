---
status: complete
---

# Implementation Plan: OpenCode Provider

PR 1 is phases 1–2 and can merge whenever it's ready. PR 2 is phase 3 and merges only after a client release that includes PR 1.

## Phases

- [x] Phase 1: Core provider support in `libs/core`, part of PR 1:
  - the enum member, the config key, the LiteLLM mapping, `provider_warnings`, and the core config, including `cost_from_response_usage`
  - the `built_in_providers` item
  - cost from `usage.cost`
  - the wire tests: request, cost, errors, and the provider-text-kept tests
- [x] Phase 2: Connect, disconnect and web UI, part of PR 1:
  - `connect_opencode` and the disconnect case, with tests
  - the regenerated API schema
  - `provider_name_map`, the icon from `assets/opencode.svg`, and the connect card with the approved copy
  - the web tests
- [ ] Phase 3: Model catalog and skills, all of PR 2:
  - OpenCode entries on existing `KilnModel`s for the default-enabled paid chat models, with flags set by the paid tests
  - the test and tooling lists
  - the `claude-maintain-models` and `kiln-check-deprecation` skill updates
