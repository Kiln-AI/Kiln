---
status: complete
---

# Functional Spec: Evals V2 — LLM-as-Judge Prompt Regression Fix

## Summary

Restore a rich, V1-fidelity auto-filled judge prompt for V2 `llm_judge` eval configs, and
make it (and the system prompt) fully editable in the create UI. The rich content is
assembled server-side from data already stored on the eval's task and spec — no datamodel
changes, no LLM calls at judge-creation time.

## Goals

1. The auto-filled judge prompt leverages the user's existing work — the task instruction
   and the spec definition (which already concatenates the spec's description + examples) —
   not just the generic one-liner `"Evaluate if the model's behaviour meets the spec: {name}"`.
2. The judge prompt and the system prompt are editable during creation. Auto-fill is a
   starting point; the user can change anything.
3. Creating the judge remains **deterministic** (no LLM call). The assembly is a pure
   function of the eval + task + spec.
4. The "test your judge" flow uses the same (possibly edited) prompt + system prompt, so the
   test reflects what will be saved.

## Non-Goals / Out of Scope

- No datamodel/storage changes (no new fields on Eval/Spec/EvalConfig; no snapshotting).
- No Copilot V1→V2 eval-config migration (tracked separately in `eval_copilot_builder_v2`).
- No structured `task_description` / `eval_steps` concepts surfaced in the API or UI — the
  judge prompt is a single string end to end.
- `thinking_instruction` stays a server default and is not user-editable here. For **g-eval**
  this means the chain-of-thought is driven by the generic default rather than V1's explicit
  per-step thinking instruction, so g-eval scoring may differ slightly from V1. Accepted.

## Rendering model (decided)

The stored `prompt_template` continues to be rendered with the existing sandboxed **Jinja2**
engine (`_template_env`) at eval time. We keep full Jinja on purpose — power like
`{{ reference_data['answer'] }}` subscripts, `{{ trace }}`, and filters must keep working.

The change is only in how the **assembled default** protects baked prose from being parsed as
Jinja:

- **Conditional, per-piece `{% raw %}`.** Each injected value (the task instruction, the spec
  definition, a score instruction) is checked for the Jinja opening delimiters `{{`, `{%`, or
  `{#`. If none are present (the ~99% case), the value is emitted **bare** — a clean prompt
  with no `{% raw %}` noise. If any are present, that single value is wrapped in
  `{% raw %}…{% endraw %}`.
- The authored scaffold text and the live data slots (`{{ task_input }}`, `{{ final_message }}`)
  are always emitted bare/live.
- We do **not** reuse the current `_sanitize_for_raw_block`, which injects spaces into every
  `{{`/`{%` and corrupts otherwise-fine content. Inside a `{% raw %}` block those delimiters
  are already literal; the only sequence that can break out is a literal `{% endraw %}`, which
  is astronomically unlikely in a spec definition. Handle it minimally (defuse just that token,
  or document as a known limitation) — do not blanket-sanitize.

**Editing story:** the default the user starts from is clean; user edits are stored verbatim
(not re-baked). If a user deliberately includes literal braces they want left alone, they add
`{% raw %}` themselves — their choice. The create endpoint only validates that the submitted
template compiles and references the model output (existing validator).

## User Flow

On the LLM-judge create page (`.../create_eval_config/llm_judge`):

1. User selects a judge model and (when applicable) algorithm — unchanged.
2. A new **"Advanced: Judge Prompt"** section (collapsed by default) contains **two editable
   fields**, both pre-filled from the backend:
   - **Judge prompt** (the `prompt_template`) — the rich assembled default.
   - **System prompt** — defaults to `"You are an evaluator."`.
3. The user may edit either field, or leave them as-is.
4. On save, both strings are sent to the create endpoint and stored on the config.
5. The existing read-only display on the eval-configs page shows the saved prompt + system
   prompt (now rich).

The editable fields are independent of the chosen model and algorithm (the same
`prompt_template` / `system_prompt` are used for both `llm_as_judge` and `g_eval`).

## Backend

### Assembly function (rich default)

Add a pure function in `libs/core/kiln_ai/adapters/eval/base_eval.py`:

```
build_default_llm_judge_prompt(eval: Eval) -> str
```

Assembles a rich prompt template string from data reachable from the eval, matching V1
content fidelity:

- **Task context** — `eval.parent_task().instruction`, when present, included as a task
  description block (conditionally raw-wrapped per the rendering rule above).
- **Criteria** — for each `eval.output_scores`:
  - Detail from the richest available source, in priority order:
    1. If `eval.associated_spec()` is not `None` and the score corresponds to the spec, use
       `spec.definition` (the full concatenated spec markdown: description + examples).
    2. Else `score.instruction`.
    3. Else `score.name`.
    (Each injected value conditionally raw-wrapped per the rendering rule.)
  - Plus the score's scale text via `score_scale_instruction(score.type)`.
- **Data slots** — trailing `<task_input>{{ task_input }}</task_input>` /
  `<model_response>{{ final_message }}</model_response>` blocks (always live).

This replaces the impoverished logic currently in `build_llm_judge_prompt_template()`, which
may be removed or reduced to call the new function.

**Exact-V1 quality bar + test:** for a spec-backed eval the assembled default must reproduce
V1-fidelity content (task instruction + the spec's full definition/examples). A
**characterization test** pins the exact assembled string for representative inputs
(spec-backed, legacy/no-spec, multi-score, and injected-Jinja cases). Where a real V1-produced
example is available, assert content parity against it.

### `materialize_llm_judge_properties` — accept overrides

Add optional `judge_prompt: str | None = None` and `system_prompt: str | None = None`:

- `prompt_template` = `judge_prompt` if a non-empty string, else `build_default_llm_judge_prompt(eval)`.
- `system_prompt` = `system_prompt` if provided, else the existing default `"You are an evaluator."`.
- `thinking_instruction` remains the existing default.

### New endpoint: fetch the defaults

```
GET /api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/default_llm_judge_prompt
→ 200 { "judge_prompt": str, "system_prompt": str }
```

- Returns `build_default_llm_judge_prompt(eval)` and the default system prompt.
- Read-only, no side effects, `ALLOW_AGENT`. 404 via standard `eval_from_id`.

### `create_llm_judge_config` + `test_v2_eval` — accept the overrides

- Add `judge_prompt: str | None = None` and `system_prompt: str | None = None` to the shared
  `LlmJudgeBuilderInput` (so **both** create and test inherit them).
- Pass them into `materialize_llm_judge_properties`.
- **Validation:** if `judge_prompt` is provided, confirm it compiles as a Jinja2 template and
  references the model output (reuse the existing `validate_v2_templates_and_expressions`
  behavior / `compile_template_or_raise`); return `400` with a clear message on failure.
  Runtime render failures remain handled via `skipped_reason=extraction_failed`.
- Empty/whitespace-only `judge_prompt` is treated as "not provided" (→ default assembled).

## Frontend

### API wrappers (`app/web_ui/src/lib/api/v2_eval_api.ts`)

- Add `getDefaultLlmJudgePrompt(projectId, taskId, evalId): Promise<{ judge_prompt, system_prompt }>`.
- Generated OpenAPI types add `judge_prompt` / `system_prompt` to `CreateLlmJudgeConfigRequest`
  / `LlmJudgeBuilderInput`; thread them through `createLlmJudgeConfig` and `testV2EvalLlmJudge`.

### Create UI (`llm_judge_form.svelte` + `eval_config_builder.svelte`)

- Add an **"Advanced: Judge Prompt"** collapse (collapsed by default) with two editable
  fields: judge prompt (textarea) and system prompt, both pre-filled from
  `getDefaultLlmJudgePrompt(...)` on load, bound up to `EvalConfigBuilder`.
- Short helper line (mirroring V1): "Customizing the judge prompt can improve eval quality.
  We've pre-filled a default based on your task and spec."
- On save (`createLlmJudgeConfig`), send the current judge prompt + system prompt.
- If the default fetch failed, send neither override and let the server assemble the default
  (graceful degradation).
- Existing "test your judge" invocations pass the current values through `testV2EvalLlmJudge`.

### Read-only display

No change to `eval_config_instruction.svelte` — it already renders `prompt_template` and
`system_prompt`; they will now show the rich/edited values.

## Edge Cases

- **Legacy eval / no spec** (`associated_spec()` is `None`): assembly falls back to
  `score.instruction` (then `score.name`), plus `task.instruction` if available. Never worse
  than today.
- **No task instruction**: the task-description block is omitted; criteria + data slots render.
- **Multiple output_scores**: one criterion block per score; only the spec-matched score uses
  `spec.definition`.
- **User clears the prompt**: treated as empty → server assembles the default (never persist
  an empty judge prompt).
- **User writes invalid Jinja**: create endpoint returns `400`; UI surfaces it and keeps the
  user on the form.
- **Spec definition contains `{{ }}` / `{% %}` / `{# #}`**: that piece is raw-wrapped in the
  assembled default. A literal `{% endraw %}` inside such content is the sole unhandled edge —
  minimally defused or documented.

## Contracts Summary

| Change | Location |
|---|---|
| `build_default_llm_judge_prompt(eval)` (rich assembly, conditional per-piece raw) | `libs/core/.../eval/base_eval.py` |
| `materialize_llm_judge_properties(..., judge_prompt=None, system_prompt=None)` | `libs/core/.../eval/base_eval.py` |
| `judge_prompt` / `system_prompt` on `LlmJudgeBuilderInput` | `app/desktop/studio_server/eval_api.py` |
| `GET .../evals/{eval_id}/default_llm_judge_prompt` → `{ judge_prompt, system_prompt }` | `app/desktop/studio_server/eval_api.py` |
| Thread overrides in create + test endpoints | `app/desktop/studio_server/eval_api.py` |
| `getDefaultLlmJudgePrompt` + thread overrides | `app/web_ui/src/lib/api/v2_eval_api.ts` |
| "Advanced: Judge Prompt" collapse: judge prompt + system prompt fields, pre-filled | `llm_judge_form.svelte` / `eval_config_builder.svelte` |
| Regenerate OpenAPI client | `app/web_ui/src/lib/generate_schema.sh` |

## Testing Considerations

- Unit: `build_default_llm_judge_prompt` — spec-backed, legacy (no spec), multi-score,
  empty-instruction, and injected-Jinja (conditional raw) cases; **characterization/V1-parity
  test** pinning the exact assembled string.
- Unit: `materialize_llm_judge_properties` uses overrides when provided, defaults otherwise.
- API: default-prompt GET returns rich content + default system prompt;
  `create_llm_judge_config` stores overrides and rejects invalid Jinja; `test_v2_eval` honors
  the overrides.
- Frontend: form pre-fills both fields, sends edited values, and gracefully handles a failed
  fetch. Prefer un-stubbed real-component tests for the textareas (see repo note on
  FormElement stub false-greens).
