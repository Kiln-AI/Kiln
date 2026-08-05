---
status: complete
approved: true
alignment_refs: [D.1, D.2, D.3, D.4, D.5]
opens: []
summary: Jinja2 input transform, extract() helper, eval consumer design, V1 BC under templates path.
---

# Evals V2 Templates + Extraction (Batch D, reframed Round 2)

**Source(s):** Group A conversation 2026-05-22 — 2026-05-26; `components/06_prereq_input_transform.md` (general Kiln infra prereq); `research_judge_prompts/_synthesis.md`, `research_judge_prompts/kiln_v1.md`, `research_judge_prompts/_input_transform_proposal_analysis.md`, `research_judge_prompts/_input_transform_details.md`; reference/ALIGNMENT.md A1, A2, D
**Author:** Steve + Claude (interactive design)
**Status:** complete

## TL;DR

- **Templating is a general Kiln capability, not eval-owned.** V2 evals are the first consumer of the `input_transform` infrastructure defined in `components/06_prereq_input_transform.md`. No eval-specific Jinja2 engine, no eval-specific FilterSpec data model.
- **One extraction mechanism** across all V2 eval types: Jinja2 expressions via the shared `extract()` helper from the prereq module. `FilterSpec` is gone. jq dependency removed from the eval path.
- **V2 `llm_judge` is a Kiln task** whose RunConfig carries a `JinjaInputTransform` with the user-authored prompt template. Eval runner assembles a synthetic input JSON (`EvalTaskInput`), passes it through the transform, and inference produces a structured score response.
- **Four reserved top-level template variables:** `final_message`, `trace`, `reference_data`, `task_input`. No `data.` wrapper. User templates write `{{ (final_message | fromjson).classification }}` directly for JSON outputs. Names are reserved at save-time.
- **Immutable EvalConfigs.** Defaults resolved and saved at creation time, never applied at runtime. Future code changes can't silently mutate saved evals.
- **V1 backwards compatibility absolute.** V1 EvalConfigs (`config_type: g_eval` / `llm_as_judge`) keep running through the existing hardcoded f-string path. Zero V1 behavior changes (A0.1).

---

## 0. Motivation

V1 Kiln has best-in-class score extraction (typed `output_scores` → JSON schema → structured output enforced + g_eval logprob weighting). But V1's prompt surface is rigid:

- No user-editable prompt — judge prompts are hardcoded f-strings in `g_eval.py`. Users only fill `task_description` and `eval_steps`.
- No field extraction — judges receive whole outputs / whole traces.
- Required `eval_steps` as a numbered list — G-Eval-paper convention, not general.
- Hardcoded system-message scaffold with rigid XML wrapping.

Group A originally scoped a Batch D fix as eval-owned templating + jq extraction. **Round 2 (2026-05-26):** elevated to a general Kiln task capability (`input_transform` on `RunConfig`) per Steve's principle that templating is general, evals are first consumer. This doc captures the eval-side consumption of that general infrastructure.

The original Batch D design (eval-owned `FilterSpec` + Jinja2) is superseded by this version. Old design is in git history if needed.

---

## 1. Principles

### 1.1 Consume the general infrastructure
Evals do NOT own Jinja2, the sandbox, or the extraction primitive. All of that is in `components/06_prereq_input_transform.md` and exported from `libs/core`. Evals import `render_input_transform`, `extract`, `compile_template_or_raise`, `compile_expression_or_raise` and use them.

### 1.2 One extraction mechanism
All V2 eval types use the same `extract()` helper (Jinja2 expression evaluation). `llm_judge` uses it for `required_var` pre-checks. Simple-check types (`exact_match`, `pattern_match`, `contains`, `set_check`) use it for `value_expression` extraction. `tool_call_check` and `step_count_check` are the typed exceptions (per A2.4 + Batch J) -- they walk the trace internally and do not use `extract()`.

### 1.3 Immutable EvalConfigs as full snapshots
`EvalConfig` represents the exact, reproducible configuration of an eval. Defaults are resolved and saved into the datamodel at creation time, never applied as runtime fallbacks. Applies to `system_prompt`, `thinking_instruction`, and any future default-bearing field.

Per Steve (2026-05-22): *"our eval configs are supposed to represent an exact config for an eval. If I change the code, the eval config shouldn't change like it does today."*

