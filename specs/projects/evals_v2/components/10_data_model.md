---
status: complete
approved: true
alignment_refs: [A1.1, A1.2, A2.1, A2.3, A2.6, A2.7, A2.8, A2.9, A2.11, C.9, C.runner.2, E.18, K.3]
opens: []
summary: Eval, EvalConfig, EvalInput, EvalRun Pydantic schemas (V2 shape).
---

# Data Model

**Author:** sub-agent dispatched 2026-06-03 for Stage 4 data-model design
**Status:** complete

## TL;DR

- **Eval** gains two optional fields (`eval_input_filter_id`, `evaluation_data_type` made optional) and a mutual-exclusivity validator. `output_scores` and `current_config_id` unchanged (C.9).
- **EvalConfig** gets a `v2` value in `EvalConfigType`, `model_name`/`model_provider` made optional, and `properties` becomes a union of the typed V2 discriminated union, legacy dict, or None. Parsing routed by an explicit `mode="before"` validator (A2.8).
- **EvalInput** is a new `KilnParentedModel` child of `Task`, carrying `tags`, `reference`, and a discriminated `data` field with per-variant input naming (A1.1).
- **EvalRun** gains `eval_input_id`, `reference_data`, and `skipped_reason` as additive optional fields. Legacy fields untouched (A2.6, A2.7, E.18).
- **V2EvalConfigProperties** is a discriminated union on inner `type` field, hosting 7 V2.0 EvalConfigType properties classes plus `code_eval` (Phase 5).
- V1/V2 read-coexistence patterns (parsing routing, validator bypass behavior, filter coexistence) are owned by `components/15_v1_v2_coexistence.md`. This file defines the schema shapes; `components/15` defines how they coexist at parse/load time.

---

## 1. Eval

Alignment refs: **A2.3** (evaluation_data_type per-config), **A2.9** (eval_set_filter_id optional + mutual exclusivity), **C.9** (1:1 cardinality preserved).

```python
class Eval(KilnParentedModel, KilnParentModel, parent_of={"configs": EvalConfig}):
    name: FilenameString
    description: str | None = None
    template: EvalTemplateId | None = None
    current_config_id: ID_TYPE = None
    output_scores: list[EvalOutputScore]          # at least one required (unchanged)
    favourite: bool = False
    template_properties: dict[str, str | int | bool | float] | None = None

    # --- V1 filter fields (TaskRun-typed) ---
    # CHANGED: optional in V2 definition (was required in V1).
    eval_set_filter_id: DatasetFilterId | None = Field(default=None)
    eval_configs_filter_id: DatasetFilterId | None = None
    train_set_filter_id: DatasetFilterId | None = None

    # --- V2 filter field (EvalInput-typed) ---
    # NEW per A2.5/A2.9.
    eval_input_filter_id: EvalInputFilterId | None = Field(default=None)

    # --- Legacy evaluation_data_type ---
    # CHANGED per A2.3: optional in V2 definition.
    # V1 EvalConfigs (g_eval, llm_as_judge) read this from the grandparent
    # Eval. V2 EvalConfigs declare their data needs in their own properties
    # and set this to None.
    evaluation_data_type: EvalDataType | None = None

    @model_validator(mode="after")
    def validate_filter_fields(self) -> Self:
        """A2.9: exactly one of eval_set_filter_id / eval_input_filter_id."""
        if (self.eval_set_filter_id is None) == (self.eval_input_filter_id is None):
            raise ValueError(
                "Exactly one of eval_set_filter_id or eval_input_filter_id must be set"
            )
        return self
```

### 1.1 Cardinality (C.9)

V2 preserves V1's cardinality model unchanged:

- **Semantic 1:1.** One Eval has one operative EvalConfig pointed to by `current_config_id`. Normal eval runs invoke only this config.
- **N on disk for calibration.** Non-current EvalConfigs are calibration candidates. `eval_config_eval` mode can score all candidates against a golden subset.
- **Multi-signal = `output_scores` within one config**, not multi-config. Different scoring approaches = different Evals.
- **Candidate type constraint:** different `V2EvalType`s allowed under one Eval (e.g. `pattern_match` alongside `llm_judge`) as long as produced scores conform to `Eval.output_scores`.

