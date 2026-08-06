---
status: complete
---

# Phase 2: Splits datamodel and accessor

## Overview

Land the model this project is built on: a typed `splits` dict on `Eval` whose values say which
store backs each split, plus the one accessor seam that resolves a split to its items. Legacy
fields stay declared and become storage-format artifacts — the fold copies them into `splits` on
load, and a provenance-preserving serializer writes each split back to the format it arrived in.

No behavior changes for any existing eval: a legacy project file loads, runs and saves exactly as
before, byte for byte. What changes is that `splits` is now the read surface, and phases 3–6 move
readers onto it. The one user-visible change is the eval-update endpoint's train-split write, which
had to move here rather than to phase 3 (step 4a).

Implements architecture §2 and §3. The risk concentration is §2.6's serializer — the byte-identical
round-trip test is the gate, and it passes.

## Steps

### 1. `libs/core/kiln_ai/datamodel/eval.py` — the split types

`TaskRunSplit` / `EvalInputSplit` / `SplitRef` exactly as architecture §2.1, plus `EvalSplitName`
(the API-addressable names) and `LEGACY_SPLIT_FIELDS = {"test": "eval_set_filter_id", "train":
"train_set_filter_id"}`, which the fold and the serializer both key on.

### 2. `Eval` fields

- `splits: Dict[str, SplitRef] = Field(default_factory=dict, ...)` — `str`-keyed per §2.2, so a
  file naming a split this build doesn't know still loads.
- `eval_set_filter_id` / `train_set_filter_id` keep their types and gain descriptions saying they
  are legacy storage written *from* `splits` (§2.6.2 mitigation 1). The wording has to work for two
  audiences, since these descriptions ship into the OpenAPI schema and the generated TS client: an
  API consumer can't "write `splits['test']` instead", so it says where the truth lives rather than
  giving a Python instruction.
- `eval_input_filter_id` is **deleted as a declared field** (§2.6.1) — it never enters the schema
  or the generated web client.
- `_legacy_homed_splits: Set[str] | None = PrivateAttr(default=None)`.

### 3. Validators

- `migrate_eval_input_filter_id` (before): pops the key and writes
  `splits["test"] = EvalInputSplit(...)`. Carries the `TODO: Remove before shipping`. Raises when
  the input also carries `eval_set_filter_id` — folding both would silently discard one backing.
- `fold_legacy_filter_fields` (after): copies both legacy fields into `splits`, records which
  splits came from there. Not gated on `_loaded_from_file` (§2.7), but **gated on provenance not
  already being recorded**, so it runs exactly once per instance. `validate_assignment=True` means
  every attribute set re-runs the after-validators; a second fold would re-derive `splits` from the
  legacy fields and revert any split the caller wrote. `save_to_file` ends with `self.path = path`,
  so without the guard a split edit is written correctly on the first save and undone on the next.
- `validate_splits` (after): a test split is required. Declared **after** the fold — an eval
  carrying only legacy fields must validate, and `test_eval_legacy_only_validates` is the guard on
  that ordering.
- `migrate_train_set_filter_id` is deleted (functional spec §3.2), and so is
  `validate_filter_fields` — except for its "not both legacy test filters" half, which moves into
  the shim above because `splits` makes the *model* state unrepresentable but says nothing about
  two conflicting *inputs* (§2.8).

### 4. `serialize_preserving_split_format`

A wrap `model_serializer` (§2.6): each split is written to its legacy field when it is legacy-homed
*and* TaskRun-backed *and* that field is present in the dump, otherwise to `splits` with the legacy
field nulled. The last condition matters because the two homes are the only homes: a caller who
excludes `eval_set_filter_id` (`exclude_none`, `exclude`) must get the split in `splits`, not
nowhere. The `splits` key is dropped entirely when nothing is left in it, which is what makes an
untouched legacy eval byte-identical. Unknown provenance (`None`) falls back to content — any
TaskRun-backed test/train split goes to its legacy field.

