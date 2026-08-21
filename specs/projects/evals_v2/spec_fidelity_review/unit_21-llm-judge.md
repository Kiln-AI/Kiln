# Unit 21-llm-judge: Type: enhanced llm_judge

**Spec file:** `components/21_type_llm_judge.md`

Requirements: 54 total — MET 39, PARTIAL 5, MISSING 3, CONTRADICTED 2, DEFERRED_OK 3, CANNOT_VERIFY 2

---

## Requirements Table

### Section 1 — Properties shape (`LlmJudgeProperties`)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Section | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 21-R01 | data-model | MET | — | `LlmJudgeProperties` has `type: Literal["llm_judge"]` | §1 `type: Literal["llm_judge"] = "llm_judge"` | `libs/core/kiln_ai/datamodel/eval.py:82` — `type: Literal[V2EvalType.llm_judge] = V2EvalType.llm_judge` | — |
| 21-R02 | data-model | MET | — | `model_name: str` field on properties (not on root EvalConfig) | §1 "Model selection -- on properties, NOT on root EvalConfig (A2.10)" | `eval.py:83` — `model_name: str` on LlmJudgeProperties | — |
| 21-R03 | data-model | MET | — | `model_provider: str` field on properties | §1 | `eval.py:84` — `model_provider: str` | — |
| 21-R04 | data-model | MET | — | `prompt_template: str` is REQUIRED Jinja2 template | §1 "REQUIRED; Jinja2 template" | `eval.py:86` — `prompt_template: str` (no default = required) | — |
| 21-R05 | data-model | MET | — | `system_prompt: str \| None = None` | §1 | `eval.py:85` — `system_prompt: str \| None = None` | — |
| 21-R06 | data-model | MET | — | `thinking_instruction: str \| None = None` | §1 | `eval.py:88` — `thinking_instruction: str \| None = None` | — |
| 21-R07 | data-model | MET | — | `required_var: list[str] = []` with Jinja2 expressions | §1 | `eval.py:87` — `required_var: list[str] = []` | — |
| 21-R08 | data-model | MET | — | `g_eval: bool = False` | §1 "renamed from g_eval_mode" | `eval.py:89` — `g_eval: bool = False` | — |
| 21-R09 | data-model | MET | — | No separate `criteria` / `eval_steps` field on LlmJudgeProperties | §1.2 "V2 has no separate field -- criteria text goes directly into the prompt_template" | `eval.py:81-89` — no eval_steps or criteria field present | — |
| 21-R10 | data-model | MET | — | No `template_vars` field | §1.3 | `eval.py:81-89` — no template_vars field | — |
| 21-R11 | data-model | MET | — | No `data_source` / `evaluation_data_type` field on properties | §1.4 | `eval.py:81-89` — no such field | — |

### Section 2 — Per-case execution flow

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Section | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 21-R12 | execution | MET | — | Required-var pre-check before template rendering; skips with `extraction_failed` | §2.2 "If any returns None or Undefined, the case is skipped with skipped_reason: extraction_failed" | `v2_eval_llm_judge.py:105-107` calls `check_required_vars()`, returns `SkippedReason.extraction_failed` | — |
| 21-R13 | execution | MET | — | Template rendered against `eval_task_input.model_dump()` by Jinja2 | §2.3-2.4 "Template rendered against eval_task_input.model_dump() by JinjaInputTransform" | `v2_eval_llm_judge.py:109-111` — `namespace = eval_input.model_dump()` then `_template_env.from_string(props.prompt_template).render(**namespace)` | Renders directly via `_template_env` instead of via `JinjaInputTransform`. Functionally equivalent; the spec's sketch used JinjaInputTransform but the rendering result is the same. |
| 21-R14 | execution | MET | — | Structured output mode selected via `default_structured_output_mode_for_model_provider()` | §2.4 step 3 | `v2_eval_llm_judge.py:138-146` — calls `default_structured_output_mode_for_model_provider()` | — |
| 21-R15 | execution | MET | — | Score schema built from `Eval.output_scores` via `BaseEval.build_score_schema()` | §2.4 step 4 | `v2_eval_llm_judge.py:114-115` — `BaseEval.build_score_schema(self.eval, allow_float_scores=False)` | — |
| 21-R16 | execution | MET | — | `allow_float_scores=False` for discrete model output | §4 "V2 llm_judge uses discrete model output only (allow_float_scores=False)" | `v2_eval_llm_judge.py:115` — `allow_float_scores=False` | — |
| 21-R17 | execution | MET | — | Score parsing dispatches on `g_eval` flag: `build_g_eval_score` vs `build_llm_as_judge_score` | §2.5 | `v2_eval_llm_judge.py:167-179` — if/else on `props.g_eval` calling the correct functions | — |

