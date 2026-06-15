---
status: complete
---

# Architecture: Input Transform (project: templates)

This is a small architecture for a tightly-scoped infrastructure feature. Two new files, two helper methods, one new dependency. Single architecture doc, no per-component files needed.

## 1. Module Layout

Two new modules in `libs/core/kiln_ai`:

| Path | Responsibility |
|---|---|
| `libs/core/kiln_ai/datamodel/input_transform.py` | Pydantic types: `JinjaInputTransform`, `InputTransform` discriminated union, `_get_input_transform_type` discriminator. |
| `libs/core/kiln_ai/utils/jinja_engine.py` | Jinja2 `SandboxedEnvironment` instances and the four public engine functions. |

Test files alongside source per project convention:

- `libs/core/kiln_ai/datamodel/test_input_transform.py`
- `libs/core/kiln_ai/utils/test_jinja_engine.py`

Extensions to existing test files:

- `libs/core/kiln_ai/datamodel/test_run_config.py` — add coverage of the new `input_transform` field on `KilnAgentRunConfigProperties` (defaults, round-trip, discriminator dispatch, backcompat).
- `libs/core/kiln_ai/adapters/model_adapters/test_base_adapter.py` (or the existing adapter integration test file the implementer locates) — add adapter integration coverage for sync + streaming paths.

**Why split between `datamodel/` and `utils/`:** matches existing precedent. `prompt_id.py` / `tool_id.py` live in `datamodel/` because they are field types used by datamodel classes. The Jinja2 engine is logic with no datamodel role — it lives in `utils/` next to `formatting.py`, `config.py`, `open_ai_types.py`, etc.

## 2. Data Model

### 2.1 `libs/core/kiln_ai/datamodel/input_transform.py`

```python
from typing import Annotated, Any, Literal, Union
from pydantic import BaseModel, Discriminator, Field, Tag, field_validator


class JinjaInputTransform(BaseModel):
    """
    Render the task input via a Jinja2 template, producing the first user
    message sent to the model. See specs/projects/templates/functional_spec.md
    for the full contract.
    """

    type: Literal["jinja"] = "jinja"
    template: str = Field(
        description="Jinja2 template source. Validated at save time.",
    )

    @field_validator("template")
    @classmethod
    def validate_template_compiles(cls, v: str) -> str:
        # Lazy import to break the datamodel <-> utils import cycle.
        from kiln_ai.utils.jinja_engine import compile_template_or_raise

        compile_template_or_raise(v)
        return v


def _get_input_transform_type(data: Any) -> str:
    if isinstance(data, dict):
        return data.get("type", "jinja")
    return getattr(data, "type", "jinja")


InputTransform = Annotated[
    Union[
        Annotated[JinjaInputTransform, Tag("jinja")],
    ],
    Discriminator(_get_input_transform_type),
]
```

**Notes:**
- Lazy import inside `validate_template_compiles` breaks the circular import (`jinja_engine` would otherwise need `InputTransform` for typing; `input_transform` needs `compile_template_or_raise`).
- Discriminator default `"jinja"` is defensive — the union is only entered when `input_transform is not None`, but mirroring the `_get_run_config_type` pattern keeps the codebase consistent.
- The Union has one member in V1. Adding a second variant (e.g., a non-Jinja transform later) is one line of code plus a new `BaseModel` class.

### 2.2 Field placement on `KilnAgentRunConfigProperties`

`libs/core/kiln_ai/datamodel/run_config.py` — add `input_transform` as a peer of `tools_config` (after line 80):

```python
class KilnAgentRunConfigProperties(BaseModel):
    type: Literal["kiln_agent"] = "kiln_agent"
    # ... existing fields ...
    tools_config: ToolsRunConfig | None = Field(
        default=None,
        description="...",
    )
    input_transform: InputTransform | None = Field(
        default=None,
        description=(
            "Optional transform applied to the task input at run time, producing "
            "the first user message sent to the model. Default None preserves "
            "the identity path."
        ),
    )
```

