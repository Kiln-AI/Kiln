---
status: complete
---

# Phase 4: Enhanced `llm_judge` + RAG Judge Templates

## Overview

This phase delivers three things:

1. **Async V2 contract** -- make `BaseV2Eval.evaluate()` async so the LLM-backed `llm_judge` adapter can `await` model calls. Update all 6 existing deterministic adapters and the runner call-site.
2. **`LlmJudgeEval` adapter** -- a new V2 adapter that renders a Jinja2 prompt template, invokes an LLM via `adapter_for_task()`, and dispatches scoring through `build_llm_as_judge_score()` or `build_g_eval_score()` from `scoring_utils.py`. Wires `forward_thinking_instructions=True` so reasoning-model judges receive eval criteria.
3. **6 RAG judge template factories** -- functions that return pre-configured `LlmJudgeProperties` for faithfulness, answer relevance, context relevance, context precision, hallucination, and answer correctness.

## Design Decisions

### Async `evaluate()`

`_run_v2_job` in `eval_runner.py` (line 344) is already `async`. It calls `evaluator.evaluate()` without `await` (line 425). Making `evaluate()` async is the cleanest single-dispatch path: one `await` added at the call-site, and all 6 deterministic adapters get a trivial `async def` with no internal awaits. This avoids a second dispatch path or `asyncio.run()` hacks.

### `forward_thinking_instructions` wiring

The existing chain: `GEvalTask` sets `thinking_instruction` on a `Task` -> `SimpleChainOfThoughtPromptBuilder.chain_of_thought_prompt()` reads it -> `base_adapter.py` line 661 extracts it as `cot_prompt` -> for reasoning models, line 688 passes it to `get_chat_formatter(strategy=single_turn_r1_thinking, thinking_instructions=cot_prompt)`. But `forward_thinking_instructions` is never passed, defaulting to `False`, so the instructions are silently dropped.

**Fix:** Add `forward_thinking_instructions: bool = False` to `AdapterConfig` (in `base_adapter.py` line 80). Plumb it through `get_chat_formatter_for_run()` at lines 688 and 697 so both reasoning-model and two-message-cot paths forward it. The V2 `LlmJudgeEval` adapter sets `AdapterConfig(forward_thinking_instructions=True)`. Legacy `GEval` is unchanged (keeps default `False`).

## Steps

### Step 1: Add `forward_thinking_instructions` to `AdapterConfig`

**File: `libs/core/kiln_ai/adapters/model_adapters/base_adapter.py`**

1a. Add field to `AdapterConfig` dataclass (after `return_on_tool_call`, around line 111):

```python
"""
When True, thinking instructions from the prompt builder's chain_of_thought_prompt()
are forwarded into the user message for reasoning models (via SingleTurnR1ThinkingFormatter).
Default False preserves legacy behavior where thinking instructions are silently dropped.
V2 llm_judge sets this to True so reasoning-model judges receive eval criteria.
"""
forward_thinking_instructions: bool = False
```

1b. In `get_chat_formatter_for_run()`, pass `self.adapter_config.forward_thinking_instructions` to all `get_chat_formatter()` calls that accept `thinking_instructions`. There are two:

- Line 688 (reasoning_capable branch): add `forward_thinking_instructions=self.adapter_config.forward_thinking_instructions`
- Line 697 (two_message_cot branch): add `forward_thinking_instructions=self.adapter_config.forward_thinking_instructions`

The `get_chat_formatter()` function (in `chat_formatter.py` line 394) already accepts `forward_thinking_instructions` and passes it to `SingleTurnR1ThinkingFormatter`. No changes needed there.

### Step 2: Make `BaseV2Eval.evaluate()` async

**File: `libs/core/kiln_ai/adapters/eval/base_v2_eval.py`**

2a. Change the abstract method signature:

```python
@abstractmethod
async def evaluate(
    self, eval_input: EvalTaskInput
) -> tuple[EvalScores, SkippedReason | None, str | None]:
```

**File: `libs/core/kiln_ai/adapters/eval/eval_runner.py`**

2b. At line 425, add `await`:

```python
scores, skipped_reason, skipped_detail = await evaluator.evaluate(eval_task_input)
```

**Files: all 6 deterministic adapters** -- change `def evaluate(` to `async def evaluate(` in each:

- `libs/core/kiln_ai/adapters/eval/v2_eval_exact_match.py` (line 18)
- `libs/core/kiln_ai/adapters/eval/v2_eval_pattern_match.py`
- `libs/core/kiln_ai/adapters/eval/v2_eval_contains.py`
- `libs/core/kiln_ai/adapters/eval/v2_eval_set_check.py`
- `libs/core/kiln_ai/adapters/eval/v2_eval_tool_call_check.py`
- `libs/core/kiln_ai/adapters/eval/v2_eval_step_count_check.py`

Each is a one-word change: `def evaluate(` -> `async def evaluate(`. No internal awaits needed.

**Files: all 6 deterministic adapter test files** -- for each test that calls `evaluator.evaluate(...)`, add `async def` + `await`. Specifically mark each test with `@pytest.mark.asyncio` (or use the project's `pytest-asyncio` auto mode if configured). Test files:

- `libs/core/kiln_ai/adapters/eval/test_v2_exact_match.py`
- `libs/core/kiln_ai/adapters/eval/test_v2_pattern_match.py`
- `libs/core/kiln_ai/adapters/eval/test_v2_contains.py`
- `libs/core/kiln_ai/adapters/eval/test_v2_set_check.py`
- `libs/core/kiln_ai/adapters/eval/test_v2_tool_call_check.py`
- `libs/core/kiln_ai/adapters/eval/test_v2_step_count_check.py`

Pattern: change `def test_*(self):` to `async def test_*(self):` and change `ExactMatchEval(cfg).evaluate(_inp())` to `await ExactMatchEval(cfg).evaluate(_inp())`.

### Step 3: Create `LlmJudgeEval` adapter

**New file: `libs/core/kiln_ai/adapters/eval/v2_eval_llm_judge.py`**

```python
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.eval.base_eval import BaseEval, model_and_provider_from_config
from kiln_ai.adapters.eval.base_v2_eval import BaseV2Eval
from kiln_ai.adapters.eval.eval_utils.scoring_utils import (
    build_g_eval_score,
    build_llm_as_judge_score,
)
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import check_required_vars
from kiln_ai.adapters.eval.g_eval import GEval
from kiln_ai.adapters.ml_model_list import (
    default_structured_output_mode_for_model_provider,
)
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.prompt_builders import PromptGenerators
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.eval import (
    EvalScores,
    EvalTaskInput,
    LlmJudgeProperties,
    SkippedReason,
)
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import StructuredOutputMode
from kiln_ai.utils.jinja_engine import _template_env


class _LlmJudgeTask(Task, parent_of={}):
    """Temporary Task for invoking an LLM judge via adapter_for_task().

    Pattern follows GEvalTask: creates an ephemeral Project/Task with the
    system prompt, thinking instruction, and output JSON schema derived
    from the parent Eval's output_scores.
    """

    def __init__(
        self,
        system_prompt: str,
        thinking_instruction: str | None,
        output_json_schema: str,
    ):
        tmp_project = Project(name="LlmJudge")
        super().__init__(
            name="LlmJudge Task",
            parent=tmp_project,
            instruction=system_prompt,
            thinking_instruction=thinking_instruction,
            output_json_schema=output_json_schema,
        )


class LlmJudgeEval(BaseV2Eval):
    """V2 adapter for llm_judge: invokes an LLM to score eval inputs.

    Supports two scoring modes:
    - LLM-as-Judge (g_eval=False): uses structured output directly.
    - G-Eval (g_eval=True): uses logprob-weighted scoring.

    The prompt_template is rendered with Jinja2 using the EvalTaskInput fields
    (final_message, trace, reference_data, task_input) as the template namespace.
    """

    async def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]:
        props = self.properties
        assert isinstance(props, LlmJudgeProperties)

        # 1. Check required_var expressions resolve
        skip, detail = check_required_vars(props.required_var, eval_input)
        if skip is not None:
            return {}, skip, detail

        # 2. Render the prompt template with EvalTaskInput fields
        namespace = eval_input.model_dump()
        rendered_prompt = _template_env.from_string(props.prompt_template).render(
            **namespace
        )

        # 3. Build the score schema from the parent Eval's output_scores
        parent_eval = self.eval_config.parent_eval()
        if parent_eval is None:
            raise ValueError("LlmJudgeEval requires a parent Eval with output_scores")
        output_json_schema = BaseEval.build_score_schema(
            parent_eval, allow_float_scores=False
        )

        # 4. Build the system prompt (default if not provided)
        system_prompt = props.system_prompt or (
            "Your job is to evaluate a model's performance on a task. "
            "Score the output according to the criteria provided."
        )

        # 5. Create ephemeral Task with system prompt, thinking instruction, schema
        judge_task = _LlmJudgeTask(
            system_prompt=system_prompt,
            thinking_instruction=props.thinking_instruction,
            output_json_schema=output_json_schema,
        )

        # 6. Resolve model and provider from LlmJudgeProperties
        model_name, provider = model_and_provider_from_config(self.eval_config)

        # 7. Configure structured output mode (disallow function_calling for g_eval)
        structured_output_mode = default_structured_output_mode_for_model_provider(
            model_name,
            provider,
            default=StructuredOutputMode.json_schema,
            disallowed_modes=[
                StructuredOutputMode.function_calling,
                StructuredOutputMode.function_calling_weak,
            ],
        )

        # 8. Request logprobs only for g_eval mode (10 is enough for all rating types)
        top_logprobs = 10 if props.g_eval else None

        # 9. Create adapter via adapter_for_task with forward_thinking_instructions=True
        adapter = adapter_for_task(
            judge_task,
            run_config_properties=KilnAgentRunConfigProperties(
                model_name=model_name,
                model_provider_name=provider,
                prompt_id=PromptGenerators.SIMPLE_CHAIN_OF_THOUGHT,
                structured_output_mode=structured_output_mode,
            ),
            base_adapter_config=AdapterConfig(
                allow_saving=False,
                top_logprobs=top_logprobs,
                forward_thinking_instructions=True,
            ),
        )

        # 10. Invoke the LLM
        _, run_output = await adapter.invoke_returning_run_output(rendered_prompt)

        # 11. Dispatch scoring
        if props.g_eval:
            geval_instance = GEval.__new__(GEval)
            return (
                build_g_eval_score(
                    run_output,
                    geval_instance.raw_output_from_logprobs,
                    geval_instance.metric_offsets,
                    geval_instance.g_eval_single_metric,
                ),
                None,
                None,
            )
        else:
            return (
                build_llm_as_judge_score(
                    run_output,
                    GEval.score_from_token_string.__func__,
                ),
                None,
                None,
            )
```

**Important implementation notes for the coding agent:**

- `model_and_provider_from_config(self.eval_config)` reads `eval_config.model_name` and `eval_config.model_provider`. The `LlmJudgeProperties` has `model_name` and `model_provider` fields. Verify these are surfaced on `EvalConfig` -- if `EvalConfig.model_name`/`model_provider` are separate top-level fields (not derived from properties), the adapter may need to read from `props.model_name` and `props.model_provider` directly and validate the provider name manually. Check `EvalConfig` model definition.
- For `score_from_token_string`: this is an instance method on `GEval` that reads from module-level `TOKEN_TO_SCORE_MAP`. The cleanest approach is to extract `score_from_token_string` as a standalone module-level function (or reimplement the 15-line lookup using `TOKEN_TO_SCORE_MAP` directly in a helper). Do NOT instantiate `GEval` (it requires eval_config + parent eval + task). The pseudocode above using `GEval.__new__` is illustrative -- the coding agent should extract or reimplement the function.
- For `build_g_eval_score` callbacks: similarly, `raw_output_from_logprobs`, `metric_offsets`, and `g_eval_single_metric` are instance methods on `GEval`. The coding agent should either: (a) extract these as standalone functions in `scoring_utils.py` or a new helper module, or (b) reimplement the logic inline. Option (a) is preferred for reuse and testability.

### Step 4: Extract GEval scoring helpers as standalone functions

**File: `libs/core/kiln_ai/adapters/eval/eval_utils/scoring_utils.py`** (extend existing file)

Extract or add these standalone functions so both `GEval` and `LlmJudgeEval` can use them without instantiating GEval:

4a. `score_from_token_string(token: str) -> float | None` -- lookup in `TOKEN_TO_SCORE_MAP` with the same cleanup logic as `GEval.score_from_token_string` (strip, unquote, lowercase, try float parse). ~15 lines.

4b. `raw_output_from_logprobs(run_output: RunOutput) -> str` -- concatenate `run_output.output_logprobs.content[*].token`. ~8 lines.

4c. `metric_offsets(raw_output: str, metrics: list[str]) -> dict[str, int]` -- find offset of each `"metric_name"` in raw JSON. ~15 lines.

4d. `g_eval_single_metric(run_output: RunOutput, metric: str, metric_offsets: dict[str, int], raw_output: str) -> float | None` -- scan logprobs in token range, call `rating_token_to_score`. ~20 lines.

4e. `rating_token_to_score(token_logprob: ChatCompletionTokenLogprob) -> float | None` -- weighted average of top logprobs for valid score tokens. ~30 lines.

All extracted from `GEval` methods (lines 368-540 of `g_eval.py`). Move `TOKEN_TO_SCORE_MAP` to `scoring_utils.py` and import it back in `g_eval.py`.

Then update `GEval` to delegate to these standalone functions (its methods become thin wrappers or are replaced entirely). This is a refactor-only change with no behavior difference.

Update `LlmJudgeEval` (Step 3) to call the standalone functions directly instead of the `GEval.__new__` workaround.

### Step 5: Register `LlmJudgeEval` in the adapter map

**File: `libs/core/kiln_ai/adapters/eval/registry.py`**

5a. Add import:

```python
from kiln_ai.adapters.eval.v2_eval_llm_judge import LlmJudgeEval
```

5b. Add entry to `_V2_ADAPTER_MAP`:

```python
V2EvalType.llm_judge: LlmJudgeEval,
```

### Step 6: Update `__init__.py` exports

**File: `libs/core/kiln_ai/adapters/eval/__init__.py`**

Add `v2_eval_llm_judge` to both the import list and `__all__`.

### Step 7: Create RAG judge template library

**New file: `libs/core/kiln_ai/adapters/eval/rag_judge_templates.py`**

Six factory functions, each returning a `LlmJudgeProperties` with a pre-written prompt template and appropriate `required_var` constraints. These are pure data -- no adapter logic.

Each function signature: `def <name>_template(model_name: str, model_provider: str) -> LlmJudgeProperties`.

The templates use the EvalTaskInput namespace variables: `final_message`, `trace`, `reference_data`, `task_input`.

**Canonical reference keys** (per component 29, section 2):

- `reference_data.retrieved_context` -- `list[str]`, the text chunks returned by the RAG retrieval system
- `reference_data.ground_truth_context` -- `list[str]`, the ideal source passages that should have been retrieved (optional, for Context Precision)
- `reference_data.reference_answer` -- `str`, the gold-standard answer for correctness checking

All six templates share these properties:

- **`g_eval: False`** -- standard structured-output scoring, not token-logprob scoring
- **Reasoning-then-verdict CoT** -- each prompt instructs the judge to reason step-by-step before producing a structured JSON verdict
- **Continuous 0-1 scoring** -- each template outputs a `score` field as a float between 0.0 and 1.0
- **Structured JSON output** -- each template defines a rich JSON output schema (claims arrays, reasoning, etc.) that goes beyond the simple score-only schema from `build_score_schema`

**Continuous scoring and `EvalOutputScore`:** Each template's `output_scores` uses `EvalOutputScore.type = TaskOutputRatingType.pass_fail`, which validates floats 0.0-1.0 inclusive (see `eval.py` `validate_scores`, lines 469-478). When `build_score_schema(eval, allow_float_scores=True)` is called with `pass_fail` type, it produces `{"type": "number", "minimum": 0, "maximum": 1}` -- the correct schema for continuous 0-1 scores.

**Scoring pipeline extension required:** The current `build_llm_as_judge_score()` in `scoring_utils.py` calls `score_from_token_fn(f"{score}")` which only handles discrete tokens via `TOKEN_TO_SCORE_MAP` (e.g., "pass" -> 1.0, "fail" -> 0.0, "3" -> 3.0). It cannot parse continuous floats like `0.73` -- `score_from_token_string("0.73")` returns `None`, causing `ValueError`. The RAG templates output structured JSON with a continuous `score` field. **Resolution:** Extend `score_from_token_string` to fall through to `float(token)` for raw numeric strings in the valid range, OR have `LlmJudgeEval` extract the `score` field directly from the structured output dict (bypassing `build_llm_as_judge_score`) when the output schema requests a number type. The coding agent should implement whichever approach is cleaner -- the key constraint is that a structured output containing `{"score": 0.73, "reasoning": "..."}` must produce `EvalScores = {"score": 0.73}`.

#### 7a. `faithfulness_template`

- **Purpose:** Measure the fraction of claims in the model's output that are supported by the retrieved context. Core hallucination-detection metric for RAG: "Did the model stick to what the retriever gave it?"
- **required_var:** `["reference_data.retrieved_context"]`
- **g_eval:** `False`
- **Prompt template uses:** `{{ task_input }}`, `{% for chunk in reference_data.retrieved_context %}[Chunk {{ loop.index }}]: {{ chunk }}{% endfor %}`, `{{ final_message }}`
- **Scoring formula:** `score = num_supported / num_total` (0 claims -> 1.0)
- **Structured JSON output:**
  ```json
  {
    "claims": [{"claim": "<text>", "supported": true, "evidence": "<quote or null>"}],
    "num_supported": "<int>",
    "num_total": "<int>",
    "score": "<float 0-1>",
    "reasoning": "<1-2 sentence summary>"
  }
  ```
- **thinking_instruction:** "Think step by step about whether each claim in the answer is supported by the provided context."

#### 7b. `answer_relevance_template`

- **Purpose:** Evaluate whether the model's output actually addresses the user's query. Detects irrelevant, off-topic, or evasive responses.
- **required_var:** `["task_input"]` -- no reference keys needed, only `task_input` + `final_message`
- **g_eval:** `False`
- **Prompt template uses:** `{{ task_input }}` and `{{ final_message }}`
- **Scoring formula:** Rubric-based 0-1 continuous (1.0 = directly addresses query; 0.0 = completely irrelevant)
- **Structured JSON output:**
  ```json
  {
    "user_intent": "<summary of what user is asking>",
    "addresses_question": "<assessment>",
    "completeness": "<assessment>",
    "conciseness": "<assessment>",
    "score": "<float 0-1>",
    "reasoning": "<1-2 sentence summary>"
  }
  ```
- **thinking_instruction:** "Think step by step about whether the response addresses the user's query, considering relevance, completeness, and conciseness."

#### 7c. `context_relevance_template`

- **Purpose:** Evaluate whether the chunks in `retrieved_context` are relevant to the user's query. Measures retriever quality (query-context alignment), not generator quality.
- **required_var:** `["task_input", "reference_data.retrieved_context"]`
- **g_eval:** `False`
- **Prompt template uses:** `{{ task_input }}`, `{% for chunk in reference_data.retrieved_context %}[Chunk {{ loop.index }}]: {{ chunk }}{% endfor %}`
- **Scoring formula:** `score = num_relevant / num_total`
- **Structured JSON output:**
  ```json
  {
    "information_need": "<summary of what info is needed>",
    "chunk_evaluations": [{"chunk_index": 1, "relevant": true, "reason": "<why>"}],
    "num_relevant": "<int>",
    "num_total": "<int>",
    "score": "<float 0-1>",
    "reasoning": "<1-2 sentence summary>"
  }
  ```
- **thinking_instruction:** "Think step by step about whether each retrieved chunk contains information relevant to answering the user's query."

#### 7d. `context_precision_template`

- **Purpose:** Measure what fraction of `retrieved_context` chunks were actually useful for producing a correct answer. Optionally compares against `ground_truth_context` if available for a stronger signal.
- **required_var:** `["task_input", "reference_data.retrieved_context"]` -- note: `ground_truth_context` is optional, guarded by `{% if reference_data.ground_truth_context %}` in the template, NOT listed in `required_var`
- **g_eval:** `False`
- **Prompt template uses:** `{{ task_input }}`, `{% for chunk in reference_data.retrieved_context %}`, `{% if reference_data.ground_truth_context %}{% for chunk in reference_data.ground_truth_context %}` (conditional)
- **Scoring formula:** `score = num_useful / num_total`
- **Structured JSON output:**
  ```json
  {
    "mode": "with_ground_truth|without_ground_truth",
    "chunk_evaluations": [{"chunk_index": 1, "useful": true, "reason": "<why>"}],
    "num_useful": "<int>",
    "num_total": "<int>",
    "score": "<float 0-1>",
    "reasoning": "<1-2 sentence summary>"
  }
  ```
- **thinking_instruction:** "Think step by step about whether each retrieved chunk is useful for producing a correct answer to the user's query."

#### 7e. `hallucination_template`

- **Purpose:** Detect claims that contradict or fabricate content not present in the retrieved context. Inverse framing of Faithfulness: higher score = more hallucination = worse. 0.0 = no hallucination = best.
- **required_var:** `["reference_data.retrieved_context"]`
- **g_eval:** `False`
- **Prompt template uses:** `{{ task_input }}`, `{% for chunk in reference_data.retrieved_context %}[Chunk {{ loop.index }}]: {{ chunk }}{% endfor %}`, `{{ final_message }}`
- **Scoring formula:** `score = num_hallucinated / num_total` (INVERTED: 0 = best, 1 = worst). 0 claims -> 0.0.
- **Structured JSON output:**
  ```json
  {
    "claims": [{"claim": "<text>", "classification": "grounded|hallucinated_contradiction|hallucinated_fabrication", "evidence": "<explanation>"}],
    "num_hallucinated": "<int>",
    "num_total": "<int>",
    "score": "<float 0-1>",
    "reasoning": "<1-2 sentence summary>"
  }
  ```
- **thinking_instruction:** "Think step by step about whether each claim in the answer is grounded in the retrieved context, contradicts it, or is fabricated."

#### 7f. `answer_correctness_template`

- **Purpose:** Evaluate the factual accuracy and completeness of the model's output compared to a gold-standard reference answer. Checks whether the final answer is actually right, independent of what context was available.
- **required_var:** `["reference_data.reference_answer", "task_input"]`
- **g_eval:** `False`
- **Prompt template uses:** `{{ task_input }}`, `{{ reference_data.reference_answer }}`, `{{ final_message }}`
- **Scoring formula:** Rubric-based 0-1 continuous weighted by core-fact coverage, contradictions, and incorrect additions
- **Structured JSON output:**
  ```json
  {
    "reference_facts": [{"fact": "<text>", "type": "core|supporting", "status": "matches|contradicts|omits", "response_text": "<quote or null>"}],
    "fabricated_content": [{"claim": "<text>", "classification": "correct_elaboration|incorrect_addition"}],
    "num_core_matched": "<int>",
    "num_core_total": "<int>",
    "num_contradictions": "<int>",
    "num_incorrect_additions": "<int>",
    "score": "<float 0-1>",
    "reasoning": "<1-2 sentence summary>"
  }
  ```
- **thinking_instruction:** "Think step by step about the factual correctness of the response compared to the reference answer, checking for matches, contradictions, omissions, and fabricated content."

**Each factory function:**

```python
def faithfulness_template(model_name: str, model_provider: str) -> LlmJudgeProperties:
    return LlmJudgeProperties(
        model_name=model_name,
        model_provider=model_provider,
        system_prompt="You are an expert fact-checker evaluating whether a response is faithful to its source context.",
        prompt_template=_FAITHFULNESS_PROMPT,
        required_var=["reference_data.retrieved_context"],
        thinking_instruction="Think step by step about whether each claim in the answer is supported by the provided context.",
        g_eval=False,
    )
```

The `_FAITHFULNESS_PROMPT` (and similar for each template) are module-level string constants with the full Jinja2 prompt text from component 29 section 3. The prompts are production-quality: they include step-by-step evaluation instructions, explicit scoring formulas, edge-case handling, and the exact JSON output structure. Copy the full prompt text from component 29 -- do not simplify or abbreviate.

**Important:** The prompt templates reference fields from `EvalTaskInput.model_dump()` namespace. The available variables are: `final_message` (str), `trace` (list[dict] | None), `reference_data` (dict | None), `task_input` (str | None). Required keys are validated via `required_var` + `check_required_vars()` before rendering, so the template can assume they exist. Optional keys (like `ground_truth_context` in Context Precision) must be guarded with `{% if reference_data.ground_truth_context %}` and are NOT listed in `required_var`.

## Tests

All tests mock model calls -- no real network requests.

### Test file: `libs/core/kiln_ai/adapters/eval/test_v2_eval_llm_judge.py`

Use the same `_make_config` / `_inp` pattern from `test_v2_exact_match.py`, adapted for `LlmJudgeProperties`. Mock `adapter_for_task` and the adapter's `invoke_returning_run_output` to return controlled `RunOutput` objects.

#### Test class: `TestLlmJudgeRequiredVars`

- **`test_missing_required_var_skips`**: Configure `required_var=["reference_data.context"]`, pass `eval_input` with `reference_data=None`. Assert returns `({}, SkippedReason.extraction_failed, <detail>)`.
- **`test_present_required_var_proceeds`**: Configure `required_var=["task_input"]`, pass `eval_input` with `task_input="hello"`. Assert no skip. (Mock the LLM call to return valid scores.)

#### Test class: `TestLlmJudgeTemplateRendering`

- **`test_template_renders_final_message`**: `prompt_template="Output: {{ final_message }}"`. Assert the rendered prompt passed to `invoke_returning_run_output` is `"Output: Hello world"`.
- **`test_template_renders_reference_data`**: `prompt_template="Ref: {{ reference_data.answer }}"`, `reference_data={"answer": "42"}`. Assert rendered = `"Ref: 42"`.
- **`test_template_renders_trace`**: `prompt_template="Trace: {{ trace[0].content }}"`, `trace=[{"content": "step1"}]`. Assert rendered = `"Trace: step1"`.
- **`test_template_strict_undefined_raises`**: `prompt_template="{{ nonexistent_var }}"`. Assert raises (Jinja2 StrictUndefined). This validates the template env catches bad templates at render time.

#### Test class: `TestLlmJudgeLlmAsJudgeScoring`

Mock `adapter_for_task` to return a mock adapter. Mock `invoke_returning_run_output` to return a `RunOutput` with `output={"score_a": "pass"}`.

- **`test_llm_as_judge_pass`**: Assert scores = `{"score_a": 1.0}`.
- **`test_llm_as_judge_fail`**: output=`{"score_a": "fail"}`. Assert scores = `{"score_a": 0.0}`.
- **`test_llm_as_judge_five_star`**: output=`{"score_a": "3"}`. Assert scores = `{"score_a": 3.0}`.
- **`test_llm_as_judge_invalid_token_raises`**: output=`{"score_a": "banana"}`. Assert raises ValueError.

#### Test class: `TestLlmJudgeGEvalScoring`

Configure `g_eval=True` in properties. Mock adapter to return `RunOutput` with `output={"score_a": "3"}` and appropriate `output_logprobs`. Use mock `ChatCompletionTokenLogprob` objects.

- **`test_g_eval_weighted_score`**: Provide logprobs with multiple rating tokens. Assert the returned score is the probability-weighted average (not just the top token).
- **`test_g_eval_missing_logprobs_raises`**: `output_logprobs=None`. Assert raises RuntimeError.

#### Test class: `TestLlmJudgeAdapterConfig`

- **`test_adapter_config_has_forward_thinking`**: Patch `adapter_for_task`, capture the `base_adapter_config` argument. Assert `forward_thinking_instructions=True`.
- **`test_adapter_config_logprobs_g_eval`**: `g_eval=True`. Assert `top_logprobs=10`.
- **`test_adapter_config_logprobs_llm_judge`**: `g_eval=False`. Assert `top_logprobs=None`.
- **`test_adapter_config_allow_saving_false`**: Assert `allow_saving=False`.

#### Test class: `TestLlmJudgeSystemPrompt`

- **`test_custom_system_prompt`**: Set `system_prompt="Custom instructions"`. Capture the Task created. Assert its instruction matches.
- **`test_default_system_prompt`**: Set `system_prompt=None`. Assert a default system prompt is used.

#### Test class: `TestLlmJudgeThinkingInstruction`

- **`test_thinking_instruction_forwarded`**: Set `thinking_instruction="Think step by step"`. Capture the Task. Assert `thinking_instruction` is set on the task.
- **`test_no_thinking_instruction`**: Set `thinking_instruction=None`. Assert task's `thinking_instruction` is None.

### Test file: `libs/core/kiln_ai/adapters/eval/test_rag_judge_templates.py`

All tests mock model calls -- no real network requests.

#### Test class: `TestRagTemplateProperties`

One test per factory function validating the returned `LlmJudgeProperties`:

- **`test_faithfulness_template`**: Assert `required_var=["reference_data.retrieved_context"]`, `g_eval=False`, `thinking_instruction` is not None.
- **`test_answer_relevance_template`**: Assert `required_var=["task_input"]`, `g_eval=False`.
- **`test_context_relevance_template`**: Assert `required_var` includes `"task_input"` and `"reference_data.retrieved_context"`, `g_eval=False`.
- **`test_context_precision_template`**: Assert `required_var` includes `"task_input"` and `"reference_data.retrieved_context"`, `g_eval=False`. Assert `"reference_data.ground_truth_context"` is NOT in `required_var` (it is optional, guarded by `{% if %}` in the prompt).
- **`test_hallucination_template`**: Assert `required_var=["reference_data.retrieved_context"]`, `g_eval=False`.
- **`test_answer_correctness_template`**: Assert `required_var` includes `"reference_data.reference_answer"` and `"task_input"`, `g_eval=False`.

#### Test class: `TestRagTemplateCompilation`

For each of the 6 factory functions:

- **`test_<template>_compiles`**: Call factory with dummy model_name/provider, then run `compile_template_or_raise(props.prompt_template)` to verify the Jinja2 template syntax is valid.
- **`test_<template>_not_useless`**: Assert the `prompt_template` contains `{{` or `{%` (the useless-template check from `validate_v2_templates_and_expressions`, which rejects templates with no Jinja2 expressions).

#### Test class: `TestRagTemplateEvalConfig`

For each of the 6 factory functions:

- **`test_<template>_builds_valid_eval_config`**: Construct a minimal `Eval` with `output_scores=[EvalOutputScore(name="score", type=TaskOutputRatingType.pass_fail, ...)]`, then build an `EvalConfig` using the factory's returned `LlmJudgeProperties`. Assert `EvalConfig` validation passes (calls `validate_v2_templates_and_expressions` internally). This proves the template integrates correctly with the eval datamodel.

#### Test class: `TestRagTemplateScoringSmoke`

For each of the 6 factory functions, a mocked end-to-end scoring smoke test. Mock `adapter_for_task` to return a mock adapter whose `invoke_returning_run_output` returns a `RunOutput` with the template's structured JSON output (e.g., for Faithfulness: `{"claims": [...], "num_supported": 3, "num_total": 4, "score": 0.75, "reasoning": "..."}`).

- **`test_<template>_parses_continuous_score`**: Run the eval with the mocked adapter. Assert the resulting `EvalScores` dict contains the continuous float score (e.g., `{"score": 0.75}`). This validates the continuous scoring pipeline works end-to-end for each template's structured output shape.

#### Test class: `TestRagTemplateMissingRequiredKey`

For each of the 6 factory functions:

- **`test_<template>_skips_on_missing_required_var`**: Construct an `EvalTaskInput` that is missing the template's required reference data (e.g., for Faithfulness: `reference_data=None` or `reference_data={}` so `retrieved_context` is absent). Call `check_required_vars(props.required_var, eval_input)`. Assert it returns `(SkippedReason.extraction_failed, <detail>)` -- proving the template correctly skips rather than crashing when data is missing.

### Test file: `libs/core/kiln_ai/adapters/eval/test_forward_thinking_instructions.py`

#### Test class: `TestAdapterConfigForwardThinking`

- **`test_forward_thinking_default_false`**: `AdapterConfig()` -> assert `forward_thinking_instructions is False`.
- **`test_forward_thinking_set_true`**: `AdapterConfig(forward_thinking_instructions=True)` -> assert `forward_thinking_instructions is True`.

#### Test class: `TestGetChatFormatterForRunForwardThinking`

These test that `get_chat_formatter_for_run` actually passes `forward_thinking_instructions` through. Requires constructing a `BaseAdapter` subclass or using the `LiteLlmAdapter` with mocked model provider.

- **`test_reasoning_model_forwards_thinking_when_true`**: Create adapter with `AdapterConfig(forward_thinking_instructions=True)`, mock `model_provider().reasoning_capable=True`, mock `prompt_builder.chain_of_thought_prompt()` to return `"Think carefully"`. Call `get_chat_formatter_for_run(input)`. Assert the returned formatter is `SingleTurnR1ThinkingFormatter` with `forward_thinking_instructions=True`.
- **`test_reasoning_model_does_not_forward_when_false`**: Same but `forward_thinking_instructions=False`. Assert formatter has `forward_thinking_instructions=False`.

### Test file: `libs/core/kiln_ai/adapters/eval/eval_utils/test_scoring_utils_standalone.py`

(Only if Step 4 extracts standalone functions)

- **`test_score_from_token_string_known_tokens`**: "pass" -> 1.0, "fail" -> 0.0, "critical" -> -1.0, "3" -> 3.0.
- **`test_score_from_token_string_variations`**: `'"pass"'` -> 1.0, `" PASS"` -> 1.0, `"1.0"` -> 1.0.
- **`test_score_from_token_string_unknown`**: `"banana"` -> None.
- **`test_raw_output_from_logprobs`**: Mock logprobs content with tokens ["a", "b", "c"]. Assert result = "abc".
- **`test_metric_offsets_single`**: raw = `'{"score_a": 1}'`. Assert `{"score_a": 1}` (offset of `"score_a"`).
- **`test_metric_offsets_duplicate_raises`**: raw with `score_a` appearing twice. Assert raises ValueError.

### Existing test updates

**All 6 existing deterministic adapter test files** need `async def` + `await` changes per Step 2. No new test cases, just mechanical async conversion.

## Out of Scope

- **`code_eval` adapter** -- Phase 5.
- **UI for creating/viewing llm_judge configs** -- Phase 6.
- **Changing legacy `GEval` behavior** -- `GEval` continues to use `forward_thinking_instructions=False` (its default). Only V2 `LlmJudgeEval` opts in.
- **Template management UI** (saving/loading RAG templates from the UI) -- not in this phase.
- **Multi-turn eval input support** -- V2 evals skip multi-turn inputs with `incompatible_input_shape` (unchanged).
- **Custom user-defined RAG templates** -- the 6 templates are built-in factories. Users configure `LlmJudgeProperties` directly for custom prompts.
- **Composite/threshold/embedding eval types** -- deferred per implementation_plan.md.
