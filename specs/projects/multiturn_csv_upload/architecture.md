---
status: complete
---

# Architecture: Multiturn CSV Upload

Implementation plan deep enough that no significant technical decisions remain. Single architecture doc — the feature touches one backend module, one endpoint, and one Svelte component, so per-component design files would be overkill.

## 1. Touched files

| File | Change | Notes |
|---|---|---|
| `libs/core/kiln_ai/utils/dataset_import.py` | Extend | Add multiturn parsing/validation/chain construction; dispatch by `task.turn_mode` inside `import_csv`. |
| `libs/server/kiln_server/run_api.py` | Light | Endpoint signature unchanged. `BulkUploadResponse` gains `imported_conversation_count: int \| None` (None for single-turn, count for multiturn). |
| `libs/server/kiln_server/run_api.py` (response model) | Light | `BulkUploadResponse` field addition + OpenAPI regen. |
| `libs/core/kiln_ai/utils/test_dataset_import.py` | Tests | New multiturn cases (see §6). Existing single-turn tests untouched. |
| `libs/server/kiln_server/test_run_api.py` | Tests | New endpoint cases for multiturn upload + mode-mismatch errors. |
| `app/web_ui/src/routes/(app)/dataset/[project_id]/[task_id]/upload_dataset_dialog.svelte` | Extend | Turn-mode-aware help block, title, sample download link. Reads `$current_task?.turn_mode`. |
| `app/web_ui/static/sample_multiturn.csv` | New file | Sample multiturn CSV downloadable from the dialog. |
| `app/web_ui/src/lib/api_schema.d.ts` | Regen | Run `generate_schema.sh` after backend change. |

## 2. Data model — nothing changes

The feature uses existing models verbatim:

- `TaskRun.trace: list[ChatCompletionMessageParam] | None` — populated with the cumulative trace.
- `TaskRun.parent_task_run_id: str | None` — links chain members.
- `TaskRun.input` / `TaskRun.output: TaskOutput` — per-turn user/assistant content.
- `TaskRun.intermediate_outputs["reasoning"]` — populated when assistant message has `reasoning_content`.
- `DataSource(type=DataSourceType.file_import, properties={"file_name": …})` — same as single-turn.

`Task.turn_mode` already exists (`TurnMode.single_turn` | `TurnMode.multiturn`). No datamodel additions.

## 3. Backend design — `dataset_import.py`

### 3.1 Module-level dispatch

```python
def import_csv(task: Task, config: ImportConfig) -> ImportResult:
    if task.turn_mode == TurnMode.multiturn:
        return _import_csv_multiturn(task, config)
    return _import_csv_single_turn(task, config)
```

`_import_csv_single_turn` is the current `import_csv` body, renamed. No behavior change for single-turn imports.

### 3.2 New return type

Replace the current `int` return with:

```python
@dataclass
class ImportResult:
    imported_run_count: int
    imported_conversation_count: int | None  # None for single-turn
```

Caller (endpoint) maps this to `BulkUploadResponse`.

Rationale: a single `int` was fine when 1 row = 1 run. For multiturn, the user thinks in conversations but the system creates N runs per conversation. Both numbers are useful.

### 3.3 Multiturn CSV row schema (header-level)

```python
class CSVMultiturnRowSchema(BaseModel):
    trace: str = Field(description="JSON-encoded list of OpenAI chat messages")
    tags: list[str] = Field(default_factory=list)
```

`trace` is a raw JSON string at the CSV layer; structural validation happens in `_validate_trace`.

### 3.4 Trace validation

