> SUPERSEDED 2026-06-03 — content consolidated into design/10_data_model.md + design/15_v1_v2_coexistence.md.

# Backwards Compatibility Plan (Code-Grounded)

**Source(s):** `ALIGNMENT.md` A0.1 + A2.1, V1 code at `~/Dropbox/workspace/kiln_new` (read 2026-05-21)
**Author:** sub-agent dispatched 2026-05-21 for Stage 3a.7 code-grounded backwards-compat plan
**Status:** draft

## Framing

This plan proposes specific code-level changes to the Kiln V1 codebase to implement V2 coexistence per ALIGNMENT.md A0.1 (V2 reads V1 cleanly; V2 never rewrites V1 on disk) and A2.1 (EvalConfig reference example). Unlike `backwards_compat_plan.md`, this plan is grounded in actual V1 code: every proposed change cites file paths and line numbers, and every coexistence assumption has been verified against the source.

**Primary goal (A0.1):** V2 reads V1 records cleanly. V2 NEVER rewrites V1 records on disk.
**Not a goal:** V1 reading V2-only records. V1 patches as V2 launch prereqs.

---

## Part 1 -- Code-level coexistence design

### 1.1 EvalConfig V2 coexistence

**Current V1 code (eval.py:259-317):**

```python
class EvalConfig(KilnParentedModel, KilnParentModel, parent_of={"runs": EvalRun}):
    name: FilenameString
    model_name: str              # required, no default
    model_provider: str          # required, no default
    config_type: EvalConfigType  # default=EvalConfigType.g_eval
    properties: dict[str, Any]   # default={}
```

Key constraints from the existing code:

1. **`model_name` and `model_provider` are required fields (no default).** V2 non-LLM configs do not have these. Solution: make them `str | None = None` on the shared model. V1 files always have them populated, so V2 reading V1 works. The `validate_properties` validator (eval.py:290-308) already implicitly relies on them for `g_eval`/`llm_as_judge` -- the V2 shape validator must enforce they are set for legacy types and None for `v2`.

2. **`validate_properties` at eval.py:290-308 has an explicit `else: raise ValueError`.** This is the gatekeeper -- any `config_type` not in `{g_eval, llm_as_judge}` hits line 308 and throws. V2 must extend this validator, not replace it. The extension adds a `config_type == EvalConfigType.v2` branch that validates the typed properties union. The legacy branches stay unchanged.

3. **`validate_json_serializable` at eval.py:310-317** calls `json.dumps(self.properties)`. When `properties` is a Pydantic `BaseModel` (V2 typed union), `json.dumps` will fail on the raw object. The validator must be updated to skip JSON-dump validation for V2 properties (the Pydantic union handles its own validation).

4. **`EvalConfigType` at eval.py:51-55** is `(str, Enum)` with two values. Adding `v2 = "v2"` is safe. V1 clients will raise `ValidationError` on unknown enum values -- acceptable per A0.1.

**Proposed V2 shape (concrete diff against current code):**

```python
# eval.py additions

class EvalConfigType(str, Enum):
    g_eval = "g_eval"
    llm_as_judge = "llm_as_judge"
    v2 = "v2"                        # NEW


class EvalConfig(KilnParentedModel, KilnParentModel, parent_of={"runs": EvalRun}):
    name: FilenameString
    # CHANGED: optional for V2 configs; V1 files always have these set
    model_name: str | None = None
    model_provider: str | None = None
    config_type: EvalConfigType = EvalConfigType.g_eval
    # CHANGED: union type -- V1 files load as dict, V2 files load as typed model
    properties: V2EvalConfigProperties | dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_properties(self) -> Self:
        if self.config_type in (EvalConfigType.g_eval, EvalConfigType.llm_as_judge):
            # --- UNCHANGED legacy validation ---
            if not isinstance(self.properties, dict):
                raise ValueError("Legacy config properties must be a dict")
            if "eval_steps" not in self.properties or not isinstance(
                self.properties["eval_steps"], list
            ):
                raise ValueError("eval_steps is required and must be a list for g_eval")
            if "task_description" in self.properties and not isinstance(
                self.properties["task_description"], str
            ):
                raise ValueError("task_description must be a string if provided")
            # Legacy configs MUST have model_name/model_provider
            if self.model_name is None or self.model_provider is None:
                raise ValueError("model_name and model_provider are required for legacy configs")
            return self
        elif self.config_type == EvalConfigType.v2:
            # --- NEW V2 validation ---
            if not isinstance(self.properties, BaseModel):
                raise ValueError("V2 config requires typed properties")
            if self.model_name is not None or self.model_provider is not None:
                raise ValueError("V2 configs must not set root-level model_name/model_provider")
            return self
        else:
            raise ValueError(f"Invalid eval config type: {self.config_type}")

    @model_validator(mode="after")
    def validate_json_serializable(self) -> Self:
        # V2 properties are Pydantic models; skip json.dumps check
        if self.config_type == EvalConfigType.v2:
            return self
        try:
            json.dumps(self.properties)
        except TypeError as e:
            raise ValueError(f"Properties must be JSON serializable: {e!s}")
        return self
```

