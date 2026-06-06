---
status: complete
approved: true
alignment_refs: [A1.4, A2.2, A2.10, C.11c, D.4, K.2, H.32a]
opens: []
summary: Enhanced V2 llm_judge -- per-criterion pass/fail verdicts, g_eval toggle, Jinja2 prompt_template, required_var, system_prompt, thinking_instruction, structured-output coupling, trace condensation, reference-data templating, V1-to-V2 wrapping shape, scoring-helper consumption.
---

# Type: LLM Judge (`llm_judge`)

**Author:** sub-agent dispatched 2026-06-03 for Stage 4 gap-fill
**Status:** complete

## TL;DR

- V2 ships a single judge type `V2EvalType.llm_judge` unifying V1's `g_eval` and `llm_as_judge` under one properties class with a `g_eval: bool` toggle (A2.2).
- The adapter (`LlmJudgeAdapter`) subclasses the existing `BaseEval` with no fork (C.11c), reads model fields from `LlmJudgeProperties` directly (A2.10), and consumes extracted scoring helpers from `scoring_utils.py` (H.32a).
- Prompt construction uses user-authored Jinja2 `prompt_template` + `required_var` + optional `system_prompt` + optional `thinking_instruction` via the general `JinjaInputTransform` infrastructure (D.4). No hardcoded f-string templates.
- Per-criterion pass/fail verdicts are a first-class pattern using per-case criteria stored in `reference_data.llm_judge_criteria` (A1.4) and iterated in the template.
- K.2 V1-to-V2 Jinja2 wrapping shape is fully specified: the Copilot path translates V1 `eval_steps` + `task_description` into a complete `prompt_template` string at creation time.

---

## 1. Properties shape (`LlmJudgeProperties`)

This is the authoritative V2 properties schema for the `llm_judge` type. The source-of-truth field names are here; the A2.1 reference snippet in reference/ALIGNMENT.md uses older names (`g_eval_mode`) that are historical.

```python
class LlmJudgeProperties(BaseModel):
    type: Literal["llm_judge"] = "llm_judge"

    # Model selection -- on properties, NOT on root EvalConfig (A2.10)
    model_name: str
    model_provider: str

    # Prompt surface -- user-authored Jinja2 (D.1, D.2)
    prompt_template: str                    # REQUIRED; Jinja2 template
    system_prompt: str | None = None        # static string; see section 6
    thinking_instruction: str | None = None # see section 7

    # Pre-check expressions -- skip case if any evaluates to None/Undefined
    required_var: list[str] = []            # Jinja2 expressions (D.3)

    # Scoring mode toggle (A2.2)
    g_eval: bool = False                    # renamed from g_eval_mode; components/40 section 3.1 authoritative
```

### 1.1. Field semantics

| Field | Type | Purpose |
|---|---|---|
| `model_name` | `str` | LiteLLM model identifier for the judge LLM (e.g. `claude-sonnet-4-6`, `gpt-4o`). |
| `model_provider` | `str` | Provider key (e.g. `anthropic`, `openai`). Read directly by the adapter, not via `BaseEval.model_and_provider()` (A2.10). |
| `prompt_template` | `str` | Jinja2 template rendered against `EvalTaskInput` (section 2). This IS the judge prompt. All criteria, scoring rubric, output formatting instructions go here. |
| `system_prompt` | `str \| None` | Static system message for the judge task. Defaults resolved at creation time per section 6. |
| `thinking_instruction` | `str \| None` | CoT instruction appended by `TwoMessageCotFormatter` (non-reasoning models) or forwarded via the `forward_thinking_instructions=True` fix (reasoning models, `components/05`). Defaults resolved at creation time per section 7. |
| `required_var` | `list[str]` | Jinja2 expressions pre-checked via `extract()` before template rendering. If any evaluates to `None`/`Undefined`, the case is skipped with `skipped_reason: extraction_failed` + `skipped_detail: "<expr>"` per C.runner.1. |
| `g_eval` | `bool` | `False` = structured-output judge (function_calling allowed, no logprobs). `True` = G-Eval logprob-weighted scoring (function_calling disallowed, `top_logprobs=10`). See section 4. |

### 1.2. No separate criteria / eval_steps field

