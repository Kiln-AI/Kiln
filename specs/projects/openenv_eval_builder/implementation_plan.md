---
status: complete
---

# Implementation Plan: Eval Builder cases grounded in an OpenEnv server

Phases 1 to 3 are the prototype (`functional_spec.md`, "Phase 1 is a prototype";
`architecture.md`, "Prototype command"). The rest of the plan is written after the prototype,
with `ui_design.md` and the finished "After the prototype" section of `architecture.md`.

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
- [ ] Checkpoint: run `prepare` and `ground --engine claude` on the eb3 eval definitions, compare
  with the eb3 runs, and iterate on the grounding prompt until the cases are comparable. Each paid
  run needs Sam's go-ahead.
- [ ] Phase 3: The real agent. `ground_case`, `ground_cases` and `ground --engine kiln`, with the
  prompt from the checkpoint, and both final-answer styles (structured output and a
  `submit_result` tool), with tests.
- [ ] Checkpoint: the measured run on two models, a strong one and a cheaper one a user would
  plausibly pick. Decide the grounding model and its control, the dropped-case UI, and retry.
- [ ] Then: `ui_design.md`, finish `architecture.md`, and plan the remaining phases (brief
  endpoint and planner guidance, grounding in `generate_cases`, episode-owned driving, judge, save,
  step 2's tool list, driver prompt flag, UI, docs).
