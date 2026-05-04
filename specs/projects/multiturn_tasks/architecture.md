---
status: complete
---

# Architecture: Multiturn Tasks

This is a single-doc architecture (no per-component docs needed). The surface is moderate: ~3 backend files, ~5 frontend files, one new enum, one new API field, one new endpoint, two new Svelte components.

## Data Model

### New enum: `TurnMode`

File: `libs/core/kiln_ai/datamodel/datamodel_enums.py`

```python
class TurnMode(str, Enum):
    single_turn = "single_turn"
    multiturn = "multiturn"
```

### `Task.turn_mode`

File: `libs/core/kiln_ai/datamodel/task.py`

Add to the `Task` class:

```python
turn_mode: TurnMode = Field(
    default=TurnMode.single_turn,
    description="Whether this task is single-turn (each run independent) or multiturn (runs continue prior runs).",
)
```

Migration: existing tasks loaded from disk without `turn_mode` get `TurnMode.single_turn` via the field default — no explicit `@model_validator(mode="before")` needed because Pydantic applies the default for missing keys. We rely on this for forward compatibility.

Immutability: enforced at the API layer (see `update_task` below). Not enforced as a pydantic validator (we still need to allow the model layer to accept either value during load).

Forbidden combinations (enforced via `@model_validator(mode="after")`):

```python
@model_validator(mode="after")
def validate_turn_mode_compatibility(self) -> "Task":
    if self.turn_mode == TurnMode.multiturn:
        if self.input_json_schema is not None:
            raise ValueError(
                "Multiturn tasks cannot have a structured input schema. "
                "Use plaintext input for multiturn tasks."
            )
        if self.output_json_schema is not None:
            raise ValueError(
                "Multiturn tasks do not support structured output yet. "
                "Use plaintext output, or set turn_mode to single_turn."
            )
    return self
```

These raise loudly per the user's directive ("loudly throw in code"). The validator runs both at create and on save, so any path that produces an invalid combination fails.

### `TaskRun` — no change

`TaskRun` already has `trace`, `parent_task_run_id`, and `input`. The semantics change for continuation runs:

- `input`: the new user-turn text only (per spec).
- `parent_task_run_id`: the prior TaskRun's id.
- `trace`: prior trace + this turn's exchange (already produced by the adapter).

No schema changes required.

## Backend API

### Task update — enforce immutability

File: `libs/server/kiln_server/task_api.py` — modify `update_task`.

Add immutability check alongside the existing schema check:

```python
if "turn_mode" in task_updates:
    if task_updates["turn_mode"] != original_task.turn_mode.value:
        raise HTTPException(
            status_code=400,
            detail="Task turn_mode cannot be changed after creation.",
        )
```

Following the existing pattern (compare value rather than block presence) so frontend round-trips of the full task object are tolerated.

### Run endpoint — accept `parent_task_run_id`

File: `libs/server/kiln_server/run_api.py`

Update `RunTaskRequest`. The field name **mirrors `TaskRun.parent_task_run_id`** on purpose — same concept, same name.

```python
class RunTaskRequest(BaseModel):
    run_config_properties: RunConfigProperties = Field(...)
    plaintext_input: str | None = Field(default=None, ...)
    structured_input: StructuredInputType | None = Field(default=None, ...)
    tags: list[str] | None = Field(default=None, ...)
    parent_task_run_id: str | None = Field(
        default=None,
        description="When set, treat this as a continuation of the given parent run "
                    "(multiturn tasks only). The parent run's trace is passed as prior_trace, "
                    "and parent_task_run_id is set on the resulting TaskRun.",
    )
```

Update `run_task` handler:

```python
async def run_task(...) -> TaskRun:
    task = task_from_id(project_id, task_id)
    ...
    prior_trace = None
    parent_task_run = None
    if request.parent_task_run_id is not None:
        if task.turn_mode != TurnMode.multiturn:
            raise HTTPException(
                status_code=400,
                detail="parent_task_run_id is only valid for multiturn tasks.",
            )
        parent_task_run = TaskRun.from_id_and_parent_path(request.parent_task_run_id, task.path)
        if parent_task_run is None:
            raise HTTPException(status_code=404, detail=f"Parent run not found: {request.parent_task_run_id}")
        prior_trace = parent_task_run.trace

    ...
    return await adapter.invoke(
        input,
        prior_trace=prior_trace,
        parent_task_run=parent_task_run,
    )
```