### 4a. `Eval.set_split()` — an architecture amendment

**This is a change to `architecture.md`, not an implementation detail.** §2.6 said flatly that a
newly created split is written to `splits`. That is wrong for splits created *on behalf of a user*,
and the update endpoint below is the case that proves it. §2.6 now has a "creating a split"
subsection describing the amended rule, and §2.6.2 and §8 point at it.

```python
def set_split(self, name: str, split: SplitRef) -> None: ...
```

`eval.splits[name] = ref` and `set_split(name, ref)` set the same value; they differ in where it is
stored. Direct assignment authors in the new format. `set_split` adds the name to
`_legacy_homed_splits` when a legacy field can hold the ref (TaskRun-backed, and named in
`LEGACY_SPLIT_FIELDS`), so the split serializes to `eval_set_filter_id` / `train_set_filter_id` and
stays readable by everything that reads those. It also marks `splits` as set, so a split added by
item assignment can't be elided by `model_dump(exclude_unset=True)`.

Why an amendment rather than "phase 3 will fix the readers": one reader is not ours and is not
migrating. `package_project_for_training` copies `eval.kiln` verbatim into the zip handed to the
closed-source remote prompt-optimization service, which resolves the train filter out of
`train_set_filter_id` (functional spec §6.3). §6.4 changes the *local* `has_train_set` check only.
A train split written solely to `splits` is invisible to that service permanently — not until a
later phase. Pulling §6.4 forward would have closed three of the four knock-ons and left that one
open forever.

The rule also runs in the direction §2.6's unknown-provenance fallback already picks: when in
doubt, write where more readers can see it.

Creation paths checked in this phase: the update endpoint (below) is the only site that creates a
split. `eval_api.py`'s create-eval endpoint passes `eval_set_filter_id=` as a construction kwarg, so
the fold already homes it in the legacy field, and needs no change. Phase 3's creation paths have
the same choice to make, and it is recorded for them in `implementation_plan.md`.

### 4b. `eval_api.py` — the update endpoint's train-split write

Architecture §2.6.2 names this as the one non-test assignment site that has to move, and §8
schedules it for phase 3. It moved here instead: once the fold stops re-deriving `splits`, the old
line doesn't merely fail to take effect — the serializer writes `train_set_filter_id: null` over the
caller's input — so leaving it would have shipped an endpoint that silently discards what it was
given. The "already set" check moves to `eval.splits.get("train")` for the same reason, and is
strictly broader: it now also catches an EvalInput-backed train split.

It calls `set_split`, not a direct `splits` write. The endpoint exists so prompt optimization has a
train set; prompt optimization reads that split out of the packaged project file; so the legacy
field is where it has to land.

### 5. `libs/core/kiln_ai/datamodel/eval_splits.py`

New module (§3): `ItemSource`, `ItemKey`, `ResolvedSplit`, `resolve_split`, `eval_run_item_key`.
`resolve_split` is the only `match` over the `SplitRef` union; `ResolvedSplit` precomputes its
`ItemKey` set so membership is a set lookup rather than a scan per result row.

### 6. `eval_runner.py` — the reads that had to move now

Three reads of the legacy fields become reads of `splits["test"]`: the source-mode check and the
filter in `collect_tasks_for_eval_input` (forced — `eval_input_filter_id` no longer exists), and
the filter in `collect_tasks_for_task_run_eval`. See "Judgment calls" below. §4's collapse of the
two collection paths is still phase 4's.

## Tests

Datamodel (`test_eval_model.py`, class `TestEvalSplits`), covering architecture §9.1:

- `test_legacy_eval_file_round_trips_byte_identically` — **the gate**. A hand-written
  pre-`splits` eval file is loaded and saved; the bytes are unchanged, so no `splits` key is added
  and no field is dropped or invented.
- `test_changing_a_test_splits_backing_moves_its_storage` saves **twice** and asserts the in-memory
  model after each save, and `test_a_split_edit_survives_unrelated_edits_and_saves` puts a rename
  between the edit and the save. These are the guards on §12.1: saving is itself an assignment, so
  a fold that ran twice would write the right file once and revert it afterwards.
