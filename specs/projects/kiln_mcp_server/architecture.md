---
status: draft
---

# Architecture: Kiln MCP Server

This project is large enough for a main architecture doc plus component designs. This file holds the overall shape and the decisions that cut across components. The detail a coding agent needs is in the component docs:

| Component doc | Covers |
|---|---|
| [mcp_server_and_api_tool](components/mcp_server_and_api_tool.md) | The `app/mcp` project, mounting in the desktop app, `call_kiln_api`, the MCP policy tag and block list |
| [skill_and_content](components/skill_and_content.md) | `kiln_skill`, the skill tree, the API reference pipeline, the knowledge tooling, the content port and edit |
| [model_info](components/model_info.md) | The model info endpoints and the models.dev cache |
| [connect_page_and_install](components/connect_page_and_install.md) | The Settings callout, the Connect page, `agent_install.md`, the stub skill, README and docs |

## 1. Shape

```
agent (Claude Code, Codex, OpenCode, ...)
   │  HTTP MCP, stateless            http://localhost:8757/mcp
   ▼
Kiln desktop app  (one FastAPI app, one port)
   ├── /mcp        kiln_mcp_server
   │     ├── kiln_skill      reads markdown shipped in the package
   │     └── call_kiln_api   policy check → loopback HTTP → /api/...
   ├── /api/...    the REST API (unchanged, plus /api/model_info/...)
   └── /           the web UI (plus /settings/connect_agent)
```

- The MCP server is a new uv workspace project, `app/mcp`, package `kiln_mcp_server`. The desktop app depends on it, builds the server and mounts it at `/mcp` on the FastAPI app it already runs. `kiln_mcp_server` never imports from `app/desktop`: the desktop passes in what it needs.
- Two tools only. Everything an agent can do is a REST endpoint, reached through `call_kiln_api`. New capability in this project (model info) is added as REST endpoints.
- `call_kiln_api` calls the REST API over loopback HTTP, exactly as the Kiln Assistant's tool does today. Every write goes through the same endpoints as the UI, so validation and git sync behave as they always do. Calling the app in process was rejected: it would buffer whole responses and break streamed endpoints.
- The server keeps no state between requests. There are no sessions, no memory of what an agent has read, and nothing to lose when Kiln restarts.

## 2. Repository layout

New:

```
app/mcp/                              new workspace member (no __init__.py here, ever)
  pyproject.toml
  kiln_mcp_server/
    server.py, ...                    server construction, mounting helpers
    api_tool/ ...                     call_kiln_api: pipeline, route index, policy, temp files, progress
    skill_tool/ ...                   kiln_skill: file index, path rules
    knowledge/ ...                    knowledge checker and index builder (ported from harness-tuner)
    skill/                            the skill tree (package data)
      SKILL.md
      references/{modes,knowledge,knowledge/api_docs,docs,levers,improving_agents}/
app/desktop/studio_server/
  model_info_api.py, api_models/..., services/model_info/...     model info endpoints
app/web_ui/src/routes/(app)/settings/connect_agent/              the Connect page
agent_install.md                      the install guide, at the repo root
.agents/skills/knowledge-maintenance/ the upkeep skill for coding agents
```

Changed:

- `app/desktop/desktop_server.py`, `dev_server.py`: build and mount the MCP server; lifespan.
- `app/desktop/build_desktop_app.sh` (and PyInstaller hooks): bundle the skill tree.
- `libs/core/kiln_ai/tools/built_in_tools/kiln_api_call_tool.py`: a structured result beside the existing string output.
- `libs/server/kiln_server/utils/agent_checks/`: the MCP policy tag.
- Route files that carry a blocked endpoint: one annotation each.
- `app/desktop/studio_server/data_gen_api.py` and four web UI pages: the data guide save moves from `PUT` to `POST`.
- `app/desktop/studio_server/provider_api.py`: the available-models logic becomes reusable.
- `libs/server/kiln_server/mcp/` help text and READMEs: renamed "Kiln project tools MCP server".
- Root `pyproject.toml`, `checks.sh`, the API-bindings CI workflow, `README.md`.

Exact file lists are in the component docs.

## 3. Decisions that cut across components

1. **MCP library.** The locked `mcp` 1.30. No bump in this project. SDK-specific code is kept to the server module and the two tool registrations.
2. **Stateless Streamable HTTP with SSE responses.** Stateless so nothing binds a client to server memory (spec two depends on this). SSE so progress updates can reach the client during a long call.
3. **One policy seam.** Before every REST call, `call_kiln_api` asks one policy object whether the call is allowed. Here it knows only the MCP block tag. Spec two adds a per-connection scope, read from the URL path, in the same place. The seam's signature already takes a connection context so callers do not change later.
4. **MCP policy is a separate tag.** `x-mcp-policy` beside the existing `x-agent-policy`. Absent means allowed. The tool reads it from the app's route objects, not from the OpenAPI document, which is slow to build.
5. **The block list** (owner-approved):
   - the git-sync OAuth steps (one returns a token) and the other git-sync setup endpoints;
   - the native file picker;
   - the Kiln Assistant's own chat endpoints;
   - the endless job-events stream;
   - the browser sign-in step for a Kiln Pro key;
   - the raw settings write;
   - "open a folder / open in the OS" endpoints and binary document download;
   - provider key connect and disconnect.

   Explicitly allowed: marking code tools as trusted, and connecting or editing a local MCP tool server. Reading settings is allowed: the response masks secrets. Spec two will block the local-MCP endpoints on fenced connections.
