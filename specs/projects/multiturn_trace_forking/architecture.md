---
status: complete
---

# Architecture: Multiturn Trace Forking

Single-doc architecture — no component sub-docs. Surface: 1 new backend endpoint, ~2 backend tests files updated, ~3 frontend files modified, 1 new icon, 0 schema changes.

## Data Model

**No changes.** The data model already supports forking via `TaskRun.parent_task_run_id`. This project only adds traversal and a UI affordance.

## Backend

### New endpoint: ancestor chain traversal

**Route:** `GET /api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/ancestors`

**File:** `libs/server/kiln_server/run_api.py`

**Response model** (define near `RunTaskRequest`):

```python
class TaskRunAncestor(BaseModel):
    run_id: str
    turn_index: int = Field(
        description="1-based turn index in the leaf's conversation (turn 1 = root, "
                    "turn N = leaf). Derived from the leaf's trace user-message count."
    )

class TaskRunAncestorsResponse(BaseModel):
    ancestors: list[TaskRunAncestor] = Field(
        description="Ordered root-to-leaf, includes the requested run itself as the "
                    "final entry. If chain_broken is true, the list contains only the "
                    "intact suffix from the leaf back to (and excluding) the break point."
    )
    chain_broken: bool = Field(
        description="True if while walking parents we encountered a parent_task_run_id "
                    "that could not be loaded (file missing/unreadable), or a cycle, or "
                    "the chain length did not match the leaf's trace user-message count."
    )
```

**Handler:**

```python
@app.get("/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/ancestors")
async def get_run_ancestors(
    project_id: Annotated[str, Path(...)],
    task_id: Annotated[str, Path(...)],
    run_id: Annotated[str, Path(...)],
) -> TaskRunAncestorsResponse:
    task = task_from_id(project_id, task_id)
    if task.turn_mode != TurnMode.multiturn:
        raise HTTPException(
            status_code=400,
            detail="Ancestors are only available for multiturn tasks.",
        )
    leaf = TaskRun.from_id_and_parent_path(run_id, task.path)
    if leaf is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    chain, chain_broken = _walk_ancestors(leaf, task.path)
    turn_count = _count_user_messages(leaf.trace)
    # Suffix-align: last entry of `chain` is the leaf (turn = turn_count),
    # walk backwards assigning turn_index = turn_count - i.
    if len(chain) > turn_count:
        # Pathological: more ancestors than user messages. Treat as broken.
        chain = chain[-turn_count:]
        chain_broken = True
    ancestors = [
        TaskRunAncestor(run_id=r.id, turn_index=turn_count - (len(chain) - 1 - i))
        for i, r in enumerate(chain)
    ]
    return TaskRunAncestorsResponse(ancestors=ancestors, chain_broken=chain_broken)
```

**Private helpers (same file):**

```python
_MAX_ANCESTOR_DEPTH = 1000  # cycle / runaway guard

def _walk_ancestors(leaf: TaskRun, task_path: Path) -> tuple[list[TaskRun], bool]:
    """
    Walk parent chain from leaf upward. Returns (chain_root_to_leaf, chain_broken).

    chain_broken is True if:
      - any parent_task_run_id failed to load,
      - we exceeded _MAX_ANCESTOR_DEPTH,
      - or we detected a cycle.

    On break, returns the intact prefix from `leaf` back to (but not including) the
    missing/cyclic node, reversed to root-to-leaf order.
    """
    chain: list[TaskRun] = [leaf]
    visited: set[str] = {leaf.id}
    current = leaf
    for _ in range(_MAX_ANCESTOR_DEPTH):
        if current.parent_task_run_id is None:
            chain.reverse()
            return chain, False
        if current.parent_task_run_id in visited:
            chain.reverse()
            return chain, True
        parent = TaskRun.from_id_and_parent_path(current.parent_task_run_id, task_path)
        if parent is None:
            chain.reverse()
            return chain, True
        chain.append(parent)
        visited.add(parent.id)
        current = parent
    chain.reverse()
    return chain, True

def _count_user_messages(trace: list[ChatCompletionMessageParam] | None) -> int:
    if not trace:
        return 0
    return sum(1 for m in trace if m.get("role") == "user")
```

