# MCP block list: the review of each endpoint

Review date: 2026-11-20. This is the record that functional spec 5.5 asks for: start from the endpoints the Kiln Assistant is denied today, review each one, and get the list approved. The final list, with route files, is in [components/mcp_server_and_api_tool.md](../components/mcp_server_and_api_tool.md) section 6.3. If this file and that table differ, the table wins and this file is corrected.

## Result

- The Kiln Assistant is denied 66 endpoints today (`DENY_AGENT` in the route's `openapi_extra`), out of 269 operations.
- The MCP blocks 27 of them and allows 39.
- The MCP also blocks 2 endpoints that the Assistant may call today. So the block list has 29 operations.
- Everything else is allowed. The MCP policy (`x-mcp-policy`) and the Assistant policy (`x-agent-policy`) are separate tags; no ruling here changes what the Assistant may call.

How the rulings were made:

- The default is allow. A user's own agent may do almost anything: the user takes responsibility for it, and the agent's own permission prompts are the user's control (functional spec 5.5).
- An endpoint is blocked when it returns a secret, takes or deletes a stored secret, is a step of a browser or desktop flow that an agent cannot complete, never returns, belongs to the Assistant's own protocol, or returns data that the tool would corrupt.
- A delete of project data is allowed. The skill tells the agent to confirm with the user before a destructive operation.
- Where the review found a group of related endpoints, one simple rule for the group was preferred over a rule per endpoint.

The "Row" column is the row number in section 6.3 of the component doc.

## 1. The 66 endpoints the Assistant is denied

### 1.1 Deletes of project data

| Method and path | Purpose | Ruling | Reason |
|---|---|---|---|
| DELETE `/api/projects/{project_id}/tasks/{task_id}` | Delete a task | Allow | A normal destructive action; the skill says to confirm first |
| DELETE `/api/projects/{project_id}/tasks/{task_id}/prompts/{prompt_id}` | Delete a prompt | Allow | Same |
| DELETE `/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}` | Delete a spec | Allow | Same |
| DELETE `/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}` | Delete an eval | Allow | Same |
| DELETE `/api/projects/{project_id}/tasks/{task_id}/eval_inputs/{eval_input_id}` | Delete an eval input | Allow | Same |
| DELETE `/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}` | Delete a run | Allow | Same |
| POST `/api/projects/{project_id}/tasks/{task_id}/runs/delete` | Delete several runs | Allow | Same |
| DELETE `/api/projects/{project_id}/documents/{document_id}` | Delete a document | Allow | Same |
| POST `/api/projects/{project_id}/documents/delete` | Delete several documents | Allow | Same |
| DELETE `/api/projects/{project_id}/documents/{document_id}/extractions/{extraction_id}` | Delete an extraction | Allow | Same |
| DELETE `/api/projects/{project_id}/code_tools/{code_tool_id}` | Delete a code tool | Allow | Same |
| DELETE `/api/projects/{project_id}/tool_servers/{tool_server_id}` | Delete a tool server and its secrets | Allow | Same |
| POST `/api/projects/{project_id}/tool_servers/{tool_server_id}/archive` | Archive a tool server | Allow | Same |
| DELETE `/api/delete_project/{project_id}` | Remove a project from Kiln's list (the files stay) | Allow | Same. It is in the git-sync route file but is not a git-sync route |

### 1.2 Evals and code trust

| Method and path | Purpose | Ruling | Reason |
|---|---|---|---|
| POST `/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/test_v2_eval` | Test a judge config | Allow | Normal work for an agent |
| POST `/api/projects/{project_id}/tasks/{task_id}/test_v2_eval_draft` | Test a judge config before the eval exists | Allow | Same |
| GET `/api/projects/{project_id}/add_code_trust` | Read whether the project is trusted to run new code | Allow | Read only |
| POST `/api/projects/{project_id}/add_code_trust` | Grant that trust | Allow | Owner's ruling. A coding agent can write and test code tools, and needs this to do it. The skill tells the agent to ask the user before it grants code trust |

### 1.3 Providers, models and settings

| Method and path | Purpose | Ruling | Row | Reason |
|---|---|---|---|---|
| GET `/api/settings` | Read all settings | Allow | | The response masks every secret |
| GET `/api/settings/{item_id}` | Read one setting | Allow | | Masked in the same way |
| POST `/api/settings` | Write settings as raw keys | Block | 20 | An unvalidated write of the whole config: it can overwrite keys, the project list and git-sync tokens. Dedicated endpoints exist for what an agent needs |
| GET `/api/settings/available_providers` | Providers that can take custom models | Allow | | Read only |
| GET `/api/settings/user_models` | List user-defined models | Allow | | Read only |
| POST `/api/settings/user_models` | Add a user-defined model | Allow | | A validated endpoint with one purpose |
| DELETE `/api/settings/user_models` | Delete a user-defined model | Allow | | Same |
| POST `/api/provider/connect_api_key` | Save a provider API key | Block | 26 | It takes a secret. The user would have to put the key into the agent's context. The user connects a provider in the app |
| POST `/api/provider/disconnect_api_key` | Delete a stored provider API key | Block | 27 | It removes a stored secret that only the user can restore |
| POST `/api/provider/openai_compatible` | Add an OpenAI-compatible provider (name, URL, key) | Block | 28 | It takes an `api_key`. Blocked with the other provider-key endpoints |
| DELETE `/api/provider/openai_compatible` | Remove an OpenAI-compatible provider | Block | 29 | It removes a stored key. Same rule |
| POST `/api/provider/ollama/connect` | Test and save the Ollama URL | Allow | | It takes a URL, not a key |
| POST `/api/provider/docker_model_runner/connect` | Test and save the Docker Model Runner URL | Allow | | Same |
| POST `/api/provider/create_kiln_copilot_api_key` | Swap a browser sign-in token for a Kiln Pro key | Block | 19 | A step of the browser sign-in. An agent cannot use it |
| GET `/api/check_entitlements` | Which Kiln Pro features the user has | Allow | | Read only, booleans |
| GET `/api/demo_tools` | Read the demo-tools flag | Allow | | Read only |
| POST `/api/demo_tools` | Set the demo-tools flag | Allow | | A harmless flag |

### 1.4 Tools and MCP tool servers

| Method and path | Purpose | Ruling | Reason |
|---|---|---|---|
| POST `/api/projects/{project_id}/connect_remote_mcp` | Add a remote MCP tool server | Allow | Normal work for an agent |
| PATCH `/api/projects/{project_id}/edit_remote_mcp/{tool_server_id}` | Edit it | Allow | Same |
| POST `/api/projects/{project_id}/connect_local_mcp` | Add a local MCP tool server (Kiln starts the given command) | Allow | Owner's ruling. It runs a command on the Kiln machine, so the skill tells the agent to ask the user first. Spec two blocks it on fenced connections |
| PATCH `/api/projects/{project_id}/edit_local_mcp/{tool_server_id}` | Edit it (Kiln starts the command again) | Allow | Same |

### 1.5 Git sync

All 14 routes under `/api/git_sync/` are blocked. Git sync is set up by a wizard in the app, with a browser step for OAuth. One simple rule was preferred over a rule per route, so the read-only config route is blocked too.

| Method and path | Purpose | Ruling | Row | Reason |
|---|---|---|---|---|
| GET `/api/git_sync/oauth/status/{state}` | Poll the OAuth flow | Block | 1 | It returns the GitHub OAuth token: the one response in the API with a secret field |
| POST `/api/git_sync/oauth/start` | Start the OAuth flow | Block | 2 | A browser flow; no use without the status call |
| GET `/api/git_sync/oauth/callback` | The redirect target of the flow | Block | 3 | For a browser only; returns an HTML page |
| GET `/api/git_sync/oauth/authorize` | The "install complete" page | Block | 4 | For a browser only; returns an HTML page |
| POST `/api/git_sync/test_access` | Test read access to a remote | Block | 5 | A step of the setup wizard; the request can carry a token |
| POST `/api/git_sync/list_branches` | List the branches of a remote | Block | 6 | Same |
| POST `/api/git_sync/clone` | Clone a repository into the projects folder | Block | 7 | Same |
| POST `/api/git_sync/test_write_access` | Test write access | Block | 8 | Same |
| POST `/api/git_sync/scan_projects` | Find Kiln projects in a clone | Block | 9 | A step of the setup wizard |
| POST `/api/git_sync/rename_clone` | Move a clone to its final path | Block | 10 | Same |
| POST `/api/git_sync/save_config` | Save a new sync config (tokens in the request) | Block | 11 | It takes secrets |
| GET `/api/git_sync/config/{project_id}` | Read a project's sync config | Block | 12 | Read only, and it returns only booleans for the tokens. Blocked so that the rule is "all of git sync" |
| PATCH `/api/git_sync/config/{project_id}` | Change the sync mode or the tokens | Block | 13 | It can take a token |
| DELETE `/api/git_sync/config/{project_id}` | Remove the sync config | Block | 14 | It removes stored tokens |

### 1.6 The desktop, downloads and the Assistant

| Method and path | Purpose | Ruling | Row | Reason |
|---|---|---|---|---|
| GET `/api/select_kiln_file` | Open a native file dialog and wait for the user | Block | 15 | A desktop dialog: the call waits until someone clicks |
| POST `/api/open_project_folder/{project_id}` | Open the project folder in the OS file browser | Block | 22 | It opens a window on the Kiln machine and returns nothing |
| POST `/api/projects/{project_id}/documents/{document_id}/open_enclosing_folder` | Open a document's folder | Block | 23 | Same |
| POST `/api/projects/{project_id}/skills/{skill_id}/open_enclosing_folder` | Open a skill's folder | Block | 24 | Same |
| GET `/api/download_dataset_jsonl` | Download a dataset as JSONL | Allow | | Text. It works well with `save_to_tmpfile` |
| GET `/api/projects/{project_id}/documents/{document_id}/download` | Download the original document file | Block | 25 | The file can be binary. The tool decodes the body as text, so a binary file arrives corrupt |
| GET `/api/projects/{project_id}/documents/{document_id}/download_extraction/{extraction_id}` | Download an extraction output | Allow | | Text. The content type of the output files is checked during implementation |
| POST `/api/chat` | The Kiln Assistant's chat stream | Block | 16 | The Assistant's own protocol; it would be an agent calling the Assistant |
| POST `/api/chat/execute-tools` | Continue a chat after tool approvals | Block | 17 | Same |
| GET `/api/chat/sessions` | List the user's Assistant chats | Allow | | Read only |
| GET `/api/chat/sessions/{session_id}` | Read one Assistant chat | Allow | | Read only |
| DELETE `/api/chat/sessions/{session_id}` | Delete an Assistant chat | Allow | | A normal destructive action |
| GET `/api/chat/version_policy` | The minimum client version of Kiln's server | Allow | | Read only |

## 2. Endpoints the Assistant may call that the MCP blocks

| Method and path | Assistant policy today | Ruling | Row | Reason |
|---|---|---|---|---|
| GET `/api/jobs/events` | Allow | Block | 18 | An endless event stream: the tool call would never return. `GET /api/jobs/{id}` on the same prefix stays allowed |
| POST `/api/open_logs` | Allow with approval | Block | 21 | It opens the logs in the OS, like the three open-folder endpoints |

## 3. Other endpoints the review looked at

These are not denied to the Assistant and are not blocked. They are listed because the review considered them.

| Method and path | Ruling | Reason |
|---|---|---|
| POST `/api/projects/{project_id}/code_tools` | Allow | Creating a code tool. Without code trust for the project the endpoint creates nothing and answers `not_trusted` |
| POST `/api/projects/{project_id}/test_code_tool` | Allow | Runs code on the Kiln machine. Without code trust for the project the endpoint runs nothing and answers `not_trusted` |
| GET `/api/jobs/{id}/wait`, POST `/api/jobs/wait` | Allow | Long blocking calls. The tool sends progress updates while they run |
| PUT `/api/projects/{project_id}/tasks/{task_id}/data_gen_guide` | Changed, not blocked | The only `PUT` route. The tool has no `PUT`, so the route becomes `POST` in this project and stays allowed |

There is no shutdown endpoint and no developer endpoint under `/api`. The developer page `/scalar` is outside `/api`, and the tool's path rule already refuses it.

## 4. What the user is told

For each blocked capability that a user might ask an agent for, the skill tells the agent to ask the user to do it in the Kiln app, with the link to the right page. The table of capabilities and pages is in [components/skill_and_content.md](../components/skill_and_content.md) section 4.4.
