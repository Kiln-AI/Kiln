---
status: complete
---

# Functional Spec: Input Transform (project: templates)

## 1. Summary

Adds a new optional field `input_transform: InputTransform | None` to `KilnAgentRunConfigProperties`. When set, the configured transform runs at task invocation time, producing the string used as the **first user message** sent to the model. V1 ships a single transform variant — `JinjaInputTransform` — that renders a Jinja2 template against the input.

**Scope of what the transform produces:**
- It produces the **first user message only**.
- It does **not** modify the system prompt (which comes from `prompt_id`).
- It does **not** modify any subsequent user turns in multi-turn flows (e.g., tool-call follow-ups, COT scratchpad turns). Those are unaffected.

This is a **general Kiln capability**: any task type (plaintext, object-schema, array-schema) can use it. The eval v2 project is the first downstream consumer but is out of scope for this project.

## 2. Goals

- A user can attach a Jinja2 template to a RunConfig and have Kiln render the template at runtime, producing the first user message the model sees.
- The same engine API is reusable by any future consumer (eval v2, A/B prompt testing, etc.) — not eval-specific.
- Backward compatible: existing RunConfigs continue to behave exactly as before (`input_transform` defaults to `None` = identity path).
- Hard-fail pre-inference on any transform error so problems are deterministic and attributable.
- Author-time safety: malformed templates are rejected at save time, not at runtime.

## 3. Non-Goals (V1)

- No eval-side code (`EvalTaskInput`, `required_var`, `value_expression`, skip semantics). Eval V2 is a separate project that consumes this API.
- No UI for authoring or editing transforms. (Out of scope; a future project.)
- No structured output type. The transform always renders to a string. If a template happens to emit a JSON string, that's still a string from the model's perspective; there is no separate "JSON output" transform variant in V1.
- No CPU/memory bounds on render. Pathological templates can hang the render call. Documented risk; revisit if it bites.
- No custom Jinja2 filters with side effects in V1. Built-in Jinja2 filters only.

## 4. Data Model

### 4.1 `InputTransform` discriminated union

A new discriminated union following the `RunConfigProperties` precedent (`run_config.py:121-127`):

```python
InputTransform = Annotated[
    Union[
        Annotated[JinjaInputTransform, Tag("jinja")],
    ],
    Discriminator(_get_input_transform_type),
]
```

V1 ships exactly one variant. The union shape is forward-compat: new variants are added by extending the `Union`.

### 4.2 `JinjaInputTransform`

```python
class JinjaInputTransform(BaseModel):
    type: Literal["jinja"] = "jinja"
    template: str
```

- `type` is the discriminator tag (literal `"jinja"`).
- `template` is the Jinja2 source.
- A `@field_validator("template")` runs `compile_template_or_raise(...)` so malformed templates are rejected at save time.

### 4.3 Placement on `KilnAgentRunConfigProperties`

Add `input_transform` to `KilnAgentRunConfigProperties` (`run_config.py:47-101`) as a peer of `tools_config`:

```python
class KilnAgentRunConfigProperties(BaseModel):
    type: Literal["kiln_agent"] = "kiln_agent"
    # ... existing fields ...
    tools_config: ToolsRunConfig | None = None
    input_transform: InputTransform | None = None   # NEW
```

- Default `None` → existing behavior preserved.
- Not on `TaskRunConfig` (the persistence wrapper) — agent-specific config belongs in the agent's variant.
- Not on `Task` — the same task can have many RunConfigs with different transforms.
- Not on `McpRunConfigProperties` — MCP tools receive raw input.

## 5. Input Handling Rules

A RunConfig with `input_transform` accepts **any** task input type. The template always sees a single variable named `input`. The value of `input` depends on the task's input shape:

| Task input | Pre-processing | Value of `input` |
|---|---|---|
| Object schema (dict) | none | the dict (`{{ input.field_name }}`, `{{ input.items() }}`, etc.) |
| Array schema (list) | none | the list (`{{ input[0] }}`, `{{ input \| length }}`) |
| Plaintext (string) | try `json.loads(...)`; on success, use parsed value; on failure, use raw string | the parsed value (dict / list / scalar) or the raw string if parse fails |

