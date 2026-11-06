---
status: complete
---

# Phase 2: Validate Once per Load (5a)

## Overview

`load_from_file` validates a record, then assigns `parent` and `path`. Each assignment re-runs every model validator (`validate_assignment=True`), without the loading context. This phase passes `parent` and `path` into the single `model_validate` call, through a `_validate_file_data` classmethod that phase 4's restore will reuse. Validators see both, with the loading context set.

Two things depend on the re-runs today and must change with it:

- The `Eval` current-config migration reads `self._loaded_from_file`, which is only `True` on the re-runs. It switches to `self.loaded_from_file(info)`.
- `KilnParentedModel.load_parent` attaches a lazily loaded parent with a validated assignment. When a validator reads `self.parent` during the single pass (for example `EvalRun.validate_output_fields`), that assignment re-runs every validator with no context and `_loaded_from_file` still `False`, so load-only exemptions stop applying (the trace-less `full_trace` `EvalRun` would fail to load). `load_parent` attaches the parent without validation instead. The type is right by construction, since it loads `parent_type()`.

A characterization test loads every `.kiln` file in `.agents/playwright_project/` with the old procedure (re-implemented in the test) and the new one, and asserts equal `model_dump()` output or the same exception type.

## Validator audit

`grep` over `libs/core/kiln_ai/datamodel` for `_loaded_from_file`, `loaded_from_file`, `loading_from_file`, `info.context` and validators that read `self.parent` / `self.path`:

| Validator | Old (re-runs) | New (single pass) |
|---|---|---|
| `Eval.upgrade_old_reference_answer_eval_config` | ran on the `path` re-run (`_loaded_from_file` true) | must switch to `loaded_from_file(info)` |
| `EvalRun.validate_output_fields`, `validate_scores`, `validate_reference_answer` | parent checks ran on the re-run | run in the pass; lazy parent load must not re-validate |
| `TaskRun.validate_input_format`, `validate_output_format`, `validate_repaired_output`, `validate_input_source`; `TaskOutput.validate_output_source`; `CodeTool.validate_parameters_schema`; `check_parent_type` | same result either way | same |
| Before-validators that upgrade old data (`TaskRunConfig`, `ExtractorConfig`, `ChunkerConfig`, `VectorStoreConfig`, `EvalConfig.dispatch_properties_parsing`, `_read_code_file` ×2) | upgrade in the first pass, no-op on re-runs | upgrade in the pass |
| `TaskRun.validate_parent_task_run_id_for_turn_mode`, `EvalConfig.validate_v2_templates_and_expressions` | the context-free re-run applied the authoring-time check, so legacy files their comments say must load failed to load | the check is skipped on load, as the comments intend |
| `Eval.migrate_legacy_split_fields` (reads `self.path`) | path set on the re-run | path set in the pass |

## Steps

1. `libs/core/kiln_ai/datamodel/basemodel.py`:
   - Add to `KilnBaseModel`:
     ```python
     @classmethod
     def _validate_file_data(
         cls, raw: dict[str, Any], path: Path, parent: "KilnBaseModel | None"
     ) -> Self:
         data = dict(raw)
         data["path"] = path
         if parent is not None:
             data["parent"] = parent
         m = cls.model_validate(data, context={"loading_from_file": True, "source_dir": path.parent})
         m._loaded_from_file = True
         return m
     ```
   - `load_from_file`: read and parse inside the `with`, then `m = cls._validate_file_data(parsed_json, path, parent)`. Drop the `parent` / `path` assignments and their comment. The `isinstance`, schema-version and `model_type` checks are unchanged and run in the same order.
   - `KilnParentedModel.load_parent`: attach the loaded parent with `self.__dict__["parent"] = loaded_parent` instead of `self.parent = loaded_parent`, with a short comment on why.
2. `libs/core/kiln_ai/datamodel/eval.py`: `upgrade_old_reference_answer_eval_config` takes `info: ValidationInfo` and checks `self.loaded_from_file(info)`.

## Tests

In `libs/core/kiln_ai/datamodel/test_basemodel.py`, a characterization section with an in-test copy of the old `load_from_file` and `load_parent`, patched in for the "old" side:

- `test_single_pass_load_matches_validate_then_assign`: every `.kiln` file in a copy of `.agents/playwright_project/`, loaded without a parent and (for parented records whose parent file exists) with one. Same `model_dump()` or same exception type. Asserts the walk covers the main record types, so it can't pass vacuously.
- `test_single_pass_load_matches_on_invalid_files`: parametrized over a wrong `model_type`, a newer schema version, a field that fails validation, and a parent of the wrong type. Same exception type old and new.
- `test_single_pass_load_runs_eval_current_config_migration`: a reference-answer `Eval` without `current_config_id` and two configs on disk. Old and new agree, and the new load picks the oldest config.
- `test_load_from_file_runs_model_validators_once`: a counting validator on a test parented model runs once per load, with and without a parent passed, and sees `path`, the parent and the loading context.
- `test_lazy_parent_load_during_validation_does_not_revalidate`: a validator that reads `self.parent` during a load without a parent runs once and sees `loaded_from_file()` true.

Legacy files that only load now that the load-only exemptions apply:

- `libs/core/kiln_ai/datamodel/test_task.py`: `test_taskrun_parent_task_run_id_on_single_turn_task_still_loads_from_file`: with and without a parent passed, and after reading `.parent`.
- `libs/core/kiln_ai/datamodel/test_eval_model.py`: `test_value_expression_unknown_variable_still_loads_with_load_from_file`.

Existing tests that cover the change: `test_eval_upgrade_old_reference_answer_eval_config` (fails without the `Eval` switch), `test_v2_full_trace_trace_less_record_loads_from_file` (fails without the `load_parent` change), `test_lazy_load_parent`.
