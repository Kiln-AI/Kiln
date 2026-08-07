---
status: complete
---

# Implementation Plan: Train/val/test splits across V1 and V2 eval datasets

See `functional_spec.md` for behavior and `architecture.md` for design. This is the build order.

## Phases

- [x] **Phase 1: Merge `scosman/evals_v2`.** Resolve conflicts, no new behavior. Resolve the split
      surface toward evals_v2 and **drop #1621's split additions rather than reconciling them** —
      `val_set_filter_id`, `filter_id_for_split`, `split_filter_id_from_eval`,
      `eval_set_filter_id_override`, the `split` API params and `migrate_val_set_filter_id` are all
      replaced by later phases. Ends with a green tree and no `split` parameter anywhere.
      (architecture §10)

      **Satisfied by the branch's base rather than by a merge.** This branch is cut from
      `scosman/evals_v2` directly, so evals_v2's tree is where phase 2 starts and there is nothing
      of #1621's to back out — see "Where this branch came from" below.

- [x] **Phase 2: Splits datamodel and accessor.** `SplitRef` union, the `splits` dict, the legacy
      fold with provenance, the provenance-preserving serializer, the `eval_input_filter_id` shim,
      the test-split validator, and deletion of `validate_filter_fields` and
      `migrate_train_set_filter_id`. Plus `eval_splits.py` — `ItemKey`, `ResolvedSplit`,
      `resolve_split`, `eval_run_item_key`. (architecture §2, §3)

- [x] **Phase 3: Creation paths and prompt optimization.** `spec_utils` returns splits rather than
      a widening tuple; `spec_api` and `copilot_api` construct `splits=` including a val split;
      prompt optimization gates on a TaskRun-backed train split and refuses an EvalInput-backed one.
      (architecture §6.4, §8) The eval-update endpoint's `splits` write landed early — phase 2 had
      to move it, see `phase_plans/phase_2.md`.

      **Decide first: do the new spec eval's test and train splits go in their legacy homes?**
      `Eval.set_split()` (architecture §2.6, added in phase 2) writes a TaskRun-backed test or train
      split to `eval_set_filter_id` / `train_set_filter_id`, where every reader below already looks;
      constructing with `splits=` alone does not. If phase 3 constructs with `splits=` only, a
      brand-new spec eval writes **no legacy fields at all** — so its **test** split, not just its
      val split, is invisible to older Kiln builds and to anything else reading the file directly.
      That is a materially wider blast radius than architecture §2.9's "splits that only new tooling
      creates", and §2.9 should be revisited if that is the choice. Using `set_split` for the
      TaskRun-backed test and train splits avoids it, and shrinks the migration list below to the
      readers that genuinely need `splits`.

      **If they do not, this must all move in the same phase or it lands red.** This list is a
      full sweep of both legacy field names across Python, Svelte and TS as of the phase-2 commit,
      not a list of what reviewers happened to notice. Line numbers are from that commit; the
      function and file names are the stable reference. Re-run the sweep before starting:
      `grep -rn "eval_set_filter_id\|train_set_filter_id" --include=*.py --include=*.svelte
      --include=*.ts libs app | grep -v api_schema.d.ts`.

      *Python readers of `eval_set_filter_id`:*

      - `jobs/workers/eval.py:283-285` — `compute_state`'s guard and filter.
      - `eval_api.py:1426, 1432` — `get_eval_progress`'s 400 guard and test-set count.
      - `eval_api.py:1497, 1503` — `get_eval_config_score_summary`.
      - `eval_api.py:1543` — `get_eval_results_summary`'s per-eval cache key.
      - `eval_api.py:1803, 1806` — `get_run_config_eval_scores`.

      *Python readers of `train_set_filter_id`:*

      - `eval_api.py:1448-1449` — `get_eval_progress`'s `train_dataset_size`. Already reports `0`
        for a train split created through the update endpoint if that endpoint stops using
        `set_split`.
      - `prompt_optimization_job_api.py:436, 448, 459, 479` — `has_train_set` (§6.4).

      *Python creation paths that must switch (§8), and are what starts the clock:*

      - `spec_api.py:108-109, 126-127`, `copilot_api.py:305-306, 331-332`, and the tuple contract
        they read from `spec_utils.py` (its docstring at `:97` names the fields).
      - `eval_api.py:736` — the create-eval endpoint passes `eval_set_filter_id=` as a construction
        kwarg. That still works (the fold homes it), so it is a choice, not a break.

      *Web UI, same timing* — these read the legacy fields off the API response and break
      identically, even though the plan assigns UI work to phase 6:

      - `eval_set_filter_id`: `[eval_id]/+page.svelte:276-277` (renders `"null (N items)"`) and
        `:525-526`, `[spec_id]/+page.svelte:634`, `compare/+page.svelte:689-690`,
        `run_result/+page.svelte:157-158`, `generate/.../data_gen_intro.svelte:117-131`.
      - `train_set_filter_id`: the eval detail page's "Training Dataset" row
        (`[eval_id]/+page.svelte:296, 303, 309`), and
        `create_prompt_optimization_job/+page.svelte:521-522, 1074, 1111` — the page whose whole
        purpose is the train split. §6.4 rewriting `has_train_set` to read `splits` makes `:521`
        `has_train_set === true && train_set_filter_id === null`, silently skipping the train-size
        fetch, and `:1074`/`:1111` pass `""` to `tagFromFilterId`, dropping the dataset and "add
        data" links.
      - Their fixtures move too, or they pass vacuously: `create_eval_config/page.test.ts:56`,
        `page.reference_data.test.ts:56`, `eval_detail.test.ts:59`,
        `generate/.../eval_options.test.ts:9`.

      *Not fixable by any phase of this project:* `package_project_for_training` copies `eval.kiln`
      verbatim into the zip read by the closed-source remote optimizer, which knows only
      `train_set_filter_id` (functional spec §6.3). A train split written only to `splits` is
      invisible to it permanently. This is the reason `set_split` exists.