### Section 4 — g_eval scoring mode

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Section | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 21-R18 | execution | MET | — | `g_eval=True`: `top_logprobs=10` | §4.1 | `v2_eval_llm_judge.py:148` — `top_logprobs = 10 if props.g_eval else None` | — |
| 21-R19 | execution | CONTRADICTED | major | `g_eval=False`: function_calling is ALLOWED (broadens model support); `g_eval=True`: function_calling DISALLOWED | §4.1 table — g_eval=False: "function_calling: Allowed"; g_eval=True: "function_calling: Disallowed" | `v2_eval_llm_judge.py:138-146` — `disallowed_modes` includes `function_calling` unconditionally, regardless of `g_eval` value | Code disallows function_calling for BOTH modes. The spec says function_calling should be allowed when g_eval=False to broaden model support. |
| 21-R20 | execution | MET | — | `g_eval=True` requires logprobs support; fail fast if model doesn't support | §4.3 "the adapter should fail fast at invocation time with a clear error message" | `v2_eval_llm_judge.py:129-136` — checks `model_provider.supports_logprobs` and raises `ValueError` | — |

### Section 5 — Scoring-helper consumption

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Section | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 21-R21 | code-structure | MET | — | Consumes `build_llm_as_judge_score` from `scoring_utils.py` | §5.1 | `v2_eval_llm_judge.py:20-21` imports and `line 175-178` uses it | — |
| 21-R22 | code-structure | MET | — | Consumes `build_g_eval_score` from `scoring_utils.py` | §5.1 | `v2_eval_llm_judge.py:20` imports and `line 168-174` uses it | — |
| 21-R23 | code-structure | MET | — | Consumes `score_from_token_string` / `TOKEN_TO_SCORE_MAP` | §5.1 | `v2_eval_llm_judge.py:24` imports `score_from_token_string`, passed to `build_llm_as_judge_score` at line 178 | — |
| 21-R24 | code-structure | MET | — | Does NOT share GEvalTask construction or `generate_*_run_description` f-strings with GEval | §5.2 | `v2_eval_llm_judge.py` — uses its own `_LlmJudgeTask` class and Jinja2 template rendering, no import of GEval | — |
| 21-R25 | code-structure | MET | — | Does NOT call `model_and_provider()` | §5.2, §11.2 | `v2_eval_llm_judge.py` — reads `props.model_name` and `props.model_provider` directly (lines 126-127) | — |
| 21-R26 | code-structure | MET | — | Inherits `build_score_schema()` from BaseEval | §5.3 | `v2_eval_llm_judge.py:114` — calls `BaseEval.build_score_schema()` | — |

