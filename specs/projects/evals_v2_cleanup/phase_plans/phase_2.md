---
status: complete
---

# Phase 2: Frontend + API surface

## Overview

This phase adds three frontend features and ensures the OpenAPI schema is up to date:

1. Regenerate the OpenAPI client so `TestV2EvalResponse.intermediate_outputs` appears in TS types.
2. D31 UI: Thread `intermediate_outputs` into the V2 result renderer in `run_result/+page.svelte`, and add a "View reasoning" link + modal in `llm_judge_result.svelte`.
3. D35 UI: Add an `n_excluded` info indicator on the compare view (`run_config_comparison_table.svelte`) next to the Status cell. Also apply the same pattern to the judge-comparison view (`compare/+page.svelte`) if it renders aggregate per-run scores with accessible `n_excluded` data.

## Steps

### Step 1: Regenerate OpenAPI schema

`TestV2EvalResponse` already has `intermediate_outputs: dict[str, str] | None = None` on the backend (eval_api.py:218). Regenerate the OpenAPI client via `mcp__HooksMCP__generate_schema` and verify with `mcp__HooksMCP__check_schema`.

### Step 2: D31 UI - Thread `intermediate_outputs` into V2 result renderer

In `run_result/+page.svelte` (~line 356-362), add `intermediate_outputs={result.intermediate_outputs ?? null}` to the `<svelte:component>` props.

### Step 3: D31 UI - Add reasoning modal to `llm_judge_result.svelte`

- Add prop: `export let intermediate_outputs: Record<string, string> | null = null`
- Add derived: `$: reasoning = intermediate_outputs?.reasoning || intermediate_outputs?.chain_of_thought || null`
- Add `Dialog` import and a `reasoning_dialog` variable
- When `reasoning` is present, render a "View reasoning" link (`text-xs` style, consistent with the existing `text-gray-400` config block) that opens a `Dialog` modal titled "Judge Reasoning" with the reasoning text

### Step 4: D35 UI - `n_excluded` indicator on `run_config_comparison_table.svelte`

- Add a helper function `excluded_for_run_config(score_summary, rc_id, output_scores)` that reads `n_excluded`/`n_used` from the first available `ScoreSummary` for a run config
- In each row's Status cell (`<td>` around line 167), when `n_excluded > 0`, render an `InfoTooltip` wrapped in a colored `<span>`: `text-error` when ratio > 0.2, `text-warning` otherwise
- The indicator coexists with the existing `percent_complete` incomplete warning

### Step 5: D35 UI - Judge-comparison view (`compare/+page.svelte`)

The compare view uses `EvalConfigResult` which has `n_excluded` at the eval-config level and `ScoreSummary` per score key with `n_excluded`/`n_used`. Apply the same info indicator on the section header or per-score rows where aggregate scores are shown.

### Step 6: Tests

- `llm_judge_result.test.ts`: Add tests for "View reasoning" link visibility and dialog modal
- New test file `run_config_comparison_table.test.ts`: Test the `n_excluded` indicator appearance, absence, color thresholds, and coexistence with incomplete warning

### Step 7: Final checks

Run all checks via HooksMCP tools: lint, format, type-check, build, tests, schema verification.

## Tests

- `llm_judge_result.test.ts`: "shows View reasoning link when reasoning present" - verifies the link appears
- `llm_judge_result.test.ts`: "hides View reasoning when no reasoning" - verifies no link when `intermediate_outputs` is null/empty
- `llm_judge_result.test.ts`: "opens dialog when View reasoning clicked" - verifies dialog shows
- `run_config_comparison_table.test.ts`: "shows info indicator when n_excluded > 0"
- `run_config_comparison_table.test.ts`: "hides info indicator when n_excluded == 0"
- `run_config_comparison_table.test.ts`: "shows text-warning when ratio <= 0.2"
- `run_config_comparison_table.test.ts`: "shows text-error when ratio > 0.2"
- `run_config_comparison_table.test.ts`: "coexists with incomplete-runs warning"
