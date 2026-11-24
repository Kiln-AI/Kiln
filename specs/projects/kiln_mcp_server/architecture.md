---
status: complete
---

# Architecture: Kiln MCP Server

This project is large enough for a main architecture doc plus component designs. This file holds the overall shape and the decisions that cut across components. The detail a coding agent needs is in the component docs:

| Component doc | Covers |
|---|---|
| [mcp_server_and_api_tool](components/mcp_server_and_api_tool.md) | The `app/mcp` project, mounting in the desktop app, `call_kiln_api`, the MCP policy tag and block list |
| [skill_and_content](components/skill_and_content.md) | `kiln_skill`, the skill tree, the API reference pipeline, the knowledge tooling, the content port and edit |
| [model_info](components/model_info.md) | The model info endpoints and the models.dev cache |
| [connect_page_and_install](components/connect_page_and_install.md) | The Settings callout, the Connect page, `agent_install.md`, the stub skill, README and docs, the rename of the old `kiln_mcp` texts |

The record of the block-list review, one row per endpoint, is [research/mcp_block_list_review.md](research/mcp_block_list_review.md).

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
  knowledge_backlog.md                the knowledge backlog: known gaps and pending ideas of the knowledge.
                                      Beside the package, so it is not bundled
  kiln_mcp_server/
    server.py, addresses.py           server construction, address rules
    texts.py                          the server instructions and the tool texts
    api_tool/ ...                     call_kiln_api: pipeline, route index, policy, temp files, progress
    skill_files.py, skill_tool.py     kiln_skill: file index, path rules, the tool
    skill_checks/ ...                 dev tooling: knowledge checker and index builder (ported from
                                      harness-tuner), skill-tree check, API reference pipeline
    skill/                            the skill tree (package data)
      SKILL.md
      references/{modes,knowledge,knowledge/api_docs,docs,levers,improving_agents}/
app/desktop/
  studio_server/kiln_mcp_mount.py     connect_kiln_mcp_server
  studio_server/model_info_api.py, api_models/..., services/model_info/...     model info endpoints
  pyinstaller_hooks/hook-kiln_mcp_server.py     bundles the package data (the skill tree)
  skill_api_reference.py              generates and checks the API reference
  conftest.py                         test fixture for the temp-file folder (section 9)