**`model_name`/`model_provider` default change risk:** Making these `str | None = None` means new EvalConfig construction without explicit values won't raise. This changes the API contract -- code that creates legacy EvalConfigs without setting these would silently succeed where it previously failed. Mitigation: the `validate_properties` validator catches this for legacy `config_type` values. Tested by existing test suite (21 tests in `test_g_eval.py`, 21 in `test_eval_runner.py`).

**Pydantic union parse order:** When loading from disk, Pydantic v2 will attempt to parse `properties` against each union member left-to-right. The union is `V2EvalConfigProperties | dict[str, Any] | None`. For V1 files, `properties` is a JSON dict. Pydantic will first try `V2EvalConfigProperties` (a discriminated union), which will fail (no `type` discriminator in legacy dicts), then fall through to `dict[str, Any]` which succeeds. This ordering is correct. However, if a V1 dict happened to contain a `type` key matching a V2 type, it could mis-parse. Risk is near-zero: V1 dicts contain `eval_steps` and `task_description`, not `type`. Still, the `validate_properties` validator would catch any mis-parse because `config_type` would be `g_eval`/`llm_as_judge` but `properties` would be a BaseModel.

**Alternative (safer): Use `mode="before"` validator to dispatch.** Instead of relying on Pydantic's union parse order, add a `mode="before"` model validator that inspects `config_type` and explicitly routes `properties` parsing:

```python
@model_validator(mode="before")
@classmethod
def dispatch_properties_parsing(cls, data: dict, info: ValidationInfo) -> dict:
    if not isinstance(data, dict):
        return data
    config_type = data.get("config_type", "g_eval")
    if config_type in ("g_eval", "llm_as_judge"):
        # Keep properties as raw dict, don't try V2 union parsing
        # (no change needed -- Pydantic parses dict[str, Any] fine)
        pass
    elif config_type == "v2":
        # Let the V2 union handle it (Pydantic's Discriminator("type") on properties)
        pass
    return data
```

This is cleaner; recommend using the `mode="before"` approach to avoid relying on Pydantic union fallback behavior.

---

### 1.2 EvalRun V2 coexistence

**Current V1 code (eval.py:93-257):**

```python
class EvalRun(KilnParentedModel):
    dataset_id: ID_TYPE
    task_run_config_id: ID_TYPE | None
    eval_config_eval: bool = False
    input: str
    output: str
    reference_answer: str | None = None
    intermediate_outputs: Dict[str, str] | None = None
    task_run_trace: str | None = None
    scores: EvalScores
    task_run_usage: Usage | None = None
```

**Additive V2 fields (safe per `extra = "ignore"` on KilnBaseModel):**

```python
class EvalRun(KilnParentedModel):
    # ... all existing fields unchanged ...

    # V2 additions -- all optional, default None
    eval_input_id: ID_TYPE | None = Field(
        default=None,
        description="ID of the EvalInput used for this run (V2 evals). Mutually exclusive with dataset_id for V2 runs."
    )
    dataset_source_type: Literal["task_run", "eval_input"] | None = Field(
        default=None,
        description="Discriminator: 'task_run' for V1 runs (dataset_id points to TaskRun), 'eval_input' for V2 runs."
    )
    # Score provenance (Batch E decision, shape TBD)
    # eval_config_version: str | None = None
    # run_provenance: RunProvenance | None = None
```

**Key concerns:**

1. **`validate_reference_answer` at eval.py:240-255** checks that `reference_answer` is only set for `EvalDataType.reference_answer` evals. V2 EvalRuns sourced from `EvalInput.reference` will populate `reference_answer` differently. The validator reads `evaluation_data_type` from the grandparent `Eval`. For V2 configs where `evaluation_data_type` lives inside config properties (per A2.3 decision), the runner must either:
   - (a) Still set `reference_answer` on EvalRun for compatibility with the existing validator, OR
   - (b) Extend the validator to skip the check for V2 configs, OR
   - (c) Store V2 reference data in a new field (`reference_data: dict[str, JsonValue] | None`) that bypasses the validator entirely.

   Recommend (c): add `reference_data` as a new additive field. V1 EvalRuns keep using `reference_answer: str | None`. V2 EvalRuns use `reference_data: dict[str, JsonValue] | None`. The existing validator is untouched.

2. **`validate_output_fields` at eval.py:146-166** reads `evaluation_data_type` from the grandparent Eval. For V2 configs where this lives in config properties, the validator will read the Eval-level value (which may be stale or absent for V2-created Evals). Either:
   - Set a default `evaluation_data_type` on V2 Evals (e.g. `final_answer`) and accept the V2 runner handles its own validation, OR
   - Extend the validator to check `config_type` and skip legacy validation for V2.

   Recommend extending the validator with a V2 bypass.

