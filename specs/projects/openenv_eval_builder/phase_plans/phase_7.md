---
status: complete
---

# Phase 7: Judge hint and reset-schema docs

## Overview

The last product phase. A judge written after the Eval Builder saves a grounded eval needs to know
that every case carries judge guidance and how to read it, so the LLM-as-Judge creation form shows
a note when the eval has an OpenEnv server (`ui_design.md`, "Writing a judge later";
`architecture.md`, "Judge hint"). Kiln's OpenEnv docs page gains a section on writing reset-schema
descriptions for models, since those descriptions now guide eval generation (`functional_spec.md`,
"Docs").

It also fixes a bug from phase 6's review: a Retry on the dropped-cases screen stores the drops
for the next plan's guidance, and they were cleared only when a plan landed. A failed Retry plan
left them in place, so a later, unrelated plan still got the "dropped cases" section.

## Steps

1. `create_eval_config/[eval_config_type]/+page.svelte`: when the type is `llm_judge` and
   `evaluator.openenv_server_id` is set, render a `Warning` (`warning_color="gray"`,
   `warning_icon="info"`) with the `ui_design.md` copy above `EvalConfigBuilder`, in a wrapper
   that owns the gap below it. No change to `EvalConfigBuilder` or the shared judge form controls
   (rough placement for v1, as the design says).
2. `builder/+page.svelte`, the retry drops:
   - `sync_step_from_history`: clear `pending_retry_drops` on any step change. Every way out of
     the plan step (Back to edit the spec, browser Back) goes through it.
   - `submit_new_plan` (Refine Plan): clear `pending_retry_drops`; a refined plan is a new plan.
   - The error screen's Retry (`on_continue_from_generate_step`) keeps them: it re-tries the
     Retry's own failed plan.
   - Update the declaration comment to say when the list is cleared.
3. Docs: Kiln's user docs are the GitBook repo (`~/Repos/docs`), not this repo, and its OpenEnv
   page (`docs/tools-and-mcp/openenv`, linked from `OPENENV_DOCS_URL`) is not written yet. Write
   the reset-schema section there: reset-schema descriptions guide eval generation, so write
   them for models: what each starting state holds, who a session can act as, and how any setup
   argument works, with an example schema.

## Tests

- Judge route page, llm_judge with `openenv_server_id`: the note renders with the
  `{{ reference_data.judge_guidance }}` text.
- Judge route page, llm_judge without `openenv_server_id`: no note.
- Judge route page, another type (`exact_match`) with `openenv_server_id`: no note.
- Builder surface: `sync_step_from_history` clears `pending_retry_drops`.
- Builder surface: `submit_new_plan` clears `pending_retry_drops`.
- Builder surface: the error screen's Retry path (`on_continue_from_generate_step`) and
  `on_plan_batch`'s pre-request body don't clear it, so a re-try of a failed Retry plan still
  carries the drops.
