# Spec-Fidelity Review: Unit 40-template-extraction

**Title:** Template + extraction layer
**Spec files:** `components/40_template_and_extraction.md`, `components/06_prereq_input_transform.md`
**Reviewer date:** 2026-06-23

Requirements: 43 total — MET 32, PARTIAL 4, MISSING 1, CONTRADICTED 1, DEFERRED_OK 4, CANNOT_VERIFY 1

---

## Requirement Table

### 40-template-extraction-R01
- **Category:** Data model
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** `EvalTaskInput.final_message` typed as `str | dict[str, Any]` (string for plain-text tasks; dict for tasks with `output_json_schema`).
- **Spec quote:** "final_message: str | dict[str, Any]" (spec40 §2 table)
- **Evidence:** `libs/core/kiln_ai/datamodel/eval.py:315` — `final_message: str`
- **Divergence:** Code uses `str` only, not `str | dict[str, Any]`. The dict case for JSON-schema tasks is not represented. In practice `TaskRun.output.output` is always a string today, so functionally OK, but the type doesn't match spec.

### 40-template-extraction-R02
- **Category:** Data model
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** `EvalTaskInput.task_input` typed as `str | dict[str, Any]` (not optional).
- **Spec quote:** "task_input: str | dict[str, Any]" (spec40 §2 table)
- **Evidence:** `libs/core/kiln_ai/datamodel/eval.py:326` — `task_input: str | None`
- **Divergence:** Code uses `str | None` with default `None`. Spec has it non-optional.

### 40-template-extraction-R03
- **Category:** Data model
- **Verdict:** MET
- **Requirement:** `EvalTaskInput.trace` typed as `list[...] | None`, default `None`.
- **Spec quote:** "trace: list[ChatCompletionMessageParam] | None = None" (spec40 §2)
- **Evidence:** `libs/core/kiln_ai/datamodel/eval.py:318` — `trace: list[dict[str, Any]] | None`, default `None`. Uses `dict[str, Any]` instead of `ChatCompletionMessageParam` TypedDict, which is equivalent at runtime.

### 40-template-extraction-R04
- **Category:** Data model
- **Verdict:** MET
- **Requirement:** `EvalTaskInput.reference_data` typed as `dict[str, JsonValue] | None`, default `None`.
- **Spec quote:** "reference_data: dict[str, JsonValue] | None = None" (spec40 §2)
- **Evidence:** `libs/core/kiln_ai/datamodel/eval.py:322` — matches.

### 40-template-extraction-R05
- **Category:** Data model
- **Verdict:** MET
- **Requirement:** `final_message` sourced from `TaskRun.output.output`.
- **Spec quote:** "Sourced from: TaskRun.output.output" (spec40 §2 table)
- **Evidence:** `libs/core/kiln_ai/datamodel/eval.py:343,368` — both `from_task_run` and `from_eval_input` use `run_output.output.output` / `task_run.output.output`.

### 40-template-extraction-R06
- **Category:** Data model
- **Verdict:** MET
- **Requirement:** `trace` sourced from `TaskRun.trace`.
- **Spec quote:** "Sourced from: TaskRun.trace" (spec40 §2 table)
- **Evidence:** `libs/core/kiln_ai/datamodel/eval.py:338-340,361-362` — sources from `task_run.trace` / `run_output.trace`.

### 40-template-extraction-R07
- **Category:** Data model
- **Verdict:** MET
- **Requirement:** `reference_data` sourced from `EvalInput.reference`. `None` if EvalInput has no reference.
- **Spec quote:** "Sourced from: EvalInput.reference. None if EvalInput has no reference" (spec40 §2 table)
- **Evidence:** `libs/core/kiln_ai/datamodel/eval.py:370` (`from_eval_input` sets `reference_data=eval_input.reference`) and `eval.py:345` (`from_task_run` sets `reference_data=None`).

### 40-template-extraction-R08
- **Category:** Data model
- **Verdict:** MET
- **Requirement:** `task_input` sourced from `TaskRun.input`.
- **Spec quote:** "Sourced from: TaskRun.input" (spec40 §2 table)
- **Evidence:** `libs/core/kiln_ai/datamodel/eval.py:346,371` — both factory methods source from run_output/task_run `.input`.