```python
ALLOWED_ROLES = {"user", "assistant"}

@dataclass
class ValidatedMessage:
    role: str       # "user" | "assistant"
    content: str
    reasoning_content: str | None  # assistant only

def _validate_trace(trace_str: str, row_number: int) -> list[ValidatedMessage]:
    # 1. JSON parse
    try:
        trace = json.loads(trace_str)
    except json.JSONDecodeError:
        raise KilnInvalidImportFormat("trace is not valid JSON.", row_number)

    # 2. Must be a list, length >= 2
    if not isinstance(trace, list):
        raise KilnInvalidImportFormat("trace must be a JSON array of messages.", row_number)
    if len(trace) < 2:
        raise KilnInvalidImportFormat(
            "trace must contain at least one user message followed by one assistant message.",
            row_number,
        )

    # 3. Per-message validation + alternation
    out: list[ValidatedMessage] = []
    for k, msg in enumerate(trace, start=1):
        if not isinstance(msg, dict):
            raise KilnInvalidImportFormat(f"message {k}: must be a JSON object.", row_number)

        role = msg.get("role")
        if role in ("system", "developer"):
            raise KilnInvalidImportFormat(
                f"message {k}: trace contains a {role} message. Multiturn tasks define "
                "their system prompt on the task itself, not per-conversation. Remove "
                "system/developer messages from your CSV, or update the task's system "
                "prompt to match.",
                row_number,
            )
        if role == "tool" or "tool_calls" in msg:
            raise KilnInvalidImportFormat(
                f"message {k}: tool calls and tool messages are not supported in CSV import.",
                row_number,
            )
        if role not in ALLOWED_ROLES:
            raise KilnInvalidImportFormat(
                f"message {k}: unsupported role '{role}'. Allowed: user, assistant.",
                row_number,
            )

        content = msg.get("content")
        if not isinstance(content, str) or not content:
            raise KilnInvalidImportFormat(
                f"message {k}: 'content' must be a non-empty string.",
                row_number,
            )

        # Alternation: even positions (k=1,3,5…) must be user; odd positions assistant.
        expected = "user" if (k % 2 == 1) else "assistant"
        if role != expected:
            raise KilnInvalidImportFormat(
                f"message {k}: expected role '{expected}', got '{role}'.",
                row_number,
            )

        reasoning = None
        if role == "assistant":
            rc = msg.get("reasoning_content")
            if rc is not None:
                if not isinstance(rc, str):
                    raise KilnInvalidImportFormat(
                        f"message {k}: 'reasoning_content' must be a string.",
                        row_number,
                    )
                reasoning = rc

        out.append(ValidatedMessage(role=role, content=content, reasoning_content=reasoning))

    # 4. Must end with assistant
    if out[-1].role != "assistant":
        raise KilnInvalidImportFormat("trace must end with an assistant message.", row_number)

    return out
```

Notes:

- Alternation rule is enforced positionally — `k % 2 == 1` (1-indexed) is always user. This also handles "starts with assistant" (rejected as "expected user, got assistant" on message 1).
- The `tool_calls in msg` check catches assistants that have `tool_calls` even if their `role` is "assistant".

### 3.5 Chain construction

```python
def _build_chain(
    task: Task,
    messages: list[ValidatedMessage],
    file_name: str,
    session_id: str,
    csv_tags: list[str],
) -> list[TaskRun]:
    """Build a chain of TaskRuns from a validated trace. Order: root → leaf."""
    chain: list[TaskRun] = []
    base_tags = generate_import_tags(session_id) + csv_tags

    for turn_idx in range(0, len(messages), 2):
        user_msg = messages[turn_idx]
        assistant_msg = messages[turn_idx + 1]

        cumulative_trace = [
            _to_openai_message(m) for m in messages[: turn_idx + 2]
        ]

        intermediate = {}
        if assistant_msg.reasoning_content:
            intermediate["reasoning"] = assistant_msg.reasoning_content

        run = TaskRun(
            parent=task,
            input=user_msg.content,
            input_source=DataSource(
                type=DataSourceType.file_import,
                properties={"file_name": file_name},
            ),
            output=TaskOutput(
                output=assistant_msg.content,
                source=DataSource(
                    type=DataSourceType.file_import,
                    properties={"file_name": file_name},
                ),
            ),
            intermediate_outputs=intermediate or None,
            trace=cumulative_trace,
            parent_task_run_id=chain[-1].id if chain else None,
            tags=list(base_tags),
        )
        chain.append(run)

    return chain


def _to_openai_message(m: ValidatedMessage) -> ChatCompletionMessageParam:
    if m.role == "user":
        return {"role": "user", "content": m.content}
    # assistant
    msg: dict = {"role": "assistant", "content": m.content}
    if m.reasoning_content:
        msg["reasoning_content"] = m.reasoning_content
    return msg
```

`chain[-1].id` works because `KilnBaseModel` auto-generates a string `id` at instantiation (current behavior across the codebase). `parent_task_run_id` is just a string, never resolved during model validation.

### 3.6 Multiturn import top-level flow