- [x] **Phase 4: `EvalRunner`.** Collapse the two collection paths into one, take a `ResolvedSplit`
      instead of a filter-id override, and delete `collect_tasks_for_eval_input` together with the
      `EvalInput`/`eval_config_eval` branch of `run_job`. (architecture §4)

- [x] **Phase 5: Jobs.** Worker resolves the split once for both the runner and the progress
      universe; `jobs/api.py` pre-resolves so a bad split 422s at request time. (architecture §5)

      **Built, reviewed and complete — but it is not on this branch, and it ships separately.**
      The phase's code targets `app/desktop/studio_server/jobs/workers/eval.py` and the eval route
      in `jobs/api.py`. Neither exists on `scosman/evals_v2`: the eval job worker belongs to the
      still-draft PR #1517 (`leonard/kil-686-eval-job`), which is where this project was originally
      built and which is not merged. Rebasing onto `scosman/evals_v2` therefore leaves this phase
      with no code to attach to.

      What is here: `phase_plans/phase_5.md`, the full plan and post-build record, unchanged. What
      is not: `jobs/workers/eval.py`'s `_resolve_split` and its `EvalJobParams.split`, `jobs/api.py`'s
      pre-resolution, their tests, and `phase5_mutation_sweep.py` (every one of its mutations edits
      one of those two files, so it is dropped rather than re-targeted — nothing in this tree plays
      the worker's role). Two consequences are visible from the outside:

      - **`POST /api/jobs/evals/run` has no `split` parameter** in this tree's `api_schema.d.ts`,
        because the route itself is not here. Functional spec §4.1 describes that endpoint and is
        annotated accordingly; architecture §5 is the jobs section and carries the same note.
      - **Phase 4's mutation sweep loses one entry** ("worker: builds the runner over an empty
        split") and phase 6 loses phase 5's five deferred cosmetic items, four of which were in
        `jobs/`. Both are recorded where they happened rather than silently dropped.

      The original phase-5 commit is `369a32ef8` on `claude/eval-splits-v1-v2-q38412`. It applies to
      a tree that has the eval job worker; re-land it there, on top of this work, when #1517 merges.
      Nothing else in this project depends on it: phases 4 and 6 are complete without it, and the
      runner already refuses a `task_run_eval` with no split (architecture §4.2), so the worker
      cannot be re-added in a form that silently drops one.

- [x] **Phase 6: API endpoints and web UI.** Required `split` on the results endpoint, val count on
      progress, drop the EvalInput guards, `compute_score_summary` over a `ResolvedSplit`,
      source-aware summary cache; then the two UI changes and the regenerated schema.
      (architecture §6, functional spec §5, §6.1)

      Phase 5 deferred five cosmetic items to this phase; **all five land with phase 5, not here.**
      Four were in `jobs/` (`test_api.py`'s unused `monkeypatch` fixture parameter,
      `workers/eval.py`'s `_item_source` placement, `api.py`'s under-described endpoint comment, and
      `_resolve_split`'s "not a reachable state" docstring) and the fifth was a missing
      `item_source` entry in `phase5_mutation_sweep.py`. None of those files are in this tree.
      `phase_plans/phase_5.md` and its review are where the list survives.

- [ ] **Phase 7: eb-v2 alignment project overview.** Write
      `specs/projects/eb_v2_splits_alignment/project_overview.md` — overview only, from the merged
      tree as it actually landed. This phase's agent writes it; it is not designed here.
      (functional spec §11)

## Notes

**Phases 2–6 each land on a green tree.** The legacy fields stay declared and constructible
throughout (architecture §2.4), so migrating readers to `splits` does not break callers that
haven't moved yet. Phase 1 dropping #1621's helpers is what avoids a half-migrated state where two
split APIs coexist.

**Phase 2 is the risk concentration.** The byte-identical round-trip test is the gate; if
serialization doesn't behave, stop rather than working around it. Test churn there is
read-not-fix work (architecture §12.6) — a test asserting on a legacy field can now pass
vacuously.

**Phase 7 runs last for a reason.** It records the real conflict surface against the model as
shipped, which isn't knowable earlier.

**Where this branch came from.** The project was first built on `scosman/eval-api-improvements`,
which is PR #1517 (`leonard/kil-686-eval-job`, draft and unmerged) plus two split commits. That
carried 52 commits of in-flight work — including files marked
`# TODO (merge blocker — do not merge toward main until resolved)` — none of which may reach a
main-destined branch. `claude/eval-splits-evals-v2` is the same project rebuilt on
`origin/scosman/evals_v2` and contains only this project's work. The original branch,
`claude/eval-splits-v1-v2-q38412` (head `940d13ad5`), is left intact as the record; the phase
commits here name their originals. The one thing lost in the move is phase 5 — see its entry above.

Two small pieces the rebuild had to carry that were not this project's: `create_dataset_task_runs`
gains a `val_tag` (it came from #1621 on the old base, and without it the copilot mints a val split
no run carries), and `phase2_mutation_sweep.py` loses two mutations over the judge-feedback-batch
surface, which is #1517's.

**Two `eval_runner.py` fixes are homeless, and need an owner outside phases 5 and 6.** Phase 4
raised both and deferred them to "whichever of phases 5 and 6 next edits `run_job` /
`collect_tasks_for_eval_config_eval`". Neither does: phase 5 is `jobs/`, and architecture §6 scopes
phase 6 to `eval_api.py` and two Svelte pages. Phase 7 is overview-only. So unless someone claims
them, they ship as-is:

- **`EvalJob` does not express which item types each run type can carry.**
  `EvalJob(item=some_eval_input, type="eval_config_eval")` still type-checks. Phase 4 made it
  unreachable but not unrepresentable.
- **Calibration dedupe ignores what a run was *for*.** `collect_tasks_for_eval_config_eval` builds
  `already_run` from every run on the eval config, including `task_run_eval` ones, so a golden
  `TaskRun` already scored for some run config is silently never calibrated. Pre-existing, not a
  regression from this project.

Full write-ups — including why each was declined and what the fix looks like — are in
`phase_plans/phase_4.md`'s "Known limitations" and `phase_plans/phase_5.md`'s. Recorded here
because phase plans are not part of a coding agent's context loading, so a note left only in them
is a note the next agent never sees.