### 40-template-extraction-R09
- **Category:** Data model / naming
- **Verdict:** MET
- **Requirement:** Four reserved top-level template variables: `final_message`, `trace`, `reference_data`, `task_input`. No `data.` wrapper. Templates reference them directly.
- **Spec quote:** "Templates reference them directly: {{ final_message.classification }}" (spec40 §2)
- **Evidence:** `v2_eval_llm_judge.py:109-110` — `namespace = eval_input.model_dump()` then `render(**namespace)`, so the four fields are top-level.

### 40-template-extraction-R10
- **Category:** Data model / properties
- **Verdict:** MET
- **Requirement:** `LlmJudgeProperties` has fields: `type`, `model_name`, `model_provider`, `system_prompt: str | None = None`, `prompt_template: str`, `required_var: list[str] = []`, `thinking_instruction: str | None = None`, `g_eval: bool = False`.
- **Spec quote:** spec40 §3.1 `LlmJudgeProperties` block
- **Evidence:** `libs/core/kiln_ai/datamodel/eval.py:81-89` — all fields match.

### 40-template-extraction-R11
- **Category:** Runtime / flow
- **Verdict:** MET
- **Requirement:** Per-case flow step 1: Eval runner builds `EvalTaskInput` for this case.
- **Spec quote:** "Eval runner builds EvalTaskInput for this case." (spec40 §3.1)
- **Evidence:** `eval_runner.py:462,488,515` — `EvalTaskInput.from_eval_input(...)` and `EvalTaskInput.from_task_run(...)`.

### 40-template-extraction-R12
- **Category:** Runtime / flow
- **Verdict:** MET
- **Requirement:** Per-case flow step 2: Pre-check each `required_var` expression via `extract()`. If any returns `None` or `Undefined`, skip with `skipped_reason: extraction_failed` + `skipped_detail`.
- **Spec quote:** "Pre-check each required_var expression via extract(expr, eval_task_input.model_dump()). If any returns None or Undefined, skip the case with skipped_reason: extraction_failed + skipped_detail" (spec40 §3.1)
- **Evidence:** `v2_eval_helpers.py:78-91` (`check_required_vars`) and `v2_eval_llm_judge.py:105-107` — extracts each var, returns `SkippedReason.extraction_failed` with detail string.

### 40-template-extraction-R13
- **Category:** Architecture
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** Per-case flow step 3: Construct the eval task's RunConfig with `input_transform = JinjaInputTransform(template=prompt_template)`.
- **Spec quote:** "Construct the eval task's RunConfig with input_transform = JinjaInputTransform(template=prompt_template)." (spec40 §3.1)
- **Evidence:** `v2_eval_llm_judge.py:152-157` — The RunConfig at line 152 does NOT include `input_transform`. Instead, template is rendered directly via `_template_env.from_string(props.prompt_template).render(**namespace)` at line 110-111, and the rendered string is passed to `invoke_returning_run_output` at line 165.
- **Divergence:** The implementation renders the template manually instead of via `input_transform` on the RunConfig. End result is functionally equivalent (same Jinja2 env, same StrictUndefined), but the architecture doesn't use the general infra path described in the spec. The spec explicitly said the RunConfig carries the transform and the adapter chain renders it.

### 40-template-extraction-R14
- **Category:** Runtime / flow
- **Verdict:** MET
- **Requirement:** Per-case flow step 4: Invoke through Kiln task infrastructure.
- **Spec quote:** "Invoke adapter.invoke_returning_run_output" (spec40 §3.1)
- **Evidence:** `v2_eval_llm_judge.py:165` — `await adapter.invoke_returning_run_output(rendered_prompt)`.

### 40-template-extraction-R15
- **Category:** Runtime / flow
- **Verdict:** MET
- **Requirement:** Per-case flow step 5: Structured score response parsed per schema built from `Eval.output_scores`.
- **Spec quote:** "Structured score response parsed per the schema built from Eval.output_scores." (spec40 §3.1)
- **Evidence:** `v2_eval_llm_judge.py:114-115` — `BaseEval.build_score_schema(self.eval, ...)` and lines 167-179 — scores parsed via `build_g_eval_score` or `build_llm_as_judge_score`.