- `test_whole_dict_assignment_replaces_splits` — `eval.splits = {...}` and `eval.splits[...] = ...`
  must not disagree.
- `test_clearing_a_legacy_field_does_not_move_its_split` — writing a legacy field doesn't half-edit
  a split, which would leave an old build and a new build disagreeing about the same eval.
- `test_both_legacy_test_filters_is_rejected` — the surviving half of `validate_filter_fields`;
  `test_shim_wins_over_an_explicit_splits_entry` pins the other direction of the same conflict.
- **`set_split` (step 4a).** `test_set_split_stores_a_new_split_in_its_legacy_home` pins the legacy
  homing. `test_set_split_uses_the_dict_when_no_legacy_field_can_hold_it` and
  `test_set_split_moves_a_split_out_of_its_legacy_home` assert correct outcomes, but those outcomes
  come from the serializer's own re-check rather than from `set_split`'s bookkeeping — they are
  outcome tests, not discriminating ones, and are described that way rather than as coverage of the
  homing condition. What discriminates it is
  `test_direct_assignment_after_set_split_authors_in_the_new_format`: `set_split` un-homes a split
  it moves to `splits`, so a later direct assignment stays in the new format instead of silently
  returning to the legacy field.
  `test_set_split_survives_exclude_unset` covers the fields-set marking — it builds the eval from a
  legacy field, because an eval built with `splits=` has the field already marked and the test would
  pass without the code under test.
  `test_set_split_refuses_to_mutate_a_readonly_eval` covers the readonly guard.
- `test_unknown_field_inside_a_split_survives_a_round_trip` and
  `test_unknown_split_source_fails_the_load` — the two halves of the forward-compat decision
  (judgment call 6).
- `test_a_split_is_never_dropped_by_an_excluded_legacy_field` — a split always lands in one of its
  two homes, under `exclude_none` and `exclude`.
- `test_serialization_schema_still_describes_the_fields` — a unit-level guard on the JSON-schema
  override, so a pydantic upgrade fails here with an obvious cause rather than as a schema diff.
- `test_legacy_fields_fold_into_splits`, `test_fresh_eval_has_populated_splits` (§2.7),
  `test_legacy_field_wins_over_splits_entry`.
- `test_splits_native_eval_does_not_acquire_legacy_fields`,
  `test_legacy_eval_gaining_a_val_split_keeps_its_legacy_fields` (the mixed-backing case),
  `test_reserialized_eval_reloads_to_the_same_splits`.
- `test_eval_input_backed_test_split_from_the_shim` — the shim maps to `splits["test"]` and the key
  is never written back.
- `test_unknown_split_key_survives_a_round_trip` (`holdout`).
- `test_eval_input_split_rejects_task_run_only_filters` — `high_rating` / `multi_filter::` are
  `ValidationError` on `EvalInputSplit` and accepted on `TaskRunSplit`.
- `test_dict_round_trip_keeps_legacy_format`, `test_model_copy_keeps_legacy_format`,
  `test_unknown_provenance_falls_back_to_legacy_fields`.
- `test_writing_a_train_split_is_serialized_in_the_arrival_format` — what the update endpoint
  does, in both formats. The endpoint's own tests (`test_eval_api.py`) now express "this eval has
  a train split" as `splits["train"]` rather than as a legacy-field assignment, which is what they
  meant all along.
- `test_eval_requires_a_test_split`, `test_eval_legacy_only_validates` (declaration-order guard).
- The removed migration is inverted rather than deleted: `test_no_train_split_minted_on_load` and
  `test_no_train_split_minted_on_new_eval` assert nothing mints a train split
  (functional spec §3.2). The slugification tests go with the code they tested.

Accessor (`test_eval_splits.py`, new), covering §9.2:

- `resolve_split` over each backing returns items from the correct store only; a
  configured-but-matching-nothing filter is an **empty** `ResolvedSplit`, an absent split is `None`.