### Section 6 — system_prompt handling

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Section | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 21-R27 | execution | MET | — | Always sends a system message | §6.2 "V2 llm_judge always sends a system message" | `v2_eval_llm_judge.py:118` — `system_prompt = props.system_prompt or _DEFAULT_SYSTEM_PROMPT` — always non-None | — |
| 21-R28 | defaults | PARTIAL | minor | Default system_prompt is `"You are an evaluator."` set at creation time | §6.2 "the builder writes a default ('You are an evaluator.') into the EvalConfig's system_prompt field at creation time" | `v2_eval_llm_judge.py:47-50` — `_DEFAULT_SYSTEM_PROMPT = "Your job is to evaluate a model's performance on a task. Score the output according to the criteria provided."` | Default text differs from spec. Also, the default is applied at runtime (line 118: `or _DEFAULT_SYSTEM_PROMPT`) rather than being written into the EvalConfig at creation time. The properties store `system_prompt=None`, so the snapshot is not self-contained. |
| 21-R29 | data-model | MET | — | `system_prompt` is a static string, not a Jinja2 template | §6.3 "system_prompt is a plain string, not a Jinja2 template" | `v2_eval_llm_judge.py:120-124` — `system_prompt` passed directly to `_LlmJudgeTask` as `instruction`, no template rendering | — |
| 21-R30 | UX | MET | — | `system_prompt` NOT exposed as a builder-UI field | §6.2 "NOT a builder-UI field" | `llm_judge_form.svelte` — no system_prompt input field. The form only has model selection, algorithm, task_description, and eval_steps | — |

### Section 7 — thinking_instruction handling

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Section | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 21-R31 | defaults | MISSING | minor | Default thinking_instruction resolved at creation time: `"Think step by step, explaining your reasoning."` from `prompt_builders.py:294-305` | §7.1 "if None at creation, the V2 builder writes Kiln's current default" | No creation-time resolution found. `thinking_instruction` stays `None` in stored properties. At runtime, the `_LlmJudgeTask` constructor receives `thinking_instruction=None`. The Task then uses its own default from prompt_builders. Functionally similar but the snapshot is not self-contained. | The spec mandates that the builder resolves the default into the EvalConfig at creation time so the config is a full snapshot. The code leaves it as None and relies on runtime default resolution. |
| 21-R32 | execution | MET | — | `forward_thinking_instructions=True` for reasoning models | §7.2 "SingleTurnR1ThinkingFormatter receives forward_thinking_instructions=True" | `v2_eval_llm_judge.py:161` — `forward_thinking_instructions=True` in `AdapterConfig` | — |

### Section 8 — Trace condensation

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Section | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 21-R33 | execution | DEFERRED_OK | — | V2.0 does NOT ship separate trace condensation pipeline or config fields | §8.2 "V2.0 does NOT ship a separate trace condensation pipeline" | No condensation pipeline found in `v2_eval_llm_judge.py` | Correctly omitted. |
| 21-R34 | execution | MET | — | Trace condensation is template-driven (handled in Jinja2) | §8.2 "the Jinja2 template handles condensation natively" | Template rendering at `v2_eval_llm_judge.py:109-111` uses `eval_input.model_dump()` which includes `trace`, making it available for template-driven condensation | — |

### Section 9 — Reference-data templating

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Section | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 21-R35 | execution | MET | — | Reference data from EvalInput.reference exposed as `reference_data` in template namespace | §9.1 | `v2_eval_llm_judge.py:109` — `namespace = eval_input.model_dump()` which includes `reference_data` field from `EvalTaskInput` | — |
| 21-R36 | execution | MET | — | Required references declared via `required_var` | §9.2 | `v2_eval_llm_judge.py:105-107` — checks required_var via `check_required_vars()` | — |
| 21-R37 | execution | MET | — | Optional references handled via Jinja2 conditionals in template | §9.2 | Template-driven; the engine renders whatever Jinja2 the user writes | — |