### 1.2 `EvalOutputScore` (unchanged)

```python
class EvalOutputScore(BaseModel):
    name: FilenameStringShort   # max 32 chars
    instruction: str | None = None
    type: TaskOutputRatingType  # five_star | pass_fail | pass_fail_critical
```

`json_key()` converts `name` to snake_case for use as `EvalRun.scores` dict keys. Custom rating types remain explicitly forbidden.

---

## 2. EvalConfig

Alignment refs: **A2.1** (V2 shape + coexistence), **A2.3** (per-config data needs), **A2.8** (explicit parsing routing), **A2.11** (adapter registry takes full EvalConfig), **C.9** (cardinality), **C.runner.2** (validator bypass), **K.3** (V2-only creation).

### 2.1 Schema

```python
class EvalConfigType(str, Enum):
    # Legacy -- kept forever for V1 files on disk (A0.1).
    g_eval = "g_eval"
    llm_as_judge = "llm_as_judge"
    # V2 marker. Inner properties.type carries the actual V2 type.
    v2 = "v2"


class EvalConfig(KilnParentedModel, KilnParentModel, parent_of={"runs": EvalRun}):
    name: FilenameString
    description: str | None = None
    config_type: EvalConfigType = EvalConfigType.g_eval

    # CHANGED: optional for V2 configs; V1 files always have these set.
    # V2 LLM types carry model fields in their own properties (A2.10).
    model_name: str | None = None
    model_provider: str | None = None

    # Properties shape depends on config_type:
    #   legacy (g_eval / llm_as_judge): untyped dict, as V1 stored it
    #   v2: typed discriminated union (inner `type` is the discriminator)
    properties: V2EvalConfigProperties | dict[str, Any] | None = None
```

### 2.2 Parsing routing (A2.8)

An explicit `model_validator(mode="before")` on EvalConfig reads `config_type` and routes parsing of `properties`. This avoids reliance on Pydantic's implicit union fallback ordering, which could mis-parse a legacy dict containing a `type` key.

```python
@model_validator(mode="before")
@classmethod
def dispatch_properties_parsing(cls, data: dict, info: ValidationInfo) -> dict:
    if not isinstance(data, dict):
        return data
    config_type = data.get("config_type", "g_eval")
    if config_type == "v2":
        # Let V2EvalConfigProperties discriminated union handle parsing
        pass
    else:
        # Legacy -- ensure properties stays as raw dict (no V2 union attempt)
        props = data.get("properties")
        if props is not None and isinstance(props, dict):
            # Wrap in a way that prevents Pydantic from trying the
            # V2 discriminated union first. Implementation: force the
            # field type annotation to dict for this parse pass.
            pass
    return data
```

Full routing implementation detail (how to prevent Pydantic from attempting V2 union parse on legacy dicts) is owned by `components/15_v1_v2_coexistence.md`.

### 2.3 Shape validation (A2.1)

```python
@model_validator(mode="after")
def validate_shape(self) -> Self:
    if self.config_type == EvalConfigType.v2:
        if not isinstance(self.properties, BaseModel):
            raise ValueError("v2 config requires typed properties")
        if self.model_name is not None or self.model_provider is not None:
            raise ValueError("V2 configs must not set root-level model_name/model_provider")
    else:
        # Legacy validation unchanged
        if self.model_name is None or self.model_provider is None:
            raise ValueError("model_name and model_provider required for legacy configs")
        if not isinstance(self.properties, dict):
            raise ValueError("Legacy config properties must be a dict")
    return self
```

The existing `validate_properties` (eval.py:290-308) and `validate_json_serializable` (eval.py:310-317) validators are extended with a V2 bypass. Detail in `components/15`.

### 2.4 V2-only creation (K.3)

After this project ships, the spec_builder and manual eval config UI produce **only V2 EvalConfigs** (`config_type="v2"`). `EvalConfigType.g_eval` and `EvalConfigType.llm_as_judge` remain in the enum to read existing V1 records on disk, but no new V1 records are created via any flow.