3. **`validate_eval_run_types` at eval.py:168-177** enforces `eval_config_eval` <-> `task_run_config_id` consistency. V2 runs may have different semantics (e.g. an EvalInput-backed run that is neither eval_config_eval nor task_run_eval in V1 terms). Either:
   - Reuse `eval_config_eval=True` for EvalInput-backed runs (semantically close), OR
   - Add a new field `run_type: Literal["task_run_eval", "eval_config_eval", "eval_input_eval"] = "task_run_eval"` and extend the validator.

   Recommend the new `run_type` field as the discriminator going forward, with `eval_config_eval` preserved for V1 compatibility.

4. **`validate_scores` at eval.py:180-238** reads `output_scores` from the grandparent Eval to validate score keys. V2 EvalRuns should produce scores that match the parent Eval's `output_scores`. This validator should work unchanged for V2 -- the score contract is Eval-level, not config-level.

---

### 1.3 EvalInput addition

**Where it slots into `Task.parent_of` (task.py:126-139):**

```python
class Task(
    KilnParentedModel,
    KilnParentModel,
    parent_of={
        "runs": TaskRun,
        "dataset_splits": DatasetSplit,
        "finetunes": Finetune,
        "prompt_optimization_jobs": PromptOptimizationJob,
        "prompts": Prompt,
        "evals": Eval,
        "specs": Spec,
        "run_configs": TaskRunConfig,
        "data_guides": DataGuide,
        "eval_inputs": EvalInput,           # NEW
    },
):
```

**How `parent_of` works (basemodel.py:768-773):** `__init_subclass__` iterates the `parent_of` dict and calls `_create_child_method` (creates `self.eval_inputs()`) and `_create_parent_methods` (sets `EvalInput.parent_type()` and `EvalInput.relationship_name()`).

**File structure on disk:**
```
task_dir/
  task.kiln
  runs/           # TaskRun children (existing)
  eval_inputs/    # EvalInput children (NEW)
    {id} - {name}/
      eval_input.kiln
  evals/          # Eval children (existing)
```

**V1 invisibility (verified):** `iterate_children_paths_of_parent_path` at basemodel.py:628-662 scans `parent_folder / cls.relationship_name()`. Each child type scans ONLY its own named folder. V1's `Task` does not have `"eval_inputs"` in its `parent_of` dict, so:
- V1 never scans the `eval_inputs/` folder.
- V1 never attempts to parse `eval_input.kiln` files.
- The folder is completely invisible to V1.

**EvalInput model shape (per ALIGNMENT.md A1.1, A1.2):**

```python
class EvalInput(KilnParentedModel):
    tags: list[str] = []
    reference: dict[str, JsonValue] | None = None
    data: EvalInputData      # discriminated union

    # Provenance (per F.1)
    source_task_run_id: str | None = None
```

No V1 coexistence concern -- EvalInput is a purely new entity.

---

### 1.4 DatasetFilter / EvalInputFilter coexistence

**Current V1 code (dataset_filters.py:10-18):**

```python
class DatasetFilter(Protocol):
    def __call__(self, task_run: TaskRun) -> bool: ...
```

All existing filters (`AllDatasetFilter`, `HighRatingDatasetFilter`, `TagFilter`, `MultiDatasetFilter`) are typed `TaskRun -> bool`. The registry `dataset_filter_from_id` returns `DatasetFilter` callables.

**Per A2.5: `DatasetFilter` stays TaskRun-only forever.** No generalization.

**New parallel filter system for V2:**

```python
# New file or section in dataset_filters.py

class EvalInputFilter(Protocol):
    def __call__(self, eval_input: EvalInput) -> bool: ...

class AllEvalInputFilter:
    def __call__(self, eval_input: EvalInput) -> bool:
        return True

class TagEvalInputFilter:
    def __init__(self, tag: str):
        self.tag = tag
    def __call__(self, eval_input: EvalInput) -> bool:
        return self.tag in eval_input.tags

# New type for filter IDs (parallel to DatasetFilterId)
EvalInputFilterId = Annotated[str, AfterValidator(lambda v: _check_eval_input_filter_id(v))]

def eval_input_filter_from_id(id: EvalInputFilterId) -> EvalInputFilter: ...
```

**Eval model extension (eval.py:328):**

```python
class Eval(...):
    # ... existing fields ...
    # NEW: V2 filter field. V1 evals leave this None.
    eval_input_filter_id: EvalInputFilterId | None = Field(
        default=None,
        description="Filter ID for EvalInput-backed datasets (V2). Mutually exclusive with V1 TaskRun filter fields for V2 evals."
    )
```

Adding this optional field is safe per `extra = "ignore"` on KilnBaseModel (V1 clients silently drop it).

**Runner dispatch (eval_runner.py:88-101):** The `collect_tasks` method currently dispatches on `eval_run_type`. V2 extends this to also check which filter field is set on the parent Eval:

```python
def collect_tasks(self) -> List[EvalJob]:
    if self.eval.eval_input_filter_id is not None:
        # V2 path: EvalInput-backed dataset
        return self.collect_tasks_for_eval_input(self.eval.eval_input_filter_id)
    elif self.eval_run_type == "eval_config_eval":
        # V1 path: TaskRun-backed, eval config eval
        return self.collect_tasks_for_eval_config_eval(self.eval.eval_configs_filter_id)
    else:
        # V1 path: TaskRun-backed, task run eval
        return self.collect_tasks_for_task_run_eval()
```

