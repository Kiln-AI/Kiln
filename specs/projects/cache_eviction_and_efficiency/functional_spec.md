---
status: complete
---

# Functional Spec: Cache Eviction and Efficiency

## Summary

Kiln's datamodel stores every record as a JSON file on disk. A process-wide cache (`ModelCache`) keeps parsed, validated pydantic models in memory, so repeat reads are fast. The cache has no size limit and keeps every field of every record it has seen. Tasks now hold tens of thousands of multi-turn runs, and the cache grows to many gigabytes.

This project bounds the cache's memory while keeping the common case fast, without changing the datamodel API that subclasses and consumers use. It does four things:

1. **Large fields load lazily.** Fields that can be huge (traces, run inputs and outputs, embeddings) are marked. The cache keeps the rest of each record in memory, and loads the marked fields from disk only when code reads them.
2. **One memory budget with eviction.** All cached data shares one budget. Large fields are evicted first; the small part of each record only when we really have to.
3. **The cache is on for app and server hosts, off for the library.** Library users can turn it back on.
4. **Change detection works on every platform.** The cache works on Linux for the first time.

It also fixes a few nearby inefficiencies that would otherwise undo the memory savings.

## How the cache works today

These facts were checked against the code and by measurement. They are the baseline for this project.

- The cache is a dict keyed by file path. Each entry holds the parsed model and the file's modified time (`st_mtime_ns`). It has no size limit and no eviction. There is no file watcher. Entries are removed only by `save_to_file`, `delete`, or when a read finds the file's modified time has changed.
- Only readonly loads (`load_from_file(..., readonly=True)`) add to the cache. A mutable load that hits the cache returns a deep copy of the cached model.
- **The cache is off on every Linux system.** Its startup check reads `f_timespec` from `os.statvfs()`. Python has never returned that field, so the check always fails. The cache has worked this way since it was added in Kiln-AI/Kiln#63 (Dec 2024). On Linux CI, 8 of the 20 tests in `test_model_cache.py` are skipped because of this.
- `load_from_file` validates a record, then assigns `parent` and `path`. Because models use `validate_assignment=True`, each assignment re-runs every model validator. This costs 5–23% of load time.
- Lookups by id (`from_id_and_parent_path`, `from_ids_and_parent_path`) read ids from the cache. On a cold cache they fully load every sibling.

Measured on this repo's datamodel, with synthetic runs:

| Run size | File size | Cached memory | First load | Read + JSON parse only | Editable copy from cache |
|---|---|---|---|---|---|
| 100 turns with reasoning | 345 KiB | 397 KiB | 1.4–4.0 ms | 0.7 ms | 1.5 ms |
| 10 turns | 38 KiB | 57 KiB | 0.7 ms | 0.08 ms | 0.46 ms |
| 1 turn | ~4 KiB | ~3.5 KiB | 0.5 ms | 0.03 ms | 0.4 ms |

Cached memory is about 1.15–1.5× the file size. 25k runs of 100 turns take about 10 GB in the cache. With input, output and trace removed, a run takes about 2 KB, so 25k runs take about 56 MB.

## Goals

