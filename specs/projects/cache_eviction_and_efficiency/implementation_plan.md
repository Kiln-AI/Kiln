---
status: complete
---

# Implementation Plan: Cache Eviction and Efficiency

Each phase ends with every project check passing (`uv run ./checks.sh --agent-mode`). See [architecture.md](architecture.md) and the [component docs](components/) for the details.

## Phases

- [x] Phase 1: **Cache on/off and change detection.**
  - `FileIdentity` (modified time, size, file id), with the broken Linux check removed.
  - `set_model_cache_enabled` / `model_cache_enabled`, off by default.
  - The `model_cache_enabled` test fixture. Skip guards removed, and existing tests that need the cache take the fixture.
  - The desktop app, `kiln_server` and `kiln_mcp` turn the cache on.
  - The macOS and Windows CI job, run on release and by hand.
- [x] Phase 2: **Validate once per load (5a).** `_validate_file_data`; the `Eval` current-config migration switched to the loading context; the old-vs-new characterization test over every fixture file.
- [x] Phase 3: **Memory budget and eviction of whole records.** Size estimates, least-recently-used order, the min(2 GB, 20% RAM) budget with physical-RAM detection, the cheap over-budget check, and eviction down to 90%. No lazy fields yet.
- [x] Phase 4: **Lazy fields core.** `lazy_fields.py`: marker, plan, summary values, detach, resolve, restore, serializer, schema override, copies and equality. The cache's large-value store, the load integration, and `mutable_copy` rebuilding from a changed file. Tested on small test models only.
- [ ] Phase 5: **Mark the real fields.**
  - Markers and the mixin on `TaskRun`, `TaskOutput`, `EvalRun`, `ChunkEmbeddings` and `WorldEpisode`, plus their summary values.
  - Consumers switched: `RunSummary`, `/chain`, `_split_judge_trace`, `trace_index`, `has_thinking_training_data`.
  - Eval score functions reviewed (5d).
  - `check_schema.sh` shows no diff.
- [ ] Phase 6: **Bulk callers and the add-example dialog.** Bulk callers that don't edit switch to readonly loads, with the call-site audit recorded (5b). `fetch_task_sample_candidates` requests the 100 newest runs (5c).
- [ ] Phase 7: **Benchmarks and docs.** Memory benchmark and warm list-load benchmark; docs and agent guidance updated for the library default and the switch; a manual macOS and Windows CI run on the branch. Docstrings for the public names in `model_cache.py`: the `ModelCache` class, the budget constants (`MAX_BUDGET_BYTES`, `RAM_FRACTION`, `FALLBACK_BUDGET_BYTES`, `EVICTION_TARGET_FRACTION`) and `stats()`.
- [ ] **Phase 8: Backlog.** Review open backlog items with the user, then close or dismiss each through the standard phase flow.
