---
status: draft
---

# Architecture: Train/val/test splits across V1 and V2 eval datasets

Implements `functional_spec.md`. Read that first — this document does not restate behavior, only
how it is built.

## 1. Shape of the solution

Three ideas, in dependency order:

1. **A typed splits dictionary on `Eval`**, whose values are a discriminated union over the two
   backings. Adding a fourth split later is a new key, not a new field, a new migration, or a new
   accessor.
2. **Legacy fields stay the on-disk home for the splits that already have one**, so existing
   project files keep working and older Kiln builds keep reading them. Load copies them into the
   dict; save projects the dict back into them.
3. **One accessor seam** — resolve a split to its items, and identify the item an `EvalRun`
   scored — used by every call site. This is what stops the 3 × 2 matrix from becoming a source
   branch per reader.

Everything else in this document follows from those.

### Single-document decision

This is one coupled seam rather than several independent components: the model, the accessor, the
runner and the endpoints are all the same idea at different layers, and splitting them into
`components/` docs would fragment it. It runs somewhat long for a single file, which is the
trade accepted.

---

## 2. Data model

### 2.1 A split reference

New in `libs/core/kiln_ai/datamodel/eval.py`, following the repo's existing discriminated-union
idiom (`EvalInputData`):

```python
class TaskRunSplit(BaseModel):
    """A split whose items are TaskRuns, selected by a dataset filter."""
    source: Literal["task_run"] = "task_run"
    filter_id: DatasetFilterId

class EvalInputSplit(BaseModel):
    """A split whose items are EvalInputs, selected by an eval-input filter."""
    source: Literal["eval_input"] = "eval_input"
    filter_id: EvalInputFilterId

SplitRef = Annotated[
    Union[TaskRunSplit, EvalInputSplit],
    Discriminator("source"),
]
```

This is where functional spec §7 is satisfied **structurally**: `EvalInputSplit.filter_id` is an
`EvalInputFilterId`, so `multi_filter::…` or `high_rating` on an EvalInput-backed split is not a
validation failure to remember — it is unrepresentable.

### 2.2 The splits dictionary

```python
EvalSplitName = Literal["train", "val", "test"]   # the API-addressable names

class Eval(...):
    splits: Dict[str, SplitRef] = Field(
        default_factory=dict,
        description="The eval's dataset splits, keyed by split name. ...",
    )
```

**Why the key is `str` and not `EvalSplitName`.** Kiln project files sync via git and are opened
by different app versions. A `Literal`-typed key means a file containing a split this build
doesn't know about fails validation, and the whole `Eval` fails to load — a future split name
would break old builds hard. A `str` key loads, preserves the unknown entry on round-trip, and
simply doesn't expose it. Unknown keys are not an error and are not warned about; they are data
for a build that understands them.

`EvalSplitName` is the addressable surface: the API accepts only those three, and adding a fourth
is a one-line change there with no data-model change at all. That is the extensibility that
matters — no new field, no new migration, no new accessor arm.

### 2.3 Legacy fields: what stays and why

| Split + backing | On-disk home | Status |
|---|---|---|
| `test` + `task_run` | `eval_set_filter_id` | **Permanent.** In shipped public projects. |
| `train` + `task_run` | `train_set_filter_id` | **Permanent.** In shipped public projects. |
| `test` + `eval_input` | `eval_input_filter_id` | **Throwaway read-shim** (§2.6). Internal only. |
| everything else | `splits` dict | New. |

`val_set_filter_id` — added by the superseded #1621 commit — **is not carried forward**. Val is
new; no shipped file contains it; it is born in the dict. Adding a legacy field for a split that
has no legacy data would be inventing a compatibility burden.

`eval_configs_filter_id` (golden) is untouched and stays exactly where it is. It is not a split
and does not enter `splits`.

### 2.4 Load: legacy fields populate the dict

A `mode="after"` model validator, running on every construction (not only file loads — see
§2.7):

```python
@model_validator(mode="after")
def populate_splits_from_legacy_fields(self) -> Self:
    if self.eval_set_filter_id is not None:
        self.splits["test"] = TaskRunSplit(filter_id=self.eval_set_filter_id)
    if self.train_set_filter_id is not None:
        self.splits["train"] = TaskRunSplit(filter_id=self.train_set_filter_id)
    return self
```

