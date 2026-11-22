---
name: tools
description: |
  MCP tool server setup: local MCP, remote MCP, Kiln task-as-tool, demo/pre-made tools. Load when: user wants to "add a tool", "connect MCP", "set up web search / Github / Slack / Python interpreter / filesystem", says the agent "needs to call an API", or any mention of integrating an external capability. Owns vocabulary mapping, demo tools list, MCP UI-only-wiring callout (sub-agent wiring lives in references/knowledge/subagents.md), per-type field guidance, and tool selection guidance.
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

**You detect the need and link to the UI.** Tool setup (connecting MCP servers, configuring commands, testing) is complex and best done in the Kiln UI.

1. Recognize that the user's problem is a tool problem (not a prompt or model problem)
2. Suggest the right type of tool (local MCP, remote MCP, Kiln task-as-tool, RAG)
3. Deep-link to the tools UI
4. After setup, remind the user to enable `tools_config` in their run config

## Tool Types

| Type | What It Is | When to Use |
|------|-----------|-------------|
| **Local MCP Server** | A program running locally on the user's machine (typically Python, Node.js, or a uvx/npx-installable CLI). Communicates over stdio. | Custom API wrappers, internal services on a private network, anything the user wants running on their own hardware |
| **Remote MCP Server** | An MCP server reachable over HTTP at a URL the user provides | Hosted/SaaS integrations (Github MCP, Firecrawl, etc.), shared team servers, anything already running somewhere |
| **Kiln Task Tool** | Another Kiln task exposed as a tool | Sub-agent patterns — see `references/knowledge/subagents.md` (full workflow including the user-approval step for wiring lives there) |
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

## ⚠️ MCP wiring is UI-only

**MCP server connect endpoints are denied to the agent** — tool-server creation for arbitrary MCP servers goes through the UI:

- `POST /api/projects/{project_id}/connect_local_mcp`
- `POST /api/projects/{project_id}/connect_remote_mcp`

**Correct flow when the user wants an MCP server wired up:** deep-link to `http://localhost:8757/tools/{project_id}/add_tools` with the tool type identified ("Local MCP" / "Remote MCP" / a specific demo) and the relevant field values pre-filled in your suggestion (name, command, URL, etc.). Offer to explain any field if asked. **Do not** speculate about *why* the endpoint is denied — it just is. Use third-person framing ("the docs note this endpoint is reserved for the UI"), not first-person ("when I try it") — you didn't try it in this session.

**Sub-agent wiring is different.** `POST /api/projects/{project_id}/kiln_task_tool` is allowed, but the agent must **draft the tool body and ask the user for approval before posting** (it adds a tool server to the project). Full flow lives in `references/knowledge/subagents.md`.

The READ side (`GET available_tools`, `GET available_tool_servers`, `GET tool_servers/{id}/config`) is fully callable — use it freely to inspect current state before making suggestions.

## Setup Field Reference

When walking the user through Add Tools in the UI, these are the fields they'll see — explain whichever ones they ask about.

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
1. Create a new Kiln task from one of the wrapped MCP tool's signature (`POST /api/projects/{project_id}/create_task_from_tool` — also UI-driven).
2. Use a wrapper Kiln task that calls the MCP tool as one of its tools.
3. Connect the MCP tool directly as an MCP run config on an existing Kiln task — input/output schemas must match exactly (`POST /api/projects/{project_id}/tasks/{task_id}/mcp_run_config`).

Don't walk the user through SDK code — point at the docs page online and the Add Tools UI.

## Tool selection guidance

Two failure modes worth flagging proactively:

1. **Pick a tool-capable model.** Tool calling needs models trained for it. Pre-flight via `GET /api/model_info/model_details` — the `supports_tools` flag of the provider entry is what matters. Kiln will warn in-UI when the chosen model lacks tool support, but the warning is dismissible — call it out in your recommendation.
2. **Don't add too many tools.** Each tool's name + description is in every prompt; dozens of tools fill the context and dilute attention. Be selective — start with the tools the task actually needs, add more only when a real gap shows up.

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

## Checking Tool State (read-side — fully callable)

These are NOT denied — call them freely to ground recommendations in current state:

- `references/knowledge/api_docs/get_api_projects_project_id_available_tools.md` — `GET /api/projects/{project_id}/available_tools` lists every tool the project can call (across all servers).
- `references/knowledge/api_docs/get_api_projects_project_id_available_tool_servers.md` — `GET /api/projects/{project_id}/available_tool_servers` lists connected tool servers (one row per Local MCP / Remote MCP / Kiln Task server). Returns `missing_secrets` per server — useful to flag when a server is wired but a teammate hasn't entered their key yet.
- `references/knowledge/api_docs/get_api_projects_project_id_tool_servers_tool_server_id_config.md` — `GET /api/projects/{project_id}/tool_servers/{tool_server_id}/config` returns one server's full config (command, URL, headers — minus secret values) plus the list of tools it exposes (`available_tools[]` with name, description, inputSchema). Use this when the user says "what is `<tool_server>` set up to do?"

After the user enables a tool in the UI, remind them to attach it to the run config they want to use it from — tool wiring at the project level isn't enough; the run config must list the tool ID under `tools_config`.