### 40-template-extraction-R16
- **Category:** Design decision
- **Verdict:** MET
- **Requirement:** No separate `template_vars` field. Templates access top-level synthetic-input fields directly.
- **Spec quote:** "No template_vars field." (spec40 §3.1)
- **Evidence:** `LlmJudgeProperties` (eval.py:81-89) has no `template_vars` field. Template is rendered against `eval_input.model_dump()` directly.

### 40-template-extraction-R17
- **Category:** Design decision
- **Verdict:** MET
- **Requirement:** No separate `criteria` / `eval_steps` field on V2 LlmJudge. Criteria goes into `prompt_template`.
- **Spec quote:** "No separate criteria / eval_steps field." (spec40 §3.1)
- **Evidence:** `LlmJudgeProperties` (eval.py:81-89) has no `criteria` or `eval_steps` field.

### 40-template-extraction-R18
- **Category:** Config / g_eval
- **Verdict:** CONTRADICTED
- **Severity:** minor
- **Requirement:** `g_eval=False` (pure llm_as_judge): function_calling allowed (broadens model support).
- **Spec quote:** "False: pure llm_as_judge; no logprobs; function_calling allowed (broadens model support)." (spec40 §3.1)
- **Evidence:** `v2_eval_llm_judge.py:138-146` — `disallowed_modes` always includes `function_calling` and `function_calling_weak`, regardless of `props.g_eval`. The restriction is applied unconditionally.
- **Divergence:** Spec says function_calling should be allowed when `g_eval=False`; code disallows it always. This restricts model support for the non-g_eval path.

### 40-template-extraction-R19
- **Category:** Config / g_eval
- **Verdict:** MET
- **Requirement:** `g_eval=True`: structured output disallows function_calling; `top_logprobs=10`; probability-weighted scoring.
- **Spec quote:** "True: structured output disallows function_calling ... top_logprobs=10; probability-weighted scoring per V1 algorithm." (spec40 §3.1)
- **Evidence:** `v2_eval_llm_judge.py:142-148` — disallowed_modes includes function_calling; `top_logprobs = 10 if props.g_eval else None`; lines 167-173 use `build_g_eval_score`.

### 40-template-extraction-R20
- **Category:** Data model / properties
- **Verdict:** MET
- **Requirement:** `ExactMatchProperties` has `type`, `value_expression: str | None = None`, `expected_value: str | None = None`, `reference_key: str | None = None`, with exactly-one-of validation for expected_value/reference_key.
- **Spec quote:** spec40 §3.2 `ExactMatchProperties` block
- **Evidence:** `eval.py:92-105` — all fields present, model_validator enforces exactly-one-of.

### 40-template-extraction-R21
- **Category:** Data model / properties
- **Verdict:** MET
- **Requirement:** `PatternMatchProperties` has `type`, `value_expression: str | None = None`, `pattern: str`, `mode: Literal["must_match", "must_not_match"] = "must_match"`.
- **Spec quote:** spec40 §3.2 `PatternMatchProperties` block
- **Evidence:** `eval.py:108-122` — all fields match. Also validates regex compiles.

### 40-template-extraction-R22
- **Category:** Data model / properties
- **Verdict:** MET
- **Requirement:** `ContainsProperties` has `type`, `value_expression: str | None = None`, `substring: str | None = None`, `reference_key: str | None = None`.
- **Spec quote:** spec40 §3.2 `ContainsProperties` block
- **Evidence:** `eval.py:125-137` — fields match. Code adds `case_sensitive: bool = True` and `mode: Literal["must_contain", "must_not_contain"] = "must_contain"` which are not in the spec but are reasonable extensions that don't conflict.

### 40-template-extraction-R23
- **Category:** Data model / properties
- **Verdict:** MET
- **Requirement:** `SetCheckProperties` has `type`, `value_expression: str | None = None`, `expected_set: list[str] | None = None`, `reference_key: str | None = None`, `mode: Literal["subset", "superset", "equal"] = "subset"`.
- **Spec quote:** spec40 §3.2 `SetCheckProperties` block
- **Evidence:** `eval.py:140-151` — all fields match, including exactly-one-of validator.

