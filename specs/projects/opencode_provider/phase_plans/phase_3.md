---
status: complete
---

# Phase 3: OpenCode model catalog and skills

## Overview

Add `opencode` provider entries to the existing `KilnModel`s that OpenCode enables by default as paid chat models, with flags set by the paid tests run through OpenCode's Chat Completions path. Add OpenCode to the paid-test and prerelease lists, and teach the model-maintenance, deprecation-check and thinking-level tooling about OpenCode so the entries stay current. This is all of PR 2, which merges only after a client release that includes phases 1–2.

## Steps

1. Build the source list from `GET https://opencode.ai/inference/v1/models` (default-settings workspace): `type == "chat"`, non-zero price, no `-free` suffix, not on the docs page's "Deprecated models" table, not a pure coding model, and an existing `KilnModel` matched on `canonical_id` (cross-checked with models.dev `opencode`).

2. `libs/core/kiln_ai/adapters/ml_model_list.py`: for each match, append after the model's other providers:
   ```python
   KilnModelProvider(
       name=ModelProviderName.opencode,
       model_id="<OpenCode id>",
       structured_output_mode=StructuredOutputMode.json_schema,
       # suggested_for_* copied from the model's other entries
       # vision + MIME types from modalities.input ∩ the native entry, plus TXT/MD
       # temp_top_p_exclusive=True on Claude
       available_thinking_levels=<constant matching capabilities.reasoning.effort>,
       default_thinking_level=<native/OpenRouter default if listed; judge rule for suggested_for_evals>,
   )
   ```
   Reuse an existing `_THINKING_LEVELS` constant when the values match exactly; otherwise add `{MODEL}_OPENCODE_THINKING_LEVELS` under one comment naming the source. Narrow flags (structured-output mode, MIME types) on paid-test failures; leave out models that can't pass.

3. `model_adapters/test_thinking_level_paid.py`: add `ModelProviderName.opencode` to the provider list; add OpenCode cases where the provider can't surface reasoning text, so only a successful run is checked.

4. `test_prompt_adaptors.py`: `test_opencode` smoke test (paid, prerelease), skipped without `OPENCODE_API_KEY`, running `claude_haiku_5_5`.

5. `pytest_prerelease_whitelist.py`: `("claude_haiku_5_5", ModelProviderName.opencode.value)` in `PRERELEASE_CHAT_MODELS`.

6. `.agents/scripts/provider_utils.py`: `opencode` in `PROVIDER_CONFIG` (`OPENCODE_API_KEY`); `fetch_opencode_models`, `parse_opencode_deprecations` (docs table → `{name_key: ISO date}`), `opencode_availability` and `fetch_opencode` returning `(ids, deprecation_dates)`.

7. `kiln-check-deprecation/scripts/check_provider.py`: an `opencode` type using `fetch_opencode`, reporting table dates under `expiring`. `extract_models.py` already extracts every non-skipped provider, so it needs no change.

8. `claude-maintain-models/scripts/check_thinking_levels.py`: `opencode` provider reading `capabilities.reasoning.effort`, strict like Cloudflare, skipped when `OPENCODE_API_KEY` is unset.

9. Skills:
   - `claude-maintain-models/SKILL.md`: an OpenCode Provider Quirks section (source list and default-workspace rule, inclusion rule and how to spot free, decision, image, embedding, video and realtime models, flags, thinking levels via `reasoning_effort`, deprecations, paid-test key); OpenCode in the Phase 1B lagging check, the model-id table, the Thinking Levels Reference, the checklist and the Lagging Providers reference.
   - `kiln-check-deprecation/SKILL.md`: OpenCode quirks, the env table, and the deprecation rule: flag each entry on the deprecated table to the user, and deprecate it only once its date has passed and a call returns 410 `ModelDeprecated`, or once the model drops off the models list. This replaces the spec's "deprecate before the listed date", because table dates don't reliably mean a model is gone (`gpt-5.1-codex-mini`, dated July 23, 2026, still returned 200 on Nov 22, 2026).
   - `kiln-prerelease-check/SKILL.md`: `OPENCODE_API_KEY` in the env list.

## Tests

- Paid suites for every OpenCode entry (`--runpaid --ollama -k opencode`): data gen, structured output and input, chain of thought, plaintext, LLM-as-judge, tools, thinking levels per level, and document extraction per MIME type.
- `test_opencode` smoke test passes with the key and skips without it.
- `test_ml_model_list.py`, `test_model_agent_info.py`, `test_ml_provider_list.py`: the new entries pass the existing list rules (judge defaults, prerelease models exist).
- `test_check_thinking_levels.py`: `opencode_efforts` reads `capabilities.reasoning.effort` (missing list → `None`); OpenCode findings are strict.
- `.agents/scripts/test_provider_utils.py`: name normalisation; the deprecated table parses to ISO dates and only that table is read; a missing table raises; availability matches by display name, then by id.
