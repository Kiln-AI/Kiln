---
status: draft
---

# Functional Spec: Kiln MCP Server

## 1. Summary

The Kiln desktop app serves an MCP server. Any agent that speaks HTTP MCP (Claude Code, Codex, OpenCode and others) can connect to it and then knows what Kiln is and how to drive it: a "local Kiln assistant" inside the user's own agent.

The server has exactly two tools, the same for every agent:

- `call_kiln_api` calls Kiln's REST API.
- `kiln_skill` serves a skill: guidance on what Kiln is, how to use the API, and how to improve agents.

Every capability is a REST endpoint. New capabilities are added as endpoints, not as more tools.

This is spec one of two. Fencing, and everything else harness-tuner needs, is [kiln_mcp_fencing](../kiln_mcp_fencing/project_overview.md). This spec builds none of that, but must leave room for it (section 13).

## 2. Goals and non-goals

Goals:

- Starting Kiln starts the MCP. Nothing else to install or run.
- Adding the MCP to an agent is enough to make that agent useful with Kiln.
- The skill is always the version that matches the running app.
- An agent that hits a problem gets an error it can act on.
- The docs make clear which of Kiln's MCP features is which.

Non-goals (this spec):

- Fencing or scoping a connection (spec two).
- Any change to harness-tuner.
- Replacing or changing the Kiln Assistant. It stays as it is. Sharing one skill between the Assistant and this MCP is P2.
- More tools, or typed per-feature tools.
- Bumping the `mcp` library. This spec builds on the version Kiln uses when the work starts.
- Server memory of a conversation. The server stays stateless.
- An automated eval of agents using the MCP.

## 3. User flows

### 3.1 Install from a prompt

1. The user finds one prompt, in the README, in the docs, or on the Connect page in Kiln (section 10):
   > Install Kiln's app, skill, and MCP following the guide here: https://kiln.tech/agent_install.md
2. They paste it into their agent.
3. The agent reads the guide (section 9) and follows it: it checks the Kiln app is installed and running, adds the MCP server to its own configuration, and creates the stub skill.
4. The user can now ask the agent to work with Kiln, or type `/kiln`.

### 3.2 Working with Kiln

1. The user asks for something that involves Kiln ("run my eval and tell me why it scores low").
2. The agent sees the server's instructions and the two tools, and calls `kiln_skill()` to read the root of the skill.
3. It follows the skill to the reference files it needs, reading each with `kiln_skill`.
4. It calls `call_kiln_api` to do the work. Where it can see the Kiln project's files, it may also read those directly (section 7.4).

### 3.3 `/kiln`

The user types `/kiln`. With the stub skill installed, the agent loads the stub, which tells it to call `kiln_skill`. Without the stub, the server's instructions and the `kiln_skill` description tell the agent that a request for `/kiln` means "call this tool". Agents that show MCP prompts as slash commands also get one from the server itself (section 4).

### 3.4 Kiln is not running

The MCP runs inside the Kiln app, so when Kiln is not running the server cannot answer and the agent's MCP client fails to connect. The MCP cannot explain this itself. Two places do:

- The stub skill: "If the `kiln_skill` tool is not available, Kiln is installed but offline: ask the user to start the Kiln app."
- The install guide and docs.

## 4. The server

- **Lifecycle.** The MCP starts and stops with the Kiln server. It is served by the desktop app and by the dev server. It is always on: there is no setting to turn it off in V1.
- **Address.** Same server and port as the REST API, at the path `/mcp`. With defaults that is `http://localhost:8757/mcp`. It follows the port and the host that Kiln is configured to use (`KILN_LOCAL_API_PORT`, `KILN_LOCAL_API_HOST`): wherever the REST API can be reached, so can the MCP. Kiln binds to loopback by default.
- **Transport.** Streamable HTTP. The server keeps no state between requests, so a Kiln restart or an app update needs no reconnect logic: the agent's next call just works, and it gets the new version's tools and skill.
- **Security.** The same as the REST API on the same port: no authentication, reachable only where Kiln is bound. The MCP exposes nothing the REST API does not.
- **Price.** Free for everyone. There is no Kiln Pro check on the MCP. Some API functions need Pro; those return their own errors (section 11).
- **Identity.** The server names itself `kiln` and reports the Kiln app version.
- **Instructions.** Some agents (Claude Code is one) do not load MCP tool descriptions until the model goes looking for a tool; only the server's `instructions` text and the tool names are in context from the start. So the trigger text (what Kiln is; call `kiln_skill` first; `/kiln` means call it) is in the server `instructions` as well as in the `kiln_skill` description. The first 500 characters stand on their own, and the whole text is under 4,000 characters, to fit the limits of the supported agents. `kiln_skill` is also marked to be loaded up front where an agent supports that.
- **Surface.** Two tools, and one MCP prompt named `kiln`. The prompt returns the same text as `kiln_skill()` with no path. Agents that show MCP prompts as slash commands (Claude Code and OpenCode show it as `/kiln:kiln`) get an entry that always matches the running app. No MCP resources.
- **Concurrency.** Agents may make several calls at once, and several agents may be connected at once.

