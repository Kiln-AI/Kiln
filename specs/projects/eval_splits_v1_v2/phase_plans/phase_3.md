---
status: complete
---

# Phase 3: Creation paths and prompt optimization

## Overview

Two things happen here. Spec eval creation starts speaking `splits` instead of flat filter-id
fields, and gains the val split functional spec §3.3 asks for. And prompt optimization stops asking
"is `train_set_filter_id` set?" and starts asking "does this eval have a train split the remote
optimizer can actually resolve?" (architecture §6.4).

The phase is small because of the decision below. It is only small because of that decision.

## The decision: new spec evals keep their legacy homes

`implementation_plan.md` puts this first, and architecture §2.6's table leaves it to this phase.

**Decision: a new spec eval's TaskRun-backed test and train splits are stored with
`Eval.set_split()`, so they serialize to `eval_set_filter_id` / `train_set_filter_id`. Its val
split has no legacy field and stays in `splits`.**

The alternative — construct with `splits=` alone and let all three land in the dict — is what the
implementation plan's hazard list is a list of. Under it, every reader of the two legacy fields
breaks for evals created from that moment on: five `eval_api.py` readers, the eval job worker,
nine web-UI reads, four `prompt_optimization_job_api.py` reads, and `package_project_for_training`,
whose consumer is the closed-source remote optimizer in another repo that is not migrating at all
(functional spec §6.3). That last one cannot be fixed by any later phase of this project, so the
choice is not "migrate the readers now or in phase 6" — it is "migrate them, or make one reader
permanently blind".

**Precisely what the decision guarantees, and what it does not.** `set_split` records where a split
will be *written*; the serializer is what writes the legacy fields. So the in-memory instance the
creation path holds has `eval_set_filter_id is None` and `train_set_filter_id is None` — the fields
are populated in the bytes, not on the object. That is architecture §2.4's "their in-memory values
are not authoritative" working as designed, and neither creation path reads them in-process, so it
is correct rather than a latent bug. But it narrows the guarantee this phase can claim: **every
reader that loads the eval from disk sees both legacy fields**, which covers all of them — the job
worker, the five `eval_api.py` reads, the nine web-UI reads (via an API response serialized from a
loaded eval) and `package_project_for_training` (which copies the file verbatim). The broader
reading — "the legacy fields are always populated" — is false, and a later phase must not rely on
it: an `Eval` handed to it in-process, unsaved, will have them as `None`.

Two consequences worth stating rather than leaving implicit:

- **Architecture §2.9 does not need revisiting.** §2.9 accepts that an old build re-saving an eval
  drops the `splits` dict, and bounds the damage to "splits that only new tooling creates". Under
  this decision that bound holds exactly: the only thing a new spec eval keeps in `splits` is its
  val split, which is new tooling's. Had the test split gone into `splits`, an old build re-saving
  a brand-new spec eval would have dropped the eval's *test* set — silently turning a working eval
  into one that fails `validate_splits` on the next load by a new build. That is materially outside
  what §2.9 accepts, and it is the concrete reason for this decision rather than a stylistic one.
- **The new format is not being avoided; it is being applied where it is the only option.** A new
  spec eval is exactly architecture §2.6's mixed shape — legacy test and train fields plus a
  `splits` key holding only val — which §2.6 calls out as the shape phase 3 was expected to
  consider.

