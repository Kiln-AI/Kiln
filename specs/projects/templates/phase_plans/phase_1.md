---
status: complete
---

# Phase 1: Engine + Datamodel Foundation

## Overview

Build the Jinja2 template engine and the data model types needed for input transforms. This phase delivers the engine module (`jinja_engine.py`), the data model types (`input_transform.py`), and the new `input_transform` field on `KilnAgentRunConfigProperties`. All three are independently testable without adapter changes.

## Steps

1. Add `jinja2 >= 3.1.0` to `libs/core/pyproject.toml` dependencies; run `uv lock`.

2. Create `libs/core/kiln_ai/utils/jinja_engine.py`:
   - Module-level `_template_env` (`SandboxedEnvironment`, `StrictUndefined`, `trim_blocks=True`, `lstrip_blocks=True`).
   - Module-level `_expression_env` (`SandboxedEnvironment`, default `Undefined`, same trim/lstrip).
   - `compile_template_or_raise(template: str) -> None` — wraps `_template_env.from_string()`, catches `TemplateSyntaxError`, re-raises as `ValueError` with line info.
   - `compile_expression_or_raise(expression: str) -> None` — wraps `_expression_env.compile_expression()`, same error handling.
   - `render_input_transform(transform: "InputTransform", task_input: Any) -> str` — dispatches on `JinjaInputTransform`, calls `_build_namespace` + `_template_env.from_string().render()`.
   - `extract(expression: str, data: dict) -> Any` — evaluates expression against data dict, auto-materializes generators.
   - `_build_namespace(task_input: Any) -> dict` — private; builds `{"input": ...}` with plaintext JSON auto-parse.

3. Create `libs/core/kiln_ai/datamodel/input_transform.py`:
   - `JinjaInputTransform(BaseModel)` with `type: Literal["jinja"]`, `template: str`, `@field_validator("template")` calling `compile_template_or_raise`.
   - `_get_input_transform_type(data: Any) -> str` discriminator function.
   - `InputTransform` discriminated union type alias.

4. Add `input_transform: InputTransform | None = Field(default=None, ...)` to `KilnAgentRunConfigProperties` in `run_config.py`, with the import of `InputTransform`.

5. Write `libs/core/kiln_ai/utils/test_jinja_engine.py` covering all engine unit tests from architecture section 7.1.

6. Write `libs/core/kiln_ai/datamodel/test_input_transform.py` covering data model tests from architecture section 7.2.

7. Extend `libs/core/kiln_ai/datamodel/test_run_config.py` with new tests for the `input_transform` field on `KilnAgentRunConfigProperties` per architecture section 7.3.

## Tests

- `test_compile_template_valid`: valid template compiles silently
- `test_compile_template_syntax_error`: syntax error raises ValueError with line info
- `test_compile_expression_valid`: valid expression compiles silently
- `test_compile_expression_syntax_error`: syntax error raises ValueError
- `test_render_dict_input`: dict input exposed via `{{ input.foo }}`
- `test_render_list_input`: list input exposed via `{{ input[0] }}` / `{{ input | length }}`
- `test_render_string_input`: string input exposed via `{{ input }}`
- `test_render_plaintext_json_dict`: JSON string auto-parsed to dict
- `test_render_plaintext_json_fallback`: non-JSON string falls back to raw string
- `test_render_undefined_error`: missing attribute raises UndefinedError
- `test_render_sandbox_violation`: dunder access raises SecurityError
- `test_extract_returns_value`: extracts Python value from dict
- `test_extract_missing_key_returns_undefined`: missing key returns Undefined (not None)
- `test_extract_explicit_none`: explicit None returns None
- `test_extract_materializes_generators`: generator result becomes list
- `test_trim_lstrip_blocks`: whitespace behavior of trim_blocks/lstrip_blocks
- `test_jinja_input_transform_valid`: valid template constructs OK
- `test_jinja_input_transform_invalid`: malformed template raises ValidationError
- `test_jinja_input_transform_roundtrip`: model_dump + re-construct equality
- `test_discriminated_union_dispatch`: dict with type "jinja" dispatches to JinjaInputTransform
- `test_run_config_input_transform_default_none`: field defaults to None
- `test_run_config_input_transform_accepts_valid`: accepts JinjaInputTransform
- `test_run_config_input_transform_dict_dispatch`: accepts dict with discriminator
- `test_run_config_backcompat_no_input_transform`: old JSON loads with input_transform=None
- `test_mcp_no_input_transform`: McpRunConfigProperties has no input_transform field