The adapter (`base_adapter.py`) already accepts both `prior_trace` and `parent_task_run`, sets `parent_task_run_id` on the new TaskRun via `generate_run`, and persists the run when `autosave_runs` is on. No adapter changes needed.

### `runs_summaries` — leaf-only filter

File: `libs/server/kiln_server/run_api.py` — modify `get_runs_summary`.

```python
async def get_runs_summary(...) -> list[RunSummary]:
    task = task_from_id(project_id, task_id)
    runs = task.runs(readonly=True)
    parent_ids: set[str] = {r.parent_task_run_id for r in runs if r.parent_task_run_id}
    return [
        RunSummary.from_run(run)
        for run in runs
        if run.id not in parent_ids
    ]
```

For single-turn tasks, no run has a `parent_task_run_id`, so the filter is a no-op. No mode branch needed.

### No new conversation endpoint

The leaf `TaskRun.trace` already contains the full conversation as a list of messages (the adapter appends each new exchange to the prior trace and stores it on the new run). The multiturn run-detail page renders the conversation directly from that field — no chain walk, no extra endpoint.

Trade-off acknowledged: per-turn metadata (model, latency, cost) and per-turn ratings for *prior* turns are not surfaced in the conversation view, since those live on the prior `TaskRun`s rather than in the trace. The leaf's metadata is rendered once (in the existing properties panel and rating UI) and applies to "the current turn." Users who want to inspect or rate an interior turn navigate to that turn's run-detail URL directly. This is acceptable for v1 — interior-node discovery is a forking-feature concern, deferred.

### Dataset splits — leaf-only

File: `libs/core/kiln_ai/datamodel/dataset_split.py` — modify `build_split_contents`.

Add a leaf filter pre-step:

```python
@classmethod
def build_split_contents(cls, task, splits, filter):
    runs = list(task.runs())
    parent_ids = {r.parent_task_run_id for r in runs if r.parent_task_run_id}
    valid_ids = []
    for task_run in runs:
        if task_run.id in parent_ids:
            continue  # interior node — skip
        if filter(task_run):
            valid_ids.append(task_run.id)
    ...  # existing shuffle / split logic unchanged
```

For single-turn tasks the `parent_ids` set is empty — no behavior change. The interior-node exclusion is global; we don't expose a way to opt back in for v1 (forking is out of scope).

## Adapter Layer

No adapter changes. The relevant entry points already accept `prior_trace` and `parent_task_run`:

- `BaseAdapter.invoke(input, input_source, prior_trace, parent_task_run)` — `base_adapter.py:201`
- `BaseAdapter._reject_multiturn_with_structured_input(prior_trace)` — `base_adapter.py:191` (already raises if multiturn + structured input; with our task-level validator this should never fire from the API path, but it remains as a defense-in-depth check)
- `BaseAdapter.generate_run(...)` — sets `parent_task_run_id` from the passed `parent_task_run` — `base_adapter.py:626`

The `MultiturnFormatter` selected via `build_chat_formatter()` (when `prior_trace` is non-empty) already produces correct messages.

## Frontend

### OpenAPI types

After backend changes, run `app/web_ui/src/lib/generate_schema.sh` to regenerate `lib/types.d.ts` so the new `prior_run_id`, `turn_mode`, and `/conversation` endpoint are typed. CI runs `check_schema.sh` to verify.

### Task creation / edit form

File: `app/web_ui/src/routes/(fullscreen)/setup/(setup)/create_task/edit_task.svelte`

Add near the top of the form (before input/output schema sections):

- A two-option control bound to a local `turn_mode` variable (default `"single_turn"`).
- Reactive: when `turn_mode === "multiturn"`, hide the input/output schema sections and show explanatory copy.
- The `turn_mode` value is included in the create-task payload.
- On the edit page (which reuses this component): pass a prop `disable_turn_mode={true}` (or detect existing task) to render the value as a read-only label.

The control itself can be a simple `<div class="join">` with two buttons, matching DaisyUI patterns already used elsewhere in the form.

### `/run` page — branch on send success