What this decision does *not* buy: an eval with a TaskRun-backed train split stored in `splits`
(hand-authored, or written by future tooling) still reports `has_train_set: true` with a null
`train_set_filter_id`, so the prompt-optimization page shows no train size and no dataset link
(implementation plan's web-UI list, `create_prompt_optimization_job/+page.svelte:521, 1074, 1111`).
No code path in this repo produces that eval after this phase, so it is a latent gap rather than a
regression, and it belongs with phase 6's UI work. It is recorded in "Deliberately not done" below.

## Steps

### 1. `libs/server/kiln_server/utils/spec_utils.py` — splits, not a widening tuple

`generate_spec_eval_filter_ids` returned a 4-tuple of strings whose positions had to be memorized
(architecture §8). It is replaced by:

```python
def spec_eval_splits(
    *, eval_tag: str, train_tag: str, val_tag: str
) -> dict[EvalSplitName, SplitRef]:
    """The splits a new spec eval is created with: test, train and val, all TaskRun-backed."""

def tag_filter_id(tag: str) -> DatasetFilterId:
    """The dataset filter that selects items carrying `tag`."""

def set_spec_eval_splits(eval: Eval, splits: Mapping[EvalSplitName, SplitRef]) -> None:
    """Store each of a new spec eval's splits where the most readers can find it."""
```

Keyed by `EvalSplitName` (the datamodel's `Literal["train", "val", "test"]`) rather than `str`,
added after review: `spec_eval_splits` is a closed constructor of exactly those three keys, so a
`"tests"` typo is a check-time error rather than a runtime one. `set_spec_eval_splits` takes a
`Mapping` because dict key types are invariant. `Eval.splits` is still `str`-keyed by design, so
`build_spec_eval` widens once, at the single point of construction.

`generate_spec_eval_tags` keeps returning four tags — the copilot passes them to
`create_dataset_task_runs` to tag the runs it generates, so they are tags, not filter ids, and
golden is one of them. It now returns them as a `SpecEvalTags` NamedTuple: existing positional
unpacking still works, and callers that want one of four same-typed strings name it instead of
counting positions. Golden is not a split (architecture §2.3), so its filter id comes from
`tag_filter_id` rather than from the splits dict.

`set_spec_eval_splits` loops `eval.set_split(name, split)` over every split rather than branching
on which ones have a legacy home. `set_split` already encodes that rule; duplicating it in the
caller would be a second place to get it wrong. For val the call is storage-neutral (no legacy
field can hold it), which is the correct outcome, not a special case.

**The two-step shape is forced.** `validate_splits` requires a test split at construction, so the
eval cannot be built empty and then filled in by `set_split`. The splits are passed to the
constructor and then re-stored through `set_split`, which changes where they serialize without
changing the model. This reads like a no-op and is not one — see "Judgment calls".

### 2. `build_spec_eval` — one creation path, not two copies of one

**Reworked after review.** The first implementation left the construction sequence inline in both
`create_spec` and `create_spec_with_copilot`, as two byte-identical blocks differing only in where
`name` came from. That duplication predates this phase, but this phase made forgetting it
consequential: it added a sixth step, `set_spec_eval_splits`, whose omission produces an eval that
looks completely correct in memory and whose test and train splits are invisible to older builds
and to `package_project_for_training`. A third creation path — or an edit to either of these two —
would have had to remember it, with nothing failing if it did not.

Both paths now call one factory in `spec_utils.py`:

```python
def build_spec_eval(
    *, task: Task, name: str, spec_type: SpecType, evaluate_full_trace: bool
) -> tuple[Eval, SpecEvalTags]:
    """A new spec eval, with its splits already stored where readers look for them."""
```

It returns the tags alongside the eval because the copilot needs them for
`create_dataset_task_runs`; `create_spec`, which generates no runs, discards them. The eval is not
saved — both callers have their own save ordering (the copilot batches every model and saves once,
`create_spec` saves the eval then rolls it back if the spec fails).

`spec_eval_splits` is keyword-only. Three same-typed tag strings in a fixed order is the hazard
architecture §8 exists to remove, and replacing a tuple return with a positional signature would
have moved that hazard rather than eliminated it — the sweep's own "test split points at the train
tag" mutation is a swap of exactly that kind. `*` makes it unrepresentable at every call site.

No legacy field is named in either creation path after this. The copilot's
`create_dataset_task_runs` call is unchanged apart from reading its tags off `SpecEvalTags` — it
already tags val runs.

`eval_api.py`'s create-eval endpoint is deliberately left alone: it takes `eval_set_filter_id` as a
request field, the fold homes it, and changing the request shape is phase 6's API work.

### 3. `app/desktop/studio_server/prompt_optimization_job_api.py` (architecture §6.4)

```python
def has_task_run_train_split(eval: Eval) -> bool:
    """Whether this eval has a train split the remote optimizer can resolve."""
    return isinstance(eval.splits.get("train"), TaskRunSplit)
```

Replaces `bool(eval.train_set_filter_id)` at all four `check_eval` return sites. Its answer changes
in two ways: an EvalInput-backed train split now reports `False` (functional spec §6.3), and a
legacy eval that used to receive an auto-minted train filter reports `False` because phase 2
deleted the minting (functional spec §3.2).

`start_prompt_optimization_job` gains a refusal, before any packaging or upload:

```python
reject_unusable_train_splits(task, request.eval_ids)
```

400 naming the eval and the reason. It resolves the requested ids against `task.evals(readonly=True)`
rather than `eval_from_id`, because an id that names no eval is not this guard's business — the
endpoint does not validate eval ids today and making it 404 would be an unrequested behavior change.

It refuses a train split that is **present and not TaskRun-backed** — not a missing one. Functional
spec §6.3 and §9 scope the 4xx to the unusable case, and the UI already gates start on
`has_train_set`; refusing an absent train split would be a broader behavior change than the spec
asks for.

**Phrased as the complement of "TaskRun-backed", not as "is an `EvalInputSplit`"** — changed after
review, and the reason is worth keeping. The first version named `EvalInputSplit` explicitly, which
is equivalent today because it is the only other `SplitRef` variant. But `has_task_run_train_split`
asks the safe question ("is it TaskRun-backed?", so an unknown variant answers `False`) while the
guard asked the unsafe complement: add a third variant to the union and `check_eval` would keep
reporting `has_train_set: false` while the guard silently stopped refusing — optimizing against an
empty set, which is the exact outcome functional spec §6.3 exists to prevent. Nothing in the type
system flags it; the union grows and the line keeps compiling. The rest of this project uses
`raise_exhaustive_enum_error` for the same reason. Renamed `reject_unusable_train_splits` to match
what it now checks, and the 400's message describes the requirement ("isn't backed by dataset
runs") rather than the one variant that violates it today.

**The guard delegates "usable" to `has_task_run_train_split` rather than re-testing it** — a second
review-round change. Keeping its own `isinstance` check put two copies of the same definition 25
lines apart in one file, which is the same drift hazard as the paragraph above in the other
direction: widen what counts as usable and `check_eval`'s `has_train_set` and the guard would
disagree, with the sweep mutating each independently and no test forcing them together. Only the
presence clause stays local, because that part genuinely differs between the two — `check_eval`
reports an absent train split, the guard ignores it.

## Tests

Mutation-tested — see the sweep section.

`libs/server/kiln_server/utils/test_spec_utils.py` (replacing `TestGenerateSpecEvalFilterIds`):

- `test_splits_are_task_run_backed_tag_filters` — three splits, all `TaskRunSplit`, filter ids
  `tag::<tag>`; no golden key.
- `test_set_splits_stores_test_and_train_in_their_legacy_homes` — asserts on `model_dump()`, not on
  `eval.splits`: both legacy fields carry their filter ids and the dumped `splits` holds only val.
  Architecture §2.6 is explicit that picking `set_split` vs direct assignment wrongly is invisible
  in the model and visible only in the serialized bytes, so this is the only shape of assertion
  that can discriminate it.
- `test_tag_filter_id_prefixes_the_tag`.
- `TestBuildSpecEval::test_returns_the_tags_the_evals_items_must_carry` — the four tags come back
  as a `SpecEvalTags`, and `eval_configs_filter_id` points at the golden tag. Golden is not a
  split, so no splits assertion covers it.
- `TestBuildSpecEval::test_splits_are_built_and_homed_in_one_step` — the factory's whole reason for
  existing. Asserts the in-memory splits *and* the dump, so an eval that never homes its splits
  fails here rather than only at the two API call sites.

An earlier version of this file also had `test_where_a_split_is_stored_is_invisible_in_the_model`,
which asserted `eval.splits == splits` after `set_spec_eval_splits`. Its own docstring conceded it
passed whichever storage the code picked — it could not fail for the code under test. **Removed
after review**: a test that cannot fail reads as coverage at a glance, and the warning it carried
now lives in the docstring of `test_set_splits_stores_test_and_train_in_their_legacy_homes`, three
lines from the assertion it explains, which is where someone editing that code will read it.

`libs/server/kiln_server/test_spec_api.py` / `app/desktop/studio_server/test_copilot_api.py`:

- The existing create tests already read the raw saved file. They are extended to assert the whole
  split layout on disk: `eval_set_filter_id` and `train_set_filter_id` populated, and
  `saved["splits"] == {"val": {...tag::val_test_spec...}}`. The stale comment about the lazy train
  migration (deleted in phase 2) is replaced by what the raw-file read now guards.
- The same tests assert `evals[0].splits` in memory, so a val split that never reaches the model is
  caught separately from one that reaches it and serializes wrong. (An earlier draft of this plan
  named that as a separate test, `test_create_spec_eval_has_a_val_split`, which was never written —
  the assertion lives in the existing create test instead.)
- Both now assert `eval_configs_filter_id`. Golden is not a split, so no splits assertion covers
  it, and this phase changed the line that sets it — on the copilot side the assertion was missing
  entirely, which review caught by mutating it to the eval tag and watching 1767 tests pass.

`app/desktop/studio_server/test_prompt_optimization_job_api.py`:

- `test_check_eval_has_train_set_by_split_backing` — parametrized over no train split / TaskRun-backed
  / EvalInput-backed → `False` / `True` / `False`, against real `Eval` instances rather than
  `MagicMock`. The existing parametrized test set `mock_eval.train_set_filter_id`, which after this
  change discriminates nothing at all: `MagicMock().splits.get("train")` is never a `TaskRunSplit`,
  so it would report `False` for every case and pass on both branches of the parametrize only
  because one of them expects `False`. It is rewritten rather than kept.
- `test_check_eval_no_current_config` and `test_check_eval_config_not_found` are parametrized over
  the same three cases (`TRAIN_SPLIT_CASES`), so both early-return sites report the eval's real
  state in both directions. The config-not-found one originally asserted `False` against an eval
  with no train split, which review showed discriminates nothing: with no train split the old
  `bool(eval.train_set_filter_id)` and the new helper both return `False`, so leaving that site
  un-migrated survived the whole test file. Sharing one parametrize list is what stops the two
  sibling sites from drifting apart again.
- `test_check_eval_missing_model_name` / `..._missing_model_provider` are the `True` and `False`
  halves of the third return site, and carry a comment saying so — with only the `False` half, that
  site could report a constant and pass.
- `test_start_prompt_optimization_job_refuses_unusable_train_splits` — parametrized over
  EvalInput-backed / TaskRun-backed / absent train split → 400 / 200 / 200. The 400 case also
  asserts `package_project_for_training` was never called and no `PromptOptimizationJob` was
  written, and the two 200 cases are what stops the guard from being "refuse everything". The whole
  success path is patched in all three cases, so without the guard the refusal case would return
  200 — the test discriminates the guard rather than an incidental failure.
- `test_start_prompt_optimization_job_ignores_unrequested_evals` — the task holds an eval the guard
  would refuse and the request names an id matching no eval; the job still starts. Pins both that
  unknown ids are skipped and that the guard reads the requested ids rather than every eval on the
  task.

### Mutation sweep

`specs/projects/eval_splits_v1_v2/phase3_mutation_sweep.py`, same harness shape as phase 2's:

    uv run python specs/projects/eval_splits_v1_v2/phase3_mutation_sweep.py

**23 mutations, all killed.** Covered: the three spec-eval splits and their tag filter ids,
`set_spec_eval_splits` in three failure shapes (does nothing, authors in the new format, homes only
some splits), `build_spec_eval`'s homing call / golden filter id / construction, the copilot's use
of the returned tags, `has_task_run_train_split` in three directions, all four `check_eval` return
sites, and four behaviors of the start-job guard (present, scoped to a *present* unusable split,
skips unknown ids, reads the requested ids).

The three `has_task_run_train_split` mutations now discriminate **two** sites rather than one,
since the start-job guard delegates its usability question to that helper: "always True" stops the
guard refusing anything and "always False" makes it refuse a usable TaskRun-backed split, and the
refusal test catches both. That is the coupling the delegation was for, made executable.

The count went 25 − 6 + 3 + 1 = 23. The factory collapsed six mutations into three — with one
construction sequence instead of two copies, "spec_api: golden filter id" and "copilot_api: golden
filter id" are the same line — and one mutation was added for the copilot's use of the tags the
factory now returns to it (`copilot_api: generated runs tagged with the train tag as the test tag`),
which is new surface the factory created.

The three factory mutations are run against **both** API test files as well as the factory's own,
which is what still proves both creation paths go through it — a path that inlined its own
construction would survive all three.

Mutations are also **attributed** — re-run against the single test named for them rather than the
whole file, so the `-x` harness is not what kills them. Done for the original set, for the ten
added or rewritten in the first review round, and for the six added or changed by the second (the
three `build_spec_eval` mutations, the copilot's tag use, and the two start-job guard entries).
All killed by their named test alone.

Two properties are deliberately *not* in the list, rather than silently missing:

- **The guard's placement before packaging.** Moving the call is a deletion plus an insertion ~30
  lines away, and this harness applies one contiguous edit. It is covered by
  `mock_package.assert_not_called()` in the refusal test, confirmed by hand-moving the call.
  An earlier version listed this as a mutation, but that entry deleted the call instead of moving
  it, making it a duplicate of "guard removed" — review caught it, and the count in this section is
  now distinct behaviors rather than list entries.
- **The values passed to the constructor's `splits=`.** An equivalent mutant, because
  `set_spec_eval_splits` re-sets all three afterwards. Verified three ways during review
  (`{test only}`, `{test, train}`, `{test: wrong filter}` all dump identically). What *is*
  load-bearing — a test split reaching the constructor before `validate_splits` runs — is mutated
  as `splits={}`.
- **The start-job guard narrowed back to naming `EvalInputSplit`.** Also an equivalent mutant: it
  is the only other `SplitRef` variant today, so no test can distinguish the two phrasings. The
  closed phrasing is there for the variant that does not exist yet, and the reason it is preferred
  is recorded in step 3 rather than left to a mutation that could never fail.

One mutation was **killed for the wrong reason** and was rewritten: `spec_eval_splits: val split
is EvalInput-backed` named `EvalInputSplit` directly, which `spec_utils.py` does not import, so it
died of a `NameError` at call time rather than of the `isinstance` assertion it exists to check —
it would have reported "killed" even with that assertion deleted. It now resolves the class inline
(`__import__(...).EvalInputSplit`) and is killed by
`test_splits_are_task_run_backed_tag_filters` alone, attributed against that test by name.

Mutations that survived a run and were fixed rather than explained away:

1. **`start job: unknown eval ids fall through to another eval`** (first run) — the test naming
   that behavior used a task with no evals, so there was nothing to fall through to. The test now
   puts a refusable eval on the task, which kills it and a new "checks every eval on the task"
   mutation too.
2. **the copilot's golden filter id taken from the eval tag** and **`check_eval: config-not-found
   return left un-migrated`** (found by review, not by this sweep) — both survived the entire
   suite. Fixed by the assertions described above; both are in the sweep, the first now as
   `build_spec_eval: golden filter id from the eval tag` since there is one construction site.

The four `check_eval` site mutations were also rewritten. They previously hardcoded a constant;
they now restore the pre-phase `bool(eval.train_set_filter_id)`, which is the plausible defect —
one site left un-migrated — and is strictly stronger, since these test evals carry their splits in
`splits` and so read `None` from the legacy field.

Phase 2's sweep was re-run unchanged against this tree: **32/32 still killed.**

The sweep script is kept as a committed project artifact next to `phase2_mutation_sweep.py`, for
the same reason: it is the executable record of what the phase's tests actually discriminate, and a
later phase changing this code can re-run it to find out what it broke.

### The self-sweep for the same shape

Review found two tests that read as coverage and discriminated nothing. Rather than fix only those,
every test this phase adds or claims was re-checked for the same shape — is the site's mutation
discriminated in *both* directions, and is the sweep's chosen mutation a plausible wrong
implementation? That found three more:

1. **`test_check_eval_no_current_config`** had the same one-direction weakness as its
   config-not-found sibling, just in the opposite direction (`True` only). Both are now parametrized
   over a shared list.
2. **`test_check_eval_missing_model_provider`** asserts `False` with no train split — which alone
   discriminates nothing for that site. Its `missing_model_name` sibling carries the `True` half, so
   the site is covered; a comment on both now says so, since deleting either would silently open a
   hole.
3. **`set_spec_eval_splits` had no mutation for homing a *subset* of splits** — a partial migration
   is a distinct and plausible defect from "authors all of them in the new format", and the sweep
   only had the latter. Added, and killed by the dump assertion.

Also corrected: this plan named a test (`test_create_spec_eval_has_a_val_split`) that was never
written, its assertion having been folded into the existing create test. A plan claiming a test
that does not exist is the documentation form of the same defect.

The second review round closed the loop on this the other way. The one test kept *because* it
could not fail — `test_where_a_split_is_stored_is_invisible_in_the_model` — was removed, and its
warning moved into the docstring of the test that does the discriminating. The self-sweep above
asks "does this test fail for a plausible wrong implementation?"; that test's honest answer was
"no, by construction", and keeping it under a name that explained why was still one suite entry
that read as coverage.

## Judgment calls made during implementation

Not derived from `architecture.md` — decisions taken while building, flagged for disagreement.

1. **`set_spec_eval_splits` re-stores splits the constructor already received.** It reads like a
   no-op and is not one: construction records provenance as "no legacy fields", and `set_split`
   moves test and train into their legacy homes. The alternative shapes are worse — passing
   `eval_set_filter_id=` / `train_set_filter_id=` as construction kwargs puts the legacy vocabulary
   back into new code (architecture §2.4 is explicit that no new code should have to know
   `eval_set_filter_id` means "test"), and a constructor-level "which splits are legacy-homed"
   argument would duplicate `set_split`'s rule. The cost is that the call is load-bearing and
   doesn't look it, which is why the tests assert on the dump.
2. **400 rather than 422** for the prompt-optimization refusal. Functional spec §9 says "4xx". 400
   matches the two guards immediately beside it in the same endpoint (tools configured,
   non-Kiln-agent run config), which the UI already renders.
3. **The refusal resolves eval ids through `task.evals()`, and ignores ids that match no eval.**
   Adding a 404 for an unknown eval id would be a behavior change nothing asked for.
4. **`check_eval`'s four return sites all go through the helper**, including the three early
   returns that report `has_train_set` alongside a failure. Keeping them as `bool(...)` would have
   left three places reporting a different definition of "has a train set" from the fourth.
5. **`build_spec_eval` returns the eval unsaved, and returns the tags to every caller.** Saving
   inside the factory was rejected: the copilot validates every model before persisting any of
   them, and `create_spec` saves the eval then deletes it if the spec fails, so neither ordering
   can move. `create_spec` discards the tags with `_tags` rather than the factory offering two
   return shapes.
6. **`spec_eval_splits` is keyed by `EvalSplitName`, not `str`.** It costs one widening
   conversion, since `Eval.splits` is `str`-keyed and dict key types are invariant. Taken because
   this function is a closed constructor of exactly those three keys — the one seam in this area
   where the key set is genuinely closed — so the conversion buys a typo caught at check time.

## Architecture edits made in this phase

Three sections of `architecture.md` were edited from this phase, recorded here so the changes are
visible in review, as phase 2 did with its three edits.

**§2.6's table row and §8 — recording the decision, not making a new one.** Both posed this
phase's `set_split` question as still open ("phase 3's call"; "a decision phase 3 has to make
explicitly"), and §8 still described `generate_spec_eval_filter_ids` as the current shape after
this phase deleted it. Both now state the answer — new spec evals home test and train in their
legacy fields, val stays in `splits` — and point at this plan for the reasoning. §8 also carries
the guarantee's exact scope (readers that *load from disk* see the legacy fields; an unsaved
in-process `Eval` does not), because phases 5 and 6 are the most likely to consult §2.6 and §8
without this plan open, and the broader reading is false.

The remaining edit is to §2.7, and is a **factual correction, not a design change**:
§2.7's conclusion — the fold is ungated because it invents nothing — is unaffected, and no code
changed because of it.

**What was wrong.** §2.7's last paragraph said `_loaded_from_file` is set after `model_validate`
returns, so a validator gated on it can only fire on a later validation pass, and that "that is how
the existing lazy migrations fire at all". The first half is true. The second is true of exactly
one of the three validators involved.

**What is actually the case**, verified against the repo rather than reasoned about:

- `Eval.upgrade_old_reference_answer_eval_config` (`eval.py:1156`) reads `self._loaded_from_file`
  directly. It is the only validator in the repo that does, and the only one that needs the second
  pass — which `load_from_file` supplies via `m.path = path` (`basemodel.py:439`) after setting the
  attribute at `:437`.
- `task_run.py:226` (`validate_input_source`) and `task_output.py:377` (`validate_output_source`)
  call `self.loaded_from_file(info)`. That method (`basemodel.py:460`) checks the
  `{"loading_from_file": True}` context that `load_from_file` passes to `model_validate`
  (`basemodel.py:434`) *before* falling back to the private attribute, so it is true on the
  **first** validation pass. Both are strict-mode relaxations rather than data-inventing
  migrations, which is why §2.7's opening paragraph does not describe them.

**Why it needed scoping.** As written, a later phase could read §2.7 as "a run-once validator can
never detect a file load in this repo" and design around a constraint that doesn't exist. It can —
via `loaded_from_file(info)`, which is now named in §2.7 as the working idiom. The edit also
tightens §2.7's opening from "the existing migrations" to naming the one lazy migration, so the
opening and the correction agree.

## The closing sweep

Re-run at the end of the phase, per `implementation_plan.md`:

    grep -rn "eval_set_filter_id\|train_set_filter_id" --include=*.py --include=*.svelte \
      --include=*.ts libs app | grep -v api_schema.d.ts

`spec_api.py`, `copilot_api.py`, `spec_utils.py` and `prompt_optimization_job_api.py` no longer
name either field. What remains is the datamodel's own declaration and serializer, the eval-update
and create-eval endpoints' request fields, and the read sites listed against phases 5 and 6 — all
of which read a field this phase keeps populated for every eval the repo creates.

The generated OpenAPI schema was diffed before and after this phase's changes and is **identical**,
so `api_schema.d.ts` needs no regeneration. (`check_schema.sh` itself cannot run in this container:
it imports `desktop_server`, which imports `tkinter`, which isn't installed. It fails the same way
on the clean phase-2 tree, along with five test modules that import the desktop app.)

## Deliberately not done

- **The web UI.** With this phase's decision, no eval this repo creates has a train split that
  `train_set_filter_id` doesn't also carry, so the reads listed against phase 3 in
  `implementation_plan.md` keep working. The latent gap is a TaskRun-backed train split stored only
  in `splits` — `has_train_set === true && train_set_filter_id === null` skips the train-size fetch
  and passes `""` to `tagFromFilterId`. Nothing in the repo writes that eval; phase 6 owns the UI.
- **`eval_api.py`'s create-eval endpoint** (`eval_set_filter_id=` as a construction kwarg). Works
  through the fold; changing the request shape is phase 6's.
- **The five `eval_api.py` legacy reads and the job worker's.** They read fields this phase keeps
  populated. Phases 5 and 6 move them to `resolve_split` for the EvalInput-backed case, which is
  the reason they move at all.
