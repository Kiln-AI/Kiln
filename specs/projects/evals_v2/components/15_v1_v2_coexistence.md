---
status: complete
approved: true
alignment_refs: [A0.1, A2.1, A2.2, A2.3, A2.5, A2.6, A2.7, A2.8, A2.9, B2.1, C.runner.2, C.runner.3, C.11b, D.5, K.1, K.3, H.32]
opens: []
summary: Every V1/V2 coexistence pattern — legacy enum dispatch, additive fields, parsing routing, EvalRun field coexistence, filter coexistence, validator V2 bypass, V2-only EvalConfig creation paths, V2 EvalConfig consuming V1 TaskRun-source data via runtime translation.
---

# V1/V2 Coexistence

## 1. Governing principle

**A0.1 — V2 reads V1; V2 never migrates V1.** Every pattern in this file derives from this principle. V2 code adds new fields, new enum values, and new parsing branches. It never rewrites V1 records on disk, never removes a V1 field, and never changes V1 runtime behavior. V1 clients failing on V2-only records is acceptable (users upgrade forward; mixed-version teams expect the newest client to push the project forward).

**D.5 — V1 backwards compatibility is absolute.** V1 EvalConfigs (`config_type: "g_eval"` / `"llm_as_judge"`) continue to use the existing `GEval` adapter, the existing three hardcoded `generate_*_run_description` f-strings, the existing `EvalDataType` enum at the Eval level. Zero V1 behavior changes, ever. This covers read + execution of existing V1 records on disk. It does NOT mean creation endpoints must keep emitting V1 shape: K.1 and K.3 intentionally change the manual/Copilot creation paths to emit V2-shaped EvalConfigs going forward.

**Key infrastructure fact (verified against `~/Dropbox/workspace/kiln_new` 2026-05-21):** `KilnBaseModel` uses Pydantic v2 default `extra = "ignore"` (no override anywhere). V2 can add new optional fields freely; V1 silently drops unknown fields when loading V2-written files. Additive-fields strategy is safe.

---

## 2. EvalConfig coexistence (A2.1, A2.2, A2.8)

### 2.1 `EvalConfigType` enum extension

V1 enum (`eval.py:51-55`) has two values: `g_eval`, `llm_as_judge`. V2 adds `v2 = "v2"`.

```python
class EvalConfigType(str, Enum):
    g_eval = "g_eval"
    llm_as_judge = "llm_as_judge"
    v2 = "v2"                        # NEW
```

Legacy values stay forever (needed for V2 to read V1 files). V1 clients will `ValidationError` on `"v2"` — acceptable per A0.1.

### 2.2 `EvalConfig` field changes

**Current V1 model (`eval.py:259-317`):**

```python
class EvalConfig(KilnParentedModel, KilnParentModel, parent_of={"runs": EvalRun}):
    name: FilenameString
    model_name: str              # required, no default
    model_provider: str          # required, no default
    config_type: EvalConfigType  # default=EvalConfigType.g_eval
    properties: dict[str, Any]   # default={}
```

**V2 changes:**

| Field | V1 | V2 | Rationale |
|---|---|---|---|
| `model_name` | `str` (required) | `str \| None = None` | V2 non-LLM configs (exact_match, etc.) have no model. V1 files always populate this. The `validate_properties` validator (see below) enforces presence for legacy types and absence for V2. |
| `model_provider` | `str` (required) | `str \| None = None` | Same rationale as `model_name`. |
| `properties` | `dict[str, Any]` | `V2EvalConfigProperties \| dict[str, Any] \| None` | V1 files parse as `dict`; V2 files parse as the typed discriminated union via the `mode="before"` routing validator. |

**Default-change risk:** Making `model_name`/`model_provider` optional means new construction without explicit values silently succeeds. The `validate_properties` validator catches this for legacy `config_type` values.

### 2.3 Properties parsing routing — `mode="before"` validator (A2.8)

Per A2.8, an explicit `model_validator(mode="before")` on `EvalConfig` inspects `config_type` and routes `properties` parsing. This avoids relying on Pydantic's implicit union fallback ordering (which would attempt the V2 discriminated union first, fail for V1 dicts, then fall through to `dict[str, Any]` — correct in practice but fragile, and a V1 dict containing a `type` key matching a V2 type could mis-parse silently).

