---
status: complete
---

# Phase 3: Reach check, save-time validation, lookup endpoint, OpenEnv tool sets

## Overview

A run can reach at most one OpenEnv environment, counted across its own tools, the allowlists of code tools it lists (nested), and the run configs of Kiln task tools it lists. This phase adds the walk that finds every environment a tool list reaches, uses it when a run config is saved and when a code tool is created, exposes it to the UI through a fast lookup endpoint, and lists each reachable environment's tools in `available_tools` so the picker can offer them. The run path (phase 4) and the run page field (phase 7) build on this.

## Steps

1. New `libs/core/kiln_ai/tools/env_reach.py`:
   - `@dataclass(frozen=True) class EnvReach: environment_id: str; via: str` where `via` is `"directly"`, `"code tool <name>"` or `"Kiln task tool <name>"`, always naming the outermost tool in the list given.
   - `class EnvironmentReachError(ValueError)` with `message` (the spec's short text, "Your tools use more than one OpenEnv (Acme, Beta). A run can only use one.") and `detail` (the message plus how each environment is reached). `str(e)` is the detail, so save errors name the paths.
   - `def environment_reach(project: Project, tool_ids: list[str]) -> list[EnvReach]`: breadth-first walk with a `visited` set of expanded tool ids. Env ids yield their environment; code tool ids load the `CodeTool` and enqueue its `tool_allowlist`; Kiln task tool ids resolve their server (`kiln_task_server_id_from_tool_id`), then the task and run config from `properties["task_id"]` / `["run_config_id"]`, and enqueue that run config's `tools_config.tools` when it's a kiln_agent config. Missing or malformed targets are skipped. Results are deduped on `(environment_id, via)` and keep first-reach order. Only ids are read; no network.
   - `def single_environment_id(project: Project, tool_ids: list[str]) -> str | None`: None when nothing is reached, the id when one is, else raises `EnvironmentReachError` with environment names loaded from the project (falling back to the id for a missing one).
2. `libs/core/kiln_ai/adapters/adapter_registry.py`:
   - `validate_env_tool_ids(task, tool_ids, project_tool_names)` now takes the run config's full tool list. It keeps the "task must belong to a project" and "direct environment exists" checks, replaces the direct-only "more than one environment" check with `single_environment_id(project, tool_ids)`, and keeps the name-collision check.
   - `validate_run_config_tool_names` calls it for every kiln_agent run config with tools, not only when direct env tool ids are present. Docstrings updated: environments are no longer eval-only.
3. `app/desktop/studio_server/code_tool_api.py` `create_code_tool`: after `validate_unique_allowlist_tool_names`, call `single_environment_id(project, request.tool_allowlist)`. The existing `ValueError` → 400 mapping covers it.
4. `app/desktop/studio_server/environment_api.py`: add
   - `RunEnvironmentRequest {tool_ids: list[ToolId]}` and `RunEnvironmentResponse {environment: EnvironmentResponse | None, error: str | None}`.
   - `POST /api/projects/{project_id}/tasks/{task_id}/run_environment` (tag Environments, `ALLOW_AGENT`): validates the task exists, calls `single_environment_id`, and returns 200 with `error` = the reach error's short message, or "OpenEnv {id} wasn't found." for a missing environment, or `environment` for one, or both null.
5. `app/desktop/studio_server/tool_api.py`:
   - `ToolSetType.OPENENV = "openenv"`.
   - `available_openenv_tool_sets(environments, session_manager, timeout_s=5)`: for every environment with an `env_url`, `asyncio.gather` over `asyncio.wait_for(session_manager.list_tools(env, fresh=True), timeout_s)`; failures and timeouts are logged at warning and skipped. Each listed environment gives `ToolSetApiDescription(type=OPENENV, set_name="OpenEnv: " + env.name, tools=[ToolApiDescription(id=build_env_tool_id(env.id, t.name), name=t.name, description=t.description, function_name=t.name)])`. `fresh=True` so an offline environment is hidden rather than served from the session manager's cache, matching MCP's live listing.
   - `get_available_tools` appends these sets after the MCP sets.
6. Web, only what the new enum value forces (the picker work stays in phase 7):
   - Regenerate `app/web_ui/src/lib/api_schema.d.ts`.
   - `tool_options.ts` `AGENT_TOOL_SET_RANK`: `openenv` after `mcp`, before `demo` (the record is exhaustive).
   - `link_builder.ts` `tool_set_type_label`: `"openenv"` → `"OpenEnv"` (exhaustive switch).
   - Regenerate agent annotations for the new route.

## Tests

- `libs/core/kiln_ai/tools/test_env_reach.py` (new):
  - direct env id yields `via="directly"`; no env ids yields `[]` and `single_environment_id` → None
  - code tool allowlist reaching an env gives `via="code tool <name>"`; nested code tool keeps the outermost name
  - Kiln task tool → run config → code tool → env gives `via="Kiln task tool <name>"`
  - cycle between two code tools terminates
  - missing code tool, missing server, missing task, missing run config and malformed ids are skipped
  - one environment reached two ways → single id
  - two environments → `EnvironmentReachError`; message names both by name; detail names each via; missing environment name falls back to id
- `libs/core/kiln_ai/adapters/test_adapter_registry.py`:
  - update the two-environments test to the new message
  - run config whose code tool reaches a second environment is refused
  - run config with only a code tool reaching one environment is accepted
- `app/desktop/studio_server/test_code_tool_api.py`: create refuses an allowlist reaching two environments (400 naming them).
- `app/desktop/studio_server/test_environment_api.py` lookup endpoint: none reached; one reached (returns environment with options); two reached (error, no environment); missing environment (error text); unknown task 404.
- `app/desktop/studio_server/test_tool_api.py`: OpenEnv set listed with correct ids and name; environment without `env_url` not listed; failing environment skipped; slow environment skipped after the timeout while others still list.
- Web: `tool_options.test.ts` order includes `openenv` between `mcp` and `demo`; `link_builder.test.ts` label for `openenv`.
