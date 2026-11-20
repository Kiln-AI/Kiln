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

This is spec one of two. Fencing, and everything else harness-tuner needs, is [kiln_mcp_fencing](../kiln_mcp_fencing/project_overview.md). This spec builds none of that, but must leave room for it (section 12).

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
- More tools, MCP resources, or typed per-feature tools.
- Bumping the `mcp` library. This spec builds on the version Kiln uses when the work starts.
- An automated eval of agents using the MCP.

## 3. User flows

### 3.1 Install from a prompt

1. The user finds one prompt, in the README, in the docs, or on the Connect page in Kiln (section 9):
   > Install Kiln's app, skill, and MCP following the guide here: https://kiln.tech/agent_install.md
2. They paste it into their agent.
3. The agent reads the guide (section 8) and follows it: it checks the Kiln app is installed and running, adds the MCP server to its own configuration, and creates the stub skill.
4. The user can now ask the agent to work with Kiln, or type `/kiln`.

### 3.2 Working with Kiln

1. The user asks for something that involves Kiln ("run my eval and tell me why it scores low").
2. The agent sees the two tools and the short description of `kiln_skill`, and calls `kiln_skill()` to read the root of the skill.
3. It follows links in the skill to the reference files it needs, reading each with `kiln_skill`.
4. It calls `call_kiln_api` to do the work.

### 3.3 `/kiln`

The user types `/kiln`. With the stub skill installed, the agent loads the stub, which tells it to call `kiln_skill`. Without the stub, the `kiln_skill` tool description tells the agent that a request for `/kiln` means "call this tool".

### 3.4 Kiln is not running

The MCP runs inside the Kiln app, so when Kiln is not running the server cannot answer and the agent's MCP client fails to connect. The MCP cannot explain this itself. Two places do:

- The stub skill: "If the `kiln_skill` tool is not available, Kiln is installed but offline: ask the user to start the Kiln app."
- The install guide and docs.

## 4. The server

- **Lifecycle.** The MCP starts and stops with the Kiln server. It is served by the desktop app and by the dev server. It is always on: there is no setting to turn it off in V1.
- **Address.** Same server and port as the REST API, at the path `/mcp`. With defaults that is `http://localhost:8757/mcp`. It follows the port and the host that Kiln is configured to use (`KILN_LOCAL_API_PORT`, `KILN_LOCAL_API_HOST`): wherever the REST API can be reached, so can the MCP. Kiln binds to loopback by default.
- **Transport.** Streamable HTTP. The server keeps no state between requests, so a Kiln restart or an app update needs no reconnect logic: the agent's next call just works, and it gets the new version's tools and skill.
- **Security.** The same as the REST API on the same port: no authentication, reachable only where Kiln is bound. The MCP exposes nothing the REST API does not.
- **Price.** Free for everyone. There is no Kiln Pro check on the MCP. Some API functions need Pro; those return their own errors (section 10).
- **Identity.** The server names itself `kiln` and reports the Kiln app version. Its MCP `instructions` text is the same short text as the `kiln_skill` description (section 6.2), for agents that put server instructions in their system prompt.
- **Surface.** Exactly two tools. No MCP resources and no MCP prompts.
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
| `save_to_tmpfile` | boolean, default `false` | MCP only. See 5.6. |