V1 carried criteria as `eval_steps: list[str]` on the raw dict properties. V2 has no separate field -- criteria text goes directly into the `prompt_template`. The builder UX populates the full template at creation time (K.1, K.2). This is deliberate: the Jinja2 template is the single source of truth for what the judge sees.

### 1.3. No `template_vars` field

Templates access `EvalTaskInput` fields directly as top-level variables (`{{ final_message }}`, `{{ trace }}`, `{{ reference_data }}`, `{{ task_input }}`). For DRYing repeated expressions, use Jinja2's `{% set %}`. See `components/40` section 2.

### 1.4. No `data_source` / `evaluation_data_type` field

V1's `evaluation_data_type` (Eval-level) is superseded per A2.3. V2 `llm_judge` declares its data needs through `prompt_template` variable references and `required_var` expressions. The runner extracts data per-config, not via a shared Eval-level switch. This unlocks V1 Pain Point 6: one Eval can mix an `llm_judge` config reading `trace` and an `exact_match` config reading a field path.

---

## 2. Per-case execution flow

This section specifies the `LlmJudgeAdapter.run_eval` sequence. Each step references the infrastructure it consumes.

### 2.1. EvalTaskInput assembly

The eval runner (owned by `components/45`) assembles an `EvalTaskInput` per case from the `EvalInput` + the `TaskRun` being evaluated. For V2 EvalConfigs consuming TaskRun-source data (B2.1 runtime translation), the runner synthesizes an in-memory `EvalInput` first.

```python
# EvalTaskInput (defined in components/40 section 2)
class EvalTaskInput(BaseModel):
    final_message: str | dict[str, Any]
    trace: list[ChatCompletionMessageParam] | None = None
    reference_data: dict[str, JsonValue] | None = None
    task_input: str | dict[str, Any]
```

### 2.2. Required-var pre-check

Before template rendering, the adapter pre-checks each `required_var` expression via `extract(expr, eval_task_input.model_dump())` from the prereq infra (`components/06`). If any returns `None` or `Undefined`, the case is skipped with `skipped_reason: extraction_failed` + `skipped_detail: "<expr>"`. No template render, no inference. This composes with C.runner.1 skip semantics.

Example: `required_var=["reference_data.reference_answer"]` ensures a case without reference data is skipped before an LLM call is wasted.

### 2.3. RunConfig construction

The adapter constructs an eval task `RunConfig` with:

```python
RunConfig(
    input_transform=JinjaInputTransform(template=self.eval_config.properties.prompt_template),
    # system_prompt, thinking_instruction, model selection handled via task/adapter infra
)
```

The `prompt_template` lives on `LlmJudgeProperties` (immutable snapshot per `components/40` section 1.3) and is copied into the RunConfig at invocation time. The EvalConfig is the source of truth; RunConfig is ephemeral.

### 2.4. Task invocation

The adapter invokes through Kiln's task infrastructure (D.4):

1. Template rendered against `eval_task_input.model_dump()` by `JinjaInputTransform`.
2. Chat formatter applies (`TwoMessageCotFormatter` for non-reasoning, `SingleTurnR1ThinkingFormatter` with `forward_thinking_instructions=True` for reasoning models per `components/05`).
3. Structured output mode selected via `default_structured_output_mode_for_model_provider()`.
4. Score schema built from `Eval.output_scores` via `BaseEval.build_score_schema()`.
5. Inference produces a structured score response.

### 2.5. Score parsing

Score parsing dispatches on the `g_eval` flag:

```python
from kiln_ai.adapters.eval.scoring_utils import (
    build_llm_as_judge_score,
    build_g_eval_score,
)

if self.eval_config.properties.g_eval:
    scores = build_g_eval_score(run_output)
else:
    scores = build_llm_as_judge_score(run_output)
```

Both functions are consumed from `scoring_utils.py` (H.32a, section 5).

---

## 3. Per-criterion pass/fail verdicts (A1.4)

### 3.1. Pattern

Per-case criteria stored as `reference_data.llm_judge_criteria` (a `list[str]`) on `EvalInput.reference` are iterated in the `prompt_template` using Jinja2's `{% for %}` loop. The structured output schema (built from `Eval.output_scores`) defines one boolean or rating dimension per criterion.

This is the reference pattern from `components/50` section 5.3:

```python
# EvalInput.reference:
{
    "llm_judge_criteria": [
        "Response correctly identifies the root cause",
        "Response suggests at least one actionable fix",
        "Response does not hallucinate error codes"
    ]
}

# LlmJudgeProperties:
LlmJudgeProperties(
    prompt_template="""\
Evaluate the following response against each criterion.
For each criterion, provide a pass/fail verdict with brief reasoning.

Criteria:
{% for criterion in reference_data.llm_judge_criteria %}
{{ loop.index }}. {{ criterion }}
{% endfor %}

Response to evaluate:
{{ final_message }}
""",
    required_var=["reference_data.llm_judge_criteria"],
    model_name="claude-sonnet-4-6",
    model_provider="anthropic",
)
```

### 3.2. Structured output coupling

The `Eval.output_scores` defines the score dimensions the judge must produce. For per-criterion verdicts, the output_scores list includes one entry per criterion:

```python
Eval(
    output_scores=[
        EvalOutputScore(name="criterion_1", type="pass_fail"),
        EvalOutputScore(name="criterion_2", type="pass_fail"),
        EvalOutputScore(name="criterion_3", type="pass_fail"),
    ]
)
```

`BaseEval.build_score_schema()` generates the JSON schema that enforces the judge's structured output. The template enumerates criteria; the schema constrains the response shape. Both are immutable on the EvalConfig snapshot, ensuring reproducibility.

### 3.3. Global vs. per-case criteria

A1.4 rules out "5 global checks PLUS case 47 has 3 extra checks" as a first-class pattern. The answer is to split case 47 into its own Eval (per "many small evals" philosophy, A0.2). Workarounds exist (hardcode global criteria in the template, conditionally append per-case extras via `{% if reference_data.extra_criteria %}`), but they are user-authored, not framework-supported.

### 3.4. Variable-length per-case criteria and output_scores

When different EvalInputs have different numbers of criteria in `reference_data.llm_judge_criteria`, the `output_scores` schema is fixed at the Eval level. Two patterns handle this:

**Pattern A: Fixed-dimension scoring with criteria text varying.** `output_scores` has a fixed number of dimensions (e.g., `overall_quality`, `factual_accuracy`, `completeness`). The criteria text in `reference_data.llm_judge_criteria` provides per-case guidance for each dimension, but the dimensions themselves are constant. This is the simpler, recommended pattern.

**Pattern B: N-criterion verdicts.** For true per-case criterion counts, the `output_scores` must accommodate the maximum count, and criteria positions must be stable across the dataset. Alternatively, use a single aggregate score with per-criterion reasoning in `intermediate_outputs`. This is an advanced pattern -- most users should use Pattern A or split into separate Evals.

---

## 4. `g_eval` scoring mode (A2.2)

### 4.1. Mode semantics

| Aspect | `g_eval=False` (default) | `g_eval=True` |
|---|---|---|
| Scoring method | Structured output (function_calling or json_schema mode) | G-Eval token-logprob weighting |
| `top_logprobs` | Not requested | `10` |
| `function_calling` | Allowed (broadens model support) | Disallowed (logprob-weighted scoring requires JSON in assistant content where token positions are findable) |
| Structured output mode | `default_structured_output_mode_for_model_provider()` | `json_schema` only (not `function_calling`) |
| Score extraction | `build_llm_as_judge_score(run_output)` from `scoring_utils.py` | `build_g_eval_score(run_output)` from `scoring_utils.py` |

### 4.2. V1 equivalence

`g_eval=False` is the V2 equivalent of V1 `EvalConfigType.llm_as_judge`. `g_eval=True` is the V2 equivalent of V1 `EvalConfigType.g_eval`. The V1 type-level distinction becomes a boolean toggle within the unified `llm_judge` type.

### 4.3. Model compatibility

Not all models support `top_logprobs`. When `g_eval=True` and the selected model does not support logprobs, the adapter should fail fast at invocation time with a clear error message rather than silently producing incorrect scores. This is an implementation-time validation (not a save-time validation, since model capabilities can change).

---

## 5. Scoring-helper consumption (H.32a)

### 5.1. What `LlmJudgeAdapter` consumes from `scoring_utils.py`

`scoring_utils.py` (extracted from GEval per `components/20` section 4) provides three seams:

| Function | Purpose | Used when |
|---|---|---|
| `build_llm_as_judge_score(run_output) -> EvalScores` | Parses structured output into score dict; maps values through `score_from_token_string()` | `g_eval=False` |
| `build_g_eval_score(run_output) -> EvalScores` | Full logprob scoring pipeline: `g_eval_single_metric()`, `rating_token_to_score()`, `raw_output_from_logprobs()`, `metric_offsets()`, `token_search_range()` | `g_eval=True` |
| `score_from_token_string()` + `TOKEN_TO_SCORE_MAP` | Token-to-numeric-score mapping | Both (via the above) |

### 5.2. What `LlmJudgeAdapter` does NOT share with GEval

| GEval seam | Why NOT shared |
|---|---|
| `GEvalTask` construction (`g_eval.py:44-81`) | V1-specific: reads V1 raw dict properties. V2 uses Jinja2 templates + `JinjaInputTransform` (D.2). |
| `generate_*_run_description` f-strings (`g_eval.py:121-247`) | Replaced entirely by user-authored Jinja2 `prompt_template` (D.1). |
| `model_and_provider()` | Extracted to separate helper per A2.10. V2 reads `properties.model_name`/`.model_provider` directly. |

### 5.3. `BaseEval.build_score_schema()`

Already class-level on `BaseEval` (`base_eval.py:105-184`), no V1 coupling. Inherited by `LlmJudgeAdapter` cleanly. Generates the JSON schema for structured output from `Eval.output_scores`.

---

## 6. `system_prompt` handling

### 6.1. Immutable snapshot at creation time

Per `components/40` section 1.3, EvalConfigs are full snapshots. Defaults are resolved and saved at creation time, never applied at runtime.

### 6.2. Resolution: always-system-message + default (RESOLVED)

Per `components/40` section 7.1 (resolved 2026-06-03): V2 `llm_judge` **always sends a system message**. When the user doesn't supply a `system_prompt`, the builder writes a default (`"You are an evaluator."`) into the EvalConfig's `system_prompt` field at creation time. No Kiln core change is required.

The `system_prompt` field is **NOT a builder-UI field** -- it is set by the default and only adjustable via the code/library API for power users. This keeps the builder simple while preserving full control.

### 6.3. Static string, not a template

`system_prompt` is a plain string, not a Jinja2 template. It does not participate in `JinjaInputTransform` rendering. Rationale: system messages are static context-setting ("You are a quality evaluator"), not data-dependent. Users wanting dynamic system messages can place that content in the `prompt_template`.

---

## 7. `thinking_instruction` handling

### 7.1. Default resolution

Per `components/40` section 7.2: if `None` at creation, the V2 builder writes Kiln's current default (`"Think step by step, explaining your reasoning."` from `prompt_builders.py:294-305`) into the EvalConfig at creation time. This ensures the saved config is a full snapshot.

### 7.2. Reasoning model path

V2 `llm_judge` depends on `components/05_prereq_thinking_formatter_fix.md`. When the judge model is reasoning-capable (o3, DeepSeek-R1, Claude reasoning), `SingleTurnR1ThinkingFormatter` receives `forward_thinking_instructions=True` so the `thinking_instruction` is appended to the user message body rather than silently dropped. This is a Kiln core fix shipped as a standalone commit before V2 `llm_judge` lands.

### 7.3. Cosmetic redundancy

Users who write CoT framing into their `prompt_template` also get the saved `thinking_instruction` appended by the formatter. This is cosmetic redundancy (not broken). Users who want to avoid it set a minimal `thinking_instruction` or leave it at the default.

---

## 8. Trace condensation

### 8.1. Scope

Trace condensation refers to pre-processing the `trace` variable before it reaches the judge's `prompt_template`. Kintsugi proved this valuable (`reports/kintsugi_synthesis.md`, `reports/kintsugi_perf_tricks.md` sections 2, 4): system prompt stripping, tool response truncation, progressive shrink.

### 8.2. V2.0 approach: template-driven

V2.0 does NOT ship a separate trace condensation pipeline or config fields (`tool_response_limit`, `progressive_shrink`). Instead, the Jinja2 template handles condensation natively:

```jinja
{# Strip system messages, truncate tool responses #}
{% for msg in trace %}
{% if msg.role != 'system' %}
{% if msg.role == 'tool' %}
Tool response ({{ msg.name }}): {{ msg.content[:500] }}
{% else %}
{{ msg.role }}: {{ msg.content }}
{% endif %}
{% endif %}
{% endfor %}
```

