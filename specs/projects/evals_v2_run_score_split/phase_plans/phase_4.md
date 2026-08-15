---
status: complete
---

# Phase 4: Server surfaces

## Overview

Phase 3 made new `EvalRun`s pointer records: `scored_run_id` set, `input` / `output` /
`task_run_trace` / `task_run_usage` all None. Every read path that still reads those
fields therefore renders blank today. This phase is the other half of that change — the
read side that makes the new records render again.

Four things land:

1. **`EvalRunWithTrace`** — the joined view model `get_eval_run_results` returns instead
   of a bare `EvalRun`. Legacy records fill it from their own inline fields, pointer
   records from the referenced `TaskRun`. One shape for the frontend (architecture §5.1).
2. **The usage rollup** in `get_run_config_eval_scores` reads `TaskRun.usage` from the
   joined trace, falling back to `task_run_usage` for legacy records (architecture §5.2).
3. **Delete protection** — 409 on deleting a `TaskRun` with `eval_source` set, single and
   bulk (architecture §6), plus the PATCH decision below.
4. **`api_schema.d.ts` regen** and the one frontend page that reads the changed response.

Score aggregation (`compute_score_summary`, `get_eval_configs_score_summary`,
completeness math) reads only fields that stayed on `EvalRun` and is untouched
(architecture §5.3).

### Two notes carried into this phase

**Skip records need `input` resolved from the source item.** A pre-generation skip has
neither an `input` (Phase 3 stopped writing one, per functional spec §3.3) nor a
`scored_run_id` to join through, so the join as specced in architecture §5.1 leaves it
blank forever. This phase resolves `input` from `dataset_id` / `eval_input_id` when the
join yields nothing — see "the input ladder" below.

**`PATCH /runs/{run_id}` must reject `eval_source`.** Decision recorded below.

### Decision: PATCH rejects `eval_source`

`update_run` deep-merges an arbitrary `Dict[str, Any]` into the run, so a client can set
any field, `eval_source` included. Before this phase that was harmless-in-shape. After
it, `eval_source` is load-bearing twice over: it hides a run from `Task.runs()` (Phase 1)
and now blocks deletion. An arbitrary PATCH could therefore make an ordinary dataset run
both invisible and **permanently undeletable** — the delete guard reads the same field
the PATCH just set, so there is no way back through the API.

So `update_run_util` rejects a top-level `eval_source` key with **400**, matching the
existing precedent in `task_api.create_task` (`"Task ID cannot be set by client."`). The
field is written by exactly one thing — the eval runner, in-process — and no frontend
call site sends it.

Narrow on purpose: this rejects only `eval_source`, not the general "PATCH can write any
field" shape, which is pre-existing and out of scope here. It is rejected because this
phase is what makes it a one-way door.

The guard tests for the *key*, so it also refuses `{"eval_source": null}` — which
`deep_update` would treat as a clear. That direction is the load-bearing one: an escape
hatch out of the delete guard would be the guard's own bypass. The accepted cost, which
D16 already sanctions, is that a trace orphaned by deleting its eval (`delete_eval`
removes the `EvalRun`s but not the `TaskRun`s they scored) stays on disk: invisible to
the dataset, unflaggable, and removable only from the filesystem.

## Steps

### 1. `app/desktop/studio_server/eval_api.py` — `EvalRunWithTrace`

New response model, replacing `List[EvalRun]` on `EvalRunResult.results`:

```python
class EvalRunWithTrace(BaseModel):
    """An eval's scores for one item, plus the trace those scores were computed over.

    The trace lives on a TaskRun for new records and inline on the EvalRun for legacy
    ones; this resolves whichever applies so the caller sees one shape.
    """

    eval_run: EvalRun
    input: str | None
    output: str | None
    task_run_trace: str | None
    task_run_usage: Usage | None
```

`task_run_trace` stays a JSON string rather than becoming the structured
`list[dict]` that `TaskRun.trace` is, because that is the shape legacy records have and
the point of the model is that both modes look alike. Pointer records are serialized with
`json.dumps(..., indent=2, ensure_ascii=False)` — the repo rule, which the equivalent
call in the V1 runner (`eval_runner.py:350`) was missing. That one is fixed here too
rather than copied, since it is the call that writes every legacy trace.

