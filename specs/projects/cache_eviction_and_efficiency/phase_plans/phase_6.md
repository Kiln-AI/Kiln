---
status: complete
---

# Phase 6: Bulk Callers and the Add-Example Dialog

## Overview

Phase 5 put lazy large fields on the real datamodel. An editable copy of a cached record needs every field, so a bulk load that returns editable copies reads every evicted run file back and holds every trace in memory at once. This phase switches the bulk callers that don't edit to `readonly=True` (functional spec 5b), records the call-site audit, switches the `/chain` endpoint's lookups to readonly (which needs a new `readonly` option on `from_id_and_parent_path`), and makes `fetch_task_sample_candidates` request only the 100 newest runs (5c).

Two findings from the audit change the shape of the 5b list:

- The copilot `spec_with_copilot` flow does edit runs: `find_multi_turn_chain_leaves` and `find_single_turn_batch_runs` return the batch's runs, and the save flow tags and rates the reviewed ones. They scan the task readonly and return editable copies of only the batch's runs, so callers don't change and the scan no longer copies every run.
- `VectorStoreLoader.iter_llama_index_nodes` loads every `ChunkEmbeddings` of every document as editable copies and only reads them. It switches to readonly.

## Steps

1. **`libs/core/kiln_ai/datamodel/basemodel.py`**: `from_id_and_parent_path` gains `readonly`, passed to both of its `load_from_file` calls, and its docstring says what it does.

   ```python
   @classmethod
   def from_id_and_parent_path(
       cls: Type[PT], id: str, parent_path: Path | None, readonly: bool = False
   ) -> PT | None: ...
   ```

2. **`libs/core/kiln_ai/datamodel/dataset_split.py`**: `build_split_contents` uses `task.runs(readonly=True)`.

3. **`libs/core/kiln_ai/adapters/vector_store_loaders/vector_store_loader.py`**: `chunked_document.chunk_embeddings(readonly=True)`.

4. **`libs/server/kiln_server/run_api.py`**:
   - `_walk_run_chain`: `TaskRun.from_id_and_parent_path(..., readonly=True)`.
   - `get_run_chain`: the leaf lookup passes `readonly=True`.
   - `delete_runs`: the per-id lookup passes `readonly=True`.

5. **`app/desktop/studio_server/eval_api.py`**: `get_eval_configs_score_summary` uses `task.runs(readonly=True)`.

6. **`app/desktop/studio_server/eval_builder_api.py`**: the judge-traces producer passes `readonly=True` to `TaskRun.from_ids_and_parent_path`.

7. **`app/desktop/studio_server/utils/copilot_utils.py`**:
   - `find_multi_turn_chain_leaves` and `find_single_turn_batch_runs`: `[run.mutable_copy() for run in task.runs(readonly=True) if target_tag in (run.tags or [])]`. Docstrings say the runs are editable copies.
   - `delete_multi_turn_batch_chains`: `task.runs(include_intermediate_runs=True, readonly=True)`.

8. **`app/web_ui/src/lib/utils/task_sample_example.ts`**:
   - `export const TASK_SAMPLE_CANDIDATE_LIMIT = 100`.
   - `fetch_task_sample_candidates` passes `query: { limit: TASK_SAMPLE_CANDIDATE_LIMIT }`. Its doc comment says the choice is among the task's newest runs, and that `candidate_filter` applies within them.

## Call-site audit (5b)

Every `.runs(`, `all_children_of_parent_path(`, `from_ids_and_parent_path(` and `from_id_and_parent_path(` call in `libs/` and `app/desktop/` outside tests, plus the other bulk loads of a class with large fields (`chunk_embeddings(`, `load_from_file` on `TaskRun` / `EvalRun`).

### Classes with large fields (`TaskRun`, `EvalRun`, `ChunkEmbeddings`)

