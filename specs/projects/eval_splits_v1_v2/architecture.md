---
status: complete
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

### 2.4 Legacy fields stay declared; nothing reads them

`eval_set_filter_id` and `train_set_filter_id` remain **real, stored, optional fields** on `Eval`.
They are not deleted, and they are not turned into computed properties over `splits`.

Kiln project files sync between clients running different app versions. Removing a field from the
datamodel is a breaking change for every older client that still expects it — the field vanishing
from the file is not something an old build can recover from. So the fields stay.

What changes is that **no application code reads them**. Every reader moves to `splits`
(§3, §4, §6). Keeping accessors under the old names would just preserve the old vocabulary inside
new code, which is the thing this project is trying to get rid of: `eval_set_filter_id` means
"test" and says "eval set", and no new code should have to know that.

So the fields become **storage-format artifacts, not state**. They exist so the bytes on disk stay
readable by older clients. Their in-memory values are not authoritative and are not read; `splits`
is the model's read surface, and §2.6 derives what gets written from it.

### 2.5 Loading: legacy fields fold into `splits`

A `mode="after"` validator folds the two declared legacy fields into the dict and records that
they came from there:

```python
_legacy_homed_splits: Set[str] | None = PrivateAttr(default=None)

@model_validator(mode="after")
def fold_legacy_filter_fields(self) -> Self:
    if self._legacy_homed_splits is not None:
        return self          # already folded; see "runs once" below
    homed: Set[str] = set()
    if self.eval_set_filter_id is not None:
        self.splits["test"] = TaskRunSplit(filter_id=self.eval_set_filter_id)
        homed.add("test")
    if self.train_set_filter_id is not None:
        self.splits["train"] = TaskRunSplit(filter_id=self.train_set_filter_id)
        homed.add("train")
    self._legacy_homed_splits = homed
    return self
```

**The fold runs once — on the first validation, and never again.** `KilnBaseModel` sets
`validate_assignment=True`, so every attribute assignment re-runs the `mode="after"` validators.
Without the early return above, each pass would re-derive `splits` from the legacy fields, which
means a split the caller had written is silently reverted by the next assignment — including
`self.path = path` at the end of `save_to_file`, so the change would also be undone on disk at the
following save. The early return is what makes §2.4's "their in-memory values are not
authoritative" true rather than aspirational: the legacy fields are read exactly once, when the
eval is first materialized.

**Precedence: a populated legacy field wins over a `splits` entry for the same split.** At most one
of the two is ever written for a given split (§2.6), so a conflict means a hand-edited file.
Preferring the legacy field keeps every Kiln client — old and new — agreeing on what the eval's
test and train splits are, which is the property worth protecting. The losing `splits` entry is
dropped from the file on the next save.

The third legacy input, `eval_input_filter_id`, is handled differently — see §2.6.1. Because a
single split cannot have two backings, an input carrying **both** `eval_set_filter_id` and
`eval_input_filter_id` is rejected rather than folded: this is the one conflict the `splits` shape
cannot make unrepresentable, since it is between two *inputs*, not two states of the model. It is
the surviving half of `validate_filter_fields` (§2.8), and it retires with the shim.

### 2.6 Saving: the format an eval arrived in is the format it leaves in

Serialization is provenance-preserving, per split:

- A split that **arrived in a legacy field** is written back to that legacy field, and omitted
  from the serialized `splits` dict.
- A split that **arrived in `splits`** is written to `splits`, and its legacy field is written as
  null.
- A split **created through `Eval.set_split()`** is written to its legacy field when one can hold
  it — TaskRun-backed, and named in `LEGACY_SPLIT_FIELDS` — and to `splits` otherwise. See
  "creating a split" below.

An untouched existing eval therefore round-trips **byte-identically**: no `splits` key appears, and
old clients keep reading it exactly as they do now. A brand-new eval created purely through
`splits` writes only `splits`. An existing eval that gains a val split keeps its legacy test and
train fields and gains a `splits` key containing only val.

#### Creating a split: `Eval.set_split()`

**Amended during phase 2** — the original rule said flatly that a newly created split is written to
`splits`, and that turned out to be wrong for splits created *on behalf of a user*.

```python
def set_split(self, name: str, split: SplitRef) -> None: ...
```

`eval.splits[name] = ref` and `eval.set_split(name, ref)` set the same value and differ only in
where it is stored. The first authors in the new format. The second stores it where the most
readers can see it: `_legacy_homed_splits` gains the name when the ref is TaskRun-backed and the
name has a legacy field, so the split serializes to `eval_set_filter_id` / `train_set_filter_id`
and everything that reads those keeps working.

