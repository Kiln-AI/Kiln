---
status: complete
---

# Phase 2: V2 Eval Engine -- Adapter Contract, Dispatch Scaffolding, and Runner Widening

## Overview

Phase 1 laid the additive schema foundation (V2 types, EvalInput, SkippedReason, EvalRun V2 fields). Phase 2 builds the runtime backbone: the `BaseV2Eval` adapter contract, two-level dispatch scaffolding (with an initially empty `_V2_ADAPTER_MAP`), EvalRunner widening for EvalInput sources, skip-check infrastructure, shared extraction/reference helpers, scoring_utils extraction, B2.1 translation, and on-read aggregation counters.

All concrete V2 adapter implementations (exact_match, pattern_match, contains, set_check, tool_call_check, step_count_check) are Phase 3. LLM-backed V2 adapters (llm_judge) and code_eval are also Phase 3+. Phase 2 delivers only the contract and plumbing that Phase 3 adapters will plug into.

### Key Concepts

- **EvalTaskInput**: A new Pydantic model assembled per-case from EvalInput + TaskRun data. Provides a flat namespace (`final_message`, `trace`, `reference_data`, `task_input`) for Jinja template rendering and value extraction. This is the universal input shape for all V2 adapters.
- **Two-level dispatch**: Outer dispatch on `EvalConfig.config_type` (g_eval/llm_as_judge -> GEval; v2 -> inner dispatch). Inner dispatch reads `properties.type` from a `_V2_ADAPTER_MAP` dict.
- **Skip-with-reason**: Before executing a V2 adapter, pre-checks verify that required data is present (e.g. reference keys exist, value_expression extracts successfully, trace is available). When a check fails, the run is saved with `skipped_reason`/`skipped_detail` and empty scores.
- **EvalJob widening**: The `item` field widens from `TaskRun` to `TaskRun | EvalInput`. New optional fields `stored_output` and `stored_trace` carry pre-fetched data for EvalInput-sourced jobs.
- **B2.1 translation**: When a V2 EvalConfig consumes TaskRun sources (backward compat), `_translate_task_run_to_eval_task_input` maps the TaskRun into an EvalTaskInput.

## Steps

### Step 1: EvalTaskInput model (`libs/core/kiln_ai/datamodel/eval.py`)

Add a new Pydantic BaseModel after the EvalInput class (around line 254):

```python
class EvalTaskInput(BaseModel):
    """The universal input namespace for V2 eval adapters.

    Assembled per-case from EvalInput + TaskRun data. Template variables
    and value_expression targets resolve against these fields.
    """
    final_message: str = Field(
        description="The final model output (task output text).",
    )
    trace: list[dict[str, Any]] | None = Field(
        default=None,
        description="The full conversation trace, if available.",
    )
    reference_data: dict[str, JsonValue] | None = Field(
        default=None,
        description="Reference/ground-truth data from EvalInput.reference.",
    )
    task_input: str | None = Field(
        default=None,
        description="The original task input text.",
    )
```

No validators needed -- this is a pure data container.

### Step 2: Save-time validation on EvalConfig (`libs/core/kiln_ai/datamodel/eval.py`)

Add a new `validate_v2_templates_and_expressions` model_validator to `EvalConfig`, after the existing `validate_properties` (around line 565). This runs only when `config_type == v2` and `properties` is a BaseModel. It validates Jinja syntax at save time:

```python
@model_validator(mode="after")
def validate_v2_templates_and_expressions(self) -> Self:
    if self.config_type != EvalConfigType.v2 or not isinstance(self.properties, BaseModel):
        return self
    from kiln_ai.utils.jinja_engine import (
        compile_expression_or_raise,
        compile_template_or_raise,
    )
    props = self.properties
    # Validate prompt_template on LlmJudgeProperties
    if hasattr(props, "prompt_template"):
        compile_template_or_raise(props.prompt_template)
        # Reject useless templates (pure literal with no variable references)
        tmpl_source = props.prompt_template.strip()
        if "{{" not in tmpl_source and "{%" not in tmpl_source:
            raise ValueError(
                "prompt_template contains no Jinja2 expressions or blocks -- "
                "it would produce the same output for every input. "
                "Use {{ final_message }} or similar."
            )
    # Validate value_expression
    if hasattr(props, "value_expression") and props.value_expression is not None:
        compile_expression_or_raise(props.value_expression)
    # Validate required_var list entries
    if hasattr(props, "required_var"):
        for var in props.required_var:
            compile_expression_or_raise(var)
    return self
```

### Step 3: Base V2 adapter class (`libs/core/kiln_ai/adapters/eval/base_v2_eval.py` -- new file)

Create a new base class for all V2 deterministic adapters. This avoids touching the existing `BaseEval` class, which is tightly coupled to LLM invocation.

```python
from abc import ABC, abstractmethod
from kiln_ai.datamodel.eval import (
    EvalConfig,
    EvalScores,
    EvalTaskInput,
    SkippedReason,
    V2EvalConfigProperties,
)

class BaseV2Eval(ABC):
    """Base class for V2 eval adapters (deterministic, no LLM call)."""

    def __init__(self, eval_config: EvalConfig) -> None:
        if not isinstance(eval_config.properties, V2EvalConfigProperties):
            raise ValueError("V2 eval requires typed V2 properties")
        self.eval_config = eval_config
        self.properties = eval_config.properties

    @abstractmethod
    def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]:
        """Run the eval on the given input.

        Returns:
            (scores, skipped_reason, skipped_detail).
            If skipped_reason is set, scores should be {}.
        """
        ...
```

Note: `V2EvalConfigProperties` is the discriminated union type -- the type annotation works for isinstance checks because the actual value will be one of the concrete properties classes.

### Step 4: Extraction helpers (`libs/core/kiln_ai/adapters/eval/eval_utils/v2_eval_helpers.py` -- new file)

Shared helpers used by multiple deterministic adapters:

```python
from kiln_ai.datamodel.eval import EvalTaskInput, SkippedReason
from kiln_ai.utils.jinja_engine import extract
from jinja2 import Undefined

def extract_value(
    expression: str | None,
    eval_input: EvalTaskInput,
) -> tuple[Any, SkippedReason | None, str | None]:
    """Extract a value from eval_input using a Jinja2 expression.

    If expression is None, defaults to eval_input.final_message.
    Returns (value, skip_reason, skip_detail).
    """
    if expression is None:
        return eval_input.final_message, None, None
    data = eval_input.model_dump()
    result = extract(expression, data)
    if isinstance(result, Undefined):
        return None, SkippedReason.extraction_failed, f"Expression '{expression}' resolved to undefined"
    return result, None, None


def check_reference_key(
    reference_key: str,
    eval_input: EvalTaskInput,
) -> tuple[Any, SkippedReason | None, str | None]:
    """Look up a key in eval_input.reference_data.

    Returns (value, skip_reason, skip_detail).
    """
    if eval_input.reference_data is None:
        return None, SkippedReason.missing_reference_key, f"No reference_data; need key '{reference_key}'"
    if reference_key not in eval_input.reference_data:
        return None, SkippedReason.missing_reference_key, f"reference_data missing key '{reference_key}'"
    return eval_input.reference_data[reference_key], None, None


def check_required_vars(
    required_vars: list[str],
    eval_input: EvalTaskInput,
) -> tuple[SkippedReason | None, str | None]:
    """Check that all required_var expressions resolve to non-Undefined values."""
    data = eval_input.model_dump()
    for var_expr in required_vars:
        result = extract(var_expr, data)
        if isinstance(result, Undefined):
            return SkippedReason.extraction_failed, f"required_var '{var_expr}' resolved to undefined"
    return None, None
```

### Step 5: Two-level adapter dispatch scaffolding (`libs/core/kiln_ai/adapters/eval/registry.py`)

