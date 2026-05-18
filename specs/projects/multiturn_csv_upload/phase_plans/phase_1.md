---
status: complete
---

# Phase 1: Backend importer + endpoint

## Overview

Add multiturn CSV parsing, validation, and TaskRun chain construction to `dataset_import.py`. Dispatch from `import_csv` on `task.turn_mode`. Introduce `ImportResult` dataclass, propagate it through `DatasetFileImporter.create_runs_from_file()`, and update `BulkUploadResponse` with `imported_conversation_count`. Cover the new code with unit and endpoint tests per the architecture doc.

No frontend changes in this phase.

## Steps

1. `libs/core/kiln_ai/utils/dataset_import.py`:
   - Add `ImportResult` dataclass with `imported_run_count: int` and `imported_conversation_count: int | None`.
   - Update `Importer` Protocol to return `ImportResult`.
   - Rename current `import_csv` body to `_import_csv_single_turn`. Have it return `ImportResult(imported_run_count=len(rows), imported_conversation_count=None)`.
   - Extend the single-turn header check so that if `trace` is present in headers and `input`/`output` are missing, raise a tailored "Task is single-turn; expected columns: input, output…" error.
   - Add `CSVMultiturnRowSchema` (pydantic) with required `trace: str` and optional `tags: list[str]`.
   - Add module-level `ALLOWED_ROLES = {"user", "assistant"}`.
   - Add `ValidatedMessage` dataclass and `_validate_trace(trace_str: str, row_number: int) -> list[ValidatedMessage]` matching architecture §3.4.
   - Add `_to_openai_message(m: ValidatedMessage) -> ChatCompletionMessageParam` helper.
   - Add `_build_chain(task, messages, file_name, session_id, csv_tags) -> list[TaskRun]` matching architecture §3.5.
   - Add `_import_csv_multiturn(task, config) -> ImportResult` matching architecture §3.6. Splits apply to leaves only.
   - Add new module-level `import_csv(task, config) -> ImportResult` that dispatches on `task.turn_mode`.
   - Update `DatasetFileImporter.create_runs_from_file()` return annotation to `ImportResult`.

2. `libs/server/kiln_server/run_api.py`:
   - Add `imported_conversation_count: int | None = None` field to `BulkUploadResponse`.
   - In the `bulk_upload` endpoint, capture the `ImportResult` and use both `imported_run_count` and `imported_conversation_count` in the response.

3. `libs/core/kiln_ai/utils/test_dataset_import.py`:
   - Add a `multiturn_task` fixture (`Task(turn_mode=TurnMode.multiturn, …)`).
   - Add helper `dicts_to_file_as_csv` is reusable; build multiturn rows where `trace` is a JSON string with `json.dumps`.
   - Add all multiturn happy-path and error-path tests listed under "Tests" below.

4. `libs/server/kiln_server/test_run_api.py`:
   - Add endpoint tests `test_bulk_upload_multiturn_success`, `test_bulk_upload_multiturn_invalid_trace_returns_422`, `test_bulk_upload_single_turn_response_has_null_conversation_count`.
   - Use the existing `multiturn_task_run_setup` fixture (or build inline) and a temp CSV file. `client.post(..., files={"file": ("name.csv", csv_bytes, "text/csv")})`.

## Tests

Unit (`libs/core/kiln_ai/utils/test_dataset_import.py`):

- `test_import_csv_multiturn_basic` — two-turn trace → 2 TaskRuns; root has `parent_task_run_id is None`; leaf's `parent_task_run_id == root.id`; leaf's `trace` has full 4 messages; root's `trace` has 2.
- `test_import_csv_multiturn_single_turn_conversation` — one user/assistant pair → 1 TaskRun, no parent.
- `test_import_csv_multiturn_multiple_conversations` — two rows → two independent chains (no cross-row parent links); `ImportResult.imported_conversation_count == 2`.
- `test_import_csv_multiturn_reasoning_content` — assistant message with `reasoning_content` → `intermediate_outputs["reasoning"]` populated.
- `test_import_csv_multiturn_no_reasoning_content` — no `reasoning_content` → `intermediate_outputs is None`.
- `test_import_csv_multiturn_tags_on_all_runs` — CSV `tags` applied to every run in the chain (root + leaf).
- `test_import_csv_multiturn_splits_apply_to_leaves_only` — leaves get split tag; intermediate runs do not.
- `test_import_csv_multiturn_returns_imported_result` — `ImportResult` shape: `imported_run_count` == sum of chain lengths, `imported_conversation_count` == row count.
- `test_import_csv_multiturn_input_output_derived` — TaskRun.input == user msg; TaskRun.output.output == assistant msg.
- `test_import_csv_multiturn_data_source_is_file_import` — input_source and output.source both `file_import` with `file_name` properly set.
- `test_import_csv_multiturn_missing_trace_column` — header missing `trace` → multiturn-specific error.
- `test_import_csv_multiturn_invalid_json_trace` — invalid JSON → "trace is not valid JSON.", row 2.
- `test_import_csv_multiturn_trace_not_array` — JSON object → "must be a JSON array".
- `test_import_csv_multiturn_trace_too_short` — empty `[]` and single-message arrays → "at least one user message followed by one assistant message".
- `test_import_csv_multiturn_unknown_role` — `function` → "unsupported role 'function'".
- `test_import_csv_multiturn_system_message_rejected` — system message → §4 system-prompt message.
- `test_import_csv_multiturn_developer_message_rejected` — developer message → same family.
- `test_import_csv_multiturn_tool_role_rejected` — tool role → tool-not-supported.
- `test_import_csv_multiturn_assistant_with_tool_calls_rejected` — assistant with `tool_calls` → tool-not-supported.
- `test_import_csv_multiturn_empty_content` — empty string content → must be non-empty string.
- `test_import_csv_multiturn_non_string_content` — int content → must be non-empty string.
- `test_import_csv_multiturn_starts_with_assistant` — leading assistant → "expected role 'user', got 'assistant'".
- `test_import_csv_multiturn_does_not_alternate` — user, user → "expected role 'assistant', got 'user'".
- `test_import_csv_multiturn_ends_with_user` — trace ends with user → "trace must end with an assistant message".
- `test_import_csv_multiturn_invalid_tag` — tag with whitespace → existing validation message.
- `test_import_csv_multiturn_preflight_no_partial_save` — bad row → no runs saved on disk.
- `test_import_csv_single_turn_task_rejects_trace_csv` — single-turn task + trace-only CSV → "Task is single-turn; expected columns…".

Endpoint (`libs/server/kiln_server/test_run_api.py`):

- `test_bulk_upload_multiturn_success` — multiturn CSV upload → 200, `imported_count == M*N`, `imported_conversation_count == M`.
- `test_bulk_upload_multiturn_invalid_trace_returns_422` — bad JSON → 422 with row-tagged detail.
- `test_bulk_upload_single_turn_response_has_null_conversation_count` — existing single-turn upload returns null conversation count.