Result: a JSON object with `status_code` and `body`. A non-2xx answer from the API is returned as data (`status_code` and the API's error body), not raised as a tool failure, so the agent can read the error and react.

### 5.3 Path rules

- Only `/api/...` paths and `/ping` are allowed. The server root also serves the web UI, and a wrong path must not return HTML into the agent's context.
- Paths with `.` or `..` segments (also percent-encoded), a query string or a fragment are refused.
- A refused path gets a helpful message, for example "did you mean `/api/projects`?".

### 5.4 MCP policy

- Every endpoint is allowed by default. A user's own agent may do almost anything: the user is taking responsibility for it.
- An endpoint can carry a block tag for the MCP. A call to a blocked endpoint is refused with a clear error that says the endpoint is not available to agents over MCP.
- This tag is separate from the tags that say what the Kiln Assistant may call. The two policies are independent.
- Blocked endpoints do not appear in the skill's API reference.
- The list of blocked endpoints is settled in the architecture step: start from the endpoints the Assistant is denied today, review each one, and get the list approved.
- The MCP adds no approval step. A call is either allowed or blocked. The agent's own permission prompts are the user's control.

### 5.5 Large responses

The tool guards against a response so large that it floods the agent's context. The design is taken from the guard the Kiln Assistant already has (details to come from the kiln-server export; see section 14). The guard's message tells the agent how to narrow the response (`jq_filter`, paging) and that it can retry with `save_to_tmpfile=true`.

### 5.6 `save_to_tmpfile` (MCP only)

For coding agents, which have shell tools.

- When `true`, the response body is written to a temporary file and the result is `status_code`, `body_path` and the size in bytes, with no `body`. The agent can then use `jq`, `grep` and so on.
- `jq_filter` runs first; the filtered result is what is saved.
- A non-2xx response is returned inline as usual, never saved: errors are small and the agent needs them at once.
- Files go in the OS temp folder under a `kiln_mcp/` subfolder, readable by the current user only. The extension is `.json` when the body is JSON, otherwise `.txt`.
- Files are deleted when Kiln starts, and when they are older than 24 hours.
- The file is on the machine that runs Kiln. An agent on another machine cannot read it; the docs say so.
- The Kiln Assistant does not get this argument: it runs in the cloud and cannot read local files.

### 5.7 Long calls

Some calls run for minutes: eval jobs, and endpoints that stream events.

- For a streaming (SSE) endpoint the tool reads the stream to its end and returns a summary (the number of events and a message), as today. The stream ending does not mean the job succeeded; the skill tells the agent to check status afterwards.
- While a call runs, the tool sends MCP progress updates so agents with short tool timeouts do not give up. The interval is shorter than the shortest known default timeout among the supported agents. The exact number is fixed in the architecture step after testing with the real agents.

## 6. `kiln_skill`

### 6.1 Contract

> **Pending research.** The contract below is the draft. It will be aligned with how Claude Code and OpenCode expose native skills to the model (tool name, argument names, return format), so models use it the way they already use skills. See `research/skill_tool_conventions/`.

- `kiln_skill()` with no path returns the root `SKILL.md`.
- `kiln_skill(path)` returns one file of the skill, as markdown text. The path is relative to the skill root, for example `references/guides/evals.md`. A leading `/` or `./` is accepted.
- An unknown path returns an error that lists the files in the nearest folder that exists, so the agent can correct itself in one step.
- A path that leaves the skill root is refused.
- Every file can be read on every connection. There is no gating.

### 6.2 Description

The tool description is the only Kiln text that is in every connected agent's context all the time. It is short, about 100–150 words:

- what Kiln is, in a sentence or two;
- when to call the tool (before working with Kiln, and whenever unsure how);
- "if the user asks for `/kiln`, call this tool".

The final wording is tuned in the content work.

## 7. Skill content

### 7.1 Tree

```
SKILL.md                     what Kiln is, a map of what it can do,
                             how to use call_kiln_api, links onward
references/
  api/                       generated API reference: catalogues, and one doc per endpoint
  guides/                    Kiln concepts and workflows (from the Kiln Assistant's skill)
  levers/                    what in Kiln an agent builder can change, and how
  improving_agents/          techniques, smells and playbooks for making an agent better
```

This is the starting shape. It is firmed up when the Assistant content arrives.

### 7.2 Sources

- **Kiln Assistant guidance** → `SKILL.md` and `references/guides/`. The Assistant's skill is in a private repo. Its content comes over as a filtered export, and a person reviews it before it is committed here. Nothing private may land in this repo.
- **Harness-tuner knowledge** (`kiln-harness-tuner-knowledge`) → `references/levers/` and `references/improving_agents/`.
  - Port the four folders: `levers/` (moved up to its own top-level folder), `techniques/`, `smells/`, `playbooks/`.
  - Write one new general entry page for them: how to improve an agent with Kiln.
  - Do not port the five role entry files (`planner.md`, `builder.md`, `analyzer.md`, `report.md`, `smells.md`). They stay in harness-tuner; their final home is an open question in spec two.
  - Adapt the text where it names things a general agent does not have (harness-tuner's gateway tools, its roles, its run folder). After the port, nothing in the skill refers to a tool that does not exist on this MCP.
- **API reference** → `references/api/`, generated from Kiln's OpenAPI document with the OSS OpenAPI-to-skill generator that already produces the Assistant's API docs.

### 7.3 Kiln's copy is the only copy

Kiln's copy of the knowledge is set up as the source of truth. Harness-tuner keeps a duplicate for a short time; fixes made there are ported over by hand (by agents) until that copy is deleted. This spec builds no sync between them.

So the upkeep tooling comes with the content:

- the knowledge checker and index builder (today `python -m kiln_harness_tuner.knowledge check|build`);
- the `knowledge-maintenance` skill for coding agents who edit the knowledge;
- the rule that a person approves a case study before it is committed, unless it is clearly public.

### 7.4 Checks

- The API reference is committed to the repo. A CI check fails when it is out of date with the API, in the same way the web UI's API schema is checked today.
- A CI check fails when a link or path inside the skill tree does not resolve to a file.
- The knowledge checker runs in CI.

### 7.5 Packaging

The skill files ship inside the app. The skill a user gets always matches the app version they are running; there is nothing to update separately.

## 8. Install guide and stub skill

### 8.1 `agent_install.md`

One guide, written for an agent to follow. It is published at `https://kiln.tech/agent_install.md`; until then the prompt points at the file on GitHub. The file lives in this repo.

It tells the agent to:

1. Check the Kiln app is installed and running (how to tell; the download link if not).
2. Add the Kiln MCP server to the agent's own configuration: HTTP MCP at `http://localhost:8757/mcp`, named `kiln`.
3. Create the stub skill (8.2) with exactly the given text.
4. Confirm it works: call `kiln_skill`.

It has notes for the three supported agents (Claude Code, Codex, OpenCode) where they differ, and a general section for any other agent that supports HTTP MCP.

We give one prompt, not per-agent commands. Agent CLIs change, and a bare "add MCP" command would not create the stub.

### 8.2 The stub skill

A tiny skill named `kiln`, installed in the agent's own skill folder. Draft text:

```
---
name: kiln
description: Kiln is an app for building, evaluating and optimizing AI agents. Use when the user asks for /kiln or wants to work with Kiln.
---

Call the `kiln_skill` tool from the `kiln` MCP server to learn how to use Kiln, then follow what it says.

If the `kiln_skill` tool is not available, Kiln is installed but offline: ask the user to start the Kiln app, then try again.
```

It gives agents a `/kiln` command and the offline message. It is not kept in sync with the app: it only points at the tool, and the tool always serves the current skill. The stub is optional; everything except `/kiln` and the offline message works without it.

### 8.3 README

The repo README and the docs get a short "Use Kiln from your coding agent" section with the same prompt.

## 9. Connect page

A "Connect your agent" page in Kiln's Settings. Functionally:

- It says what this is in a sentence: use Kiln from Claude Code, Codex and other agents.
- It shows the one prompt from 3.1 with a Copy button.
- When Kiln is not on the default address, the copied prompt also states the real MCP URL, because the guide can only name the default.
- It shows the MCP URL for people who want to configure an agent by hand.
- It links to the docs.

Layout and wording are in the UI design step.

## 10. Errors

Principles:

- An error says what went wrong and what to do about it, in words an agent can act on or pass to the user.
- Fix unclear errors at the REST endpoint, so every API client benefits. Fix in the MCP only when the problem is specific to the MCP (rare).
- No fixed list is written now. The implementation plan has a phase that probes the real API through the MCP, reads the code, finds unclear errors and fixes them.

Seed list for that phase:

- the endpoint is blocked by the MCP policy;
- the path is not allowed;
- Kiln Pro is not connected, or its key is invalid;
- no provider is connected for the model asked for;
- the project or task id was not found;
- request validation errors (422);
- timeouts.

## 11. Docs: which MCP is which

Kiln has several MCP features. The docs name each one and say what it is for:

- **Kiln MCP server** (this spec): connect a coding agent to the Kiln app. Agents list it as `kiln`.
- **Kiln project tools MCP server** (the existing `kiln_mcp` command in `libs/server/kiln_server/mcp`): serves one project's tools to other apps. It is not the way to connect a coding agent to Kiln. The command name stays; its docs and `--help` text are renamed and say what it is and is not.
- **Remote and local MCP tool servers:** give the agents you build in Kiln tools from an MCP server.
- **An MCP tool as a task:** run a remote agent over MCP as a Kiln task.

## 12. Room for spec two

- Spec two scopes a connection by its URL path. `/mcp` in this spec is the open default and keeps that meaning.
- Spec two adds no tools and changes no skill files. A scoped connection gets the same two tools and the same API, and clear errors when it goes outside its scope. So `call_kiln_api` has one place where a per-connection policy can be applied later. In this spec that place applies only the MCP block tag.
- `save_to_tmpfile` will need a folder a fenced agent can read. Tracked in spec two.

## 13. Constraints

- **Python.** The new project supports the same Python versions as the rest of the repo's test matrix (3.10 and up), though the desktop build uses 3.13.
- **Project layout.** The MCP is its own project under `app/mcp`. The desktop app imports and runs it.
- **Clean codebase.** No code is ported from harness-tuner's MCP servers.
- **Writes go through the API.** The tool calls the same REST endpoints the UI does, so everything that happens on a write today (validation, git sync) still happens.
- **Supported agents.** Tested with Claude Code, Codex and OpenCode. Other agents that support HTTP MCP should work and get the general section of the guide.

## 14. Dependencies and open items

- **kiln-server export** (private repo; provided as a filtered, reviewed zip). Needed for: the Assistant's guidance (7.2), the large-response guard design (5.5), and how the OpenAPI-to-skill generator is run (7.2).
- **`kiln_skill` contract** (6.1): pending the skill tool research.
- **MCP block list** (5.4): settled in the architecture step.
- **Progress interval** (5.7): fixed in the architecture step after testing.

## 15. Sign-off

- Unit tests for the server and both tools, and the CI checks in 7.4.
- The last phase of the implementation plan is a manual sanity check. A person runs these with Claude Code and one other supported agent, on a real Kiln app. Expect a lot of iteration on the skill content from what this finds.
  - Install from the prompt, in a fresh agent.
  - `/kiln`.
  - List my projects and tasks.
  - Create a task with a prompt and run it.
  - Run an eval and summarise the results.
  - Find out why an eval scores low, and propose a fix (uses `improving_agents/`).
  - Fetch a large list with `save_to_tmpfile` and query it with `jq`.
  - Use a function that needs Kiln Pro while not connected: the agent explains how to fix it.
  - Kiln not running: the agent tells the user to start Kiln.