app/web_ui/src/routes/(app)/settings/connect_agent/              the Connect page
docs/agent_install.md                 the install guide
.agents/skills/knowledge-maintenance/ the upkeep skill for coding agents
.gitattributes                        LF line ends for the skill tree
```

There is no `skill_tool/` package and no `knowledge/` package: the tool is two modules, and the ported knowledge tooling is part of `skill_checks/`.

Changed:

- `app/desktop/desktop_server.py`: mount the MCP server and the model info router; lifespan; shutdown bound (section 9 shows the combined result). `dev_server.py` and `dev_app.py` do not change: the dev server builds the same app.
- `app/desktop/build_desktop_app.sh` does not change: it already passes the hooks folder, and the new hook file does the bundling. `app/desktop/test_pyinstaller_hooks.py` gets the tests.
- `libs/core/kiln_ai/tools/built_in_tools/kiln_api_call_tool.py`: a structured result beside the existing string output.
- `libs/core/kiln_ai/utils/config.py`: the base-URL function and the models.dev off switch.
- `libs/core/kiln_ai/adapters/remote_config.py`: the time of the last good remote model-list load.
- `libs/server/kiln_server/utils/agent_checks/`: the MCP policy tag; new annotation files.
- Route files that carry a blocked endpoint: one annotation each.
- `app/desktop/studio_server/data_gen_api.py` and four web UI pages: the data guide save moves from `PUT` to `POST`. `app/web_ui/src/lib/api_schema.d.ts` is regenerated.
- `app/desktop/studio_server/provider_api.py`: the available-models logic becomes reusable.
- `libs/server/kiln_server/mcp/` docstrings, `--help` text and READMEs: renamed "Kiln project tools MCP server". The protocol name and the MCP `instructions` of that server do not change.
- `app/web_ui/src/routes/(app)/settings/+page.svelte`: the Connect callout.
- Root `pyproject.toml` and `uv.lock`, `app/desktop/pyproject.toml`, root `conftest.py`, `Makefile`, `AGENTS.md`, `checks.sh`, `README.md`, `.agents/skills/kiln-conventions/references/server_desktop.md`.
- CI workflows: `build_and_test.yml`, `build_desktop.yml`, `playwright.yml`, `check_api_bindings.yml`.

Exact file lists are in the component docs. Files that more than one component changes are in section 9.

## 3. Decisions that cut across components

1. **MCP library.** The locked `mcp` 1.30. No bump in this project. SDK imports are limited to the modules that the server component doc lists (its section 1); that list is the only one.
2. **Stateless Streamable HTTP with SSE responses.** Stateless so nothing binds a client to server memory (a later scopes project depends on this). SSE so progress updates can reach the client during a long call.
3. **One policy seam.** Before every REST call, `call_kiln_api` asks one policy object whether the call is allowed. Here it knows only the MCP block tag. A later scopes project adds a per-connection scope, read from the URL path, in the same place. The seam's signature already takes a connection context so callers do not change later.
   - **It covers direct MCP calls only.** A task run whose tools include Kiln's built-in `call_kiln_api` tool (`kiln_tool::call_kiln_api`) can reach every endpoint that the deny list blocks, because the core tool checks no policy. A direct call through the MCP can start such a run. The follow-up scopes project (`project_overview.md`, P2) is where that route is enforced; this project only records it.
4. **MCP policy is a separate tag.** `x-mcp-policy` beside the existing `x-agent-policy`. Absent means allowed. The tool reads it from the app's route objects, not from the OpenAPI document, which is slow to build.
5. **The block list** (owner-approved; 30 operations). The exact rows are in the server component doc, section 6.3. Every row is in one of these groups:
   - every route under `/api/git_sync/`: the OAuth steps (one returns a token), the setup steps, and the per-project sync config, its read included (one simple rule);
   - the native file picker;
   - the Kiln Assistant's own chat endpoints (`POST /api/chat`, `POST /api/chat/execute-tools`);
   - the endless job-events stream;
   - the browser sign-in step for a Kiln Pro key;
   - the raw settings write;
   - "open in the OS": open the logs (`open_logs`), a project folder, a document's folder, a skill's folder;
   - binary document download;
   - provider key connect and disconnect, and adding or removing an OpenAI-compatible provider (the add takes a key, the remove deletes a stored one);
   - granting code trust (`POST /api/projects/{project_id}/add_code_trust`): only the user grants it, on the app page `/settings/trust_code/{project_id}`, which no page of the app links to and the skill gives the agent.

   Explicitly allowed: reading the code trust state (`GET .../add_code_trust`), and connecting or editing a local MCP tool server. Reading settings is allowed: the response masks secrets. The download of an extraction output stays allowed. Spec two will block the local-MCP endpoints on fenced connections. For each blocked capability that a user might ask for, the skill tells the agent to ask the user to do it in the app, with the link to the right page (skill component doc, section 4.4).
6. **No `PUT`.** The API has a single `PUT` route (saving a task's data guide). It becomes `POST`, with the UI updated in the same change, so the tool's method list stays as it is and the Assistant can call it too.
7. **The skill is package data.** It ships inside `kiln_mcp_server`, is bundled into the app, and is read with `importlib.resources`. The app address is the only thing the tool ever changes in a file's text.
8. **Generated files are committed and checked.** The API reference is generated by a pinned `openapi2skill` from an in-process dump of the OpenAPI document, with MCP-blocked endpoints removed. A CI check fails when it is stale. The generator needs Python 3.13, so that check runs only there; everything else supports Python 3.10 and up.
9. **Model info lives with the desktop API**, not in `kiln_mcp_server`. It is a normal part of the REST API that any client can use.
10. **Nothing private lands here.** The source of the Assistant's skill stays outside the repository. Its code samples are reference only. Each ported content file is reviewed before it is committed.
11. **One rule for the app address.** The address that users see (links in the skill, the Connect page, the install guide) is derived in one way.
    - *`kiln_skill`.* The address comes from the host and port that Kiln is bound to, which the desktop passes in. The tool never reads the Host header of a request. A loopback or wildcard bind gives `http://localhost:<port>`. A specific non-loopback host gives `http://<host>:<port>`, with an IPv6 address in brackets.
    - *Default.* The default address is `http://localhost:8757`. The skill text is written with it. The tool replaces that string in the text it serves only when the computed address differs.
    - *Connect page.* The page uses `window.location.origin` (the build-time `base_url` under `vite dev`). Any loopback host name (`localhost`, `127.0.0.1`, `[::1]`) on port 8757 is the default: the prompt gets no extra sentence. The manual URL always shows the real origin plus `/mcp`.
    - *Guide.* The guide is written with the default address, and tells the agent to use the URL from the prompt when the prompt gives one.
    - Accepted effects: behind a forwarded port (`ssh -L 9000:localhost:8757`) the skill's links name the address on Kiln's machine, so that case needs no special handling. With a wildcard bind the skill's links name `localhost`, because the server cannot know which address a remote user opened.