### 2.5 Adapter registry signature (A2.11)

`eval_adapter_from_type` changes from taking `EvalConfigType` (enum) to taking the full `EvalConfig` object. One internal call site (`eval_runner.py:204`). V2 dispatch reads `properties.type` to pick the V2 adapter. Two-level dispatch detail in `components/20_eval_config_types_overview.md` and `components/45_runner_architecture.md`.

---

## 3. V2EvalType and V2EvalConfigProperties

Alignment refs: **A2.1** (discriminated union shape), **A2.11** (adapter dispatch keyed on V2EvalType).

### 3.1 V2EvalType enum

```python
class V2EvalType(str, Enum):
    """V2-only type enum. Grows with new V2 types. Plugin extensibility
    (E.36) adds to this enum in V2.x."""
    llm_judge = "llm_judge"
    exact_match = "exact_match"
    pattern_match = "pattern_match"
    set_check = "set_check"
    tool_call_check = "tool_call_check"
    contains = "contains"
    step_count_check = "step_count_check"
    code_eval = "code_eval"            # Phase 5 (B.12)
```

7 V2.0 launch types + `code_eval` (Phase 5). `composite`, `threshold`, `json_schema`, `event_ordering`, `embedding_similarity`, `dag_metric` are deferred post-V2 per A2.4.

### 3.2 V2EvalConfigProperties discriminated union

```python
V2EvalConfigProperties = Annotated[
    Union[
        LlmJudgeProperties,
        ExactMatchProperties,
        PatternMatchProperties,
        SetCheckProperties,
        ToolCallCheckProperties,
        ContainsProperties,
        StepCountCheckProperties,
        CodeEvalProperties,          # Phase 5
    ],
    Discriminator("type"),
]
```

Discriminator is the inner `type` field on each properties class (standard Pydantic v2 `Annotated[Union[...], Discriminator("type")]` pattern, works on Python 3.10+ with Pydantic v2).

### 3.3 Per-type properties classes (canonical shapes)

Per-type properties are defined here for schema completeness. Behavioral detail for each type lives in its own design file (`components/21`, `components/22`, `components/27`). Template/extraction infrastructure (`prompt_template`, `value_expression`, `required_var`) is defined in `components/40_template_and_extraction.md`.

#### LlmJudgeProperties

```python
class LlmJudgeProperties(BaseModel):
    type: Literal[V2EvalType.llm_judge] = V2EvalType.llm_judge
    model_name: str
    model_provider: str
    system_prompt: str | None = None
    prompt_template: str                    # Jinja2 template; REQUIRED
    required_var: list[str] = []            # Jinja2 expressions pre-checked
    thinking_instruction: str | None = None
    g_eval: bool = False                    # G-Eval token-logprob mode
```

`model_name`/`model_provider` on LlmJudgeProperties (not root EvalConfig) per A2.10. `g_eval` (renamed from `g_eval_mode` per A2.2 field-name note) toggles scoring mode. Full judge design in `components/21_type_llm_judge.md`.

#### ExactMatchProperties

```python
class ExactMatchProperties(BaseModel):
    type: Literal[V2EvalType.exact_match] = V2EvalType.exact_match
    value_expression: str | None = None     # Jinja2 expression; None = whole final_message
    expected_value: str | None = None       # literal comparison target
    reference_key: str | None = None        # OR pull from reference_data[reference_key]
    # Validator: exactly one of expected_value / reference_key required
```

> **Note:** `components/22_type_deterministic_basics.md` is authoritative for the full per-type fields (e.g. `case_sensitive` on `exact_match`, `case_sensitive` and `mode` on `contains`). This file shows the core schema shape; see `components/22` for the complete properties.

#### PatternMatchProperties

```python
class PatternMatchProperties(BaseModel):
    type: Literal[V2EvalType.pattern_match] = V2EvalType.pattern_match
    value_expression: str | None = None
    pattern: str                            # regex
    mode: Literal["must_match", "must_not_match"] = "must_match"
```

