---
name: tools
description: |
  MCP tool server setup: local MCP, remote MCP, Kiln task-as-tool, demo/pre-made tools. Load when: user wants to "add a tool", "connect MCP", "set up web search / Github / Slack / Python interpreter / filesystem", says the agent "needs to call an API", or any mention of integrating an external capability. Owns vocabulary mapping, demo tools list, MCP wiring through the API (sub-agent wiring lives in references/knowledge/subagents.md), per-type field guidance, and tool selection guidance.
---
# Knowledge: Tools (MCP Tool Servers)

Tools give agents abilities beyond text generation via MCP (Model Context Protocol) tool servers — web search, API calls, database queries, custom integrations, etc. **Kiln supports any MCP server** (local-stdio or remote-http), plus Kiln-native search tools (RAG), Kiln Task as Tool (sub-agents), and **code tools** — native Python functions registered as tools, a lightweight alternative to a whole MCP server for a small piece of custom logic (Beta, trust-gated). For code tools, load `references/knowledge/code_tools.md`.

## User vocabulary

Recognize any of these as "wants a tool / MCP server" and load this file:

| User says | Maps to |
|---|---|
| "add a tool", "connect a tool", "set up tools" | this file |
| "connect MCP", "add an MCP server", "wire up MCP" | this file |
| "I want web search" / "Firecrawl" / "scrape sites" | this file → Firecrawl demo |
| "I need Python" / "let it run code" / "calculator" | this file → Pydantic Python demo (or Math demo for arithmetic-only) |
| "Slack" / "Github" / "stock quotes" / "filesystem access" | this file → demo tools list |
| "agent needs to call an API" / "let it hit our internal service" | this file → custom MCP (local or remote) |
| "RAG" / "search my documents" / "knowledge base" | `references/knowledge/rag.md` (separate flow — Kiln-native, not MCP) |
| "sub-agent" / "Subagent" / "Kiln Task as Tool" | `references/knowledge/subagents.md` (separate flow — owns that archetype) |

## API Docs

Load the relevant endpoint doc **before** making each API call — they have request body schemas, response fields, and parameter details.

| Endpoint | Load |
|----------|------|
| **Tools & MCP catalog** (full index) | `references/knowledge/api_docs/tools_mcp_api_list.md` |
| GET available tools | `references/knowledge/api_docs/get_api_projects_project_id_available_tools.md` |
| GET available tool servers | `references/knowledge/api_docs/get_api_projects_project_id_available_tool_servers.md` |
| GET kiln task tools | `references/knowledge/api_docs/get_api_projects_project_id_kiln_task_tools.md` |
| POST connect remote MCP | `references/knowledge/api_docs/post_api_projects_project_id_connect_remote_mcp.md` |
| PATCH edit remote MCP | `references/knowledge/api_docs/patch_api_projects_project_id_edit_remote_mcp_tool_server_id.md` |
| POST connect local MCP | `references/knowledge/api_docs/post_api_projects_project_id_connect_local_mcp.md` |
| PATCH edit local MCP | `references/knowledge/api_docs/patch_api_projects_project_id_edit_local_mcp_tool_server_id.md` |
| GET tool server | `references/knowledge/api_docs/get_api_projects_project_id_tool_servers_tool_server_id.md` |
| GET tool server config | `references/knowledge/api_docs/get_api_projects_project_id_tool_servers_tool_server_id_config.md` |
| POST archive tool server | `references/knowledge/api_docs/post_api_projects_project_id_tool_servers_tool_server_id_archive.md` |
| DELETE tool server | `references/knowledge/api_docs/delete_api_projects_project_id_tool_servers_tool_server_id.md` |
| POST add kiln task tool | `references/knowledge/api_docs/post_api_projects_project_id_kiln_task_tool.md` |
| PATCH edit kiln task tool | `references/knowledge/api_docs/patch_api_projects_project_id_edit_kiln_task_tool_tool_server_id.md` |
| GET tasks compatible with tool | `references/knowledge/api_docs/get_api_projects_project_id_tasks_compatible_with_tool.md` |
| POST create task from tool | `references/knowledge/api_docs/post_api_projects_project_id_create_task_from_tool.md` |
| GET search tools | `references/knowledge/api_docs/get_api_projects_project_id_search_tools.md` |
| GET tool definition (task tool) | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_tools_tool_id_definition.md` |
| GET demo tools | `references/knowledge/api_docs/get_api_demo_tools.md` |
| POST set demo tools | `references/knowledge/api_docs/post_api_demo_tools.md` |
| POST create MCP run config | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_mcp_run_config.md` |

## The Agent's Role with Tools