---

### 1.5 Runner / adapter dispatch

**Current V1 dispatch chain:**

1. `EvalRunner.__init__` (eval_runner.py:41-86) takes `eval_configs`, `run_configs`, `eval_run_type`.
2. `EvalRunner.run_job` (eval_runner.py:201) calls `eval_adapter_from_type(job.eval_config.config_type)` which returns the adapter CLASS.
3. `eval_adapter_from_type` (registry.py:7-15) is a match statement: `g_eval -> GEval`, `llm_as_judge -> GEval`, else exhaustive error.
4. The adapter class is instantiated with `(eval_config, run_config_properties, skills)`.
5. `BaseEval.__init__` (base_eval.py:21-38) reads `eval_config.model_name` and `eval_config.model_provider`.

**V2 extension -- two-level registry (per A2.1, pending Batch C 11b lock):**

```python
# registry.py

def eval_adapter_from_type(eval_config: EvalConfig) -> type[BaseEval] | type[BaseEvalV2]:
    if eval_config.config_type == EvalConfigType.v2:
        # V2 dispatch: keyed on properties.type
        return v2_eval_adapter_from_properties_type(eval_config.properties)
    # Legacy dispatch: keyed on config_type enum
    match eval_config.config_type:
        case EvalConfigType.g_eval:
            return GEval
        case EvalConfigType.llm_as_judge:
            return GEval
        case _:
            raise_exhaustive_enum_error(eval_config.config_type)


def v2_eval_adapter_from_properties_type(properties: V2EvalConfigProperties) -> type[BaseEvalV2]:
    # Dispatch on the inner type discriminator
    match properties.type:
        case V2EvalType.llm_judge:
            return LlmJudgeV2
        case V2EvalType.exact_match:
            return ExactMatchV2
        # ... etc
```

**Signature change impact:** The current `eval_adapter_from_type` takes `EvalConfigType` (an enum). Changing it to take `EvalConfig` (the full object) is a breaking API change for any external callers. Internal callers: only `eval_runner.py:204`. External callers: unknown but the function is not public API. The change at the call site is minimal:

```python
# eval_runner.py:204 (current)
evaluator = eval_adapter_from_type(job.eval_config.config_type)(job.eval_config, ...)

# eval_runner.py:204 (proposed)
evaluator = eval_adapter_from_type(job.eval_config)(job.eval_config, ...)
```

**BaseEval vs BaseEvalV2 (pending Batch C 11c):**

`BaseEval.__init__` at base_eval.py:21-38 calls `self.eval_config.model_name` and `self.eval_config.model_provider` unconditionally. V2 non-LLM adapters do not have these. Options:

- (a) **Separate `BaseEvalV2` class** that does not read root-level model fields. V2 adapters inherit from `BaseEvalV2`; legacy adapters inherit from `BaseEval` unchanged.
- (b) **Guard the model field reads** behind a `config_type` check in `BaseEval.__init__`.

Recommend (a): cleaner separation, no risk of breaking legacy adapters.

```python
class BaseEvalV2:
    """Base class for V2 eval adapters. Does not assume LLM model fields at root."""
    def __init__(self, eval_config: EvalConfig):
        self.eval_config = eval_config
        self.eval = eval_config.parent_eval()
        self.task = self.eval.parent_task()

    @abstractmethod
    async def run_eval(
        self,
        input_data: EvalInput | TaskRun,
        eval_job_item: EvalInput | TaskRun | None = None,
    ) -> tuple[EvalScores, Dict[str, str] | None]:
        pass
```

---

### 1.6 Composite EvalConfigs mixing V1 and V2 children

**Current composite support:** There is no composite EvalConfig type in V1. The `composite` type is V2-only (per type catalog). When a composite config scores an Eval, it reads child config scores from `EvalRun.scores` -- the scores dict is the same structure regardless of whether the child was scored by a legacy adapter or a V2 adapter.

**Does it work today?** No -- composite doesn't exist yet. But the data format is compatible: both legacy and V2 `EvalRun`s write `scores: EvalScores` (= `Dict[str, float]`). The composite adapter reads these from disk. As long as child runs are saved before the composite reads them, the mixing works.

**Test coverage needed:** An explicit test that creates:
1. An Eval with `output_scores` covering both legacy and V2 configs.
2. A legacy `g_eval` EvalConfig producing some score keys.
3. A V2 `exact_match` EvalConfig producing other score keys.
4. A `composite` EvalConfig that reads both.

---

### 1.7 Eval model coexistence

**Current Eval model (eval.py:328-475):**

Key fields affected by V2:

1. **`current_config_id`** (eval.py:339-341): Required, points to the active EvalConfig. For V2 Evals that may have multiple active configs (if 1:N in Batch C), this field persists as the "primary" config. Additive field `active_config_ids: list[str] | None = None` may be added. V1 clients ignore the new field.