#### ContainsProperties

```python
class ContainsProperties(BaseModel):
    type: Literal[V2EvalType.contains] = V2EvalType.contains
    value_expression: str | None = None
    substring: str | None = None
    reference_key: str | None = None
    # Validator: exactly one of substring / reference_key required
```

#### SetCheckProperties

```python
class SetCheckProperties(BaseModel):
    type: Literal[V2EvalType.set_check] = V2EvalType.set_check
    value_expression: str | None = None
    expected_set: list[str] | None = None
    reference_key: str | None = None
    mode: Literal["subset", "superset", "equal"] = "subset"
    # Validator: exactly one of expected_set / reference_key required
```

#### ToolCallCheckProperties (J.37)

```python
class ArgMatch(BaseModel):
    value: JsonValue
    match_mode: Literal["exact", "contains", "regex"] = "exact"

class ToolCallSpec(BaseModel):
    tool_name: str
    expected_args: dict[str, ArgMatch] | None = None  # None = ignore args

class ToolCallCheckProperties(BaseModel):
    type: Literal[V2EvalType.tool_call_check] = V2EvalType.tool_call_check
    expected_tools: list[ToolCallSpec]
    match_mode: Literal["any", "all", "ordered", "never"] = "all"
    on_unexpected_tools: Literal["ignore", "fail"] = "ignore"
```

Does not use `value_expression` or `extract()`. Walks the trace internally.

#### StepCountCheckProperties (J.38)

```python
class StepCountCheckProperties(BaseModel):
    type: Literal[V2EvalType.step_count_check] = V2EvalType.step_count_check
    count_type: Literal["tool_calls", "model_responses", "turns"]
    min_count: int | None = None
    max_count: int | None = None

    @model_validator(mode="after")
    def check_bounds(self) -> Self:
        if self.min_count is None and self.max_count is None:
            raise ValueError("step_count_check requires at least one of min_count / max_count")
        if (self.min_count is not None and self.max_count is not None
                and self.min_count > self.max_count):
            raise ValueError("min_count must be <= max_count")
        return self
```

Does not use `value_expression` or `extract()`. Walks the trace internally.

#### CodeEvalProperties (Phase 5)

```python
class CodeEvalProperties(BaseModel):
    type: Literal[V2EvalType.code_eval] = V2EvalType.code_eval
    code: str                               # user Python source (a `def score(...)` definition)
    # Full properties shape (helper-library surface, scorer contract,
    # timeout / resource limits) specified in components/27_type_code_eval.md.
```

Gated by Phase 5 (B.12/B.13). Execution model is `multiprocessing` (spawn) + `freeze_support()` per B.13. Full properties shape owned by `components/27_type_code_eval.md`.

---

## 4. EvalInput

Alignment refs: **A1.1** (field placement + per-variant naming), **A1.2** (reference shape), **K.3** (EvalInput as V2 eval dataset entity).

### 4.1 Schema

```python
class EvalInput(KilnParentedModel):
    """V2 eval dataset item. Child of Task, sibling of TaskRun.
    
    EvalInput is self-contained -- carries all data needed for an eval run
    (input + reference). Runs don't live-read from upstream sources.
    """
    tags: list[str] = []
    reference: dict[str, JsonValue] | None = None
    data: EvalInputData                     # discriminated union

    # NOTE: source_task_run_id is NOT included in V2.
    # Deferred to the future Feedback Pipeline project (Batch F punted
    # 2026-06-03). Will be added additively by that project.
```

Registered as a child of `Task`:

```python
class Task(KilnParentedModel, KilnParentModel, parent_of={
    # ... existing children ...
    "eval_inputs": EvalInput,               # NEW
}):
```

V1 invisibility is guaranteed: V1's `Task` has no `"eval_inputs"` in its `parent_of` dict, so `iterate_children_paths_of_parent_path` (basemodel.py:628-662) never scans the `eval_inputs/` folder.

### 4.2 File structure on disk