**You detect the need and do the setup through the API.** The user can also do it in the app at `http://localhost:8757/tools/{project_id}/add_tools`; link it when they prefer that.

1. Recognize that the user's problem is a tool problem (not a prompt or model problem)
2. Suggest the right type of tool (local MCP, remote MCP, Kiln task-as-tool, RAG)
3. Add it (see "Wiring an MCP server" below), then check the tools it exposes
4. Attach the tool to a run config through `tools_config` (see the end of this file)

## Tool Types

| Type | What It Is | When to Use |
|------|-----------|-------------|
| **Local MCP Server** | A program running locally on the user's machine (typically Python, Node.js, or a uvx/npx-installable CLI). Communicates over stdio. | Custom API wrappers, internal services on a private network, anything the user wants running on their own hardware |
| **Remote MCP Server** | An MCP server reachable over HTTP at a URL the user provides | Hosted/SaaS integrations (Github MCP, Firecrawl, etc.), shared team servers, anything already running somewhere |
| **Kiln Task Tool** | Another Kiln task exposed as a tool | Sub-agent patterns — see `references/knowledge/subagents.md` (full workflow, including when to ask the user first, lives there) |
| **Kiln Search (RAG)** | Built-in document search over indexed PDFs/text | When the agent needs the user's own documents — `references/knowledge/rag.md` owns the setup flow |
| **Demo / Pre-made tools** | One-click pre-configured popular MCP servers | Fastest way to get the user started — see Demo tools list below |

## Demo / Pre-made tools (the "we support any MCP, here are some examples" list)

Kiln ships several popular MCP servers pre-configured on the Add Tools screen. These are NOT built into Kiln — they are curated third-party servers; the user should trust the authors and review their privacy policies before enabling. Most require either a developer dependency (Node.js, Deno, `uvx`) or an API key:

| Demo tool | What it does | Requires |
|---|---|---|
| **Math Tools** | Built-in `add`, `subtract`, `multiply`, `divide` — for arithmetic the model is bad at | Nothing — one click, enable from `GET /api/demo_tools` toggle |
| **Web Search & Scrape (Firecrawl)** | Search the web + scrape pages into clean text | Firecrawl API key |
| **Run Python (Pydantic)** | Sandboxed Python interpreter — math, iteration, matrix ops, anything the model can't do directly | Deno (sandbox runtime) |
| **Local File Access (Anthropic Filesystem)** | Read/write specific folders on the user's hard drive — paths are configurable at setup | Node.js |
| **Stock Quotes (Twelve Data)** | Realtime quotes + market data | Twelve Data API key |
| **Github MCP** | Manage repos, issues, PRs, workflows | Github access token |

For anything not in this list — internal services, niche SaaS, custom integrations — the user adds a custom MCP server (see "Setup Field Reference" below). For discovering existing MCP servers, point the user at the public MCP server registry without naming a specific domain — direct them to search "MCP server registry" or check the Kiln docs.

**Toggling the demo tools section visibility:**
- `references/knowledge/api_docs/get_api_demo_tools.md` — `GET /api/demo_tools` returns whether demo tools are enabled (boolean).
- `references/knowledge/api_docs/post_api_demo_tools.md` — `POST /api/demo_tools?enable_demo_tools=true|false` toggles them.

## Wiring an MCP server

The connect endpoints add a tool server to the project:

- `POST /api/projects/{project_id}/connect_local_mcp` — `references/knowledge/api_docs/post_api_projects_project_id_connect_local_mcp.md`
- `POST /api/projects/{project_id}/connect_remote_mcp` — `references/knowledge/api_docs/post_api_projects_project_id_connect_remote_mcp.md`

1. **Read the current state** first: `GET /api/projects/{project_id}/available_tool_servers` lists the servers the project has, so you do not add a second copy of one (see "Checking Tool State" below).
2. **Draft the server** with the user: the type ("Local MCP" / "Remote MCP" / a specific demo) and the field values (name, command and arguments, or URL and headers; see "Setup Field Reference" below). Mark API keys and tokens as secrets. A secret value comes from the user; if they would rather not share it in the conversation, they add the server in the app at `http://localhost:8757/tools/{project_id}/add_tools`.
3. **Ask the user first** before you add a local MCP server: it runs a program on the machine where Kiln runs. For a remote server, the URL must come from the user.
4. **Connect it** (`POST /api/projects/{project_id}/connect_local_mcp` body essentials: `{name, command, args[], env_vars{}, secret_env_var_keys[], is_archived: false}` — validates connectivity on create), then read `GET /api/projects/{project_id}/tool_servers/{tool_server_id}/config` to check that it exposes the tools you expect.
5. **Iterate.** A server that lists no tools usually has a wrong command, path or key; fix the field and edit the server (`PATCH .../edit_local_mcp/{tool_server_id}` or `.../edit_remote_mcp/{tool_server_id}`), then check again. For a local server, a change to its command, arguments or environment runs a different program: ask the user first, as in step 3. When you work on the machine where Kiln runs, you can run the command in a terminal yourself to read its error (the debug path under "Local MCP — fields"); it runs the same program, so the same ask applies.
6. **Attach the tool** to a new run config (the end of this file).