### 1.4 Use Kiln tasks natively
V2 evals run as Kiln tasks (like V1 `GEvalTask` in `g_eval.py:37-81`). They inherit existing chat-formatter, structured-output-mode selection, CoT routing, intermediate-output capture. **No new formatter infrastructure built inside V2 evals.** Cosmetic friction (e.g., `<user_input>` wrapping by `TwoMessageCotFormatter` for non-reasoning models) accepted — non-reasoning is the minority path now.

---

## 2. Synthetic Input Assembly

The eval runner assembles a synthetic JSON document per case from the `EvalInput` + the `TaskRun` being evaluated. This becomes the structured task input that `input_transform` projects from.

```python
class EvalTaskInput(BaseModel):
    """Synthetic input the eval runner constructs for a V2 eval task.
    
    NOT user-authored — built by the eval runner from EvalInput + TaskRun.
    Templates reference these fields directly as top-level variables.
    """
    final_message: str
    trace: list[ChatCompletionMessageParam] | None = None
    reference_data: dict[str, JsonValue] | None = None
    task_input: str | None
```

| Field | Sourced from | Notes |
|---|---|---|
| `final_message` | `TaskRun.output.output` | Always the raw string; use the `fromjson` filter to parse JSON outputs (e.g. `(final_message \| fromjson).field`) |
| `trace` | `TaskRun.trace` | Kiln's modified OpenAI format. `None` for `EvalDataType.final_answer` runs that don't carry traces |
| `reference_data` | `EvalInput.reference` | `None` if EvalInput has no reference |
| `task_input` | `TaskRun.input` | The original input given to the task being evaluated |

### Reserved top-level names

`final_message`, `trace`, `reference_data`, `task_input` are reserved. Templates reference them directly: `{{ (final_message | fromjson).classification }}` (for JSON outputs), `{{ reference_data.expected_answer }}`. No `data.` namespace wrapper.

User templates may NOT redefine these names via `{% set %}` (Jinja2 allows it but it's semantically wrong; we don't enforce but document).

### Sub-agent / trace format

Traces are stored in Kiln's modified OpenAI format, not OTEL. Sub-agent invocations appear as tool calls in the parent trace, not nested traces. A template's `{{ trace }}` walk does NOT see a sub-agent's internal trace. Right default for outcome-focused evals; a known limit for evals wanting per-step sub-agent inspection. Future feature (post-V2.0): opt-in flag to fetch and inject Kiln-owned sub-agent sub-traces.

---

## 3. Per-Type Properties

### 3.1 `llm_judge`

```python
class LlmJudgeProperties(BaseModel):
    type: Literal["llm_judge"] = "llm_judge"
    model_name: str
    model_provider: str
    system_prompt: str | None = None        # static string; see §7.1
    
    # The prompt template lives on the eval task's RunConfig as a
    # JinjaInputTransform. EvalConfig holds the source-of-truth template
    # string here; the eval runner constructs the task's RunConfig with
    # input_transform = JinjaInputTransform(template=prompt_template) at
    # invocation time. Stored on EvalConfig (not on RunConfig directly) so
    # immutability per §1.3 is preserved on the eval-config snapshot.
    prompt_template: str                    # Jinja2 template; REQUIRED
    
    # Jinja2 expressions that must evaluate to non-None / non-Undefined.
    # If any fails, the case is skipped pre-render with structured reason.
    # Example: ["final_message", "reference_data.expected_answer"]
    required_var: list[str] = []
    
    thinking_instruction: str | None = None  # see §7.2
    g_eval: bool = False                     # if True: top_logprobs=10, disallow function_calling
```

**Per-case flow:**
1. Eval runner builds `EvalTaskInput` for this case.
2. Pre-check each `required_var` expression via `extract(expr, eval_task_input.model_dump())`. If any returns `None` or `Undefined`, skip the case with `skipped_reason: extraction_failed` + `skipped_detail: "<expr>"` (no template render, no inference). Composes with C.runner.1.
3. Construct the eval task's RunConfig with `input_transform = JinjaInputTransform(template=prompt_template)`.
4. Invoke `adapter.invoke_returning_run_output(eval_task_input.model_dump())` — the prereq infra renders the template against the dict.
5. Structured score response parsed per the schema built from `Eval.output_scores`.

**Why `prompt_template` is on `LlmJudgeProperties` and ALSO ends up on RunConfig.input_transform at runtime:** the EvalConfig is the immutable snapshot — the source of truth lives there. RunConfig is constructed per invocation from the EvalConfig. This preserves immutability per §1.3 — saved EvalConfig templates can't change if Kiln core defaults change later.