**Known tradeoff: a legacy record ships its trace twice.** The model embeds the whole
`EvalRun`, whose deprecated `input` / `output` / `task_run_trace` / `task_run_usage` are
still serialized, so for a legacy record each appears both on the wrapper and on
`eval_run`. A V1 `full_trace` eval's results page therefore carries two copies of its
largest field per row. Pointer records are unaffected (the inner fields are all None),
and Phase 5 migrates only V2 records, so for V1 projects this is permanent rather than
transitional.

Accepted rather than fixed. A trimmed inner model would fork `EvalRun` into two shapes
for one response, and a `@field_serializer` that dropped the fields would make the
generated OpenAPI schema describe a payload the API doesn't send — a worse problem than
the bytes. The duplication is what "one shape for the caller" costs on the legacy side,
and the legacy side is frozen.

### 2. `eval_api.py` — `resolve_eval_run_traces(task, eval_runs)`

Module-level, so it is testable without the HTTP layer:

```python
def resolve_eval_run_traces(
    task: Task, eval_runs: List[EvalRun]
) -> List[EvalRunWithTrace]:
```

Bulk loads only, no per-record directory scans (`from_ids_and_parent_path` is the
existing bulk accessor, one scan per call):

1. Load every referenced `scored_run_id` as a `TaskRun`. A short count of what came back
   catches dangling references, which get one `logger.warning` per request — not per
   record. Given delete protection, a missing trace means data was lost out of band, or
   the project was imported with `package-project --exclude-task-runs` (architecture
   §4.1); silently rendering blanks would hide both.
2. Resolve each record through `EvalRunWithTrace.from_own_fields` or `.from_scored_run` —
   the two rules live as classmethods next to the fields they fill.
3. `_fill_missing_inputs_from_source_items` collects the records whose `input` is still
   None and loads their source items — `TaskRun`s for `dataset_id`, `EvalInput`s for
   `eval_input_id`.

Every bulk load in the module goes through `load_task_children_by_id`, generic over the
child model so the same guard covers `TaskRun` and `EvalInput`. It short-circuits an
empty id set, which is not a micro-optimization: `from_ids_and_parent_path` reads any
child whose id isn't already cached in order to check it, so calling it with nothing to
find would read the entire directory off disk.

Per-record resolution:

- **`scored_run_id` None** (legacy inline, and pre-generation skips): the record's own
  `input` / `output` / `task_run_trace` / `task_run_usage`.
- **`scored_run_id` set, trace found**: `trace.input`, `trace.output.output`
  (**never `repaired_output`** — functional spec §5.2 — repair can happen after
  scoring), `json.dumps(trace.trace)`, `trace.usage`.
- **`scored_run_id` set, trace missing**: all four None. The score still renders and
  still aggregates; only the drill-through is gone (functional spec §5.3). Never raises.

**The input ladder.** `input` alone gets a third rung: when the two rules above leave it
None, it is resolved from the *source item* named by `dataset_id` / `eval_input_id`.
That covers the pre-generation skip records this phase's carried note is about, and
dangling pointers get it for free — the source item's input is a true statement of what
was fed in either way. The other three fields have no such fallback: nothing but the
trace can say what the model produced.

Source item input text:

| Item | Text |
|---|---|
| `TaskRun` | `run.input` |
| `EvalInput`, single-turn | `data.user_message.text` |
| `EvalInput`, multi-turn synthetic | `data.first_message.text`, or None |

Multi-turn is not hypothetical here: `incompatible_input_shape` on a multi-turn item is
one of the two ways a pre-generation skip is written (`eval_runner._is_multi_turn`), so
it is exactly the row that would otherwise render blank.

### 3. `eval_api.py` — `get_eval_run_results` returns the joined model

The split filter is unchanged; the returned list is wrapped:

```python
results = resolve_eval_run_traces(task, matching_runs)
```

### 4. `eval_api.py` — usage rollup in `get_run_config_eval_scores`

`eval_run.task_run_usage` becomes the resolved trace's usage. `TaskRun.usage`, not
`cumulative_usage`: it already accumulates across every LLM call and, unlike
`MessageUsage`, carries `total_llm_latency_ms`, which this summary reports (functional
spec §5.1).

