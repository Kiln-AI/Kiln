---
status: complete
---

# Functional Spec: Multiturn CSV Upload

## 1. Overview

Extend Kiln's existing bulk-upload endpoint (`POST /api/projects/{project_id}/tasks/{task_id}/runs/bulk_upload`) so that, when invoked on a multiturn task, it accepts a CSV whose rows describe full conversations. Each row materializes as a chain of `TaskRun`s linked via `parent_task_run_id` — structurally identical to what a live multiturn run produces.

## 2. CSV Format

### 2.1 Multiturn CSV (one row = one conversation)

| Column | Required | Notes |
|---|---|---|
| `trace` | **yes** | JSON-encoded list of OpenAI-format chat messages (the full conversation). |
| `tags` | no | Comma-separated tag list, applied to every run in the chain. Same validation as existing single-turn CSV (no whitespace inside a tag). |

No `input`, `output`, `reasoning`, or `chain_of_thought` columns for multiturn. All of that information lives inside `trace`:

- The current-turn `input` for each TaskRun is derived from the corresponding user message in the trace.
- The current-turn `output` for each TaskRun is derived from the corresponding assistant message.
- Assistant `reasoning_content` (if present on a message) is captured in that run's `intermediate_outputs["reasoning"]`.

### 2.2 Trace JSON schema

`trace` must parse to a JSON array of message objects. Allowed shapes (v1):

```jsonc
// User message
{ "role": "user", "content": "<string>" }

// Assistant message
{
  "role": "assistant",
  "content": "<string>",
  "reasoning_content": "<string, optional>"
}
```

**Rejected in v1** (import errors loudly rather than silently dropping):

- `system` and `developer` messages — multiturn tasks define their system prompt on the task itself; per-conversation system prompts would silently collide. See §4 for the error message and rationale.
- `tool` messages and `tool_calls` on assistant messages.
- Multi-part content arrays (`content: [{type: "text", …}, {type: "image_url", …}]`).
- Per-message telemetry fields (`usage`, `latency_ms`, `cost`).

### 2.3 Trace validity rules

A trace is valid iff **all** of:

1. Parses as a JSON array with length ≥ 2.
2. Every element has a `role` field in `{user, assistant}` and a `content` field that is a non-empty string. Any other role (`system`, `developer`, `tool`, …) rejects the row — see §4.
3. Messages strictly alternate `user, assistant, user, assistant, …`, starting with `user`.
4. The last message is an `assistant` message. (The chain's leaf TaskRun's `output` must come from an assistant turn.)

## 3. Behavior

### 3.1 Endpoint routing

Same endpoint, auto-detected by `task.turn_mode`:

- `turn_mode == single_turn` → existing single-turn CSV parser (unchanged).
- `turn_mode == multiturn` → new multiturn CSV parser.

The two formats are not interchangeable — uploading a single-turn-shaped CSV to a multiturn task (or vice versa) fails header validation with a clear error.

### 3.2 Conversation → TaskRun chain materialization

For a row whose `trace` contains M user→assistant turn pairs, the import creates **M TaskRuns** in parent-chain order:

- TaskRun 1 (root): `parent_task_run_id = None`, `trace = [user_1, assistant_1]`, `input = user_1.content`, `output = assistant_1.content`.
- TaskRun k (1 < k < M): `parent_task_run_id = TaskRun_{k-1}.id`, `trace = [user_1, assistant_1, …, user_k, assistant_k]`, `input = user_k.content`, `output = assistant_k.content`.
- TaskRun M (leaf): same pattern, full trace.

For each created TaskRun:

- `input_source` = `DataSource(type=file_import, properties={"file_name": <uploaded filename>})`
- `output` = `TaskOutput(output=assistant_k.content, source=DataSource(type=file_import, ...))`
- `intermediate_outputs["reasoning"]` = `assistant_k.reasoning_content` if present, else key omitted.
- `tags` = auto import tag(s) + any tags from the CSV row (applied to every run in the chain so chain queries remain consistent).
- Per-message `usage` / `latency_ms` are **not** populated. `cumulative_usage` is left null.

### 3.3 Splits

The existing endpoint accepts a `splits` form parameter (JSON mapping split name → proportion). For multiturn:

- Splits are assigned **only to leaf TaskRuns** — intermediate runs do not receive split tags. This matches how the rest of the system treats intermediate runs (filtered out by `filter_runs(include_intermediate_runs=False)`).

### 3.4 Persistence semantics