Notes:
- The helpers are private to the module (underscore-prefixed). They have no need to live in the data model layer.
- `_walk_ancestors` walks chronologically backwards (leaf → root) building a list in reverse, then reverses once at the end. O(N) in chain depth.
- `_MAX_ANCESTOR_DEPTH` is intentionally generous; real chains will be small.
- Cycle detection: tracks visited ids. A cycle is an inconsistency we shouldn't see in practice, but tolerating it keeps the endpoint safe.

### No changes to existing endpoints

- `POST /api/projects/{p}/tasks/{t}/run` already accepts `parent_task_run_id` and creates the forked TaskRun. The fork UI reuses this endpoint as-is.
- `get_runs_summary` continues to filter to leaves. Forking creates new leaves alongside existing ones — they'll all show up.

## Frontend

### OpenAPI regeneration

After backend changes, run `app/web_ui/src/lib/generate_schema.sh`. The new endpoint will be typed automatically.

### Page-level orchestration

**File:** `app/web_ui/src/routes/(app)/dataset/[project_id]/[task_id]/[run_id]/run/+page.svelte`

Add an `ancestors` state and a load function next to the existing `load_run`:

```ts
let ancestors: TaskRunAncestor[] = []
let ancestors_chain_broken: boolean = false
let ancestors_load_failed: boolean = false

async function load_ancestors(
  req_project_id: string,
  req_task_id: string,
  req_run_id: string,
) {
  if (task?.turn_mode !== "multiturn") {
    ancestors = []
    return
  }
  try {
    const { data, error } = await client.GET(
      "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/ancestors",
      { params: { path: { project_id: req_project_id, task_id: req_task_id, run_id: req_run_id } } },
    )
    if (req_project_id !== project_id || req_task_id !== task_id || req_run_id !== run_id) return
    if (error) throw error
    ancestors = data?.ancestors ?? []
    ancestors_chain_broken = !!data?.chain_broken
    ancestors_load_failed = false
  } catch (_) {
    ancestors = []
    ancestors_chain_broken = false
    ancestors_load_failed = true
  }
}
```

Trigger `load_ancestors` after `task` is loaded **and** `run` is loaded (it depends on knowing the task's `turn_mode` and the leaf's existence). A simple reactive guard:

```ts
$: if (task && run && task.turn_mode === "multiturn") {
  load_ancestors(project_id, task_id, run_id)
}
```

Compute a positional mapping from trace index to run id (passed to TraceComponent):

```ts
$: forkable_run_ids = compute_forkable_run_ids(run?.trace ?? [], ancestors)
```

```ts
// Co-located helper (same file or a small adjacent .ts module).
function compute_forkable_run_ids(
  trace: TraceMessage[],
  ancestors: TaskRunAncestor[],
): (string | null)[] {
  // Returns an array same length as `trace`. For each user message at index i in
  // the trace, set the entry to the matching run_id (or null if no ancestor maps to it,
  // or if this is turn 1 — turn 1 user blocks are not forkable). For non-user messages, null.
  const result: (string | null)[] = trace.map(() => null)
  const user_indices = trace
    .map((m, i) => ({ m, i }))
    .filter(({ m }) => m.role === "user")
    .map(({ i }) => i)
  const total_turns = user_indices.length
  // Suffix-align ancestors onto user_indices. If ancestors.length < total_turns,
  // the first (total_turns - ancestors.length) user messages have no run id.
  const offset = total_turns - ancestors.length
  for (let k = 0; k < ancestors.length; k++) {
    const turn_index_k = ancestors[k].turn_index
    if (turn_index_k === 1) continue  // turn 1 not forkable
    const trace_idx = user_indices[offset + k]
    if (trace_idx !== undefined) result[trace_idx] = ancestors[k].run_id
  }
  return result
}
```