```python
@model_validator(mode="before")
@classmethod
def dispatch_properties_parsing(cls, data: dict, info: ValidationInfo) -> dict:
    if not isinstance(data, dict):
        return data
    config_type = data.get("config_type", "g_eval")
    if config_type == "v2":
        # Let V2EvalConfigProperties discriminated union handle parsing
        # (Pydantic's Discriminator("type") on properties)
        pass
    else:
        # Legacy — keep properties as raw dict; do NOT attempt V2 union parsing
        pass
    return data
```

This validator runs before the `mode="after"` shape validator. The two together provide the full parsing + validation pipeline.

### 2.4 Shape validation — `mode="after"` validator

Extends the existing `validate_properties` at `eval.py:290-308`. The existing `else: raise ValueError` gatekeeper at line 308 now has a new `elif` branch for `config_type == v2`:

```python
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
            raise ValueError(
                "model_name and model_provider are required for legacy configs"
            )
        return self
    elif self.config_type == EvalConfigType.v2:
        # --- NEW V2 validation ---
        if not isinstance(self.properties, BaseModel):
            raise ValueError("V2 config requires typed properties")
        if self.model_name is not None or self.model_provider is not None:
            raise ValueError(
                "V2 configs must not set root-level model_name/model_provider"
            )
        return self
    else:
        raise ValueError(f"Invalid eval config type: {self.config_type}")
```

### 2.5 JSON-serializable validator guard

The existing `validate_json_serializable` at `eval.py:310-317` calls `json.dumps(self.properties)`. When `properties` is a Pydantic `BaseModel` (V2 typed union), `json.dumps` fails on the raw object. V2 bypass:

```python
@model_validator(mode="after")
def validate_json_serializable(self) -> Self:
    if self.config_type == EvalConfigType.v2:
        return self  # V2 properties are Pydantic models — own validation
    try:
        json.dumps(self.properties)
    except TypeError as e:
        raise ValueError(f"Properties must be JSON serializable: {e!s}")
    return self
```

### 2.6 Judge unification naming (A2.2)

V2 ships a single judge type: `V2EvalType.llm_judge`. Both legacy V1 enum values (`EvalConfigType.g_eval`, `EvalConfigType.llm_as_judge`) stay in the enum forever and continue to dispatch to the legacy `GEval` adapter unchanged. V2 `LlmJudgeProperties` carries `g_eval: bool = False` (per the Batch D design file, which renamed the original `g_eval_mode` used in the A2.2 alignment text). No auto-upgrade of V1 evals: V1 `g_eval` configs stay V1 forever on disk.

### 2.7 V1/V2 client interaction matrix

| File on disk | V1 Kiln client | V2 Kiln client |
|---|---|---|
| V1 EvalConfig (`config_type in {g_eval, llm_as_judge}`) | Loads cleanly. Runs via existing `GEval`. | Loads via legacy parsing path (properties as dict, root model fields populated). Dispatches to legacy adapter. |
| V2 EvalConfig (`config_type = "v2"`) | `"v2"` is unknown enum value. V1 raises `ValidationError`. Also: `validate_properties` at `eval.py:290-308` has `else: raise ValueError` for unknown config_type. Both block V1 from loading V2-only configs — acceptable per A0.1. | Loads via V2 parsing path. Properties validated as discriminated union. Dispatches to V2 adapter registry keyed on `properties.type`. |

---

## 3. EvalRun field coexistence (A2.6, A2.7, C.runner.2)

### 3.1 Additive V2 fields on EvalRun

All new fields are optional with default `None`. Safe per `extra = "ignore"` — V1 clients silently drop them.

```python
class EvalRun(KilnParentedModel):
    # --- Existing fields unchanged ---
    dataset_id: ID_TYPE | None = None  # CHANGED to optional — V1 TaskRun source
    # ... input, output, reference_answer, scores, etc. all unchanged ...

    # --- V2 additions ---
    eval_input_id: ID_TYPE | None = None     # V2 EvalInput source (A2.6)
    reference_data: dict[str, JsonValue] | None = None  # V2 reference (A2.7)
    skipped_reason: str | None = None  # per E.18 — tolerant str, SkippedReason convention
    skipped_detail: str | None = None  # per E.18 — case-specific detail
```

### 3.2 Input-source mutual exclusivity (A2.6)

