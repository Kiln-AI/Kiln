---
status: complete
---

# Phase 3: The block list and `PUT` → `POST` for the data guide

## Overview

Annotate the 29 operations of the MCP block list with the `x-mcp-policy` tag, so `call_kiln_api` refuses them, and pin the list with a test against the real desktop app. Change the one `PUT` route (the data guide save) to `POST`, because the tool has no `PUT`, and update its callers and generated files.

Specs: [mcp_server_and_api_tool](../components/mcp_server_and_api_tool.md) sections 6.3, 7 and 10; [mcp_block_list_review](../research/mcp_block_list_review.md).

## Steps

1. **Annotate the blocked routes** with `openapi_extra=with_mcp_deny(<the route's current agent policy>)`, importing `with_mcp_deny` from `kiln_server.utils.agent_checks`(`.policy`) in each file. The agent policy of each route stays as it is.
   - `app/desktop/git_sync/git_sync_api.py`: all 14 routes under `/api/git_sync/` (rows 1–14). `DELETE /api/delete_project/{project_id}` is not annotated.
   - `app/desktop/studio_server/import_api.py`: `GET /api/select_kiln_file` (row 15).
   - `app/desktop/studio_server/chat/routes.py`: `POST /api/chat`, `POST /api/chat/execute-tools` (rows 16–17).
   - `app/desktop/studio_server/jobs/api.py`: `GET /api/jobs/events`, `with_mcp_deny(ALLOW_AGENT)` (row 18).
   - `app/desktop/studio_server/provider_api.py`: `create_kiln_copilot_api_key`, `connect_api_key`, `disconnect_api_key`, `POST` and `DELETE openai_compatible` (rows 19, 26–29).
   - `app/desktop/studio_server/settings_api.py`: `POST /api/settings`, `POST /api/open_logs` (`with_mcp_deny(agent_policy_require_approval(...))`), `POST /api/open_project_folder/{project_id}` (rows 20–22).
   - `libs/server/kiln_server/document_api.py`: document `open_enclosing_folder` and `download` (rows 23, 25).
   - `app/desktop/studio_server/skill_api.py`: skill `open_enclosing_folder` (row 24).

2. **`PUT` → `POST`** for `/api/projects/{project_id}/tasks/{task_id}/data_gen_guide`:
   - `app/desktop/studio_server/data_gen_api.py`: `@app.put` → `@app.post`; `ALLOW_AGENT` stays.
   - `app/desktop/studio_server/test_data_gen_api.py`: the nine `client.put(` → `client.post(`.
   - Web UI `client.PUT(` → `client.POST(` in `data_guide/+page.svelte`, `data_guide/refine/+page.svelte`, `data_guide_setup/+page.svelte`, `data_guide_setup_copilot/+page.svelte` under `app/web_ui/src/routes/(app)/generate/[project_id]/[task_id]/`.
   - The end-to-end UI tests that seed a guide with `apiRequest.put` (`app/web_ui/tests/e2e/act_data_guide_routing.spec.ts`, `act_data_guide_actions.spec.ts`) → `apiRequest.post`, with their texts.
   - Regenerate `app/web_ui/src/lib/api_schema.d.ts` with `generate_schema.sh`.
   - Add `annotations/post_api_projects_project_id_tasks_task_id_data_gen_guide.json` with `dump_annotations` (the `make annotations` command, run on the app's OpenAPI document); keep the `put_…` file.

3. **End-to-end test**: in `app/desktop/studio_server/test_kiln_mcp_mount.py`, `_agent_session` also calls a blocked endpoint (`GET /api/jobs/events`) and the test checks the blocked text.

## Tests

- `app/desktop/studio_server/test_mcp_block_list.py`:
  - `test_blocked_routes_match_the_block_list`: `EXPECTED_MCP_BLOCKED` (the 29 rows as `(method, path)`) equals the set read from `make_app().routes` with `is_mcp_denied`.
  - `test_each_blocked_route_is_reachable_by_its_template` (parametrised over the rows): `RouteIndex.match` on the template with each `{param}` replaced by `x` returns `found` with that entry, and it is blocked.
  - `test_each_blocked_route_is_tagged_in_openapi` (parametrised): the operation carries `x-mcp-policy` in `app.openapi()`.
  - `test_routes_kept_open` (parametrised): `add_code_trust` GET and POST, `connect_local_mcp`, `edit_local_mcp`, `GET /api/settings`, `GET /api/jobs/{id}`, `DELETE /api/delete_project/{project_id}`, `GET /api/download_dataset_jsonl`, `download_extraction`, and `POST data_gen_guide` are found and not blocked.
  - `test_agent_policies_are_unchanged_by_the_block`: each blocked route still carries its `x-agent-policy` (all `deny`, except `GET /api/jobs/events` allow and `POST /api/open_logs` allow with approval).
- `app/desktop/studio_server/test_kiln_mcp_mount.py::test_end_to_end_on_the_running_app`: the blocked call returns `isError` true with the blocked text for `GET /api/jobs/events`.
- `app/desktop/studio_server/test_data_gen_api.py`: the existing save tests run on `POST`; `PUT` on the path → 405.