The reason the distinction has to exist is that the legacy fields are read by more than old Kiln
builds. `package_project_for_training` copies `eval.kiln` verbatim into the zip handed to the
closed-source remote prompt-optimization service, which resolves the train filter out of
`train_set_filter_id` (functional spec §6.3). That reader is in another repo and is not migrating
to `splits` in this project or any phase of it, so a train split written only to `splits` is
invisible to it permanently — not until a later phase, but for good. §6.4's local `has_train_set`
change does not touch it.

Which one a call site wants follows from whose split it is:

| Call site | Which | Why |
|---|---|---|
| Eval-update endpoint's train split (§2.6.2) | `set_split` | Exists so prompt optimization can use it; the zip reader needs the legacy field. |
| Spec / copilot eval creation (§8) | `set_split` | Decided in phase 3: test and train are legacy-homed so the zip reader and older builds still see them; val stays in `splits`. See §8 and `phase_plans/phase_3.md`. |
| A val split, or any EvalInput-backed split | either — same result | No legacy field can hold it, so both write `splits`. |
| Tests and tooling authoring the new format | direct assignment | The point is to exercise the new format. |

Precisely what this does to the provenance rule: **construction** with `splits=` never acquires
legacy fields, and that is still true. `set_split` is the one way an eval **can** acquire a legacy
field after the fact, and that is its whole purpose — an eval constructed
`splits={"test": TaskRunSplit(...)}` and then given `set_split("train", TaskRunSplit(...))`
serializes with `eval_set_filter_id: null` and a populated `train_set_filter_id`. Mixed, and
correct: each split is stored where it was asked to be. Phase 3 is explicitly asked to consider
exactly this shape for new spec evals, so it is not a corner case.

**Picking the wrong one of the two fails silently, in both directions.** This is the second sharp
edge in the design (§2.6.2 has the first), and the table above is only a useful decision aid to
someone who knows what misreading it costs:

- Direct assignment where `set_split` was needed: the split is invisible to the prompt-optimization
  zip reader, to four `eval_api.py` readers and to nine web-UI readers. No error, and
  `eval.splits[name]` reads back exactly what was written.
- `set_split` where new-format authoring was intended: the split lands in a legacy field, and a
  test asserting on `eval.splits` still passes, because both forms produce the same in-memory
  model. Only the serialized bytes differ.

Neither shows up in the model's read surface, which is the point of the read surface — so the only
thing that catches a wrong pick is a test that asserts on **serialized output**. Tests for code
that sets a split should assert on `model_dump()` or the saved file, not on `eval.splits`.

This is implemented as a wrap-mode `model_serializer` rather than a hook on `save_to_file`:

```python
@model_serializer(mode="wrap")
def serialize_preserving_split_format(self, handler): ...
```

The distinction matters. `KilnParentedModel` has more than one persistence path, and a projection
that lives on one save method can be bypassed by another — silently, and only visibly to users on
older clients. A serializer is part of serializing the model, so no persistence path can miss it.

**Unknown provenance degrades to the compatible choice.** When `_legacy_homed_splits` is `None`,
serialization falls back to *content*-determined behavior: any TaskRun-backed test or train split
is written to its legacy field. The fragile case degrades to **more** old-client compatibility,
never to a silent format flip. This is the one place the provenance rule is deliberately not
honored, because honoring it would mean guessing.

Provenance turns out to be **harder to lose than an earlier draft of this section assumed**, which
is why the fallback is a safety net rather than a common path. Pydantic copies private attributes,
so `model_copy()`, `model_copy(deep=True)`, `copy.deepcopy` and `pickle` all carry it. And
`Eval(**eval.model_dump())` re-derives it correctly: the dump of a legacy eval has no `splits` key,
so the fold re-runs over the legacy fields exactly as a file load would. The fallback is reached
only by `model_construct`, which skips validation and therefore never records provenance in the
first place.

**Backing changes force a format change.** If a legacy-homed test split is changed from
TaskRun-backed to EvalInput-backed, its legacy field cannot hold the new value. It is written as
null and the split moves into `splits`. Old clients lose that eval's test split. This is
unavoidable — the legacy field has no representation for an EvalInput filter — and it is the
correct failure: the eval genuinely now points at data an old client cannot resolve.

### 2.6.1 The `eval_input_filter_id` shim

