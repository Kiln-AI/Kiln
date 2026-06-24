---
status: complete
---

# Implementation Plan: Evals V2 Manual Create-Flow Remediation

Dependency-ordered checklist. Detail lives in `architecture.md` (this project) and the
**destination specs** `evals_v2/components/70` (+ `21`, `27`, `22`) — not restated here. The
coding agent writes a `phase_plans/phase_N.md` before each phase. Scope: the **manual create
flow only**. Run the standard web + python check suites before each phase's code review.

## Phases

- [x] **Phase 1 — Routing & container restructure (nav fix).**
  Replace the in-page state machine with real routes (arch §1): `+layout.ts` shared load; picker
  index route; one dynamic `[eval_config_type]` builder route; extract `EvalConfigBuilder`
  container (Save + trust gate + Save-Without-Testing move in). Native nav (select→`goto`, Back,
  refresh-restores-type, deep-link); legacy `?config_type=` redirect; carry
  `next_page`/`save_as_default`; `beforeNavigate` guard; remove the on-screen Back button.
  Left/right two-column layout. **Behavior of forms + existing test inputs preserved** (the
  dataset picker lands in Phase 3; llm_judge still V1 until Phase 2). Target: `70 §1`.

- [ ] **Phase 2 — Manual `llm_judge` emits V2 (ship-blocker).**
  Core helpers (arch §2.2): extract `score_scale_instruction()` (refactor `build_score_schema`
  to use it); add `build_llm_judge_prompt_template()` (the owner-approved template) +
  `materialize_llm_judge_properties()` (explicit `system_prompt`/`thinking_instruction`/
  `required_var`). Backend `create_llm_judge_config` endpoint (arch §2.3). Frontend: reuse
  `llm_judge_form.svelte`, **remove** the V1 `task_description`+`eval_steps` authoring, keep
  model picker + algo→`g_eval`; `do_save` sends `{model_name, provider, g_eval}`. Regenerate
  OpenAPI schema. Verify a V2 `llm_judge` round-trips save/load/run. Target: `components/21`.

- [ ] **Phase 3 — Test Run dataset-item harness.**
  Replace the four inputs with a **recent-`TaskRun` picker** (reuse `TaskRunPicker`; `GET /runs`);
  client `TaskRun→EvalTaskInput` mapping; **Advanced** reference_data; **empty-dataset** state →
  Save-Without-Testing only; spinner/Cancel kept. **Include `llm_judge`** (extend `test_v2_eval`
  to bake from the builder input, arch §3.3). **Shape-validity gates Save** (fix `test_has_run`).
  Score results render V1-parity floats (no badge). Target: `70 §1`/`§2`.

- [ ] **Phase 4 — Deterministic form correctness + picker.**
  `set_check.mode` **required** (drop the `= "subset"` default; UI sends explicit; audit other
  mode enums; regen schema) — double-robustness. "JSONPath"→"Jinja2" wording + help across forms.
  On-blur validation (regex, min≤max, XOR). `tool_call_check`: hide `on_unexpected_tools` on
  "Never", collapse `expected_args`. Type picker order + "(recommended)" + labels. Target:
  `70 §3.1`/`§3.2`, `§1`; shapes in `22`.

- [ ] **Phase 5 — Form polish (droppable, LOW).**
  Radio groups (disable inactive) for the literal-vs-reference XOR; `set_check.expected_set`
  tag-input. Cleanly droppable without affecting the structural fixes.

## Notes

- **Ordering:** Phase 1 (structure) before Phase 2 (emit-V2 in the clean container). If the
  ship-blocker must land first, 1↔2 can swap — `do_save` then moves into the container during the
  restructure (one extra move, no rework of logic).
- **Decisions baked in** (see `functional_spec §6`): Q1 split into routes; Q2 manual-create-only,
  phased; Q3 keep newer drift; backend-baked judge template; V1 score-parity (no badge); no
  silent API defaults.

## Not in this build (out of scope — separate projects)

- **View / run-result / comparison surfaces**, typed score badges, fail-loud view binding.
- **Read-only config-detail + clone/prefill** (`70 §4.3`, E.17).
- **Copilot / eval-builder / questionnaire** emitting V2.
- Anything `70` marks out of scope (onboarding, SDG, right-sizing).