## 5. `call_kiln_api`

### 5.1 One implementation

Kiln already has a `call_kiln_api` tool: the one the Kiln Assistant uses. The MCP tool wraps the same implementation, so the two do not drift. Improvements made here reach the Assistant too, except where this spec says "MCP only".

### 5.2 Contract

Arguments:

| Argument | Type | Meaning |
|---|---|---|
| `method` | string | `GET`, `POST`, `PATCH` or `DELETE`. |
| `url_path` | string | An API path, such as `/api/projects`. No query string. |
| `body` | object, array, string or none | The JSON request body. Not allowed on `GET` or `DELETE`. |
| `query_params` | object or none | Query parameters. A list value repeats the key. |
| `jq_filter` | string or none | A jq filter applied to a successful JSON response before it is returned. |
| `body_limit` | integer, default `30000` | MCP only. See 5.6. |
| `save_to_tmpfile` | boolean, default `false` | MCP only. See 5.7. |

Result: a JSON object with `status_code` and `body`. A non-2xx answer from the API is returned as data (`status_code` and the API's error body), not raised as a tool failure, so the agent can read the error and react.

### 5.3 Path rules

- Only `/api/...` paths and `/ping` are allowed. The server root also serves the web UI, and a wrong path must not return HTML into the agent's context.
- Paths with `.` or `..` segments (also percent-encoded), a query string or a fragment are refused.
- A refused path gets a helpful message, for example "did you mean `/api/projects`?".
- A trailing slash is removed before the call. Models often add one, and the route would otherwise not be found.

### 5.4 Unknown endpoints

When the method and path match no endpoint of the API, the tool says so and points the agent at the API catalogues in the skill, in place of a bare "not found".

### 5.5 MCP policy

- Every endpoint is allowed by default. A user's own agent may do almost anything: the user is taking responsibility for it.
- An endpoint can carry a block tag for the MCP. A call to a blocked endpoint is refused with a clear error that says the endpoint is not available to agents over MCP.
- This tag is separate from the tags that say what the Kiln Assistant may call. The two policies are independent.
- Blocked endpoints do not appear in the skill's API reference.
- Blocks are rare. Endpoints that return secrets (such as provider API keys) are the first category. The list is settled in the architecture step: start from the endpoints the Assistant is denied today, review each one, and get the list approved.
- The MCP adds no approval step. A call is either allowed or blocked. The agent's own permission prompts are the user's control.

### 5.6 `body_limit` (MCP only)

A guard against a response so large that it floods the agent's context.

- Default `30000` characters. The agent may pass a higher number.
- It applies to `GET` only. A `POST`, `PATCH` or `DELETE` has already done its work; failing it afterwards would invite a retry that repeats the change.
- It is measured on the body that would be returned, after `jq_filter`.
- When the body is over the limit, the tool returns an error and no body:
  > Body too long. Length NNN on limit NNN. Either narrow your request (a `jq_filter`, paging or filter parameters), save it to a file with `save_to_tmpfile`, or call again passing a `body_limit` higher than NNN.
- It does not apply when `save_to_tmpfile` is `true`: nothing large is returned.

### 5.7 `save_to_tmpfile` (MCP only)

For coding agents, which have shell tools.

- When `true`, the response body is written to a temporary file and the result is `status_code`, `body_path` and the size in bytes, with no `body`. The agent can then use `jq`, `grep` and so on.
- `jq_filter` runs first; the filtered result is what is saved.
- A non-2xx response is returned inline as usual, never saved: errors are small and the agent needs them at once.
- Files go in the OS temp folder under a `kiln_mcp/` subfolder, readable by the current user only. The extension is `.json` when the body is JSON, otherwise `.txt`.
- Files are deleted when Kiln starts, and when they are older than 24 hours.
- The file is on the machine that runs Kiln. An agent on another machine cannot read it; the docs say so.
- The Kiln Assistant does not get this argument: it runs in the cloud and cannot read local files.

### 5.8 Long calls

Some calls run for minutes: eval jobs, and endpoints that stream events.

- For a streaming (SSE) endpoint the tool reads the stream to its end and returns a summary (the number of events and a message), as today. The stream ending does not mean the job succeeded; the skill tells the agent to check status afterwards.
- While a call runs, the tool sends MCP progress updates so agents with short tool timeouts do not give up. The interval is shorter than the shortest known default timeout among the supported agents. The exact number is fixed in the architecture step after testing with the real agents.

### 5.9 Optional, later: "load the endpoint doc first"

The Kiln Assistant's service refuses a `call_kiln_api` call until the model has loaded that endpoint's doc earlier in the conversation. This spec does not build that.

- The skill text says to load the endpoint doc before a call, and that is all V1 relies on.
- After the manual sanity check (section 16), if agents are seen calling endpoints wrongly because they skipped the docs, a check can be added as a later, optional phase. If the manual checks show no problem, it is skipped. Newer models may not need it, and we do not assume they do.
- Any such check must keep the server stateless.

## 6. `kiln_skill`

Based on how coding agents expose skills natively ([research](research/skill_tool_conventions/summary.md)). No native skill tool takes a file path: they return the skill's instructions and the model reads further files with its file tool. Our tool does both jobs, because the files are not on the agent's disk.

### 6.1 Contract

- One optional argument, `path`. There is no skill-name argument: the tool serves one skill.
- `kiln_skill()` returns the skill's instructions: one header sentence, then the body of the root `SKILL.md` without its frontmatter. The header says how to read a file the instructions mention, with an example:
  > This skill is served by the `kiln_skill` tool. To read a file this skill references by a relative path, for example `references/knowledge/specs_and_evals.md`, call `kiln_skill` with path "references/knowledge/specs_and_evals.md". Paths are relative to the skill root.
- `kiln_skill(path)` returns that file's text, unchanged.
- A path to a folder returns a listing of the folder.
- An unknown path returns an error that names the bad path and lists the files in the nearest folder that exists, so the agent can correct itself in one step.
- A path that leaves the skill root, or an absolute path, is refused.
- Forgiving input: `./references/x.md` and `skill://kiln/references/x.md` mean `references/x.md`; `SKILL.md` or an empty path means no path; an argument named `resource` is accepted as `path`; a stray `name`, `skill` or `id` argument is ignored.
- Results are plain text.
- Every file can be read on every connection. There is no gating.

### 6.2 Description

The tool description follows the shape of the native skill tools: one imperative line; what Kiln is; "call this tool first, before any other Kiln tool"; one line per argument; "users may ask for it by name (`/kiln`); that is a request to call this tool"; "only paths the instructions list are valid; do not guess".

It is short, about 100–150 words. The same trigger text is in the server instructions (section 4). The final wording is tuned in the content work.

## 7. Skill content

### 7.1 Tree

The skill keeps the layout of the Kiln Assistant's skill, whose files link to each other by full path, and adds the harness-tuner knowledge beside it:

```
SKILL.md                         what Kiln is, how to route a request, the rules for
                                 using the API, and a map of the files below
references/
  modes/                         one file per kind of request (learn about Kiln,
                                 project operations, improve a task, ...)
  knowledge/                     how to do specific things in Kiln
  knowledge/api_docs/            generated API reference: catalogues, and one doc per endpoint
  docs/                          a copy of Kiln's public help articles, with an index
  levers/                        what in Kiln an agent builder can change, and how
  improving_agents/              techniques, smells and playbooks for making an agent better
```

- The tree is a valid Agent Skill named `kiln`, so it can also be served through a standard mechanism later without changing the content.
- Every file is reachable: each knowledge, lever and improving-agents file is listed by a mode (or by a file a mode lists), with its full path and a line on what it holds and when to read it.
- Files refer to each other by the full path from the skill root (`references/knowledge/rag.md`), never by a bare filename, and never by writing out a tool call. The tool adds the "how to read a file" sentence (6.1).

### 7.2 Sources

- **Kiln Assistant's skill** → `SKILL.md`, `references/modes/`, `references/knowledge/`, `references/docs/`. It comes from a private repo as a filtered export that a person has reviewed.
- **Harness-tuner knowledge** (`kiln-harness-tuner-knowledge`) → `references/levers/` and `references/improving_agents/` (`techniques/`, `smells/`, `playbooks/`).
  - The five role entry files (`planner.md`, `builder.md`, `analyzer.md`, `report.md`, `smells.md`) are not ported. They stay in harness-tuner; their final home is an open question in spec two.
  - In their place, the knowledge is wired into the skill's modes, mainly "improve a task".
- **API reference** → `references/knowledge/api_docs/`, generated from Kiln's OpenAPI document with `openapi2skill`, the OSS generator that already produces the Assistant's API docs. Its file names are kept as generated.

### 7.3 Adapting the content

The Assistant's skill was written for a dedicated assistant inside the Kiln app; the knowledge was written for harness-tuner's loop agents. Both are edited for a user's own coding agent. This is real content work and is its own phase in the plan.

- **Identity.** The skill does not take over the agent. It no longer says "you are Kiln Assistant", and its rules (always be in a mode, how to greet, what to do at session start) apply only while the agent is doing Kiln work.
- **Loaded on demand.** The Assistant has `SKILL.md` in context at all times. Here it arrives through a tool call, and can drop out when the agent's context is compacted. Text that assumes it is always present is rewritten.
- **File references.** Every `skill(name="kiln-chat", resource="…")` becomes a plain root-relative path (7.1).
- **Links into the app.** The skill tells the agent to give the user links to pages of the Kiln app, written as paths such as `/optimize/{project_id}/{task_id}`. Those only resolve inside the app. The instructions returned by `kiln_skill()` state the app's real base URL (for example `http://localhost:8757`), and tell the agent to put it in front of every app link.
- **What the agent may do.** The Assistant is denied many endpoints and its skill sends the user to the UI for those ("UI-only"). Wherever the MCP allows an endpoint, that wording is changed so the agent does the work itself. The skill text and the MCP block list (5.5) must agree.
- **Destructive actions.** The skill keeps its guidance to confirm with the user before destructive or irreversible operations.
- **Model info.** The Assistant's three model-info tools are replaced by the model-info endpoints (section 8), called through `call_kiln_api`.
- **Help articles.** Each copied article gets its public URL, which the skill asks the agent to share and which the copies lack today.
- **Harness-tuner wording.** Text that names harness-tuner's gateway tools, its roles or its run folder is rewritten for a general agent. After the port, nothing in the skill refers to a tool that does not exist on this MCP.

### 7.4 New guide: working with a project's files directly

A coding agent can often see the Kiln project's files on disk. The Assistant never could, so its skill says nothing about it. A new knowledge file covers it:

- **Reading files directly is fine.** If reading, grepping or listing the files is faster than the API, do that.
- **Writes always go through the API.** The API runs the validation checks and the necessary side effects. Writing a file directly can invalidate the whole Kiln project.
- **Respect immutability.** Prompts, skills and run configs are linked to eval measurement history. Changing one in place invalidates the measurements. Always add a new copy, so history is kept.

It says nothing about val or test data: only fenced roles are barred from those, and their file access is blocked by other means (spec two).

### 7.5 Kiln's copy of the knowledge is the only copy

Kiln's copy of the harness-tuner knowledge is set up as the source of truth. Harness-tuner keeps a duplicate for a short time; fixes made there are ported over by agents until that copy is deleted. This spec builds no sync between them.

So the upkeep tooling comes with the content:

- the knowledge checker and index builder (today `python -m kiln_harness_tuner.knowledge check|build`);
- the `knowledge-maintenance` skill for coding agents who edit the knowledge;
- the rule that a person approves a case study before it is committed, unless it is clearly public.

### 7.6 Checks

- The API reference is committed to the repo, generated as a whole (never file by file) by a script that pins the generator version. A CI check fails when it is out of date with the API, in the same way the web UI's API schema is checked today.
- A CI check fails when a path written in any skill file does not resolve to a file, or when a file is not reachable from `SKILL.md`.
- The knowledge checker runs in CI.

### 7.7 Packaging

The skill files ship inside the app. The skill a user gets always matches the app version they are running; there is nothing to update separately.

### 7.8 Nothing private lands in this repo

The export from the private repo never enters this repository. Whoever ports a file is responsible for two things: that it works here (correct links, fits this project's goals), and that nothing sensitive from the private repo comes with it. Service code in the export is reference only; it is not copied.

## 8. Model info endpoints

The skill needs model information in many places: choosing a model, prices, finding the exact Kiln model id. Kiln gets REST endpoints for it, reached through `call_kiln_api` like everything else.

- **Basis.** Harness-tuner's model info implementation. It and the Assistant service's version have drifted, and harness-tuner's is the better one. The skill text is updated to match these endpoints.
- **Data.** Kiln's model list joined with the public models.dev catalogue: prices, limits, capabilities, release dates, Kiln's featured ranking and notes.
- **What the endpoints give:**
  - **List models**, with filters (provider, family, tags, capabilities such as tools or vision, reasoning, open weights), a name search, a sort (featured, price, newest) and paging. Each row has the model id, name, featured rank, median price, and its providers with a status for each.
  - **Model details** by Kiln model id: the full record, with per-provider prices, limits, capabilities, thinking levels and what Kiln suggests the model for.
  - **List providers**, each marked connected or not, with a count of models ready to use.
- **Status.** Each provider entry says whether the user can run it now (the provider is connected) or not. Harness-tuner's "allowed by the run's model policy" status is not part of these endpoints.
- **Freshness.** Kiln can run for weeks, so the data is reloaded when it is stale. A failed reload keeps the last good data. Every answer says which sources it has and how old they are. With no network, the endpoints still answer from Kiln's own model list, with prices missing.
- These endpoints are a normal part of the API: the Kiln UI and other clients may use them.

## 9. Install guide and stub skill

### 9.1 `agent_install.md`

One guide, written for an agent to follow. It is published at `https://kiln.tech/agent_install.md`; until then the prompt points at the file on GitHub. The file lives in this repo.

It tells the agent to:

1. Check the Kiln app is installed and running (how to tell; the download link if not).
2. Add the Kiln MCP server to the agent's own configuration: HTTP MCP at `http://localhost:8757/mcp`, named `kiln`.
3. Create the stub skill (9.2) with exactly the given text.
4. Confirm it works: call `kiln_skill`.

It has notes for the three supported agents (Claude Code, Codex, OpenCode) where they differ, and a general section for any other agent that supports HTTP MCP.

We give one prompt, not per-agent commands. Agent CLIs change, and a bare "add MCP" command would not create the stub.

### 9.2 The stub skill

A tiny skill named `kiln`, installed in the agent's own skill folder. Draft text:

```
---
name: kiln
description: Kiln is an app for building, evaluating and optimizing AI agents. Use when the user asks for /kiln or wants to work with Kiln.
---

Call the `kiln_skill` tool from the `kiln` MCP server to learn how to use Kiln, then follow what it says.

If the `kiln_skill` tool is not available, Kiln is installed but offline: ask the user to start the Kiln app, then try again.
```

It gives agents a `/kiln` command and the offline message. It is not kept in sync with the app: it only points at the tool, and the tool always serves the current skill. The stub is optional; everything except a literal `/kiln` and the offline message works without it.

### 9.3 README

The repo README and the docs get a short "Use Kiln from your coding agent" section with the same prompt.

## 10. Connect page

A "Connect your agent" page in Kiln's Settings. Functionally:

- It says what this is in a sentence: use Kiln from Claude Code, Codex and other agents.
- It shows the one prompt from 3.1 with a Copy button.
- When Kiln is not on the default address, the copied prompt also states the real MCP URL, because the guide can only name the default.
- It shows the MCP URL for people who want to configure an agent by hand.
- It links to the docs.

Layout and wording are in the UI design step.

## 11. Errors

Principles:

- An error says what went wrong and what to do about it, in words an agent can act on or pass to the user.
- Fix unclear errors at the REST endpoint, so every API client benefits. Fix in the MCP only when the problem is specific to the MCP (rare).
- No fixed list is written now. The implementation plan has a phase that probes the real API through the MCP, reads the code, finds unclear errors and fixes them.

Seed list for that phase:

- the endpoint is blocked by the MCP policy;
- the path is not allowed, or matches no endpoint;
- Kiln Pro is not connected, or its key is invalid;
- no provider is connected for the model asked for;
- the project or task id was not found;
- request validation errors (422);
- timeouts.

The same phase adds missing descriptions to API routes. Most rows in the generated API catalogues have none today, so the agent must choose an endpoint by its name alone.

## 12. Docs: which MCP is which

Kiln has several MCP features. The docs name each one and say what it is for:

- **Kiln MCP server** (this spec): connect a coding agent to the Kiln app. Agents list it as `kiln`.
- **Kiln project tools MCP server** (the existing `kiln_mcp` command in `libs/server/kiln_server/mcp`): serves one project's tools to other apps. It is not the way to connect a coding agent to Kiln. The command name stays; its docs and `--help` text are renamed and say what it is and is not.
- **Remote and local MCP tool servers:** give the agents you build in Kiln tools from an MCP server.
- **An MCP tool as a task:** run a remote agent over MCP as a Kiln task.

## 13. Room for spec two

- Spec two scopes a connection by its URL path. `/mcp` in this spec is the open default and keeps that meaning.
- Spec two adds no tools and changes no skill files. A scoped connection gets the same two tools and the same API, and clear errors when it goes outside its scope. So `call_kiln_api` has one place where a per-connection policy can be applied later. In this spec that place applies only the MCP block tag.
- The server is stateless here, and spec two relies on that.
- `save_to_tmpfile` will need a folder a fenced agent can read. Tracked in spec two.
- Harness-tuner will use the model info endpoints (section 8) and add its own model policy on top.

## 14. Constraints

- **Python.** The new project supports the same Python versions as the rest of the repo's test matrix (3.10 and up), though the desktop build uses 3.13.
- **Project layout.** The MCP is its own project under `app/mcp`. The desktop app imports and runs it.
- **Clean codebase.** No code is ported from harness-tuner's MCP servers. The model info endpoints are the exception: they are built from harness-tuner's model info code.
- **Writes go through the API.** The tool calls the same REST endpoints the UI does, so everything that happens on a write today (validation, git sync) still happens.
- **Supported agents.** Tested with Claude Code, Codex and OpenCode. Other agents that support HTTP MCP should work and get the general section of the guide.

## 15. Open items

- **MCP block list** (5.5): settled in the architecture step.
- **Progress interval** (5.8): fixed in the architecture step after testing.
- **A person's call before publishing:** two of the Assistant's knowledge files (`code_tools.md`, `judge_types.md`) say that user code runs with no network or filesystem sandbox. This is a fact about the public app; a security owner should see the wording before it ships in the skill.

## 16. Sign-off

- Unit tests for the server, both tools and the model info endpoints, and the CI checks in 7.6.
- The last phase of the implementation plan is a manual sanity check. A person runs these with Claude Code and one other supported agent, on a real Kiln app. Expect a lot of iteration on the skill content from what this finds.
  - Install from the prompt, in a fresh agent.
  - `/kiln`.
  - List my projects and tasks.
  - Create a task with a prompt and run it.
  - Pick a model for a task, using the model info endpoints.
  - Run an eval and summarise the results.
  - Find out why an eval scores low, and propose a fix (uses `improving_agents/`).
  - Read project files directly to answer a question, then make a change through the API.
  - Fetch a large list: hit the `body_limit` error, then use `save_to_tmpfile` and query the file with `jq`.
  - Use a function that needs Kiln Pro while not connected: the agent explains how to fix it.
  - Kiln not running: the agent tells the user to start Kiln.
- After the sanity check, decide whether the optional "load the endpoint doc first" check (5.9) is needed.