**No `template_vars` field.** Templates access top-level synthetic-input fields directly. For DRYing repeated expressions, use Jinja2's built-in `{% set %}`:

```jinja
{% set summary = (final_message | fromjson).summary %}
{% set ref = reference_data.expected_summary %}
Compare {{ summary }} against expert: {{ ref }}
```

**No separate `criteria` / `eval_steps` field.** Criteria text goes directly into the `prompt_template`. The builder UX populates the full template at creation time.

**`g_eval` (renamed from `g_eval_mode`):**
- `True`: structured output disallows function_calling (logprob-weighted scoring needs the JSON in assistant content where token positions are findable); `top_logprobs=10`; probability-weighted scoring per V1 algorithm.
- `False`: pure llm_as_judge; no logprobs; function_calling allowed (broadens model support).
- This is the V2 equivalent of V1's `config_type` distinction (`g_eval` vs `llm_as_judge`).

### 3.2 Simple-check types

```python
class ExactMatchProperties(BaseModel):
    type: Literal["exact_match"] = "exact_match"
    value_expression: str | None = None    # Jinja2 expression; None = whole final_message
    expected_value: str | None = None      # literal
    reference_key: str | None = None       # OR pull from reference_data[reference_key]
    # exactly one of expected_value / reference_key required

class PatternMatchProperties(BaseModel):
    type: Literal["pattern_match"] = "pattern_match"
    value_expression: str | None = None
    pattern: str
    mode: Literal["must_match", "must_not_match"] = "must_match"

class ContainsProperties(BaseModel):
    type: Literal["contains"] = "contains"
    value_expression: str | None = None
    substring: str | None = None
    reference_key: str | None = None

class SetCheckProperties(BaseModel):
    type: Literal["set_check"] = "set_check"
    value_expression: str | None = None
    expected_set: list[str] | None = None
    reference_key: str | None = None
    mode: Literal["subset", "superset", "equal"] = "subset"
```

**`value_expression` semantics:**
- Jinja2 expression evaluated via `extract()` against `EvalTaskInput`. Returns whatever the expression yields (string, dict, list, int).
- If `None`: extracted value is the whole `final_message`.
- Save-time validation: `compile_expression_or_raise(value_expression)` from prereq infra.
- Null/missing extraction: case skipped with `skipped_reason: extraction_failed` + `skipped_detail: "<value_expression>"` per C.runner.1.

**Reference data pattern:**
- Simple check types: prefer typed `reference_key: str` field. Better DX, validates at save time that the key is provided, self-documenting.
- LLM judges: pull reference data via Jinja2 expression in `prompt_template` (`{{ reference_data.expected_answer }}`) or via `required_var` for must-have references.

`reference_data` appears as a top-level template variable AND as a typed `reference_key: str` field on simple types. The same `EvalInput.reference` dict is accessed two ways. **Not redundant** — they serve different ergonomic needs.

### 3.3 `tool_call_check`

Unchanged from prior Batch D design. Typed properties shape per A2.4 + Batch J Proposal 37. Does not use `input_transform` or `extract()`. Walks the trace JSON internally with a typed matcher.

### 3.3b `step_count_check`

Like `tool_call_check`, `step_count_check` is a typed deterministic trace inspector that does NOT use `value_expression`, `extract()`, or `input_transform`. It walks the trace internally and counts steps by `count_type` (`tool_calls` | `model_responses` | `turns`) against `min_count` / `max_count` bounds. Properties shape (`StepCountCheckProperties`) is locked in reference/ALIGNMENT.md J.38. Full type design is owned by `components/22_type_deterministic_basics.md`.

### 3.4 `code_eval`

Unchanged. Gets raw sources via helper library injected into the worker namespace. Per B.12 + B.13 (Phase 5).

---

## 4. Save-Time Validation

EvalConfigs with `llm_judge` or simple-check types must validate their Jinja2 strings at save time. Use the prereq infra:

- `prompt_template` → `compile_template_or_raise(prompt_template)` (full template)
- `required_var[i]` → `compile_expression_or_raise(expr)` (each expression)
- `value_expression` → `compile_expression_or_raise(value_expression)`

Invalid Jinja2 → Pydantic `ValidationError` → save rejected.

### Useless-template rejection (`llm_judge`)

A `prompt_template` that references zero variables, or only references variables that are sub-paths of `reference_data`, cannot meaningfully evaluate a model's output. Save-time validation parses the template AST to find variable references; rejects the save unless at least one reference is:
- A reserved top-level var that's NOT `reference_data` (`final_message`, `trace`, or `task_input`), OR
- A sub-path of one of those (`(final_message | fromjson).summary`, `trace[0].content`, etc.)

