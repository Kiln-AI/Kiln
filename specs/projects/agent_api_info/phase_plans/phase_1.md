---
status: draft
---

# Phase 1: Port `prompt_type_label` to Python + Surface `type` on `ApiPrompt`

## Overview

Create a single source of truth for prompt type labels by porting the TS `getPromptType` function to Python, adding a `type` field to the `ApiPrompt` response model, and switching the Svelte UI to consume the server-computed `type` instead of re-deriving it client-side.

## Steps

1. Create `libs/core/kiln_ai/datamodel/prompt_type.py` with `prompt_type_label(prompt_id: str, generator_id: str | None) -> str` function and `_GENERATOR_LABELS` dict, matching the TS logic exactly.

2. Add `type: str` field to `ApiPrompt` in `libs/server/kiln_server/prompt_api.py`. Compute it via `prompt_type_label` in the `get_prompts` endpoint when constructing `ApiPrompt` instances (both custom prompts and task_run_config prompts). Also update the `update_prompt` handler's return value.

3. Update `app/web_ui/src/routes/(app)/prompts/[project_id]/[task_id]/+page.svelte`:
   - Remove the `getPromptType` import
   - Replace `getPromptType(prompt.id, prompt.generator_id)` calls with `prompt.type`
   - In the sort comparator for "type", use `a.type` / `b.type` instead of `getPromptType(...)`.

4. Update `app/web_ui/src/routes/(app)/prompts/[project_id]/[task_id]/saved/[prompt_id]/+page.svelte`:
   - Remove the `getPromptType` import
   - Replace `getPromptType(prompt_model?.id || "", prompt_model?.generator_id || null)` with `prompt_model?.type ?? "Unknown"`

5. Delete the `getPromptType` function from `app/web_ui/src/routes/(app)/prompts/[project_id]/[task_id]/prompt_generators/prompt_generators.ts` (lines 102-116).

6. Regenerate the OpenAPI schema via `generate_schema.sh` to pick up the new `type` field on `ApiPrompt`.

## Tests

- `libs/core/kiln_ai/datamodel/test_prompt_type.py`: Golden table test covering every branch:
  - `fine_tune_prompt::xxx` -> "Fine-Tune"
  - `task_run_config::xxx` -> "Frozen"
  - Each of the 7 generator IDs -> their respective labels
  - `id::xxx` with no generator_id -> "Custom"
  - Unknown prompt_id with no generator_id -> "Unknown"
  - `id::xxx` with unknown generator_id -> "Custom" (falls through generator lookup)
- Existing `test_prompt_api.py` tests continue to pass (additive `type` field).
- Existing Svelte tests continue to pass.