### 40-template-extraction-R24
- **Category:** Extraction semantics
- **Verdict:** MET
- **Requirement:** `value_expression` semantics: Jinja2 expression evaluated via `extract()` against `EvalTaskInput`. If `None`: extracted value is the whole `final_message`.
- **Spec quote:** "If None: extracted value is the whole final_message." (spec40 §3.2)
- **Evidence:** `v2_eval_helpers.py:26-38` (`extract_value`) — if expression is None, returns `eval_input.final_message`.

### 40-template-extraction-R25
- **Category:** Extraction semantics / skip
- **Verdict:** MET
- **Requirement:** Null/missing extraction: case skipped with `skipped_reason: extraction_failed` + `skipped_detail`.
- **Spec quote:** "Null/missing extraction: case skipped with skipped_reason: extraction_failed + skipped_detail: '<value_expression>'" (spec40 §3.2)
- **Evidence:** `v2_eval_helpers.py:39-44` — returns `SkippedReason.extraction_failed` with detail string when result is Undefined or None.

### 40-template-extraction-R26
- **Category:** Typed eval types
- **Verdict:** MET
- **Requirement:** `tool_call_check` does NOT use `input_transform` or `extract()`. Walks trace internally.
- **Spec quote:** "Does not use input_transform or extract(). Walks the trace JSON internally with a typed matcher." (spec40 §3.3)
- **Evidence:** `v2_eval_tool_call_check.py` — no imports of `extract` or `input_transform`. Uses `_extract_tool_calls` which directly walks the trace dicts.

### 40-template-extraction-R27
- **Category:** Typed eval types
- **Verdict:** MET
- **Requirement:** `step_count_check` does NOT use `value_expression`, `extract()`, or `input_transform`. Walks the trace internally.
- **Spec quote:** "step_count_check is a typed deterministic trace inspector that does NOT use value_expression, extract(), or input_transform." (spec40 §3.3b)
- **Evidence:** `v2_eval_step_count_check.py` — no imports of `extract` or `input_transform`. Uses internal `_count` method.

### 40-template-extraction-R28
- **Category:** Save-time validation
- **Verdict:** MET
- **Requirement:** `prompt_template` validated at save time via `compile_template_or_raise(prompt_template)`.
- **Spec quote:** "prompt_template -> compile_template_or_raise(prompt_template)" (spec40 §4)
- **Evidence:** `eval.py:704-705` — `compile_template_or_raise(props.prompt_template)` in `validate_v2_templates_and_expressions`.

### 40-template-extraction-R29
- **Category:** Save-time validation
- **Verdict:** MET
- **Requirement:** `required_var[i]` validated at save time via `compile_expression_or_raise(expr)`.
- **Spec quote:** "required_var[i] -> compile_expression_or_raise(expr)" (spec40 §4)
- **Evidence:** `eval.py:713-714` — `for var in props.required_var: compile_expression_or_raise(var)`.

### 40-template-extraction-R30
- **Category:** Save-time validation
- **Verdict:** MET
- **Requirement:** `value_expression` validated at save time via `compile_expression_or_raise(value_expression)`.
- **Spec quote:** "value_expression -> compile_expression_or_raise(value_expression)" (spec40 §4)
- **Evidence:** `eval.py:716-726` — validates for ExactMatch, PatternMatch, Contains, SetCheck when `value_expression is not None`.

### 40-template-extraction-R31
- **Category:** Save-time validation
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** Useless-template rejection: save-time validation parses the template AST to find variable references; rejects unless at least one reference is a reserved top-level var that's NOT `reference_data`. Error message: "prompt_template must reference at least one variable from model output (final_message, trace, or task_input)."
- **Spec quote:** "Save-time validation parses the template AST to find variable references; rejects the save unless at least one reference is: A reserved top-level var that's NOT reference_data" (spec40 §4)
- **Evidence:** `eval.py:706-712` — The check is `if "{{" not in tmpl_source and "{%" not in tmpl_source` -- a simple string-level check for Jinja2 syntax markers, NOT an AST-based variable reference check. A template like `{{ reference_data.expected }}` (which references only reference_data) would pass, violating the spec's intent. The error message also differs from the spec.
- **Divergence:** Uses a surface-level "has any Jinja2 syntax" check instead of AST-based variable reference analysis. Does not enforce the "at least one non-reference_data variable" constraint.

