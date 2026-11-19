---
status: complete
---

# Phase 6: Builder UI for grounded cases

## Overview

The Eval Builder page wires the phase 5 routes into a multi-turn build whose run config reaches one
OpenEnv server. The planner gets the server's reset arguments and, on a Retry, the dropped
scenarios; the planned cases are checked against the server through the `ground_cases` stream,
with a progress stage and a dropped-cases screen; the judge lane asks for tool support; the
grounded fields ride the drive, the claim builder, the re-judge and the save; review shows each
case's starting state and judge guidance, read-only. A build without an OpenEnv server behaves as
today. Every backend call is stubbed in tests.

## Steps

1. `builder/batch_plan_guidance.ts`
   - `multiturn_plan_guidance(spec, { openenv = false } = {})`: on an OpenEnv build the
     world-state paragraph says the reset arguments describe the starting states, Kiln fits each
     scenario to real data after planning, and scenarios still name kinds, never specific records.
   - `reset_arguments_section(brief: string | null): string | null`: the trimmed brief, or null
     when blank. The brief route already carries the framing (`RESET_ARGUMENTS_FRAMING` in
     `reset_schema_brief.py`), so the prototype and the product send the same words.
   - `synthetic_user_guide_section(guide: string | null): string | null`: the prototype's
     `DATA_GUIDE_FRAMING` then `<data_guide>`; null when blank. Not wired until the guide's UI
     exists.
   - `dropped_cases_section(drops: GroundingDrop[]): string | null`: framing that these could not
     be checked against the environment and must not be planned again in the same form, then one
     scenario and reason each; null when empty.
   - `compose_plan_guidance(base, sections: (string | null)[], steer)`: base, each non-blank
     section, then the steer. Base stays a strict prefix.

2. `builder/builder_draft.ts`
   - `SyntheticUserCaseWire` gains `openenv_reset?: OpenEnvReset | null` and
     `judge_guidance?: string | null`.
   - `CachedSuCases` gains `openenv_server_id?: string | null`, `judge_model?: string | null`
     (`provider/model`) and `grounding_dropped?: number` (cases dropped and accepted with
     Continue). `reusable_cached_cases(cache, prompts, spec, grounding: CaseGroundingKey)` also
     misses when the server differs, or when the build is grounded and the judge model differs.
   - `BuilderDraft` gains `openenv_server_lookup: { tool_ids_key, openenv_server_id } | null` and
     `reset_arguments_brief: { openenv_server_id, brief } | null`, both null on older drafts.

3. New `builder/grounding_flow.ts`
   - Types: `GroundingDrop {scenario, drop_detail}`, `GroundingFrame` (the phase 5 frames from
     `api_schema`), `GroundingProgress {total, checked, dropped}`, `GroundingOutcome {grounded:
     SyntheticUserCaseWire[], drops: GroundingDrop[]}`.
   - `grounding_request_cases(cases, plan_prompts): GroundCaseApi[]`: scenario text from the plan
     row each case came from (`scenario_index`, else its position).
   - `apply_grounding_frame(state, frame, cases, plan_prompts)`: pure reducer: a grounded case
     takes the frame's simulated user, `openenv_reset` and `judge_guidance`; a dropped one adds a
     drop; `grounding_failed` throws a `KilnError` (code kept).
   - `stream_ground_cases({project_id, task_id, body, signal, on_progress}): Promise<GroundingOutcome>`:
     `fetch` + `sse_data_payloads`, the reducer, progress per frame; grounded cases returned in
     request order. A non-OK response or a stream with no `grounding_finished` throws.
   - `grounded_server_id(cases): string | null`: the server the cases' resets name (for the save).
   - `model_choice_key(choice)`: `provider/model`.
   - `openenv_lookup_key(tool_ids)`: the sorted tool ids as JSON.

4. `builder/progress_count.svelte`: `failed_label = "failed"` prop, used in the count line.

5. New `builder/dropped_cases_screen.svelte`: `SettingsHeader` title "Some Cases Don't Fit Your
   Environment" with the one-line count as subtitle (or the none-fit line), a house table with
   one row per drop (scenario in `ClampedText` with one line and See all into a `SeeAllDialog`,
   reason under it in muted text), and a right-aligned button row: Cancel, Retry, Continue With N
   (primary; absent when every case dropped, Retry primary then). Props: `drops`, `total`,
   `grounded_count`, `on_cancel`, `on_retry`, `on_continue`.

