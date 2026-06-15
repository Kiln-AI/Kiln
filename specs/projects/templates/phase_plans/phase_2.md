---
status: complete
---

# Phase 2: Adapter Integration

## Overview

Wire the input transform into the adapter execution pipeline. Both the sync path (`_run_returning_run_output`) and streaming path (`_prepare_stream`) apply the transform after input schema validation but before the formatter. The original `input` is preserved for `TaskRun.input` persistence; only the model-facing message is transformed.

## Steps

1. Add import of `render_input_transform` to `base_adapter.py`.

2. Add `_apply_input_transform` helper method to `BaseAdapter`:
   ```python
   def _apply_input_transform(self, input: InputType) -> InputType:
       if not isinstance(self.run_config, KilnAgentRunConfigProperties):
           return input
       transform = self.run_config.input_transform
       if transform is None:
           return input
       return render_input_transform(transform, input)
   ```

3. Wire sync path in `_run_returning_run_output`: after input schema validation, introduce `model_input = self._apply_input_transform(input)` and pass `model_input` to the formatter. `input` (original) continues to flow to `generate_run`.

4. Wire streaming path in `_prepare_stream`: same pattern — `model_input = self._apply_input_transform(input)` passed to formatter and `_create_run_stream`.

5. Write adapter integration tests in `test_base_adapter.py` covering all cases from architecture section 7.4.

## Tests

- `test_input_transform_object_schema`: object-schema task with JinjaInputTransform — rendered string passed to _run, raw dict preserved in TaskRun.input
- `test_input_transform_plaintext_json`: plaintext JSON input parsed and templated correctly
- `test_input_transform_plaintext_non_json`: non-JSON plaintext exposed via {{ input }}
- `test_input_transform_array_schema`: list input exposed via {{ input[0] }}
- `test_input_transform_none_identity`: transform=None path is identical to no-transform behavior
- `test_input_transform_streaming_parity`: _prepare_stream applies transform same as sync
- `test_input_transform_undefined_error_pre_inference`: UndefinedError raised before inference (mock provider never called)
- `test_input_transform_mcp_unchanged`: MCP run config ignores input_transform logic