```python
def _import_csv_multiturn(task: Task, config: ImportConfig) -> ImportResult:
    session_id = str(int(time.time()))

    required_headers = {"trace"}
    optional_headers = {"tags"}

    chains: list[list[TaskRun]] = []  # all chains, preflight-validated
    with open(config.dataset_path, "r", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)

        if not reader.fieldnames:
            raise KilnInvalidImportFormat("CSV file appears to be empty or missing headers")

        actual_headers = set(reader.fieldnames)
        missing = required_headers - actual_headers
        if missing:
            # Distinguish from single-turn header error so the message is actionable
            if "input" in actual_headers or "output" in actual_headers:
                raise KilnInvalidImportFormat(
                    "Task is multiturn; expected column: trace (and optional tags). "
                    f"Got: {', '.join(sorted(actual_headers))}."
                )
            raise KilnInvalidImportFormat(
                f"Missing required headers: {', '.join(missing)}."
            )

        unknown = actual_headers - (required_headers | optional_headers)
        if unknown:
            logger.warning(f"Unknown headers in CSV will be ignored: {', '.join(unknown)}")

        for row_number, row in enumerate(reader, start=2):
            try:
                validated = CSVMultiturnRowSchema.model_validate({
                    **row,
                    "tags": deserialize_tags(row.get("tags")),
                })
            except ValidationError as e:
                raise KilnInvalidImportFormat(
                    format_validation_error(e),
                    row_number=row_number,
                ) from e

            messages = _validate_trace(validated.trace, row_number)
            chain = _build_chain(
                task=task,
                messages=messages,
                file_name=config.dataset_name,
                session_id=session_id,
                csv_tags=validated.tags,
            )
            chains.append(chain)

    # Splits apply to leaves only.
    leaves = [chain[-1] for chain in chains]
    add_tag_splits(leaves, config.tag_splits)

    # Save in order: each chain's parents before its children.
    total_runs = 0
    for chain in chains:
        for run in chain:
            run.save_to_file()
            total_runs += 1

    return ImportResult(
        imported_run_count=total_runs,
        imported_conversation_count=len(chains),
    )
```

Single-turn import also adopts the `ImportResult` return type:

```python
def _import_csv_single_turn(task: Task, config: ImportConfig) -> ImportResult:
    # ...existing body...
    return ImportResult(imported_run_count=len(rows), imported_conversation_count=None)
```

### 3.7 Reverse-direction header check (single-turn task, multiturn-shaped CSV)

The existing single-turn header check fails with "Missing required headers: input, output" when `trace` is the only column. To make the error actionable, extend that check:

```python
# in _import_csv_single_turn header validation
if missing_headers and "trace" in actual_headers:
    raise KilnInvalidImportFormat(
        "Task is single-turn; expected columns: input, output (and optional "
        "reasoning, chain_of_thought, tags). Got: "
        f"{', '.join(sorted(actual_headers))}."
    )
```

The existing generic missing-headers error is kept as a fallback for other cases.

## 4. Endpoint design — `run_api.py`

### 4.1 `BulkUploadResponse`

```python
class BulkUploadResponse(BaseModel):
    success: bool
    filename: str
    imported_count: int                          # existing — total runs created
    imported_conversation_count: int | None = None  # new — conversations, or None for single-turn
```

`imported_count` semantics preserved (matches existing tests and frontend behavior). New nullable field carries the conversation count.

### 4.2 Endpoint body

```python
result = importer.create_runs_from_file()
return BulkUploadResponse(
    success=True,
    filename=file_name,
    imported_count=result.imported_run_count,
    imported_conversation_count=result.imported_conversation_count,
)
```

`DatasetFileImporter.create_runs_from_file()` now returns `ImportResult` instead of `int`. No other endpoint changes — header/format errors continue to surface as 422 with `detail=str(e)`.

### 4.3 OpenAPI client regen

Run `app/web_ui/src/lib/generate_schema.sh` after the response model change so the frontend type updates.

## 5. Frontend design — `upload_dataset_dialog.svelte`

### 5.1 Script additions

```ts
import { current_task } from "$lib/stores"
$: is_multiturn = $current_task?.turn_mode === "multiturn"
$: dialog_title = is_multiturn ? "Add Multiturn CSV to Dataset" : "Add CSV to Dataset"
```

### 5.2 Template

