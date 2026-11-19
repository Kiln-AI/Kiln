---
status: complete
---

# Implementation Plan: Eval Builder cases grounded in an OpenEnv server

Phases 1 to 3 are the prototype (`functional_spec.md`, "Phase 1 is a prototype";
`architecture.md`, "Prototype command"). Phases 4 to 7 build the product version: `ui_design.md` and
`architecture.md`, "Product integration".

Before phase 2 runs against a real server: a local Seahaven branch with Kiln-AI/Seahaven#51 and
#52 merged, and the world served on it (`in-flight.md`, "Running both Seahaven PRs before they
ship"). This is local setup, not a phase.

## Phases

- [x] Phase 1: Foundations, no model calls. `OpenEnvSessionManager.metadata()`,
  `reset_schema_brief.py`, and `eval_grounding` models, prompt and `GroundingSession` (tools,
  limits, call log, episode lifecycle), with tests against the fake server.
- [x] Phase 2: Prompt iteration with `claude -p`. The `prepare` subcommand, the `grounding_mcp`
  server, and `ground --engine claude` (default model `claude-opus-5-5`), with tests that stub the
  kiln_server clients and the `claude` call.
- [x] Checkpoint: run `prepare` and `ground --engine claude` on the eb3 eval definitions, compare
  with the eb3 runs, and iterate on the grounding prompt until the cases are comparable. Results in
  `prototype_results.md`: 36 of 38 grounded across three worlds.
- [x] Phase 3: The real agent. `ground_case`, `ground_cases` and `ground --engine kiln`, with the
  prompt from the checkpoint, and both final-answer styles (structured output and a
  `submit_result` tool), with tests.
- [x] Checkpoint: the measured run. Haiku 5.5 on the Anthropic provider, the same 38 cases: 28
  grounded for $3.85, then 33 for $4.64 with a prompt rule (`prototype_results.md`). Opus was
  not rerun through Kiln: the prototype already showed the strong-model result. Decided: grounding
  runs on the Judge Model, dropped cases get Continue, Retry and Cancel, Retry re-plans with the
  drop reasons.
- [x] Phase 4: Core library. The grounding prompt rules from the Haiku runs;
  `render_judge_guidance`; `TaskRun.reference` and `EvalTaskInput.from_trace` reading it;
  `Eval.openenv_server_id`; `openenv_episode_scope` extracted from the eval runner, which uses
  it; `SyntheticUserCase.openenv_reset` and `judge_guidance`; `run_cases_batch` drives a
  grounded case in its episode; the driver prompt's grounded flag. With tests.
- [x] Phase 5: Studio server. Tool capabilities without an episode; the reset arguments brief
  route; the streamed `ground_cases` route; the pipeline request's grounded fields and the
  grounded judge (template, transient judge, review re-judge); save writes `openenv_reset`,
  `judge_guidance` on inputs and golden runs, and `Eval.openenv_server_id`. Regenerate the
  OpenAPI client. With tests.
- [x] Phase 6: Builder UI. Server lookup after step 1; planner guidance sections and the
  OpenEnv rule-12 wording; the checking-cases phase and its progress; the dropped-cases screen;
  the judge lane's tool requirement and tooltip; the read-only section in review; the save
  payload; the cached-cases key. With tests.
- [x] Phase 7: The judge hint on the judge creation form, and Kiln's OpenEnv docs on writing
  reset-schema descriptions for models.
- [x] Phase 8: The eval's OpenEnv server on the spec page's Properties and the eval page's
  Evaluator Properties, read-only (`functional_spec.md`, "Follow-ups after v1").
- [ ] Phase 9: Run configs that don't fit a grounded eval's server: one fit rule in libs/core,
  the runner errors instead of running without the environment, `run_comparison` refuses or
  skips with the reason, and the comparison table warns and disables the run.
- [ ] Phase 10: Replace Dropped Cases on the dropped-cases screen: plan, generate and ground only
  replacements for the dropped rows, merge them into the plan and both caches.
- [ ] Later, once its UI is scoped: the project-wide multi-turn synthetic user guide, wired into
  the planner's section and the grounding request.
