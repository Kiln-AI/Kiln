---
status: in_progress
---

# Phase 5: agent_overview endpoint

## Overview

Build the `GET /api/projects/{project_id}/tasks/{task_id}/agent_overview` endpoint in a new `agent_api.py` file. This endpoint returns a one-shot summary of a task covering all entity types (project, task, dataset, docs, search tools, prompts, specs, evals, tool servers, run configs, fine-tunes, prompt optimization jobs, skills, connected providers). Wire it into the app via `connect_agent_api(app)` in `desktop_server.py`.

## Steps

1. Create `app/desktop/studio_server/agent_api.py` with:
   - All response Pydantic models (AgentOverviewProject, AgentOverviewTask, AgentOverviewDataset, AgentOverviewDocs, AgentOverviewSearchTool, AgentOverviewSearchTools, AgentOverviewPrompt, AgentOverviewSpec, AgentOverviewSpecs, AgentOverviewEval, AgentOverviewOutputScore, AgentOverviewToolServer, AgentOverviewToolServers, AgentOverviewRunConfig, AgentOverviewRunConfigs, AgentOverviewFineTune, AgentOverviewPromptOptimizationJob, AgentOverviewSkill, AgentOverviewSkills, AgentOverview)
   - Helper functions: `_truncate_to_words`, `_split_tool_and_skill_ids`, `_dataset_stats`, `_docs_stats`, `_search_tools_block`, `_tool_servers_block`, `_skills_block`, `_specs_block`, `_evals_block`, `_prompts_block`, `_run_configs_block`, `_connected_providers_block`, `_fine_tunes_block`, `_prompt_optimization_jobs_block`
   - `connect_agent_api(app)` with the GET route using `openapi_extra=ALLOW_AGENT`

2. Wire `connect_agent_api` into `app/desktop/desktop_server.py` (add import + call before `connect_chat_api`)

3. Create `app/desktop/studio_server/test_agent_api.py` with tests for:
   - `_truncate_to_words`: under/at/over limit, None, empty
   - `_split_tool_and_skill_ids`: mixed, all skills, all tools, empty
   - `_dataset_stats`: tags, sources, ratings aggregation
   - `_docs_stats`: kind and tag aggregation
   - Archive filtering for search_tools, tool_servers, skills, specs
   - Happy path endpoint test with realistic fixtures
   - Empty task endpoint test
   - 404 for unknown project/task
   - Truncation edge cases (exactly 300, 301 words)

4. Regenerate OpenAPI schema (`generate_schema.sh`)

## Tests

- `test_truncate_to_words_under_limit`: text shorter than limit passes through unchanged, truncated=False
- `test_truncate_to_words_at_limit`: exactly at limit, no truncation
- `test_truncate_to_words_over_limit`: truncated text ends with ` ...`, truncated=True
- `test_truncate_to_words_none`: None input returns (None, False)
- `test_truncate_to_words_empty`: empty string returns ("", False)
- `test_split_tool_and_skill_ids_mixed`: skills separated from tools by prefix
- `test_split_tool_and_skill_ids_empty`: empty list returns two empty lists
- `test_dataset_stats_aggregation`: correct by_tag, by_source, by_rating counts
- `test_docs_stats_aggregation`: correct by_kind, by_tag counts
- `test_search_tools_block_filters_archived`: archived excluded, count correct
- `test_tool_servers_block_filters_archived`: archived excluded, count correct
- `test_skills_block_filters_archived`: archived excluded, count correct
- `test_specs_block_filters_archived`: archived specs excluded, count correct
- `test_agent_overview_happy_path`: full response shape with all sections populated
- `test_agent_overview_empty_task`: all lists empty, counts zero
- `test_agent_overview_not_found`: 404 for bad project/task IDs
- `test_agent_overview_instruction_truncation`: 300-word and 301-word instruction edge cases