Build the two-level dispatch mechanism with an initially EMPTY `_V2_ADAPTER_MAP`. Phase 3 will register concrete adapters into this map. The `type_not_available` skip path is the expected runtime behavior when a V2 type has no registered adapter.

```python
from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.base_v2_eval import BaseV2Eval
from kiln_ai.adapters.eval.g_eval import GEval
from kiln_ai.datamodel.eval import EvalConfig, EvalConfigType, V2EvalType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error

# Phase 2: empty map. Phase 3 will register concrete adapters here.
_V2_ADAPTER_MAP: dict[V2EvalType, type[BaseV2Eval]] = {}


def eval_adapter_from_type(eval_config: EvalConfig) -> type[BaseEval]:
    """Legacy dispatch -- returns a BaseEval subclass for g_eval/llm_as_judge.
    For v2, raises NotImplementedError (v2 adapters use v2_eval_adapter_from_config)."""
    match eval_config.config_type:
        case EvalConfigType.g_eval:
            return GEval
        case EvalConfigType.llm_as_judge:
            return GEval
        case EvalConfigType.v2:
            raise NotImplementedError(
                "V2 eval configs use v2_eval_adapter_from_config(), not eval_adapter_from_type()"
            )
        case _:
            raise_exhaustive_enum_error(eval_config.config_type)


def v2_eval_adapter_from_config(eval_config: EvalConfig) -> BaseV2Eval:
    """V2 dispatch -- reads properties.type and looks up the adapter in _V2_ADAPTER_MAP.

    Returns an instantiated adapter, or raises NotImplementedError if the
    V2 type has no registered adapter (type_not_available skip path).
    """
    if eval_config.config_type != EvalConfigType.v2:
        raise ValueError("v2_eval_adapter_from_config only accepts V2 configs")
    from pydantic import BaseModel
    if not isinstance(eval_config.properties, BaseModel):
        raise ValueError("V2 config must have typed properties")
    v2_type = eval_config.properties.type
    adapter_cls = _V2_ADAPTER_MAP.get(v2_type)
    if adapter_cls is None:
        raise NotImplementedError(f"V2 eval type '{v2_type}' is not yet implemented")
    return adapter_cls(eval_config)
```

The existing `eval_adapter_from_type` signature stays the same for backward compat. The new `v2_eval_adapter_from_config` is called from `run_job` for V2 configs. In Phase 2, all V2 types will hit the `NotImplementedError` path (empty map), which the runner translates to a `SkippedReason.type_not_available` skip record.

### Step 6: EvalJob widening (`libs/core/kiln_ai/adapters/eval/eval_runner.py`)

Update the `EvalJob` dataclass (line 23). The `type` Literal keeps the existing two values unchanged (no new `eval_run_type` values per component 45). Source mode (TaskRun vs EvalInput) is derived from `eval.eval_input_filter_id`, not from the job type.

```python
@dataclass
class EvalJob:
    item: TaskRun | EvalInput
    type: Literal["task_run_eval", "eval_config_eval"]
    eval_config: EvalConfig
    task_run_config: TaskRunConfig | None = None
    # Pre-fetched data for EvalInput-sourced jobs (set during collect_tasks)
    stored_output: str | None = None
    stored_trace: list[dict[str, Any]] | None = None
```

Add `EvalInput` to imports at top of file:

```python
from kiln_ai.datamodel.eval import EvalConfig, EvalDataType, EvalInput, EvalRun, EvalScores, EvalTaskInput
```

Also import:
```python
from kiln_ai.datamodel.dataset_filters import DatasetFilterId, EvalInputFilterId, dataset_filter_from_id, eval_input_filter_from_id
```

### Step 7: EvalRunner.__init__ source-mode detection (`libs/core/kiln_ai/adapters/eval/eval_runner.py`)

Extend `__init__` (starting at line 41) to detect source mode. After the existing `run_configs` validation block (around line 78), add source-mode detection. No new `eval_run_type` values are introduced -- source mode is orthogonal to run type (component 45):