Import at the top of `run_config.py`:

```python
from kiln_ai.datamodel.input_transform import InputTransform
```

No other changes to `run_config.py` — discriminator, validators, narrowing helpers are unaffected.

### 2.3 Backward compatibility at the field level

Existing on-disk RunConfigs without `input_transform` parse with `input_transform=None`. This is automatic via Pydantic's default. No migration code, no `upgrade_old_entries`-style hook needed.

The Pydantic `model_validator(mode="before") upgrade_old_entries` on `TaskRunConfig` (`task.py:99`) is unaffected — it backfills `structured_output_mode` and does not touch `input_transform`.

## 3. Engine Module

### 3.1 `libs/core/kiln_ai/utils/jinja_engine.py`

```python
"""
Jinja2 template engine for Kiln input transforms.

Two SandboxedEnvironment instances:
  - Template env: StrictUndefined, used by `compile_template_or_raise` and `render_input_transform`.
  - Expression env: default Undefined, used by `compile_expression_or_raise` and `extract`.

Both envs share trim_blocks=True and lstrip_blocks=True for prompt-friendly output.

Public API:
  - compile_template_or_raise(template) -> None
  - compile_expression_or_raise(expression) -> None
  - render_input_transform(transform, task_input) -> str
  - extract(expression, data) -> Any
"""

from __future__ import annotations

import json
import types
from typing import TYPE_CHECKING, Any

from jinja2 import StrictUndefined, TemplateSyntaxError, Undefined
from jinja2.sandbox import SandboxedEnvironment

if TYPE_CHECKING:
    from kiln_ai.datamodel.input_transform import InputTransform


_template_env = SandboxedEnvironment(
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)

_expression_env = SandboxedEnvironment(
    undefined=Undefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def compile_template_or_raise(template: str) -> None:
    """Validate that the template compiles. Raises ValueError on syntax error."""
    try:
        _template_env.from_string(template)
    except TemplateSyntaxError as e:
        raise ValueError(
            f"Invalid Jinja2 template: {e.message} (line {e.lineno})"
        ) from e


def compile_expression_or_raise(expression: str) -> None:
    """Validate that a Jinja2 expression compiles. Raises ValueError on syntax error."""
    try:
        _expression_env.compile_expression(expression)
    except TemplateSyntaxError as e:
        raise ValueError(
            f"Invalid Jinja2 expression: {e.message} (line {e.lineno})"
        ) from e


def render_input_transform(
    transform: "InputTransform",
    task_input: Any,
) -> str:
    """Render the transform against the task input, returning the first-user-message string.

    See specs/projects/templates/functional_spec.md §5 for the input-handling rules.
    """
    # Lazy import to break circular dependency at type level.
    from kiln_ai.datamodel.input_transform import JinjaInputTransform

    if isinstance(transform, JinjaInputTransform):
        namespace = _build_namespace(task_input)
        return _template_env.from_string(transform.template).render(**namespace)

    raise ValueError(f"Unknown InputTransform variant: {type(transform).__name__}")


def extract(expression: str, data: dict) -> Any:
    """Evaluate a Jinja2 expression against a dict; returns the Python value.

    - Missing keys return Undefined (not None, not a raise).
    - Explicit null values return None.
    - Generators are auto-materialized to lists.
    """
    compiled = _expression_env.compile_expression(expression)
    result = compiled(**data)
    if isinstance(result, types.GeneratorType):
        result = list(result)
    return result


def _build_namespace(task_input: Any) -> dict:
    """
    Build the rendering namespace per functional_spec §5:
      - The template always sees a single variable `input`.
      - For plaintext (str) inputs, try json.loads(); fall back to the raw string.
      - For dict/list inputs, expose them under `input` as-is.
    """
    if isinstance(task_input, str):
        try:
            parsed = json.loads(task_input)
        except (ValueError, TypeError):
            parsed = task_input
        return {"input": parsed}
    return {"input": task_input}
```