**Sub-agent wiring** goes through `POST /api/projects/{project_id}/kiln_task_tool`: draft the tool body and ask the user first, since it adds a tool server to the project. Full flow lives in `references/knowledge/subagents.md`.

The READ side (`GET available_tools`, `GET available_tool_servers`, `GET tool_servers/{id}/config`) needs no confirmation — use it freely to inspect current state before making suggestions.

## Setup Field Reference

These are the fields of a tool server, in the connect request and on the Add Tools page — explain whichever ones the user asks about.

### Local MCP — fields

| Field | What it is |
|---|---|
| **Name / Description** | For you and the team — never sent to the model |
| **Command** | The bare executable: `npx`, `uvx`, `deno`, a shell script path. **No spaces, no arguments here.** |
| **Arguments** | Each argument as a separate item. Example: command `npx`, args `["-y", "firecrawl-mcp"]` |
| **Environment variables** | `key: value` pairs. **Mark API keys / tokens as secrets** (`secret_env_var_keys`) so they aren't synced to git when the project is shared |
| **stdio mode** | Required — most MCP servers default to stdio; some accept a flag. The local-MCP path assumes stdio |

Common debug path if the command fails: confirm it works in a fresh terminal (PATH, dependencies). If a custom PATH is needed, set `custom_mcp_path` in `~/.kiln_ai/settings.yaml`.

### Remote MCP — fields