- Validation is preflight: all rows must validate before *any* TaskRun is saved (matching existing behavior for single-turn CSV).
- On success, all chains are saved sequentially. Within a single conversation, parents must save before children so `parent_task_run_id` references resolve to persisted IDs.
- On a save failure mid-way (rare; disk/IO), partial state is left in place — the same partial-write characteristic the existing import has. Not worth introducing a transactional layer for v1.

## 4. Errors

Errors are reported as `KilnInvalidImportFormat(message, row_number)` (existing exception), surfaced to the API as a 400. Specific errors v1 must produce:

| Condition | Error message |
|---|---|
| Task is `single_turn`, CSV has `trace` column or lacks `input`/`output` | `Task is single-turn; expected columns: input, output (and optional reasoning, chain_of_thought, tags). Got: <columns>.` |
| Task is `multiturn`, CSV lacks `trace` column | `Task is multiturn; expected column: trace (and optional tags). Got: <columns>.` |
| `trace` not valid JSON | `Row N: trace is not valid JSON.` |
| `trace` not a JSON array | `Row N: trace must be a JSON array of messages.` |
| Trace shorter than 2 messages | `Row N: trace must contain at least one user message followed by one assistant message.` |
| `system` or `developer` message present | `Row N, message K: trace contains a system message. Multiturn tasks define their system prompt on the task itself, not per-conversation. Remove system/developer messages from your CSV, or update the task's system prompt to match.` |
| `tool` message or `tool_calls` present | `Row N, message K: tool calls and tool messages are not supported in CSV import.` |
| Any other unknown role | `Row N, message K: unsupported role '<role>'. Allowed: user, assistant.` |
| Non-string or empty content | `Row N, message K: 'content' must be a non-empty string.` |
| Roles do not alternate user/assistant (or trace does not start with user) | `Row N, message K: expected role '<expected>', got '<actual>'.` |
| Last message is not assistant | `Row N: trace must end with an assistant message.` |
| Invalid tag (whitespace, etc.) | reuses existing tag validation message |

Unknown CSV columns produce a warning (not an error), matching existing behavior.

## 5. UI

Entry point unchanged: `app/web_ui/src/routes/(app)/dataset/[project_id]/[task_id]/upload_dataset_dialog.svelte`, invoked from the "Add Data" page. Task context comes from the existing `current_task` store (`$lib/stores.ts`), which carries `turn_mode`.

### 5.1 Turn-mode-aware help block

The dialog branches its help text on `$current_task?.turn_mode`:

- **`single_turn` (existing):** unchanged — lists `input` (required), `output` (required), `reasoning`, `chain_of_thought`, `tags`.
- **`multiturn`:** new help text. Lists:
  - `trace` (required) — JSON-encoded list of OpenAI chat messages, each `{role: "user" | "assistant", content: string}`. Assistant messages may include optional `reasoning_content`.
  - `tags` (optional) — comma-separated.

  Also includes:
  - A short inline example showing one row (`trace` with two user/assistant pairs).
  - A "Download sample CSV" link pointing at a static asset (`/static/sample_multiturn.csv` or equivalent — exact path TBD in implementation).
  - A one-line callout: "Multiturn traces must alternate user/assistant and end with assistant. System messages are not supported — set the system prompt on the task instead."

### 5.2 Dialog title

Title varies by turn mode:

- Single-turn: "Add CSV to Dataset" (unchanged).
- Multiturn: "Add Multiturn CSV to Dataset".

### 5.3 Unchanged surface

- File picker, accept filter (`.csv`), upload button, cancel button.
- `splits` form-data wiring (existing).
- Error rendering. The new multiturn errors from §4 surface through the same mechanism as existing CSV errors (the dialog already throws on API error; the parent page is responsible for rendering it — no dialog-level change needed).

### 5.4 Not in this dialog

- Per-row preview, dry-run, or trace-rendering inside the upload flow. Users validate by uploading and reading errors — same as existing single-turn UX.

## 6. Out of Scope (v1)

- `system` and `developer` messages inside `trace`. Rejected at import — multiturn tasks define their system prompt on the task itself; per-conversation overrides would silently collide with that single source of truth.
- Tool-call turns (`role: "tool"`, `tool_calls` on assistant messages).
- Multi-part content arrays (`content: [{type: "text", …}, {type: "image_url", …}]`).
- Per-message telemetry fields (`usage`, `latency_ms`, `cost`).
- Branching conversations within a CSV (each row is one linear chain; no shared ancestors across rows).
- CSV **export** of multiturn runs (KIL-658 is import only).
- Alternative authoring formats (sharegpt, ChatML, JSONL). CSV with JSON `trace` only.