```python
# Determine source mode from the eval's filter fields (orthogonal to eval_run_type)
self._source_mode: Literal["task_run", "eval_input"] = "task_run"
if target_eval.eval_input_filter_id is not None:
    self._source_mode = "eval_input"
    if eval_run_type == "task_run_eval":
        raise ValueError(
            "task_run_eval mode is not compatible with eval_input_filter_id"
        )
```

The `eval_run_type` parameter continues to accept only `"eval_config_eval"` and `"task_run_eval"`. Source mode is derived from `eval.eval_input_filter_id`, keeping run type and input source orthogonal.

### Step 8: collect_tasks three-path dispatch (`libs/core/kiln_ai/adapters/eval/eval_runner.py`)

Extend `collect_tasks` (line 88) with a third path:

```python
def collect_tasks(self) -> List[EvalJob]:
    if self._source_mode == "eval_input":
        return self.collect_tasks_for_eval_input()
    elif self.eval_run_type == "eval_config_eval":
        if self.eval.eval_configs_filter_id is not None:
            return self.collect_tasks_for_eval_config_eval(
                self.eval.eval_configs_filter_id
            )
        else:
            raise ValueError(
                "Eval configs filter ID is required for eval runs of type 'eval_config_eval'"
            )
    else:
        return self.collect_tasks_for_task_run_eval()
```

### Step 9: collect_tasks_for_eval_input (`libs/core/kiln_ai/adapters/eval/eval_runner.py`)

Add a new method to `EvalRunner`. Note: EvalInput-sourced jobs still use the existing `eval_config_eval` type (no new type values). The source mode is already tracked via `_source_mode`.

```python
def collect_tasks_for_eval_input(self) -> List[EvalJob]:
    """Collect jobs from EvalInput items under the task."""
    filter_id = self.eval.eval_input_filter_id
    if filter_id is None:
        raise ValueError("eval_input_filter_id is required for eval_input source mode")
    input_filter = eval_input_filter_from_id(filter_id)

    # Dedup: already_run[eval_config_id] = set of eval_input_ids
    already_run: Dict[ID_TYPE, Set[ID_TYPE]] = {}
    for eval_config in self.eval_configs:
        already_run[eval_config.id] = set()
        for run in eval_config.runs(readonly=True):
            if run.eval_input_id is not None:
                already_run[eval_config.id].add(run.eval_input_id)

    jobs: List[EvalJob] = []
    for eval_input in self.task.eval_inputs(readonly=True):
        if not input_filter(eval_input):
            continue
        for eval_config in self.eval_configs:
            if eval_input.id in already_run[eval_config.id]:
                continue
            jobs.append(
                EvalJob(
                    item=eval_input,
                    eval_config=eval_config,
                    type=self.eval_run_type,
                )
            )
    return jobs
```

### Step 10: TaskRun-to-EvalTaskInput translation (`libs/core/kiln_ai/adapters/eval/eval_runner.py`)

Add a module-level helper function:

```python
def _build_eval_task_input_from_task_run(
    task_run: TaskRun,
    eval: Eval,
) -> EvalTaskInput:
    """Translate a TaskRun into the V2 EvalTaskInput namespace (B2.1 compat).

    Only supports single-turn task runs. Multi-turn traces with no final
    output are not translatable and will raise.
    """
    trace_data: list[dict[str, Any]] | None = None
    if task_run.trace is not None:
        trace_data = task_run.trace

    return EvalTaskInput(
        final_message=task_run.output.output,
        trace=trace_data,
        reference_data=None,
        task_input=task_run.input,
    )


def _build_eval_task_input_from_eval_input(
    eval_input: EvalInput,
    stored_output: str,
    stored_trace: list[dict[str, Any]] | None,
) -> EvalTaskInput:
    """Build EvalTaskInput from an EvalInput + stored execution results."""
    task_input: str | None = None
    if hasattr(eval_input.data, "message") and eval_input.data.message is not None:
        task_input = eval_input.data.message

    return EvalTaskInput(
        final_message=stored_output,
        trace=stored_trace,
        reference_data=eval_input.reference,
        task_input=task_input,
    )
```

