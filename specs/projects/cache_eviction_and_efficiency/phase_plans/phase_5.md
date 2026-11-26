---
status: complete
---

# Phase 5: Mark the Real Fields

## Overview

Phase 4 built the lazy-field machinery and tested it on small test models. This phase puts it on the real datamodel: `TaskRun`, `TaskOutput`, `EvalRun`, `ChunkEmbeddings` and `WorldEpisode` gain `LazyFieldsMixin`, their large fields get `LargeField` markers, and the summary values the spec lists are added. The list-view consumers that read a large field only to compute something small switch to those summary values, so list operations on a cached task never read run files. The eval score functions are reviewed (5d) to confirm they read only normal fields. The OpenAPI schema must not change.

## Steps

1. **`libs/core/kiln_ai/datamodel/lazy_fields.py`**: add the preview helper that summary values and `RunSummary` share.

   ```python
   def preview_text(text: str | None, max_length: int = 100) -> str | None:
       """`text` cut to `max_length` characters, with "…" when cut; None stays None."""
   ```

2. **`libs/core/kiln_ai/datamodel/task_output.py`**: `class TaskOutput(LazyFieldsMixin, KilnBaseModel)`; `output: Annotated[str, LargeField()] = Field(...)`.

3. **`libs/core/kiln_ai/datamodel/world.py`**: `class WorldEpisode(LazyFieldsMixin)`; `final_state: Annotated[dict[str, JsonValue] | None, LargeField()] = Field(...)`; summary value `has_final_state -> bool` (`self.final_state is not None`).

4. **`libs/core/kiln_ai/datamodel/task_run.py`**: `class TaskRun(LazyFieldsMixin, KilnParentedModel, KilnParentModel, parent_of=...)`; mark `input`, `intermediate_outputs` and `trace`. `output.output`, `repaired_output.output` and `world_episode.final_state` come from the nested classes. Summary values:
   - `input_preview -> str | None`: `preview_text(self.input)`
   - `output_preview -> str | None`: `preview_text(self.output.output)`, `None` when the output is empty
   - `trace_length -> int`: `len(self.trace) if self.trace else 0`
   - `has_thinking -> bool`: `self.thinking_training_data() is not None`
   - `has_thinking_training_data()` returns `self.has_thinking`.

5. **`libs/core/kiln_ai/datamodel/eval.py`**: `class EvalRun(LazyFieldsMixin, KilnParentedModel)`; mark `input`, `output`, `reference_answer`, `intermediate_outputs`, `task_run_trace` and `judge_trace`. Summary value `judge_trace_length -> int`.

6. **`libs/core/kiln_ai/datamodel/embedding.py`**: `class ChunkEmbeddings(LazyFieldsMixin, KilnParentedModel)`; mark `embeddings`.

7. **`libs/server/kiln_server/run_api.py`**:
   - `RunSummary.format_preview` calls `preview_text`.
   - `RunSummary.from_run` uses `run.input_preview` and `run.output_preview`.
   - `repair_status_display_name` uses `run.output_preview` for its "No output" and "Repair needed" checks.
   - `_position_chain_turns` uses `run.trace_length`.

8. **`app/desktop/studio_server/eval_api.py`**: `_split_judge_trace` sets `has_judge_trace` from `eval_run.judge_trace_length > 0`.

9. **`libs/core/kiln_ai/adapters/eval/trace_index.py`**: `_stored_trace_key` checks `not run.world_episode.has_final_state`.

10. **Eval score functions (5d).** Review the score summary builders in `eval_api.py` (`compute_score_summary`, `run_config_eval_scores`, `scored_trace_usage_for_run_configs`, `get_eval_configs_score_summary`, `count_human_evals`), `eval_input_references`, and the eval worker's `_compute_state_sync` (`jobs/workers/eval.py`). Any that reads a large field only to test whether it's set switches to a summary value.

11. **Shared test fixtures in the root `conftest.py`**: `evict_large_values` (a callable that drops every entry's large values from the test's cache, keeping the records) and `large_field_restores` (a spy on `lazy_fields._restore`). `test_lazy_fields.py` switches from its local copies to these.

12. **Schema**: run `app/web_ui/src/lib/check_schema.sh`; it must show no diff.

## Tests

`libs/core/kiln_ai/datamodel/test_lazy_fields_datamodel.py` (new):
- `test_plans_for_marked_classes`: plan paths for `TaskRun`, `TaskOutput`, `WorldEpisode`, `EvalRun` and `ChunkEmbeddings` match the component doc's table.
- `test_round_trip_through_cache_eviction_and_restore` (parametrized over a `TaskRun` with every large field set, including `repaired_output` and a `world_episode` with a final state, a legacy inline `EvalRun`, and `ChunkEmbeddings`): the cached record is detached; after eviction, reads, `model_dump`, `model_dump_json`, equality and `mutable_copy` match a cache-off load, with one file read.
- `test_task_run_detach_scrubs_validated_values`: `_last_validated_input` / `_last_validated_output` are gone from a detached run.
- `test_save_evicted_run_changes_only_the_edit`: a mutable copy of an evicted run, with its tags edited and saved, gives a file equal to the original apart from the tags.
- `test_task_run_summary_values_match_live_values` (parametrized: empty, short, exactly-100-character and long input and output; no trace and a trace; no intermediate outputs, `reasoning`, `chain_of_thought`, and unrelated keys; no world episode, an episode with a final state, and one without): each summary value on a detached run equals the cache-off value, with no file reads.
- `test_eval_run_judge_trace_length` (`None`, empty, and a three-message judge trace).
- `test_summary_values_not_serialized`: no summary value name appears in a detached run's `model_dump()` or in the JSON schema.
- `test_serialization_schema_unchanged` (parametrized over the five classes, both modes): the JSON schema equals that of a twin class built from the same fields without the mixin or markers.
- `test_dataset_filters_read_no_large_fields`: `ThinkingModelDatasetFilter` and `ThinkingModelHighRatedFilter` on an evicted run give the cache-off answer with no file reads.

`libs/server/kiln_server/test_run_api.py`:
- `test_run_summary_format_preview` extended: exactly 100 characters is kept whole.
- `test_run_summary_repair_status_display_name` updated for `output_preview`.
- `test_run_summary_reads_no_large_fields`: `RunSummary.from_run` on an evicted run equals the cache-off summary and reads no files.
- `test_position_chain_turns_reads_no_large_fields`: chain positions from evicted runs equal the cache-off positions, with no file reads.
- `test_run_endpoints_match_cache_off_after_eviction`: `GET /runs`, `GET /runs/{id}` and `runs_summaries` on a task whose cached runs were evicted return the same JSON as with the cache off.

`libs/core/kiln_ai/adapters/eval/test_trace_index.py`:
- `test_stored_trace_key_reads_no_large_fields`: on evicted world runs, with and without a final state, the key equals the cache-off key and no file is read.

`app/desktop/studio_server/test_eval_api.py`:
- `test_split_judge_trace_reads_no_large_fields`: on an evicted `EvalRun`, `has_judge_trace` is correct, the copy dumps `judge_trace: null` and every other field in full, and the flag reads no file.
- `test_score_summaries_read_no_large_fields`: `compute_score_summary` and `run_config_eval_scores` over evicted legacy inline eval runs and evicted scored traces read no files.