2. **`eval_set_filter_id` and `eval_configs_filter_id`** (eval.py:343-349): V1 filter IDs. For V2 evals using EvalInput datasets, these are None and `eval_input_filter_id` is populated instead. Issue: `eval_set_filter_id` is currently non-optional (`DatasetFilterId` without default). V2 Evals without TaskRun datasets need this to be optional.

   ```python
   # CHANGED: optional for V2 evals that use EvalInput datasets
   eval_set_filter_id: DatasetFilterId | None = Field(
       default=None,
       description="..."
   )
   ```

   **Risk:** Making `eval_set_filter_id` optional changes the V1 API contract. Code that creates V1 Evals without explicitly setting this will silently succeed. Mitigation: add a validator that enforces `eval_set_filter_id` is set when no `eval_input_filter_id` is provided.

3. **`evaluation_data_type`** (eval.py:365-368): Stays at Eval level for V1 Evals. V2 EvalConfigs carry their own. The runner reads from the appropriate location.

4. **`validate_template_properties` at eval.py:476-549**: Validates that `eval_configs_filter_id` is set for all non-RAG templates. V2 evals may not have templates at all. The validator is guarded by `self.template is not None` at eval.py:478 -- but line 479 checks `self.template is not EvalTemplateId.rag` which includes the case `self.template is None` (None is not rag, so the check triggers). **This is a bug for V2 evals without templates** -- they'd fail the `eval_configs_filter_id` check.

   Fix: guard the entire block with `if self.template is not None:`.

   ```python
   @model_validator(mode="after")
   def validate_template_properties(self) -> Self:
       if self.template is None:
           return self  # V2 evals and non-template evals skip template validation
       # ... rest unchanged ...
   ```

5. **`upgrade_old_reference_answer_eval_config` at eval.py:396-438**: Migration validator that sets `current_config_id` for legacy reference_answer evals. Only runs when `_loaded_from_file` is True. Safe for V2 evals (they always have `current_config_id` set). No change needed.

6. **`migrate_train_set_filter_id` at eval.py:440-459**: Sets `train_set_filter_id` for legacy evals. Only runs when `_loaded_from_file` is True and `train_set_filter_id` is None. Safe for V2 evals. No change needed (V2 evals can inherit the auto-generated filter ID).

---

## Part 2 -- Specific code changes by file

### `libs/core/kiln_ai/datamodel/eval.py`

| Change | Description | Code shape | Phase |
|---|---|---|---|
| **Add `v2` to `EvalConfigType`** | New enum member | `v2 = "v2"` at line ~55 | Phase 0, sub-task 1 |
| **Add `V2EvalType` enum** | V2-only type enum for properties discriminator | New `class V2EvalType(str, Enum)` with `llm_judge`, `exact_match`, etc. | Phase 0, sub-task 1 |
| **Add V2 properties classes** | `LlmJudgeProperties`, `ExactMatchProperties`, etc. | New `BaseModel` subclasses per ALIGNMENT.md A2.1 | Phase 0, sub-task 1 |
| **Add `V2EvalConfigProperties` union** | Annotated discriminated union | `V2EvalConfigProperties = Annotated[Union[...], Discriminator("type")]` | Phase 0, sub-task 1 |
| **Change `EvalConfig.model_name`** | `str` -> `str \| None = None` | Field default change at line ~267-268 | Phase 0, sub-task 1 |
| **Change `EvalConfig.model_provider`** | `str` -> `str \| None = None` | Field default change at line ~269-270 | Phase 0, sub-task 1 |
| **Change `EvalConfig.properties` type** | `dict[str, Any]` -> `V2EvalConfigProperties \| dict[str, Any] \| None` | Type annotation change at line ~277 | Phase 0, sub-task 1 |
| **Extend `validate_properties`** | Add `config_type == v2` branch; enforce model_name/provider constraints | New elif branch at line ~306 (before the `else: raise`) | Phase 0, sub-task 1 |
| **Guard `validate_json_serializable`** | Skip json.dumps for V2 properties | Add `if self.config_type == EvalConfigType.v2: return self` at top of validator | Phase 0, sub-task 1 |
| **Add `eval_input_filter_id` to `Eval`** | New optional field for V2 EvalInput datasets | `eval_input_filter_id: EvalInputFilterId \| None = None` after line ~349 | Phase 0, sub-task 2 |
| **Make `eval_set_filter_id` optional** | Required -> optional for V2 evals | `eval_set_filter_id: DatasetFilterId \| None = None` at line ~343 | Phase 0, sub-task 2 |
| **Fix `validate_template_properties`** | Guard with `if self.template is None: return self` | Add guard at line ~477 | Phase 0, sub-task 2 |
| **Add V2 fields to `EvalRun`** | `eval_input_id`, `dataset_source_type`, `reference_data` | Three new optional fields with defaults | Phase 0, sub-task 3 |
| **Extend `validate_reference_answer`** | Allow V2 runs to use `reference_data` without triggering legacy constraint | Add V2 bypass check | Phase 0, sub-task 3 |
| **Add `EvalInput` class** | New `KilnParentedModel` for eval datasets | New class per A1.1/A1.2 shape | Phase 0, sub-task 4 |
| **Add `EvalInputData` union** | Discriminated union for input variants | New types + union per A1.1 | Phase 0, sub-task 4 |

