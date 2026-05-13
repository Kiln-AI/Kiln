---
status: complete
---

# Functional Spec: Multiturn Trace Forking

## Goal

Allow a user viewing a multiturn conversation to **fork** from any user turn — replacing that turn's user message with a new one and continuing inference from there. The fork produces a new `TaskRun` whose parent is the run that immediately preceded the forked turn, creating a sibling branch under that parent. Existing branches remain intact.

The data model already supports branches (`TaskRun.parent_task_run_id`); v1 of the multiturn feature deferred the UI to expose them. This project ships that UI plus the backend traversal needed to associate trace blocks with their originating `TaskRun` ids.

## Vocabulary

- **Trace**: the OpenAI-format message list stored on `TaskRun.trace`. Index 0 is the system message (sourced from task config); subsequent entries are user/assistant/tool messages.
- **Turn**: one user message + the assistant's response to it. One turn corresponds to exactly one `TaskRun`.
- **Conversation chain**: an ordered list of `TaskRun`s from root (turn 1) to leaf (most recent turn), linked by `parent_task_run_id`.
- **Forking**: creating a new `TaskRun` whose `parent_task_run_id` equals the run at turn K-1, with a user message that differs from the original turn K. The original turn K and any descendants of it remain on disk; the fork becomes a sibling branch.
- **Chain broken**: a parent file referenced by `parent_task_run_id` is missing or unloadable. Walking stops at that point.

## User Story

> I'm reviewing a multiturn run at turn 5 and realize my question on turn 3 was poorly phrased. I want to retry from there with a different question, without losing the existing chain.

The user clicks a "fork" affordance on turn 3's user block. The page visually truncates to turns 1–2, and an inline composer appears with turn 3's original user text prefilled. The user edits the text and clicks Send. A new `TaskRun` is created with `parent_task_run_id` = the turn-2 `TaskRun` id. The page navigates to the new leaf's run page, where the conversation now reads turns 1, 2, (new) 3.

## Behavior

### When fork is available

Fork is available on **user blocks only**, for multiturn tasks. Specifically:

| Position | Fork button shown? | Notes |
|---|---|---|
| System block (trace[0]) | No | Sourced from task config, not a `TaskRun`. |
| Turn 1 user block | **No** | Forking turn 1 = a brand-new conversation. Users should start a new conversation via the `/run` page instead. |
| Turns 2..N-1 user blocks (interior) | **Yes** (when ancestor chain unbroken at that point) | Creates a sibling under the prior turn's run. |
| Turn N user block (leaf) | **Yes** | Creates a sibling of the leaf, under the same parent as the leaf. This is *not* redundant with the existing bottom composer (which appends a new turn N+1). Forking the leaf user block lets the user replace their most recent message instead of adding another turn. |
| Assistant blocks | No | Out of scope for v1 (deferred to a future trace-editor feature). |
| Tool call/result blocks | No | Same as assistant. |

If the parent chain is broken above turn K, fork buttons are hidden for turns 1..K (and only available from turn K+1 onward, since those have a resolved ancestor).

### Fork interaction (inline composer)

1. User clicks fork on turn K's user block.
2. Conversation visually truncates: turns 1..K-1 remain visible; turn K and everything after it are hidden.
3. An inline composer appears immediately below turn K-1 with:
   - The original turn K user text prefilled.
   - Run config picker, defaulted to **turn K's original run config** (i.e. the run config of the run we are about to replace).
   - Send button.
   - Cancel button (closes the inline composer, re-expands the full trace).
4. While the inline composer is open, the existing bottom composer (used for appending a new turn) is **hidden** to avoid two competing composers.
5. Only one inline composer can be open at a time. Clicking fork on another user block while one is open replaces the active fork target (with confirmation if the composer has unsaved edits — see Edge Cases).
6. On Send:
   - Frontend POSTs to `/api/projects/{p}/tasks/{t}/run` with `parent_task_run_id` = turn K-1's `TaskRun` id and `plaintext_input` = composer text.
   - Server validates as today (multiturn task, parent exists). Adapter produces the new `TaskRun` and persists it.
   - Frontend navigates to `/dataset/{p}/{t}/{new_run_id}/run` (using SvelteKit `goto` with `replaceState: true` is fine — matches the existing composer behavior).