| Call site | Outcome |
|---|---|
| `datamodel/dataset_split.py` `build_split_contents` (`task.runs()`) | Switched. Only filters runs and collects ids. |
| `datamodel/dataset_split.py` `missing_count`, `_get_runs` | Already readonly. |
| `datamodel/eval_splits.py` split resolution | Already readonly. |
| `datamodel/basemodel.py` generated child methods (`all_children_of_parent_path`) | Generic; passes the caller's `readonly`. |
| `adapters/fine_tune/dataset_formatter.py` JSONL export (`task.runs(include_intermediate_runs=True)`) | Kept mutable, as the spec decides: the export reads every field of the split's runs. |
| `adapters/prompt_builders.py`, `adapters/eval/eval_runner.py` (three), `adapters/eval/trace_index.py` index build | Already readonly. |
| `adapters/eval/trace_index.py` `_load_indexed` (`TaskRun.load_from_file`) | Kept mutable: one file per eval item, returned to the eval runner as the trace it scores, which reads its trace anyway. |
| `adapters/vector_store_loaders/vector_store_loader.py` (`chunk_embeddings()`) | Switched. Reads embeddings only. |
| `adapters/rag/rag_runners.py` (two), `adapters/rag/progress.py` | Already readonly. |
| `cli/commands/migrate_eval_runs.py` (`load_from_file`, `all_children_of_parent_path_with_errors`) | Kept: a migration that rewrites records. The CLI runs with the cache off, so nothing is lazy there. |
| `kiln_server/run_api.py` `_walk_run_chain` (`from_id_and_parent_path`) | Switched. Reads ids and parent ids. |
| `kiln_server/run_api.py` `get_run_chain` leaf lookup | Switched. Reads the leaf's trace and ids. |
| `kiln_server/run_api.py` `get_run_chain` `has_children`, `_collect_cascade_delete_runs`, `get_runs`, `get_runs_summaries`, tag counts | Already readonly. |
| `kiln_server/run_api.py` `task_and_run_from_id` | Kept mutable: shared by `get_run` and the repair and delete endpoints, which edit or serialize every field. |
| `kiln_server/run_api.py` `delete_runs` per-id lookup | Switched. Reads `eval_source` and deletes; the cascade's ancestors were already readonly. |
| `kiln_server/run_api.py` `run_task` parent lookup | Kept mutable: one run whose trace is read anyway, handed to `adapter.invoke`. |
| `kiln_server/run_api.py` `run_task` "parent still exists" check | Switched. Only checks the run exists. |
| `kiln_server/run_api.py` `edit_tags` (`from_ids_and_parent_path`) | Kept mutable: edits and saves the selected runs. |
| `kiln_server/run_api.py` `update_run` | Kept mutable: dumps every field to build the edited run. |
| `kiln_server/feedback_api.py` `_run_from_ids` | Kept mutable: one run, used as the parent of a new `Feedback`. |
| `studio_server/eval_api.py` `get_eval_configs_score_summary` (`task.runs()`) | Switched. Reads ids and ratings. |
| `studio_server/eval_api.py` `runs_in_filter` | Already readonly (its callers pass `readonly=True`). |
| `studio_server/eval_api.py` `load_task_children_by_id`, `eval_input_references`, every `eval_config.runs(...)` | Already readonly. |
| `studio_server/eval_api.py` judge-trace endpoint (`EvalRun.from_id_and_parent_path`) | Kept mutable: one record, whose large field it returns. |
| `studio_server/eval_builder_api.py` judge-traces producer (`from_ids_and_parent_path`) | Switched. Reads traces, inputs and outputs. |
| `studio_server/utils/copilot_utils.py` `find_multi_turn_chain_leaves`, `find_single_turn_batch_runs` | Switched the scan to readonly; returns editable copies of the batch's runs only, because `spec_with_copilot` tags and rates them. |
| `studio_server/utils/copilot_utils.py` `delete_multi_turn_batch_chains` | Switched. Reads tags, parents and annotations, and deletes. |
| `studio_server/utils/copilot_utils.py` `delete_single_turn_batch_runs` | Switched. Reads tags and annotations, and deletes. |
| `studio_server/finetune_api.py`, `studio_server/agent_api.py`, `jobs/workers/eval.py` | Already readonly. |
| `kiln_server/provenance_api.py` | Already readonly. |