- `test_legacy_eval_resolves_its_test_split` — no caller needs to know it came from
  `eval_set_filter_id`.
- `eval_run_item_key` for both `EvalRun` shapes, and its guard.
- `test_membership_does_not_cross_stores` — a `TaskRun` and an `EvalInput` sharing an id;
  the TaskRun-keyed run is not a member of the EvalInput-backed split. This is the test that fails
  if anything reverts to comparing bare ids.
- `test_golden_set_is_not_a_split`.

### Every test in this phase is mutation-tested

Three review rounds each found a test in this phase that read well and discriminated nothing: five
vacuous assignments in `test_eval_runner.py`, two docstrings claiming coverage they didn't have,
and `test_set_split_survives_exclude_unset` passing against a fixture that pre-set the field. So
the claims above are not asserted, they are measured: 32 mutations — one per behavior this phase
claims — were applied to the source, the named tests run, and the source restored. **All 32 are
killed.** The harness ships with the specs —
`specs/projects/eval_splits_v1_v2/phase2_mutation_sweep.py` — because re-running it is the cheapest
way for a later phase to check that this phase's tests still bite:
`uv run python specs/projects/eval_splits_v1_v2/phase2_mutation_sweep.py`.

Covered: the fold's run-once guard, both fold branches, provenance recording, `validate_splits`,
both shim behaviors, four serializer behaviors (legacy-field-present check, provenance,
empty-`splits` deletion, legacy writes), the JSON-schema override, all four `set_split` behaviors
(readonly guard, fields-set marking, homing in both directions), `extra="allow"` on **both** split
types, `EvalInputSplit`'s filter-type narrowing, five `eval_splits.py` behaviors (absent-split
`None`, correct store, source-aware membership, `item_keys` copying, `eval_run_item_key`), two
runner behaviors, both update-endpoint behaviors, and both halves of the V2-judge guard. Two
further mutations confirm deleted behavior stays deleted: folding golden in as a split, and
re-introducing train-split minting.

Two mutations initially survived and were fixed rather than explained away — `set_split`'s
fields-set marking (the fixture pre-set the field; the test now builds from a legacy field) and its
homing bookkeeping (nothing exercised the one sequence where it is load-bearing; that sequence is
now a test). One mutation was mis-written rather than surviving: gating minting on
`_loaded_from_file` inside the fold is dead code, because that flag is only set after validation
returns (see §2.7).

Carry-forward from the phase 1 review — the V2-judge 422 invariant, not just one endpoint:

- `test_endpoints_reject_v2_judge` (`test_judge_feedback_batch_api.py`) is parametrized over
  `create`, `run` and `create_and_run`, with `JudgeFeedbackBatchRunner` patched to raise if
  reached, and asserts no batch is written.
- `test_run_rejects_v2_judge` (`jobs/workers/test_judge_feedback_batch.py`) covers the fourth
  caller, `JudgeFeedbackBatchJobWorker.run`.
- Both were verified to fail when the guard is removed.

Test churn read rather than mechanically fixed:

- The six non-datamodel tests that built an EvalInput-backed eval via `eval_input_filter_id=` now
  pass `splits={"test": EvalInputSplit(...)}`. They still passed through the shim, but that shim is
  a throwaway (§2.6.1) and those tests are not about it.
- Five assignments in `test_eval_runner.py` that pointed an eval's test split at a tag by writing
  `eval.eval_set_filter_id` now write `splits["test"]`. Only two of them failed after the fold fix;
  the other three had started passing **vacuously**, because the fixture's `all` filter happens to
  select the same single run the tag does. That is §12.6's hazard in the wild: the tests still
  passed, and had stopped testing what they name.

Not changed, and deliberately: the `train_set_filter_id` assignments in
`test_prompt_optimization_job_api.py` and the `eval_set_filter_id` assignment in
`test_eval_api.py`'s results-summary cache test. Those exercise production code that still reads
the legacy field, so they are load-bearing today and move with their readers in phases 3 and 6.