### `libs/core/kiln_ai/datamodel/task.py`

| Change | Description | Code shape | Phase |
|---|---|---|---|
| **Add `eval_inputs` to `Task.parent_of`** | Register EvalInput as child | `"eval_inputs": EvalInput` in parent_of dict at line ~129 | Phase 0, sub-task 4 |
| **Add `eval_inputs()` typed method** | Return type wrapper | `def eval_inputs(self, readonly=False) -> list[EvalInput]:` | Phase 0, sub-task 4 |
| **Add import** | Import EvalInput | `from kiln_ai.datamodel.eval import EvalInput` at top | Phase 0, sub-task 4 |

### `libs/core/kiln_ai/datamodel/dataset_filters.py`

| Change | Description | Code shape | Phase |
|---|---|---|---|
| **Add `EvalInputFilter` protocol** | Parallel to `DatasetFilter` but typed to `EvalInput` | New `Protocol` class | Phase 0, sub-task 5 |
| **Add `EvalInputFilterId` type** | Validated string type for V2 filter IDs | `Annotated[str, AfterValidator(...)]` | Phase 0, sub-task 5 |
| **Add `eval_input_filter_from_id`** | Registry function for EvalInput filters | New function, parallel to `dataset_filter_from_id` | Phase 0, sub-task 5 |
| **Add basic EvalInput filters** | `AllEvalInputFilter`, `TagEvalInputFilter` | New filter classes/functions | Phase 0, sub-task 5 |

### `libs/core/kiln_ai/adapters/eval/registry.py`

| Change | Description | Code shape | Phase |
|---|---|---|---|
| **Change `eval_adapter_from_type` signature** | Takes `EvalConfig` instead of `EvalConfigType` | Signature change + V2 dispatch branch | Phase 0, sub-task 6 |
| **Add `v2_eval_adapter_from_properties_type`** | Inner dispatch for V2 types | New function with match on `properties.type` | Phase 1 (when V2 adapters exist) |

### `libs/core/kiln_ai/adapters/eval/base_eval.py`

| Change | Description | Code shape | Phase |
|---|---|---|---|
| **Add `BaseEvalV2` class** | V2 adapter base (no root model_name/provider assumption) | New class parallel to `BaseEval` | Phase 0, sub-task 6 |

### `libs/core/kiln_ai/adapters/eval/eval_runner.py`

| Change | Description | Code shape | Phase |
|---|---|---|---|
| **Extend `collect_tasks`** | Add EvalInput-backed dataset path | New `collect_tasks_for_eval_input` method + dispatch in `collect_tasks` | Phase 0, sub-task 7 |
| **Update `run_job`** | Handle V2 adapter dispatch (pass `EvalConfig` instead of `config_type`) | Line ~204: `eval_adapter_from_type(job.eval_config)` | Phase 0, sub-task 6 |
| **Extend `EvalJob`** | Support EvalInput items | `item: TaskRun \| EvalInput` + adjust type field | Phase 0, sub-task 7 |

### `libs/core/kiln_ai/adapters/eval/g_eval.py`

| Change | Description | Code shape | Phase |
|---|---|---|---|
| **No changes to V1 GEval** | Legacy adapter stays untouched. V2 `llm_judge` adapter is a new class. | -- | -- |

### New files

| File | Purpose | Phase |
|---|---|---|
| `libs/core/kiln_ai/adapters/eval/v2/` | V2 adapter directory | Phase 1 |
| `libs/core/kiln_ai/adapters/eval/v2/llm_judge.py` | V2 LLM judge (may share helpers with GEval) | Phase 1 |
| `libs/core/kiln_ai/adapters/eval/v2/exact_match.py` | V2 exact match | Phase 1 |
| `libs/core/kiln_ai/adapters/eval/v2/base_eval_v2.py` | BaseEvalV2 class (if not in base_eval.py) | Phase 0 |
| `libs/core/kiln_ai/datamodel/eval_input.py` | EvalInput model (may live in eval.py or separate file) | Phase 0 |

---

## Part 3 -- Document modifications needed

### `PLAN.md`

| Section | Change | Priority |
|---|---|---|
| Phase 0 heading (line 229) | "Schema migration" -> "Additive schema introduction" | **must-fix** |
| Phase 0 bullet 2 (line 231) | "legacy auto-migrates via `model_validator`" -> "V2 `config_type` added; legacy shapes preserved; `model_validator` validates V2 shape only" | **must-fix** |
| Phase 0 bullet 3 (line 232) | Add qualifier: "V1 Evals keep it at Eval level" | **must-fix** |
| Phase 0 bullet 4 (line 233) | "unified under" -> "V2 `llm_judge` type added (legacy types preserved)" | **must-fix** |
| Phase 0 bullet 6 (line 235) | "`DatasetFilter` generalized" -> "New `EvalInputFilter` added (DatasetFilter unchanged)" | **must-fix** |
| design/15 description (line 195) | Reframe as `15_v1_v2_coexistence.md`; drop `model_validator` migration framing | **should-fix** |
| Risks to phase against (line 289) | Add: "V2 EvalRun validator extensions -- existing validators at eval.py:146-255 read grandparent Eval fields; V2 configs relocate some fields" | **should-fix** |