This is sufficient for V2.0. Template-driven condensation gives users full control over what the judge sees without adding new config fields. The RAG templates in `components/29` demonstrate this pattern.

### 8.3. Future: config-driven condensation (post-V2)

If template-driven condensation proves too verbose or error-prone, a future version can add optional condensation config fields to `LlmJudgeProperties` (e.g., `trace_condensation: TraceCondensationConfig | None = None`). The architectural seam is the `EvalTaskInput.trace` assembly step in the runner -- a condensation pass can be inserted between assembly and template rendering without changing the adapter interface.

---

## 9. Reference-data templating

### 9.1. Access pattern

Reference data from `EvalInput.reference` is exposed as `reference_data` in the `EvalTaskInput` (per `components/40` section 2, `components/50` section 6). Templates access it as `{{ reference_data.<key> }}`.

### 9.2. Required vs optional reference keys

**Required references:** Declared via `required_var`. Example: `required_var=["reference_data.reference_answer"]`. Cases without the key are skipped (C.runner.1).

**Optional references:** Handled via Jinja2 conditionals in the template:

```jinja
{% if reference_data and reference_data.ground_truth_context %}
Expert reference context:
{% for chunk in reference_data.ground_truth_context %}
- {{ chunk }}
{% endfor %}
{% endif %}
```

This pattern is used extensively by RAG templates (`components/29` sections 3.1-3.6).

### 9.3. Per-case criteria as reference data

Per-case criteria (`reference_data.llm_judge_criteria: list[str]`) are accessed and iterated in the template. See section 3 for the full pattern. The naming convention follows `components/50` section 4.3: `llm_judge_criteria` is domain-qualified to avoid collision with other EvalConfigTypes that might define "criteria."

---

## 10. V1 prompt to V2 Jinja2 wrapping shape (K.2)

### 10.1. Context

K.2 requires `copilot_api.py:337-340` to construct V2 `LlmJudgeProperties` from V1-shaped Copilot responses. The Copilot response contains `eval_steps: list[str]` and `task_description: str` (V1 fields). These must be wrapped into a complete V2 `prompt_template`.

### 10.2. V1 prompt structure (for reference)

V1's `GEval.generate_final_answer_run_description()` (`g_eval.py:121-133`) produces:

```
You will be given an eval_input (the original input/prompt given to the model)
and an eval_output (the model's response). Your task is to evaluate the quality
of the eval_output using the following criteria:

[task_description]

Evaluation Steps:
1. [eval_step_1]
2. [eval_step_2]
...

eval_input: [input]
eval_output: [output]
```

### 10.3. V2 wrapping shape

The Copilot translation constructs a Jinja2 `prompt_template` that embeds the V1 content in V2 syntax:

```python
def v1_to_v2_prompt_template(
    task_description: str,
    eval_steps: list[str],
) -> str:
    """Wrap V1 eval_steps + task_description into a V2 Jinja2 prompt_template."""
    steps_block = "\n".join(
        f"{i+1}. {step}" for i, step in enumerate(eval_steps)
    )
    return f"""\
You will evaluate the quality of the model's response using the following criteria:

{task_description}

Evaluation Steps:
{steps_block}

The original input/prompt given to the model:
{{{{ task_input }}}}

The model's response:
{{{{ final_message }}}}
"""
```

### 10.4. Wrapping rules

| V1 field | V2 destination | Notes |
|---|---|---|
| `task_description` | Embedded literally in `prompt_template` | Static text describing what the judge evaluates. |
| `eval_steps` | Embedded as numbered list in `prompt_template` | V1's criteria, baked into the template. |
| `model_name` | `LlmJudgeProperties.model_name` | Direct mapping. |
| `model_provider` | `LlmJudgeProperties.model_provider` | Direct mapping. |
| `g_eval_mode` (V1 `EvalConfigType`) | `LlmJudgeProperties.g_eval` | Copilot always produces `g_eval=False` (`copilot_api.py:340`). |
| (absent) | `system_prompt` | Filled with default per section 6.2 at creation time. |
| (absent) | `thinking_instruction` | Filled with default per section 7.1 at creation time. |

### 10.5. Reserved variable embedding

