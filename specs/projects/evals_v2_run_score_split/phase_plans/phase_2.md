---
status: complete
---

# Phase 2: `TraceIndex`

## Overview

The lookup that decides whether an eval job generates a trace or reuses one. It is the
piece that makes the whole project work, and the piece that has to be right under
concurrency: `AsyncJobRunner` runs 25 jobs at once, and two jobs sharing an
`(item, run_config)` but differing in `eval_config` must not both generate. That is the
exact spend this project exists to eliminate (architecture §2.1).

The index cannot be precomputed like the existing `already_run` set, because a trace
persisted by one job in a run must be visible to the next — both to another concurrent
job and to a retry after a scoring failure (functional spec §4.2, §4.3).

Standalone and unused until Phase 3: nothing constructs a `TraceIndex` in this phase.

## Steps

1. **New file `libs/core/kiln_ai/adapters/eval/trace_index.py`.**

   ```python
   TraceKey = Tuple[ItemSource, str, str]   # (source_type, source_id, run_config_id)


   def trace_key(item: ItemKey, run_config_id: ID_TYPE) -> TraceKey: ...


   class TraceIndex:
       def __init__(self, task: Task): ...
       async def get_or_create(
           self, key: TraceKey, generate: Callable[[], Awaitable[TaskRun]]
       ) -> tuple[TaskRun, bool]: ...
   ```

   **Deviation from architecture §2.2 — `TraceKey` is `tuple[ItemSource, str, str]`, not
   `tuple[str, ID_TYPE, ID_TYPE]`.** Same reasoning Phase 1 settled for
   `EvalItemSource.source_id`, and here it is load-bearing rather than stylistic: this
   tuple is a *dict key*. `ID_TYPE` is `Optional[str]`, so an id-less item and an id-less
   run config would produce `(source_type, None, None)` — one key that every id-less job
   collides on, silently handing them each other's traces. Making the nullability
   impossible in the key type moves the check to the one place that can do something
   about it: `trace_key()`, which raises. `ItemSource` (from `eval_splits`) rather than
   bare `str` for the first slot, so the key speaks the same vocabulary as `ItemKey` and
   a typo is a type error.

   `trace_key()` exists so Phase 3's call sites — which hold `item.id` and
   `task_run_config.id`, both `ID_TYPE` — have one place to convert, rather than each
   growing its own `assert is not None`. It rejects `""` along with `None`: an empty id
   collides exactly as a null one does.

2. **`TraceIndex.__init__` seeds from disk.**

   `self._task.runs(readonly=True, include_eval_generated=True)` — the only caller in the
   codebase that passes that flag (architecture §4). Skips runs with no `path` (unsaved)
   and runs with no key of their own: `_stored_trace_key()` returns None for a run with no
   `eval_source` or no `output.source.run_config_id`, since half a key can never be
   matched by a job. `setdefault` implements D8 "first wins" for duplicate traces arriving
   from sync.

   The default `include_intermediate_runs=False` rides along, so a trace that is the
   parent of another run would be invisible here. That is correct only because
   architecture §3.2 skips multi-turn items outright — an assumption load-bearing enough
   to be commented at the call, since breaking it produces no error, just permanent
   regeneration.

   **Paths, not objects** (architecture §2.2). The architecture argues this on memory,
   which does not survive contact with `ModelCache`: the seed's own `readonly=True` load
   already pins every TaskRun in the task, traces included, in a process-lifetime dict.
   The real benefit is freshness — reloading re-reads the record through the cache's
   mtime check, so an index built at the start of a long eval never serves a stale object
   and stays correct across cache invalidation. The comment in the code says that, not
   the memory story.

3. **`get_or_create` locks per key, using the existing `AsyncLockManager`.**

   Architecture §2.2 sketches the two-level locking by hand (`_registry_lock` guarding
   `_key_locks`). `kiln_ai.utils.lock.AsyncLockManager` already *is* that structure — a
   manager mutex held only for entry creation, a per-key `asyncio.Lock` held across the
   critical section — and additionally reclaims idle entries, so a long eval over
   thousands of items does not accumulate one dead `Lock` per key. Own an instance rather
   than using `shared_async_lock_manager`: the keys are this index's, and
   `vector_store_registry` / `lancedb_adapter` set the precedent for a private manager.

   Inside the lock: a cached path means load and return `(trace, False)`; otherwise
   `await generate()`, check the result, record the path, return `(run, True)`.

   Logging per architecture §8: `debug` on reuse, `info` on generation.

   A `generate` that raises records nothing and releases the lock, so the job's retry —
   or another job on the same key — tries again. That is architecture §8's "generation
   raises → nothing persisted" row.