The loop visits many evals, so the traces are bulk-loaded **once for the endpoint**
(`scored_trace_usage_for_run_config`) — a per-eval load would be one directory scan per
eval, over a `runs/` directory that now holds every eval trace too. That needs the set of
eval configs before the main loop, so the "which config does this eval report on" rule
moves to a module-level helper used by both passes:

```python
def summary_eval_config(eval: Eval) -> EvalConfig | None:
    """The eval config a summary reports on: the only one, or the explicitly chosen one."""
```

**Only the usage is kept, not the TaskRuns.** The pre-pass returns
`Dict[str, Usage | None]`. Traces are the large field (architecture §2.2) and usage is
the only thing read off them here, so holding whole runs for the life of the request
would pin every trace body in memory for a handful of numbers. For the same reason the
pre-pass narrows the id set toward what the loop will actually look up: evals whose spec
is archived are filtered out of `evals` once, up front, so both passes see the same list;
and records with `skipped_reason` set are excluded, since the loop `continue`s past them
before it reads usage at all.

**One of the loop's filters is deliberately not applied: test-split membership.** A
record for this run config that belongs to the train split still has its trace read and
parsed, then discarded. Applying that filter would mean resolving every eval's test split
in the pre-pass *as well as* in the loop, and split resolution is the more expensive of
the two — it is a filter over the whole dataset, against one extra `TaskRun` parse per
out-of-split record whose result is dropped immediately rather than retained. The
transient cost is accepted; the retained set is already exact.

`eval_run_task_usage` then answers per record: `task_run_usage` when there is no
`scored_run_id` (what legacy records carry), the trace's `usage` when there is one, and
None when the pointer dangles — so a missing trace contributes nothing to the average
rather than counting as a zero. "Trace missing" and "trace recorded no usage" collapse to
the same `None`, which is right: both mean there is nothing to report.

### 5. `libs/server/kiln_server/run_api.py` — delete protection

One shared message, three call sites (two delete paths and the PATCH guard read the same
field, so the reason is worded once):

```python
EVAL_TRACE_DELETE_MESSAGE = (
    "This run can't be deleted because it's needed for an eval."
)
```

- `delete_run`: `409` when `run.eval_source is not None`. 409 not 400 — the request is
  well-formed; the resource state forbids it.
- `delete_runs` (bulk): the same check per run, reported through the **existing**
  `failed_runs` / `error` collection rather than aborting the batch, so the non-eval
  runs in a mixed selection are still deleted and the user learns why the rest were not.
  Raising the `HTTPException` inside the existing `try` would technically work — the bare
  `except Exception` would catch it — but it would stringify as `"409: ..."` into a 500
  body, so the check is explicit and records the plain message.

  The reason collection changes shape while we're here: `last_error` kept only whichever
  failure came last, which was survivable when "Run not found" was the only reason and is
  not now — a mixed batch would report "Run not found" about runs that are on disk and
  merely protected. It becomes a list of distinct reasons in first-seen order, joined
  into the same `error` string, so the response schema is unchanged.

No reverse reference scan (D16): the flag on the TaskRun is sufficient and holds whether
or not an EvalRun currently points at it.

### 6. `run_api.py` — `update_run_util` rejects `eval_source`

400, per the decision above. In `update_run_util` rather than the endpoint body: it is
the merge point, and the guard should hold for any future caller of it.

### 7. Frontend — `run_result/+page.svelte`

The rows are now `EvalRunWithTrace`. `input` and `output` come off the wrapper; scores,
`reference_answer`, `intermediate_outputs`, `skipped_reason` and `skipped_detail` come
off `result.eval_run`. `displayed_result` (the thinking dialog) follows the same move.

`input` and `output` are rendered as `?? ""`: both are now legitimately null (a dangling
trace reference, or a skip whose dataset item is gone), and Svelte 4 stringifies `null`
into four literal characters in the DOM.

No other visual change: the same three blocks render from the same values.
`reference_answer` stays on the inner record — it is a legacy-only field with no pointer-mode counterpart
(new records carry `reference_data` instead), so there is nothing to join for it.

### 8. `api_schema.d.ts` regeneration