```
task_dir/
  task.kiln
  runs/            # TaskRun children (existing)
  eval_inputs/     # EvalInput children (NEW)
    {id} - {name}/
      eval_input.kiln
  evals/           # Eval children (existing)
```

### 4.3 `EvalInputData` discriminated union (A1.1)

```python
EvalInputData = Annotated[
    Union[
        SingleTurnEvalInputData,
        MultiTurnSyntheticEvalInputData,
        # Future variants: ImageGenEvalInputData, ClassifierEvalInputData, etc.
    ],
    Discriminator("type"),
]
```

Each variant names and types its input field semantically. There is no shared `ContentProperties` abstraction -- that concept is dropped per A1.1. Modality extensibility happens through new variants or by extending `UserMessage` with attachments.

#### SingleTurnEvalInputData

```python
class UserMessage(BaseModel):
    text: str
    # Future: attachments, images-in-chat, etc.

class SingleTurnEvalInputData(BaseModel):
    type: Literal["single_turn"] = "single_turn"
    user_message: UserMessage
```

Nearly empty for V2.0 -- that is fine. It is a typed slot for future single-turn-only fields and preserves the discriminator tag.

#### MultiTurnSyntheticEvalInputData

```python
class MultiTurnSyntheticEvalInputData(BaseModel):
    type: Literal["multi_turn_synthetic"] = "multi_turn_synthetic"
    first_message: UserMessage | None = None
    synthetic_user_info: SyntheticUserInfo
```

`first_message` is optional. UI always sets this on eval creation; power users may leave it `None` for purely synthetic conversations where the synthetic user generates turn 1 from persona/goal/policy. When set, the synthetic user takes over from turn 2.

`SyntheticUserInfo` is a typed Pydantic model (not a flat dict). Its field list is owned by the parallel multi-turn-synthetic project (C.5). The model carries an explicit version field or equivalent discriminator for forward evolution.

### 4.4 `reference` shape (A1.2)

```python
reference: dict[str, JsonValue] | None = None
```

- Flat dict at the top level of EvalInput (universal across all turn types).
- `JsonValue` from Pydantic v2: `None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]`.
- Root must be a dict or None. Top-level non-dict values (array, string, bool) are rejected.
- No EvalInput-creation-time validation of reference shape -- validation happens at config-bind time. Each `V2EvalType` declares the reference keys it consumes. Runner checks this contract at the start of each (input x config) job. Missing keys = skip; mismatched types = skip (C.runner.1).
- Naming guidelines for reference keys: prefer EvalConfigType-prefixed names (`llm_as_judge_criteria`, `exact_match_expected`) to avoid collisions when multiple configs consume the same EvalInput. Detail in `components/50_reference_data.md`.

### 4.5 Per-case criteria (A1.4 -- no separate field)

No `criteria` field on EvalInput. Per-case variation is expressed through reference data parameters that EvalConfigs opt to consume. For example, per-case judge criteria are stored as `reference["llm_as_judge_criteria"]: list[str]`, consumed by an enhanced `llm_judge` EvalConfigType. Global checks ("the 12 things this eval cares about") live on EvalConfig properties.

---

## 5. EvalRun

Alignment refs: **A2.6** (eval_input_id as orthogonal source field), **A2.7** (reference_data additive field), **C.runner.2** (validate_output_fields V2 bypass), **E.18** (skipped_reason).

### 5.1 Schema

```python
class EvalRun(KilnParentedModel):
    # --- Existing V1 fields (unchanged) ---
    dataset_id: ID_TYPE | None = None       # CHANGED: optional (was required). V1 TaskRun source.
    task_run_config_id: ID_TYPE | None = None
    eval_config_eval: bool = False           # UNCHANGED -- what's being evaluated
    input: str
    output: str | None = None                # CHANGED: optional for skipped-before-execution runs (E.18). None when skipped_reason set; non-None otherwise.
    reference_answer: str | None = None      # UNCHANGED -- V1 snapshot
    intermediate_outputs: dict[str, str] | None = None
    task_run_trace: str | None = None
    scores: EvalScores                       # Dict[str, float]
    task_run_usage: Usage | None = None

    # --- V2 additive fields ---
    eval_input_id: ID_TYPE | None = None     # NEW per A2.6 -- V2 EvalInput source
    reference_data: dict[str, JsonValue] | None = None   # NEW per A2.7
    skipped_reason: str | None = None                      # NEW per E.18
    # Stored as str for back/forward-compat; set by convention to a SkippedReason value; unknown values tolerated on load.
    skipped_detail: str | None = None                    # NEW per E.18 -- case-specific detail (key name, expression, type)
```