File: `app/web_ui/src/routes/(app)/run/+page.svelte`

Modify the `run_task()` handler to branch on `$current_task.turn_mode`:

```svelte
const data = await client.POST(...);
if (fetch_error) throw fetch_error;
response = data;
if ($current_task.turn_mode === "multiturn" && data?.id) {
  await goto(`/dataset/${project_id}/${task_id}/${data.id}/run`);
  return;
}
// existing single-turn behavior: render output inline
```

Cosmetic: change submit label from `"Run"` to `"Send"` when multiturn.

No file split needed for `/run/+page.svelte` — this is a small, focused change. The conversation view lives on the run-detail page, not here.

### Dataset run-detail page — conversation rendering for multiturn

File: `app/web_ui/src/routes/(app)/dataset/[project_id]/[task_id]/[run_id]/run/+page.svelte`

Currently 528 lines. We branch its body based on `$current_task?.turn_mode`:

- Single-turn: existing layout (Properties + Input + Run output) — unchanged.
- Multiturn: render `<ConversationView>` (new) sourced from `run.trace`, plus the existing leaf-level Properties + Rating, plus `<Composer>` (new) at the bottom.

To keep this file lean, we extract the multiturn UI into separate components rather than inlining.

### New components

Location: `app/web_ui/src/lib/ui/conversation/`

#### `conversation_view.svelte`

Props:
- `trace: ChatCompletionMessageParam[]` — taken directly from the leaf TaskRun's `trace` field
- `task: Task`

Internal: groups the trace messages into turns (skipping the system message; pairing each user message with the immediately following assistant message — tool calls/results are flattened into the assistant block of the turn that requested them, since the adapter only creates a new TaskRun per `user → assistant` exchange).

Renders one `<TurnCard>` per turn.

#### `turn_card.svelte`

Props:
- `user_text: string`
- `assistant_text: string`
- `turn_index: number` (1-based)
- `tool_messages?: ChatCompletionMessageParam[]` — optional list of inlined tool call/result messages within this turn

Renders:
- Header strip: "Turn N"
- User message — markdown via `chat_markdown.svelte`
- Tool calls/results, if any — collapsible block (reuse `chat_step_group.svelte` if its API is convenient, else a small local `<details>`)
- Reasoning content (if the assistant message carries `reasoning_content`) — collapsible block
- Assistant message — markdown via `chat_markdown.svelte`

