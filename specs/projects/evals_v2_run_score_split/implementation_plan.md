---
status: complete
---

# Implementation Plan: Split eval traces from eval scores

Design lives in [`functional_spec.md`](functional_spec.md) and
[`architecture.md`](architecture.md). This is the build order only.

Depends on `claude/eval-splits-evals-v2` being merged first.

## Phases

- [x] **Phase 1: Datamodel and default-exclude.** `EvalItemSource`, `TaskRun.eval_source`,
      `Task.runs(include_eval_generated=False)`, `EvalRun.scored_run_id` + `eval_usage`,
      field deprecations, `validate_record_mode`. Architecture §1.
      *Additive and protective — nothing writes the new fields yet. Must land before
      Phase 3 (architecture §10).*

- [x] **Phase 2: `TraceIndex`.** New `adapters/eval/trace_index.py` plus its tests,
      including the 25-way concurrency test. Architecture §2.2, §9.2.
      *Standalone and unused until Phase 3.*

- [ ] **Phase 3: Runner.** `_run_v2_job` restructure, `run_task` persists traces,
      `_resolve_trace`, `EvalTaskInput.from_trace`, populate `eval_usage`.
      Architecture §3, §9.3.
      *Where the behavior change lands. Reuse works at the end of this phase.*

- [ ] **Phase 4: Server surfaces.** `EvalRunWithTrace` joined view model, usage rollup
      from the joined trace, 409 delete protection (single + bulk), `api_schema.d.ts`
      regen. Architecture §5, §6, §9.4, §9.5.
      *Note from Phase 1 review: `PATCH /runs/{run_id}` (`run_api.py`) deep-merges an
      arbitrary `Dict[str, Any]` into the run, so a client can set `eval_source` on any
      TaskRun. Harmless today, and pre-existing in shape (the same endpoint can already
      set `parent_task_run_id` and hide a run from `runs()`). Phase 4 makes `eval_source`
      load-bearing for delete protection, at which point an arbitrary PATCH can make an
      ordinary dataset run permanently undeletable. Decide there whether to reject the
      field on PATCH.*

- [ ] **Phase 5: Migration.** `migrate-eval-runs` CLI command with dry-run, over internal
      V2 project data. Architecture §7, §9.6.