`eval_input_filter_id` is the exception to §2.4 and is **not** kept as a declared field. It is read
out of the raw input by a `mode="before"` validator, folded into `splits["test"]` as an
`EvalInputSplit`, and dropped:

```python
@model_validator(mode="before")
@classmethod
def migrate_eval_input_filter_id(cls, data: Any) -> Any:
    # TODO: Remove before shipping. Only internal projects contain this key;
    # no public project file has ever had it.
    ...
```

The compatibility argument in §2.4 does not apply to it: no public project file has ever contained
the key, so there is no older client with real data to protect. Keeping it as a declared field
would put it in the schema and the generated web client for the sake of internal projects that
will all have been migrated before ship. As a before-validator it never enters the API surface,
and removing it later is deleting one validator.

This is the resolution of functional spec §3.4: the field disappears rather than being renamed to
`test_eval_input_filter_id`, and the principle it was named for — the split is the key, the source
is a property of its value — is expressed structurally by `splits` instead.

### 2.6.2 What this costs at call sites

The legacy fields remain constructible and assignable, so nothing breaks mechanically. But since
their in-memory values are not authoritative, writing to them no longer changes the eval:

- **Construction.** `spec_api.py` and `copilot_api.py` construct `splits=` rather than passing
  legacy kwargs — which §8 already requires of them for the val split.
- **Assignment.** One non-test site: the eval-update endpoint's
  `eval.train_set_filter_id = request.train_set_filter_id`. It calls
  `eval.set_split("train", TaskRunSplit(...))` instead — `set_split` rather than a direct `splits`
  write, because that split is created for prompt optimization, which reads it out of the packaged
  project file (§2.6, "creating a split").

This is one of the two sharp edges in the design: assigning a legacy field silently does nothing
rather than failing. (The other is choosing between `set_split` and direct assignment, which is
also silent — see §2.6.) Mitigations, in order of importance — (1) the fields' descriptions state
that `splits` is authoritative, (2) §9.1 covers the update endpoint explicitly, (3) a grep for
reads and writes of both names is part of the phase's definition of done. If a stronger guarantee
is wanted later, the fields can be renamed with a leading underscore alias or made `init=False`, at
the cost of touching every construction site.

Both edges share a shape: the wrong choice is invisible in `eval.splits` and visible only in the
serialized bytes. Tests over code that writes a split need to assert on the dump or the file.

### 2.7 Why the fold is not gated on `_loaded_from_file`

The existing lazy migration (`Eval.upgrade_old_reference_answer_eval_config`) gates on
`self._loaded_from_file`, because it *invents* data and should only do so for files. The §2.5
fold invents nothing — it relocates values that are already set.
Gating it on file loads would mean `Eval(eval_set_filter_id="tag::x")` has an empty `splits` while
the same eval loaded from disk has a test split, which is exactly the split-brain this design
exists to eliminate.

It runs on every construction path, so a caller may pass either the legacy fields or `splits` and
get the same model. Note the provenance consequence: an eval *constructed* with legacy kwargs is
recorded as legacy-homed and will serialize that way, which is the same answer content-determined
fallback would give.

There is a second reason the gate would not have worked, found while building §2.5's run-once rule:
the **private attribute** `_loaded_from_file` is set by the loader **after** `model_validate`
returns, so a validator reading it directly can only fire on a *later* validation pass — in
practice the `self.path = path` assignment at the end of `load_from_file`, via
`validate_assignment`. A run-once validator gets no second pass, so `self._loaded_from_file` inside
the fold would be permanently false rather than merely wrong.