Fork state management on the page:

```ts
let fork_target: { turn_index: number; parent_run_id: string | null; prefill: string } | null = null

function on_fork(run_id: string, trace_index: number) {
  // Look up turn_index for this trace_index using ancestors. The forked run's parent
  // is the run at turn_index - 1 in ancestors (which may be null only if turn_index === 1,
  // already filtered out).
  const this_turn = ancestors.find((a) => a.run_id === run_id)
  if (!this_turn) return
  const parent = ancestors.find((a) => a.turn_index === this_turn.turn_index - 1)
  const trace = run?.trace ?? []
  const original_text = content_string_from_user_message(trace[trace_index]) ?? ""
  fork_target = {
    turn_index: this_turn.turn_index,
    parent_run_id: parent?.run_id ?? null,
    prefill: original_text,
  }
}

function cancel_fork() {
  // Composer component handles its own "dirty" confirmation before calling this.
  fork_target = null
}
```

`content_string_from_user_message` is a tiny local helper that mirrors what `trace.svelte` already does in `content_from_message`.

Render branching:

```svelte
{#if task?.turn_mode === "multiturn"}
  {#if ancestors_chain_broken}
    <div role="alert" class="alert alert-warning ...">
      Some earlier turns can't be forked because their run data is missing.
    </div>
  {/if}
  {#if ancestors_load_failed}
    <div role="alert" class="alert alert-warning ...">
      Couldn't load conversation history. Forking is unavailable.
    </div>
  {/if}

  <TraceComponent
    trace={run.trace ?? []}
    {project_id}
    markdown_content={true}
    {forkable_run_ids}
    truncate_at_trace_index={fork_target ? fork_target_trace_index : null}
    on_fork={on_fork}
  />

  {#if fork_target}
    <Composer
      mode="fork"
      {project_id}
      task_id={task.id}
      parent_task_run_id={fork_target.parent_run_id}
      prefill_text={fork_target.prefill}
      forked_turn_index={fork_target.turn_index}
      run_config_seed={...turn-K-run-config}
      on_cancel={cancel_fork}
      on_success={(new_id) => goto(`/dataset/${project_id}/${task_id}/${new_id}/run`, { replaceState: true })}
    />
  {:else}
    <!-- existing bottom composer (append mode) -->
  {/if}
{/if}
```

`fork_target_trace_index` is derived from `fork_target.turn_index` by indexing into `user_indices` (computed alongside `forkable_run_ids`). TraceComponent uses it to hide messages at or after that index.

### TraceComponent changes

**File:** `app/web_ui/src/lib/ui/trace/trace.svelte`

Add three new optional props:

```ts
export let forkable_run_ids: (string | null)[] | undefined = undefined
export let truncate_at_trace_index: number | null = null
export let on_fork: ((run_id: string, trace_index: number) => void) | undefined = undefined
```

Two behavior changes inside the `{#each trace as message, index}` loop:

1. **Hide truncated messages:**

```svelte
{#each trace as message, index}
  {#if truncate_at_trace_index === null || index < truncate_at_trace_index}
    <!-- existing block render -->
  {/if}
{/each}
```

2. **Render fork button in user block header** when `forkable_run_ids?.[index]` is non-null:

```svelte
<div class="collapse-title flex items-center justify-between cursor-pointer min-w-0" role="presentation">
  <span class="font-medium text-xs ... uppercase">{getRoleDisplayName(message.role)}</span>
  <div class="px-2 text-sm text-gray-600 ... grow {messageExpanded[index] ? 'hidden' : ''}">
    {getMessagePreview(message)}
  </div>
  {#if message.role === "user" && forkable_run_ids?.[index] && on_fork}
    <button
      type="button"
      class="btn btn-ghost btn-xs"
      aria-label="Fork from this turn"
      title="Fork from here"
      on:click|stopPropagation={() => on_fork(forkable_run_ids[index]!, index)}
    >
      <ForkIcon class="w-4 h-4" />
    </button>
  {/if}
</div>
```

