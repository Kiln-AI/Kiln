---
status: complete
---

# Implementation Plan: Input Transform (project: templates)

Small project. Two phases — foundation (engine + datamodel) then adapter integration. Each phase is independently testable and reviewable in one sitting.

## Phases

- [x] **Phase 1: Engine + datamodel foundation**
  - Add `jinja2 >= 3.1.0` to `libs/core/pyproject.toml`; run `uv lock`.
  - Create `libs/core/kiln_ai/utils/jinja_engine.py` with `_template_env` / `_expression_env`, `compile_template_or_raise`, `compile_expression_or_raise`, `render_input_transform`, `extract`, and private `_build_namespace`.
  - Create `libs/core/kiln_ai/datamodel/input_transform.py` with `JinjaInputTransform` (template `field_validator`), `_get_input_transform_type`, and the `InputTransform` discriminated union.
  - Add `input_transform: InputTransform | None = None` to `KilnAgentRunConfigProperties` in `libs/core/kiln_ai/datamodel/run_config.py` (peer of `tools_config`).
  - Tests: `utils/test_jinja_engine.py`, `datamodel/test_input_transform.py`, extensions to `datamodel/test_run_config.py` per architecture §7.1–7.3.
  - Run `uv run ./checks.sh --agent-mode`.

- [ ] **Phase 2: Adapter integration**
  - Add `_apply_input_transform` helper to `BaseAdapter` in `libs/core/kiln_ai/adapters/model_adapters/base_adapter.py`.
  - Wire call sites in `_run_returning_run_output` (sync) and `_prepare_stream` (streaming), keeping the original `input` for `generate_run` and using a separate `model_input` for the formatter — per architecture §4.3.
  - Adapter integration tests per architecture §7.4: object-schema, plaintext (JSON + non-JSON), array-schema, identity (transform=None) byte-identical, streaming path parity, `UndefinedError` surfaces pre-inference (mock provider, assert never invoked), MCP run config unchanged.
  - Run `uv run ./checks.sh --agent-mode`.
