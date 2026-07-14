---
status: complete
approved: true
alignment_refs: [A1.3, A2.3, A2.5, A2.6, A2.11, B2.1, C.9, C.runner.1, C.runner.3, C.11b, E.18, K.3, H.32, H.32a]
opens: []
summary: EvalInput flow, adapter dispatch, multi-config orchestration, candidate calibration, missing-reference skip handling, runner constructor branching, TaskRun-to-EvalInput runtime translation.
---

# Runner Architecture

**Author:** sub-agent dispatched 2026-06-03 for Stage 4 gap-fill
**Status:** complete

## TL;DR

- **EvalInput flow:** The V2 runner collects EvalInput items via `collect_tasks_for_eval_input`, filters by `eval_input_filter_id`, and constructs `EvalJob` instances with `item: EvalInput`. The synthetic `EvalTaskInput` JSON doc (final_message, trace, reference_data, task_input) is assembled per case from the EvalInput + TaskRun output, then fed through the adapter's scoring path.
- **EvalJob widened:** `EvalJob.item` changes from `TaskRun` to `TaskRun | EvalInput`. A new `stored_output: str | None` field carries pre-existing output for `eval_config_eval` mode with TaskRun sources.
- **Runner dispatch:** `collect_tasks` dispatches by which filter field is set on the Eval (`eval_input_filter_id` vs `eval_set_filter_id` / `eval_configs_filter_id`). Three collection paths; one run-job path with adapter dispatch.
- **Two-level adapter dispatch:** Runner calls `eval_adapter_from_type(eval_config)` (signature widened per A2.11). Outer branch on `config_type`; inner branch on `properties.type` for V2. Legacy GEval path untouched.
- **Multi-config orchestration:** `task_run_eval` mode runs only `current_config_id`; `eval_config_eval` mode runs all candidate configs. Mode is orthogonal to input source (C.9).
- **B2.1 runtime translation:** When a V2 EvalConfig consumes TaskRun-source data, the runner synthesizes an in-memory EvalInput per TaskRun. No persist. `EvalRun.dataset_id` points at the source TaskRun.
- **Skip emission:** The runner emits skipped EvalRuns with `SkippedReason` values from `components/85` before task execution (reference-key, input-shape, trust, type-availability checks) and during extraction (`extraction_failed`). No hard-fail on individual skips.
- **Score provenance:** EvalRuns carry `reference_data` (from EvalInput.reference) and link to the immutable parent EvalConfig via the existing `parent_of` chain. Cross-ref `components/85`.

---

## 1. EvalJob extension (B2.1)

The runner's job dataclass widens to accept both V1 and V2 input sources:

```python
@dataclass
class EvalJob:
    eval_config: EvalConfig
    item: TaskRun | EvalInput             # widened from TaskRun (was eval_runner.py:25)
    run_config: KilnAgentRunConfigProperties | None = None
    stored_output: str | None = None      # NEW -- for eval_config_eval with TaskRun source
    stored_trace: str | None = None       # NEW -- trace JSON for eval_config_eval
```

- `item: TaskRun` -- V1 path or B2.1 translation source.
- `item: EvalInput` -- V2 native path (from `eval_input_filter_id`-backed Evals).
- `stored_output` -- populated only for `eval_config_eval` mode when the source is a TaskRun. Carries `TaskRun.output.output` so the V2 adapter can score existing output without re-running the task. Not populated for EvalInput-sourced `eval_config_eval` (future: EvalInput may gain output storage; for V2.0, `eval_config_eval` with EvalInput source is the Copilot golden-subset path where TaskRuns are the source per K.3).
- `stored_trace` -- populated alongside `stored_output` when the TaskRun has a trace. Carries `json.dumps(TaskRun.trace)`.

---

## 2. Runner constructor branching (C.runner.3)

### 2.1 `EvalRunner.__init__` extension

The constructor validation at `eval_runner.py:64-78` gains a new branch for `eval_input_filter_id`-sourced runs. No new `eval_run_type` value -- run mode and input source are orthogonal.

```python
class EvalRunner:
    def __init__(
        self,
        eval: Eval,
        eval_configs: list[EvalConfig],
        run_configs: list[KilnAgentRunConfigProperties] | None = None,
        eval_run_type: Literal["task_run_eval", "eval_config_eval"] = "task_run_eval",
        ...
    ):
        # Existing invariant -- unchanged
        if eval_run_type == "task_run_eval":
            assert run_configs is not None and len(run_configs) > 0
        else:
            assert run_configs is None or len(run_configs) == 0

        # Source-validation branch (NEW: EvalInput path)
        if eval.eval_input_filter_id is not None:
            # V2 path: validate EvalInput dataset availability
            self._validate_eval_input_source(eval)
        elif eval_run_type == "eval_config_eval":
            # V1 path: eval_configs_filter_id
            self._validate_eval_config_eval_source(eval)
        else:
            # V1 path: task_run_eval with eval_set_filter_id
            self._validate_task_run_eval_source(eval)

        # Existing: all eval_configs share the same parent Eval and grandparent Task
        # Existing: preload skills from all run configs
```