### 3.2 Why two `SandboxedEnvironment` instances

The `undefined=` setting is environment-scoped, so distinguishing "template render must hard-fail on missing var" (`StrictUndefined`) from "expression evaluation should return `Undefined`" (default `Undefined`) requires two instances. Both use `SandboxedEnvironment` and the same `trim_blocks` / `lstrip_blocks` settings — they share the same security boundary and syntax surface.

### 3.3 Why `_build_namespace` is private

The plaintext-parse-and-namespace step is not exposed as a public helper. Reasons:

- Eval v2 will construct its own synthetic dict (4-field assembly: `final_message`, `trace`, `reference_data`, `task_input`) and pass it directly to `render_input_transform`. It does not need the plaintext auto-parse logic.
- No other V1 consumer exists.
- Exposing it now would be speculative API surface. If a future consumer needs it, we can promote it then.

### 3.4 Compile cost

`render_input_transform` and `extract` re-compile their source on every call. Jinja2 compilation is fast (microseconds for prompt-sized templates), so this is acceptable for V1. If profiling later shows it matters, a module-level LRU cache keyed on the source string can be added inside the engine module without changing the public API.

## 4. Adapter Integration

### 4.1 New helper on `BaseAdapter`

Add a single helper method to `BaseAdapter` (`libs/core/kiln_ai/adapters/model_adapters/base_adapter.py`):

```python
def _apply_input_transform(self, input: InputType) -> InputType:
    """
    If the run config has an input_transform, render it and return the
    resulting string. Otherwise return input unchanged.

    MCP run configs (no input_transform field) are a no-op.
    """
    if not isinstance(self.run_config, KilnAgentRunConfigProperties):
        return input
    transform = self.run_config.input_transform
    if transform is None:
        return input
    return render_input_transform(transform, input)
```

Imports added at top of the file:

```python
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties  # already imported
from kiln_ai.utils.jinja_engine import render_input_transform
```

**Why a helper method, not inline:** the same logic is needed in two places (sync + stream). Centralizing it keeps both paths in lockstep. Future transform variants only need to update one site.

### 4.2 Call sites

**Sync path** — `_run_returning_run_output` (`base_adapter.py:215`), insert between schema validation (line 234) and the existing formatter block (line 239):

```python
        if self.input_schema is not None:
            validate_schema_with_value_error(...)

        # NEW: apply the input transform if one is configured.
        input = self._apply_input_transform(input)

        # Format model input for model call ... (existing code)
        formatted_input = input
        formatter_id = self.model_provider().formatter
        ...
```

**Streaming path** — `_prepare_stream` (`base_adapter.py:414`), insert between schema validation (line 428) and the formatter block (line 430):

```python
        if self.input_schema is not None:
            validate_schema_with_value_error(...)

        # NEW: apply the input transform if one is configured.
        input = self._apply_input_transform(input)

        formatted_input = input
        formatter_id = self.model_provider().formatter
        ...
```

### 4.3 What gets persisted as `TaskRun.input`

The transform mutates the **local** `input` variable in the adapter methods (from `dict` / `list` / `str` to the rendered `str`), but `generate_run` is called from `_run_returning_run_output` line 307 with the local `input` variable too:

```python
            run = self.generate_run(
                input,
                input_source,
                ...
            )
```

So we have a problem: if we overwrite `input` with the rendered string, `generate_run` will save the transformed string as `TaskRun.input`, violating functional_spec §10/§12.

**Fix: keep a separate name for the transformed value.** Replace the helper's call style:

```python
        if self.input_schema is not None:
            validate_schema_with_value_error(...)

        # NEW: derive the model-facing input. Original `input` is preserved
        # for TaskRun.input persistence.
        model_input = self._apply_input_transform(input)

        formatted_input = model_input
        formatter_id = self.model_provider().formatter
        if formatter_id is not None:
            formatter = request_formatter_from_id(formatted_input)
            formatted_input = formatter.format_input(model_input)
```