No per-turn rating control. No "View run details" link (the trace doesn't carry per-turn TaskRun ids). The leaf's rating + metadata is shown once at the top/bottom of the page using the existing run-detail UI — that suffices for "rate the current turn."

#### `composer.svelte`

Props:
- `task: Task`
- `project_id: string`
- `previous_run: TaskRun` — the leaf, to inherit its run config as default and to source `parent_task_run_id`
- `on_send: (new_run_id: string) => void` — invoked after a successful turn

Internal:
- Reuses `RunConfigComponent` and `RunInputForm` (plaintext only — multiturn is plaintext per validation).
- Run config defaults from `previous_run.output.source.run_config` so the user lands on the same model/prompt by default.
- Send handler POSTs `/run` with `parent_task_run_id: previous_run.id`, then calls `on_send(new_run_id)`.

The page-level handler for `on_send`:

```ts
async function on_send(new_run_id: string) {
  await goto(`/dataset/${project_id}/${task_id}/${new_run_id}/run`, {
    replaceState: true,
  });
  // SvelteKit page params change triggers re-load via $page reactive block; or call load_run() / load_chain() explicitly.
}
```

`replaceState: true` keeps the back button from cycling through every turn.

### Markdown reuse

Existing component at `app/web_ui/src/lib/ui/chat/chat_markdown.svelte` is already in `$lib/ui` — usable as-is from the conversation components without further extraction.

## Error Handling

Backend:
- Invalid task config (multiturn + structured I/O): pydantic `ValueError` → FastAPI returns 422.
- Continuation on single-turn task: 400 (with descriptive message).
- Parent run not found: 404.
- Adapter-level rejection of multiturn + structured input: still raises `ValueError` (defense-in-depth) → 422 if it ever fires.

Frontend:
- `/run` Send failure: existing inline error path.
- Composer Send failure: error inline above the composer; user's text preserved; explicit Retry button.
- Conversation load failure: existing run-detail-page error path.

## Testing Strategy

### Backend (pytest)

New / modified tests under `libs/core/kiln_ai/datamodel/test_*.py` and `libs/server/kiln_server/test_*.py`:

- `test_task.py`:
  - `Task` defaults `turn_mode=single_turn`.
  - Existing task JSON without `turn_mode` loads as `single_turn`.
  - `multiturn` + `input_json_schema` raises ValueError.
  - `multiturn` + `output_json_schema` raises ValueError.
  - `single_turn` allows both schemas.
- `test_task_api.py`:
  - PATCH with `turn_mode` matching existing → 200.
  - PATCH with `turn_mode` differing → 400.
  - POST creating a multiturn task with structured schema → 422.
- `test_run_api.py`:
  - POST `/run` with `parent_task_run_id` for multiturn task → new TaskRun has `parent_task_run_id` set; `trace` extends parent's.
  - POST `/run` with `parent_task_run_id` for single-turn task → 400.
  - POST `/run` with non-existent `parent_task_run_id` → 404.
  - GET `/runs_summaries` filters interior nodes for a multiturn task with a 3-turn chain (returns leaf only).
  - GET `/runs_summaries` for single-turn task returns all runs.
- `test_dataset_split.py`:
  - `build_split_contents` excludes interior nodes given a multiturn chain.
  - Single-turn unchanged.

### Frontend (vitest)

- Component tests for `TurnCard.svelte`, `ConversationView.svelte`, `Composer.svelte`:
  - TurnCard renders user + assistant + metadata.
  - ConversationView renders N TurnCards for an N-element chain.
  - Composer disables Send while pending; preserves text on error; calls `on_send` with the new run id.
- Page-level smoke: dataset run-detail page renders single-turn layout for single-turn task, conversation layout for multiturn task.

### Manual

- End-to-end click path with a real model: create multiturn task → send turn 1 → observe URL change → send turn 2 → observe new run created with `parent_task_run_id` set → backtrack to leaf → observe conversation view.
- Confirm `runs_summaries` list view shows only leaves after a multiturn conversation.

## File Touch Map

Backend:
- `libs/core/kiln_ai/datamodel/datamodel_enums.py` — add `TurnMode`.
- `libs/core/kiln_ai/datamodel/task.py` — field + validator.
- `libs/core/kiln_ai/datamodel/dataset_split.py` — leaf filter in `build_split_contents`.
- `libs/server/kiln_server/task_api.py` — immutability check in `update_task`.
- `libs/server/kiln_server/run_api.py` — `parent_task_run_id` field, plumb into `run_task`, leaf filter in `get_runs_summary`.

Frontend:
- `app/web_ui/src/routes/(fullscreen)/setup/(setup)/create_task/edit_task.svelte` — turn_mode selector, conditional schema section visibility, read-only mode for edit.
- `app/web_ui/src/routes/(app)/run/+page.svelte` — branch on success; relabel button.
- `app/web_ui/src/routes/(app)/dataset/[project_id]/[task_id]/[run_id]/run/+page.svelte` — branch into ConversationView + Composer for multiturn.
- `app/web_ui/src/lib/ui/conversation/conversation_view.svelte` — new.
- `app/web_ui/src/lib/ui/conversation/turn_card.svelte` — new.
- `app/web_ui/src/lib/ui/conversation/composer.svelte` — new.
- `app/web_ui/src/lib/types.d.ts` — regenerated from OpenAPI.

Tests:
- Backend tests listed above (likely 3-4 test files touched).
- Frontend tests for the three new components.

## Out of Scope (Architectural Notes)

- **Streaming:** the run endpoint remains one-shot. The composer architecture (clear separation between request/response and view rendering) leaves room to swap in an SSE consumer later without restructuring.
- **Tool approvals:** none. Multiturn runs invoke tools the same way the existing run page does.
- **Forking / branching UI:** the data model already tolerates branches via `parent_task_run_id`; no UI exposes branching in v1. Dataset split filter excludes all interior nodes — when forking arrives, this filter will need to become more nuanced (likely opt-in inclusion of selected interior nodes).
- **Eval / finetune integration for multiturn:** out of scope; the eval team owns this.