**That is a fact about the raw attribute, not about detecting a file load.** Corrected during phase
3, because an earlier wording of this paragraph ("that is how the existing lazy migrations fire at
all") could be read as *no* run-once validator can ever tell it is loading a file, which is false.
`upgrade_old_reference_answer_eval_config` is the only validator in this repo that reads
`self._loaded_from_file` directly, and so the only one that depends on the second pass. The working
idiom is `self.loaded_from_file(info)` (`basemodel.py`), which checks the
`{"loading_from_file": True}` context that `load_from_file` passes to `model_validate` *before*
falling back to the private attribute — so it is true on the **first** validation pass, during the
load itself. `task_run.py:226` (`validate_input_source`) and `task_output.py:377`
(`validate_output_source`) use it that way; both are strict-mode relaxations rather than
data-inventing migrations, which is why they are not covered by the paragraph above. A run-once
validator **can** therefore detect a file load in this repo — it just cannot do so via the raw
private attribute.

This does not change §2.7's conclusion: the fold is ungated because it invents nothing and must
behave identically for a loaded and a constructed eval, not because a working gate was
unavailable.

### 2.8 Validation

Replaces `validate_filter_fields`:

```python
@model_validator(mode="after")
def validate_splits(self) -> Self:
    if "test" not in self.splits:
        raise ValueError("An eval must have a test split ...")
    return self
```

The old "exactly one of `eval_set_filter_id` / `eval_input_filter_id`" invariant **disappears from
the model rather than being reimplemented**: `splits["test"]` is a single value, so two backings
for one split is not a state the model can be in. That is functional spec §1's "exactly one backing
per split" made structural.

What that argument does not cover is the *input* side, where two legacy keys can still name the
same split. An input carrying both is rejected in the `eval_input_filter_id` shim (§2.5, §2.6.1) —
the alternative is folding both and silently discarding one. That check is the only surviving piece
of `validate_filter_fields`, it lives with the shim, and it retires with it.

Both this and §2.5's fold are `mode="after"` validators, so **declaration order matters**: the
fold must be declared first. This is the one ordering convention in the design that isn't enforced
by pydantic, and §9.1 covers it with a test that an eval carrying only legacy fields validates
rather than raising "must have a test split".

Neither loads children, so neither needs the `_currently_migrating_eval_ids` recursion guard — but
neither may be moved anywhere that does.

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
    eval_id: ID_TYPE          # added in phase 4; see below

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

**`eval_id` was added in phase 4**, when the runner started taking a `ResolvedSplit` instead of
deriving its items from the eval. Once a split is a value passed between layers, nothing else ties
those items to the eval whose judges are about to score them — `EvalRunner(eval_configs=[a_config],
split=resolve_split(task, other_eval, "test"))` was accepted in silence. Consumers compare it
against the eval they are working on; §4.2's standard is "impossible by construction", and without
it that had become convention. It identifies the split's origin only, so it is not part of item
identity: `ItemKey` and the membership tests are unchanged.

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

#### What exists today

`eval_config_eval` is judge calibration: it scores a *judge* by re-using a dataset item's stored
output and correlating the judge's score against a human rating. Its item scope is
`eval_configs_filter_id` — the golden set.

On evals_v2 the runner dispatches on an **eval-level** source mode:

```python
def collect_tasks(self):
    if self._source_mode == "eval_input":       # set from eval.eval_input_filter_id
        return self.collect_tasks_for_eval_input()
    elif self.eval_run_type == "eval_config_eval":
        ...
```

The source-mode check comes first, so an EvalInput-backed eval routes **every** run type through
`collect_tasks_for_eval_input()` — including calibration, which has nothing to do with the eval's
test-set backing. Calibration then collects `EvalInput` items as `eval_config_eval` jobs.

`EvalInput` has no stored output and no rating storage, so there is nothing for those jobs to
score. `run_job` handles that by writing a persisted, deliberately-empty record per item:

```python
if isinstance(job.item, EvalInput):
    if job.type == "eval_config_eval":
        eval_run = EvalRun(
            ..., eval_input_id=job.item.id, dataset_id=None,
            eval_config_eval=True, scores={}, output=None,
            skipped_reason=SkippedReason.incompatible_input_shape.value,
            skipped_detail="EvalInput source has no stored output; eval_config_eval "
                           "over EvalInput is deferred in V2.0 ...",
        )
        eval_run.save_to_file()
    return True
```

The net effect of running calibration on an EvalInput-backed eval today: a **successful** run
(200, no error) that scored nothing and left one junk record per item on disk.

#### What we delete, and why

Both halves: `collect_tasks_for_eval_input()` and the `EvalInput`/`eval_config_eval` branch of
`run_job`.

The reason is that they only exist to paper over the mis-routing. The skipped-record writing is
not a feature — it is the handler for jobs that should never have been collected. Once source is
a property of a split rather than of the eval (§2), there is no eval-level source mode, and
`collect_tasks` becomes:

- `eval_config_eval` → scoped by `eval_configs_filter_id`, which is `DatasetFilterId`-typed, so
  its items are **always** `TaskRun`s.
- `task_run_eval` → the resolved split, either backing.

Calibration can no longer reach an `EvalInput`, so the branch that handled reaching one has
nothing left to handle. Deleting it is removing dead code, not removing behavior.

#### Why not a guard instead

Functional spec §6.2 asked for a loud refusal. A guard would be new code checking for a state and
raising — something to maintain, and something a later edit could route around. Making the state
unreachable is strictly stronger: there is no combination of inputs that expresses "calibrate a
judge over EvalInput items", so there is nothing to refuse.

The honest failure that remains is the pre-existing one: `eval_config_eval` with no
`eval_configs_filter_id` raises, surfacing as a 4xx. An EvalInput-backed eval that never had a
golden set gets exactly that — "no golden set configured" — which is accurate, and better than
today's fake-success.

#### Records already written

Deleting the code does not delete records it already wrote. Any that exist are `EvalRun`s with
`eval_config_eval=True`, `eval_input_id` set, `dataset_id=None`, `scores={}`, `output=None`,
`task_run_config_id=None`, and `skipped_reason=incompatible_input_shape`.

They are inert under every reader, checked rather than assumed:

- **Judge comparison** looks items up with `expected_dataset_items.get(eval_run.dataset_id)`.
  `dataset_id` is `None`, so the lookup misses and the run is skipped by the existing
  already-handled "removed from the filter" branch.
- **Run-config summaries** filter on `task_run_config_id == run_config_id`. These carry `None`, so
  they never match a run config.
- **Calibration dedupe** builds a set of `run.dataset_id`, adding `None`. Harmless: no `TaskRun`
  has a `None` id.

So no cleanup or data migration is specified. The residual cost is cosmetic — they inflate
`eval_config.runs()` counts and would appear in any UI that lists calibration runs raw. If that
proves visible, deleting them is a one-off script, not a schema concern.

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
#1621 (adding val). `generate_spec_eval_tags` keeps its four values — those are dataset tags the
copilot passes to `create_dataset_task_runs`, and golden is one of them — but
`generate_spec_eval_filter_ids` is **deleted** in phase 3, replaced by a `spec_eval_splits` helper
returning `dict[EvalSplitName, SplitRef]`. A 4-tuple of strings whose positions must be memorized
is exactly the shape this project is replacing elsewhere.

Spec eval creation gains a TaskRun-backed val split, per functional spec §3.3.

Both callers must construct `splits=` rather than passing legacy kwargs, since §2.4 makes those
computed and therefore not `__init__` arguments.

**Decided in phase 3: a new spec eval's TaskRun-backed test and train splits ARE moved into their
legacy homes with `set_split`; its val split has no legacy field and stays in `splits`.** So a new
spec eval is §2.6's mixed shape — legacy test and train fields plus a `splits` key holding only
val. The alternative (constructing with `splits=` alone) would have made a brand-new spec eval's
**test** split invisible to `package_project_for_training`'s zip reader, which is in another repo
and never migrates — permanently, not until a later phase. Full reasoning, and what the decision
does and does not guarantee, in `phase_plans/phase_3.md`.

Note the guarantee's exact scope: `set_split` records where a split will be *written*, so the
in-memory instance the creation path holds still has `eval_set_filter_id is None`. Every reader
that **loads the eval from disk** sees both legacy fields; an `Eval` handed to a later phase
in-process and unsaved does not. Phases 5 and 6 must not read the broader claim into this.

Phase 3 also collapsed both creation paths into one `spec_utils.build_spec_eval` factory, so
construction and the `set_split` homing cannot be separated by a caller that forgets the second
step.

The eval-update endpoint's one assignment moved to `set_split` in phase 2, ahead of this phase,
because the run-once fold (§2.5) made the old line silently discard its input.

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
  save and vice versa — asserted after **two** saves, and against the in-memory model as well as
  the file, since `save_to_file` is itself an assignment and §12.1's failure mode only shows up on
  the second write. An unrelated edit (a rename) must not revert a split either.
- An input carrying both `eval_set_filter_id` and `eval_input_filter_id` raises (§2.8).
- The `eval_input_filter_id` shim maps an old-format file to `splits["test"]` as an
  `EvalInputSplit`, and the key is not re-serialized.
- Legacy-wins precedence when a hand-edited file has both.
- An unknown split key (`"holdout"`) loads without error and survives a round trip.
- `EvalInputSplit(filter_id="multi_filter::a&b")` and `high_rating` raise `ValidationError`;
  `TaskRunSplit` accepts them.
- Missing test split raises. **And**: an eval carrying only legacy fields validates rather than
  raising it — the guard on §2.8's declaration-order dependency.
- A freshly constructed `Eval` (not loaded from file) has a populated `splits` (§2.7).

Provenance (§2.6), which is where the subtle failures live:

- A splits-native eval (no legacy fields in the source) round-trips writing **only** `splits`, with
  both legacy fields null — it does not acquire them.
- An existing legacy-format eval that gains a val split keeps its legacy test and train fields and
  gains a `splits` key containing **only** val.
- `Eval(**eval.model_dump())` on a legacy-format eval still serializes to legacy format (by
  re-deriving provenance), and `model_copy()` likewise (by carrying it).
- The unknown-provenance fallback itself, which only `model_construct` reaches: a TaskRun-backed
  test split goes to `eval_set_filter_id`, and a split whose legacy field is excluded from the dump
  stays in `splits` rather than being written nowhere.
- The eval-update endpoint's train-split write (§2.6.2) is reflected in `splits` **and** in the
  serialized output, in whichever format the eval arrived in.

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

### This branch replaces #1621 rather than extending it

Everything #1621 added to the split surface — `val_set_filter_id`, `filter_id_for_split`,
`split_filter_id_from_eval`, `eval_set_filter_id_override`, the `migrate_val_set_filter_id`
migration — is deleted by this design and replaced by `splits`, `resolve_split` and
`ResolvedSplit`.

Anywhere this branch meets a tree that already carries #1621, expect the diff to read as a large
deletion of code that is already there. That is correct, not lost work. Reviewers should compare
against this document rather than against #1621.

---

## 11. Alternatives considered and rejected

**Legacy fields as `@computed_field` properties over `splits`.** A middle draft. It removed the
sync problem cleanly, but it **deletes the stored fields from the datamodel** — and Kiln project
files sync between clients on different app versions, so a field disappearing from the file is a
breaking change an older client cannot recover from. Rejected: the fields must remain declared and
stored (§2.4). Its good idea is kept — put the format logic in a serializer, not a save hook — and
the safety it bought is preserved by §2.6's `model_serializer`.

**Legacy fields projected by a hook on `save_to_file`.** The first draft. Rejected because
`KilnParentedModel` has more than one persistence path, so a projection attached to one save method
can be bypassed by another, silently, and only visibly to users on older clients.

**Content-determined format instead of provenance-determined.** Always write TaskRun-backed test
and train splits to their legacy fields, regardless of how the eval was loaded. Simpler, no private
attribute, and strictly *more* old-client compatible — but it means a splits-native eval acquires
legacy fields it never had, and there is no way to author an eval in the new format. Rejected in
favour of provenance, with content-determination retained as the fallback when provenance is
unknown (§2.6) so the fragile paths degrade to the safe answer.

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

1. **The fold must never run twice, and `validate_assignment` makes that easy to break.** Every
   attribute assignment on a `KilnBaseModel` re-runs the `mode="after"` validators, so anything
   that re-enables the fold on a second pass — removing §2.5's early return, resetting
   `_legacy_homed_splits`, or adding another validator that derives `splits` from the legacy
   fields — makes writes to `splits` **unstable on exactly the legacy evals this design exists to
   protect**: the edit is reverted by the next assignment, and `save_to_file` ends with
   `self.path = path`, so it is also undone on disk at the following save. The failure is silent
   in the worst way, because the first save writes the correct file.

   Its milder twin is the original form of this risk: assigning a legacy field is a no-op rather
   than an error, so a future author reaching for the familiar name changes nothing. Mitigated by
   field descriptions, a grep in the phase's definition of done, and tests that save twice and
   compare the in-memory model against the file it just wrote (§9.1).
2. **`model_serializer` interaction with `KilnParentedModel`.** The wrap serializer must be
   invoked by whatever dump path `save_to_file` uses, and must compose with the parent/child
   machinery. Standard pydantic behavior, but this datamodel has custom save code, so the
   byte-identical round-trip test (§9.1) is the guard rather than an assumption.
3. **Provenance is a private attribute**, which makes it invisible state, and invisible state is
   where format bugs hide. It is more durable than this document first claimed — copies, deep
   copies and pickles all carry it, and a dict round trip re-derives it (§2.6) — so the
   content-determined fallback is reached only via `model_construct`. The residual risk is not
   losing it but *mis-setting* it: nothing outside the fold may write it.
4. **Old builds dropping the dict** (§2.9). Accepted, bounded, documented.
5. **`compute_score_summary` signature change** ripples into the compare page's data path; the
   change is mechanical but touches more call sites than the other endpoint edits.
6. **Test-file churn.** Many tests set `eval_set_filter_id` / `train_set_filter_id` directly.
   Unlike the computed-field design, these keep *working* — they just stop being authoritative,
   so a test asserting on `splits` would fail while one asserting on the legacy field passes
   vacuously. Test updates here need reading, not just mechanical fixing.