**Precedence: a populated legacy field wins over a dict entry for the same split.** On disk at
most one of the two is ever populated for a given split (§2.5 clears the other), so a conflict
means a hand-edited file. Preferring the legacy field keeps every Kiln build — old and new —
agreeing on what the eval's test and train splits are, which is the property worth protecting.

### 2.5 Save: the dict projects back into legacy fields

Before serialization, each split with a legacy home writes to it, and clears it when it isn't
using it:

```python
def project_splits_to_legacy_fields(self) -> None:
    test = self.splits.get("test")
    self.eval_set_filter_id = test.filter_id if isinstance(test, TaskRunSplit) else None
    train = self.splits.get("train")
    self.train_set_filter_id = train.filter_id if isinstance(train, TaskRunSplit) else None
```

So on disk:

- A TaskRun-backed test or train split lives in its legacy field. **Byte-identical to today** for
  every existing eval — an eval nobody has changed serializes exactly as it does now.
- An EvalInput-backed test or train split, and every val split, lives in `splits`.
- Nothing is written twice, so the two representations cannot drift.

This is the "saving doesn't move them" contract: the dict is the API, the legacy fields remain
the storage for what they already store. Migrating them into the dict later is a separate,
deliberate change — delete the projection and the load shim together, once nothing reads the old
files.

**Where the projection hooks in** is an implementation detail with one hard requirement: it must
run on every persistence path, not just an overridden `save_to_file`. `KilnParentedModel` has
save paths that a naive override would miss. The safest placement is a `model_serializer`
(wrap-mode) or a `mode="before"` serialization hook on `Eval`, so the projection is a property of
serializing the model rather than of one method. This must be verified against `basemodel.py`'s
save machinery during implementation, and covered by the round-trip tests in §9.

### 2.6 The `eval_input_filter_id` shim

`eval_input_filter_id` does **not** remain a field on `Eval`. It is read out of the raw input by a
`mode="before"` validator and dropped:

```python
@model_validator(mode="before")
@classmethod
def migrate_eval_input_filter_id(cls, data: Any) -> Any:
    # TODO: Remove before shipping. Only internal projects contain this key;
    # no public project file has ever had it. Carries the pre-rename value
    # into splits["test"].
    ...
```

It never enters the schema, so it never reaches the web client or the API surface, and deleting
the shim is deleting one validator. This is the resolution of functional spec §3.4: the field
disappears rather than being renamed, and the principle — the split is the key, the source is a
property of its value — is expressed structurally.

### 2.7 Why the load validator is not gated on `_loaded_from_file`

The existing migrations gate on `self._loaded_from_file`, because they *invent* data and should
only do so for files. This validator invents nothing — it mirrors fields that are already set,
including on freshly constructed evals. Gating it on file loads would mean
`Eval(eval_set_filter_id="tag::x").splits` is empty while the same eval loaded from disk has a
test split, which is exactly the kind of split-brain the accessor exists to eliminate.

Callers constructing an `Eval` may set either the legacy fields or `splits`; both produce the same
resolved model.

### 2.8 Validation

Replaces `validate_filter_fields`:

```python
@model_validator(mode="after")
def validate_splits(self) -> Self:
    if "test" not in self.splits:
        raise ValueError("An eval must have a test split ...")
    return self
```

The old "exactly one of `eval_set_filter_id` / `eval_input_filter_id`" invariant **disappears
rather than being reimplemented**: `splits["test"]` is a single value, so two backings for one
split is not a state the model can be in. That is functional spec §1's "exactly one backing per
split" made structural.

This validator must run *after* §2.4, and both must tolerate partially-constructed evals during
child-loading (see the existing `_currently_migrating_eval_ids` recursion guard for the pattern —
this validator does not load children, so it should not need the guard, but must not be moved
somewhere that does).

### 2.9 Known limitation: old builds drop the dict