7. On Send failure: same error UX as the existing composer (inline error above the composer; user text preserved; explicit retry).

### Backend — parent-chain traversal

A new endpoint exposes the ordered ancestor chain for a given leaf run:

- **`GET /api/projects/{p}/tasks/{t}/runs/{run_id}/ancestors`**
- Returns: `{ ancestors: [{run_id: str, turn_index: int}, ...], chain_broken: bool }`
  - `ancestors` is ordered **root → leaf** and **includes the requested run itself** as the final entry.
  - `turn_index` is 1-based (turn 1 = root, turn N = leaf).
  - `chain_broken` is `true` if while walking parents we encountered a `parent_task_run_id` that could not be loaded from disk (file missing / unreadable). In that case, the returned `ancestors` list contains only the runs reachable from the leaf back to (and not including) the missing parent — i.e. the suffix of the chain whose linkage is intact.
- 400 if the task is not multiturn.
- 404 if the requested run id itself is not found.
- The endpoint does not 5xx on missing parents — broken chains are normal failure modes, surfaced via `chain_broken`.

The endpoint is consumed by the run-detail page on load (one call per page render) and used to map each user block in the trace to its `TaskRun` id.

### Trace-to-run mapping

The mapping is positional:

- Each `TaskRun` in the chain corresponds to exactly one turn (one user + one assistant exchange).
- Walking the chain from root to leaf produces an ordered list of `TaskRun` ids of length `T`. The trace on the leaf contains the system message at index 0 followed by `T` turns' worth of messages.
- Turn K's user block → run at chain position K.
- If `chain_broken: true`, the first user blocks (those preceding the break) are *not* mappable to a run id. Their fork buttons are hidden. The system block always has no associated run.

If the leaf trace's turn count and the returned `ancestors` length disagree (an inconsistency we don't expect, but tolerating defensively), the UI treats the deficit as a broken chain — fork buttons are shown only for turns where a one-to-one mapping is unambiguous (suffix-aligned from the leaf).

### Multiple branches / siblings

Forking produces sibling branches under a shared parent. The data model already tolerates this. Out of scope for v1:

- Surfacing siblings as alternative branches in the run-detail UI (no "view other branch" navigation).
- Listing or counting siblings.

Dataset list pages already show only leaves; each branch's leaf appears as its own entry. Users navigate between branches by opening different leaves from the dataset list — same as today.

## API Changes

### New endpoint

Already specified above:

`GET /api/projects/{p}/tasks/{t}/runs/{run_id}/ancestors`

### Existing endpoints — no change

- `POST /api/projects/{p}/tasks/{t}/run` already accepts `parent_task_run_id` and produces a forked `TaskRun`. No new behavior needed for forking — the existing path is reused.
- `runs_summaries` continues to filter to leaves only. Forking adds new leaves under shared parents; both branches show up as separate entries in the list.

## UI Changes

### Run-detail page for multiturn (`/dataset/{p}/{t}/{run_id}/run`)

- On load, fetch the ancestor chain via the new endpoint alongside the existing run load.
- For each user block rendered in the trace, attach the corresponding `TaskRun` id from the ancestor chain (positional mapping).
- Render a fork affordance (icon button) on each eligible user block per the table above.
- Inline composer behavior as specified.

### `/run` page

Unchanged. Forking turn 1 is not a flow we support; users start a new conversation via the existing entry.

### Visual design

Detailed in the UI design step. Functional requirements:

- The fork affordance must be discoverable but unobtrusive (it shouldn't dominate the user block).
- The fork affordance lives inside the **expanded** user block (below the message content), not in the collapsed header. The header is a click-to-expand target; putting an interactive button there competes with the expand click. Users discover the fork affordance by expanding a user turn — the same gesture they use to inspect the turn before forking.
- The truncated state must clearly communicate "this is a fork in progress" — not look like a normal continuation.
- The original user text must be visible in the composer (prefilled, editable, clearable).
- Send/Cancel must be unambiguous.

## Error Handling

Backend:
- Ancestors endpoint, task not multiturn → 400.
- Ancestors endpoint, run not found → 404.
- Ancestors endpoint, missing parent mid-walk → 200 with `chain_broken: true` and a truncated `ancestors` list.
- Fork submission (existing `/run` endpoint): same errors as today (404 if parent not found, 400 if task not multiturn, 422 on invalid task config).

Frontend:
- Inline composer submission fails → inline error, user text preserved, retry available.
- Ancestor chain fetch fails (network / 5xx) → render the conversation without fork affordances and show a non-blocking warning. The page is still usable.
- Inline composer cancel with unsaved edits → confirmation prompt before discarding.

## Edge Cases

- **Forking the leaf user block.** Creates a sibling of the current leaf under the leaf's parent. The original leaf remains intact on disk. After Send, we navigate to the new sibling's run page; the original leaf is reachable from the dataset list page.
- **Forking turn 1.** Not supported in v1 — no fork button shown. Users wanting to start fresh use the `/run` page.
- **Forking a run that itself has siblings.** Fine. The new run becomes a third sibling. The data model allows N branches per parent.
- **Broken parent chain.** Fork buttons hidden for the affected prefix. A small banner / warning indicates the chain is broken. The composer at the bottom (for normal continuation) still works.
- **Trace length mismatch with ancestor count.** Treat as broken chain, hide fork buttons for the unmapped prefix.
- **Opening fork while a fork is already open.** If the active composer has unsaved edits, confirm before switching; otherwise switch immediately.
- **Concurrent edits** (rare — multiple windows): the existing `/run` endpoint already handles its own concurrency. No additional locking for the ancestor endpoint (read-only).
- **System message change after a fork.** The task's system message comes from the task config at run time, not from the parent's trace. A fork therefore uses the *current* task config's system message, which may differ from the parent's. This matches existing continuation semantics (turn N+1 today already uses the current task config). Not a new concern.

## Out of Scope (v1)

- Forking on assistant or tool blocks (deferred to a future "trace editor" that allows manual editing of arbitrary turns without re-inference).
- Forking turn 1 (use `/run` to start a new conversation).
- Sibling navigation UI on the run-detail page.
- Visual branch tree / graph view of all branches under a task.
- Inline editing of the assistant or tool messages.
- Deleting a branch.
- Counting / listing branches under a parent.
- Streaming responses (not yet supported anywhere in multiturn).

## Acceptance Criteria

1. From a multiturn run-detail page with an N-turn chain (N ≥ 2), each user block at turns 2..N shows a fork button. Turn 1 does not.
2. Clicking fork on turn K truncates the visible conversation to turns 1..K-1, opens an inline composer prefilled with turn K's original user text, defaults the run config to turn K's original config, and hides the bottom composer.
3. Submitting the inline composer creates a new `TaskRun` with `parent_task_run_id` = turn K-1's run, and navigates to the new run's detail page.
4. Forking the leaf's user block (turn N) creates a sibling under turn N-1's run; the original leaf remains on disk and reachable.
5. The ancestors endpoint returns the correct ordered chain for any leaf, including chains of length 1.
6. Deleting a parent run file by hand on disk results in `chain_broken: true` and a partial chain; fork buttons hide for the unmappable prefix; the rest of the UI continues to work.
7. The ancestors endpoint rejects requests for single-turn tasks with 400.
8. A failed fork submission preserves the user's edited text and offers retry.

## Open / Deferred

- A trace-editor feature for manually editing assistant / tool messages without re-inference. Mentioned to keep design extensible; not in v1.
- Surfacing sibling branches in the run-detail UI.