**Variable-exposure rule (uniform):** the template always references `{{ input }}` (or attribute / index access from it). No top-level unpacking, no aliasing, no name-collision rules. Templates port unchanged across tasks with different input shapes.

**Plaintext auto-parse rationale:** Users who provide JSON-shaped plaintext get useful templating without changing task config. Users who provide non-JSON plaintext still get a usable `{{ input }}` variable. The "magic" (`"42"` parses to int 42, `"true"` to bool True) is accepted because Jinja2 handles those types fine in templates.

## 6. Output Contract

`render_input_transform(...)` returns a `str`. That string becomes the body of the **first user message** sent to the model, replacing the input that would otherwise have been passed to the prompt-builder / formatter.

- The string may contain anything — including content that happens to be valid JSON. From the model's perspective, it is text either way; this project does not model "string vs JSON" as separate types.
- Empty string is permitted (model receives an empty first user message). No special handling.
- The transform does not produce or modify the system prompt, subsequent user messages, assistant messages, or any other part of the conversation. See §1.

## 7. Engine Configuration

V1 uses Jinja2's `SandboxedEnvironment` in two configurations:

| Env | `undefined` | Used for | Behavior on missing var |
|---|---|---|---|
| Template env | `StrictUndefined` | `render_input_transform`, `compile_template_or_raise` | Raises `UndefinedError` |
| Expression env | `Undefined` (default) | `extract`, `compile_expression_or_raise` | Returns `Undefined` (falsy, distinct from `None`) |

Both environments share these options:

- `trim_blocks=True` — strips the newline after a block tag (cleaner prompt output).
- `lstrip_blocks=True` — strips leading whitespace before a block tag.
- No `FileSystemLoader` or other I/O loader. Templates are rendered from inline strings only.
- No custom filters in V1.

**Why two envs:** Template rendering wants hard-fail on missing vars (authors must see typos). Expression evaluation wants `Undefined` so callers can distinguish "missing key" from "explicit null" without exception handling.

**Why same sandbox class:** Same security boundary, same syntax surface, same filter set. The two envs are configuration variants of the same class.

## 8. Public API

Exported from `libs/core/kiln_ai/utils/jinja_engine.py`:

```python
def compile_template_or_raise(template: str) -> None:
    """Validate that the template compiles. Raises ValueError on syntax error."""

def render_input_transform(transform: InputTransform, task_input: Any) -> str:
    """Render the transform against task_input, returning the first-user-message string.

    task_input may be a dict, list, or string (for plaintext tasks).
    See §5 for the namespace construction rules.
    """

def extract(expression: str, data: dict) -> Any:
    """Evaluate a Jinja2 expression against a dict. Returns the Python value.

    Generators are auto-materialized to lists. Missing keys return Undefined
    (not None). Used by consumers that pre-extract individual values from
    structured data.
    """

def compile_expression_or_raise(expression: str) -> None:
    """Validate that a Jinja2 expression compiles. Raises ValueError on syntax error."""
```

`extract` and `compile_expression_or_raise` are general-purpose Jinja2 expression evaluation — not eval-specific. They ship in V1 because (a) they're tiny additions on top of the engine and (b) the next consumer (eval v2) will need them, so adding them later would be more churn than including them now.

**Compilation cost.** `compile_*_or_raise` returns `None`; it does not return a compiled object. `render_input_transform` and `extract` therefore re-compile their source on every call. Jinja2 compilation is fast (microseconds for typical prompt-sized templates), so this is acceptable for V1. If profiling later shows it matters, caching can be added inside the engine module (e.g., module-level LRU cache keyed on the source string) without changing the public API. Returning `None` from the validators keeps that future open.

## 9. Save-Time Validation

When a RunConfig with `input_transform: JinjaInputTransform` is saved:

- `JinjaInputTransform.template`'s `@field_validator` calls `compile_template_or_raise(template)`.
- Invalid Jinja2 syntax → Pydantic `ValidationError` → save rejected.

This catches typos, unclosed blocks, bad filter names, and other syntactic errors before any runtime invocation.

