---
name: subagents
description: |
  Kiln Task as Tool — sub-agents (Subagents, multi-actor, subtasks). Load when: user says "sub agent", "subagent", "Subagents", "delegate to another task", "orchestrator", "multi-actor", or describes one task calling another. Owns the vocabulary mapping, 4-step setup workflow, and tool name/description guidance.
---
# Knowledge: Sub-Agents (Kiln Task as Tool)

In Kiln, **a "sub-agent" is a Kiln Task wired as a tool** that another Task can call. Same feature, many names users use:

| User says | Maps to |
|---|---|
| "sub agent", "sub-agent", "subagent", "Subagent", "Subagents" | Kiln Task as Tool |
| "Multi-Actor Interaction" (from the docs) | Kiln Task as Tool |
| "subtask", "delegate to another task", "orchestrator + worker" | Kiln Task as Tool |
| "agent that calls another agent" | Kiln Task as Tool |
| "tool that uses another model" (when user is on the Add Tools page) | Kiln Task as Tool |

Recognize any of these and load this file. Don't ask the user to clarify which Kiln feature they mean.

## When to use sub-agents

- **Multi-actor pattern:** an orchestrator task delegates specialized work (e.g. a *TV Show Expert* delegates Futurama questions to a *Futurama Transcript QA* sub-agent).
- **Context management:** the sub-agent runs in its own context window; only its summarized result returns to the parent. Single biggest reason to reach for this pattern when the parent's context is bloating.

## Setup Workflow (4 steps)

1. **Sub-agent task** must already exist (the task that will be *called*). If not, create it first via Project Operations.
2. **Saved run config on the sub-agent task.** Sub-agents need a *saved* run config (not a transient one) so the parent gets deterministic behavior. Create via `POST /api/projects/{project_id}/tasks/{task_id}/run_configs`.
3. **Parent task + its own run config.** The task that will *do the calling*. Standard task creation flow.
4. **Wire the sub-agent in (ask the user first, then POST/PATCH).** Draft `{name, description, task_id, run_config_id, is_archived: false}` and **show it to the user for approval** before posting — sub-agent wiring adds a tool server to the project, so the user must consent. On "yes / go / approved", load `references/knowledge/api_docs/post_api_projects_project_id_kiln_task_tool.md` and `POST /api/projects/{project_id}/kiln_task_tool` with the approved body. Report the new tool server ID and link to `http://localhost:8757/tools/{project_id}/tool_servers/{ts_id}`. **Editing an existing wiring is the same gate:** changing a tool server's name/description/run_config via `PATCH /api/projects/{project_id}/edit_kiln_task_tool/{tool_server_id}` is also a project-structure mutation — draft the edit and get approval before the PATCH, never silently. The name + description are what the parent model reads to decide when to invoke the sub-agent (see "Tool name & description guidance" below) — get those right with the user before asking for approval.

**MCP wiring is still UI-only.** `POST /api/projects/{project_id}/connect_local_mcp` and `POST /api/projects/{project_id}/connect_remote_mcp` remain denied to the agent — for those, deep-link to `http://localhost:8757/tools/{project_id}/add_tools` instead.

## Tool name & description guidance

The model that *calls* the sub-agent reads only the tool name + description to decide whether to invoke it. Quality matters:

- **Poor:** `search` — "Search for information"  *(what does it search?)*
- **Better:** `web_search` — "Search the web for information"  *(returns webpages? summaries?)*
- **Best:** `web_researcher` — "This tool can search and scrape the web for information. Ask it a question and it will research using the web, and reply with a summarized answer."

Aim for the third style: name a role, describe behavior, hint at input/output shape.

## API Docs

| Endpoint | Load |
|---|---|
| GET kiln task tools (list existing) | `references/knowledge/api_docs/get_api_projects_project_id_kiln_task_tools.md` |
| GET tasks compatible with a tool | `references/knowledge/api_docs/get_api_projects_project_id_tasks_compatible_with_tool.md` |
| POST add Kiln task tool *(wires sub-agent — load before step 4)* | `references/knowledge/api_docs/post_api_projects_project_id_kiln_task_tool.md` |
| PATCH edit Kiln task tool | `references/knowledge/api_docs/patch_api_projects_project_id_edit_kiln_task_tool_tool_server_id.md` |

## UI Deep Links

| Action | Link |
|---|---|
| Add a Kiln Task as Tool | `http://localhost:8757/tools/{project_id}/add_tools` *(then click "Kiln Task as Tool")* |
| View existing tool servers | `http://localhost:8757/tools/{project_id}/tool_servers/{ts_id}` |

## Further reading

- `references/docs/agents.md` — Multi-Actor Interaction section has the visual walkthrough.
- `references/knowledge/tools.md` — broader tool-server catalog (MCP local/remote, RAG, demo tools).