### 2.2 Coverage matrix

Both V1 and V2 work over either run mode. The `run_configs iff task_run_eval` invariant is mode-driven, not source-driven:

| Source | Run mode | `run_configs` | Data flow |
|---|---|---|---|
| TaskRun (V1, `eval_set_filter_id`) | `task_run_eval` | required | Existing -- run task fresh on TaskRun input, judge |
| TaskRun (V1, `eval_configs_filter_id`) | `eval_config_eval` | not used | Existing -- judge against stored TaskRun output |
| EvalInput (V2, `eval_input_filter_id`) | `task_run_eval` | required | NEW -- runner reads `EvalInput.data.user_message`, runs via run_configs, judges output |
| EvalInput (V2, `eval_input_filter_id`) | `eval_config_eval` | not used | NEW -- runner reads stored output (per B2.1), judges only |
| TaskRun (V1 filter) -- **V2 EvalConfig** | either | per mode | NEW (B2.1) -- runner synthesizes in-memory EvalInput per TaskRun; V2 adapter consumes EvalInput shape |

---

## 3. Job collection and dispatch by filter field (A2.5, C.runner.3)

### 3.1 `collect_tasks` top-level dispatch

```python
def collect_tasks(self) -> list[EvalJob]:
    if self.eval.eval_input_filter_id is not None:
        # V2 path: EvalInput-backed dataset
        return self.collect_tasks_for_eval_input()
    elif self.eval_run_type == "eval_config_eval":
        # V1 path: eval config eval
        return self.collect_tasks_for_eval_config_eval()
    else:
        # V1 path: task run eval
        return self.collect_tasks_for_task_run_eval()
```

### 3.2 `collect_tasks_for_eval_input` (NEW)

Loads EvalInput children from the parent Task, applies the `EvalInputFilter` registered for `eval.eval_input_filter_id`, and constructs EvalJob instances. For `task_run_eval` mode, crosses with all `run_configs`. For `eval_config_eval` mode, no run_configs.

```python
def collect_tasks_for_eval_input(self) -> list[EvalJob]:
    eval_inputs = self.task.eval_inputs()  # NEW: Task.eval_inputs() child accessor
    filter_fn = eval_input_filter_from_id(self.eval.eval_input_filter_id)
    filtered = [ei for ei in eval_inputs if filter_fn(ei)]

    jobs = []
    for eval_input in filtered:
        for eval_config in self.eval_configs:
            if self.eval_run_type == "task_run_eval":
                for run_config in self.run_configs:
                    if not self._already_run(eval_config, run_config, eval_input_id=eval_input.id):
                        jobs.append(EvalJob(
                            eval_config=eval_config,
                            item=eval_input,
                            run_config=run_config,
                        ))
            else:
                # eval_config_eval -- no run_configs
                if not self._already_run(eval_config, eval_input_id=eval_input.id):
                    jobs.append(EvalJob(
                        eval_config=eval_config,
                        item=eval_input,
                    ))
    return jobs
```

### 3.3 B2.1 integration in existing collectors

When the EvalConfig has `config_type == "v2"` and the source is TaskRun-shaped, the existing `collect_tasks_for_task_run_eval` and `collect_tasks_for_eval_config_eval` methods inject `stored_output` and `stored_trace` on the EvalJob. The runner translates later in `run_job` (section 5).

```python
def collect_tasks_for_eval_config_eval(self) -> list[EvalJob]:
    # Existing: iterate task.runs() filtered by eval.eval_configs_filter_id
    for task_run in filtered_runs:
        for eval_config in self.eval_configs:
            if not self._already_run(eval_config, dataset_id=task_run.id):
                job = EvalJob(
                    eval_config=eval_config,
                    item=task_run,
                )
                # B2.1: carry stored output/trace for V2 adapters
                if eval_config.config_type == EvalConfigType.v2:
                    job.stored_output = task_run.output.output if task_run.output else None
                    job.stored_trace = json.dumps(task_run.trace) if task_run.trace else None
                jobs.append(job)
    return jobs
```

### 3.4 `_already_run` predicate extension

