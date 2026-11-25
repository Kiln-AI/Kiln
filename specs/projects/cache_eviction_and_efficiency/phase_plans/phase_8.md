---
status: complete
---

# Phase 8: Backlog

## Overview

The user decided the five open backlog items. Three are closed in this phase and two are dismissed.

Closed:

- **The `Eval` `current_config_id` migration leaves an un-migrated eval in the cache.** The migration lists the eval's configs with `self.configs(readonly=True)`. That re-reads the eval's own file readonly, twice (once in `_load_children_of_parent_path`, once in `iterate_children_paths_of_parent_path`). The recursion guard skips the migration for that inner copy, and with the cache on the inner copy is cached. So a later readonly load of the eval returns `current_config_id=None`, and every readonly config cached in that pass has the un-migrated copy as its `parent` (also after a readonly first load, where the outer load does overwrite the eval's own entry). The fix stops the migration from reading the eval's file at all: it finds the config files without loading their parent and loads each one with `parent=self`. Nothing re-enters the validator, so the recursion guard and its module-level set and lock go.
- **`_restore` wraps only some exception types.** Any other exception from re-reading or re-validating the file is wrapped in `LargeFieldUnavailableError`, naming the file and field, so an `AttributeError` raised there can't make `getattr(run, "trace", None)` return `None` or `hasattr` return `False`.
- **The JSONL export loads every run of the task as an editable copy.** The export path only reads its runs: `_get_tool_definitions_from_config` reads `output.source` and hands the run's parent task (not the run) to `tool_from_id` / `load_skills_from_tool_ids`, which only read it; `build_training_chat` reads `input`, `trace`, `output`, `repaired_output` and `intermediate_outputs`; the chat formatter and the format generators build new dicts and dataclasses, and keep references to the trace's `tool_calls` lists without changing them. So the export loads the task's runs readonly, and only the split's runs read their large fields.

Dismissed (user decisions): the cache budget ignoring cgroup memory limits (won't fix), and a restore that meets a save in progress not being retried (left as is: no data loss, and the next load caches the record).

## Steps

1. **`libs/core/kiln_ai/datamodel/basemodel.py`**: split the directory scan out of `KilnParentedModel.iterate_children_paths_of_parent_path` into a new classmethod:

   ```python
   @classmethod
   def iterate_children_paths_in_folder(cls, parent_folder: Path) -> Iterator[Path]:
       """The record files of this class in a parent's folder. Doesn't load the parent."""
   ```

   `iterate_children_paths_of_parent_path` keeps its `None` check and its readonly parent load, then `yield from cls.iterate_children_paths_in_folder(parent_folder)`. Its behaviour doesn't change.

2. **`libs/core/kiln_ai/datamodel/eval.py`**, `Eval.upgrade_old_reference_answer_eval_config`:
   - Return early when `self.path is None` (in place of the `self.id is None` check, which only served the guard).
   - Load the configs with
     `[EvalConfig.load_from_file(p, parent=self) for p in EvalConfig.iterate_children_paths_in_folder(self.path.parent)]`.
     Mutable loads never add to the cache, and `parent=self` keeps config validators from loading the eval. A short comment says why it isn't `self.configs()`.
   - Remove the recursion guard, `_migration_lock`, `_currently_migrating_eval_ids` and the `Lock` import.

3. **`libs/core/kiln_ai/datamodel/lazy_fields.py`**, `_restore`: after the `ValueError` clause, `except Exception as e` raises `LargeFieldUnavailableError(root.path, field, f"reading the record raised {type(e).__name__}: {e}")` from `e`.

4. **`libs/core/kiln_ai/adapters/fine_tune/dataset_formatter.py`**, `DatasetFormatter.dump_to_file`: `self.task.runs(readonly=True, include_intermediate_runs=True)`.

5. **`specs/projects/cache_eviction_and_efficiency/backlog.md`**: move the three closed items under a "Closed" heading and the two dismissed ones under "Dismissed", each with a one-line resolution.

## Tests

`libs/core/kiln_ai/datamodel/test_eval_model.py`:
- `test_eval_migration_caches_only_migrated_copies` (parametrized: first load mutable, first load readonly): with the cache on, after the first load of an un-migrated reference-answer eval, a readonly load of the eval and the `parent` of each readonly config all have the oldest config's id as `current_config_id`. Fails before the fix.
- The existing `test_eval_upgrade_old_reference_answer_eval_config` covers the cache-off migration unchanged (oldest config picked, set value kept, other data types skipped, no configs).

`libs/core/kiln_ai/datamodel/test_basemodel.py` (or the existing children tests there):
- `test_iterate_children_paths_in_folder_does_not_load_parent`: returns the same paths as `iterate_children_paths_of_parent_path`, and returns nothing for a folder with no relationship folder, without loading the parent file (it can be missing).

`libs/core/kiln_ai/datamodel/test_lazy_fields.py`:
- `test_restore_unexpected_error_raises` (parametrized: `AttributeError`, `TypeError`): re-validation raising that error makes the large-field read raise `LargeFieldUnavailableError` with the path, field and chained cause, and `getattr(record, "body", None)` and `hasattr(record, "body")` raise rather than returning a default.

`libs/core/kiln_ai/adapters/fine_tune/test_dataset_formatter.py`:
- `test_dataset_formatter_reads_large_fields_of_split_runs_only`: four saved runs, a split holding two, the cache on and large values evicted; the export writes the two split runs in split order and re-reads exactly two run files. Fails before the fix (four re-reads).