## Judgment calls made during implementation

Recorded separately because they are **not** derived from `architecture.md` — they are decisions
taken while building, and are the parts of this phase most worth a reviewer's disagreement.

1. **`__get_pydantic_json_schema__` override on `Eval`** (`_without_model_serializer`). Not
   anticipated by the architecture. A wrap `model_serializer` makes pydantic describe the model's
   *serialization* schema as a bare `{"type": "object", "additionalProperties": true}` — and
   FastAPI generates response schemas in serialization mode, so `Eval` would have collapsed to an
   untyped object in `api_schema.d.ts` and taken every web-UI read of `evaluator.name`,
   `eval_set_filter_id` etc. down with it. The options were to abandon §2.6's serializer or to
   restore the field-derived schema; I restored the schema, since every key the serializer can emit
   is a declared field, so the field-derived schema is the accurate description. The regenerated
   client confirms it: `Eval` is unchanged apart from `eval_input_filter_id` → `splits`. The cost is
   a piece of pydantic-internal knowledge (where `serialization` sits on the core schema) that could
   break on a pydantic upgrade — it would surface as a schema-check failure, not a silent one.

2. **Moving `eval_runner.py`'s legacy reads in this phase** rather than phase 4. Two of the three
   are forced: `eval_input_filter_id` no longer exists. The third (`eval_set_filter_id` in
   `collect_tasks_for_task_run_eval`) I moved as well, for consistency with the EvalInput arm
   beside it. My original justification — that it prevents phase 3 landing red — **was wrong**, as
   the reviewer showed: five other sites still read the legacy field and break at the same moment,
   so this change buys nothing on its own. It is still the right change, just not a sufficient one;
   the full list of sites — Python, web UI, and the one nobody can fix — is recorded against phase 3
   in `implementation_plan.md`.

3. **An input carrying both `eval_input_filter_id` and `eval_set_filter_id` raises**, rather than
   the earlier behavior of folding both and letting the legacy field win, which silently discarded
   the EvalInput backing. Architecture §2.8 argues the "exactly one backing" invariant becomes
   structural, and it does — for the model, where one key holds one value. It does not cover two
   *inputs* naming the same split, which is a state the shim can still be handed. Raising is the
   smaller of the two dishonest options, and it retires with the shim. §2.5 and §2.8 have been
   updated to say so.

   The shim still *wins* over an explicit `splits["test"]` entry, which architecture doesn't
   specify. A previous version of this plan claimed that was tested; it wasn't. It is now
   (`test_shim_wins_over_an_explicit_splits_entry`), and the asymmetry with the case above is
   deliberate: two conflicting *backings* is a contradiction, while shim-vs-`splits` is the same
   old-value-wins rule the fold uses for the declared fields.

4. **`splits` is omitted from the serialized output when empty**, rather than written as `{}`.
   Required for byte-identity, and safe because an eval always has a test split.

5. **`ResolvedSplit` precomputes its key set** in a non-init frozen field, and `item_keys()` returns
   a copy. `__contains__` is called once per result row in phase 6's endpoints, so the set is built
   once; the copy keeps a caller that mutates the returned set (phase 6's
   `remaining_expected_dataset_ids`) from corrupting the split.

6. **Forward compatibility is two levels deep, not three, and that is a decision.** Unknown split
   *names* round-trip (§2.2), and unknown *fields inside* a `SplitRef` now round-trip too —
   `TaskRunSplit` and `EvalInputSplit` are `extra="allow"`, which is the same argument §2.2 makes
   for keys, applied one level down. That holds only for splits stored in `splits`: a split
   projected into a legacy flat field becomes a bare filter-id string, and its extras are dropped.
   Unavoidable — the legacy field has room for one string — and noted in the field comment. An unknown `source` value still fails the whole `Eval` to load.
   That is deliberate, and `test_unknown_split_source_fails_the_load` pins it: an unknown *key* is a
   split this build can safely ignore, whereas an unknown *source* on a split this build addresses
   (`test`) cannot be resolved to items — accepting it as opaque would convert a loud load failure
   into a silent "this eval has no items" at every reader, and `validate_splits` would pass while
   the eval was unusable. It would also give an escape from the filter-type guarantee §2.1 exists to
   enforce. The sharp edge, worth revisiting if a third source ever appears: an unknown source on a
   split this build *doesn't* address (`holdout`) fails the load too, which is exactly the §2.2
   failure mode. Fixing that asymmetry needs a per-entry decision the current shape can't express.