The existing "already run" check (which enables restartability) extends to handle `eval_input_id`:

```python
def _already_run(
    self,
    eval_config: EvalConfig,
    run_config: KilnAgentRunConfigProperties | None = None,
    dataset_id: str | None = None,
    eval_input_id: str | None = None,
) -> bool:
    # Check persisted EvalRun files for a matching
    # (eval_config, run_config, dataset_id | eval_input_id) triple
    ...
```

---

## 4. Multi-config orchestration and candidate calibration (C.9)

### 4.1 Two run modes

Per C.9, `task_run_eval` mode runs only the operative config (`current_config_id`). `eval_config_eval` mode runs all candidate configs against the golden subset to drive promotion decisions.

| Mode | Which configs run | Purpose |
|---|---|---|
| `task_run_eval` | `current_config_id` only (the promoted candidate) | Production scoring -- "score this input with the validated judge" |
| `eval_config_eval` | All `eval_configs` under the Eval | Calibration -- "how do these judge candidates compare against the golden subset?" |

### 4.2 Candidate type diversity

Per C.9 option (b), candidates under one Eval may be different `V2EvalType`s (e.g., a `pattern_match` candidate alongside an `llm_judge` candidate) as long as the produced scores conform to `Eval.output_scores` shape. The runner does not enforce type uniformity -- `EvalRun.validate_scores` catches mismatches at save time.

### 4.3 Calibration flow with mixed V1/V2 configs

An Eval may have both legacy V1 EvalConfigs (on disk from before V2) and V2 EvalConfigs. The runner handles both:

- V1 configs: dispatched to `GEval` via the legacy registry path. Receive `TaskRun` items directly.
- V2 configs: dispatched to the V2 adapter registry. Receive `EvalInput` items (native or synthesized via B2.1).

Both produce `EvalRun` records with `scores: EvalScores` conforming to the shared `Eval.output_scores`. The calibration comparison (`get_eval_configs_score_summary` in `eval_api.py`) reads all EvalRuns under each config regardless of type.

---

## 5. `run_job` -- adapter dispatch and EvalInput flow (A2.11, C.11b, B2.1, H.32)

### 5.1 Overview

`run_job` is the per-job execution function called by `AsyncJobRunner`. It handles adapter instantiation, B2.1 runtime translation, skip checks, task execution, scoring, and EvalRun persistence.

```python
async def run_job(self, job: EvalJob) -> None:
    # 1. Adapter dispatch (two-level per C.11b)
    adapter_cls = eval_adapter_from_type(job.eval_config)  # A2.11: full EvalConfig
    evaluator = adapter_cls(job.eval_config, job.run_config, skills=self.skills)

    # 2. Determine effective item (B2.1 translation if needed)
    effective_item, source_dataset_id, source_eval_input_id = (
        self._resolve_item(job)
    )

    # 3. Pre-execution skip checks (C.runner.1)
    skip_reason, skip_detail = self._check_skip_conditions(job.eval_config, effective_item)
    if skip_reason is not None:
        self._persist_skipped_run(job, skip_reason, source_dataset_id, source_eval_input_id, skipped_detail=skip_detail)
        return

    # 4. Extraction pre-check (D.3 -- required_var / value_expression)
    skip_reason, skip_detail = self._check_extraction(job.eval_config, effective_item)
    if skip_reason is not None:
        self._persist_skipped_run(job, skip_reason, source_dataset_id, source_eval_input_id, skipped_detail=skip_detail)
        return

    # 5. Execute
    if self.eval_run_type == "task_run_eval":
        task_run, scores, intermediate = await evaluator.run_task_and_eval(effective_item)
    else:
        scores, intermediate = await evaluator.run_eval(effective_item, stored_output=job.stored_output)

    # 6. Persist EvalRun
    self._persist_eval_run(job, scores, intermediate, source_dataset_id, source_eval_input_id, ...)
```

### 5.2 B2.1 runtime TaskRun-to-EvalInput translation

When a V2 EvalConfig receives a TaskRun-source item, the runner synthesizes an in-memory EvalInput:

```python
def _resolve_item(self, job: EvalJob) -> tuple[TaskRun | EvalInput, str | None, str | None]:
    """Returns (effective_item, source_dataset_id, source_eval_input_id)."""

    if isinstance(job.item, EvalInput):
        # V2 native path -- EvalInput is the source
        return job.item, None, job.item.id

    # job.item is TaskRun
    task_run = job.item

    if job.eval_config.config_type != EvalConfigType.v2:
        # Legacy config + TaskRun source -- pass through unchanged
        return task_run, task_run.id, None

    # B2.1: V2 config + TaskRun source -- synthesize in-memory EvalInput
    eval_input = self._translate_task_run_to_eval_input(task_run)
    return eval_input, task_run.id, None  # dataset_id = TaskRun.id (preserves correlation API)


def _translate_task_run_to_eval_input(self, task_run: TaskRun) -> EvalInput:
    """Synthesize an in-memory EvalInput from a TaskRun (B2.1).

    The resulting EvalInput is NOT persisted. It exists only for the
    duration of this job's execution.
    """
    # Edge case: multi-turn TaskRun -- cannot translate
    if task_run.parent_task_run_id is not None:
        raise _IncompatibleInputShape()

    return EvalInput(
        tags=task_run.tags or [],
        reference=None,  # TaskRuns don't carry structured reference data
        data=SingleTurnEvalInputData(
            user_message=UserMessage(text=task_run.input),
        ),
        # Not persisted -- no path/id needed. In-memory only.
    )
```

**Translation mapping (B2.1):**

| TaskRun field | EvalInput / side-channel destination |
|---|---|
| `TaskRun.input` | `SingleTurnEvalInputData.user_message.text` |
| `TaskRun.tags` | `EvalInput.tags` |
| `TaskRun.output.output` | `EvalJob.stored_output` (for `eval_config_eval` mode); passed to V2 adapter via D.2 reserved `final_message` variable |
| `TaskRun.trace` | `EvalJob.stored_trace`; passed to adapter as D.2 reserved `trace` variable |
| `TaskRun.id` | NOT carried on EvalInput (`source_task_run_id` deferred with Batch F). Tracked via `EvalRun.dataset_id` pointing at the TaskRun. |
| `TaskRun.output.rating` | Stays on TaskRun; correlation API reads it unchanged |

**EvalRun source field for B2.1 runs:** `EvalRun.dataset_id` points at the source TaskRun (not `eval_input_id`). This preserves the correlation API's ability to pair (TaskRun rating, EvalRun judge scores) for V2 EvalConfig runs without modification.

### 5.3 `BaseEval.run_eval` signature widening (H.32 residue)

The abstract `run_eval` method signature widens to accept both types:

```python
class BaseEval(ABC):
    @abstractmethod
    async def run_eval(
        self,
        item: TaskRun | EvalInput,
        stored_output: str | None = None,
        stored_trace: str | None = None,
    ) -> tuple[EvalScores, dict[str, str] | None]:
        ...
```

This is a mechanical consequence of B2.1, not a new design decision (H.32 confirmation). In practice:
- Legacy `GEval` always receives `TaskRun` (the runner guarantees this).
- V2 adapters always receive `EvalInput` (native or synthesized via B2.1).
- Each concrete subclass narrows in practice; the union is a formality.

---

## 6. Pre-execution skip checks and emission (C.runner.1, E.18)

### 6.1 Skip check pipeline

The runner performs pre-execution checks before invoking the adapter. Each check can produce a `SkippedReason` value. If any check fails, a partial EvalRun is persisted with that reason and the job terminates. Other (input x config) jobs proceed normally -- no hard-fail on individual skips.

```python
def _check_skip_conditions(
    self,
    eval_config: EvalConfig,
    item: TaskRun | EvalInput,
) -> tuple[SkippedReason | None, str | None]:
    # 1. Type availability (A2.11 registry)
    if eval_config.config_type == EvalConfigType.v2:
        if not _adapter_available(eval_config.properties.type):
            return SkippedReason.type_not_available, str(eval_config.properties.type)

    # 2. Input shape compatibility (B2.1 edge cases)
    if not self._input_shape_compatible(eval_config, item):
        return SkippedReason.incompatible_input_shape, self._describe_shape_mismatch(eval_config, item)

    # 3. Reference key presence (C.runner.1 / A1.3)
    if isinstance(item, EvalInput):
        missing = self._missing_reference_keys(eval_config, item)
        if missing:
            return SkippedReason.missing_reference_key, missing[0]

    # 4. Trust gate (B.13 -- code_eval only)
    if (eval_config.config_type == EvalConfigType.v2
            and eval_config.properties.type == V2EvalType.code_eval):
        if not project_trust_granted(self.task.project):
            return SkippedReason.code_eval_not_trusted, None

    return None, None  # all checks passed
```

### 6.2 Extraction pre-check (D.3)

After the structural skip checks pass, the runner pre-checks extraction expressions before invoking the adapter:

```python
def _check_extraction(
    self,
    eval_config: EvalConfig,
    item: TaskRun | EvalInput,
) -> tuple[SkippedReason | None, str | None]:
    if eval_config.config_type != EvalConfigType.v2:
        return None, None  # legacy configs don't use extract()

    props = eval_config.properties

    # llm_judge: pre-check required_var expressions
    if hasattr(props, 'required_var'):
        eval_task_input = self._build_eval_task_input(item)
        for expr in props.required_var:
            result = extract(expr, eval_task_input)
            if result is None or isinstance(result, Undefined):
                return SkippedReason.extraction_failed, expr

    # deterministic types with value_expression: pre-check
    if hasattr(props, 'value_expression') and props.value_expression is not None:
        eval_task_input = self._build_eval_task_input(item)
        result = extract(props.value_expression, eval_task_input)
        if result is None or isinstance(result, Undefined):
            return SkippedReason.extraction_failed, props.value_expression

    return None, None
```

### 6.3 When each `SkippedReason` is emitted

The `SkippedReason` enum is **defined in `components/85_observability_and_audit.md`** (section 2.2). This file owns the runtime emission behavior -- when and how the runner emits each value:

| `SkippedReason` value | Emission point | Condition | `skipped_detail` |
|---|---|---|---|
| `missing_reference_key` | `_check_skip_conditions` step 3 | EvalInput.reference is missing a key the EvalConfig declares as required (per A1.3 multi-config reference contract) | The missing key name (e.g. `"expected_classification"`) |
| `incompatible_input_shape` | `_check_skip_conditions` step 2 | EvalInput data variant does not match EvalConfig's expected shape (e.g., multi-turn TaskRun under single-turn config in B2.1 path; multi-turn V2 config under V1 TaskRun source) | Short description of the mismatch |
| `extraction_failed` | `_check_extraction` | A `required_var` expression (llm_judge) or `value_expression` (deterministic type) evaluated to null/Undefined on this input (D.3) | The expression that returned null/Undefined (e.g. `"reference_data.reference_answer"`) |
| `missing_trace` | Adapter-level pre-check | Trace-walking type (`tool_call_check`, `step_count_check`) found `trace` is None (components/22 section 2) | `None` |
| `code_eval_not_trusted` | `_check_skip_conditions` step 4 | `CodeEvalAdapter` trust gate not accepted for this project (B.13) | `None` |
| `type_not_available` | `_check_skip_conditions` step 1 | V2 adapter registry has no adapter for the config's `properties.type` (forward-compat guard; should not occur in V2.0 with closed catalog per E.36) | The unavailable type name |

**No values added or removed vs `components/85`.** The six values seeded there (`missing_reference_key`, `incompatible_input_shape`, `extraction_failed`, `missing_trace`, `code_eval_not_trusted`, `type_not_available`) cover all known skip conditions from the locked alignment decisions and V2 type catalog. `missing_trace` is emitted by the trace-walking types (`tool_call_check`, `step_count_check`) when `trace` is None (see `components/22` section 2). The `skipped_reason` field is persisted as a tolerant `str` (not a strict enum type); see `components/85` section 2.2 for rationale.

### 6.4 Skipped EvalRun persistence

```python
def _persist_skipped_run(
    self,
    job: EvalJob,
    reason: SkippedReason,
    dataset_id: str | None,
    eval_input_id: str | None,
    skipped_detail: str | None = None,
) -> None:
    eval_run = EvalRun(
        skipped_reason=reason,
        skipped_detail=skipped_detail,
        dataset_id=dataset_id,
        eval_input_id=eval_input_id,
        task_run_config_id=job.run_config.id if job.run_config else None,
        eval_config_eval=(self.eval_run_type == "eval_config_eval"),
        input=self._extract_input_text(job.item),
        output=None,           # skipped before execution
        scores={},             # no scores (validator relaxed per E.18)
        reference_data=self._extract_reference_data(job.item),
    )
    eval_run.save_to_file(parent=job.eval_config)
```

Skipped EvalRuns are a terminal state:
- Counted toward `percent_complete` in on-read aggregation.
- Excluded from score means (`n_excluded` counter).
- Validator relaxation: `validate_scores` allows empty scores when `skipped_reason is not None`; `output` field accommodates `None` when skipped. Detail in `components/10_data_model.md` section 5.4.

---

## 7. EvalTaskInput assembly (D.3 cross-ref)

The runner assembles the synthetic `EvalTaskInput` document that serves as the Jinja2 template context for V2 eval types. This assembly is defined in `components/40_template_and_extraction.md` section 2; the runner is the executor:

```python
def _build_eval_task_input(self, item: TaskRun | EvalInput, task_run_output: str | None = None) -> EvalTaskInput:
    """Build the synthetic JSON input for V2 eval template rendering.

    Sources data from either EvalInput (V2 native) or TaskRun (V1/B2.1).
    The four reserved top-level variables (final_message, trace,
    reference_data, task_input) are populated per D.2.
    """
    if isinstance(item, EvalInput):
        return EvalTaskInput(
            final_message=task_run_output or "",
            trace=None,  # populated after task execution in run_job
            reference_data=item.reference,
            task_input=item.data.user_message.text if hasattr(item.data, 'user_message') else "",
        )
    else:
        # TaskRun path (legacy or B2.1 -- before synthesis)
        task_run = item
        return EvalTaskInput(
            final_message=task_run.output.output if task_run.output else "",
            trace=task_run.trace,
            reference_data=None,  # TaskRuns don't carry structured reference
            task_input=task_run.input,
        )
```

The `EvalTaskInput` fields are the reserved top-level Jinja2 template variables (`final_message`, `trace`, `reference_data`, `task_input`). User templates reference them directly: `{{ final_message }}`, `{{ reference_data.expected_answer }}`.

---

## 8. Adapter dispatch flow (A2.11, C.11b, H.32a)

### 8.1 Two-level registry dispatch

Per A2.11 and C.11b, `eval_adapter_from_type` accepts the full `EvalConfig` and performs two-level dispatch. The registry implementation is owned by `components/20_eval_config_types_overview.md` section 2; the runner consumes it:

```python
# In run_job:
adapter_cls = eval_adapter_from_type(job.eval_config)  # returns type[BaseEval]
evaluator = adapter_cls(job.eval_config, job.run_config, skills=self.skills)
```

**Call site change** at `eval_runner.py:204`:

```python
# Before (V1):
evaluator = eval_adapter_from_type(job.eval_config.config_type)(job.eval_config, ...)

# After (V2):
evaluator = eval_adapter_from_type(job.eval_config)(job.eval_config, ...)
```

### 8.2 V2 adapter data guarantees

The runner guarantees each adapter family receives the correct item type:

| Adapter family | Always receives | How |
|---|---|---|
| Legacy `GEval` | `TaskRun` | Runner passes `TaskRun` directly; V2 EvalConfigs never route to GEval |
| V2 adapters (`LlmJudgeAdapter`, deterministic, `CodeEvalAdapter`) | `EvalInput` | Native EvalInput for V2 Evals; synthesized in-memory EvalInput for B2.1 TaskRun sources |

### 8.3 Scoring helper consumption (H.32a)

V2 `LlmJudgeAdapter` consumes the extracted scoring helpers from `scoring_utils.py` (per `components/20` section 4):

```python
from kiln_ai.adapters.eval.scoring_utils import (
    build_llm_as_judge_score,
    build_g_eval_score,
)

class LlmJudgeAdapter(BaseEval):
    async def run_eval(self, item: EvalInput, **kwargs):
        # ... own task/prompt construction via D.2/D.3/D.4 ...
        run_output = await self._invoke_llm(...)
        if self.eval_config.properties.g_eval:
            return build_g_eval_score(run_output)
        else:
            return build_llm_as_judge_score(run_output)
```

Legacy GEval imports the same helpers with zero behavior change. The helpers are pure functions with no V1 coupling (verified in `components/20` section 4.1).

---

## 9. Reference-key checking (A1.3, C.runner.1)

### 9.1 Per-config declared reference keys

Per A1.3, each EvalConfig declares which reference keys it consumes. The runner checks this contract at the start of each (input x config) job:

```python
def _missing_reference_keys(self, eval_config: EvalConfig, item: EvalInput) -> list[str]:
    """Check if EvalInput.reference contains all keys the config requires."""
    if eval_config.config_type != EvalConfigType.v2:
        return []  # legacy configs don't declare reference keys

    required_keys = self._get_required_reference_keys(eval_config)
    if not required_keys:
        return []

    reference = item.reference or {}
    return [k for k in required_keys if k not in reference]
```

### 9.2 How required keys are derived

Required reference keys are derived per EvalConfigType:

| Type | Required keys source |
|---|---|
| `llm_judge` | Keys referenced via `reference_data.*` in `required_var` expressions |
| `exact_match`, `contains`, `set_check` | `reference_key` field on properties (when `expected_value` / `substring` / `expected_set` is None) |
| `pattern_match` | None (pattern is on the config, not reference data) |
| `tool_call_check`, `step_count_check` | None (walk trace directly) |
| `code_eval` | None at runner level (code accesses reference_data freely; type errors are runtime, not pre-checked) |

### 9.3 Input-shape compatibility