12. **Host check on a loopback bind allows any port.** The allowed hosts are the loopback names with any port (and the bare names), not only the bound port. A forwarded port keeps working, and the port adds nothing against DNS rebinding.
13. **Wildcard binds for the tool's own HTTP calls.** `0.0.0.0` becomes `127.0.0.1` and `::` becomes `[::1]` (an IPv6-only socket does not accept IPv4). This is the target of the loopback call, not the address shown to users (item 11).
14. **What the core refactor changes for the Kiln Assistant.** Three things, all improvements that reach the Assistant (functional spec 5.1): the loopback client ignores proxy settings from the environment (`trust_env=False`); the base URL is right for wildcard and IPv6 hosts; a trailing slash is removed from the path. Everything else the Assistant sees stays byte-identical: tool name, description, schema, output string, error texts.
15. **Three checks stay MCP only:** the unknown-endpoint text, the wrong-method text, and the `query_params` coercion. The two texts need the app's route table, which the core tool does not have, and the hosted Assistant service has its own equivalent check. The coercion belongs to the MCP tool's own argument schema.
16. **The trigger text has one home.** One module, `kiln_mcp_server/texts.py`, holds the server instructions, the two tool descriptions and the `path` argument description. The opening sentence, "Kiln is an app for building, evaluating and optimizing AI agents", is one constant used by the instructions and by the `kiln_skill` description, and a test ties them. The content phase tunes these texts in a batch of its own.

## 4. Error handling