Replace the existing help block with a conditional:

```svelte
{#if is_multiturn}
  <p>
    Upload a CSV where each row describes one conversation. The CSV must have a header row.
    The following columns are supported:
  </p>
  <ul class="mb-3 ml-4 mt-3 list-disc">
    <li><code>trace</code> - Required. JSON-encoded list of OpenAI chat messages.</li>
    <li><code>tags</code> - Optional, comma-separated.</li>
  </ul>
  <p class="mb-2">Each <code>trace</code> entry is one message:</p>
  <pre class="text-xs bg-base-200 p-2 rounded mb-3 overflow-x-auto">
{`[
  {"role": "user", "content": "What is the capital of France?"},
  {"role": "assistant", "content": "Paris."},
  {"role": "user", "content": "And of Germany?"},
  {"role": "assistant", "content": "Berlin."}
]`}
  </pre>
  <p class="mb-3 text-xs opacity-70">
    Traces must alternate user/assistant and end with assistant. System messages are not
    supported — set the system prompt on the task instead.
  </p>
  <p class="mb-6">
    <a href="/sample_multiturn.csv" download class="link">Download sample CSV</a>
  </p>
{:else}
  <!-- existing single-turn help block, unchanged -->
{/if}
```

### 5.3 Title binding

`<Dialog title={dialog_title} …>` instead of the hardcoded string.

### 5.4 Success message (parent page)

The "Add Data" page (`add_data/+page.svelte`) already calls `onImportCompleted`. The dialog itself doesn't display success text. If the parent surfaces a count, it can branch on `imported_conversation_count`:

- `null` (single-turn): "Imported N runs."
- non-null (multiturn): "Imported N conversations (M turns total)."

If the parent doesn't currently display counts, no change needed here.

### 5.5 Sample CSV asset

`app/web_ui/static/sample_multiturn.csv` (served at `/sample_multiturn.csv`):

```csv
trace,tags
"[{""role"":""user"",""content"":""Hi""},{""role"":""assistant"",""content"":""Hello!""}]",greeting
"[{""role"":""user"",""content"":""What is 2+2?""},{""role"":""assistant"",""content"":""4""},{""role"":""user"",""content"":""And 3+3?""},{""role"":""assistant"",""content"":""6""}]",math
```

Two rows, demonstrates both one-turn and multi-turn shapes.

## 6. Testing strategy

### 6.1 Core unit tests (`libs/core/kiln_ai/utils/test_dataset_import.py`)

New tests, each writing a minimal in-memory CSV to a tempfile and calling `import_csv` on a multiturn `Task` fixture:

| Test | Asserts |
|---|---|
| `test_import_csv_multiturn_basic` | One conversation, two turns. Verifies 2 TaskRuns, chain order, `parent_task_run_id` link, leaf's full trace, root's `parent_task_run_id is None`. |
| `test_import_csv_multiturn_single_turn_conversation` | Trace with one user/assistant pair → one TaskRun, no parent. |
| `test_import_csv_multiturn_multiple_conversations` | Two rows, verifies they're independent chains (no cross-row parent links). |
| `test_import_csv_multiturn_reasoning_content` | Assistant message with `reasoning_content` → TaskRun's `intermediate_outputs["reasoning"]` populated. |
| `test_import_csv_multiturn_no_reasoning_content` | Assistant without `reasoning_content` → `intermediate_outputs is None`. |
| `test_import_csv_multiturn_tags_on_all_runs` | CSV `tags` column applied to every run in chain. |
| `test_import_csv_multiturn_splits_apply_to_leaves_only` | With splits set, only leaf runs receive split tags; intermediate runs have only import + csv tags. |
| `test_import_csv_multiturn_returns_imported_result` | `ImportResult` shape: `imported_run_count == sum of chain lengths`, `imported_conversation_count == row count`. |
| `test_import_csv_multiturn_input_output_derived` | TaskRun.input == user message; TaskRun.output.output == assistant message. |
| `test_import_csv_multiturn_data_source_is_file_import` | input_source and output.source both have `type=file_import`, `file_name` set. |

Error tests (one per row in §4 of the functional spec):