And `generate_run(input, ...)` continues to receive the **original** `input`, not `model_input`. This matches the existing pattern in the file ("we save the original input in the task without formatting" — comment at line 236).

For `_prepare_stream`, same change: introduce `model_input = self._apply_input_transform(input)` and pass `model_input` (via the formatter) into `_create_run_stream(...)`.

### 4.4 No change required to MCP path

`McpRunConfigProperties` has no `input_transform` field. The helper's `isinstance(self.run_config, KilnAgentRunConfigProperties)` guard returns the input unchanged for MCP. No further changes to the MCP execution path.

### 4.5 Order of operations

The transform runs:

1. **After** input schema validation (so transform receives validated structured input when applicable).
2. **Before** provider-specific formatter (so the formatter sees a string, exactly as it would for a non-transform plaintext task today).
3. **Before** trace assembly / inference.

This ordering ensures:

- Schema validation still catches malformed structured input (transform doesn't bypass it).
- The formatter receives a string in all transform cases, matching the existing plaintext-task code path.
- The rendered string lands in `TaskRun.trace[0]` (first user message) via the existing trace mechanism.

## 5. Error Handling

All transform errors are pre-inference and bubble up as plain Python exceptions. No new exception class is introduced.

| Failure | Where | Surfaced as |
|---|---|---|
| Template syntax error at save | Pydantic `field_validator` | `ValidationError` (save rejected) |
| `UndefinedError` (missing variable) | Runtime, `render_input_transform` | `UndefinedError` re-raised |
| Sandbox `SecurityError` | Runtime, `render_input_transform` | `SecurityError` re-raised |
| Filter exception | Runtime, `render_input_transform` | exception re-raised |
| Template syntax error at runtime (defense-in-depth; shouldn't happen) | Runtime, `render_input_transform` | `TemplateSyntaxError` re-raised |

The adapter does not catch these — they propagate out of `_run_returning_run_output` / `_prepare_stream` and are caught by the existing `except Exception` block at line 331 of `base_adapter.py`, which wraps them in `KilnRunError` for the caller. This matches how schema-validation errors and formatter errors are surfaced today.

**Important:** because the transform runs before the `try` block at line 250 (the wrapped region), `KilnRunError` wrapping does NOT apply to transform errors. They surface as plain exceptions to the caller. This is the right behavior — transform errors are configuration / authoring errors, not run-execution errors, and shouldn't be conflated with model failures. (Same treatment as the existing schema-validation errors above.)

## 6. Dependency

Add `jinja2` to `libs/core/pyproject.toml`. Use the latest 3.x release (currently `jinja2 >= 3.1.0`).

Run `uv lock` after the dependency change. Verify `uv.lock` updates cleanly.

## 7. Tests

### 7.1 `utils/test_jinja_engine.py`

Engine-level unit tests (see functional_spec §16 for the full list — copying here for the implementer):

- `compile_template_or_raise` raises `ValueError` with line info on syntax error; returns silently on valid templates.
- `compile_expression_or_raise` same, for expressions.
- `render_input_transform(JinjaInputTransform("{{ input.foo }}"), {"foo": 1})` → `"1"`.
- `render_input_transform(JinjaInputTransform("{{ input[0] }}"), [1, 2, 3])` → `"1"`.
- `render_input_transform(JinjaInputTransform("{{ input }}"), "hello")` → `"hello"`.
- `render_input_transform(JinjaInputTransform("{{ input.foo }}"), '{"foo": 1}')` (plaintext JSON) → `"1"`.
- `render_input_transform(JinjaInputTransform("{{ input }}"), "not json")` (plaintext fallback) → `"not json"`.
- `render_input_transform(JinjaInputTransform("{{ input.missing }}"), {"foo": 1})` → raises `UndefinedError`.
- `render_input_transform(JinjaInputTransform("{{ input.__class__.__bases__ }}"), {})` → raises `SecurityError`.
- `extract("foo", {"foo": 42})` → `42`.
- `extract("foo", {})` → `Undefined` (not None, not raise).
- `extract("foo", {"foo": None})` → `None`.
- `extract("data | map(attribute='x') | list", {"data": [{"x": 1}, {"x": 2}]})` → `[1, 2]` (generator materialized).
- `trim_blocks=True` / `lstrip_blocks=True` behavior in a representative template.

### 7.2 `datamodel/test_input_transform.py`

- `JinjaInputTransform(template="{{ input }}")` constructs successfully.
- `JinjaInputTransform(template="{% if ")` (malformed) raises `ValidationError` from Pydantic.
- `JinjaInputTransform` round-trips through `.model_dump()` and re-construction.
- Discriminated union dispatches `{"type": "jinja", "template": "..."}` to `JinjaInputTransform`.
- Unknown `type` in the discriminator raises a clean Pydantic error.

### 7.3 `datamodel/test_run_config.py` (extensions)

- `KilnAgentRunConfigProperties(...)` without `input_transform` has `input_transform = None`.
- `KilnAgentRunConfigProperties(input_transform=JinjaInputTransform(...))` accepts a valid transform.
- `KilnAgentRunConfigProperties(input_transform={"type": "jinja", "template": "..."})` accepts a dict (discriminator dispatches).
- Old on-disk RunConfig JSON (no `input_transform` key) loads with `input_transform = None` (backcompat regression test — fixture or hand-written dict).
- `McpRunConfigProperties` does not have an `input_transform` field (negative test).

### 7.4 Adapter integration tests

- Object-schema task + RunConfig with `JinjaInputTransform`: rendered string lands in the first user message of `TaskRun.trace`; `TaskRun.input` is the raw dict.
- Plaintext task + RunConfig with `JinjaInputTransform`: JSON-shaped plaintext is parsed; non-JSON plaintext is passed through as a string.
- Array-schema task + RunConfig with `JinjaInputTransform`: list is exposed via `{{ input[0] }}`.
- RunConfig with `input_transform=None`: sync adapter behavior is byte-identical to pre-feature (golden output check or recorded trace diff).
- Streaming path (`_prepare_stream`) applies the transform the same way as the sync path. (Use the existing streaming integration test pattern or a focused unit test on `_prepare_stream`.)
- A template referencing a missing key surfaces `UndefinedError` before inference is called — mock the underlying model provider call and assert it's never invoked.
- MCP run config (no `input_transform`): pipeline behavior unchanged.

### 7.5 Coverage targets

No quantitative targets. The bullet list above is the authoritative checklist; the coding agent does not add or omit tests beyond it without surfacing the decision in the phase plan.

## 8. Out of Scope / Future Hooks

- No CPU/memory bounds on render (acceptable risk for V1; see functional_spec §13).
- No compile-result cache in V1 (engine API designed so it can be added later without breaking callers).
- No custom Jinja2 filters in V1 (built-in filters only).
- No eval-side code (consumed by future eval v2 project).
- No UI for authoring transforms (future project).
- No public exposure of `_build_namespace` (future, if needed).

## 9. Implementation Order (informational; the implementation_plan.md drives phasing)

A natural order for the coding agent:

1. Add `jinja2` dependency, `uv lock`.
2. Create `utils/jinja_engine.py` with the four public functions + the two `SandboxedEnvironment` instances. Write `test_jinja_engine.py` to validate the engine in isolation (no datamodel imports).
3. Create `datamodel/input_transform.py` with `JinjaInputTransform`, `InputTransform`, discriminator. Write `test_input_transform.py`.
4. Add the field to `KilnAgentRunConfigProperties`; extend `test_run_config.py` for the new field.
5. Add `_apply_input_transform` to `BaseAdapter` and wire both call sites; add adapter integration tests.

The implementation plan may bundle some of these into a single phase. See `implementation_plan.md` for the actual phasing.