Error message: `"prompt_template must reference at least one variable from model output (final_message, trace, or task_input)."`

---

## 5. Built-in Template Library (V2 format)

V1 spec types (Toxicity, Bias, etc. — 17 types per `research_judge_prompts/kiln_v1.md` §10) currently store properties (`eval_steps`, `task_description`) that get reassembled into a prompt at runtime. **V2 templates store fully-authored Jinja2 strings directly.**

One-time content migration:
- Each existing V1 spec type re-authored as a V2 template: complete `prompt_template` Jinja2 string + optional `system_prompt`.
- The hardcoded eval_steps content from V1 ends up baked into the new prompt_template strings.
- UI ships V2-only: picking "Toxicity" fills the V2 form directly.
- V1 EvalConfigs continue to work via the V1 path (no migration of user configs).

Content work coordinated with Stage 5 builder UX (Batch G).

---

## 6. Concrete Examples

### 6.1 Simple exact match

```python
EvalConfig(
    config_type="v2",
    properties=ExactMatchProperties(
        type="exact_match",
        value_expression="(final_message | fromjson).classification",
        reference_key="expected_classification",
    )
)
```

Extracts `(final_message | fromjson).classification`, compares to `reference_data["expected_classification"]`.

### 6.2 Pattern match on whole output

```python
EvalConfig(
    config_type="v2",
    properties=PatternMatchProperties(
        type="pattern_match",
        # value_expression omitted = whole final_message
        pattern=r"^Summary:\s+.+",
        mode="must_match",
    )
)
```

### 6.3 LLM judge with template

```python
EvalConfig(
    config_type="v2",
    properties=LlmJudgeProperties(
        type="llm_judge",
        model_name="claude-sonnet-4-6",
        model_provider="anthropic",
        system_prompt="You are an expert evaluator. Respond honestly and concisely.",
        prompt_template="""\
{% set user_question = trace[0].content %}
{% set ref = reference_data.reference_answer if reference_data else none %}

The user asked: {{ user_question }}

The model produced this answer:
{{ final_message }}

{% if ref %}
Reference answer from expert:
{{ ref }}
{% endif %}

Score whether the model's answer is factually correct and well-aligned with the reference (if available).
""",
        required_var=["trace[0].content"],   # the user question must exist
        g_eval=True,
    )
)
```

If a particular EvalInput has no `reference_data`, the `{% if ref %}` block renders empty and the judge sees no reference section. If `trace[0].content` can't be extracted (e.g., no trace), the case is skipped.

---

## 7. Open Decisions

### 7.1 System message presence in V2 — RESOLVED

**Decision (2026-06-03):** V2 `llm_judge` always sends a system message. If the user doesn't author a `system_prompt`, the builder writes a generic default (`"You are an evaluator."`) into the EvalConfig's `system_prompt` field at creation time per §1.3 (immutable EvalConfigs). The default is editable via the code/library API for power users.

**No Kiln core change required.** This decision eliminates the conditional dependency on "make Kiln core system message optional." The `system_prompt` field is **not exposed in the builder UI** -- it is set by the default and only adjustable via the code/library API. This keeps the builder simple while preserving full control for power users.

This resolves `O-system-message-presence`.

### 7.2 `thinking_instruction` default — RESOLVED

V2 llm_judge has `thinking_instruction: str | None = None`. If `None` at creation, V2 builder writes Kiln's current default (`"Think step by step, explaining your reasoning."` from `prompt_builders.py:294-305`) into the EvalConfig at creation per §1.3.

V1 sources thinking_instruction from `eval_steps`; V2 from user override or saved default. Same shape, different source.

**Redundancy note:** users writing CoT framing into the `prompt_template` get the saved `thinking_instruction` ALSO appended by `TwoMessageCotFormatter` for non-reasoning models. Cosmetic redundancy, not broken. Users avoiding it set their own `thinking_instruction`.

**Reasoning models:** V2 llm_judge depends on `components/05_prereq_thinking_formatter_fix.md` (separate Kiln core fix) so reasoning models receive the saved `thinking_instruction` via the fixed formatter path.

---

## 8. Backwards Compatibility

V1 EvalConfigs (`config_type: "g_eval"` or `"llm_as_judge"`) keep running through:
- The existing `GEval` adapter class
- The existing three hardcoded f-string `generate_*_run_description` methods
- The existing `EvalDataType` enum at the Eval level
- The existing properties shape (`eval_steps`, `task_description`, `template_properties`)