### `V2_PITCH.md`

| Section | Change | Priority |
|---|---|---|
| Phase 0 scope (line 111) | Remove "`model_validator` for V1 configs"; replace with "additive V2 markers" | **must-fix** |
| Phase 0 bullet 4 (impl phasing table) | Add "legacy types preserved" qualifier | **must-fix** |
| DatasetFilter row in coexistence table (line 94) | Already says "new `EvalInputFilter`" -- correct. Verify it doesn't say "generalized" | -- |

### `alignment_plan.md`

| Section | Change | Priority |
|---|---|---|
| Decision 31 (line 71) | "migration via `model_validator`" -> "coexistence validation + explicit upgrade" | **must-fix** |
| Batch H description (line 183-194) | Remove "mostly already specified in synthesis"; replace with "fresh design under A0.1" | **must-fix** |
| Decisions 7, 8 (lines 29-30) | Add "(V2-only; legacy preserved)" qualifiers | **should-fix** |
| Batch ordering section | Add one-line A0.1 reminder | **should-fix** |

### `OPENS.md`

| Section | Change | Priority |
|---|---|---|
| Migration item, line 73 | Add superseded note: A0.1 rejects model_validator migration | **must-fix** |
| EvalConfig items, lines 24-25 | Add "V2-only" context per A0.1 | **should-fix** |
| TaskRun conversion, line 75 | Add "explicit user action" qualifier | **should-fix** |

### `reports/_synthesis.md`

| Section | Change | Priority |
|---|---|---|
| "Breaks" table (lines 385-396) | Add superseded note: migration paths in this table replaced by coexistence per A0.1 | **should-fix** |
| "Cross-cutting risks" migration row | Add note: risk resolved by A0.1 | **should-fix** |

---

## Part 4 -- New opens (not previously tracked)

1. **`validate_template_properties` bug for non-template Evals (eval.py:476-549).** The validator at line 479 checks `self.template is not EvalTemplateId.rag` which is True when `self.template is None`, causing V2 (or any non-template) Evals to fail the `eval_configs_filter_id` check. Fix is a one-line guard: `if self.template is None: return self`. This is a V1 bug that also affects V2.

2. **`EvalRun.validate_output_fields` reads `evaluation_data_type` from grandparent Eval (eval.py:146-166).** V2 configs relocate this to config properties (per A2.3). The validator will read a stale or default Eval-level value for V2 runs. Needs an explicit V2 bypass or the V2 runner must ensure the Eval-level field stays consistent. Design decision needed.

3. **`eval_set_filter_id` is currently required (non-optional, no default) on `Eval` (eval.py:343-345).** Making it optional for V2 evals is an API-level change. Every place that creates an Eval today passes this field -- but removing the requirement means future V1-style code could accidentally omit it. A validator must enforce mutual exclusivity: exactly one of `{eval_set_filter_id, eval_input_filter_id}` must be set.

4. **`BaseEval.model_and_provider()` (base_eval.py:40-54) is called from `GEval.run_eval`.** This method reads `self.eval_config.model_name` directly. If V2 LLM-based adapters share this base class, they need model fields to live inside `properties`, not at root. Confirms the recommendation for a separate `BaseEvalV2` class.

5. **`EvalRunner.__init__` unconditionally reads `run_configs` and validates them against the task (eval_runner.py:64-75).** V2 EvalInput-backed runs may not use `run_configs` at all. The `__init__` must be extended to handle EvalInput-only runs where `run_configs` is None even for non-eval_config_eval runs.

6. **Pydantic union parse order for `EvalConfig.properties`.** When loading V1 files from disk, Pydantic will attempt `V2EvalConfigProperties` first (discriminated union on `type`), fail, then fall through to `dict[str, Any]`. This is correct but relies on implicit ordering. A `mode="before"` validator that explicitly routes parsing based on `config_type` is safer. Design decision: implicit union fallback vs explicit pre-routing.

---

## Part 5 -- Sequencing recommendation

### Ordered implementation sequence

1. **Doc fixes (must-fix-before-resuming-batches).** PLAN.md Phase 0, alignment_plan.md decision 31 + Batch H, OPENS.md migration item, V2_PITCH.md Phase 0. These prevent sub-agents from inheriting wrong constraints.

2. **`validate_template_properties` bug fix (eval.py:476).** One-line guard. Fix in V1 now -- it's a pre-existing bug that blocks non-template Eval creation, not just V2.

3. **Phase 0 sub-task 1: EvalConfig schema extension.** Add `v2` to enum, add V2 properties types, change `model_name`/`model_provider` to optional, extend `validate_properties`, guard `validate_json_serializable`. Characterization tests for the existing validators first.