### 5.2 Input source fields (A2.6)

`dataset_id` (V1 TaskRun source) XOR `eval_input_id` (V2 EvalInput source). Exactly one must be set per run.

```python
@model_validator(mode="after")
def validate_input_source(self) -> Self:
    # Skipped runs still record which input they were skipped for.
    if (self.dataset_id is None) == (self.eval_input_id is None):
        raise ValueError("Exactly one of dataset_id or eval_input_id must be set")
    return self
```

`eval_config_eval` remains orthogonal -- it indicates what is being evaluated (run_config vs eval_config), not where the input came from. The two dimensions are independent per the coverage matrix in A2.6.

**B2.1 interaction:** When a V2 EvalConfig consumes V1 TaskRun-source data via runtime translation, `EvalRun.dataset_id` points at the source TaskRun (not `eval_input_id`). The synthesized in-memory EvalInput is not persisted. This preserves the correlation API pairing (TaskRun rating, EvalRun judge scores).

### 5.3 Reference data (A2.7)

V2 EvalRuns store structured reference data in `reference_data: dict[str, JsonValue] | None`. This is sourced from `EvalInput.reference` at run time by the V2 runner. The legacy `reference_answer: str | None` field is untouched -- V1 EvalRuns continue to use it. The existing `validate_reference_answer` validator stays as-is (gates only `reference_answer`, never `reference_data`).

### 5.4 Skip persistence (E.18)

```python
class SkippedReason(str, Enum):
    """Terminal skip reasons -- convention enum. Canonical definition in
    components/85_observability_and_audit.md section 2.2; mirrored here for schema completeness.
    Stored as str for back/forward-compat; set by convention to a SkippedReason value;
    unknown values tolerated on load."""
    missing_reference_key = "missing_reference_key"
    extraction_failed = "extraction_failed"
    missing_trace = "missing_trace"
    incompatible_input_shape = "incompatible_input_shape"
    code_eval_not_trusted = "code_eval_not_trusted"
    type_not_available = "type_not_available"
```

Skipped EvalRuns are a terminal state:

- `skipped_reason: str | None` is the category; `skipped_detail: str | None` carries the case-specific information (the missing key name, the failed expression, the unavailable type, etc.). The reason is for stable rollups and grouping; the detail is for human inspection. See `components/85` section 2.3 for per-value `skipped_detail` conventions.
- Counted toward `percent_complete`.
- Excluded from score means.
- Carry no scores (or empty scores). The `validate_scores` validator (eval.py:181-237) must be extended: when `skipped_reason is not None`, allow empty/None scores.
- May carry no output. `output` is `str | None = None` (Stage 5 pick, 2026-06-05) so a skipped-before-execution run persists `None` rather than a sentinel. Matches `components/45` `_persist_skipped_run` (`output=None`). Non-skipped runs always set a non-None output.

Transient failures are NOT persisted -- they surface to UI ephemerally. DB-level absence ("incomplete") remains the signal for retry-able / not-yet-run cases.

### 5.5 `validate_output_fields` V2 bypass (C.runner.2)

The existing validator at `eval.py:146-166` reads `evaluation_data_type` from the grandparent Eval to gate `task_run_trace`/`reference_answer` presence. For V2 EvalRuns, this gate is meaningless (data contract moved to per-config properties per A2.3).

```python
@model_validator(mode="after")
def validate_output_fields(self) -> Self:
    eval_config = self.parent_eval_config()
    if eval_config and eval_config.config_type == EvalConfigType.v2:
        return self  # V2: per-config properties drive data contract
    # ... existing V1 logic unchanged ...
    return self
```