- Bound the cache's memory for any dataset size.
- Keep list operations (dataset page, tag counts, filters, eval score pages) fast and served from memory.
- Read large fields from disk only for the few requests that need them (a run's detail page, the eval runner, export).
- No change to the datamodel API for subclasses or consumers, except a small number of call sites listed below.
- No change to the on-disk format and no change to API response schemas.
- No possible data loss from lazy loading.

## Non-goals

- File watching. It is out of scope (see "Out of scope").
- Detecting memory pressure from the operating system.
- A configurable budget.
- A saved index for faster cold starts. The first list load after startup still reads every run file.
- Changing how lookups by id work. They must not rely on folder names, because folders are sometimes copied around.

## 1. Where the cache is on

| Host | Cache |
|---|---|
| Desktop app (`app/desktop`, including the dev server) | On |
| `kiln_server` (REST server in `libs/server`) | On |
| `kiln_mcp` (MCP server in `libs/server`) | On |
| `kiln_ai` used as a library, including the `kiln_ai` CLI | Off by default |

- The library exposes a public function to turn the cache on or off for the process. It follows the same pattern as `set_strict_mode`. Library users who call it get the same behavior as the app: the same budget, lazy large fields and eviction.
- Each host turns the cache on in its own startup code. Nothing turns it on at import time.
- Turning the cache off clears it.

**Behavior change for library users:** today the library caches by default on macOS and Windows. After this project, library scripts that load the same records repeatedly will be slower unless they turn the cache on. Lookups by id in the library will fully load each sibling on every call.

**When the cache is off, nothing is lazy.** Every load returns a complete, ordinary pydantic model, exactly as an uncached load does today. Lazy fields exist only for records that came from the cache.

## 2. Detecting changed files

- The cache records three facts about each file when it loads it: modified time (`st_mtime_ns`), size (`st_size`) and file id (`st_ino`). Before serving a cached record, it stats the file. If any of the three changed, or the file is gone, the entry is dropped and the file is reloaded.
- The broken Linux check is removed. The cache works on all platforms.
- Kiln's own saves and deletes still clear the entry directly, as they do today.

**Accepted risk.** On older Linux kernels, file timestamps update only every few milliseconds, so two writes can share a timestamp. A change is missed only if all of these happen together:
- a program other than Kiln rewrites the file in place;
- the new content has exactly the same size;
- the write lands within a few milliseconds of the previous write;
- Kiln read the file in between.

Git replaces files rather than editing them in place, so the file id changes and git sync is covered. Macs on HFS+ (1-second timestamps) and FAT/exFAT drives (2-second timestamps) already carry a larger version of this risk today. Approved as acceptable.

## 3. Lazy large fields

### Marking fields

A datamodel author marks a field as large with an annotation on the field's type. The marker works on nested models too; for example, `TaskOutput.output` is marked inside `TaskRun.output`. No other change to the model class is needed.

Fields marked in this project:

| Model | Large fields |
|---|---|
| `TaskRun` | `trace`, `intermediate_outputs`, `input`, `output.output`, `repaired_output.output`, `world_episode.final_state` |
| `EvalRun` | `input`, `output`, `task_run_trace`, `judge_trace`, `intermediate_outputs`, `reference_answer` |
| `ChunkEmbeddings` | `embeddings` |

Every other field is a normal field.

### What a cached record holds

- When a record is loaded and added to the cache, it is fully validated, exactly as today. Every validator sees every field. Then the cache drops the values of its large fields from the cached copy. Empty values (`None`) are kept, since they cost nothing.
- "Not loaded" and "really `None`" are never confused. A dropped field is absent from the record, and the record tracks which fields are absent. A field that holds `None` keeps its real `None` value. `None` is never used as the marker for a dropped field. Reading a real `None` field never touches disk.
- The record keeps its normal fields and a small set of **summary values** computed from the large fields at load time (see below).
- The first time code reads any large field of a cached record, the cache reads the file once and restores **all** of that record's large fields. They stay in memory until evicted.
- The restored values are validated against the field's type. Model validators are not re-run; they already passed for this exact file (same modified time, size and file id).

### Summary values

These are small values derived from large fields. Code that only needs to know something small about a large field uses them instead of reading the field.

- They are read-only properties, computed from the full record when it loads. On a record built in memory (not loaded from disk), they compute from the live fields.
- They are not saved to disk, not included in `model_dump`, and not added to API responses or the OpenAPI schema.

The values added in this project:

| Model | Value | Replaces |
|---|---|---|
| `TaskRun` | `input_preview` (first 100 characters) | `RunSummary.format_preview(run.input)` |
| `TaskRun` | `output_preview` (first 100 characters of `output.output`) | `RunSummary.format_preview(run.output.output)`, and the "No output" check in `repair_status_display_name` |
| `TaskRun` | `trace_length` (number of messages) | `len(run.trace)` in the `/chain` endpoint |
| `TaskRun` | `has_thinking` | the body of `has_thinking_training_data()`, used by the finetune "thinking" filter |
| `EvalRun` | `judge_trace_length` (number of messages) | `bool(eval_run.judge_trace)` in `_split_judge_trace` (eval results endpoint) |

Where an existing method reads a large field only to compute one of these, the method is changed to use the summary value, so its callers don't change (for example `has_thinking_training_data()`). The architecture step confirms the full list of call sites.

Presence checks on large fields in validators (for example `self.task_run_trace is None` in `EvalRun.validate_output_fields`) need no change. Validators run on the full record at load time.

### Guarantees (no data loss)

These must hold for every model with large fields. Each is covered by tests.

1. **Saving writes every field.** `save_to_file` on any record, including a copy of a cached record, writes every field. Pydantic silently leaves out a missing field when it dumps a model (checked), so the base class must restore large fields before any dump.
2. **Serialization includes every field.** `model_dump`, `model_dump_json` and FastAPI responses, including nested models, always include large fields. A full-run API response is identical to today's.
3. **Editable copies are complete.** `mutable_copy()`, and a mutable `load_from_file` that hits the cache, return a model with every field present.
4. **Other copies and comparisons behave.** `model_copy`, equality and `repr` on a cached record behave as if all fields were present. Equality may load large fields to compare them.
5. **No silent fallbacks.** If a large field can't be restored (the file was deleted, or it no longer parses), reading it raises a clear error that names the file. It never returns `None` or an empty value in place of real data.

### Records whose file changed after caching

A caller can hold a cached record while its file changes on disk (git sync, another Kiln instance, a manual edit), then read a large field.

Today, the held record stays a complete copy of the old version. An editable copy made from it is also the old version, and saving that copy overwrites the newer file.

Behavior after this project:
- **Reading a large field returns the value from the file as it is now.** If the large fields were evicted, the old values are gone, so the record's normal fields can be from the old version while its large fields are from the new one. A debug log notes the mismatch. This mix is the one new risk, and it is accepted. It is small, because large fields (input, output, trace) are almost never edited after a run is created; edits are to tags, ratings and repairs.
- **An editable copy made from such a record is rebuilt from the current file.** It never mixes versions. Saving it no longer overwrites newer changes on disk with old data, which is an improvement on today.
- New reads of the record through `load_from_file` see the change and reload it, as they do today.

### Hidden disk reads

Reading a large field on a cached record can now read the file. This happens only when code reads a large field; list operations, which use normal fields and summary values, never do. This is the cost of bounded memory. Where it shows up:
- Code that reads large fields of every run in a big dataset (eval runner, JSONL export) reads each file once per pass, if its large fields were evicted. Datasets whose large fields fit in the budget stay in memory, as today.
- The read is a blocking file read wherever the field is accessed, including inside `async` handlers. Loading records in `async` handlers already blocks today, so this adds no new kind of blocking.

## 4. Memory budget and eviction

- **Budget:** min(2 GB, 20% of physical RAM), computed once at startup. Not configurable. It covers everything in the cache.
- **What counts:** each cached record's estimated memory, split into its normal part and its large-field part. Estimates come from file size, scaled to match measured in-memory size. They are approximate; a benchmark checks the estimate stays within about 50% of real memory for typical runs.
- **Eviction order** when the cache is over budget:
  1. Large fields, least recently used first. Evicting a record's large fields keeps its normal part and summary values.
  2. Only when no large fields remain cached: whole records, least recently used first.
- **Cheap check on every add.** The cache keeps a running total of its estimated size, updated as entries are added, restored, evicted or removed. Adding data costs one addition and one comparison with the budget. Eviction work happens only when the total goes over budget. It then evicts down to 90% of the budget, so the next adds don't each trigger eviction. Recency is tracked in an ordered structure, so reads and evictions take constant time per entry.
- There is no background thread in the library.
- Evicting data never affects a caller that already holds a value. A caller holding a trace list keeps it; the cache just stops pointing to it.
- A single record whose large fields exceed the whole budget is served, but its large fields are not kept after the read.

## 5. Efficiency fixes

### 5a. Validators run once per load

`load_from_file` passes `parent` and `path` in a way that does not re-run model validators. Validators that need the parent or path still get them. Load results must be identical to today's, including errors for invalid files.

### 5b. Bulk callers that don't edit use readonly loads

Bulk loads that return editable copies defeat lazy loading: each copy needs every field, so every large field of every run is read from disk and held in memory at once. Bulk callers that load many runs and don't edit them switch to `readonly=True`. Known callers:
- `DatasetSplit` creation (`dataset_split.py`)
- `eval_configs_score_summary` (`eval_api.py`)
- the copilot `spec_with_copilot` flow and the eval builder's single-turn and multi-turn pipelines (`copilot_utils.py`)
- any others found during implementation

Callers that really edit keep mutable loads: `edit_tags`, which only touches the selected runs, and the JSONL export, which needs large fields but only for the split's runs. A caller wrongly switched to readonly raises `ReadOnlyMutationError` at once, so mistakes fail loudly.

`Task.runs()` keeps `readonly=False` as its default, so the library API doesn't change.

### 5c. Add-example dialog

The web UI's add-example dialog calls `GET /runs` with no limit. It downloads every full run, traces included, just to auto-select one example and show a picker. The call lives in `fetch_task_sample_candidates` (`task_sample_example.ts`), which four places use: the add-example dialog, the task sample selector, the spec builder, and the data guide's existing-run picker.

It changes to request only the 100 newest runs (`GET /runs?limit=100`). The auto-select rules don't change: the most recent five-star run, else the most recent run.

Visible change (approved):
- the picker lists at most the 100 newest runs;
- the five-star auto-select looks only within those 100.

The `GET /runs` endpoint itself is not changed, since external API callers rely on it.

### 5d. Eval score pages

Marking `EvalRun`'s large fields (above) means score summaries and the eval worker's progress counts stop holding copies of traces and outputs. The functions that build score summaries are reviewed to confirm they read only normal fields and summary values. Any that read a large field just to check presence switch to a summary value.

## Out of scope

- **File watching**, on any platform. It can't replace the file check without losing correctness:
  - macOS delivers change events late.
  - Windows drops events during large changes.
  - Linux needs one watch per run folder and hits the system's watch limits.
  - Synced folders and mounts give unreliable events.
- **Memory-pressure detection.**
- **Idle shrink** (dropping cached data when the app is unused). The budget alone bounds memory.
- **A configurable budget.**
- **RAG progress endpoint** loading every embedding (`progress.py`). Marking `ChunkEmbeddings.embeddings` as large already stops its vectors from staying cached.
- **Lookups by id from folder names.**
- **A "do not cache this class" option.** No model on the field list needs it.

## Compatibility

- On-disk format: unchanged.
- API response schemas and the OpenAPI document: unchanged.
- Datamodel API: unchanged for subclasses and consumers, apart from the call sites named in sections 3 and 5.
- Library behavior: the cache defaults to off (see section 1).

## Testing and verification

- **Lazy fields:** unit tests for each guarantee in section 3. Cover save, dump, nested dump, FastAPI responses, `mutable_copy`, `model_copy`, equality, a changed file and a deleted file, for both a top-level large field and a nested one (`TaskOutput.output`).
- **Field marking:** for every model on the field list, a test round-trips a record through cache, eviction and restore, and checks it is identical to a fresh load.
- **Budget:** tests with a small test budget check the eviction order and the size accounting, and that a record larger than the budget is still served.
- **Memory benchmark:** loads a few thousand large synthetic runs with the cache on, checks the estimated cache size stays under budget, and checks real memory is in line with the estimate.
- **Speed benchmarks:** warm list loads are no slower than today. First loads are no slower than today; the validator fix in 5a should make them 5–23% faster.
- **Change detection:** tests for a changed size, a replaced file (new file id) and a changed modified time. The skip guards in `test_model_cache.py` are removed, so all cache tests run on Linux.
- **Platforms:** cache tests pass locally on Linux (the agent's environment) and in the normal CI run, which uses Ubuntu.
  - CI today runs the Python tests only on Ubuntu, plus one Windows job scoped to a single test file.
  - This project adds a macOS and Windows run of the full Python test suite that does not run on every push. It runs:
    - when a release is created, the same trigger the desktop release build uses;
    - when started by hand from the Actions tab, on any branch.
  - Pushes keep running Ubuntu only, as today.
  - The macOS and Windows run uses Python 3.13, the desktop app's version, to keep it short. The workflow's steps are adjusted so they run on all three operating systems.
  - Before merge, a maintainer starts it by hand on the PR branch.
  - The cache and datamodel tests must pass on macOS and Windows. The suite has never run on macOS, and only one file has run on Windows, so other tests may fail there. Failures outside this project's code are listed in the PR, not fixed in this project.
- **Hosts:** tests check the cache is on after each host's startup (desktop app, `kiln_server`, `kiln_mcp`), off by default in the library, and that the library switch works.
- **Add-example dialog:** UI tests for the auto-select rules, plus a manual check in the app.