- **API errors pass through.** A non-2xx answer from the REST API is returned to the agent as data (status code and the API's error body). The agent reads it and reacts.
- **Tool refusals are tool errors with exact text.** A refused path, an unknown endpoint, a blocked endpoint, a body over the limit, an unknown skill path: each is returned as an MCP tool error whose text says what is wrong and what to do. The texts are fixed in the component docs and tested.
- **Unclear API errors are fixed at the endpoint.** A late phase probes the real API through the MCP and fixes unclear errors where they are raised, so every client benefits. Only MCP-specific problems are fixed in the MCP. Section 10 has the method.
- **"Not connected" errors the agent cannot fix.** The endpoints that connect Kiln Pro or a provider key are blocked. So the skill says what the agent tells the user: connect in the app, with the link to the Kiln Pro page or the providers page (skill component doc, section 4.4).
- **Outside data fails soft.** If models.dev cannot be reached, model info answers from Kiln's own list and says which source is missing. Its models.dev data is loaded on demand, never on a timer. A request that finds no data, or data older than 6 hours, waits for a fresh load, for 15 seconds at most; if the load fails or is too slow, the request is answered from the last good data, marked stale with its age.
- **Logging.** The MCP logs through the app's existing logging setup. Temp-file paths and request paths may be logged; bodies are not.

## 5. Testing

- Unit tests sit beside the source, as elsewhere in the repo, and never reach the network.
- Each step of the `call_kiln_api` pipeline, the route index, the policy tag, the temp-file manager, the path rules of `kiln_skill`, the model info join and the models.dev cache have their own tests.
- One integration test mounts the server on the real desktop app and makes MCP calls end to end with the SDK's client.
- Checks that run as tests or CI steps: the API reference is fresh; every path written in the skill resolves and every file is reachable; the knowledge checker passes; every MCP-blocked route still exists; no hand-written skill file names a blocked endpoint; after the probe phase, no unblocked route lacks a description.
- An app from `make_app()` can enter its lifespan once, because the MCP session manager runs once per server object. The rule for tests, and the check of the existing tests against it, are in the server component doc, section 10.
- The web page follows the web UI's test conventions.
- The final phase is a manual sanity check with real agents (functional spec section 16). It also verifies the per-agent details in the install guide that could not be checked without the real CLIs.

## 6. Build order

The components depend on each other in this order; the implementation plan follows it. Each component doc's test plan says in which step each of its tests lands.

1. The `app/mcp` project, the server mounted in the desktop app, and `kiln_skill` serving a placeholder skill tree: a minimal hand-written `SKILL.md`, replaced in the content phase. The PyInstaller hook.
2. The `KilnApiCallTool` refactor, the MCP `call_kiln_api` tool with the policy seam, the `x-mcp-policy` tag and the route index, the block list annotations, and the `PUT` to `POST` change. The "exactly two tools" test and the end-to-end test land here.
3. Model info endpoints. The API reference is not regenerated here: its pipeline does not exist yet.
4. The API reference pipeline and its freshness check (the reference is generated for the first time, with the model info endpoints in it); the skill-tree check.
5. The knowledge tooling port, with the maintenance skill and the knowledge backlog.
6. The content port and edit (it needs 2 to 5: the text must match the block list, the model info endpoints, the generated API docs and the checks). Its last batch tunes the server and tool texts.
7. The Connect page, the install guide, README, and the rename of the `kiln_mcp` help text.
8. Probe the real API for unclear errors and missing route descriptions; fix them (section 10).
9. Reviews by people, on the content as it stands after step 8: a security owner reads the sandbox wording in `code_tools.md`, `judge_types.md` and `levers/new_tool.md`; a person confirms the knowledge's public-source claims and approves case studies; the owner reads `SKILL.md`, `train_val_test.md` and the two glue files of the merge (`run_an_experiment.md`, `diagnose_an_agent.md`). Their changes are made before step 10.
10. Manual sanity check.
11. Optional later, only if step 10 shows a need: a "load the endpoint doc first" check that keeps the server stateless.

## 7. Risks

- **Agent tool timeouts.** The SDK sends progress only when the client asks for it. An agent with a short default timeout and no progress support can give up on a long call. The install guide sets longer timeouts for the agents known to need it; the sanity check confirms it.
- **The progress interval is a design value.** It is 2 seconds. The real agents cannot be run in this environment, so the value is confirmed in the manual sanity phase (step 10), which also checks that each agent sends a progress token.
- **The content edit is large.** Two sources written for other readers (a dedicated assistant, and fenced loop agents) become one skill for the user's own agent, such as Claude Code or Codex. It is its own phase, done in batches, each verified by a check. The merge of the two sources follows one rule, so that the edit does not drift into a redesign: the knowledge's method is ported unchanged (section 11, item 1).
- **Drift while two knowledge copies exist.** Harness-tuner keeps its copy until spec two is adopted. The port records the harness-tuner commit it was made from, and later fixes are ported by hand from the diff since that commit (skill component doc, section 9).
- **Packaging.** The skill tree must be bundled explicitly, and `app/mcp/` must stay a plain folder. Both are covered by tests, but a full packaged build is only verified on a real build.

## 8. Follow-ups outside this spec

- Docs pages in the separate docs repo (the feature page, and "which MCP is which"), and their final URLs. When the feature page is live, the Connect page gets its "Read the Docs" link.
- Publishing `agent_install.md` at `https://kiln.tech/agent_install.md`, then the URL switch in this repo.
- The hosted Kiln Assistant: the `POST` data-guide route and the three model info routes change the agent-policy annotation files in this repo. The hosted service picks them up when it next updates its Kiln version. Nothing is done there in this project.
- The web UI's own models.dev price fetch could use the model info endpoints.
- A refresh of the copied help articles (8 public pages have no copy yet). It needs the docs repo.
- Harness-tuner adopts the model info endpoints and drops its copies of the model info code and of the knowledge.
- The harness-tuner skill-authoring guide, which this port leaves out. A separate decision. (`kiln-task-setup` and `experiment-costing` are ported in Phase 19: [skill_and_content](components/skill_and_content.md) section 9.)
- The knowledge file `using_harness_tuner`: how the user's own agent, connected to Kiln with the skill, runs the Kiln Harness Tuner CLI in place of running experiments itself. It is the first new entry of the knowledge backlog. Until it exists, the skill recommends Harness Tuner and gives no CLI steps.
- Tooling to read the noise of an eval. This project adds none, and no guidance of its own on noise.
- Model info: a short cache for the availability check; a hint field for a search that finds nothing under the default filters; a person reads the models.dev terms of use for a desktop app that fetches the file.
- Web UI: an icon of its own for the Connect callout.
- Spec two ([harness_tuner_switchover](../harness_tuner_switchover/project_overview.md)): harness-tuner moves onto Kiln's skill and shared APIs.
- Scopes for MCP connections (fencing): a later P2 project.

## 9. Shared files

These files are changed by more than one component, or by a component and a later step. The combined result is fixed here so that the components do not disagree.

### 9.1 `app/desktop/desktop_server.py`

```
def make_app(tk_root: tk.Tk | None = None, *, host: str | None = None, port: int | None = None):
    setup_litellm_logging()                                  # unchanged start
    ...
    app = kiln_server.make_app(lifespan=lifespan, extra_middleware=[GitSyncMiddleware])
    connect_provider_api(app)
    models_dev_cache = ModelsDevCache(enabled=not Config.shared().skip_models_dev)      # model info
    app.state.models_dev_cache = models_dev_cache
    connect_model_info_api(app, available_models=available_models, models_dev=models_dev_cache)
    connect_prompt_api(app)
    ...                                                      # the other connect_* calls, unchanged order
    connect_jobs_api(app)
    connect_kiln_mcp_server(app, host=bound_host, port=bound_port)      # MCP server
    # Important: webhost must be last, it handles all other URLs
    connect_webhost(app)
    return app

async def lifespan(app: FastAPI):
    ...                                                      # unchanged start
    try:
        await _start_background_syncs()
        async with app.state.kiln_mcp_server.run():          # MCP server
            yield
    finally:
        job_registry.events.shutdown()
        cache = getattr(app.state, "models_dev_cache", None)             # model info
        if cache is not None:
            await cache.aclose()                             # cancels a refresh in flight; does not raise
        try:
            await _stop_background_syncs()
        finally:
            await shutdown_shared_session_manager()
            datamodel_strict_mode.set_strict_mode(original_strict_mode)
```

- **Order of `connect_*` calls.** The model info router can be anywhere after `connect_provider_api(app)`; it is placed directly after it. `connect_kiln_mcp_server` is the last `connect_*` before `connect_webhost`, because the route index is built from the routes that exist at that moment and must see every route.
- **Host and port.** `bound_host` and `bound_port` are the `host` and `port` arguments. `server_config(port, host, tk_root)` passes its own values: `make_app(tk_root=tk_root, host=host, port=port)`. When an argument is `None` (the dev app and most tests call `make_app()` with no argument), `make_app` takes `Config.shared().kiln_local_api_host` and `kiln_local_api_port`, the values the dev server binds to. `connect_kiln_mcp_server` itself never reads `Config`.
- **Lifespan.** The MCP component enters its session manager around the `yield` and adds nothing to the `finally` block. The model info component adds the `aclose()` call to the `finally` block and nothing else.
- **`server_config`** also gets `timeout_graceful_shutdown=2` (server component).

### 9.2 Other shared files

| File | Who changes what |
|---|---|
| Root `conftest.py` | Model info only: one autouse fixture, `skip_models_dev`, which sets `KILN_SKIP_MODELS_DEV=true`. The MCP server adds no fixture here: a root fixture would import `kiln_mcp_server` for every test in the repo |
| `app/desktop/conftest.py` (new) | MCP server only: one autouse fixture, `kiln_mcp_tmp_root`, which points the temp-file folder of a desktop app built in a test at `tmp_path` |
| `libs/core/kiln_ai/utils/config.py` | MCP server: `local_api_base_url(host, port)`, and `Config.kiln_local_api_base_url()` calls it. Model info: the `skip_models_dev` setting |
| Root `pyproject.toml`, `uv.lock` | MCP server: the `app/mcp` workspace member, source and dependency. Skill: the `openapi2skill` dev dependency and its pinned git source |
| `app/desktop/studio_server/provider_api.py` | MCP server: the block annotation on five routes. Model info: the module-level `available_models()` |
| `Makefile` | Skill: the targets `skill_index` and `api_docs`. The existing `annotations` and `schema` targets are used, not changed |
| `AGENTS.md` | Skill: two rows in the checks table (API reference, skill indexes), and one line that names the `knowledge-maintenance` skill and its approval rule |
| `.gitattributes` (new) | Skill: `app/mcp/kiln_mcp_server/skill/** text eol=lf` |
| `checks.sh` | Skill: the API reference check. No other component adds a line |
| `.github/workflows/check_api_bindings.yml` | Skill: the API reference check as a step |
| `.github/workflows/build_and_test.yml`, `build_desktop.yml`, `playwright.yml` | MCP server: the `uv build` step for `app/mcp`, and `app/mcp/**` in the path filters |
| `.agents/skills/kiln-conventions/references/server_desktop.md` | MCP server: one sentence on the MCP policy tag. Connect page component: the `kiln_mcp` row and a row for the new server |
| `app/web_ui/src/lib/api_schema.d.ts`, `libs/server/kiln_server/utils/agent_checks/annotations/` | Generated. Regenerated in step 2 (`POST` data guide), step 3 (model info routes) and step 8 (route descriptions), each time in the change that alters the API |
| `app/mcp/kiln_mcp_server/skill/references/knowledge/api_docs/` | Generated. First written in step 4; regenerated in every later change that alters an unblocked route |

## 10. Probing the API for unclear errors

Build step 8 (functional spec 11). It runs after the content is in place, so the agent that probes has the real skill.

- **Method.** A coding agent drives the real API of a running Kiln through the MCP, against a seeded test project made for the probe, never a user's project. It walks the seed list of functional spec 11 (blocked endpoint, bad path, Kiln Pro not connected or key invalid, no provider for the model, unknown project or task id, validation errors, timeouts), and then every catalogue of the API reference: for each endpoint it makes one call that should work and the calls most likely to go wrong (a missing field, a wrong id, a wrong type). For each unclear error it reads the endpoint's code and fixes the message where it is raised. Only a problem specific to the MCP is fixed in the MCP.
- **The bar for an error.** An error is acceptable when it does three things: it says what is wrong; it names the field or the id; it says what to do next. A message that fails one of the three is fixed.
- **Route descriptions.** Every unblocked route gets an OpenAPI `description` (the handler's docstring, or `description=`). Its first sentence says what the endpoint does, in words an agent can choose by, and fits in the 100 characters that the generator keeps in a catalogue row. The `summary` stays a short name. The measure is the count of catalogue rows with an empty description: 197 of 269 in the measurement made before the block list, zero at the end.
- **Regenerated in the same change.** A changed message or description changes the OpenAPI document. Each such change also regenerates the API reference (`make api_docs`), `api_schema.d.ts` (`make schema`) and the agent-policy annotations (`make annotations`), so the checks stay green.
- **Exit test.** A checked-in test, `app/desktop/studio_server/test_route_descriptions.py`: every operation of `make_app().openapi()` that is not MCP-blocked has a non-empty `description`. The probe findings (endpoint, the old message, the fix, or "left as is" with the reason) are recorded in the phase plan.

## 11. Owner decisions

These were open; the owner has ruled on each.

1. **The merge of the two content sources is approved. It is a port, not a redesign of the method.** The knowledge's method is ported unchanged, with vocabulary rewording only; the Assistant's content stays as "how to do it in Kiln". Three Assistant experiment files are not imported (`experiment_batch.md`, `optimize_quality.md`, `optimize_performance.md`), and each piece of their unique content gets a destination. Two new glue files are written: `run_an_experiment.md`, which opens with the choice between Kiln Harness Tuner (experimentation at scale: the agent dispatches it and never manages it itself) and a by-hand procedure for one or two clear ideas, and `diagnose_an_agent.md` (Kiln API steps only). The improve-task mode becomes the router into the knowledge. The five-owner rule decides every overlap, and no skill file selects, compares or keeps a candidate on the test split. The detail is in the skill component doc, sections 4.5 and 9.1 to 9.4.
2. **Harness-tuner's knowledge backlog is ported**, to `app/mcp/knowledge_backlog.md`: beside the package, so it is not bundled. Entries that concern only harness-tuner's loop code stay behind. The maintenance skill keeps its backlog procedure, with the new path. The first new entry is `using_harness_tuner` (section 8). The detail is in the skill component doc, section 7.
3. **No docs link until the docs page is live.** The Connect page has no "Read the Docs" link in this project. It is added when the docs page exists (section 8).
4. **No licence field** is set in `app/mcp/pyproject.toml`: the package is covered by the repository's licence files and is not published. The package carries the same version as the other workspace members and is bumped with them at release.
5. **Reviews by people are a phase of their own** (build step 9).

Things to verify during implementation are in the "Open items" section of each component doc.