6. `builder/claim_evidence.ts`: `TraceClaims` gains `openenv_reset?` and `judge_guidance?`.
   New `builder/environment_guidance.svelte`: a closed `Collapse` titled "Environment and Judge
   Guidance" with a "Starting State" `SettingsHeader` over a `PropertyList` of the reset
   arguments by path (`flatten_reset_arguments` in `grounding_flow.ts`; long or multi-line values
   in an `Output` capped with Show All), and a "Judge Guidance" `SettingsHeader` over an `Output`
   holding `ChatMarkdown`. `claim_evidence_review.svelte` renders it under the overview when the
   trace has `judge_guidance`.

7. `builder/+page.svelte`
   - State: `openenv_server_lookup`, `reset_arguments_brief` (drafted), `pending_retry_drops`,
     `landed_plan_steer`, `grounding_stop {drops, grounded, total} | null`, grounding counters,
     `accepted_grounding_drops`. `$: build_is_openenv`.
   - `resolve_drive_run_config` also returns the config's tool ids.
     `ensure_openenv_server(tool_ids)` looks the server up through `lookup_run_openenv_server`
     once per tool set (a reach error throws); `ensure_reset_arguments_brief(server_id)` reads the
     brief route once per server.
   - `on_plan_batch` (multi-turn): resolves the run config and the server, then composes
     `multiturn_plan_guidance(spec, {openenv})` with the reset arguments and dropped cases
     sections and the steer. A landed plan clears `pending_retry_drops` and records the steer in
     `landed_plan_steer`; clears `grounding_stop`.
   - `on_drive_multi_turn`: the server is resolved after the run config; the case cache is keyed
     on it and the judge model; after `generating_cases`, an OpenEnv build runs
     `grounding_cases` through `stream_ground_cases`. Drops stop before driving with
     `grounding_stop`; none caches the grounded cases and drives them. Shortfall accounting
     subtracts the drops accepted with Continue.
   - Drop screen actions: Continue caches the grounded cases with their drop count and drives;
     Retry sets `pending_retry_drops`, restores the landed steer, plans, then drives; Cancel
     clears `grounding_stop` and the cached cases and returns to the plan.
   - Progress: `generation_phase = "grounding_cases"`, title and description from `ui_design.md`,
     `ProgressCount` with `noun="cases checked"`, `failed_label="dropped"`.
   - Judge lane: `requires_tool_support: true` and an extra tooltip sentence on an OpenEnv build.
   - Case judged → the trace carries the case's `openenv_reset` and `judge_guidance`; claims
     build sends `judge_guidance`; re-judge sends one guidance per leaf when any is set; save
     sends `openenv_server_id: grounded_server_id(driven_cases)`.
   - Keyboard: the drop screen has no keyboard path, like the partial stop screen.

## Tests

- `batch_plan_guidance`: OpenEnv rule-12 wording swapped in and the default unchanged; reset
  arguments section passes the brief through and is null when blank; dropped cases section lists
  each scenario and reason, null when empty; synthetic user guide section framing, null when
  blank; compose order base, sections, steer, blank sections skipped, base a strict prefix.
- `builder_draft`: cache misses on a changed server, on a changed judge model when grounded,
  ignores the judge when ungrounded, older caches without the keys read as ungrounded; empty draft
  carries the new keys as null.
- `grounding_flow`: request cases take the plan text by `scenario_index` and by position;
  reducer applies grounded and dropped frames and throws on `grounding_failed`; the stream with a
  stubbed `fetch` reports progress per frame and returns grounded cases in request order, throws
  on a non-OK response and on a stream without `grounding_finished`; `grounded_server_id`;
  `flatten_reset_arguments` paths for nested keys.
- `progress_count`: "3 of 20 cases checked — 1 dropped" with `failed_label`.
- `dropped_cases_screen`: title, count line, one row per drop with its reason, Continue With N,
  Retry and Cancel call their handlers in order Cancel, Retry, Continue; all dropped hides
  Continue and makes Retry primary.
- `claim_evidence_review`: the guidance section renders closed under the overview for a grounded
  trace, shows the reset arguments by path and the guidance; absent for an ungrounded trace.
- `generate_step_surface` (source assertions): the judge lane adds `requires_tool_support` on an
  OpenEnv build; the grounding phase renders `ProgressCount` with the dropped label; the plan
  request composes sections; the save sends `openenv_server_id`; claims and re-judge send the
  guidance.
