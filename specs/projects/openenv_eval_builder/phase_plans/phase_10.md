---
status: complete
---

# Phase 10: Replace Dropped Cases

## Overview

The dropped-cases screen gains a fourth action, **Replace Dropped Cases**, shown when at least
one case fit. It plans one new scenario per dropped case (guidance: the original sections, the
dropped-cases section, and a new section listing the kept scenarios; the plan's steer last),
generates simulated users for the new scenarios only, grounds only those, and puts them in the
dropped rows' places in `batch_plan.prompts`, so kept rows keep their indices. Both case caches
are rewritten for the merged plan, so the drive reuses them without generating or grounding the
kept cases again. Drops among the replacements (or replacement rows the generator skipped, or
rows the planner returned no scenario for) show the screen again for those drops only.

## Steps

1. `batch_plan_guidance.ts`:
   - `GroundingDrop` gains `scenario_index: number` (the plan row).
   - `kept_scenarios_section(scenarios: string[]): string | null`: "## Scenarios already in the
     batch", the instruction to plan different ones, the list in `<kept_scenarios>`. Null when
     empty.

2. `grounding_flow.ts`, `apply_grounding_frame`:
   - `case_dropped` records `scenario_index: request_case.scenario_index`.
   - `case_grounded` sets the grounded case's `scenario_index` to the request case's resolved
     row, so every grounded case names its plan row even when generation left it null.

3. New `replace_flow.ts` (pure, with `replace_flow.test.ts`):
   - `kept_scenarios(prompts, drops): string[]`: the plan rows not dropped.
   - `type Replacement = { row: number; scenario: string }`
   - `plan_replacements(prompts, drops, new_prompts): { prompts: string[]; replacements:
     Replacement[]; unreplaced: GroundingDrop[] }`: pairs drops (by row order) with the new
     scenarios; the merged plan has each replaced row's text swapped; drops beyond the planner's
     output stay as they were.
   - `place_replacement_cases(cases, replacements): { cases; missing: GroundingDrop[] }`:
     maps each generated case's request-relative `scenario_index` to its plan row; rows with no
     case become drops with `SIMULATED_USER_MISSING_DETAIL`.
   - `merge_cases(kept, replaced_rows, added)`: kept cases (rows resolved, position fallback)
     less those on replaced rows, plus the added cases, ordered by row.
   - `merge_drops(...lists)`: concatenated, ordered by row.

4. `dropped_cases_screen.svelte`: new `on_replace` prop; a "Replace Dropped Cases" button between
   Retry and Continue, only when `fit_count > 0`. Header comment updated.

5. `+page.svelte`:
   - Extract `request_batch_plan(guidance, count, data_guide)` from `on_plan_batch` (POST, error
     message, trim/filter/clamp, empty check) and `request_generated_cases(case_prompts)` from
     `generated_cases_for_plan` (POST, error message). Both return null after setting
     `generation_error`. `on_plan_batch` and `generated_cases_for_plan` call them.
   - `multi_turn_plan_guidance(replacing: { drops; kept_scenarios } | null = null)`: on
     replacement, the dropped-cases section takes `replacing.drops`, the kept-scenarios section is
     added, and the steer is `landed_plan_steer` (the plan on screen's). Otherwise unchanged.
   - `grounding_stop` gains `target_run_config_id` and `judge_choice: ModelChoice`, set by the
     drive, which the replacement grounding reuses.
   - `replacing_count: number | null`: set while a replacement runs; the planning and generating
     animation copy names the replacement count.
   - `on_replace_dropped_cases()`: plan (count = drops) → `plan_replacements` → generate the new
     scenarios → `place_replacement_cases` → commit the merged plan (discarding driven results of
     the old plan if any) and `cached_su_cases` for it (kept generated cases + new, only when the
     old cache belonged to the old plan) → ground the placed cases (skipped when none) → merge with
     the kept grounded cases and all remaining drops. Remaining drops: `grounding_stop` again.
     None: write `cached_grounded_cases` for the merged plan (`grounding_dropped: 0`) and call
     `on_drive_multi_turn()`, which reuses it. Abort returns quietly; failures land on the
     existing error screen.
   - Mount: `on_replace={() => void on_replace_dropped_cases()}`.

## Tests

- `batch_plan_guidance.test.ts`: `kept_scenarios_section` lists each scenario, null when empty;
  existing drop fixtures carry `scenario_index`.
- `grounding_flow.test.ts`: a `case_dropped` frame records the request case's `scenario_index`; a
  grounded case with a null `scenario_index` takes its request row.
- `replace_flow.test.ts`:
  - `kept_scenarios` keeps the non-dropped rows in order.
  - `plan_replacements` swaps dropped rows in place and keeps kept rows' indices; fewer new
    scenarios than drops leaves the rest unreplaced, with original text.
  - `place_replacement_cases` remaps indices to plan rows; a salvage-missed scenario becomes a drop
    with the simulated-user reason; a null `scenario_index` falls back to position.
  - `merge_cases` replaces cases on replaced rows and orders by row; resolves null indices by
    position.
  - `merge_drops` orders by row.
- `dropped_cases_screen.test.ts`: four buttons in order with Continue primary, Replace calls
  `on_replace`; no Replace when nothing fit.
- `generate_step_surface.test.ts`: the replace handler plans with the kept scenarios and drops,
  generates only the replacements, writes both caches for the merged plan, re-stops on drops, and
  is the fifth mention of `on_drive_multi_turn`; the guidance helper adds the kept section.