```python
def _input_shape_compatible(self, eval_config: EvalConfig, item: TaskRun | EvalInput) -> bool:
    """Check if the item's shape is compatible with the EvalConfig."""
    if isinstance(item, TaskRun):
        # B2.1 edge case: multi-turn TaskRun cannot translate to single-turn EvalInput
        if item.parent_task_run_id is not None:
            return False
        # Multi-turn V2 EvalConfig under TaskRun source
        if (eval_config.config_type == EvalConfigType.v2
                and self._config_expects_multi_turn(eval_config)):
            return False
    elif isinstance(item, EvalInput):
        # Future: check EvalInput.data.type vs config's expected shape
        # (e.g., image-gen EvalInput under text-only config)
        pass
    return True
```

---

## 10. EvalRun persistence and score provenance (A2.6, E.18, E.17 cross-ref)

### 10.1 Normal EvalRun persistence

```python
def _persist_eval_run(
    self,
    job: EvalJob,
    scores: EvalScores,
    intermediate_outputs: dict[str, str] | None,
    source_dataset_id: str | None,
    source_eval_input_id: str | None,
    task_run: TaskRun | None = None,  # from run_task_and_eval
    ...
) -> None:
    eval_run = EvalRun(
        dataset_id=source_dataset_id,           # A2.6: V1 source
        eval_input_id=source_eval_input_id,     # A2.6: V2 source
        task_run_config_id=job.run_config.id if job.run_config else None,
        eval_config_eval=(self.eval_run_type == "eval_config_eval"),
        input=self._extract_input_text(job.item),
        output=self._extract_output_text(task_run, job),
        scores=scores,
        intermediate_outputs=intermediate_outputs,
        reference_answer=self._extract_reference_answer(job.item),  # V1 field -- None for V2
        reference_data=self._extract_reference_data(job.item),      # V2 field -- from EvalInput.reference
        task_run_trace=self._serialize_trace(task_run, job),
        task_run_usage=self._extract_usage(task_run),
    )
    eval_run.save_to_file(parent=job.eval_config)
```

### 10.2 Input-source field semantics (A2.6)

Per the `EvalRun.validate_input_source` validator, exactly one of `dataset_id` (V1) or `eval_input_id` (V2) is set:

| Source | `dataset_id` | `eval_input_id` |
|---|---|---|
| V2 EvalInput (native) | None | EvalInput.id |
| V1 TaskRun (legacy or B2.1) | TaskRun.id | None |

The B2.1 translation path preserves `dataset_id` pointing at the source TaskRun (not the synthesized in-memory EvalInput) to maintain the correlation API pairing.

### 10.3 Score provenance chain (E.17 cross-ref)

Per `components/85_observability_and_audit.md` section 1, V2.0 introduces no new score-provenance fields. The existing `parent_of` chain is sufficient:

```
EvalRun -> EvalConfig (immutable, carries config_type/properties/model) -> Eval -> Task
```

The runner's only provenance responsibility is persisting the EvalRun as a child of the correct EvalConfig. The `EvalRun.reference_data` field (A2.7) carries the structured reference snapshot from EvalInput.reference, providing run-time reference traceability.

### 10.4 On-read aggregation impact (E.18)

Skipped EvalRuns (with `skipped_reason is not None`) affect the on-read aggregation in `eval_api.py`:

- `n_used` = EvalRuns with all expected score keys populated AND `skipped_reason is None`.
- `n_excluded` = EvalRuns with `skipped_reason is not None`.
- `percent_complete = (n_used + n_excluded) / dataset_size`.
- Score means computed only over `n_used` EvalRuns.

---

## 11. V2-specific `evaluation_data_type` handling (A2.3)

V2 EvalConfigs declare their data needs in their own properties (per A2.3). The Eval-level `evaluation_data_type` field is `None` for V2 Evals. The runner's existing branches that switch on `evaluation_data_type` to decide what to serialize into EvalRun fields (trace, reference_answer) are bypassed for V2:

```python
# In run_job, after task execution:
if job.eval_config.config_type == EvalConfigType.v2:
    # V2: data contract is per-config properties, not Eval-level.
    # Always serialize trace and reference_data if available.
    task_run_trace = json.dumps(task_run.trace) if task_run and task_run.trace else None
    reference_data = self._extract_reference_data(job.item)
else:
    # Legacy: existing behavior keyed on evaluation_data_type
    if self.eval.evaluation_data_type == EvalDataType.full_trace:
        task_run_trace = json.dumps(task_run.trace) if task_run and task_run.trace else None
    # ... etc
```

---