### Step 11: run_job widening for V2 (`libs/core/kiln_ai/adapters/eval/eval_runner.py`)

Modify `run_job` (line 203) to handle V2 configs. The key change: when `eval_config.config_type == EvalConfigType.v2`, use `v2_eval_adapter_from_config` and the `BaseV2Eval.evaluate()` path instead of the `BaseEval.run_eval()` path.

At the top of `run_job`, add dispatch branching:

```python
async def run_job(self, job: EvalJob) -> bool:
    try:
        if job.eval_config.config_type == EvalConfigType.v2:
            return await self._run_v2_job(job)
        else:
            return await self._run_legacy_job(job)
    except Exception as e:
        # ... existing error handling ...
```

Extract the existing run_job body into `_run_legacy_job`. Add `_run_v2_job`:

```python
async def _run_v2_job(self, job: EvalJob) -> bool:
    from kiln_ai.adapters.eval.registry import v2_eval_adapter_from_config

    # Dispatch -- if the V2 type has no registered adapter, skip with type_not_available
    try:
        evaluator = v2_eval_adapter_from_config(job.eval_config)
    except NotImplementedError:
        async with self._save_context():
            eval_run = EvalRun(
                parent=job.eval_config,
                task_run_config_id=job.task_run_config.id if job.task_run_config else None,
                dataset_id=job.item.id if isinstance(job.item, TaskRun) else None,
                eval_input_id=job.item.id if isinstance(job.item, EvalInput) else None,
                eval_config_eval=job.type == "eval_config_eval",
                scores={},
                input="",
                output=None,
                skipped_reason=SkippedReason.type_not_available.value,
                skipped_detail=f"V2 eval type not yet implemented",
            )
            eval_run.save_to_file()
        return True

    # Build EvalTaskInput
    if isinstance(job.item, TaskRun):
        eval_task_input = _build_eval_task_input_from_task_run(job.item, self.eval)
        dataset_id = job.item.id
        eval_input_id = None
        task_input_str = job.item.input
        task_output = job.item.output.output
    else:
        # EvalInput path -- stored_output must be set or we skip
        if job.stored_output is None:
            # Not yet executed; for now this is an error (Phase 3 will add execution)
            raise ValueError("EvalInput jobs require stored_output (task execution not yet implemented)")
        eval_task_input = _build_eval_task_input_from_eval_input(
            job.item, job.stored_output, job.stored_trace
        )
        dataset_id = None
        eval_input_id = job.item.id
        task_input_str = eval_task_input.task_input or ""
        task_output = job.stored_output

    # Run the evaluator
    scores, skipped_reason, skipped_detail = evaluator.evaluate(eval_task_input)

    # Save
    async with self._save_context():
        eval_run = EvalRun(
            parent=job.eval_config,
            task_run_config_id=job.task_run_config.id if job.task_run_config else None,
            dataset_id=dataset_id,
            eval_input_id=eval_input_id,
            eval_config_eval=job.type == "eval_config_eval",
            scores=scores,
            input=task_input_str,
            output=task_output if skipped_reason is None else None,
            reference_data=eval_task_input.reference_data,
            skipped_reason=skipped_reason.value if skipped_reason else None,
            skipped_detail=skipped_detail,
        )
        eval_run.save_to_file()

    return True
```

Keep the existing error handling wrapper in `run_job` so both legacy and V2 share the same retry logic.

### Step 12: Scoring utils extraction (`libs/core/kiln_ai/adapters/eval/eval_utils/scoring_utils.py` -- new file)

**Prerequisite**: Before extracting, write characterization tests (see Tests section) that capture the exact current behavior of `build_llm_as_judge_score` and `build_g_eval_score` with known inputs/outputs. Only then refactor.