`generate_schema.sh`, then `check_schema.sh` must pass.

## Tests

`app/desktop/studio_server/test_eval_api.py` — the existing results tests move to the
nested shape (`data["results"][0]["eval_run"]["id"]`), plus new classes covering the
join.

**The resolver and its helpers, called directly** (`TestResolveEvalRunTraces`). The
endpoint tests below exercise the same join end to end; these pin what the endpoint
can't isolate:

- **How many times the directory is read.** A spy on `TaskRun.from_ids_and_parent_path`
  over a mixed set: exactly two calls, one for the pointer records' traces and one for
  the skips' source items. This is the invariant that silently rots into an N+1, and its
  cost is a scan over every eval trace in the project.
- The same spy on `scored_trace_usage_for_run_config` over **two** evals: exactly one
  call. That function exists *only* to make this true, and moving the load back inside
  the loop passes every other test in the suite.
- The pre-pass leaves out records with `skipped_reason`, which the rollup drops before it
  reads usage.
- An all-legacy result set reads nothing at all — the empty-set guard, asserted rather
  than assumed.
- `eval_item_input_text` over all four item shapes, parametrized, including a multi-turn
  item with no first message (the one shape with nothing to show, and reachable, since
  multi-turn is what pre-generation skips are for).
- `eval_run_task_usage` for legacy, pointer, and dangling-pointer records.
- `summary_eval_config` for one config, several with no default, and several with one
  named.
- A dangling reference logs exactly one warning for the request, not one per record.

**Trace resolution, through the endpoint**

- A pointer record resolves `input` / `output` / `task_run_trace` / `task_run_usage` from
  the referenced TaskRun, and a legacy record resolves them from its own fields — the two
  compared against each other in one test rather than asserted separately, which is the
  "frontend sees one shape" claim.
- `output` is the TaskRun's `output.output` when it also has a `repaired_output`. The
  repair is deliberately a *different* string, so the assertion fails if the field is
  swapped.
- A dangling `scored_run_id` returns 200 with all four fields None, and the record's
  scores still present.
- `task_run_trace` for a pointer record parses back to the TaskRun's messages, rather
  than being asserted as an opaque string.

**Skip records (the carried note)**

- A pre-generation skip over a TaskRun item resolves `input` from the dataset item.
- A pre-generation skip over a single-turn EvalInput resolves `input` from its user
  message, and over a multi-turn EvalInput from its first message — the multi-turn case
  being the one the runner actually writes.
- A skip whose source item is itself missing returns 200 with `input` None.
- A *scoring* skip (skip with `scored_run_id`) resolves from its trace like any pointer
  record, not from the source item.

**Usage rollup**

- Pointer record: the mean usage reports the TaskRun's `usage`, including
  `total_llm_latency_ms` — the field `cumulative_usage` would have dropped.
- Legacy record: the mean usage still reports `task_run_usage`.
- Mixed: both contribute, and a pointer record whose trace is missing contributes
  nothing rather than raising.

**Characterization.** No new test: `compute_score_summary` is not called from any code
this phase changes, and the existing `test_score_summary_*` tests are already pure
characterization over it. A duplicate would assert the same thing about the same
untouched function.

`libs/server/kiln_server/test_run_api.py`

- Deleting an eval-generated run → 409, with the run still on disk afterwards (a 409
  that deleted anyway would pass a status-only assertion).
- Deleting an ordinary run still succeeds (the guard is scoped to the flag).
- Bulk delete over a mix: the ordinary runs are gone, the eval-generated one is still on
  disk and named in `failed_runs`, with the reason in the error.
- Bulk delete over two *different* failure kinds reports both reasons, not just the last.
- PATCH with `eval_source` → 400, and the run on disk is unchanged. No `task_from_id`
  patch in that test: the guard has to refuse before the run is loaded at all.
- PATCH with `{"eval_source": null}` → 400 as well. This is the load-bearing half —
  `deep_update` treats null as a clear, so allowing it would be a way out of the delete
  guard.
- PATCH with an unrelated field still succeeds on a run that *is* an eval trace — the
  rejection is about the field, not about the run.

`app/web_ui` — no new frontend tests; the page has none today and the change is a field
rename. `npm run check` covers the type change.