### 40-template-extraction-R32
- **Category:** Backwards compatibility
- **Verdict:** MET
- **Requirement:** V1 EvalConfigs (`config_type: g_eval` / `llm_as_judge`) keep running through the existing GEval adapter, hardcoded f-string path. Zero V1 behavior changes (A0.1).
- **Spec quote:** "V1 EvalConfigs (config_type: 'g_eval' or 'llm_as_judge') keep running through... The existing GEval adapter class... Zero V1 behavior changes." (spec40 §8)
- **Evidence:** `registry.py:42-46` — g_eval and llm_as_judge both route to `GEval`. `g_eval.py` has the three `generate_*_run_description` f-string methods.

### 40-template-extraction-R33
- **Category:** Backwards compatibility
- **Verdict:** MET
- **Requirement:** V2 EvalConfigs (`config_type: "v2"`) route through new V2 adapters.
- **Spec quote:** "V2 EvalConfigs (config_type: 'v2', properties typed by V2EvalType) route through new V2 adapters" (spec40 §8)
- **Evidence:** `registry.py:55-73` — `v2_eval_adapter_from_config` dispatches by `properties.type` to the `_V2_ADAPTER_MAP`.

### 40-template-extraction-R34
- **Category:** Principle / immutability
- **Verdict:** MET
- **Requirement:** `prompt_template` is on `LlmJudgeProperties` (EvalConfig's properties), not on RunConfig directly, preserving immutability per §1.3.
- **Spec quote:** "EvalConfig is the immutable snapshot -- the source of truth lives there. RunConfig is constructed per invocation from the EvalConfig." (spec40 §3.1)
- **Evidence:** `eval.py:86` — `prompt_template: str` is on `LlmJudgeProperties`. The RunConfig constructed in `v2_eval_llm_judge.py:152` does not carry the template.

### 40-template-extraction-R35
- **Category:** System prompt
- **Verdict:** MET
- **Requirement:** V2 `llm_judge` always sends a system message. If user doesn't author `system_prompt`, a default is used. The field is not exposed in the builder UI.
- **Spec quote:** "V2 llm_judge always sends a system message. If the user doesn't author a system_prompt, the builder writes a generic default ('You are an evaluator.')" (spec40 §7.1)
- **Evidence:** `v2_eval_llm_judge.py:47-49,118` — `_DEFAULT_SYSTEM_PROMPT` is used when `props.system_prompt` is None: `system_prompt = props.system_prompt or _DEFAULT_SYSTEM_PROMPT`. Default text is "Your job is to evaluate a model's performance on a task. Score the output according to the criteria provided." (slightly different from spec's "You are an evaluator." but the spec says this is "editable via the code/library API" so the exact text is flexible).

### 40-template-extraction-R36
- **Category:** Prereq infra / engine
- **Verdict:** MET
- **Requirement:** Engine uses `SandboxedEnvironment`. Two envs: template env with `StrictUndefined`, expression env with default `Undefined`.
- **Spec quote:** "SandboxedEnvironment(undefined=StrictUndefined)... SandboxedEnvironment(undefined=Undefined)" (spec06 §3)
- **Evidence:** `jinja_engine.py:30-39` — `_template_env = SandboxedEnvironment(undefined=StrictUndefined, ...)` and `_expression_env = SandboxedEnvironment(undefined=Undefined, ...)`.

### 40-template-extraction-R37
- **Category:** Prereq infra / API
- **Verdict:** MET
- **Requirement:** Four public functions exported: `compile_template_or_raise`, `compile_expression_or_raise`, `render_input_transform`, `extract`.
- **Spec quote:** "Three public functions exported from libs/core/kiln_ai/<path>/jinja_engine.py ... compile_template_or_raise ... compile_expression_or_raise ... render_input_transform ... extract" (spec06 §4)
- **Evidence:** `jinja_engine.py:43,53,63,80` — all four functions defined and importable.

### 40-template-extraction-R38
- **Category:** Prereq infra / extract semantics
- **Verdict:** MET
- **Requirement:** `extract()` returns `Undefined` for missing keys (not raises), `None` for explicit null, auto-materializes generators to lists.
- **Spec quote:** "Missing keys return Undefined... Explicit null values return None... Generators are auto-materialized to lists." (spec06 §4)
- **Evidence:** `jinja_engine.py:80-98` — uses `_expression_env` (default Undefined), `undefined_to_none=False`, and `isinstance(result, types.GeneratorType)` check.

### 40-template-extraction-R39
- **Category:** Prereq infra / data model
- **Verdict:** MET
- **Requirement:** `input_transform: InputTransform | None = None` on `KilnAgentRunConfigProperties`. Default `None` preserves current behavior.
- **Spec quote:** "input_transform: InputTransform | None = None  # NEW -- default None preserves current behavior" (spec06 §2)
- **Evidence:** `run_config.py:82-89` — field exists with `None` default.

### 40-template-extraction-R40
- **Category:** Prereq infra / data model
- **Verdict:** MET
- **Requirement:** `JinjaInputTransform` with `type: Literal["jinja"]` and `template: str`, with `field_validator` calling `compile_template_or_raise`.
- **Spec quote:** spec06 §2 `JinjaInputTransform` block
- **Evidence:** `input_transform.py:6-23` — matches spec. Has type, template, and field_validator.

### 40-template-extraction-R41
- **Category:** Prereq infra / placement
- **Verdict:** MET
- **Requirement:** `input_transform` NOT on `TaskRunConfig` (parent), NOT on `Task`, NOT on `McpRunConfigProperties`.
- **Spec quote:** "Important: NOT on TaskRunConfig (parent), NOT on Task, NOT on McpRunConfigProperties." (spec06 §2)
- **Evidence:** `run_config.py:82` — on `KilnAgentRunConfigProperties`. `McpRunConfigProperties` (run_config.py:113-122) has no `input_transform`.

### 40-template-extraction-R42
- **Category:** Prereq infra / runtime
- **Verdict:** MET
- **Requirement:** Adapter chain applies transform between "task input received" and "input handed to prompt builder". If `input_transform is None`, existing behavior unchanged.
- **Spec quote:** "The transform sits between 'task input received' and 'input handed to the prompt builder / formatter'" (spec06 §6)
- **Evidence:** `base_adapter.py:247,443,529-543` — `_apply_input_transform` called in both `invoke` and `invoke_returning_run_output`, returns input unchanged if transform is None.

### 40-template-extraction-R43
- **Category:** Deferred
- **Verdict:** DEFERRED_OK
- **Requirement:** Custom Jinja2 filters not in V2.0 scope.
- **Spec quote:** "Custom Jinja2 filters ... not in V2.0 scope." (spec40 §9 Confirmed no-action)
- **Evidence:** `jinja_engine.py` — no custom filters added to either env.

### 40-template-extraction-R44
- **Category:** Deferred
- **Verdict:** DEFERRED_OK
- **Requirement:** V1 template library content migration is future work (Stage 5 / Batch G).
- **Spec quote:** "V1 template library content migration -- who authors the V2 versions ... Stage 5 / Batch G content work." (spec40 §9 Opens)
- **Evidence:** No V2 template library content found; correctly deferred.

### 40-template-extraction-R45
- **Category:** Deferred
- **Verdict:** DEFERRED_OK
- **Requirement:** Resource limits on template rendering deferred to future hardening.
- **Spec quote:** "Resource limits (CPU, memory) on template rendering... Defer to future hardening." (spec06 §10)
- **Evidence:** No resource limits implemented. Correctly deferred.

### 40-template-extraction-R46
- **Category:** Deferred
- **Verdict:** DEFERRED_OK
- **Requirement:** Structured output emission (JSON output from templates) not in V1.
- **Spec quote:** "Future extension (NOT V1): emit structured output" (spec06 §6)
- **Evidence:** `render_input_transform` returns `str`. Correctly deferred.

### 40-template-extraction-R47
- **Category:** Prereq infra / consume
- **Verdict:** MET
- **Requirement:** Evals consume (not rebuild) the prereq infra. No eval-specific Jinja2 engine or FilterSpec.
- **Spec quote:** "Evals do NOT own Jinja2, the sandbox, or the extraction primitive. All of that is in components/06... Evals import compile_template_or_raise, compile_expression_or_raise and use them." (spec40 §1.1)
- **Evidence:** `eval.py:698-700` imports from `kiln_ai.utils.jinja_engine`; `v2_eval_helpers.py:10` imports `extract` from same. No separate eval-specific engine.

### 40-template-extraction-R48
- **Category:** Runtime / thinking
- **Verdict:** CANNOT_VERIFY
- **Severity:** minor
- **Requirement:** `thinking_instruction` default: if `None` at creation, V2 builder writes Kiln's current default into the EvalConfig.
- **Spec quote:** "If None at creation, V2 builder writes Kiln's current default ... into the EvalConfig at creation per §1.3." (spec40 §7.2)
- **Evidence:** `v2_eval_llm_judge.py:122` passes `thinking_instruction=props.thinking_instruction` to the task. The builder-side default population would be in the frontend/API layer which is beyond the scope of the code pointers provided.

### 40-template-extraction-R49
- **Category:** Runtime / thinking
- **Verdict:** MET
- **Requirement:** V2 llm_judge wires `forward_thinking_instructions=True` on the formatter.
- **Spec quote:** "Wires forward_thinking_instructions=True on the formatter" (spec40 §9)
- **Evidence:** `v2_eval_llm_judge.py:161` — `forward_thinking_instructions=True` in AdapterConfig.

---

## Verifier-Added Requirements (source: verifier_added)

### 40-template-extraction-R50
- **Category:** Runtime / rendering
- **Verdict:** MET
- **Requirement:** Template rendering uses StrictUndefined (hard error on missing variables during render).
- **Spec quote:** "StrictUndefined (missing vars must raise, not render empty)" (spec06 §1)
- **Evidence:** `v2_eval_llm_judge.py:45,110` — imports `_template_env` which uses `StrictUndefined`. Template rendered via `_template_env.from_string(props.prompt_template).render(**namespace)`.

### 40-template-extraction-R51
- **Category:** Data model / routing
- **Verdict:** MET
- **Requirement:** V2 config_type is `"v2"`, not a separate value per eval type.
- **Spec quote:** "V2 EvalConfigs (config_type: 'v2', properties typed by V2EvalType)" (spec40 §8)
- **Evidence:** `eval.py:63-65` — `EvalConfigType.v2 = "v2"`. All V2 types share this config_type with typed properties.

### 40-template-extraction-R52
- **Category:** Prereq infra / V1 compat
- **Verdict:** MET
- **Requirement:** Existing RunConfigs without `input_transform` field load cleanly (default None).
- **Spec quote:** "All existing RunConfigs in the wild have no input_transform field. After this change, they parse as having input_transform=None." (spec06 §9)
- **Evidence:** `run_config.py:82` — `input_transform: InputTransform | None = Field(default=None, ...)`. Pydantic will default missing field to None.

### 40-template-extraction-R53
- **Category:** Prereq infra / security
- **Verdict:** MET
- **Requirement:** Both envs use `SandboxedEnvironment` (same security model).
- **Spec quote:** "Same SandboxedEnvironment class -- Same security model" (spec06 §3)
- **Evidence:** `jinja_engine.py:30,36` — both use `SandboxedEnvironment`.

---

## Summary

The template + extraction layer implementation is largely faithful to the spec. The main gaps are:

1. **CONTRADICTED (R18):** `g_eval=False` should allow `function_calling` mode but the code always disallows it. Minor severity since it only restricts model provider selection; doesn't break functionality.

2. **PARTIAL (R31):** Useless-template rejection uses a surface-level string check (`{{` / `{%` presence) instead of the AST-based variable reference analysis the spec describes. Templates referencing only `reference_data` would incorrectly pass validation.

3. **PARTIAL (R13):** LLM judge renders templates directly via `_template_env` instead of constructing a RunConfig with `input_transform = JinjaInputTransform(...)`. Functionally equivalent but doesn't use the general infra path.

4. **PARTIAL (R01, R02):** `EvalTaskInput` field types narrower than spec (`final_message` is `str` not `str | dict`, `task_input` is `str | None` not `str | dict`).