### Section 10 — V1 to V2 wrapping shape (K.2)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Section | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 21-R38 | builder | MISSING | major | Copilot path must construct V2 `LlmJudgeProperties` from V1-shaped Copilot responses via a `v1_to_v2_prompt_template()` function | §10.1-10.3 "The Copilot translation constructs a Jinja2 prompt_template that embeds the V1 content in V2 syntax" | No `v1_to_v2_prompt_template` function found anywhere in the codebase. `grep -rn "v1_to_v2" /Users/scosman/Dropbox/workspace/kiln_new/` returns no results. The copilot API (`copilot_api.py`) has no LLM judge references. | The V1-to-V2 wrapping path is not implemented. |
| 21-R39 | builder | CONTRADICTED | major | The LLM judge create form should produce V2 `LlmJudgeProperties` with `prompt_template` (via the wrapping shape) | §10.3-10.4 "V1 fields... must be wrapped into a complete V2 prompt_template" | `create_eval_config/+page.svelte:346-347` — when `is_llm_judge`, calls `llmJudgeFormComponent.getConfigType()` which returns `"g_eval"` or `"llm_as_judge"` (V1 types). `llm_judge_form.svelte:36-41` returns `{ eval_steps, task_description }` — a V1 properties dict. The config is created as a V1 legacy config, not a V2 config with LlmJudgeProperties. | The form creates V1 legacy configs instead of V2 configs with prompt_template. The spec explicitly designed the unified llm_judge type to supersede V1's g_eval and llm_as_judge types. |
| 21-R40 | builder | MISSING | minor | `required_var` should be empty `[]` for wrapped V1-to-V2 templates | §10.6 | No wrapping exists (see 21-R38), so required_var derivation is also missing | Dependent on 21-R38. |
| 21-R41 | validation | PARTIAL | minor | Generated template must pass `compile_template_or_raise()` and reference at least one non-`reference_data` reserved variable | §10.7 "at least one reference to a non-reference_data reserved variable" | `eval.py:706-712` — save-time validation checks for any `{{` or `{%` syntax, but does NOT specifically verify a non-reference_data variable is referenced. A template using only `{{ reference_data.foo }}` would pass. | The check is weaker than what the spec requires. |

