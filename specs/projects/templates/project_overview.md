---
status: complete
---

# Templates

<!-- edit permission check -->
<!-- edit permission verified -->


This is a new project to add input templates to Kiln run configs. Input templates take the raw input passed to Kiln and transform it in some way. They key one for first version is Jinja2 templates taking json, converting to some new format.

The details below were written by another agent.
 - They are quite detailed, but not final and we can still change
 - The agent in question is the "eval v2" agent, which will be a consumer of this project. That's why it cares about details.

 I've reviewed a lot of this, but it's NOT FINAL even if it looks uber detailed. During planning, review the codebase to make sure it'a appriopiate, make sure the APIs make sense for a general purpose input transformation.

 While we aren't building a UI for it in this project, we will later.

 # Spec from other Agent

 ----

 ---
status: complete
---

# Prereq: Jinja Input Transform on RunConfig

**Source(s):** Group A conversation 2026-05-22 — 2026-05-25; `research_judge_prompts/_input_transform_proposal_analysis.md`, `research_judge_prompts/_input_transform_details.md`; Steve's input_transform proposal (verbatim, captured below); ALIGNMENT.md A0.1
**Author:** Steve + Claude (interactive design)
**Status:** complete — design locked; implementation handed to coding agent
**Type:** Kiln core infrastructure (NOT eval-specific). Evals V2 is one consumer.

---

## TL;DR