Extract `build_llm_as_judge_score` and `build_g_eval_score` from `GEval` (g_eval.py lines 331-387) into standalone functions in a new file:

```python
from kiln_ai.datamodel.eval import EvalScores, EvalOutputScore
from kiln_ai.adapters.run_output import RunOutput

def build_llm_as_judge_score(
    run_output: RunOutput,
    score_from_token_fn: Callable[[str], float | None],
) -> EvalScores:
    """Convert discrete LLM judge output to float scores."""
    ...

def build_g_eval_score(
    run_output: RunOutput,
    output_scores: list[EvalOutputScore],
    raw_output_from_logprobs_fn: Callable[[RunOutput], str],
    metric_offsets_fn: Callable[[str, list[str]], dict[str, int]],
    g_eval_single_metric_fn: Callable,
) -> EvalScores:
    """Build G-Eval weighted scores from logprobs."""
    ...
```

Note: The exact extraction API may evolve during implementation. The key constraint is that GEval's `build_llm_as_judge_score` and `build_g_eval_score` methods should delegate to these functions, and the characterization tests must continue to pass before and after the refactor.

### Step 13: On-read aggregation counters (`app/desktop/studio_server/eval_api.py`)

Add `n_used` and `n_excluded` fields to `ScoreSummary`:

```python
class ScoreSummary(BaseModel):
    mean_score: float = Field(description="The mean score across all runs.")
    n_used: int = Field(default=0, description="Number of runs used in this score average.")
    n_excluded: int = Field(default=0, description="Number of runs excluded (skipped) for this score.")
```

Update `compute_score_summary` (line 494) to count skipped runs and populate these fields. In the loop over `eval_config.runs()`, check `eval_run.skipped_reason is not None` and increment `n_excluded` counters instead of processing scores. When building `ScoreSummary` results, pass through `n_used=score_counts[...][...]` and the accumulated `n_excluded`.

Also add `n_excluded` to `EvalConfigResult`:

```python
class EvalConfigResult(BaseModel):
    eval_config_id: ID_TYPE = Field(description="The eval config ID.")
    results: Dict[str, ScoreSummary | None] = Field(...)
    percent_complete: float = Field(...)
    n_excluded: int = Field(default=0, description="Total skipped runs for this config.")
```

## Tests

**Important**: Since no concrete V2 adapters ship in Phase 2 (they are Phase 3), all runner/dispatch/EvalInput flow tests use a minimal **stub/fake V2 adapter** defined inside the test module only (not in production code). This stub implements `BaseV2Eval.evaluate()` with trivial logic (e.g. always returns `{"stub_score": 1.0}`) and is registered into `_V2_ADAPTER_MAP` via monkeypatch for the duration of each test.

### Test file: `libs/core/kiln_ai/adapters/eval/test_g_eval_characterization.py` (new)

These tests MUST be written and passing BEFORE the scoring_utils extraction in Step 12.

- **`test_build_llm_as_judge_score_five_star`**: Provide a RunOutput with dict output `{"quality": 4}`, verify `build_llm_as_judge_score` returns `{"quality": 0.75}` (or the correct mapped value for token "4").
- **`test_build_llm_as_judge_score_pass_fail`**: Provide `{"accuracy": "pass"}`, verify mapped score.
- **`test_build_llm_as_judge_score_missing_metric`**: Output with a metric that has no valid score token raises ValueError.
- **`test_build_g_eval_score_uniform_logprobs`**: Provide RunOutput with uniform logprobs across rating tokens, verify the weighted average is the midpoint.
- **`test_build_g_eval_score_skewed_logprobs`**: Provide RunOutput with logprobs heavily favoring "5", verify score is close to 1.0.

### Test file: `libs/core/kiln_ai/datamodel/test_eval_task_input.py` (new)