The wrapped template uses exactly two reserved variables:
- `{{ task_input }}` -- the original input given to the model being evaluated.
- `{{ final_message }}` -- the model's response.

It does NOT use `{{ trace }}` or `{{ reference_data }}` because V1 Copilot configs do not reference traces or structured reference data. Users wanting those features author a custom template.

### 10.6. `required_var` derivation

For the wrapped V1-to-V2 template, `required_var` is empty (`[]`). Both `task_input` and `final_message` are always present in `EvalTaskInput` (they come from the TaskRun, which always has input and output). No pre-check needed.

### 10.7. Save-time validation

The generated template passes `compile_template_or_raise()` (D.3 save-time validation). It references `task_input` and `final_message`, satisfying the useless-template rejection rule (`components/40` section 4: at least one reference to a non-`reference_data` reserved variable).

---

## 11. Adapter architecture (C.11c, A2.10)

### 11.1. Inheritance

```
BaseEval (generic, no LLM coupling)
  |
  +-- LlmJudgeAdapter (V2; reads model fields from LlmJudgeProperties)
```

`LlmJudgeAdapter` subclasses `BaseEval` directly (C.11c: no `BaseEvalV2` fork). It is built fresh on the V2 infrastructure (D.2/D.3/D.4 + `scoring_utils.py`), not derived from or inheriting GEval.

### 11.2. Model-field access (A2.10)

`LlmJudgeAdapter` reads `model_name` and `model_provider` directly from `self.eval_config.properties`:

```python
class LlmJudgeAdapter(BaseEval):
    @property
    def model_name(self) -> str:
        return self.eval_config.properties.model_name

    @property
    def model_provider(self) -> str:
        return self.eval_config.properties.model_provider
```

It does NOT call the extracted `legacy_model_fields` helper (that helper is for GEval only). It does NOT use `BaseEval.model_and_provider()` (that method is being extracted per A2.10).

### 11.3. Adapter contract

Per `components/20` section 3.3:

1. Subclasses `BaseEval`.
2. Receives `EvalInput` via the runner (V2 adapters receive `EvalInput` per B2.1 translation; the `run_eval` signature widens to `TaskRun | EvalInput`).
3. Uses `BaseEval.build_score_schema()` for score-schema generation.
4. Returns scores conforming to the parent `Eval.output_scores` shape (validated at EvalRun save time per C.9).

### 11.4. Sketch implementation

```python
class LlmJudgeAdapter(BaseEval):
    async def run_eval(
        self, item: EvalInput, eval_job_item: TaskRun | EvalInput | None = None
    ) -> tuple[EvalScores, dict[str, str] | None]:
        props: LlmJudgeProperties = self.eval_config.properties

        # 1. Assemble EvalTaskInput (runner provides this; adapter may receive
        #    it pre-assembled or construct from item + stored output)
        eval_task_input = self._build_eval_task_input(item, eval_job_item)

        # 2. Pre-check required_var
        input_dict = eval_task_input.model_dump()
        for expr in props.required_var:
            if extract(expr, input_dict) is None:
                raise SkipCaseError(SkippedReason.extraction_failed, detail=expr)

        # 3. Construct eval task (like GEvalTask but using JinjaInputTransform)
        eval_task = self._build_eval_task(props)
        run_config = KilnAgentRunConfigProperties(
            input_transform=JinjaInputTransform(template=props.prompt_template),
            model_name=props.model_name,
            model_provider=props.model_provider,
            # g_eval=True disallows function_calling
            structured_output_mode=(
                "json_schema" if props.g_eval
                else default_structured_output_mode_for_model_provider(
                    props.model_provider
                )
            ),
            top_logprobs=10 if props.g_eval else None,
        )

        # 4. Invoke through Kiln task infra (D.4)
        adapter = adapter_for_task(eval_task, run_config)
        # forward_thinking_instructions=True per components/05
        run_output = await adapter.invoke_returning_run_output(input_dict)

        # 5. Parse scores via scoring_utils (H.32a)
        if props.g_eval:
            scores = build_g_eval_score(run_output)
        else:
            scores = build_llm_as_judge_score(run_output)

        return scores, run_output.intermediate_outputs
```

This is a sketch, not binding implementation. The actual code will follow Phase 1 implementation patterns. Key points:

- `SkipCaseError` is the adapter-level mechanism for triggering a C.runner.1 skip (exact exception type is a `components/45` detail).
- The `_build_eval_task` method creates a temporary `Task` (similar to V1's `GEvalTask`) with the score schema and system prompt, but without the V1-specific `task_description`/`eval_steps` properties reading.
- The adapter passes `forward_thinking_instructions=True` to the chat formatter for reasoning models (per `components/05`).

---

## 12. V1 backwards compatibility

### 12.1. Legacy paths unchanged (D.5)

V1 EvalConfigs (`config_type: "g_eval"` or `"llm_as_judge"`) continue running through:
- The existing `GEval` adapter class.
- The existing three hardcoded `generate_*_run_description` f-string methods.
- The existing `EvalDataType` enum on the grandparent Eval.
- The existing properties shape (`eval_steps`, `task_description`, `template_properties`).

Zero V1 behavior changes, ever. Per A0.1 and D.5.

### 12.2. No auto-upgrade

V1 configs stay V1 forever (A2.2). If a user wants V2 features (per-criterion verdicts, trace condensation, reference templating), they create a new V2 EvalConfig alongside the V1 one. No silent rewrite; no auto-convert.

### 12.3. V2 adapter is additive

`LlmJudgeAdapter` is registered in the V2 sub-registry (`_V2_ADAPTER_MAP` in `components/20` section 2.2) alongside the existing `GEval` registration in the legacy dispatch path. The two adapters coexist; neither knows about the other.

---

## 13. Alignment reference coverage

| Ref | Decision | Coverage in this file |
|---|---|---|
| A1.4 | Per-case criteria via reference data | Section 3 (per-criterion pass/fail verdicts using `reference_data.llm_judge_criteria`; template iteration; structured-output coupling; global vs per-case interaction) |
| A2.2 | Unify g_eval and llm_as_judge under `llm_judge` with `g_eval: bool` | Section 1 (properties shape with `g_eval` field); Section 4 (mode semantics, V1 equivalence, model compatibility) |
| A2.10 | `model_and_provider` helper extraction; BaseEval stays generic | Section 11.2 (adapter reads model fields from properties directly, not via helper) |
| C.11c | V2 adapter base class: generic BaseEval, no fork | Section 11.1 (inheritance tree; no BaseEvalV2) |
| D.4 | Use Kiln tasks natively | Section 2 (execution flow: JinjaInputTransform, chat formatter, structured output mode, build_score_schema); Section 6 (system_prompt); Section 7 (thinking_instruction) |
| K.2 | Copilot path: V1 to V2 translation | Section 10 (wrapping shape, field mapping, reserved variable embedding, required_var derivation, save-time validation) |
| H.32a | Legacy/V2 code reuse: scoring helper extraction | Section 5 (what is consumed from scoring_utils.py, what is NOT shared, BaseEval.build_score_schema inheritance) |

---

## Opens

None. All seven alignment refs are fully covered. No blocking questions remain for this file's scope.

Implementation-time verification items (not design opens):
- ~~Check system_prompt Kiln core dependency status before implementing~~ — RESOLVED: always-system-message + default `"You are an evaluator."` (section 6.2).
- Validate `g_eval=True` + model logprob support at invocation time (section 4.3; straightforward runtime check).

---

## Sources

- `reference/ALIGNMENT.md` -- A1.4, A2.2, A2.10, C.11c, D.4, K.2, H.32a decision entries
- `components/20_eval_config_types_overview.md` -- adapter contract, two-level dispatch, scoring-helper extraction seam
- `components/40_template_and_extraction.md` -- LlmJudgeProperties shape (section 3.1), EvalTaskInput assembly, save-time validation, system_prompt/thinking_instruction handling
- `components/50_reference_data.md` -- reference-key contract, per-case criteria pattern (section 5.3), naming guidelines
- `components/05_prereq_thinking_formatter_fix.md` -- forward_thinking_instructions fix for reasoning models
- `components/29_rag_judge_templates.md` -- first consumer of llm_judge; validates template rendering against reference-data contract
- `batch_h_coexistence_and_builder.md` -- H.32a code-reuse strategy (option a: extract-helpers-then-build-V2-fresh)
- `reports/kintsugi_synthesis.md` -- semantic-criteria section, per-criterion pattern, trace condensation