## 12. Dataset shape per flow (K.3)

Per K.3 (as amended by B2.1), after this project ships:

| Flow | Eval set | Golden subset | EvalConfig type | Filter fields on Eval |
|---|---|---|---|---|
| **Copilot path** | EvalInputs (V2) | TaskRuns (V1, unchanged) | V2 (`config_type="v2"`) | `eval_input_filter_id` + `eval_configs_filter_id` |
| **Manual path** | TaskRuns (V1, unchanged) | TaskRuns (V1, unchanged) | V2 (`config_type="v2"`) | `eval_set_filter_id` + `eval_configs_filter_id` |

The runner handles all four cells via the three collection paths in section 3. The B2.1 translation (section 5.2) bridges the "V2 EvalConfig + TaskRun source" combination for the manual path.

---

## 13. Alignment-ref coverage index

| Ref | Decision summary | Coverage in this file |
|---|---|---|
| A1.3 | Multi-config reference data consumption | Section 9 (reference-key checking; per-config declared keys checked at job start) |
| A2.3 | `evaluation_data_type` per-config in V2 | Section 11 (V2 bypass of Eval-level data-type switch; per-config properties drive data needs) |
| A2.5 | DatasetFilter coexistence -- separate filter types | Section 3.1 (dispatch by which filter field is set), Section 2.2 (coverage matrix) |
| A2.6 | EvalRun `eval_input_id` as orthogonal source field | Section 10.2 (input-source field semantics; XOR validator) |
| A2.11 | Adapter registry signature `EvalConfigType` to `EvalConfig` | Section 8.1 (call site change; two-level dispatch consumption) |
| B2.1 | V2 EvalConfig + TaskRun source -- runtime translation | Section 1 (EvalJob extension), Section 3.3 (collector integration), Section 5.2 (translation mapping + in-memory EvalInput synthesis) |
| C.9 | Eval-EvalConfig 1:1 cardinality; calibration candidates | Section 4 (two run modes; candidate type diversity; mixed V1/V2 calibration) |
| C.runner.1 | Missing reference data -- skip + report | Section 6 (skip check pipeline; reference-key checking; skipped EvalRun persistence) |
| C.runner.3 | `EvalRunner.__init__` extension for EvalInput-sourced runs | Section 2 (constructor branching; coverage matrix) |
| C.11b | V2 adapter registry -- two-level dispatch | Section 8 (dispatch flow; adapter data guarantees; consumed from `components/20`) |
| E.18 | Skip persistence + n_used/n_excluded | Section 6.3-6.4 (emission table; persistence; aggregation impact at section 10.4) |
| K.3 | V2-only EvalConfigs; dataset shape per flow | Section 12 (per-flow table; B2.1 bridges manual path) |
| H.32 | Coexistence confirmation -- no new schema | Section 5.3 (`run_eval` signature widening -- the sole residue; mechanical, not a new decision) |
| H.32a | Scoring helper extraction + V2 judge built fresh | Section 8.3 (consumption pattern; cross-ref `components/20` section 4) |

---

## 14. Cross-file ownership boundaries

| Concern | Owner | This file's role |
|---|---|---|
| `SkippedReason` enum value definitions + semantics | `components/85_observability_and_audit.md` | Runtime emission behavior (when/how each value is emitted -- section 6) |
| `EvalRun.skipped_reason` field definition | `components/10_data_model.md` | Persists the skip; section 6.4 shows the persistence pattern |
| Validator relaxation for skipped EvalRuns | `components/10_data_model.md` + this file | This file defines what a skipped EvalRun carries; `components/10` defines the validator changes |
| `EvalTaskInput` assembly + template variables | `components/40_template_and_extraction.md` | This file executes the assembly; `components/40` defines the shape |
| Two-level adapter registry implementation | `components/20_eval_config_types_overview.md` | This file consumes `eval_adapter_from_type`; `components/20` defines the registry |
| Scoring helper functions (`scoring_utils.py`) | `components/20_eval_config_types_overview.md` | This file shows the consumption pattern; `components/20` defines what moves |
| EvalConfig parsing routing + coexistence validators | `components/15_v1_v2_coexistence.md` | This file dispatches based on the parsed result; `components/15` defines parsing |
| Score provenance chain semantics | `components/85_observability_and_audit.md` | This file persists the EvalRun; `components/85` explains why that's sufficient |

---

## Opens

None. All 14 alignment_refs are covered. The `SkippedReason` enum from `components/85` is referenced, not redefined. No new skip values are needed beyond the six seeded there. No inconsistencies with siblings `10`, `15`, `20`, or `85` were found during authoring.