**Not validated at save time:**
- Whether the template's referenced variables exist on the task's input schema. (Cannot be checked without the task input present, and only the task's `input_json_schema` is statically known — even that might not match a future plaintext-task pairing if the schema is removed.)
- Whether the task associated with this RunConfig has structured input or not. (No restriction — see §5.)

## 10. Runtime Execution

At task invocation time, in both the synchronous and streaming adapter paths (`_run_returning_run_output` and `_prepare_stream`):

1. Input schema validation (existing behavior) — validates task input against `input_schema` if the task has one.
2. **New:** If `run_config.input_transform is not None`:
   - Construct the rendering namespace per §5.
   - Call `render_input_transform(transform, task_input)` → string.
   - Substitute the rendered string as the model-facing first user message for the rest of the pipeline.
3. Provider-specific formatter (existing behavior) — applies on the now-string input.
4. Inference (existing behavior).

If `input_transform is None`, step 2 is skipped entirely — the existing identity path is preserved.

**`TaskRun.input` stores the raw, un-transformed input. Always.** This is a deliberate choice, not an oversight:

- The rendered string is **derivative** — given the raw input + the transform, we can recompute it anytime. The raw input is the only canonical record of what the user/caller actually sent.
- Transforms are **not reversible**. If we stored only the rendered string, we could never reconstruct the original input.
- The rendered string is a **string**. For object-schema and array-schema tasks it almost certainly does not validate against the task's `input_json_schema`. Persisting it as `TaskRun.input` would corrupt the schema invariant on the task run.

The rendered string flows through the formatter and lands in `TaskRun.trace[0]` (first user message) via the existing trace mechanism. No new `TaskRun` field is required to recover "what the model actually saw."

## 11. Error Handling

All transform errors are pre-inference. Inference is not called if any of the following fail:

| Condition | When | Surfaced as |
|---|---|---|
| Template syntax error | Save time | Pydantic `ValidationError` (save rejected) |
| Template syntax error | Runtime (shouldn't happen — save-time blocks it) | Re-raised as runtime error |
| `UndefinedError` (missing variable) | Runtime | Re-raised; inference not attempted |
| Render exception (filter raised, etc.) | Runtime | Re-raised; inference not attempted |
| Sandbox `SecurityError` | Runtime | Re-raised; inference not attempted |

**Philosophy: fail loud, fail fast, fail attributable.** Consumers that need softer semantics (eval v2's skip-with-reason) wrap the API with their own pre-checks (e.g., calling `extract` with `required_var` expressions before render). The general-task path keeps the hard-fail semantics.

## 12. Persistence

- No new `TaskRun` field.
- No new `TaskRunConfig` field beyond `input_transform`.
- Raw task input remains in `TaskRun.input` (already persisted).
- Rendered model-facing string is captured in `TaskRun.trace[0]` (existing trace mechanism).
- Existing on-disk RunConfigs without `input_transform` load cleanly (default `None`).

## 13. Security

Threat model: templates are user-authored content. Sources range from local user (low risk) to shared/community datasets (higher risk).

**Templates are Jinja2 syntax, NOT Python code.** What this means concretely:

- No arbitrary Python execution. There is no `{% python %}` block; there is no `eval()`; template syntax cannot define or call Python functions other than the filters / tests that Jinja2 itself exposes.
- No file I/O. No `open(...)`, no `read()`, no `Path(...)`. Templates render from inline strings; no `FileSystemLoader` or other I/O loader is configured.
- No network I/O. No `requests`, no `urllib`, no socket access.
- No shell access. No `subprocess`, no `os.system`, no `popen`.
- No `import`. Templates cannot import Python modules.
- No access to dunder attributes (`__class__`, `__bases__`, `__subclasses__`, `__globals__`, etc.). Jinja2's `SandboxedEnvironment` blocks the known SSTI exploit chains that traverse these.
- No mutation of host objects passed in. Filters are pure-by-Jinja2-convention and we do not register any custom filters with side effects in V1.

What templates **can** do:
- Jinja2 syntax — `{{ ... }}` substitution, `{% if %}` / `{% for %}` blocks, `{% set %}`, etc.
- Built-in Jinja2 filters and tests (`| default`, `| length`, `| join`, `| upper`, `| tojson`, `is defined`, `is none`, etc.).
- Attribute access and indexing on the data passed in (`{{ input.field }}`, `{{ input[0] }}`).
- Arithmetic and string concatenation on the values in scope.

Save-time validation rejects templates that fail to compile. Runtime errors (missing var, sandbox violation, filter exception) re-raise pre-inference (§11).

**Documented out of scope:** No CPU/memory bounds on render — a pathological template (e.g., a `{% for %}` over a huge generator or a deeply recursive `{% include %}`-equivalent) can hang the render call. Acceptable risk for V1; revisit if it becomes a real problem.

## 14. Backward Compatibility

- `input_transform: InputTransform | None = None` — default `None`.
- All existing on-disk RunConfigs (no `input_transform` field) load with `input_transform=None`. No migration.
- Adapter pipeline with `input_transform is None` skips the new render step entirely → behavior unchanged.
- V1 eval configs are unaffected (the eval adapter constructs its own RunConfig and does not set `input_transform`).
- No V1 behavior changes for any task, RunConfig, or eval that doesn't opt into the new field.

## 15. Dependency

- New `jinja2` dependency added to `libs/core/pyproject.toml`.

## 16. Tests

Required validation at implementation time:

### Unit tests (engine)

- `compile_template_or_raise` raises `ValueError` with line info on syntax error; returns silently on valid templates.
- `compile_expression_or_raise` same, for expressions.
- `render_input_transform` exposes dict input via `{{ input.field }}` (attribute access on the dict).
- `render_input_transform` exposes list input via `{{ input[0] }}` / `{{ input | length }}`.
- `render_input_transform` exposes string input via `{{ input }}`.
- `render_input_transform` parses plaintext that is valid JSON and exposes the parsed value via `{{ input }}` (including the dict / list / scalar cases from §5).
- `render_input_transform` falls back to raw string when plaintext doesn't parse as JSON.
- `render_input_transform` raises `UndefinedError` on a template referencing a missing attribute (e.g., `{{ input.missing }}` on `StrictUndefined`).
- `render_input_transform` raises on sandbox violation (e.g., `{{ input.__class__.__bases__ }}` and similar dunder-walk attempts).
- `extract` returns Python objects (string, list, dict, int) per expression.
- `extract` returns `Undefined` for missing keys (not `None`, not a raise).
- `extract` returns `None` for explicit null values.
- `extract` materializes generators to lists (`{{ data | map(attribute='x') | list }}`).
- `trim_blocks` / `lstrip_blocks` produce the expected whitespace behavior in a test template.

### Data model tests

- `JinjaInputTransform` field validator rejects malformed templates with `ValueError`.
- `JinjaInputTransform` round-trips through JSON serialization (save → load → equal).
- `KilnAgentRunConfigProperties.input_transform` defaults to `None`.
- Discriminated union dispatches `{"type": "jinja", "template": "..."}` to `JinjaInputTransform`.
- A `KilnAgentRunConfigProperties` saved without `input_transform` loads with `input_transform=None` (backcompat).

### Adapter integration tests

- RunConfig with `input_transform: JinjaInputTransform(...)` on an object-schema task: rendered string lands in the first user message of `TaskRun.trace`; raw dict input preserved unchanged on `TaskRun.input`.
- RunConfig with `input_transform: JinjaInputTransform(...)` on a plaintext task with JSON-shaped input: parsing happens, rendered string is correct.
- RunConfig with `input_transform: JinjaInputTransform(...)` on a plaintext task with non-JSON input: `{{ input }}` evaluates to the raw string.
- RunConfig with `input_transform=None` (or absent): adapter behavior is byte-identical to the pre-feature path (golden output check).
- Streaming path (`_prepare_stream`) applies the transform the same way as the sync path.
- A template referencing a missing key surfaces `UndefinedError` before inference is called (mock the inference layer; assert it's never invoked).

## 17. Opens (resolved in architecture)

These are deferred to the architecture doc, not to the coding agent:

- Exact insertion point line numbers in `base_adapter.py` for both sync and stream paths.
- Whether to expose the plaintext-JSON-parse + namespace-construction step as a public helper (so eval v2 can reuse the same input-shape handling) or keep it private inside `render_input_transform`.
- Whether `extract`'s `data` parameter must be a dict, or can also accept lists/scalars for symmetry with `render_input_transform`.
- Whether `InputTransform` types live in `datamodel/input_transform.py` or alongside the engine in `utils/jinja_engine.py`.
- Whether to add a module-level compile cache (LRU) in V1 or defer until profiling shows a need. See §8 — public API stays the same either way.