### 5.6 On-read aggregation rules (E.18)

No persisted aggregate entity. Aggregation stays on-read in `eval_api.py`:

- `n_used` = EvalRuns with all expected score keys populated AND `skipped_reason is None`.
- `n_excluded` = EvalRuns with `skipped_reason is not None`.
- `percent_complete = (n_used + n_excluded) / dataset_size`.
- Score means computed only over `n_used` EvalRuns.

API response shapes (`ScoreSummary` / `EvalResultSummary`) gain `n_used: int` and `n_excluded: int` per `(run_config_id x score_key)`.

---

## 6. Schema relationships and file layout

### 6.1 Parent-child hierarchy

```
Task (task.kiln)
  |-- runs/ (TaskRun)             # V1 dataset items
  |-- eval_inputs/ (EvalInput)    # V2 dataset items (NEW)
  |-- evals/ (Eval)
  |     |-- configs/ (EvalConfig)
  |     |     |-- runs/ (EvalRun)
```

### 6.2 Cross-entity references

| Field | On | Points to | Type |
|---|---|---|---|
| `current_config_id` | Eval | EvalConfig.id | ID_TYPE |
| `eval_set_filter_id` | Eval | DatasetFilter registry | DatasetFilterId (string) |
| `eval_input_filter_id` | Eval | EvalInputFilter registry | EvalInputFilterId (string) |
| `eval_configs_filter_id` | Eval | DatasetFilter registry (golden subset) | DatasetFilterId (string) |
| `dataset_id` | EvalRun | TaskRun.id | ID_TYPE |
| `eval_input_id` | EvalRun | EvalInput.id | ID_TYPE |
| `task_run_config_id` | EvalRun | TaskRunConfig.id | ID_TYPE |

### 6.3 V1 invisibility

EvalInput is invisible to V1 clients:
- V1's `Task` has no `"eval_inputs"` in `parent_of`, so `iterate_children_paths_of_parent_path` never scans `eval_inputs/`.
- `KilnBaseModel` uses Pydantic v2 default `extra = "ignore"` (no override anywhere). V2 additive fields on Eval/EvalConfig/EvalRun are silently dropped by V1.
- New `EvalConfigType.v2` raises in V1 (verified: enum raise + explicit `else: raise ValueError` in V1 `validate_properties`). V1 cannot load V2 EvalConfigs. Acceptable per A0.1.

---

## 7. Alignment-ref coverage index

Each alignment ref mapped to where its schema impact is specified above.

| Ref | Decision summary | Section(s) |
|---|---|---|
| A1.1 | EvalInput field placement + per-variant naming | 4.1, 4.3 |
| A1.2 | `reference` shape (flat dict, JsonValue) | 4.4 |
| A2.1 | EvalConfig V2 shape (discriminated union) | 2.1, 2.3, 3.1, 3.2 |
| A2.3 | `evaluation_data_type` per-config; Eval field optional | 1 (`evaluation_data_type`), 5.5 |
| A2.6 | EvalRun `eval_input_id` orthogonal source | 5.1, 5.2 |
| A2.7 | EvalRun `reference_data` additive field | 5.1, 5.3 |
| A2.8 | EvalConfig properties parsing routing | 2.2 |
| A2.9 | `eval_set_filter_id` optional + mutual exclusivity | 1 (`validate_filter_fields`) |
| A2.11 | Adapter registry signature change | 2.5 |
| C.9 | Eval-EvalConfig 1:1 cardinality preserved | 1.1 |
| C.runner.2 | `validate_output_fields` V2 bypass | 5.5 |
| E.18 | `skipped_reason` enum on EvalRun | 5.1, 5.4, 5.6 |
| K.3 | V2-only EvalConfig creation | 2.4 |

---

## Opens

None. All alignment refs covered with no unresolved design questions at the schema level. Implementation-level details (exact `SkippedReason` enum seed values, `output` field handling for skipped runs) are delegated to `components/45_runner_architecture.md` per E.18's explicit "punted to Stage 5" note, and are not schema-design opens.
