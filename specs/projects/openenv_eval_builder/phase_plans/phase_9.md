---
status: complete
---

# Phase 9: Run Configs That Don't Fit a Grounded Eval's Server

## Overview

For an eval with `openenv_server_id`, a run config fits when its tool ids include at least one
OpenEnv tool and every OpenEnv tool id names the eval's server. Today a run config with no
OpenEnv tools runs the grounded cases silently without the environment, and one with another
server's tools fails each item behind an anonymous "N errors". This phase puts the rule in one
libs/core function, makes the runner error per item instead of running without the environment,
makes `run_comparison` refuse (hand-picked) or skip (`all_run_configs`) with the reason, and has
the comparison table warn and disable the row's Run Eval. Evals without `openenv_server_id`, and
eval inputs without `openenv_reset`, behave exactly as today.

## Steps

1. New `libs/core/kiln_ai/adapters/eval/openenv_fit.py`:
   - `OpenEnvMisfit = Literal["no_openenv_tools", "other_openenv_server"]`
   - `openenv_misfit(eval_openenv_server_id: ID_TYPE | None, run_config: TaskRunConfig) -> OpenEnvMisfit | None`:
     None when the eval has no server; direct tool ids only (`kiln_tool::openenv::<id>::…`).
   - `openenv_misfit_message(misfit, run_config_name, openenv_server_label) -> str`:
     "This eval's cases run in OpenEnv server 'X'; run config 'N' has none of its tools." /
     "...; run config 'N' uses tools from another OpenEnv server."
   - `openenv_server_label(openenv_server_id, project) -> str`: the server's name, or its id when
     it can't be loaded.
   - `SkippedRunConfig` (dataclass: `id`, `name`, `reason`) and
     `split_run_configs_by_openenv_fit(eval, run_configs, openenv_server_label) -> tuple[list[TaskRunConfig], list[SkippedRunConfig]]`.
2. `eval_runner.py`:
   - `_openenv_tool_mismatch` gains `eval_openenv_server_id` and a `"no_openenv_tools"` kind,
     returned when the item has an `openenv_reset` and `openenv_misfit` says
     `"no_openenv_tools"`.
   - `_uses_openenv` raises a ValueError for it, built with `openenv_misfit_message` (server id
     as the label; the runner reads no server file per job).
   - `validate_openenv_readiness` reports it per run config with the server's name and the item
     ids.
   - Both pass `self.eval.openenv_server_id`.
3. `app/desktop/studio_server/eval_api.py`, `run_comparison`, only when the eval has
   `openenv_server_id`:
   - `all_run_configs`: split with `split_run_configs_by_openenv_fit`; 400 naming every reason
     when none fit; otherwise run the fitting ones.
   - Both modes: `validate_openenv_readiness()` → 400 with its message (hand-picked misfits are
     refused here).
   - `run_eval_runner_with_status(eval_runner, skipped_run_configs=[])`: each progress frame
     carries `skipped_run_configs: [{id, name, reason}]` when the list is non-empty.
4. `app/web_ui/src/lib/utils/openenv.ts`: `openenv_misfit(eval_openenv_server_id, tool_ids)`
   mirroring step 1, and `openenv_misfit_note(misfit, server_name)`:
   "No OpenEnv tools. This eval's cases run in <name>." / "Uses another OpenEnv server. This
   eval's cases run in <name>."
5. `lib/components/run_config_comparison_table.svelte`: load the eval's server with
   `create_openenv_server_loader`; a misfit row's Status cell shows the note in an inline
   `Warning` (color warning), and its Run Eval (interactive button or link) is replaced by a
   disabled Run Eval button inside a DaisyUI tooltip carrying the note.
6. `lib/components/run_eval.svelte`: read `skipped_run_configs` from progress frames and list them
   in the progress dialog under a warning ("Skipped N run configs:" then each reason). A refused
   run already shows the server's message (fetch-based stream).
7. No OpenAPI model changes (the SSE frame isn't in the schema); confirm with `check_schema.sh`.

## Tests

- `test_openenv_fit.py`: no server → None; no tools → no_openenv_tools; project tools only →
  no_openenv_tools; MCP-type run config → no_openenv_tools; eval's tools (+ project tools) →
  None; another server's tool, alone or mixed with the eval's → other_openenv_server; messages;
  label falls back to id; split keeps order and reports skipped.
- `test_eval_runner_openenv.py`: grounded eval + reset input + project-tools run config → item
  error naming the server and run config, nothing launched; same with a no-tools run config;
  non-grounded eval keeps running project tools (existing tests); grounded eval + input without
  reset + project tools runs as today; readiness reports no-tools misfit with server name.
- `test_eval_api.py`: grounded eval, hand-picked misfit → 400 with reason; `all_run_configs`
  skips misfits and frames carry `skipped_run_configs`; all misfit → 400; non-grounded eval
  frames unchanged.
- `openenv.test.ts`: `openenv_misfit` cases and note copy.
- `run_config_comparison_table.test.ts`: misfit row shows the note and a disabled Run Eval; a
  fitting row and a non-grounded eval show no note.
- `run_eval.test.ts` (if a harness exists, else a small extracted helper test): skipped run
  configs listed in the progress dialog.
