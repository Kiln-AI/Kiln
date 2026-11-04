---
status: complete
---

# Implementation Plan: OpenAI Responses API for newer OpenAI models

Phases 1–3 go on **branch 1**, which merges before the app release. Phase 4 goes on **branch 2**, built on branch 1, which merges after the release is live. The full order is in [architecture §7](./architecture.md#7-release-checklist).

- **Branch 1** is `claude/pensive-cannon-3jnl5q`. It already holds the research and this spec, so its PR carries both.
- **Branch 2** is `claude/pensive-cannon-3jnl5q-model-list`. Create it from branch 1's latest commit when Phase 4 starts, and push Phase 4 only there.
- Each phase ends with the paid-test commands it added, for someone on the team to run with real keys.

## Phases

- [ ] Phase 1 (branch 1): Upgrade LiteLLM to 1.105.6 and send `store: false`.
  - `pyproject.toml` pin with its comment, and `uv.lock` (architecture §3.1).
  - `store` in `build_extra_body` (§3.5, first branch), with unit tests.
  - New `test_openai_responses_wire.py` with wire cases 1, 2 and 4 (§6).
  - Paid test: a `store: false` tool loop on `gpt_5_4_pro`.
- [ ] Phase 2 (branch 1): Reasoning summaries in the adapter.
  - Provider field `openai_reasoning_summary` set to `"auto"` on the twelve providers (§3.2).
  - Config property `open_ai_reasoning_summaries` (§3.3), and its path through `LiteLlmCoreConfig` and `LiteLlmConfig` (§3.4).
  - `reasoning_summary` in `build_extra_body` (§3.5, second branch).
  - `StreamingCompletion` fixes (§3.7): normalize reasoning deltas, put reasoning items back on the rebuilt message, and join all summary parts.
  - Internal streaming for non-streamed summary calls (§3.6). Stop and propose punting if it isn't clean (§8, decision 2).
  - Mapping for the unverified-org error (§3.8).
  - Unit tests, and wire cases 3, 5, 6 and 7.
  - Paid summaries test, and the adjustment to the thinking-level paid test (§6).
- [ ] Phase 3 (branch 1): Summaries setting in the app.
  - Desktop connect `options` and disconnect reset (§3.9).
  - The OpenAI dialog checkbox with an (i) tooltip, built with the `kiln-ui` skill (§3.10).
  - Backend and web tests.
  - Maintainer skill doc for the field (§3.11).
  - The `docs-sync` skill before the PR.
- [ ] Phase 4 (branch 2, after release): Model list changes (§4).
  - Turn tools on for the ten providers.
  - Hide `max` on GPT-6 Astra, Sol and Luna for OpenAI direct, using new constants with a comment explaining why. Reword the GPT-6.1 Sol and Terra comments to give the same reason.
  - Update the model list tests.
  - Add the branch 2 paid tests: tools at every thinking level, narration then a tool call, and the ten models added to the streaming and `return_on_tool_call` lists.
  - Finish the rest of the maintainer docs.
  - After the team's paid run, apply F6 to GPT-6.1 Terra only if tools at `none` fail. Any other `none` failure goes to the user.
