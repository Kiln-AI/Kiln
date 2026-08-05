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

- [ ] **Phase 2: Splits datamodel and accessor.** `SplitRef` union, the `splits` dict, the legacy
      fold with provenance, the provenance-preserving serializer, the `eval_input_filter_id` shim,
      the test-split validator, and deletion of `validate_filter_fields` and
      `migrate_train_set_filter_id`. Plus `eval_splits.py` — `ItemKey`, `ResolvedSplit`,
      `resolve_split`, `eval_run_item_key`. (architecture §2, §3)

- [ ] **Phase 3: Creation paths and prompt optimization.** `spec_utils` returns splits rather than
      a widening tuple; `spec_api` and `copilot_api` construct `splits=` including a val split;
      the eval-update endpoint writes `splits`; prompt optimization gates on a TaskRun-backed train
      split and refuses an EvalInput-backed one. (architecture §6.4, §8)

- [ ] **Phase 4: `EvalRunner`.** Collapse the two collection paths into one, take a `ResolvedSplit`
      instead of a filter-id override, and delete `collect_tasks_for_eval_input` together with the
      `EvalInput`/`eval_config_eval` branch of `run_job`. (architecture §4)

- [ ] **Phase 5: Jobs.** Worker resolves the split once for both the runner and the progress
      universe; `jobs/api.py` pre-resolves so a bad split 422s at request time. (architecture §5)

- [ ] **Phase 6: API endpoints and web UI.** Required `split` on the results endpoint, val count on
      progress, drop the EvalInput guards, `compute_score_summary` over a `ResolvedSplit`,
      source-aware summary cache; then the two UI changes and the regenerated schema.
      (architecture §6, functional spec §5, §6.1)

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