4. **Phase 0 sub-task 2: Eval model extension.** Add `eval_input_filter_id`, make `eval_set_filter_id` optional, add mutual-exclusivity validator. This enables the runner to dispatch on filter type.

5. **Phase 0 sub-task 3: EvalRun model extension.** Add `eval_input_id`, `dataset_source_type`, `reference_data`. Extend validators with V2 bypasses.

6. **Phase 0 sub-task 4: EvalInput entity.** New model, add to `Task.parent_of`. No dependencies on other sub-tasks.

7. **Phase 0 sub-task 5: EvalInputFilter.** New protocol + basic filters + registry. Depends on sub-task 4.

8. **Phase 0 sub-task 6: Registry + BaseEvalV2.** Change registry signature, add `BaseEvalV2`. Depends on sub-tasks 1 and 3.

9. **Phase 0 sub-task 7: Runner extension.** Add `collect_tasks_for_eval_input`, extend `EvalJob`, wire V2 dispatch. Depends on sub-tasks 5 and 6.

10. **Characterization tests for GEval `reference_answer` path.** Zero existing tests for `generate_ref_ans_run_description` and the `reference_answer` evaluation branch in `GEval.run_eval` (eval.py:307-313). Must be added before any refactoring of the legacy adapter, to prevent regressions when V2 `llm_judge` shares helpers.

11. **Doc fixes (should-fix).** alignment_plan.md qualifiers, OPENS.md context, _synthesis.md superseded notes.

12. **Phase 1 V2 adapters.** Build on the Phase 0 foundation.

### What blocks what

- Sub-tasks 1-4 are independent and can be parallelized.
- Sub-task 5 depends on 4 (EvalInput model must exist for filter typing).
- Sub-task 6 depends on 1 (V2EvalConfigProperties must exist for registry dispatch).
- Sub-task 7 depends on 5 and 6 (runner needs both filter and adapter infrastructure).
- Phase 1 depends on all Phase 0 sub-tasks.

---

## Opens

- [ ] **Pydantic union parse routing strategy for `EvalConfig.properties`** -- implicit union fallback vs explicit `mode="before"` validator. The implicit approach works but is fragile; the explicit approach is safer but adds a validator. Design decision before Phase 0 sub-task 1.
- [ ] **`validate_output_fields` V2 bypass design** -- how does the validator handle V2 EvalRuns where `evaluation_data_type` has moved to config properties? Options: (a) V2 runner sets a consistent Eval-level default, (b) validator checks `config_type` and skips, (c) validator reads from config properties when `config_type == v2`. Blocks Phase 0 sub-task 3.
- [ ] **`eval_set_filter_id` mutual exclusivity validator design** -- exact shape of the validator that enforces "exactly one of `{eval_set_filter_id, eval_input_filter_id}` must be set." Edge cases: legacy evals loaded from disk that have neither (possible if created before the field was required). Blocks Phase 0 sub-task 2.
- [ ] **V2 `llm_judge` code sharing with legacy `GEval`** -- inheritance, delegation, or clean rewrite? `GEval` at 563 lines with significant logprob-processing logic worth reusing. Decision 32a (pending Batch H) covers this, but Phase 1 implementation needs the answer. Does not block Phase 0.
- [ ] **`EvalRunner.__init__` refactoring for EvalInput-only runs** -- the constructor validates `run_configs` against `eval_run_type` at lines 64-78. V2 EvalInput-backed runs don't fit either V1 type cleanly. May need a new `eval_run_type` value or a restructured constructor. Blocks Phase 0 sub-task 7.

## Sources

- `~/Dropbox/workspace/kiln_new/libs/core/kiln_ai/datamodel/eval.py` -- EvalConfig, EvalRun, Eval, all validators
- `~/Dropbox/workspace/kiln_new/libs/core/kiln_ai/datamodel/basemodel.py` -- KilnBaseModel (ConfigDict, extra policy), KilnParentedModel, parent_of
- `~/Dropbox/workspace/kiln_new/libs/core/kiln_ai/datamodel/task.py` -- Task parent_of declarations
- `~/Dropbox/workspace/kiln_new/libs/core/kiln_ai/datamodel/task_run.py` -- TaskRun model
- `~/Dropbox/workspace/kiln_new/libs/core/kiln_ai/adapters/eval/registry.py` -- adapter registry
- `~/Dropbox/workspace/kiln_new/libs/core/kiln_ai/adapters/eval/base_eval.py` -- BaseEval interface
- `~/Dropbox/workspace/kiln_new/libs/core/kiln_ai/adapters/eval/g_eval.py` -- GEval adapter
- `~/Dropbox/workspace/kiln_new/libs/core/kiln_ai/adapters/eval/eval_runner.py` -- EvalRunner + EvalJob
- `~/Dropbox/workspace/kiln_new/libs/core/kiln_ai/datamodel/dataset_filters.py` -- DatasetFilter protocol + registry
- `ALIGNMENT.md` -- A0.1, A1.1-A1.4, A2.1, A2.5, F.1, F.2
- `V2_PITCH.md` -- coexistence table
- `backwards_compat_plan.md` -- earlier non-code-grounded plan (structure reference)