- **`test_eval_task_input_basic_assembly`**: Construct EvalTaskInput with all four fields populated, verify `.model_dump()` round-trips.
- **`test_eval_task_input_defaults`**: Construct with only `final_message`, verify `trace` and `reference_data` are None.
- **`test_eval_task_input_from_task_run`**: Call `_build_eval_task_input_from_task_run` with a mock TaskRun, verify `final_message == task_run.output.output` and `task_input == task_run.input`.
- **`test_eval_task_input_from_eval_input`**: Call `_build_eval_task_input_from_eval_input` with a mock EvalInput, stored_output, and reference, verify all fields map correctly.

### Test file: `libs/core/kiln_ai/adapters/eval/test_v2_dispatch_and_contract.py` (new)

Tests for the dispatch scaffolding, `BaseV2Eval` contract, and extraction helpers. Uses a stub adapter since no concrete adapters exist in Phase 2.

- **`test_base_v2_eval_abstract_contract`**: Verify `BaseV2Eval` cannot be instantiated directly (ABC enforcement).
- **`test_stub_v2_eval_evaluate`**: Define a minimal `StubV2Eval(BaseV2Eval)` in the test module that returns `{"stub_score": 1.0}`. Verify it can be instantiated with an EvalConfig and `evaluate()` returns the expected tuple.
- **`test_stub_v2_eval_receives_eval_task_input`**: Verify the stub's `evaluate()` receives a correctly shaped `EvalTaskInput`.
- **`test_v2_dispatch_empty_map_raises`**: With the empty `_V2_ADAPTER_MAP`, calling `v2_eval_adapter_from_config` for any V2 type raises `NotImplementedError` (the `type_not_available` skip path).
- **`test_v2_dispatch_with_monkeypatched_stub`**: Monkeypatch `_V2_ADAPTER_MAP` to register the stub for one V2 type, verify `v2_eval_adapter_from_config` returns an instance of the stub.
- **`test_v2_dispatch_rejects_legacy_config`**: Non-v2 config_type -> raises ValueError.
- **`test_legacy_dispatch_unchanged`**: g_eval/llm_as_judge still returns GEval via `eval_adapter_from_type`.
- **`test_extract_value_from_final_message`**: `extract_value(None, eval_input)` returns `final_message`.
- **`test_extract_value_from_expression`**: `extract_value("trace[0].content", eval_input)` extracts correctly.
- **`test_extract_value_undefined_skips`**: Expression resolves to undefined -> returns `SkippedReason.extraction_failed`.
- **`test_check_reference_key_present`**: Key exists in `reference_data` -> returns the value.
- **`test_check_reference_key_missing`**: Key absent -> returns `SkippedReason.missing_reference_key`.
- **`test_check_reference_key_no_reference_data`**: `reference_data` is None -> returns `SkippedReason.missing_reference_key`.
- **`test_check_required_vars_all_present`**: All vars resolve -> returns `(None, None)`.
- **`test_check_required_vars_missing`**: One var undefined -> returns `SkippedReason.extraction_failed`.

### Test file: `libs/core/kiln_ai/adapters/eval/test_registry.py` (extend existing)

- **`test_v2_dispatch_all_types_unimplemented`**: Iterate over all `V2EvalType` values, verify each raises `NotImplementedError` (empty map).
- **`test_v2_dispatch_rejects_legacy_config`**: Non-v2 config_type -> raises ValueError.
- **`test_legacy_dispatch_unchanged`**: g_eval/llm_as_judge still returns GEval.
- **`test_legacy_dispatch_v2_raises`**: v2 config_type via `eval_adapter_from_type` -> raises NotImplementedError with message about `v2_eval_adapter_from_config`.

### Test file: `libs/core/kiln_ai/adapters/eval/test_eval_runner.py` (extend existing)

Uses a monkeypatched stub V2 adapter to test the runner's V2 code paths without requiring production adapters.