`eval_config_eval: bool` stays single-purpose (what's being evaluated). Input source is modeled orthogonally via `dataset_id` XOR `eval_input_id`:

```python
@model_validator(mode="after")
def validate_input_source(self):
    if (self.dataset_id is None) == (self.eval_input_id is None):
        raise ValueError("Exactly one of dataset_id or eval_input_id must be set")
    return self
```

V1 EvalRuns always have `dataset_id` set and `eval_input_id = None`, passing this validator unchanged.

### 3.3 Reference data coexistence (A2.7)

V1 EvalRuns use `reference_answer: str | None` (snapshotted from `TaskRun.output.output` for `EvalDataType.reference_answer` evals). V2 EvalRuns use `reference_data: dict[str, JsonValue] | None` (sourced from `EvalInput.reference`). The two fields coexist; the existing `validate_reference_answer` validator gates only `reference_answer` and is untouched. No new validator for `reference_data` at this layer — V2 data-contract validation is per-config at adapter bind time (per A2.3).

### 3.4 `validate_output_fields` V2 bypass (C.runner.2)

The existing validator at `eval.py:146-166` reads `evaluation_data_type` from the grandparent `Eval` to gate `task_run_trace` / `reference_answer` presence. For V2 EvalRuns where `evaluation_data_type` is `None` (A2.3), this gate is meaningless. Single-line V2 bypass:

```python
@model_validator(mode="after")
def validate_output_fields(self) -> Self:
    eval_config = self.parent_eval_config()
    if eval_config and eval_config.config_type == EvalConfigType.v2:
        return self  # V2: per-config properties drive data contract
    # ... existing V1 logic unchanged ...
    return self
```

V1 EvalRuns never hit the bypass (their `config_type` is `g_eval` or `llm_as_judge`).

### 3.5 `validate_eval_run_types` — unchanged

The existing validator at `eval.py:168-177` enforcing `eval_config_eval <-> task_run_config_id` consistency is orthogonal to input source (per A2.6) and stays unchanged.

---

## 4. Eval model coexistence (A2.3, A2.5, A2.9)

### 4.1 `evaluation_data_type` made optional (A2.3)

```python
class Eval(KilnParentedModel):
    # CHANGED: optional for V2 Evals; defaults to final_answer for V1 back-compat
    evaluation_data_type: EvalDataType | None = EvalDataType.final_answer
```

**Default rationale:** The default is `EvalDataType.final_answer` rather than `None`. This is deliberate for V1 backwards compatibility: a V1 Eval on disk that omits this field (e.g., an older file format) loads with `final_answer`, which is the correct V1 behavior (V1 evals evaluate the model's final answer unless explicitly configured for `full_trace` or `reference_answer`). A `None` default would make such V1 Evals ambiguous and could break the `validate_output_fields` validator which reads this field for V1 EvalRuns. V2 Evals that need `None` semantics set it explicitly when constructed.

V1 clients treat this as required (compiled against the V1 definition). V2 EvalConfigs declare their data needs in their own properties (per A2.3); the Eval-level field is preserved only for V1 EvalConfigs which continue to read it from the grandparent Eval.

### 4.2 Filter field coexistence (A2.5, A2.9)

**`DatasetFilter` stays TaskRun-only forever.** No generalization, no union. A new `EvalInputFilter` protocol is introduced for V2 evals using EvalInput datasets.

```python
class Eval(KilnParentedModel):
    # CHANGED: optional for V2 evals (A2.9)
    eval_set_filter_id: DatasetFilterId | None = Field(default=None, ...)
    # NEW: V2 filter field
    eval_input_filter_id: EvalInputFilterId | None = Field(default=None, ...)
    # UNCHANGED: golden subset filter, TaskRun-typed in both flows
    eval_configs_filter_id: DatasetFilterId | None = None

    @model_validator(mode="after")
    def validate_filter_fields(self):
        if (self.eval_set_filter_id is None) == (self.eval_input_filter_id is None):
            raise ValueError(
                "Exactly one of eval_set_filter_id or eval_input_filter_id must be set"
            )
        return self
```

**Coexistence rules:**
- V1 evals: `eval_set_filter_id` populated, `eval_input_filter_id = None`. Runner uses TaskRun path.
- V2 evals using EvalInput datasets: `eval_set_filter_id = None`, `eval_input_filter_id` populated. Runner uses EvalInput path.
- `eval_configs_filter_id` (golden subset) is independent and TaskRun-typed in both flows (B2.1 closure table confirms this).

**EvalInputFilter protocol (parallel to `DatasetFilter` at `dataset_filters.py:10-18`):**

```python
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
```

V1's `DatasetFilter` callables, typed `(TaskRun) -> bool`, are never touched.

### 4.3 `validate_template_properties` guard

The existing validator at `eval.py:476-549` checks `self.template is not EvalTemplateId.rag` — which is `True` when `self.template is None`, causing V2 (or any non-template) Evals to fail the `eval_configs_filter_id` check. This is a pre-existing V1 bug that also blocks V2. Fix:

```python
@model_validator(mode="after")
def validate_template_properties(self) -> Self:
    if self.template is None:
        return self  # V2 evals and non-template evals skip template validation
    # ... rest unchanged ...
```

### 4.4 Other Eval validators — no change needed

- `upgrade_old_reference_answer_eval_config` at `eval.py:396-438`: only runs when `_loaded_from_file` is True; V2 Evals always have `current_config_id` set. Safe.
- `migrate_train_set_filter_id` at `eval.py:440-459`: V2 Evals can inherit the auto-generated filter ID. Safe.

---

## 5. EvalInput addition — V1 invisibility

### 5.1 Placement under Task

```python
class Task(KilnParentedModel, KilnParentModel, parent_of={
    "runs": TaskRun,
    # ... existing entries ...
    "eval_inputs": EvalInput,           # NEW
}):
```

**V1 invisibility (verified):** `iterate_children_paths_of_parent_path` at `basemodel.py:628-662` scans `parent_folder / cls.relationship_name()`. V1's `Task` has no `"eval_inputs"` in its `parent_of` dict:
- V1 never scans the `eval_inputs/` folder.
- V1 never attempts to parse `eval_input.kiln` files.
- The folder is completely invisible to V1.

### 5.2 Disk layout

```
task_dir/
  task.kiln
  runs/           # TaskRun children (existing)
  eval_inputs/    # EvalInput children (NEW)
    {id} - {name}/
      eval_input.kiln
  evals/          # Eval children (existing)
```

No V1 coexistence concern — EvalInput is a purely new entity.

---

## 6. Adapter dispatch coexistence (C.11b, A2.1)

### 6.1 Two-level registry dispatch

Per C.11b and A2.11, `eval_adapter_from_type` signature changes from `EvalConfigType` (enum) to `EvalConfig` (full object). Single call site to update: `eval_runner.py:204`.

```python
# registry.py
def eval_adapter_from_type(eval_config: EvalConfig) -> type[BaseEval]:
    if eval_config.config_type == EvalConfigType.v2:
        return v2_eval_adapter_from_properties_type(eval_config.properties)
    # Legacy dispatch — UNCHANGED
    match eval_config.config_type:
        case EvalConfigType.g_eval:
            return GEval
        case EvalConfigType.llm_as_judge:
            return GEval
        case _:
            raise_exhaustive_enum_error(eval_config.config_type)

def v2_eval_adapter_from_properties_type(
    properties: V2EvalConfigProperties,
) -> type[BaseEval]:
    match properties.type:
        case V2EvalType.llm_judge:
            return LlmJudgeV2
        case V2EvalType.exact_match:
            return ExactMatchV2
        # ... etc per V2 type catalog
```

Call site change at `eval_runner.py:204`:

```python
# Before (V1):
evaluator = eval_adapter_from_type(job.eval_config.config_type)(job.eval_config, ...)

# After (V2):
evaluator = eval_adapter_from_type(job.eval_config)(job.eval_config, ...)
```

### 6.2 No `BaseEvalV2` fork (C.11c reference)

Per C.11c, V2 adapters subclass the existing `BaseEval`. The legacy-specific `model_and_provider()` method (at `base_eval.py:40-54`) is extracted to a helper module (per A2.10). V2 LLM adapters read model fields from their own properties; V2 non-LLM adapters inherit `BaseEval` cleanly without touching model fields. No base class fork.

---

## 7. Runner coexistence (C.runner.3, B2.1)

### 7.1 `EvalRunner.__init__` extension (C.runner.3)

The constructor validation at `eval_runner.py:64-78` gains a new branch for `eval_input_filter_id`-sourced runs. No new `eval_run_type` value — run mode and input source are orthogonal.

**Coverage matrix (V1 and V2 both work over either run mode):**

| Source | Run mode | `run_configs` | Data flow |
|---|---|---|---|
| TaskRun (V1, `eval_set_filter_id`) | `task_run_eval` | required | Existing — run task fresh, judge |
| TaskRun (V1, `eval_configs_filter_id`) | `eval_config_eval` | not used | Existing — judge stored output |
| EvalInput (V2, `eval_input_filter_id`) | `task_run_eval` | required | NEW — runner reads `EvalInput.user_message`, runs via run_configs, judges output |
| EvalInput (V2, `eval_input_filter_id`) | `eval_config_eval` | not used | NEW — runner reads stored output (per B2.1), judges only |
| TaskRun (V1 filter) — **V2 EvalConfig** | either | per mode | NEW (B2.1) — runner synthesizes in-memory EvalInput per TaskRun; V2 adapter consumes EvalInput shape |

The `run_configs iff task_run_eval` invariant is applied identically in both branches — it is mode-driven, not source-driven.

### 7.2 Runner dispatch by filter field

```python
def collect_tasks(self) -> List[EvalJob]:
    if self.eval.eval_input_filter_id is not None:
        # V2 path: EvalInput-backed dataset
        return self.collect_tasks_for_eval_input(self.eval.eval_input_filter_id)
    elif self.eval_run_type == "eval_config_eval":
        # V1 path: eval config eval
        return self.collect_tasks_for_eval_config_eval(self.eval.eval_configs_filter_id)
    else:
        # V1 path: task run eval
        return self.collect_tasks_for_task_run_eval()
```

### 7.3 Runtime TaskRun-to-EvalInput translation (B2.1)

When an EvalConfig has `config_type == "v2"` and the source is TaskRun-shaped (via `eval_set_filter_id` or `eval_configs_filter_id`), the runner synthesizes an in-memory `EvalInput` from each TaskRun for V2 adapter consumption. This enables V2 EvalConfigs under Evals that still use TaskRun datasets (the manual flow, Copilot golden subset).

**Translation mapping:**
- `TaskRun.input` -> `SingleTurnEvalInputData.user_message.text`
- `TaskRun.tags` -> `EvalInput.tags`
- `TaskRun.output.output` -> carried as runner side-channel (`stored_output` on `EvalJob`) for `eval_config_eval` mode; passed to the V2 adapter via the D.2 reserved variable mechanism
- `TaskRun.trace` -> passed to adapter as the D.2 reserved `trace` template variable
- `TaskRun.id` -> NOT carried (F.1 field `source_task_run_id` was un-locked/deferred with Batch F; the synthesized EvalInput is in-memory/runtime-only anyway)
- `TaskRun.output.rating` -> stays on TaskRun; the correlation API at `eval_api.py:1250-1367` continues reading ratings from TaskRun and judge scores from EvalRun unchanged

**EvalJob extension:**

```python
@dataclass
class EvalJob:
    item: TaskRun | EvalInput   # widened from TaskRun (was eval_runner.py:25)
    stored_output: str | None = None  # for eval_config_eval mode with TaskRun source
    # ... existing fields ...
```

**EvalRun source field for V2 EvalConfig + TaskRun-source runs:** `EvalRun.dataset_id` points at the source TaskRun (per A2.6). This preserves the correlation API's ability to pair (TaskRun rating, EvalRun judge scores) for V2 EvalConfig runs without modification.

**Edge cases:**
- Multi-turn TaskRuns (with `parent_task_run_id`) -> skip via C.runner.1 with `incompatible_input_shape` reason
- TaskRun with no rating -> calibration excludes downstream (no skip; judge still produces scores)
- Multi-turn V2 EvalConfigs under V1 TaskRun source -> skip with `incompatible_input_shape`

**No bind-time validator** preventing V2 EvalConfig under V1-filter Eval. The translation path makes the combination work end-to-end.

---

## 8. V2-only EvalConfig creation paths (K.1, K.3)

### 8.1 Manual eval config endpoint (K.1)

`POST /create_eval_config` (`eval_api.py:859-880`) keeps its existing focused, LLM-judge-specific request shape. Handler internally constructs V2-shaped EvalConfig:

```python
EvalConfig(
    config_type="v2",
    properties=LlmJudgeProperties(
        g_eval=request.g_eval_mode,
        model_name=request.model_name,
        model_provider=request.provider,
        eval_steps=...,
        system_prompt=...,      # D.4 default
        thinking_instruction=...,  # D.4 default
    ),
)
```

Request body: `name`, `model_name`, `provider`, `eval_steps`, `task_description`, `g_eval_mode: bool` (replacing V1 `type: EvalConfigType`). URL unchanged.

### 8.2 Dataset shape per flow (K.3, as amended by B2.1)

After this project ships, the spec_builder and manual eval config UI produce **only V2 EvalConfigs**. Dataset shape varies per flow:

| Flow | Eval set | Golden subset | Train set | Filter fields on Eval |
|---|---|---|---|---|
| **Copilot path** | EvalInputs (V2) | TaskRuns (V1, unchanged) | TaskRuns (V1, unchanged) | `eval_input_filter_id` + `eval_configs_filter_id` |
| **Manual path** | TaskRuns (V1, unchanged) | TaskRuns (V1, unchanged) | TaskRuns (V1, unchanged) | `eval_set_filter_id` + `eval_configs_filter_id` |
| **Synth-for-fine-tuning** | n/a | n/a | n/a (orthogonal to evals) | n/a |

EvalConfig type in both flows: always V2 (`config_type="v2"`). The `EvalConfigType.g_eval` and `EvalConfigType.llm_as_judge` enum values remain in the codebase to read existing V1 records on disk, but no new V1 EvalConfig records are created via any path.

The A2.9 mutual-exclusivity validator (`eval_set_filter_id` XOR `eval_input_filter_id`) is compatible with this table because `eval_configs_filter_id` (golden subset) is independent and TaskRun-typed in both flows.

### 8.3 Copilot path V1-to-V2 translation (K.2 reference)

`copilot_api.py:337-340` is updated to construct V2 EvalConfigs from V1-shaped Copilot responses. Field mapping: `model_name` / `model_provider` / `eval_steps` / `task_description` direct; `g_eval=False` always (Copilot always produces non-g_eval); V1 free-form prompt wrapped into V2 Jinja2 `prompt_template`. No remote `api.kiln.tech` changes in this project. Implementation detail for the wrapping shape is owned by `components/21_type_llm_judge.md`.

---

## 9. Coupling-point coverage (H.32)

H.32 is a confirmation, not a new lock. A code-grounded sweep enumerated 12 actual TaskRun-to-eval-pipeline coupling points. All 12 are covered by previously locked decisions:

| # | Coupling point | File:line | Covering decision | Status |
|---|---|---|---|---|
| 1 | `DatasetFilter` protocol typed to `TaskRun` — `DatasetFilter.__call__(self, task_run: TaskRun) -> bool` | `dataset_filters.py:17` | A2.5 — `DatasetFilter` stays TaskRun-only; new `EvalInputFilter` for V2; runner dispatches by which Eval filter field is set | COVERED |
| 2 | `EvalJob.item` typed as `TaskRun` — runner's job dataclass is `item: TaskRun` | `eval_runner.py:25` | B2.1 — `EvalJob` changes to `item: TaskRun \| EvalInput` union + optional `stored_output` | COVERED |
| 3 | `BaseEval.run_eval` signature typed to `TaskRun` — `run_eval(self, task_run: TaskRun, eval_job_item: TaskRun \| None)` | `base_eval.py:94-95` | C.11c + B2.1 — runner guarantees V2 adapters always receive EvalInput and legacy adapters always receive TaskRun; base signature widens to `TaskRun \| EvalInput` as formality. Mechanical, owned by `components/45_runner_architecture.md`. | COVERED (mechanical residue) |
| 4 | `BaseEval.run_task_and_eval` typed to `TaskRun` | `base_eval.py:56-57` | C.11c / runner architecture — V2 adapters go through different dispatch path | COVERED |
| 5 | `EvalRunner.collect_tasks*` iterate `task.runs()` | `eval_runner.py:129, 169` | C.runner.3 — new branch for `eval_input_filter_id`-sourced runs loads EvalInput collection | COVERED |
| 6 | `EvalRun.dataset_id` points to TaskRun ID | `eval.py:104` | A2.6 — add `eval_input_id: ID_TYPE \| None`; validator enforces XOR | COVERED |
| 7 | `EvalRun.validate_output_fields` reads `evaluation_data_type` from grandparent Eval | `eval.py:146-166` | C.runner.2 — V2 bypass via `config_type` check | COVERED |
| 8 | `EvalRun.validate_eval_run_types` enforces `eval_config_eval <-> task_run_config_id` | `eval.py:168-177` | A2.6 — orthogonal to input source; validator unchanged | COVERED |
| 9 | `GEval.run_eval` reads `task_run.input`, `task_run.output.output`, `task_run.trace` | `g_eval.py:292-319` | D.5 — V1 GEval adapter NEVER changed. V2 adapters read from EvalInput/template vars. For V2 EvalConfig + TaskRun source: B2.1 translates. | COVERED |
| 10 | `BaseEval.model_and_provider()` reads root `eval_config.model_name/model_provider` | `base_eval.py:40-54` | A2.10 — extracted to helper module; V2 adapters read from `properties` | COVERED |
| 11 | `eval_adapter_from_type()` takes `EvalConfigType` enum | `registry.py:7` | A2.11 — signature changes to accept full `EvalConfig`; V2 dispatch keyed on `properties.type` | COVERED |
| 12 | `Eval.eval_set_filter_id` is required (no default) | `eval.py:343` | A2.9 — made optional; mutual-exclusivity validator with new `eval_input_filter_id` | COVERED |

**Lone residue:** `BaseEval.run_eval` abstract method signature widening (coupling point #3). This is a mechanical consequence of B2.1, not a new design decision. The runner dispatches correctly — V2 adapters always receive EvalInput, legacy adapters always receive TaskRun. Design detail is in `components/45_runner_architecture.md`.

---

## 10. Composite EvalConfigs mixing V1 and V2 children

There is no composite EvalConfig type in V1. The `composite` type is deferred post-V2 (A2.4). However, the score contract is compatible: both legacy and V2 `EvalRun`s write `scores: EvalScores` (= `Dict[str, float]`). If composite ships in V2.x, mixed-type scoring (V1 `g_eval` + V2 `exact_match` children) works because the composite adapter reads scores from persisted EvalRuns, not from the child adapters directly.

---

## 11. Implementation sequencing

Ordered by dependency (from `reference/backwards_compat_plan_grounded.md`, reconciled against locked decisions):

1. **EvalConfig schema extension (Phase 0, sub-task 1):** Add `v2` to enum, add V2 properties types, change `model_name`/`model_provider` to optional, add `mode="before"` routing validator (A2.8), extend `validate_properties` (A2.1), guard `validate_json_serializable`.
2. **Eval model extension (Phase 0, sub-task 2):** Add `eval_input_filter_id` (A2.5), make `eval_set_filter_id` optional (A2.9), add mutual-exclusivity validator, fix `validate_template_properties` guard.
3. **EvalRun model extension (Phase 0, sub-task 3):** Add `eval_input_id` (A2.6), `reference_data` (A2.7), `skipped_reason` (E.18). Change `dataset_id` to optional. Add `validate_input_source` validator. Add `validate_output_fields` V2 bypass (C.runner.2).
4. **EvalInput entity (Phase 0, sub-task 4):** New model, add to `Task.parent_of`. No dependencies on sub-tasks 1-3.
5. **EvalInputFilter (Phase 0, sub-task 5):** New protocol + basic filters + registry. Depends on sub-task 4.
6. **Registry + BaseEval helper extraction (Phase 0, sub-task 6):** Change registry signature (A2.11), extract `model_and_provider()` helper (A2.10). Depends on sub-task 1.
7. **Runner extension (Phase 0, sub-task 7):** Add `collect_tasks_for_eval_input` (C.runner.3), extend `EvalJob` for B2.1 runtime translation, wire V2 dispatch. Depends on sub-tasks 5 and 6.
8. **V2 creation paths (Phase 0, sub-task 8):** K.1 manual endpoint V2 internals, K.2 Copilot local translation, K.3 dataset shape wiring.

Sub-tasks 1-4 are independent and can be parallelized. Sub-task 5 depends on 4. Sub-task 6 depends on 1. Sub-task 7 depends on 5 and 6. Sub-task 8 depends on 1.

---

## 12. File-by-file change summary

### `libs/core/kiln_ai/datamodel/eval.py`

| Change | Alignment ref | Phase |
|---|---|---|
| Add `v2` to `EvalConfigType` | A2.1 | 0.1 |
| Add `V2EvalType` enum + V2 properties classes + `V2EvalConfigProperties` union | A2.1 | 0.1 |
| Change `EvalConfig.model_name/model_provider` to `str \| None = None` | A2.1 | 0.1 |
| Change `EvalConfig.properties` type to `V2EvalConfigProperties \| dict \| None` | A2.1 | 0.1 |
| Add `dispatch_properties_parsing` `mode="before"` validator | A2.8 | 0.1 |
| Extend `validate_properties` with V2 branch | A2.1 | 0.1 |
| Guard `validate_json_serializable` for V2 | A2.1 | 0.1 |
| Make `Eval.evaluation_data_type` optional | A2.3 | 0.2 |
| Make `Eval.eval_set_filter_id` optional | A2.9 | 0.2 |
| Add `Eval.eval_input_filter_id` | A2.5 | 0.2 |
| Add `Eval.validate_filter_fields` mutual-exclusivity validator | A2.9 | 0.2 |
| Fix `validate_template_properties` None guard | (pre-existing bug) | 0.2 |
| Change `EvalRun.dataset_id` to optional | A2.6 | 0.3 |
| Add `EvalRun.eval_input_id` | A2.6 | 0.3 |
| Add `EvalRun.reference_data` | A2.7 | 0.3 |
| Add `EvalRun.skipped_reason` | E.18 | 0.3 |
| Add `EvalRun.validate_input_source` XOR validator | A2.6 | 0.3 |
| Extend `EvalRun.validate_output_fields` with V2 bypass | C.runner.2 | 0.3 |

### `libs/core/kiln_ai/datamodel/task.py`

| Change | Alignment ref | Phase |
|---|---|---|
| Add `"eval_inputs": EvalInput` to `Task.parent_of` | A2.5 | 0.4 |

### `libs/core/kiln_ai/datamodel/dataset_filters.py`

| Change | Alignment ref | Phase |
|---|---|---|
| Add `EvalInputFilter` protocol | A2.5 | 0.5 |
| Add `EvalInputFilterId` type | A2.5 | 0.5 |
| Add `eval_input_filter_from_id` registry | A2.5 | 0.5 |
| Add `AllEvalInputFilter`, `TagEvalInputFilter` | A2.5 | 0.5 |

### `libs/core/kiln_ai/adapters/eval/registry.py`

| Change | Alignment ref | Phase |
|---|---|---|
| Change `eval_adapter_from_type` to accept `EvalConfig` | A2.11, C.11b | 0.6 |
| Add `v2_eval_adapter_from_properties_type` dispatch | A2.11, C.11b | Phase 1 |

### `libs/core/kiln_ai/adapters/eval/base_eval.py`

| Change | Alignment ref | Phase |
|---|---|---|
| Extract `model_and_provider()` to helper module | A2.10 | 0.6 |

### `libs/core/kiln_ai/adapters/eval/eval_runner.py`

| Change | Alignment ref | Phase |
|---|---|---|
| Extend `EvalJob` to `item: TaskRun \| EvalInput` + `stored_output` | B2.1 | 0.7 |
| Add `collect_tasks_for_eval_input` method | C.runner.3 | 0.7 |
| Extend `collect_tasks` dispatch for `eval_input_filter_id` | C.runner.3 | 0.7 |
| Add TaskRun-to-EvalInput runtime translation in collectors | B2.1 | 0.7 |
| Extend `__init__` constructor validation for EvalInput source | C.runner.3 | 0.7 |
| Update `run_job` to pass `EvalConfig` to `eval_adapter_from_type` | A2.11 | 0.6 |

### `libs/core/kiln_ai/adapters/eval/g_eval.py`

| Change | Alignment ref | Phase |
|---|---|---|
| **No changes** | D.5 | -- |

### `app/desktop/studio_server/eval_api.py`

| Change | Alignment ref | Phase |
|---|---|---|
| Update `POST /create_eval_config` to construct V2 EvalConfig internally | K.1 | 0.8 |

### `app/desktop/studio_server/copilot_api.py`

| Change | Alignment ref | Phase |
|---|---|---|
| Update V1-to-V2 translation at `copilot_api.py:337-340` | K.2 | 0.8 |

### New files

| File | Purpose | Phase |
|---|---|---|
| `libs/core/kiln_ai/datamodel/eval_input.py` | EvalInput model (may live in `eval.py` or separate) | 0.4 |
| `libs/core/kiln_ai/adapters/eval/v2/` | V2 adapter directory | Phase 1 |
| `libs/core/kiln_ai/adapters/eval/scoring_utils.py` | Extracted pure scoring helpers (H.32a, owned by `components/20`) | Phase 0 |

---

## 13. Cross-references

- **Schema shapes** (V2EvalType enum, V2EvalConfigProperties union, EvalInput model, EvalRun fields): owned by `components/10_data_model.md`. This file describes the coexistence patterns around those shapes, not the shapes themselves.
- **Adapter dispatch architecture** (two-level registry, runner orchestration, TaskRun-to-EvalInput translation detail): `components/45_runner_architecture.md`.
- **Scoring helper extraction** (H.32a): `components/20_eval_config_types_overview.md` and `components/21_type_llm_judge.md`.
- **Template and extraction infrastructure** (D.2/D.3/D.4): `components/40_template_and_extraction.md`.
- **Builder integration** (K.1-K.5): `components/70_builder_and_onboarding.md`.