### Section 11 — Adapter architecture

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Section | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 21-R42 | architecture | PARTIAL | minor | `LlmJudgeAdapter` subclasses `BaseEval` directly (no BaseEvalV2 fork) | §11.1 "subclasses BaseEval directly (C.11c: no BaseEvalV2 fork)" | `v2_eval_llm_judge.py:76` — `class LlmJudgeEval(BaseV2EvalBridge)`. `base_eval.py:217` — `class BaseV2EvalBridge(BaseEval)`. There IS a `BaseV2EvalBridge` intermediate class, not a direct BaseEval subclass. | The spec says "no fork", but `BaseV2EvalBridge` is a thin V2 shim. It still inherits from `BaseEval`, so the "no fork" spirit is preserved (it's not a separate base class for V2), but the intermediate class wasn't in the spec. This is a minor architectural difference. |
| 21-R43 | architecture | MET | — | Reads `model_name` and `model_provider` directly from properties, not via helper | §11.2 | `v2_eval_llm_judge.py:126-127` — `model_name = props.model_name`, `provider = ModelProviderName(props.model_provider)` | — |
| 21-R44 | architecture | MET | — | Registered in V2 sub-registry (`_V2_ADAPTER_MAP`) | §12.3 | `registry.py:32` — `V2EvalType.llm_judge: LlmJudgeEval` | — |

### Section 3 — Per-criterion pass/fail verdicts

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Section | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 21-R45 | pattern | MET | — | Per-case criteria stored as `reference_data.llm_judge_criteria` iterable in template | §3.1 | Template-driven pattern; the Jinja2 engine supports `{% for %}` over `reference_data.llm_judge_criteria`. No special code needed beyond template rendering, which is implemented at `v2_eval_llm_judge.py:109-111`. | — |
| 21-R46 | pattern | MET | — | `Eval.output_scores` defines score dimensions; `build_score_schema()` generates JSON schema | §3.2 | `v2_eval_llm_judge.py:114-115` — `BaseEval.build_score_schema(self.eval, allow_float_scores=False)` | — |

### Section 12 — V1 backwards compatibility

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Section | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 21-R47 | compat | MET | — | V1 EvalConfigs continue running through existing GEval adapter (zero V1 behavior changes) | §12.1 "Zero V1 behavior changes, ever." | Legacy dispatch path in `registry.py` still maps `g_eval` and `llm_as_judge` to GEval. LlmJudgeEval is only in `_V2_ADAPTER_MAP`. | — |
| 21-R48 | compat | MET | — | No auto-upgrade from V1 to V2 | §12.2 | No migration code found. V1 configs stay V1. | — |
| 21-R49 | compat | MET | — | V2 adapter is additive; coexists with GEval in separate registry | §12.3 | `registry.py:25-32` — `_V2_ADAPTER_MAP` separate from legacy dispatch | — |

### General / Cross-cutting

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Section | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 21-R50 | data-model | DEFERRED_OK | — | Future config-driven trace condensation deferred to post-V2 | §8.3 | No condensation config fields on LlmJudgeProperties | Correctly omitted. |
| 21-R51 | data-model | DEFERRED_OK | — | RAG templates deferred from V2.0 | §source list — "deferred from V2.0" | No RAG template code found | Correctly omitted. |
| 21-R52 | execution | CANNOT_VERIFY | — | `SkipCaseError` is the adapter-level mechanism for triggering a C.runner.1 skip | §11.4 sketch note | The adapter returns `(scores, SkippedReason, detail)` tuple instead of raising an exception. The runner handles skips via the return value. Whether this matches C.runner.1 exactly would require checking components/45. | — |
| 21-R53 | validation | MET | — | Save-time validation: `compile_template_or_raise()` on `prompt_template` | §10.7 | `eval.py:705` — `compile_template_or_raise(props.prompt_template)` in model validator | — |
| 21-R54 | validation | MET | — | Save-time validation: `compile_expression_or_raise()` on each `required_var` | §10.7 | `eval.py:713-714` — loops over `props.required_var` calling `compile_expression_or_raise(var)` | — |

---

## Verifier-added items (re-scan)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Section | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 21-V01 | execution | PARTIAL | minor | Adapter class name should be `LlmJudgeAdapter` | §11.4 "class LlmJudgeAdapter(BaseEval)" | `v2_eval_llm_judge.py:76` — `class LlmJudgeEval(BaseV2EvalBridge)` | Named `LlmJudgeEval` instead of `LlmJudgeAdapter`. The spec's sketch used `LlmJudgeAdapter`. Minor naming divergence. |
| 21-V02 | execution | CANNOT_VERIFY | — | Structured output mode for `g_eval=True` should be `json_schema` only (not function_calling) | §4.1 "Structured output mode: json_schema only (not function_calling)" | The code always disallows function_calling (see 21-R19), so g_eval=True does get json_schema. But g_eval=False also gets the same restriction, which contradicts the spec. The g_eval=True requirement itself is MET; the divergence is captured in 21-R19. | — |

---

## Summary

The `LlmJudgeProperties` data model is faithfully implemented. The backend adapter correctly handles Jinja2 template rendering, required-var pre-checks, g_eval/non-g_eval score parsing, forward_thinking_instructions wiring, and scoring-helper consumption from `scoring_utils.py`.

**Key gaps:**

1. **CONTRADICTED (21-R19):** Function_calling is disallowed for both g_eval modes. The spec allows function_calling when `g_eval=False` to broaden model support.

2. **CONTRADICTED (21-R39):** The LLM judge create form produces V1 legacy configs (`g_eval` / `llm_as_judge` with `eval_steps` / `task_description`) instead of V2 configs with `LlmJudgeProperties` and `prompt_template`. This means users creating LLM judge configs through the UI get V1 configs, not the V2 unified type the spec designed.

3. **MISSING (21-R38):** The `v1_to_v2_prompt_template()` wrapping function specified in §10 does not exist. No copilot path translates V1 eval_steps into a V2 Jinja2 prompt_template.

4. **PARTIAL (21-R28):** Default system_prompt text differs from spec ("You are an evaluator." vs actual), and the default is applied at runtime rather than baked into the EvalConfig at creation time.

5. **MISSING (21-R31):** Default `thinking_instruction` is not resolved at creation time as the spec requires for snapshot completeness.