**Zero V1 behavior changes.** Per A0.1. V1 path is permanent.

V2 EvalConfigs (`config_type: "v2"`, properties typed by `V2EvalType`) route through new V2 adapters that build per-invocation RunConfigs with `JinjaInputTransform`. Code sharing between V1 and V2 is via refactored helpers (Batch H 32a), not by mutating V1 paths.

---

## 9. Implementation Notes

- **Phase 0 prerequisites:**
  - `components/06_prereq_input_transform.md` — general `input_transform` on RunConfig (Jinja2 + sandbox + render/extract API)
  - `components/05_prereq_thinking_formatter_fix.md` — `SingleTurnR1ThinkingFormatter` reasoning-model fix
- Phase 0: add V2 type properties (`LlmJudgeProperties`, `ExactMatchProperties`, etc.) to the data model (already in PLAN.md Phase 0 sub-task 1).
- Phase 1: V2 llm_judge adapter that:
  - Builds `EvalTaskInput` per case
  - Pre-checks `required_var` via `extract()` (skip with reason on null/Undefined)
  - Constructs an eval task RunConfig with `JinjaInputTransform(template=prompt_template)`
  - Invokes through Kiln's task infrastructure
  - Wires `forward_thinking_instructions=True` on the formatter (depends on prereq #2)
- Stage 5: `components/21_type_llm_judge.md` consumes this for the judge type; `components/22_type_deterministic_basics.md` for simple-check types.
- Builder UX (Batch G): V2 template picker flow; one-time content migration from V1 spec types.

---

## Opens

### Resolved

- ~~**System message presence in V2 (§7.1)**~~ — [RESOLVED 2026-06-03: always-system-message + default `"You are an evaluator."`, lib/API-only, not a builder UI field].

### Open — implementation-time / smaller scope

- [ ] **`reference_key` vs `expected_value` exclusivity validation mechanics.** Directional coexistence resolved; implementation just needs a Pydantic `model_validator` on each simple-check type to enforce "exactly one of."
- [ ] **V1 template library content migration** — who authors the V2 versions of the 17 spec types. Stage 5 / Batch G content work.

### Confirmed no-action (notes only)

- **Few-shot examples:** users can author few-shot examples directly into their Jinja2 `prompt_template` or `system_prompt`. No separate mechanism. Per Steve's #13: Kiln builder handles few-shot today.
- **Custom Jinja2 filters** (e.g., recursive descent equivalent to jq's `..`): not in V2.0 scope, with the exception of `fromjson` (see below). Future additions to the shared `kiln_ai` engine module if needed.

### `fromjson` filter

A built-in Jinja2 `fromjson` filter is registered on both the template and expression environments. It parses a JSON string into a Python object (dict, list, or scalar). Usage: `(final_message | fromjson).field_name`.

**Strict behavior:** if the input is not a string, or not valid JSON, `fromjson` raises `JinjaExtractionError` (a `ValueError` subclass). In eval adapters, this error is caught and converted to a clean skip with `skipped_reason: extraction_failed` and a legible detail message. Templates using `fromjson` on non-JSON outputs will skip the case rather than crash the eval run.

---

## Sources

- `components/06_prereq_input_transform.md` — general Kiln capability this design consumes
- `components/05_prereq_thinking_formatter_fix.md` — reasoning-model fix prerequisite
- `research_judge_prompts/_synthesis.md` — cross-competitor patterns
- `research_judge_prompts/kiln_v1.md` — current V1 wire structure
- `research_judge_prompts/_system_message_verification.md` — 7/10 competitors omit system messages
- `research_judge_prompts/_kiln_task_infrastructure_compat.md` — Kiln task infra inheritance
- `research_judge_prompts/_input_transform_proposal_analysis.md` — original Full Move analysis
- `research_judge_prompts/_input_transform_details.md` — Jinja2 expression coverage + data model details
- `research_judge_prompts/_batch_d_design_audit.md` — audit of prior Batch D design (Round 1)
- reference/ALIGNMENT.md A0.1 (backwards compat), A1.x (EvalInput / reference), A2.x (EvalConfig V2 shape), C.runner.1 (skip semantics), D.1-D.5 (Batch D locks)
- PLAN.md Phase 0, Phase 1 — implementation slots
- Group A interactive conversation 2026-05-22 → 2026-05-26