### Classes without large fields

Kept as they are. A mutable load of these copies one small record, and lazy loading doesn't apply to them.

- `kiln_server`: `spec_api.py` (`Spec`, `Eval`), `feedback_api.py` (`Feedback`), `task_api.py` (`Task`), `document_api.py` (`RagConfig`, `ExtractorConfig`, `ChunkerConfig`, `EmbeddingConfig`, `VectorStoreConfig`, `RerankerConfig`, `Document`, `Extraction`; the bulk `Document.from_ids_and_parent_path`).
- `kiln_ai`: `tools/rag_tools.py`, `tools/tool_registry.py`, `tools/kiln_task_tool.py`, `adapters/provider_tools.py`, `adapters/rag/progress.py` (`VectorStoreConfig`), `adapters/chunkers/semantic_chunker.py`, `adapters/eval/eval_runner.py` (`World`), `adapters/adapter_registry.py` (`Skill`, `World`), `datamodel/eval.py` (`configs`).
- `studio_server`: `code_tool_api.py`, `tool_api.py`, `skill_api.py`, `eval_api.py` (`Eval`, `EvalInput`, `World`, `configs`), `data_gen_api.py`, `prompt_optimization_job_api.py`, `finetune_api.py` (`Finetune`, `DatasetSplit`), `world_api.py`.

## Tests

`libs/core/kiln_ai/datamodel/test_basemodel.py`:
- `test_from_id_and_parent_path_readonly`: with the cache on, `readonly=True` returns the cached instance, which rejects assignment; the default still returns a separate editable copy.
- `test_from_id_and_parent_path_readonly_caches_scanned_siblings`: a readonly lookup on a cold cache leaves every scanned sibling cached, so the next lookup reads no file.

`libs/core/kiln_ai/datamodel/test_dataset_split.py`:
- `test_build_split_contents_reads_no_large_fields`: on cached, evicted runs, a high-rating split holds the same ids as with the cache off, and no run file is re-read.

`libs/core/kiln_ai/adapters/vector_store_loaders/test_vector_store_loader.py`:
- `test_iter_llama_index_nodes_restores_only_matching_embeddings`: with two documents, one per embedding config, a pass over evicted embeddings gives the same nodes and re-reads one file.

`libs/server/kiln_server/test_run_api.py`:
- `test_get_chain_reads_only_the_leaf_large_fields`: on a cached, evicted three-turn chain, `GET /chain` returns the cache-off response and re-reads only the leaf's file.
- `test_bulk_delete_reads_no_large_fields`: deleting cached, evicted runs removes their folders and re-reads no file.

`app/desktop/studio_server/test_eval_api.py`:
- `test_eval_configs_score_summary_reads_no_large_fields`: on cached, evicted golden runs and eval runs, the endpoint returns the cache-off response and re-reads no file.

`app/desktop/studio_server/test_eval_builder_api.py`:
- `TestJudgeTraces.test_happy_path_full_stream` extended: the bulk loader is called with `readonly=True`.

`app/desktop/studio_server/utils/test_copilot_utils.py`:
- `test_find_batch_runs_copies_only_the_batch` (parametrized over the multi-turn and single-turn finders): on a task with other cached, evicted runs, the finder returns editable runs that save, and re-reads only the batch's files.
- `test_delete_multi_turn_batch_chains_reads_no_large_fields`: deleting a cached, evicted batch removes every turn and re-reads no file.

`app/web_ui/src/lib/utils/task_sample_example.test.ts` (new):
- the request asks for `limit=100`;
- the most recent five-star run is auto-selected;
- with no five-star run, the most recent run is auto-selected;
- with no runs, or none passing `candidate_filter`, the result asks for manual entry;
- `candidate_filter` limits the candidates;
- a request error is thrown.