- New optional field `input_transform: InputTransform | None` on `KilnAgentRunConfigProperties`. Default `None` = current behavior unchanged.
- V1 ships one concrete transform type: `JinjaInputTransform` — Jinja2 template that projects structured task input into the model-facing user-message string.
- Two Jinja2 usage modes (both in the shared engine): full template render (`StrictUndefined`) for the prompt; single-expression evaluation (default `Undefined`) for value extraction. Both exported as a public API in `libs/core` for any consumer (evals being the first).
- Templating requires structured (JSON-schema) task input. Plaintext input with no transform is the existing identity path — unchanged.
- Missing variables and invalid JSON fail hard pre-inference (deterministic, attributable). This is the right error model for general tasks. Consumers that need softer semantics (e.g., evals' skip-with-reason) wrap the API with a pre-check.
- Engine: Jinja2 `SandboxedEnvironment`. Templates are author-time content but may come from collaborators / shared datasets; sandbox from day one.
- Rendered output is captured in the existing `TaskRun.trace` mechanism (first user message of the trace is the rendered input). No new `TaskRun` field required.
- V1 EvalConfigs and existing RunConfigs are unaffected (`input_transform=None` default).

---

## 1. Goal + Scope

### What this is

A new optional field on `KilnAgentRunConfigProperties` that lets RunConfigs transform the task input into the user-message payload at runtime, using a Jinja2 template. This is a **general Kiln task capability** — any task type can use it, not just evals.

### What this is NOT

- Not a new task input mode. The task's input contract stays the same: plaintext OR JSON-matching-schema, locked at task creation. Templating is a projection OVER structured input, not a peer of plaintext / JSON.
- Not a custom DSL. We use Jinja2 unchanged, with `StrictUndefined` for templates and `SandboxedEnvironment` for security.
- Not eval-specific. Evals will be the first consumer (V2 llm_judge templates, V2 simple-check expression extraction), but the design must serve future consumers (general task prompt versioning, A/B testing, etc.) just as well.

### Steve's proposal (verbatim, for context)

> Context: Kiln tasks currently accept input as either plaintext or JSON-matching-a-schema, with the mode locked at task creation. We're adding Jinja templating. The original plan scoped templates to evals; we've decided instead to make templating a general task-level capability via input_transform, with evals as the first client rather than the owner.
>
> The design:
> - input_transform is an optional field on run config (not task config, not a new input mode). It applies a transformation to an existing task input at run time, producing the model-facing payload. The task's input contract is unchanged — still plaintext or JSON-schema, still locked at creation. We are NOT adding a third input type. Templating is a projection over structured input, not a peer of plaintext/JSON.
> - Engine: Jinja with two non-negotiable settings — StrictUndefined (missing vars must raise, not render empty) and SandboxedEnvironment (sandbox from day one).
>
> The contract: structured input + valid template → rendered prompt; anything else → hard error at config or render time, before inference.
> - Template transforms require structured (JSON) input. Plaintext + no-transform is identity.
> - Invalid JSON or missing variables fail totally, immediately, pre-inference.

---

## 2. Data Model

### `InputTransform` discriminated union

```python
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Discriminator, Tag, field_validator

class JinjaInputTransform(BaseModel):
    """Render task input via a Jinja2 template, producing a string for the model.
    
    The template is rendered against the task's structured input as the
    rendering context (top-level fields accessible directly — no `data.` wrapper).
    """
    type: Literal["jinja"] = "jinja"
    template: str  # Jinja2 source. Validated at save time.
    
    @field_validator("template")
    @classmethod
    def validate_template_compiles(cls, v: str) -> str:
        from kiln_ai.<path>.jinja_engine import compile_template_or_raise
        compile_template_or_raise(v)  # raises ValueError on syntax error
        return v


def _get_input_transform_type(v):
    if isinstance(v, dict):
        return v.get("type")
    return getattr(v, "type", None)

# Discriminated union; V1 has exactly one member. Add more via Union extension.
InputTransform = Annotated[
    Union[Annotated[JinjaInputTransform, Tag("jinja")]],
    Discriminator(_get_input_transform_type),
]
```

### Placement on `KilnAgentRunConfigProperties`

Add `input_transform` to the existing class at `libs/core/kiln_ai/datamodel/run_config.py:48-97`:

```python
class KilnAgentRunConfigProperties(BaseModel):
    type: Literal["kiln_agent"] = "kiln_agent"
    model_name: str
    model_provider_name: ModelProviderName
    prompt_id: PromptId
    # ... existing fields ...
    input_transform: InputTransform | None = None  # NEW — default None preserves current behavior
```

**Important: NOT on `TaskRunConfig` (parent), NOT on `Task`, NOT on `McpRunConfigProperties`.**
- `TaskRunConfig` (`task.py:63-105`) is the persistence wrapper; the agent-specific configuration belongs in the agent's RunConfigProperties subclass.
- `Task` would tie one transform per task — breaks the "same eval, different judge prompts" workflow (per ALIGNMENT.md C.9).
- `McpRunConfigProperties` does not need this — MCP tools receive raw input.

### Immutability

`TaskRunConfig` is immutable-by-convention (no `frozen=True` on `KilnParentedModel`, but the workflow is create-once / reference-by-ID — same as `EvalConfig`). `input_transform` follows the same convention: changing the field on a saved RunConfig is "don't do that," not enforced by Pydantic.

If we ever choose to enforce immutability on RunConfigs (recommended but out of scope here), `input_transform` participates in that enforcement automatically.

---

## 3. Engine Setup

Both modes use the same `SandboxedEnvironment` instance for consistency. The difference is which API method is used per call.

```python
# libs/core/kiln_ai/<path>/jinja_engine.py  (path: coding agent decides)

from jinja2.sandbox import SandboxedEnvironment
from jinja2 import StrictUndefined, Undefined, TemplateSyntaxError, UndefinedError

# Single shared instance for rendering judge prompts / templates
_template_env = SandboxedEnvironment(undefined=StrictUndefined)

# Separate instance for single-expression extraction with softer Undefined semantics
_expression_env = SandboxedEnvironment(undefined=Undefined)
```

**Why two envs:**
- Template render needs `StrictUndefined` — if a template references a missing variable, that's a bug the user should see immediately. Hard error pre-inference.
- Expression evaluation (used by consumers that pre-check values) needs default `Undefined` — `Undefined` is falsy, distinct from `None` (explicit null vs missing key), composable with `| default(...)` filter. This gives the eval consumer's `required_var` pre-check a clean signal: extracted value is `Undefined` → required check fails → skip the case with a reason.

**Why same SandboxedEnvironment class** — Same security model, same syntax surface, same custom filters (when we add any post-V2.0). The two `env` instances are configuration variants.

---

## 4. Public API

Three public functions exported from `libs/core/kiln_ai/<path>/jinja_engine.py` (final path picked by implementer):

```python
def compile_template_or_raise(template: str) -> None:
    """Validate that the template compiles. Used by save-time validators.
    
    Raises ValueError with the Jinja2 error message if invalid.
    """
    try:
        _template_env.from_string(template)
    except TemplateSyntaxError as e:
        raise ValueError(f"Invalid Jinja2 template: {e.message} (line {e.lineno})")


def render_input_transform(transform: InputTransform, task_input: dict) -> str:
    """Render the transform against the task's structured input.
    
    Returns the rendered string (model-facing user message body).
    
    Raises:
        UndefinedError: if the template references a missing variable.
        TemplateSyntaxError: if the template is malformed (should not happen
            at runtime since save-time validation rejects bad templates;
            included for safety).
    
    Note: `task_input` must be a dict (JSON-schema-matching structured input).
    Templating over plaintext is not supported.
    """
    if isinstance(transform, JinjaInputTransform):
        return _template_env.from_string(transform.template).render(**task_input)
    raise ValueError(f"Unknown transform type: {type(transform).__name__}")


def extract(expression: str, data: dict) -> Any:
    """Evaluate a Jinja2 expression against a data dict and return the result.
    
    Used by consumers that pre-extract individual values from structured data
    (e.g., the evals consumer uses this for `required_var` pre-checks and for
    simple-check `value_expression` fields).
    
    Returns:
        The evaluated value. May be a string, dict, list, int, None (explicit
        null), or Undefined (missing key). Generators are auto-materialized
        to lists.
    
    Raises:
        TemplateSyntaxError: if the expression is malformed (caught at save
            time by consumers that validate).
    """
    import types
    compiled = _expression_env.compile_expression(expression)
    result = compiled(**data)
    if isinstance(result, types.GeneratorType):
        result = list(result)
    return result


def compile_expression_or_raise(expression: str) -> None:
    """Validate that an expression compiles. Used by consumer save-time validators."""
    try:
        _expression_env.compile_expression(expression)
    except TemplateSyntaxError as e:
        raise ValueError(f"Invalid Jinja2 expression: {e.message} (line {e.lineno})")
```

**Why `extract` lives here:** It's general Jinja2 expression evaluation, not eval-specific. Any future consumer (general task input introspection, prompt A/B testing, etc.) gets the same primitive for free.

---

## 5. Compile-Time Validation

### RunConfig save

When a RunConfig with `input_transform: JinjaInputTransform` is saved:

- The `validate_template_compiles` validator on `JinjaInputTransform` runs `compile_template_or_raise(template)`.
- Invalid Jinja2 syntax → Pydantic `ValidationError` → save rejected.

This catches template typos / unclosed blocks / bad filter names at save time, before any runtime invocation.

### Consumer save (informational, not enforced here)

Consumers that hold Jinja2 expressions (e.g., the evals consumer's `value_expression` and `required_var` fields) should run `compile_expression_or_raise` in their own field validators. The prereq infra exposes the helper; consumers use it.

---

## 6. Runtime Execution

### Where in the adapter chain

The transform sits between "task input received" and "input handed to the prompt builder / formatter":

1. Adapter is invoked with the task's structured input (dict).
2. If `run_config.input_transform is not None` AND the task has `input_json_schema` (structured input) → call `render_input_transform(transform, task_input)` to produce a rendered string.
3. Pass the rendered string as the model-facing user message body. From the formatter's perspective downstream, this is just a string input — same as it would have received without a transform.
4. If `input_transform is None` → existing behavior (input passes through unchanged).

The implementer picks the exact insertion point in `libs/core/kiln_ai/adapters/model_adapters/base_adapter.py` (likely inside or before `_run_returning_run_output`).

### Input contract

`input_transform` requires the task's input to be structured (JSON matching `input_json_schema`). Reason: templating projects fields of a structured value into a rendered string. A plaintext input has no fields to project.

**Validation at task association time (recommended):** if a RunConfig with `input_transform` is associated with a task that has no `input_json_schema`, that's a misconfiguration. Validate at the RunConfig-task linking point, OR at the first run attempt.

Implementer's discretion on where to enforce. Both work; first-run is simpler.

### Output contract (V1)

Renders to a string. Future extension (NOT V1): emit structured output (template → JSON for a JSON-schema task). Don't foreclose this in the type signature even though V1 only implements string output. See §11 Open.

---

## 7. Error Handling

All transform errors are pre-inference (the inference call is not made if the transform fails).

| Error | When | Behavior |
|---|---|---|
| Template syntax error | Save time | Pydantic ValidationError; save rejected |
| Template syntax error | Runtime (shouldn't happen — save-time blocks it) | Re-raise as runtime error |
| `UndefinedError` from `StrictUndefined` | Runtime (template references a missing variable) | Hard error pre-inference. Surfaces user errors so they can fix them. |
| Task input is not a dict (e.g., plaintext) | Runtime | Hard error pre-inference with clear message ("input_transform requires structured task input") |
| Render error (custom filter exception, etc.) | Runtime | Hard error pre-inference |

**This is the general-task philosophy: fail loud, fail fast, fail attributable.** Consumers that need softer semantics (e.g., evals' skip-with-reason) wrap the API with their own pre-check (see §11 Eval consumer).

---

## 8. Persistence

**No new `TaskRun` field required.** The rendered model-facing input is already captured in `TaskRun.trace` (first user message) by the existing trace mechanism.

To inspect what the model received after transform, read `TaskRun.trace[0]` (or whichever message is the first user message — implementer to confirm exact position based on existing trace conventions).

Implications:
- No schema migration to `TaskRun`
- Inspection of "what did the model actually see after templating" is already available in existing tooling

If a future need arises for storing template input separately from the rendered output (e.g., to re-run with a different template version), that's an additive change. Not V1.

---

## 9. V1 Backwards Compatibility

- `input_transform: InputTransform | None = None` — default `None` means no transform.
- All existing RunConfigs in the wild have no `input_transform` field. After this change, they parse as having `input_transform=None`. Behavior unchanged.
- Adapter code that runs with `input_transform is None` skips the render step entirely — identity path.
- No V1 EvalConfig is affected. V1 evals use the existing `GEval` adapter (`g_eval.py`) which constructs prompts via hardcoded f-strings, doesn't go through `input_transform`.

**Per ALIGNMENT.md A0.1: V2 reads V1; V2 never migrates V1. This change is additive — no V1 behavior is altered.**

---

## 10. Security

### Threat model

Templates are user-authored content stored in RunConfig. Risk surfaces:

1. **Local user authoring own templates:** low risk — user has full local access already.
2. **Shared RunConfigs from other team members:** medium risk — a malicious template author could include attribute access on dangerous objects to exfiltrate data.
3. **Templates from public datasets / community libraries:** higher risk — unvetted content.

### Mitigations

- **`SandboxedEnvironment`** — Jinja2's sandboxed environment disallows attribute access on dangerous methods (`__class__`, `__bases__`, `__subclasses__`, etc.) used in known Jinja2 SSTI exploits. This is the standard mitigation for user-authored Jinja2 templates.
- **No file I/O loaders** — we render templates from inline strings only, not via `FileSystemLoader` or similar. No risk of reading arbitrary files.
- **No custom filters with side effects** — V1 ships no custom filters. Future custom filters must be pure (no I/O, no state mutation).
- **Compile-time validation** — catches obvious typos / bad syntax before runtime.

### Out of scope

- Resource limits (CPU, memory) on template rendering. Jinja2's `SandboxedEnvironment` doesn't bound execution time. If a template enters a pathological loop (e.g., user typo combining `{% for %}` and unbounded data), the render call can hang. Future hardening if needed.

---

## 11. Tests

Required validation at implementation:

### Unit tests

- `JinjaInputTransform` field validator rejects malformed templates with a clear error
- `render_input_transform` correctly substitutes variables from a dict input
- `render_input_transform` raises `UndefinedError` on a template referencing a missing variable
- `extract` returns Python objects (string, list, dict, int) per the expression
- `extract` returns `Undefined` for missing keys (default mode, not strict)
- `extract` returns `None` for explicit null values
- `extract` materializes generators to lists (test: `data | map(attribute='x') | list` returns a list, not a generator)
- `compile_template_or_raise` and `compile_expression_or_raise` raise `ValueError` with line/column info on invalid input

### Integration tests

- A RunConfig with `input_transform: JinjaInputTransform(...)` saves, loads, and renders correctly end-to-end
- A RunConfig with `input_transform=None` (or absent) runs through the adapter chain unchanged (V1 behavior preserved)
- Sandbox enforcement: a template trying to access `__class__.__bases__[0].__subclasses__()` raises `SecurityError` (Jinja2's sandbox catches this)

### Backcompat tests

- Existing on-disk RunConfigs (without the new field) load cleanly and behave as before
- A RunConfig saved with `input_transform=None` is functionally equivalent to one with no field set

---

## 12. Eval Consumer (isolated section)

This is here so the implementer knows the constraints from the first consumer, but the eval-specific design lives in `design/40_template_and_extraction.md`. The prereq infra MUST work for evals; the eval design DOC describes how evals use it.

### How evals will consume `input_transform` (high level)

1. Eval runner takes an `EvalInput` + the `TaskRun` being evaluated.
2. Assembles a synthetic JSON document with four fields:
   ```python
   {
     "final_message": str | dict,  # TaskRun.output.output
     "trace": list | None,         # TaskRun.trace (modified OpenAI format)
     "reference_data": dict | None, # EvalInput.reference
     "task_input": str | dict       # TaskRun.input
   }
   ```
3. For V2 `llm_judge` EvalConfigs:
   - The judge runs as a Kiln task. Its `RunConfig` carries a `JinjaInputTransform` with the user-authored `prompt_template`.
   - The eval runner calls `render_input_transform(transform, synthetic_input)` to produce the user message string.
   - Before render, eval runner pre-evaluates each `required_var` expression via `extract(...)`. If any returns `Undefined` or `None`, the case is skipped with `skipped_reason: "missing_required_var:<expr>"` (no template render, no inference). This is the eval-specific soft-fail layer wrapping the prereq's hard-fail engine.
4. For V2 simple-check EvalConfigs (`exact_match`, `pattern_match`, etc.):
   - These don't render templates. They call `extract(value_expression, synthetic_input)` to pull a single value, then compare it to `expected_value` / `reference_data[reference_key]`.

### Constraints the prereq infra must respect

- **`extract` returns `Undefined` for missing keys (not raises).** The eval `required_var` pre-check relies on being able to distinguish "missing" from "present-but-null" without trying-and-catching exceptions on every check.
- **Both `render` (StrictUndefined) and `extract` (default Undefined) use the same engine class** — the eval runner relies on a single security/sandbox surface. If they diverge in capability (e.g., one supports a custom filter the other doesn't), eval consumption will hit weird edge cases.
- **Public API surface** — `render_input_transform`, `extract`, `compile_template_or_raise`, `compile_expression_or_raise` must all be importable from the same module. Evals will import all four.

### What's NOT in the prereq infra (eval-side concerns)

- `EvalTaskInput` Pydantic model — eval-specific assembly, lives in eval code
- `required_var` field, skip semantics, structured `skipped_reason` values — eval-specific
- Simple-check `value_expression` validators — eval-specific
- Reserved-variable rules (`final_message`, `trace`, `reference_data` are always top-level) — eval consumer's convention, not a prereq concern. From the prereq's perspective, the eval runner just passes a dict with whatever keys.

---

## Opens

- [ ] **Final module path** in `libs/core` for `jinja_engine.py` (or whatever it's named). Coding agent picks the right location. Suggested: `libs/core/kiln_ai/utils/jinja_engine.py` or similar.
- [ ] **Exact insertion point** in the adapter chain for the transform render call. Coding agent picks; likely inside `_run_returning_run_output` or just before formatter assembly in `base_adapter.py`.
- [ ] **Plaintext-input validation timing** — fail at RunConfig save (when the user pairs a transform-bearing RunConfig with a no-schema task) vs. fail at first run. Either works; coding agent picks.
- [ ] **Structured output emission** — V1 emits string only. Don't foreclose JSON output in the future; the V2 `JinjaInputTransform.type` discriminator allows adding a `JsonJinjaInputTransform` later without breaking V1.
- [ ] **Resource limits** — Jinja2 sandbox doesn't bound CPU/memory. If users author pathological templates, render can hang. Defer to future hardening.

---

## Sources

- `libs/core/kiln_ai/datamodel/task.py:63-105` — `TaskRunConfig` (parent of RunConfigProperties)
- `libs/core/kiln_ai/datamodel/run_config.py:48-97` — `KilnAgentRunConfigProperties` (placement target)
- `libs/core/kiln_ai/datamodel/run_config.py:121-127` — `RunConfigProperties` discriminated union
- `libs/core/kiln_ai/adapters/model_adapters/base_adapter.py:209-215` — `invoke_returning_run_output` (probable insertion point)
- `libs/core/kiln_ai/utils/open_ai_types.py:125-168` — `ChatCompletionMessageParam` (trace message type)
- `libs/core/kiln_ai/tools/built_in_tools/kiln_api_call_tool.py:131-140` — existing Kiln jq usage pattern (reference for how external libs are integrated)
- `research_judge_prompts/_input_transform_details.md` — Jinja2 expression coverage verification + data model sketches
- `research_judge_prompts/_input_transform_proposal_analysis.md` — original Full Move analysis
- `design/40_template_and_extraction.md` — eval consumer design (downstream of this prereq)
- ALIGNMENT.md A0.1 — backwards compat principle
- Steve's input_transform proposal (verbatim in §1)