4. **`_generated_path` enforces both halves of the generator's contract.**

   Persisted (`run.path is not None`) — the trace has to be durable before scoring is
   attempted (functional spec §4.1) — *and* stamped so that `_stored_trace_key(run)`
   equals the key it was generated for.

   The second half is not redundant with the first. The index files the run under the key
   the caller asked for, but the next process rebuilds the index from the run's own
   `eval_source` and `output.source.run_config_id`. If Phase 3 stamps the wrong item, or
   an adapter leaves `output.source.run_config_id` unset, everything is correct for the
   rest of that run and the trace is then never found again — the eval regenerates it on
   every future run, with no error and nothing to notice. That is the exact spend this
   project exists to remove, so the disagreement is caught where the mistake is made
   rather than inferred later from a bill.

5. **`_load_indexed` degrades instead of serving something wrong.**

   Two cases, both dropping the entry and falling through to generation:

   - The file is gone (`FileNotFoundError`) — sync, or an external delete that never met
     the API's 409 guard (§6). Architecture §8's posture for a missing trace everywhere
     else is to degrade, not to cascade.
   - The record at the path no longer files itself under this key — the write path's
     check, applied on read. Entries only ever enter `_paths` verified, so this needs a
     file to change identity in place, which only sync can do. Rare, but strictly worse
     than the write-side mismatch it mirrors: that one costs a regeneration, this one
     would score a judge against a different item's output and produce numbers that look
     entirely normal.

## Tests

New file `libs/core/kiln_ai/adapters/eval/test_trace_index.py` (architecture §9.2).

The fake generator builds its callable through `for_key(key)`, stamping the run it
persists with that key — the same shape as Phase 3, where the runner closes over the job
it is generating for. A generator that ignored the key and always stamped the same one
would put the task in a state production cannot produce (five runs all claiming one trace
key), and would make the mismatch tests below unwritable.

- Seed finds an existing eval-generated run: `get_or_create` returns it, `was_generated`
  is False, and `generate` is never awaited.
- Seed ignores a run with `eval_source is None` — an ordinary dataset run with the same
  run config is not reusable as a trace.
- Seed ignores an eval-generated run with no `output.source.run_config_id`.
- Duplicate seed entries: first wins (D8), asserted against the same iteration order the
  seed uses rather than against filesystem ordering.
- **Concurrency:** 25 concurrent `get_or_create` on one key call `generate` exactly once,
  and every caller gets the same run, with exactly one `was_generated=True`.
- Different keys generate concurrently: the generators rendezvous, so a per-key lock that
  had become a global one would deadlock the test rather than pass it slowly.
- A generated trace is reused by a later call on the same key without a re-seed — the
  live-index property Phase 3's retry path depends on.
- **A generated trace is found by a *fresh* `TraceIndex` over the same task** — the
  cross-run property the project's whole payoff rests on, and the one a single run's
  behavior can never reveal.
- Distinct keys get distinct traces, and each is still found on its own key by a later
  index.
- A generated run stamped with a different key raises, parametrized over a wrong run
  config, a wrong item id and a wrong source type; a generated run with no `eval_source`
  raises too, and leaves the key free for a correct retry.
- `generate` returning an unsaved run (no `path`) raises, and the key is not recorded.
- `generate` raising propagates and leaves the key clean, so a later call can generate.
- A trace file deleted after seeding regenerates instead of raising, and a trace file
  re-stamped after seeding is regenerated rather than served.
- `trace_key` raises on a None or empty `source_id` or `run_config_id`, and round-trips an
  `EvalItemSource` through `eval_item_key`.

Each of the behaviors that carry real risk — the per-key lock, its non-globalness, the
stamped-key postcondition, the vanished-file fallback and the read-path key check — was
mutation-checked: disabling it fails the test that claims it.