| Field | What it is |
|---|---|
| **Name / Description** | For you and the team — never sent to the model |
| **Server URL** | Full HTTPS URL of the MCP endpoint — provided by the user (whoever runs the MCP server they're connecting to). Do not invent example domains. |
| **Headers** | `key: value` pairs sent with each request. **Mark API keys / auth tokens as secrets** (`secret_header_keys`) so they aren't synced to git |

### Tool name & description guidance (applies to all types)

The model that *uses* the tool reads only the tool name + description to decide whether to call it. Quality matters:

- **Poor:** `search` — "Search for information"  *(what does it search?)*
- **Better:** `web_search` — "Search the web for information"  *(returns webpages? summaries?)*
- **Best:** `web_researcher` — "This tool can search and scrape the web for information. Ask it a question and it will research using the web, and reply with a summarized answer."

Aim for the third style: name a role, describe behavior, hint at input/output shape.

## Connecting an existing external agent via MCP

If the user already has an agent built outside Kiln and wants Kiln to evaluate or call it: wrap the existing agent in an MCP server (Python, JS, Go, Rust, Java SDKs all available — see `references/docs/tools-and-mcp/connect-to-existing-agents.md`), then connect it as a Remote MCP. From there they can either:
1. Create a new Kiln task from one of the wrapped MCP tool's signature (`POST /api/projects/{project_id}/create_task_from_tool`; see `references/knowledge/api_docs/post_api_projects_project_id_create_task_from_tool.md`).
2. Use a wrapper Kiln task that calls the MCP tool as one of its tools.
3. Connect the MCP tool directly as an MCP run config on an existing Kiln task — input/output schemas must match exactly (`POST /api/projects/{project_id}/tasks/{task_id}/mcp_run_config`).

Don't walk the user through SDK code — point at the docs page online; connect the wrapped server as a Remote MCP as above.

## Tool selection guidance

Two failure modes worth flagging proactively:

1. **Pick a tool-capable model.** Tool calling needs models trained for it. Pre-flight via `GET /api/model_info/model_details` — the `supports_tools` flag of the provider entry is what matters. Kiln will warn in-UI when the chosen model lacks tool support, but the warning is dismissible — call it out in your recommendation.
2. **Don't add too many tools.** Each tool's name + description is in every prompt; dozens of tools fill the context and dilute attention. Be selective — start with the tools the task actually needs, add more only when a real gap shows up. When a task's tool set may already be too large, read `references/improving_agents/smells/too-many-tools.md` and `references/improving_agents/smells/unnecessary-tools.md`.

## Secrets management (one-line summary)

Anything marked as a secret (`secret_env_var_keys`, `secret_header_keys`) is **never written to disk in the project files**. Kiln projects sync via git and would otherwise leak keys; non-secret env vars/headers DO sync (so the team can reuse non-sensitive config). When a teammate pulls a project that has secret-marked tools, they'll be prompted to re-enter the secrets in settings before the tool works.

## Synthetic data + fine-tuning caveat

At this time Kiln **does not** support tool calling during synthetic data generation or fine-tuning. If a user asks "can I fine-tune with my tools?", the honest answer is "not yet" — they should run their tool-using configs against evals, not training jobs. (Kiln team is working on it.)

## Kiln as an MCP server (the other direction)

The flows above are for Kiln calling external tools (Kiln-as-MCP-client). Kiln can also expose its own RAG search tools and Kiln Task as Tool agents to other MCP clients (Claude Desktop, Cursor, etc.) — install via `uv tool install kiln_server` and run `kiln_mcp` pointing at a project. This is rare and lives in a separate flow; mention it only if the user explicitly asks "can I use Kiln from Claude Desktop / Cursor / another MCP client?" and link them at the kiln_mcp README.

## UI Deep Links

| Action | Link |
|--------|------|
| Add/manage tools | `http://localhost:8757/tools/{project_id}/add_tools` |
| View tool server (after wired) | `http://localhost:8757/tools/{project_id}/tool_servers/{ts_id}` |
| Use a tool in a run | `http://localhost:8757/run?tool_id={tool_id}` |

## Checking Tool State (read side)

Call these freely to ground recommendations in current state:

- `references/knowledge/api_docs/get_api_projects_project_id_available_tools.md` — `GET /api/projects/{project_id}/available_tools` lists every tool the project can call (across all servers).
- `references/knowledge/api_docs/get_api_projects_project_id_available_tool_servers.md` — `GET /api/projects/{project_id}/available_tool_servers` lists connected tool servers (one row per Local MCP / Remote MCP / Kiln Task server). Returns `missing_secrets` per server — useful to flag when a server is wired but a teammate hasn't entered their key yet.
- `references/knowledge/api_docs/get_api_projects_project_id_tool_servers_tool_server_id_config.md` — `GET /api/projects/{project_id}/tool_servers/{tool_server_id}/config` returns one server's full config (command, URL, headers — minus secret values) plus the list of tools it exposes (`available_tools[]` with name, description, inputSchema). Use this when the user says "what is `<tool_server>` set up to do?"

## Tool IDs

**Tool id forms**: `kiln_tool::call_kiln_api` (built-in REST tool) · `mcp::local|remote::<server_id>::<tool_name>` · `kiln_tool::skill::<skill_id>` · `kiln_tool::code::<code_tool_id>` · `kiln_task::<tool_server_id>`.

**The built-in `kiln_tool::call_kiln_api` is hidden from UI tool pickers** (intentional, `tool_api.py`): UI conversations silently drop it while API/eval runs keep it. MCP tools ARE UI-visible.

After a tool server is added, attach its tool to the run config that should use it — tool wiring at the project level isn't enough; the run config must list the tool ID under `tools_config.tools`. A run config cannot be edited, so create a new one with the tool listed (`references/knowledge/model_create_configs.md`).

## See also

When and why, in the knowledge: `references/levers/tool_config.md`, `references/levers/new_tool.md`, `references/improving_agents/playbooks/fit-the-tool-layer-to-the-agent.md`, `references/improving_agents/playbooks/wrong-tool-chosen.md`, `references/improving_agents/playbooks/failure-at-a-tool-call.md`, `references/improving_agents/playbooks/malformed-tool-calls.md`, `references/improving_agents/playbooks/missing-context-the-agent-could-be-given.md`, `references/improving_agents/techniques/cap-and-preview-wrapper.md`, `references/improving_agents/techniques/consolidate-tools.md`, `references/improving_agents/techniques/directive-in-the-tool-response.md`, `references/improving_agents/techniques/errors-the-agent-can-act-on.md`, `references/improving_agents/techniques/guard-tool-calls-at-the-boundary.md`, `references/improving_agents/techniques/new-tool-description.md`, `references/improving_agents/techniques/normalize-inputs-wrapper.md`, `references/improving_agents/techniques/remove-or-scope-tools.md`, `references/improving_agents/techniques/roll-up-tool.md`, `references/improving_agents/smells/fixed-call-chain.md`, `references/improving_agents/smells/general-query-tool-without-a-guide.md`, `references/improving_agents/smells/too-many-tools.md`, `references/improving_agents/smells/tool-results-flood-the-context.md`, `references/improving_agents/smells/tool-search.md`, `references/improving_agents/smells/tools-on-a-live-server.md`, `references/improving_agents/smells/unnecessary-tools.md`, `references/improving_agents/smells/very-long-tool-description.md`.