## Architecture corrections made in this phase

`architecture.md` has been edited three times from this phase; recorded here so the changes are
visible in review. The amendment adding `Eval.set_split()` to §2.6 is the substantive one and is
described in step 4a. The other two are statements about how pydantic behaves, verified against it
rather than reasoned about:

1. **§2.6's "provenance does not survive `model_copy()` or `Eval(**eval.model_dump())`" was wrong
   in both halves.** Pydantic copies private attributes, so `model_copy`, `model_copy(deep=True)`,
   `deepcopy` and `pickle` all carry provenance; and a dict round trip *re-derives* it, because the
   dump of a legacy eval has no `splits` key and the fold re-runs over the legacy fields. Only
   `model_construct` reaches the content-determined fallback. §2.6 and §12.3 now say this, and the
   two test docstrings that claimed to exercise the fallback have been corrected — one test covers
   it, not three.

2. **§12.1's risk was pointed at the wrong thing, and my first read of it made it worse.** I
   reported that `validate_assignment=True` makes legacy-field assignment *work*, and suggested
   downgrading the risk. The same mechanism was in fact re-running the fold on every assignment —
   including `save_to_file`'s own `self.path = path` — so writes to `splits` were reverted in
   memory and undone on disk at the next save, on exactly the legacy evals this design protects.
   Fixed in the fold (step 3) and §12.1 is rewritten around the real invariant: **the fold must
   run once**. The original "assigning a legacy field does nothing" edge is true again, and is
   kept as the milder half of that risk.

**Readonly, corrected.** An earlier version of this plan noted that dict mutation bypasses the
readonly guard and concluded "no code does it". That stopped being true the moment `set_split`
became a blessed public mutator that looks like an attribute setter — and readonly instances are the
*cached* ones, shared with every other holder of the file, so a silent mutation there is not a local
mistake. `set_split` now calls `_ensure_not_readonly("splits")` explicitly, with a test. Direct
`eval.splits[...] = ...` on a readonly instance still bypasses the guard, exactly as
`template_properties` and every other dict field on these models does; that is pre-existing
behavior this phase does not change, and `set_split` is the path that is now safe.

`ResolvedSplit` is `frozen=True` with `eq` on, so it is unhashable while `items` is a list. Nothing
hashes it and §6.3's cache keys on `(source, filter_id)` rather than on the split, so this is left
alone — flagged in case phase 6 wants one in a set.

Two more left alone deliberately:

- **Shallow `model_copy()` aliases `splits` and `_legacy_homed_splits` with the original**, so
  mutating `copy.splits[...]` mutates the source. That is pydantic's normal shallow-copy behavior
  for any mutable field, and the repo's own copy path (`mutable_copy`) deep-copies, so no production
  caller is exposed. Worth knowing because `splits` is a field callers are now told to mutate in
  place; `set_split` doesn't change it either way.
- **`model_dump(exclude_unset=True)` after a direct `eval.splits[name] = ref`** still omits the
  split when no legacy field can hold it, because item assignment leaves the field unset.
  `set_split` marks it set, which covers the path this phase blesses; the direct-assignment path is
  a caller-beware combination, and nothing in the repo dumps an `Eval` with `exclude_unset`.

The `TODO: Remove before shipping` on the `eval_input_filter_id` shim is required by §2.6.1 and
fine mid-project, but CI blocks TODOs on `main` — it must go with the shim before the final PR.