- **`test_eval_runner_init_eval_input_source`**: Create EvalRunner with an Eval that has `eval_input_filter_id` set, verify `_source_mode == "eval_input"`.
- **`test_eval_runner_init_rejects_task_run_eval_with_eval_input`**: Eval with `eval_input_filter_id` + `eval_run_type="task_run_eval"` -> raises ValueError.
- **`test_collect_tasks_for_eval_input_filters`**: Mock eval_inputs with tags, verify filter is applied and dedup works.
- **`test_collect_tasks_for_eval_input_dedup`**: Create EvalRuns with eval_input_ids, verify those inputs are skipped.
- **`test_run_v2_job_with_stub_adapter`**: Monkeypatch `_V2_ADAPTER_MAP` with a stub, create a V2 EvalConfig + TaskRun, call `run_job`, verify EvalRun is saved with the stub's scores.
- **`test_run_v2_job_type_not_available_skip`**: V2 EvalConfig with a type NOT in `_V2_ADAPTER_MAP` (empty map) -> EvalRun saved with `skipped_reason=type_not_available`, empty scores.
- **`test_run_v2_job_skipped_by_adapter`**: Stub adapter returns a `SkippedReason` -> EvalRun saved with that skip reason, empty scores.
- **`test_run_v2_job_eval_input_path`**: V2 job from EvalInput with stored_output, stub adapter -> EvalRun saved with `eval_input_id`.
- **`test_eval_job_type_unchanged`**: Verify EvalJob.type only accepts `"task_run_eval"` and `"eval_config_eval"` (no new values).

### Test file: `libs/core/kiln_ai/datamodel/test_eval_model.py` (extend existing)

- **`test_v2_eval_config_validates_prompt_template_syntax`**: Invalid Jinja in prompt_template -> raises ValueError.
- **`test_v2_eval_config_validates_value_expression_syntax`**: Invalid Jinja expression -> raises ValueError.
- **`test_v2_eval_config_rejects_useless_template`**: Template with no `{{` or `{%` -> raises ValueError.
- **`test_v2_eval_config_valid_template_passes`**: Template with `{{ final_message }}` passes.
- **`test_v2_eval_config_validates_required_var`**: Invalid expression in required_var list -> raises ValueError.

### Test file: `app/desktop/studio_server/test_eval_api.py` (extend existing)

- **`test_score_summary_n_used_n_excluded`**: compute_score_summary with a mix of scored and skipped runs returns correct `n_used` and `n_excluded`.
- **`test_score_summary_all_skipped`**: All runs skipped -> `n_used=0`, `n_excluded=N`, `mean_score` not present (or ScoreSummary is None).

## Out of Scope

These items are explicitly deferred to future phases:

- **Concrete deterministic V2 adapters**: exact_match, pattern_match, contains, set_check (component 22). Phase 3. Phase 2 ships the `BaseV2Eval` contract and empty `_V2_ADAPTER_MAP`; Phase 3 implements and registers these adapters.
- **LLM-backed V2 adapters**: llm_judge adapter (requires LLM invocation, thinking instructions, g_eval logprob weighting). Phase 3.
- **Agentic adapters**: tool_call_check, step_count_check (require multi-turn trace parsing). Phase 3+.
- **code_eval adapter**: Sandboxed code execution. Phase 3+.
- **Task execution for EvalInput sources**: Running the task model to generate output from EvalInput data. Phase 3. (Phase 2 only supports stored_output pre-fetched data, or B2.1 translation from TaskRun sources.)
- **Multi-turn EvalInput execution**: Building conversation flows from MultiTurnSyntheticEvalInputData. Phase 3+.
- **Frontend UI changes**: No web_ui changes in this phase.
- **API endpoints for V2 eval creation/management**: eval_api.py route changes beyond aggregation counters.
- **EvalInput CRUD API**: Creating/listing/filtering EvalInputs via REST.
- **Prompt template rendering in llm_judge**: The Jinja template rendering for LLM judge prompts is validated at save time in this phase, but actual rendering happens in the llm_judge adapter (Phase 3).
- **New eval_run_type values**: Per component 45, no new values are introduced. Source mode remains orthogonal to run type.