6. **No `PUT`.** The API has a single `PUT` route (saving a task's data guide). It becomes `POST`, with the UI updated in the same change, so the tool's method list stays as it is and the Assistant can call it too.
7. **The skill is package data.** It ships inside `kiln_mcp_server`, is bundled into the app, and is read with `importlib.resources`. The app address is the only thing the tool ever changes in a file's text.
8. **Generated files are committed and checked.** The API reference is generated by a pinned `openapi2skill` from an in-process dump of the OpenAPI document, with MCP-blocked endpoints removed. A CI check fails when it is stale. The generator needs Python 3.13, so that check runs only there; everything else supports Python 3.10 and up.
9. **Model info lives with the desktop API**, not in `kiln_mcp_server`. It is a normal part of the REST API that any client can use.
10. **Nothing private lands here.** The kiln-server export stays outside the repository. Its code samples are reference only. Each ported content file is reviewed before it is committed.

## 4. Error handling

- **API errors pass through.** A non-2xx answer from the REST API is returned to the agent as data (status code and the API's error body). The agent reads it and reacts.
- **Tool refusals are tool errors with exact text.** A refused path, an unknown endpoint, a blocked endpoint, a body over the limit, an unknown skill path: each is returned as an MCP tool error whose text says what is wrong and what to do. The texts are fixed in the component docs and tested.
- **Unclear API errors are fixed at the endpoint.** A late phase probes the real API through the MCP and fixes unclear errors where they are raised, so every client benefits. Only MCP-specific problems are fixed in the MCP.
- **Outside data fails soft.** If models.dev cannot be reached, model info answers from Kiln's own list and says which source is missing.
- **Logging.** The MCP logs through the app's existing logging setup. Temp-file paths and request paths may be logged; bodies are not.

## 5. Testing

- Unit tests sit beside the source, as elsewhere in the repo, and never reach the network.
- Each step of the `call_kiln_api` pipeline, the route index, the policy tag, the temp-file manager, the path rules of `kiln_skill`, the model info join and the models.dev cache have their own tests.
- One integration test mounts the server on the real desktop app and makes MCP calls end to end with the SDK's client.
- Checks that run as tests or CI steps: the API reference is fresh; every path written in the skill resolves and every file is reachable; the knowledge checker passes; every MCP-blocked route still exists.
- The web page follows the web UI's test conventions.
- The final phase is a manual sanity check with real agents (functional spec section 16). It also verifies the per-agent details in the install guide that could not be checked without the real CLIs.

## 6. Build order

The components depend on each other in this order; the implementation plan follows it.

1. The `app/mcp` project, the server mounted in the desktop app, and `call_kiln_api` with the policy seam.
2. The MCP policy tag, the block list annotations, and the `PUT` to `POST` change.
3. Model info endpoints.
4. `kiln_skill` serving, and the API reference pipeline (it needs the block list).
5. The knowledge tooling port.
6. The content port and edit (it needs 2, 3, 4 and 5: the text must match the block list, the model info endpoints, the generated API docs and the checks).
7. The Connect page, the install guide, README and help-text renames.
8. Probe the real API for unclear errors and missing route descriptions; fix them.
9. Manual sanity check.
10. Optional, only if the sanity check shows a need: a "load the endpoint doc first" check that keeps the server stateless.

## 7. Risks

- **Agent tool timeouts.** The SDK sends progress only when the client asks for it. An agent with a short default timeout and no progress support can give up on a long call. The install guide sets longer timeouts for the agents known to need it; the sanity check confirms it.
- **The content edit is large.** Two sources written for other readers (a dedicated assistant, and fenced loop agents) become one skill for a general coding agent. It is its own phase, done in batches, each verified by a check.
- **Drift while two knowledge copies exist.** Harness-tuner keeps its copy until spec two is adopted. Fixes are ported by hand.
- **Packaging.** The skill tree must be bundled explicitly, and `app/mcp/` must stay a plain folder. Both are covered by tests, but a full packaged build is only verified on a real build.

## 8. Follow-ups outside this spec

- Docs pages in the separate docs repo (the feature page the app links to, and "which MCP is which").
- Publishing `agent_install.md` at `https://kiln.tech/agent_install.md`.
- The web UI's own models.dev price fetch could use the model info endpoints.
- Spec two: fencing, and everything harness-tuner needs.
