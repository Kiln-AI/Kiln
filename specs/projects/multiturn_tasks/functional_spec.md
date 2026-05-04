---
status: complete
---

# Functional Spec: Multiturn Tasks

## Goal

Allow a Kiln `Task` to be either single-turn or multiturn. A multiturn task supports continuation — a new run can be created from a prior run's trace, producing a chat-like conversation. Single-turn tasks behave exactly as today.

## Vocabulary

- **Trace**: the OpenAI-format message list (`list[ChatCompletionMessageParam]`) stored on `TaskRun.trace`. It contains the full conversation up to and including this turn.
- **Turn**: one user message + one assistant response inside a conversation. In this design, **one turn = one `TaskRun`**.
- **Conversation**: a chain of `TaskRun`s linked by `parent_task_run_id`. The leaf is the most recent turn; walking parents reaches turn 1.

## Data Model

### `Task.turn_mode`

A new field on `Task`:

- Name: `turn_mode`
- Type: string enum
- Values: `"single_turn"` | `"multiturn"`
- Default: `"single_turn"`
- Existing tasks loaded from disk without the field: treated as `"single_turn"` via the existing migration pattern (`@model_validator(mode="before")` while `loading_from_file=True`).

**Immutable.** Once a task is created, `turn_mode` cannot be changed. The Task update API rejects any change to this field with a clear error. Rationale: changing turn mode mid-life would create incoherent run histories and break dataset/eval semantics. Users who need a different mode should create a new task.

### `TaskRun` (no schema change)

`TaskRun` already has the necessary fields:

- `trace: list[ChatCompletionMessageParam]` — full conversation history up to and including this turn.
- `parent_task_run_id: str | None` — link to the previous turn's TaskRun.
- `input: str` — for a continuation TaskRun, this stores **only the new user-turn text** (i.e. the user's message for this turn). The earlier conversation is reachable via `trace` and via the parent chain.
- `output`: the assistant's response text for this turn (matches today's semantics).

No new TaskRun fields are required.

## Validation Rules

The following combinations are rejected. Errors are raised loudly in code (clear exception messages, not silent fallbacks):

| Combination | Behavior |
|---|---|
| `turn_mode=multiturn` + `input_json_schema` set | **Rejected at task creation/save.** Multiturn requires plaintext input. |
| `turn_mode=multiturn` + `output_json_schema` set | **Rejected at task creation/save** for v1. Door left open: design assumes that, if added later, every assistant turn would conform to the output schema. Not implemented now. |
| Continuation run (multiturn) where any prior assistant message contains structured output | n/a in v1 because of the rule above. |
| Tool-approval workflow on multiturn run page | n/a in v1. Tools execute the same as on the current run page, with no approval step. |

UI corollary: at task creation, if the user picks `multiturn`, the input/output schema fields are hidden (or disabled). If the user already filled in a schema, switching to multiturn is blocked with an inline error.

Backend corollary: API requests that violate any of the above are rejected with a 4xx error and a descriptive message.

## Run Lifecycle (Multiturn)

### Turn 1 — fresh conversation

1. User navigates to `/run` for a multiturn task.
2. Same input form as today (plaintext input, run-config picker).
3. User clicks Send.
4. Backend `POST /api/projects/{p}/tasks/{t}/run` runs the task with no `prior_trace`. A new `TaskRun` is created and persisted to disk.
5. Frontend navigates the user to `/dataset/{p}/{t}/{new_run_id}/run` (the run-detail page becomes the conversation page).

### Turn 2..N — continuation

