---
status: complete
---

# Phase 1: Backend — ancestors endpoint

## Overview

Add a new `GET /api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/ancestors`
endpoint that walks `TaskRun.parent_task_run_id` from leaf to root and returns
the ordered chain (root→leaf, leaf inclusive) plus a `chain_broken` flag.

This endpoint is consumed by the frontend run-detail page (Phase 2) to map each
trace user-message back to its originating `TaskRun.id`, which in turn powers
the fork affordance.

The traversal must defensively handle: missing parents on disk, runaway depth,
cycles, and pathological cases where the trace user-message count is fewer than
the resolved chain length. All these surface as `chain_broken: true` with a
suffix of the chain returned (never a 5xx).

## Steps

1. **`libs/server/kiln_server/run_api.py`** — add response models near
   `RunTaskRequest`:

   ```python
   class TaskRunAncestor(BaseModel):
       run_id: str = Field(
           description="The TaskRun id at this turn position in the chain."
       )
       turn_index: int = Field(
           description=(
               "1-based turn index in the leaf's conversation (turn 1 = root, "
               "turn N = leaf). Derived from the leaf's trace user-message count."
           )
       )

   class TaskRunAncestorsResponse(BaseModel):
       ancestors: list[TaskRunAncestor] = Field(
           description=(
               "Ordered root-to-leaf, includes the requested run itself as the "
               "final entry. If chain_broken is true, the list contains only the "
               "intact suffix from the leaf back to (and excluding) the break point."
           )
       )
       chain_broken: bool = Field(
           description=(
               "True if while walking parents we encountered a parent_task_run_id "
               "that could not be loaded (file missing/unreadable), a cycle, the "
               "depth guard tripped, or the chain length exceeded the leaf trace's "
               "user-message count."
           )
       )
   ```

2. **`libs/server/kiln_server/run_api.py`** — add private helpers near the top
   of the module:

   ```python
   _MAX_ANCESTOR_DEPTH = 1000

   def _walk_ancestors(leaf: TaskRun, task_path: Path | None) -> tuple[list[TaskRun], bool]:
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

   def _count_user_messages(trace) -> int:
       if not trace:
           return 0
       return sum(1 for m in trace if m.get("role") == "user")
   ```

3. **`libs/server/kiln_server/run_api.py`** — add route handler in
   `connect_run_api`:

   ```python
   @app.get(
       "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/ancestors",
       summary="Get Run Ancestors",
       tags=["Runs"],
       openapi_extra=ALLOW_AGENT,
   )
   async def get_run_ancestors(
       project_id: Annotated[str, Path(...)],
       task_id: Annotated[str, Path(...)],
       run_id: Annotated[str, Path(...)],
   ) -> TaskRunAncestorsResponse:
       task = task_from_id(project_id, task_id)
       if task.turn_mode != TurnMode.multiturn:
           raise HTTPException(400, "Ancestors are only available for multiturn tasks.")
       leaf = TaskRun.from_id_and_parent_path(run_id, task.path)
       if leaf is None:
           raise HTTPException(404, f"Run not found: {run_id}")
       chain, chain_broken = _walk_ancestors(leaf, task.path)
       turn_count = _count_user_messages(leaf.trace)
       if len(chain) > turn_count and turn_count > 0:
           chain = chain[-turn_count:]
           chain_broken = True
       ancestors = [
           TaskRunAncestor(
               run_id=str(r.id),
               turn_index=turn_count - (len(chain) - 1 - i),
           )
           for i, r in enumerate(chain)
       ]
       return TaskRunAncestorsResponse(ancestors=ancestors, chain_broken=chain_broken)
   ```

   Note: `turn_count == 0` is a degenerate trace; we still return the chain as
   ancestors but with `turn_index` reflecting `0 - offset` for each — instead
   surface this as a broken-chain edge: if `turn_count == 0` and `len(chain) > 0`
   we treat the entire chain as unresolved (return empty ancestors, broken=true).

4. **`app/web_ui/src/lib/api_schema.ts`** — regenerate via
   `app/web_ui/src/lib/generate_schema.sh` after backend code lands.

## Tests

Add a new `TestGetRunAncestors` test class (or a flat group of tests with the
naming pattern `test_get_ancestors_*`) at the end of
`libs/server/kiln_server/test_run_api.py`:

- `test_get_ancestors_single_turn_task_returns_400` — request against a
  single-turn task returns 400.
- `test_get_ancestors_run_not_found_returns_404` — multiturn task but
  unknown run id returns 404.
- `test_get_ancestors_single_turn_chain_returns_self_only` — a multiturn task
  with one run (no parent), trace has 1 user message → ancestors length 1 with
  `turn_index: 1`, `chain_broken: false`.
- `test_get_ancestors_three_turn_chain_returns_full_chain_root_to_leaf` —
  build root→mid→leaf with leaf trace containing 3 user messages; assert
  ordered ancestors with `turn_index` 1/2/3 and `chain_broken: false`.
- `test_get_ancestors_missing_parent_mid_chain_sets_chain_broken` — build
  root→mid→leaf, delete `mid` from disk, call endpoint on leaf →
  `chain_broken: true`, ancestors only contains the leaf, leaf `turn_index: 3`.
- `test_get_ancestors_cycle_in_chain_is_handled` — manually save a run whose
  `parent_task_run_id` points back to itself (or two runs pointing at each
  other). Endpoint returns `chain_broken: true` and terminates without infinite
  loop.
- `test_get_ancestors_chain_longer_than_trace_user_messages_is_broken` —
  3-run chain but leaf trace only has 1 user message. Returns 1 ancestor
  (the leaf, `turn_index: 1`), `chain_broken: true`.