`stopPropagation` on the button click is essential — without it, the click would also toggle the collapse.

The TraceComponent remains agnostic about "turns" — it works in `trace_index` space, and the page-level orchestrator translates between trace indices and turn indices.

### Composer changes

**File:** the composer component used by the multiturn run-detail page. From the explorer, the composer is currently inlined via a `FormContainer` + `RunInputForm` block in `+page.svelte` (no standalone composer component). For this project we extract it into `app/web_ui/src/lib/ui/conversation/multiturn_composer.svelte`.

Props on the new `MultiturnComposer.svelte`:

```ts
export let mode: "append" | "fork" = "append"
export let project_id: string
export let task_id: string
export let parent_task_run_id: string | null
export let prefill_text: string = ""
export let forked_turn_index: number | undefined = undefined
export let run_config_seed: RunConfigProperties | undefined = undefined  // defaults the picker
export let on_success: (new_run_id: string) => void | Promise<void>
export let on_cancel: (() => void) | undefined = undefined
```

Internal behavior:
- Wraps the existing `FormContainer` + `RunInputForm` + `RunConfigComponent` triad.
- In fork mode: prepends a context strip header (`↪ Forking turn N`); shows a Cancel button alongside Send.
- On mount in fork mode: textarea initialized with `prefill_text`, focus moved to end.
- Dirty-check on Cancel: if textarea content differs from `prefill_text`, show a DaisyUI `<dialog>` confirming discard. If clean, call `on_cancel` immediately.
- On Send: calls the existing `send_multiturn` with the relevant args; on success calls `on_success(new_id)`.

The append-mode composer behaves exactly as today (the existing inline implementation moves into this component). We don't break the existing flow.

### New icon

**File:** `app/web_ui/src/lib/ui/icons/fork_icon.svelte`

A small Svelte component following the convention of `tools_icon.svelte`, `database_icon.svelte`, etc. SVG path is a standard git-branch glyph (two circles joined by a forking line). Single-file, no props beyond `class`.

### File touch map

| File | Change |
|---|---|
| `libs/server/kiln_server/run_api.py` | Add `TaskRunAncestor`, `TaskRunAncestorsResponse`, `_walk_ancestors`, `_count_user_messages`, `get_run_ancestors` route. |
| `libs/server/kiln_server/test_run_api.py` | Tests for the new endpoint (cases below). |
| `app/web_ui/src/lib/api_schema.ts` | Regenerated. |
| `app/web_ui/src/routes/(app)/dataset/[project_id]/[task_id]/[run_id]/run/+page.svelte` | Ancestors load + state, `forkable_run_ids` computation, fork-target state, render switch between `MultiturnComposer` instances. Existing append-mode inline composer replaced by `<MultiturnComposer mode="append" .../>`. |
| `app/web_ui/src/lib/ui/trace/trace.svelte` | New props `forkable_run_ids`, `truncate_at_trace_index`, `on_fork`. Fork button in user block header. |
| `app/web_ui/src/lib/ui/conversation/multiturn_composer.svelte` | New component (extracted + extended for fork mode). |
| `app/web_ui/src/routes/(app)/dataset/[project_id]/[task_id]/[run_id]/run/multiturn_send.ts` | Used as-is. |
| `app/web_ui/src/lib/ui/icons/fork_icon.svelte` | New. |

## Error Handling

Backend:
- Task is single-turn → 400 from ancestors endpoint.
- Run id not found → 404 from ancestors endpoint.
- Missing parent during traversal → 200 with `chain_broken: true`, partial chain returned.
- Cycle detected → 200 with `chain_broken: true`, partial chain returned.
- `_MAX_ANCESTOR_DEPTH` exceeded → 200 with `chain_broken: true`, partial chain returned (matches cycle case).
- All other errors propagate normally via FastAPI exception handling.

