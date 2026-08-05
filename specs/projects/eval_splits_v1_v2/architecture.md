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

`eval_configs_filter_id` (golden) stays a plain `DatasetFilterId` field and does **not** enter
`splits`. Uniformity would argue for putting it in — it is a named subset selected by a filter —
but its type inside the dict would be `SplitRef`, which admits `EvalInputSplit`. That would make
an EvalInput-backed golden set representable again, handing back the exact guarantee §2.8 wins.
Keeping golden outside the dict is what keeps "golden is TaskRun-only" true at the type level
rather than by convention.

### 2.4 `splits` is the only stored state; legacy fields are derived

The legacy fields stop being stored fields and become **computed fields** over `splits`:

```python
@computed_field
@property
def eval_set_filter_id(self) -> DatasetFilterId | None:
    test = self.splits.get("test")
    return test.filter_id if isinstance(test, TaskRunSplit) else None

@computed_field
@property
def train_set_filter_id(self) -> DatasetFilterId | None:
    train = self.splits.get("train")
    return train.filter_id if isinstance(train, TaskRunSplit) else None
```

`@computed_field` is an established idiom in this datamodel (`basemodel.py:347`,
`extraction.py:304`), and pydantic serializes computed fields on every dump.

This is the important structural choice, and it is a correction to my first draft. Modelling the
legacy fields as *stored state kept in sync with the dict by a save hook* creates two sources of
truth and one hook that must fire on every persistence path — and `KilnParentedModel` has save
paths a naive override misses. That hook failing is silent, and only breaks users on older
builds. Deriving the fields instead **designs the failure mode out**: there is nothing to keep in
sync, no hook to place, and serialization cannot miss them because they are part of the
serialization.

On disk the result is exactly the intended contract:

- A TaskRun-backed test or train split serializes into its legacy field. **Byte-identical to
  today** — an eval nobody has changed writes exactly as it does now, with no `splits` key added.
- An EvalInput-backed test or train split, and every val split, serializes into `splits`.
- Nothing is written twice, so the representations cannot drift — because there is only one.

"Saving doesn't move them" holds: the dict is the API and the in-memory truth, while the bytes on
disk keep their current shape for the splits that already have one. Moving them later is deleting
the computed fields and the parse-time fold below.

### 2.5 Parse: legacy keys fold into the dict

A `mode="before"` validator reads the legacy keys out of the raw input and writes them into
`splits`, so they never need to exist as stored fields:

```python
@model_validator(mode="before")
@classmethod
def fold_legacy_filter_fields(cls, data: Any) -> Any:
    # eval_set_filter_id  -> splits["test"]  (task_run)
    # train_set_filter_id -> splits["train"] (task_run)
    # eval_input_filter_id -> splits["test"] (eval_input)   [TODO: §2.6]
    ...
```

**Precedence: a populated legacy key wins over a `splits` entry for the same split.** At most one
of the two is ever written for a given split (§2.4 emits exactly one), so a conflict means a
hand-edited file. Preferring the legacy key keeps every Kiln build — old and new — agreeing on
what the eval's test and train splits are, which is the property worth protecting.

### 2.5.1 What this costs

Computed fields are not assignable and not `__init__` kwargs, so two kinds of call site change,
both of which fail loudly at type-check or import time rather than silently:

- **Construction.** `spec_api.py` and `copilot_api.py` pass `eval_set_filter_id=` /
  `train_set_filter_id=` to `Eval(...)`. They construct `splits=` instead — which §8 already
  requires of them for the val split.
- **Assignment.** Exactly one non-test site: `eval_api.py:834`,
  `eval.train_set_filter_id = request.train_set_filter_id` in the eval-update endpoint. It writes
  `eval.splits["train"] = TaskRunSplit(...)` instead.

Test files assign these fields in a number of places and will need updating; that is mechanical
and the failures are immediate.

This is a real cost, and it is the right trade: a handful of loud, compile-time call-site edits in
exchange for deleting an entire class of silent persistence bug.

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

### 2.7 Why the fold is not gated on `_loaded_from_file`

The existing migrations gate on `self._loaded_from_file`, because they *invent* data and should
only do so for files. The §2.5 fold invents nothing — it relocates keys that are already present.
Gating it on file loads would mean `Eval(eval_set_filter_id="tag::x")` has an empty `splits` while
the same eval loaded from disk has a test split, which is exactly the split-brain this design
exists to eliminate.

Because it is a `mode="before"` validator it runs on every construction path, so a caller may pass
either the legacy keys or `splits` and get the same model.

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

Ordering is automatic rather than a convention to maintain: §2.5's fold is `mode="before"` and
this is `mode="after"`, so pydantic guarantees the fold has already run. Neither loads children,
so neither needs the `_currently_migrating_eval_ids` recursion guard — but neither may be moved
anywhere that does.

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

Both callers must construct `splits=` rather than passing legacy kwargs, since §2.4 makes those
computed and therefore not `__init__` arguments. The eval-update endpoint's one assignment
(`eval_api.py:834`) moves to `eval.splits["train"] = TaskRunSplit(...)` for the same reason.

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

## 11. Alternatives considered and rejected

**Legacy fields as stored state, synced by a save hook.** My first draft. Rejected in favour of
§2.4's computed fields: it created two sources of truth and a hook that had to fire on every
persistence path, where a miss is silent and only affects users on older builds. It was the
largest risk in the design and it was self-inflicted.

**Self-describing filter ids** — encode the store in the selector (`task_run:tag::x` /
`eval_input:tag::x`), so a split is a plain string and `SplitRef` isn't needed at all. This is
arguably the *more* correct model: it fixes the ambiguity at its root, since `tag::val_x` would
never appear without saying what it selects, and the source-awareness rules in §3.1 would become
unnecessary rather than enforced. Rejected on blast radius: `DatasetFilterId` is used well beyond
evals (dataset splits, finetunes), so a new grammar means migrating every filter id in every
project file, and `EvalInputFilterId`'s narrower grammar would move from a type guarantee to a
parse-time check. Worth revisiting if filter ids are ever reworked for another reason.

**Golden in the `splits` dict.** Uniform, but its value type would be `SplitRef`, which admits
`EvalInputSplit` — reintroducing an EvalInput-backed golden set as a representable state. See
§2.3.

**`splits` as a list of named refs** rather than a dict. Gives ordering, avoids the key-type
question, but makes name-uniqueness a validator and lookup a scan. The dict is better on both.

**A `Literal`-typed dict key.** See §2.2 — it breaks old builds hard on a file containing a future
split name.

---

## 12. Open risks

1. **Validator/serializer interaction with `KilnParentedModel`.** Computed fields must appear in
   whatever dump path `save_to_file` uses, and the `mode="before"` fold must see the raw file
   dict. Both are standard pydantic behavior, but this datamodel has custom save machinery, so
   the byte-identical round-trip test (§9.1) is the guard rather than an assumption.
2. **Old builds dropping the dict** (§2.9). Accepted, bounded, documented.
3. **`compute_score_summary` signature change** ripples into the compare page's data path; the
   change is mechanical but touches more call sites than the other endpoint edits.
4. **Test-file churn.** Many tests assign `eval_set_filter_id` / `train_set_filter_id` directly.
   These break loudly and are mechanical to fix, but the volume is non-trivial and should not be
   mistaken for design trouble mid-implementation.
