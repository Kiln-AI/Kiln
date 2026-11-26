---
status: complete
---

# Phase 1: Rename World to Environment

## Overview

Rename the unreleased World feature to Environment across core, server, desktop, web schema and tests, following the name map in `architecture.md` section 2. No behaviour changes. No migration: saved eval data and dev projects using the old names are allowed to break. The `*_worlds*` agent-policy annotation files are deleted and regenerated under the new paths, and the web OpenAPI types are regenerated.

## Steps

1. Move files with `git mv`:
   - `libs/core/kiln_ai/datamodel/world.py` → `environment.py`; `test_world.py` → `test_environment.py`
   - `libs/core/kiln_ai/worlds/` → `libs/core/kiln_ai/environments/`
   - `libs/core/kiln_ai/tools/world_tool.py` → `env_tool.py`; `test_world_tool.py` → `test_env_tool.py`
   - `libs/core/kiln_ai/adapters/eval/test_eval_runner_worlds.py` → `test_eval_runner_environments.py`
   - `app/desktop/studio_server/world_api.py` → `environment_api.py`; `test_world_api.py` → `test_environment_api.py`
2. Identifier rename, applied in this order so compound names resolve first:
   - `kiln_tool::world::` → `kiln_tool::env::`; `WORLD_TOOL_ID_PREFIX` → `ENV_TOOL_ID_PREFIX`; `build_world_tool_id` → `build_env_tool_id`; `world_and_tool_name_from_id` → `env_and_tool_name_from_id`
   - `world_id` → `environment_id`; `world_version` → `env_version` (including `_compose_world_version` → `_compose_env_version`, `WorldSessionManager.world_version()` → `env_version()`)
   - `WorldReset` → `EnvironmentReset`, `WorldEpisode` → `EnvironmentEpisode`, `WorldSessionManager` → `EnvironmentSessionManager`, `World` → `Environment`, `World*Request/Response` → `Environment*Request/Response`
   - `world_reset` → `env_reset`, `world_episode` → `env_episode`, `world_session_manager` → `env_session_manager`, `world_trace_tag` → `env_trace_tag`, `validate_world_tool_ids` → `validate_env_tool_ids`, `_WorldTarget` → `_EnvTarget`, `_world_*` helpers → `_env_*`, mismatch literals `"no_world_reset"` → `"no_env_reset"`, `"other_world"` → `"other_env"`
   - `Project.worlds()` / `parent_of={"worlds": ...}` → `environments`; `EpisodeContext.world` → `.environment`; `_EnvServer.world_id/.world_version` → `.environment_id/.env_version`
   - Import paths `kiln_ai.worlds` → `kiln_ai.environments`, `kiln_ai.datamodel.world` → `kiln_ai.datamodel.environment`, `kiln_ai.tools.world_tool` → `kiln_ai.tools.env_tool`, `studio_server.world_api` → `studio_server.environment_api`, `connect_world_api` → `connect_environment_api`
3. Routes `/api/projects/{project_id}/worlds...` → `/environments...` with path param `environment_id`; OpenAPI tag "Worlds" → "Environments" in `libs/server/kiln_server/server.py`.
4. Replace the hard-coded `kiln_tool::world::{world.id}` string in `eval_runner.py` with `build_env_tool_id`.
5. Rewrite remaining prose ("world tool", "the world's environment", docstrings, field descriptions, error messages) by hand to read naturally with "environment" / "OpenEnv". Leave English and geometry uses of "world" alone (hello-world strings, lineage viewport, synth-data guidance, batch-plan guidance, synthetic-user world-state).
6. Delete `libs/server/kiln_server/utils/agent_checks/annotations/*_worlds*.json`; regenerate annotations with `dump_annotations.py` and `app/web_ui/src/lib/api_schema.d.ts` with `generate_schema.sh`.
7. Repo-wide grep for `kiln_tool::world`, `world_`, `World`, `worlds`: every remaining hit is English.

## Tests

- Existing suites for the renamed modules pass under their new names (`test_environment.py`, `test_env_tool.py`, `test_session_manager.py`, `test_eval_runner_environments.py`, `test_environment_api.py`, plus eval, trace index, tool registry, adapter registry, sandbox bridge, code eval and jobs tests).
- `test_no_world_identifiers_remain`: a grep-style test over `libs/core/kiln_ai`, `libs/server/kiln_server` and `app/desktop/studio_server` Python sources fails on any `kiln_tool::world` string or `World`/`world_` identifier.
- Full `uv run ./checks.sh --agent-mode` passes, including the OpenAPI schema check.