| Test | Asserts |
|---|---|
| `test_import_csv_multiturn_missing_trace_column` | Header missing `trace` → KilnInvalidImportFormat with "Task is multiturn; expected column: trace". |
| `test_import_csv_multiturn_invalid_json_trace` | `trace` not valid JSON → row-number-tagged error. |
| `test_import_csv_multiturn_trace_not_array` | `trace` is JSON object/string/number → "must be a JSON array". |
| `test_import_csv_multiturn_trace_too_short` | Empty / one-message trace → "at least one user message followed by one assistant message". |
| `test_import_csv_multiturn_unknown_role` | Role `"function"` → "unsupported role 'function'. Allowed: user, assistant." |
| `test_import_csv_multiturn_system_message_rejected` | Role `"system"` → §4 error mentioning task-level system prompt. |
| `test_import_csv_multiturn_developer_message_rejected` | Role `"developer"` → same message family. |
| `test_import_csv_multiturn_tool_role_rejected` | Role `"tool"` → "tool calls and tool messages are not supported". |
| `test_import_csv_multiturn_assistant_with_tool_calls_rejected` | Assistant message containing `tool_calls` → same. |
| `test_import_csv_multiturn_empty_content` | `content: ""` → "'content' must be a non-empty string". |
| `test_import_csv_multiturn_non_string_content` | `content: 42` or `content: [...]` → same error. |
| `test_import_csv_multiturn_starts_with_assistant` | First message is assistant → "expected role 'user', got 'assistant'". |
| `test_import_csv_multiturn_does_not_alternate` | user, user, assistant → "expected role 'assistant', got 'user'". |
| `test_import_csv_multiturn_ends_with_user` | …user, assistant, user → "trace must end with an assistant message". |
| `test_import_csv_multiturn_invalid_tag` | Tag containing whitespace → reuses existing tag validation. |
| `test_import_csv_multiturn_preflight_no_partial_save` | Row 3 has invalid trace → no TaskRuns from rows 2 or 3 are saved (mock the storage layer or check fs state). |
| `test_import_csv_single_turn_task_rejects_trace_csv` | Single-turn task, CSV with only `trace` column → "Task is single-turn; expected columns: input, output…". |

### 6.2 Endpoint tests (`libs/server/kiln_server/test_run_api.py`)

| Test | Asserts |
|---|---|
| `test_bulk_upload_multiturn_success` | Upload to multiturn task → 200, `imported_count == M*N`, `imported_conversation_count == M`. |
| `test_bulk_upload_multiturn_invalid_trace_returns_422` | Bad JSON in trace → 422 with row-tagged detail. |
| `test_bulk_upload_single_turn_response_has_null_conversation_count` | Existing single-turn upload returns `imported_conversation_count: None`. |

### 6.3 Frontend tests (`app/web_ui` Vitest)

| Test | Asserts |
|---|---|
| `upload_dataset_dialog renders multiturn help when task is multiturn` | Mount with `current_task` set to multiturn task → `trace` column listed, `system messages are not supported` callout visible, sample download link present. |
| `upload_dataset_dialog renders single-turn help by default` | Existing behavior unchanged. |
| `upload_dataset_dialog dialog title varies by turn_mode` | Title is "Add Multiturn CSV to Dataset" for multiturn, "Add CSV to Dataset" for single-turn. |

### 6.4 Coverage target

Match repo's existing standards (`uv run python3 -m pytest --benchmark-quiet -q -n auto .`). All new code paths covered. No e2e/Playwright additions in v1 — UI surface is small and unit tests cover the conditional rendering.

## 7. Error handling strategy

- All validation errors raise `KilnInvalidImportFormat` with `row_number` so the existing exception flow produces "Error in row N: …" prefixes.
- The endpoint catches `KilnInvalidImportFormat` and returns 422 with `detail=str(e)` (existing behavior preserved).
- Preflight: nothing persists until all rows are validated. Mid-save IO failures leave partial state — same characteristic as today's single-turn import. Not worth a transactional layer for v1.
- `logger.warning` for unknown headers (preserves existing pattern).
- No retries.

## 8. Open technical questions

None outstanding. Functional spec resolved system-message handling; trace format is locked to OpenAI-style alternation; chain materialization is fully specified above.

## 9. Single-doc vs component breakdown

Single architecture doc — no `/components` subdirectory. The feature has one backend module (~150 LOC of new code), one endpoint with a tiny signature delta, and one Svelte component change. Splitting into per-component docs would be ceremony without value.