1. User is on `/dataset/{p}/{t}/{run_id}/run` (the run-detail page) for a multiturn task. The page renders the full conversation from the loaded TaskRun's `trace`.
2. A composer is shown at the bottom of the page (only for multiturn tasks).
3. User picks a run config (defaults to the previous turn's config; user can change it for this turn) and types the next message.
4. On Send, frontend POSTs the run request including a reference to the prior TaskRun id. Backend resolves `prior_trace` from that prior TaskRun's `trace`.
5. Backend creates a new `TaskRun` with:
   - `input` = the new user-turn text only
   - `parent_task_run_id` = prior TaskRun's id
   - `trace` = `prior_trace` + the new exchange
   - persisted to disk
6. Frontend replaces the URL to `/dataset/{p}/{t}/{new_run_id}/run` (browser history replace, not push, to avoid back-button stepping through every turn — TBD if push is preferred).
7. The page now shows the conversation with the additional turn. Composer is reset.

### Run config across turns

Each turn picks its own run config. The default for turn N is the run config used for turn N-1. The user can switch model / prompt method between turns. (Note: this flexibility may be revisited later if it complicates evals, per user direction.)

### Errors during a turn

If a turn fails (model error, tool error, validation), no new `TaskRun` is persisted. The composer remains populated with the user's input so they can retry. Existing single-turn run error behavior is the model.

## API Changes

### Task create / update

- `Task` payload includes `turn_mode`.
- Update endpoint rejects any change to `turn_mode` (must equal the existing value).

### `POST /api/projects/{p}/tasks/{t}/run` — RunTaskRequest

Add an optional field referencing a prior TaskRun:

- `prior_run_id: str | None` (or similar; exact name decided in architecture step)

When set:
- Server loads the prior `TaskRun`, derives `prior_trace` from its `trace` field, passes through to the adapter.
- Server validates that the task is `multiturn`. If the task is single-turn, reject with 4xx.
- Server sets `parent_task_run_id` on the resulting new TaskRun to `prior_run_id`.

When unset: existing behavior (turn 1 of a multiturn convo, or a single-turn task run).

### `runs_summaries` endpoint

Add a leaf-only filter so list views show only the latest turn of each conversation:

- Endpoint: `GET /api/projects/{p}/tasks/{t}/runs_summaries`
- Default behavior: returns only TaskRuns that are not a `parent_task_run_id` of any other TaskRun (i.e. leaves).
- Single-turn TaskRuns are always leaves (no children), so they are unaffected.
- Multiturn intermediate runs are hidden in summary lists. They remain reachable via deep links (run-detail page still loads any id).

### Dataset splits

Dataset split creation must also respect leaf-only semantics for multiturn tasks. When splits are populated from TaskRun ids, only leaves are eligible. Including an interior turn in a split is rejected with a clear error.

(Forking / explicit selection of an interior node is out of scope for v1. A future feature will allow taking a handle on a parent node to fork a conversation.)

## UI

### Same `/run` route, cleanly split

The `/run` route remains the entry point for new runs. Internally the page branches:

- Single-turn task: existing UI (input form, run config, output).
- Multiturn task: input form for turn 1 only (no inline output rendering — on success, we navigate away).

The implementation must split the page into focused components. No 800-line monolith. Concretely (subject to architecture step):

- Split out the input form, the run-config picker, and the output panel as separate components if not already.
- The multiturn turn-1 view reuses the input form and run-config picker.
- A new "conversation view" component is used on the run-detail page for multiturn tasks.

### Run-detail page (`/dataset/{p}/{t}/{run_id}/run`)

- Single-turn task: unchanged.
- Multiturn task:
  - Renders the conversation from the loaded TaskRun's `trace` field.
  - Each message rendered with the existing chat markdown renderer (reuse / extract `chat_markdown.svelte`).
  - Per-message UI shows role (user / assistant), and any reasoning / tool-call structure as appropriate.
  - A composer is pinned at the bottom: textarea + run-config picker + Send button.
  - On Send: creates new TaskRun, URL updates to `/dataset/{p}/{t}/{new_run_id}/run`.

The conversation rendering is intentionally more structured than the chat page (this is not a chat clone). It looks like the current run UI, with each turn as a clearly bounded block, not a free-flowing chat stream.

### Task creation / edit

- Task creation form: add `turn_mode` selector (single-turn default).
- If multiturn is selected: hide / disable input and output schema fields and explain why.
- Task edit form: `turn_mode` is shown as read-only.

### No streaming in v1

Each turn is one-shot, same as today's run endpoint. The page shows a loading state while waiting for the assistant's response. Streaming is explicitly deferred — the run-page split should be done in a way that lets streaming be added later as a focused change (e.g. the conversation-view component would consume an updateable message rather than only a finalized one).

### Markdown rendering

Each message in the conversation view is rendered with markdown. Reuse the existing chat markdown renderer. If keeping it under `routes/(app)/chat/` is too coupled, lift it to a shared `$lib` location.

## Out of Scope (v1)

- Streaming responses on the multiturn run page.
- Tool-approval workflow on the multiturn run page.
- Multiturn + structured output (door left open in design).
- Evals: no eval-side changes; eval team owns this separately.
- Finetune: no `ChatStrategy` plumbing, no multiturn dataset export.
- Forking conversations / explicit interior-node selection in dataset split UI.
- Editing or deleting individual turns.
- Branching multiple replies from the same parent.
- Toggling a task between single-turn and multiturn after creation.

## Edge Cases

- **Loading a deeply-nested run:** the run-detail page must walk the chain via `trace` (which already includes everything) — no extra API calls needed to display the conversation.
- **Orphaned interior runs:** if a multiturn task has interior runs but no leaves (all leaves deleted), the interior runs are still reachable by id but won't appear in `runs_summaries`. Acceptable.
- **Branching due to retries (future):** retries that create a new TaskRun off the same `parent_task_run_id` would create branches. v1 does not expose retries that branch — a failed turn does not persist a TaskRun, so no branching occurs. The data model already tolerates branches via `parent_task_run_id`.
- **Run-config change mid-conversation:** producing a turn with a different model/prompt is allowed. The run-config used is recorded on the new TaskRun, same as any single run today.
- **Task immutability after first run:** because `turn_mode` is immutable from creation, no special handling needed once runs exist.