Persisted models use pydantic's default `extra="ignore"`. A build predating this change reads an
eval, ignores `splits`, and — if it re-saves that eval — **writes it back without the dict**.
TaskRun-backed test and train splits survive (they're in legacy fields the old build understands);
val splits and EvalInput-backed splits would be lost.

This is accepted, not solved. It is bounded to splits that only new tooling creates, it requires
an old build to write, and the alternative — refusing to load, or duplicating the dict into fields
old builds understand — is worse. Recorded here so it is a known cost rather than a surprise.

---

## 3. The accessor seam

New module: `libs/core/kiln_ai/datamodel/eval_splits.py`. It needs `Task`, `Eval` and both filter
resolvers; a separate module keeps it out of import cycles.

### 3.1 Item identity

```python
ItemSource = Literal["task_run", "eval_input"]
ItemKey = Tuple[ItemSource, ID_TYPE]
```

Every membership test, cache key and dedupe set in this project keys on `ItemKey`, never a bare
id. Functional spec §5.3 is the reason: ids are `str(uuid.uuid4().int)[:12]` from one generator
shared by all model types, so a cross-store collision is unlikely rather than impossible, and
would silently admit one item's result into another's split.

### 3.2 Resolving a split

```python
@dataclass(frozen=True)
class ResolvedSplit:
    name: str
    source: ItemSource
    items: List[TaskRun] | List[EvalInput]

    def item_keys(self) -> Set[ItemKey]: ...
    def __contains__(self, key: ItemKey) -> bool: ...
    def __len__(self) -> int: ...


def resolve_split(task: Task, eval: Eval, split: EvalSplitName) -> ResolvedSplit | None:
    """The items in one of an eval's splits, from whichever store backs it.

    Returns None when the eval has no such split — the caller decides whether
    that is a 422, a zero, or a skip.
    """
```

`resolve_split` is the **only** place that branches on `source`. One `match` over the `SplitRef`
union: `TaskRunSplit` → `dataset_filter_from_id` over `task.runs(readonly=True)`;
`EvalInputSplit` → `eval_input_filter_from_id` over `task.eval_inputs(readonly=True)`.

Returning `None` rather than raising is deliberate: the three callers want three different things
from an absent split (422, `0`, skip), and an exception would force each to catch it.

### 3.3 Identifying what an `EvalRun` scored

```python
def eval_run_item_key(eval_run: EvalRun) -> ItemKey:
    """The item this run scored. EvalRun validates exactly one of dataset_id
    (TaskRun) or eval_input_id (EvalInput) is set."""
```

Membership is then `eval_run_item_key(run) in resolved_split` — source-aware by construction,
with no call site able to get it wrong by comparing raw ids.

### 3.4 Call sites

Every source branch in the project resolves to one of these two functions:

| File | Today | After |
|---|---|---|
| `eval_runner.py` | `_source_mode` + two `collect_tasks_*` paths | `resolve_split` (§4) |
| `eval_api.py` `dataset_ids_in_filter` | TaskRun-only helper | `resolve_split(...).item_keys()` |
| `eval_api.py` `get_eval_progress` | 400s on EvalInput | three `resolve_split` calls |
| `eval_api.py` `get_eval_config_score_summary` | 400s on EvalInput | `resolve_split` |
| `eval_api.py` `get_eval_results_summary` | skips EvalInput evals | `resolve_split`, cached by `(source, filter_id)` |
| `eval_api.py` `get_eval_run_results` | no split filtering | `resolve_split` + `eval_run_item_key` |
| `eval_api.py` `compute_score_summary` | `expected_dataset_ids: set[ID_TYPE]` | `ResolvedSplit` |
| `jobs/workers/eval.py` | `dataset_filter_from_id` over `task.runs()` | `resolve_split` |

`runs_in_filter` stays TaskRun-typed and is used only for the golden set, which is TaskRun-only by
definition. It is not generalized — generalizing it would imply golden can be EvalInput-backed,
which is precisely what this project says it can't.

---

## 4. `EvalRunner`

### 4.1 The two collection paths collapse into one

Today `collect_tasks()` branches on `self._source_mode` and dispatches to
`collect_tasks_for_eval_input()`, which internally re-implements both run types. After this change
there is no eval-level source mode at all — source is a property of the split — and the method
becomes:

```python
def collect_tasks(self) -> List[EvalJob]:
    if self.eval_run_type == "eval_config_eval":
        return self.collect_tasks_for_eval_config_eval()   # golden, always TaskRun
    return self.collect_tasks_for_task_run_eval()          # the resolved split, either source
```

`collect_tasks_for_task_run_eval` iterates `self.split.items` and dedupes on
`(eval_config_id, run_config_id, ItemKey)`. It does not know or care which store the items came
from; `run_job` already handles both item types via `isinstance`.

**`collect_tasks_for_eval_input` is deleted.** This is the structural answer to functional spec
§4.2: a split override cannot be silently ignored because there is no second collection path left
to forget to apply it to.

### 4.2 The runner takes a resolved split, not a filter id

```python
def __init__(
    self,
    eval_configs: List[EvalConfig],
    run_configs: List[TaskRunConfig] | None,
    eval_run_type: Literal["eval_config_eval", "task_run_eval"],
    split: ResolvedSplit | None = None,   # required for task_run_eval
    save_context: SaveContext | None = None,
):
```

`#1621`'s `eval_set_filter_id_override: DatasetFilterId | None` is replaced. Passing an
already-resolved split means the runner has no filter to re-resolve and no default to fall back
to: `task_run_eval` with `split=None` raises `ValueError`, and `eval_config_eval` with a `split`
raises `ValueError` (it scopes by the golden filter). The item set is the parameter, so "accepted
then dropped" is not expressible.

### 4.3 Judge evaluation over EvalInput becomes unexpressible

Functional spec §6.2 requires that judge evaluation over `EvalInput` items fail loudly and write
nothing. Under this design it cannot be requested at all: `eval_config_eval` scopes by
`eval_configs_filter_id`, which is `DatasetFilterId`-typed, so its items are always `TaskRun`s.

The code on evals_v2 that manufactures a skipped `EvalRun` per `EvalInput` item
(`skipped_reason=incompatible_input_shape`, "eval_config_eval over EvalInput is deferred") is
**deleted along with `collect_tasks_for_eval_input`**. It is not replaced with a refusal, because
there is no longer a path that reaches it.

The remaining honest failure is unchanged from today: `eval_config_eval` with no
`eval_configs_filter_id` raises, surfacing as a 4xx. This satisfies §6.2 more completely than a
guard would — nothing to refuse, and no junk records to clean up.

---

## 5. Job worker and jobs API

### 5.1 `jobs/workers/eval.py`

`EvalJobParams.split: EvalSplitName | None` is kept from #1621. `_dataset_filter_id` and
`_split_override` are replaced by a single resolution:

```python
def _resolve_split(self, eval: Eval, task: Task, params: EvalJobParams) -> ResolvedSplit:
    split = resolve_split(task, eval, params.split or "test")
    if split is None:
        raise ...  # 422-mapping error; see §7
    return split
```

One call, used for **both** the runner's item source and the progress universe — which is what
fixes functional spec §4.3. The current code builds progress from `task.runs(readonly=True)`
filtered by a `DatasetFilterId`; that is empty for an EvalInput-backed split and would report a
zero total and let a resume short-circuit. `len(resolved_split)` is correct for either backing by
construction.

The `eval.eval_set_filter_id` fallback — non-optional on #1621, `| None` on evals_v2, a type error
after the merge — is gone: there is no fallback, only the resolved split.

### 5.2 `jobs/api.py`

Pre-resolution before job creation stays, so a bad split is a 422 at request time rather than a
doomed background job. It resolves through `resolve_split` (off the event loop via
`asyncio.to_thread`, as today, since entity loads are blocking IO) and must hold for both
backings.

---

## 6. API layer (`eval_api.py`)

### 6.1 `get_eval_run_results`

`split: EvalSplitName` becomes a **required** query parameter (functional spec §5). Resolve, then
filter:

```python
split_items = resolve_split(task, eval, split)
if split_items is None:
    raise HTTPException(422, ...)
results = [r for r in results if eval_run_item_key(r) in split_items]
```

`split_filter_id_from_eval` (#1621) is deleted — it returned a `DatasetFilterId` and assumed test
always resolves, both of which are now wrong.

The one caller — `.../[run_config_id]/run_result/+page.svelte` — passes `"test"`. Regenerating the
OpenAPI client types the parameter as required, so a missed caller is a build failure rather than
a runtime 422.

### 6.2 `get_eval_progress`

`EvalProgress` gains `val_dataset_size: int`. All three split sizes come from `resolve_split`,
with `None → 0`:

```python
dataset_size=len(test_split),          # test; resolve_split never returns None for test
train_dataset_size=_size(train_split), # 0 when absent
val_dataset_size=_size(val_split),     # 0 when absent
```

The `if eval.eval_set_filter_id is None: raise HTTPException(400, ...)` guard is **deleted**, per
functional spec §6.1 — it exists only because the code could count `TaskRun`s and nothing else.
Golden counts continue to come from `runs_in_filter(eval.eval_configs_filter_id)` and are zero
when golden is unset, which is the expected V2 state and not an error.

### 6.3 `get_eval_config_score_summary` and `get_eval_results_summary`

Same treatment: the `eval_set_filter_id is None` 400 in the former and the silent `continue` in
the latter are both replaced by `resolve_split(task, eval, "test")`.

`compute_score_summary` takes a `ResolvedSplit` instead of `expected_dataset_ids: set[ID_TYPE]`,
and its internal `remaining_expected_dataset_ids` bookkeeping keys on `ItemKey`.

`get_eval_results_summary`'s per-eval cache keys on `(source, filter_id)` rather than `filter_id`,
because the `tag::` grammar is shared across stores and the filter id alone does not identify
which one it addresses (functional spec §5.3).

`get_eval_config_score_summary`'s existing "No dataset ids in eval set filter" 400 on an empty test
split is retained as-is — it is about emptiness, not about backing.

### 6.4 Prompt optimization

`prompt_optimization_job_api.py` currently reports `has_train_set=bool(eval.train_set_filter_id)`
in four places. It becomes a helper:

```python
def has_task_run_train_split(eval: Eval) -> bool:
    return isinstance(eval.splits.get("train"), TaskRunSplit)
```

Starting a job against an eval whose train split is EvalInput-backed raises a 4xx naming the
reason. The remote service resolves the train filter against the project zip's `runs/` directory,
which never contains `eval_inputs/`; teaching it EvalInput is a different repo's project.

Note this now reports `False` for legacy evals that previously got an auto-minted train filter —
intended, per functional spec §3.2.

---

## 7. Errors

`resolve_split` returning `None` is not an error at the datamodel layer; each caller maps it:

| Caller | `None` means |
|---|---|
| `jobs/api.py` pre-check | 422, naming the split and the eval |
| `jobs/workers/eval.py` | job-creation error (unreachable — the pre-check fires first) |
| `get_eval_run_results` | 422 |
| `get_eval_progress` | `0` for that split's size |
| `get_eval_config_score_summary` | 422 (test is required, so this is a corrupt-file case) |

Messages name the split as the caller spelled it (`train`, `val`, `test`) and the eval id. The
#1621 message *"no test_set_filter_id"* — naming a field that has never existed — is removed with
`split_filter_id_from_eval`.

Datamodel-layer failures (`ValidationError` from a malformed `SplitRef`, missing test split) map
to 422 at the API boundary via the existing handling.

---

## 8. Creation paths

`spec_utils.generate_spec_eval_tags` / `generate_spec_eval_filter_ids` were widened to 4-tuples by
#1621 (adding val). That widening is kept, but the callers (`spec_api.py`, `copilot_api.py`)
construct `splits` entries rather than assigning four flat fields. Returning a
`dict[str, SplitRef]` from a single helper is preferable to a growing tuple — a 4-tuple of strings
whose positions must be memorized is exactly the shape this project is replacing elsewhere.

Spec eval creation gains a TaskRun-backed val split, per functional spec §3.3.

The two lazy migrations — `migrate_train_set_filter_id` and #1621's `migrate_val_set_filter_id` —
are **deleted**, per functional spec §3.2.

---

## 9. Testing strategy

Python: `pytest`, alongside the existing `test_eval_model.py`, `test_eval_runner.py`,
`test_eval_api.py`, `jobs/test_api.py`. Web: `npm run test_run` for the one page change.

### 9.1 Datamodel round-trip — the highest-risk area

- An eval with only legacy fields loads with a populated `splits`; `splits["test"]` and
  `splits["train"]` are `TaskRunSplit`s with the legacy filter ids.
- **Byte-identical round-trip**: load an existing-format eval file, save it, and assert the
  serialized output is unchanged — no `splits` key added, no fields dropped or invented. This is
  the single most important test in the project (functional spec §8.3).
- An eval with an EvalInput-backed val split round-trips through the dict, and its
  `val_set_filter_id`-shaped legacy field is absent.
- Changing `splits["test"]` from `TaskRunSplit` to `EvalInputSplit` clears `eval_set_filter_id` on
  save and vice versa.
- The `eval_input_filter_id` shim maps an old-format file to `splits["test"]` as an
  `EvalInputSplit`, and the key is not re-serialized.
- Legacy-wins precedence when a hand-edited file has both.
- An unknown split key (`"holdout"`) loads without error and survives a round trip.
- `EvalInputSplit(filter_id="multi_filter::a&b")` and `high_rating` raise `ValidationError`;
  `TaskRunSplit` accepts them.
- Missing test split raises.
- A freshly constructed `Eval` (not loaded from file) has a populated `splits` (§2.7).

### 9.2 Accessor

- `resolve_split` over each backing returns items from the correct store, and an empty
  `ResolvedSplit` — not `None` — for a configured-but-matching-nothing filter.
- `None` for an absent split.
- `eval_run_item_key` returns the right `(source, id)` for both `EvalRun` shapes.
- **Cross-store id collision**: construct a `TaskRun` and an `EvalInput` with the *same* id, put
  the EvalInput in an EvalInput-backed split, and assert an `EvalRun` keyed on the TaskRun is not
  a member. This is the test that would fail if anything reverts to comparing bare ids.

### 9.3 Runner

- `task_run_eval` over an EvalInput-backed split produces jobs for exactly the matching
  `EvalInput`s — asserted on **which items**, not on a success status. Functional spec's
  verification note is explicit that a silently-full run returns 200, so status assertions cannot
  catch it.
- The same for a TaskRun-backed non-test split.
- Dedupe: an existing `EvalRun` for an item excludes it from a re-run, per backing.
- Overlapping splits reuse already-scored items (item-grained cache still holds with two stores).
- `task_run_eval` with `split=None` raises; `eval_config_eval` with a split raises.
- `eval_config_eval` collects only `TaskRun`s, and **writes no skipped `EvalRun`s** for an eval
  whose test split is EvalInput-backed (§4.3).

### 9.4 Job worker and jobs API

- Progress totals match the requested split's size, per backing — the §5.1 regression test.
- A resume against a partially-run split does not short-circuit against the wrong universe.
- A bad split 422s at job creation, both backings.

### 9.5 API

- `get_eval_run_results` without `split` → 422.
- With each split, per backing, returns exactly that split's runs; a run from the other store is
  never included.
- `get_eval_progress` returns real sizes for an EvalInput-backed eval, `0` for absent train/val,
  and zeroed golden counts without erroring.
- `get_eval_config_score_summary` and `get_eval_results_summary` produce real numbers for an
  EvalInput-backed eval.
- The results-summary cache does not collide two evals sharing a filter id across stores.
- Prompt optimization reports no train set for an EvalInput-backed train split and 4xx on start.

### 9.6 Regression: the no-split path

The run API with `split` omitted runs the same items and reports the same totals as before this
change, for a TaskRun-backed eval. Functional spec §8.1.

---

## 10. Sequencing

The merge (`scosman/evals_v2` into this branch) lands before any of this. Conflicts are expected
in `eval.py`, `eval_runner.py`, `eval_api.py` and `spec_utils.py` from two directions — #1621 is
already dirty against `main` independently of evals_v2.

Resolve conflicts toward **evals_v2's** shape where the two disagree, since #1621's split code is
being substantially rewritten here anyway: `eval_set_filter_id: DatasetFilterId | None`, the
`EvalInput` model, and the V2 judge types are all keepers, while `filter_id_for_split`,
`split_filter_id_from_eval`, `val_set_filter_id` and `eval_set_filter_id_override` are all deleted
by this design.

---

## 11. Open risks

1. **Serialization hook placement** (§2.5). If the projection doesn't run on every save path, an
   eval saved through a path that misses it loses its legacy fields — silently, and only for
   users on older builds. The byte-identical round-trip test is the guard; the hook must be
   verified against `basemodel.py` rather than assumed.
2. **Validator ordering.** §2.4 must run before §2.8, and neither may run inside the child-loading
   recursion that `_currently_migrating_eval_ids` guards.
3. **Old builds dropping the dict** (§2.9). Accepted, bounded, documented.
4. **`compute_score_summary` signature change** ripples into the compare page's data path; the
   change is mechanical but touches more call sites than the other endpoint edits.