Frontend:
- Ancestors fetch network/5xx error → set `ancestors_load_failed = true`, render warning banner, hide fork buttons everywhere. The page is otherwise usable; the bottom append-mode composer still works.
- `chain_broken: true` → render warning banner; fork buttons hidden for the unmappable prefix (handled naturally by `compute_forkable_run_ids`).
- Fork composer submit error → existing `send_multiturn` error path; inline error preserves text.

## Testing Strategy

### Backend (pytest)

**File:** `libs/server/kiln_server/test_run_api.py` — add a new test class `TestGetRunAncestors`:

- `test_single_turn_task_returns_400` — multiturn validation.
- `test_run_not_found_returns_404`.
- `test_single_turn_chain_returns_self_only` — a run with no parent: returns `[{run_id, turn_index: 1}]`, `chain_broken: false`.
- `test_three_turn_chain_returns_full_chain_root_to_leaf` — chain of 3 runs, leaf trace has 3 user messages, returns 3 ancestors with `turn_index` 1, 2, 3 and `chain_broken: false`.
- `test_missing_parent_mid_chain_sets_chain_broken` — chain of 3 runs, delete middle run from disk before calling endpoint; returns leaf + leaf's loadable suffix (in this case just the leaf, since the middle one is missing), `chain_broken: true`.
- `test_cycle_in_chain_is_handled` — construct two TaskRuns whose `parent_task_run_id` references each other; endpoint returns `chain_broken: true` without infinite loop.
- `test_chain_length_exceeds_trace_user_messages_is_chain_broken` — pathological: leaf trace has 1 user message but the parent chain is 3 long. Returns last `len(trace)` entries, `chain_broken: true`.

Use the existing test fixtures for projects/tasks/runs. Where parent files need to be "missing," delete the file from disk inside the test before calling the endpoint.

### Frontend (vitest)

Components touched / created get unit tests:

**`trace.svelte`:**
- Fork button renders on user blocks where `forkable_run_ids[i]` is non-null.
- Fork button absent on system / assistant / tool blocks.
- Clicking fork calls `on_fork(run_id, trace_index)` and does not toggle the collapse.
- `truncate_at_trace_index = K` hides messages at index ≥ K.

**`multiturn_composer.svelte`:**
- Append mode renders no Cancel button, no context strip; behaves like the old inline composer.
- Fork mode renders the context strip with `"Forking turn N"` and a Cancel button.
- Fork mode prefills the textarea.
- Cancel with clean input calls `on_cancel` immediately.
- Cancel with dirty input opens a confirmation dialog; only after confirming does `on_cancel` fire.
- Send POSTs with the supplied `parent_task_run_id` and calls `on_success` with the new id.

**Page-level smoke** (`+page.svelte`):
- For a multiturn run, mounts `<MultiturnComposer mode="append">` by default and switches to `mode="fork"` when `fork_target` is set.
- `compute_forkable_run_ids` produces the expected positional mapping for an unbroken 3-turn chain.
- Same helper with a broken-chain ancestor list (length-1, ancestors[0].turn_index = 3, but trace has 3 user messages) returns nulls for the first two user blocks and the run id for the third.

### Manual

- Create a multiturn task, run 4 turns. From turn 2's user block click fork; confirm truncation, prefill, default run config, and successful send → land on the new leaf with conversation length 2.
- From the original leaf (turn 4), fork the leaf's user block; confirm new sibling under turn 3 is created.
- Manually delete turn 2's file on disk. Reload turn 4. Confirm the warning banner shows; fork buttons appear only on turns 3 and 4 (the suffix).
- Confirm bottom composer still works in all scenarios.

## Out of Scope (Reaffirmed)

- Forking on assistant / tool blocks.
- Forking turn 1.
- Sibling navigation UI.
- Branch tree visualization.
- Streaming responses.
