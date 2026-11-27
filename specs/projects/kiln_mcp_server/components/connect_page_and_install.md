---
status: complete
---

# Component: Connect page and install guide

How a user gets from the Kiln app, the README or the docs to an agent that has the Kiln MCP server and the stub skill. Covers the Settings callout, the page `/settings/connect_agent`, `agent_install.md`, the stub skill text, the README section, the rename of the existing `kiln_mcp` texts, and the follow-up in the docs repo. Contracts: [functional_spec.md](../functional_spec.md) sections 3, 9, 10, 12, 16 and [ui_design.md](../ui_design.md). The web UI calls no endpoint for this component. This is build step 7 of [architecture.md](../architecture.md) section 6. This doc owns the rename of the `kiln_mcp` texts (section 6); the server doc only points here.

## 1. Files

Web paths are under `app/web_ui/src/routes/(app)/settings/`.

| File | Change |
|---|---|
| `+page.svelte`, `page.test.ts` | Connect callout in the `{:else}` of the update callout (section 2); tests 8.1 |
| `connect_agent/+page.svelte` | New page (3.4). No `+page.ts`: no params, no load |
| `connect_agent/connect_agent.ts` | New: constants and pure functions (3.3) |
| `connect_agent/connect_agent.test.ts`, `connect_agent/page.test.ts` | New (8.2, 8.3) |
| `/docs/agent_install.md` | New; full draft in 4.3 |
| `/README.md` | New section and one Highlights bullet (section 5) |
| `libs/server/kiln_server/mcp/{__init__.py,mcp.py,runtime.py,tool_selection.py,mcp_server_tool_utils.py,README.md}`, `libs/server/README.md`, `.agents/skills/kiln-conventions/references/server_desktop.md` | Text rename (section 6) |

Nothing under `lib/ui/`, `lib/components/` or `app_page.svelte` changes, so the `kiln-ui` gate reports no `SHARED_CONTROL_TOUCHED`.

## 2. Settings callout

Use `Callout` (`lib/ui/callout.svelte`), the component "Update Available" uses. It renders a `CalloutCard`, whose one style is the blue highlight (`border-primary/30 bg-primary/5`). No new prop is needed.

```
{#if $update_info.update_result?.has_update}
  <Callout testid="update-available-callout" ... >   <!-- unchanged -->
{:else}
  <Callout
    testid="connect-agent-callout"
    title="Connect to Claude, Codex, and more"
    description="Use Kiln from your own agent."
    button_label="Connect"
    button_href="/settings/connect_agent"
  >
    <div slot="icon"><TerminalIcon /></div>
  </Callout>
{/if}
```

- **Rule.** One callout at a time. The Connect callout shows whenever `has_update` is not true: no update, check loading, check failed, `update_result` null. It is not dismissible and keeps no state.
- **Known effect.** If the update check ends while Settings is open and finds an update, the update callout replaces this one. The check starts in `routes/(app)/+layout.svelte`, so it has normally ended before the user opens Settings. Accepted.
- **Icon and button.** `TerminalIcon`, already imported by this page; no new icon file. `Callout` renders `<a class="btn btn-primary btn-sm">`: the only primary button on Settings in either state. No row is added to `sections`.
- **Promotion only.** The blue `CalloutCard` treatment is for this promotion on Settings. The Connect page itself does not use it: there the prompt is core content, not a promotion.

## 3. The page `/settings/connect_agent`

### 3.1 Component plan (`.agents/skills/kiln-ui/SKILL.md`, section 2)

Sibling screen: the Edit Task form (`settings/edit_task/[project_id]/[task_id]/`), a reference screen with the same `Settings` breadcrumb and the same width (`max-w-[900px]`). The page reads like one of its fields: a `FormElement` label and description over the content. Read-only content is `Output`, as on the Saved Prompt page.

| Element | House control used | Sibling it matches | Justification if custom |
|---|---|---|---|
| Title, subtitle, breadcrumb | `AppPage` | Edit Task header | |
| "Setup Prompt" label, description, info tooltip | `FormElement inputType="header_only"` | Edit Task field labels; New Code Tool "Python Function" | |
| Prompt text and its copy button | `Output` (default) | Saved Prompt page "Prompt" | |
| "Set Up Manually" | `Collapse` (closed, default fill) | "Advanced Options" on forms | |
| "MCP Server URL" label, description, info tooltip | `FormElement inputType="header_only"` | Edit Task field labels | |
| URL text and its copy button | `Output show_border` | "Preview Data Guide" (an `Output` inside a default `Collapse`) | |
| Vertical rhythm | one container `max-w-[900px] flex flex-col gap-6`; label to content is `FormElement`'s own spacing; children carry no margins | Edit Task (24 between fields) | |

Rules that bite: no `<input>` or `<label>` in the route; no hand-drawn box and no `CalloutCard` (the prompt is content, not a promotion); no bold text for the prompt or URL (`Output` sets their type and carries the copy button); no `aria-expanded` or `{#if open}`; no font or size prop on a shared control. There is no primary button on the page. Expected gate result: 0 FAIL, 0 WARN.

### 3.2 Copy: `Output`'s copy button

The prompt and the URL each render in an `Output`, whose icon button copies `raw_output`. No route-local copy button. `Output` gives no "Copied" feedback and its button has no accessible name; both are owned by the shared control and are not changed here.

### 3.3 `connect_agent.ts`

```
import { dev } from "$app/environment"
import { base_url } from "$lib/api_client"

export const DEFAULT_ORIGIN = "http://localhost:8757"
export const MCP_PATH = "/mcp"
// The one place the guide URL is set. Later: "https://kiln.tech/agent_install.md" (4.1).
export const AGENT_INSTALL_GUIDE_URL =
  "https://raw.githubusercontent.com/Kiln-AI/Kiln/main/docs/agent_install.md"
export const BASE_PROMPT =
  `Install Kiln's app, skill, and MCP following the guide here: ${AGENT_INSTALL_GUIDE_URL}`

export function app_origin(is_dev: boolean = dev): string
export function mcp_url(origin: string): string
export function is_default_address(origin: string): boolean
export function build_prompt(origin: string): string
```

The address rule is the one of architecture section 3, item 11; this is its page side.

- `app_origin`: `base_url` when `is_dev`, otherwise `window.location.origin`. In any production build the UI is served by the Kiln server, so the page origin is the server's real address (the desktop app opens `http://localhost:{port}`, `app/desktop/desktop_main.py:103`). Under `vite dev` the page origin is the Vite server, so the build-time `base_url` (`http://localhost:${VITE_API_PORT || "8757"}`) is used; this is a decision. `window` is read only inside the function.
- `mcp_url`: `origin` without trailing slashes, plus `MCP_PATH`. It always shows the real origin, also when that origin counts as the default: on `http://127.0.0.1:8757` the manual URL is `http://127.0.0.1:8757/mcp`.
- `is_default_address`: true when the origin is plain HTTP on port 8757 at a loopback host name. With `u = new URL(origin)`: `u.protocol === "http:"`, `u.port === "8757"`, and `u.hostname` is one of `localhost`, `127.0.0.1`, `[::1]`. A string that `URL` cannot parse gives false. So `http://127.0.0.1:8757` and `http://[::1]:8757` are the default and get no extra sentence: the guide's `http://localhost:8757` reaches the same server. `DEFAULT_ORIGIN` stays as the name of the address that the guide and the skill are written with.
- `build_prompt`: `BASE_PROMPT` for the default address; otherwise `BASE_PROMPT + "\n\nThe Kiln MCP server is at " + mcp_url(origin) + "."`. The blank line puts the sentence on its own line, so it does not run on from the guide URL.

The two exact strings today (the second for origin `http://localhost:9000`). After the switch in 4.1 both read `… here: https://kiln.tech/agent_install.md`.

```
Install Kiln's app, skill, and MCP following the guide here: https://raw.githubusercontent.com/Kiln-AI/Kiln/main/docs/agent_install.md
Install Kiln's app, skill, and MCP following the guide here: https://raw.githubusercontent.com/Kiln-AI/Kiln/main/docs/agent_install.md

The Kiln MCP server is at http://localhost:9000/mcp.
```

### 3.4 `+page.svelte`

State: three constants set once in the instance script, `origin = app_origin()`, `url = mcp_url(origin)`, `prompt = build_prompt(origin)`. Nothing is reactive; there is no store, `onMount`, loading state or error state. The script also calls `agentInfo.set({ name: "Connect Your Agent", description: "Shows the prompt and the MCP server URL for connecting an agent (Claude Code, Codex, OpenCode or another) to Kiln's MCP server." })`. Imports: `AppPage`, `Collapse`, `FormElement`, `Output`, `./connect_agent`.

```
<AppPage
  title="Connect Your Agent"
  subtitle="Use Kiln from Claude Code, Codex, and other agents."
  breadcrumbs={[{ label: "Settings", href: "/settings" }]}
>
  <div class="max-w-[900px] flex flex-col gap-6">
    <div>
      <FormElement inputType="header_only" id="connect_agent_prompt" label="Setup Prompt"
        description="Paste this into your agent. Then ask it to work with Kiln."
        info_description="Your agent follows Kiln's install guide: it checks that Kiln is running, adds the Kiln MCP server to its settings and creates a Kiln skill."
        value="" />
      <div data-testid="connect-agent-prompt"><Output raw_output={prompt} /></div>
    </div>
    <Collapse title="Set Up Manually">
      <div>
        <FormElement inputType="header_only" id="connect_agent_mcp_url" label="MCP Server URL"
          description="Add this to your agent as an HTTP MCP server."
          info_description="Use the HTTP transport (also called streamable HTTP), with no authentication. If your agent has a tool timeout, set it to 30 minutes: some Kiln calls take minutes."
          value="" />
        <div data-testid="connect-agent-mcp-url"><Output raw_output={url} show_border /></div>
      </div>
    </Collapse>
  </div>
</AppPage>
```

`Output` wraps long text, so the prompt and URL stay readable and the copy icon stays visible at any width. The manual section holds only the URL (UI design).

### 3.5 Static build, accessibility, edge cases

- **Static build.** `routes/+layout.ts` sets `prerender = true` and `ssr = false`; the adapter is `adapter-static`. The route has no parameters, so the build writes `settings/connect_agent.html` and the desktop web host (`HTMLStaticFiles`) serves it at `/settings/connect_agent`. No config change. With `ssr = false` no component code runs at build time; the `window` read still stays inside `app_origin()` because `connect_agent.test.ts` imports the module without a DOM.
- **Why runtime.** The compiled app's `base_url` is always port 8757, so it cannot show a port set with `KILN_LOCAL_API_PORT`.
- **Text.** The prompt and URL are plain selectable text in `Output`, which sets `translate="no"`, so browser translation does not change what the user reads against what is copied.
- **Clipboard failure.** `navigator.clipboard` is missing outside a secure context (Kiln opened over plain HTTP on a non-loopback host, for example with `KILN_LOCAL_API_HOST=0.0.0.0`). The copy icon then does nothing and the user selects the text. No error is shown (UI design: no error state). This is a known limit, accepted. The page still shows the origin the user opened, which is the right address for that user.
- **Owned by shared controls, not changed here.** `Collapse` works from the keyboard through its checkbox, which has no accessible name today. `Output`'s copy button has no accessible name and no "Copied" feedback.

## 4. `agent_install.md`

### 4.1 Location and URL

- File: `/docs/agent_install.md`, in the repo's `docs/` folder. Not inside `app/mcp/`, and never served by `kiln_skill`: it is for an agent that does not have the MCP yet.
- URL now: `https://raw.githubusercontent.com/Kiln-AI/Kiln/main/docs/agent_install.md` (plain text). URL later: `https://kiln.tech/agent_install.md`.
- The switch is one commit: change `AGENT_INSTALL_GUIDE_URL` in `connect_agent.ts` and the prompt line in `README.md`. A test (8.2) fails while the two differ. The guide does not contain its own URL, so it does not change. The docs page (section 7) is updated in its own repo.
- `kiln.tech` should answer that URL with a redirect to the raw GitHub file, or with a copy made at deploy time, so no second file is maintained by hand. Someone with access to the website sets this up; it is a follow-up outside this repo (architecture section 8).

### 4.2 The stub skill: single source

The text of functional spec 9.2 is written once in this repo: in the fenced block of step 3 of the guide. Nothing in the app or the MCP server embeds it. A test (8.2) pins that block to the exact text, so a change to the stub is a deliberate change to the test. The docs page links to the guide and does not repeat the text. The first sentence of its `description` is the shared opening `WHAT_KILN_IS` of the server's `texts.py` (architecture section 3, item 16); the content phase changes that sentence only together with this stub.

Decisions in the guide (4.3):

- The agent does not install the Kiln app itself. It sends the user to the download page and waits, although the prompt says "Install Kiln's app".
- The MCP server and the stub skill are installed at user level, so that they work in every project.
- Codex users invoke the stub as Codex does, with `$kiln`. The guide says so; the Connect page names neither `/kiln` nor `$kiln`, only "ask it to work with Kiln".
- The `405` or `404` test in step 1 relies on the server answering `GET /mcp` with 405 (server doc 2.1).
- Any other answer in step 1 stops the agent, which asks the user. The agent never starts a Kiln server itself: a second server that it starts and registers at user level breaks later sessions.

### 4.3 Full draft

`````
# Install Kiln for your agent

This guide is for an agent such as Claude Code or Codex to follow. If you are a person, give this file's URL to your agent and ask it to follow the guide.

Kiln is a desktop app for building, evaluating and optimizing AI agents. Its built-in MCP server lets you, the agent, use Kiln. Do steps 1 to 4 in order, then report to the user (step 5).

This guide uses Kiln's default address, `http://localhost:8757`, and its default MCP server URL, `http://localhost:8757/mcp`. If the user's prompt gave a different MCP server URL, use that URL in every step, and use it without `/mcp` as Kiln's address.

## Step 1: Check that Kiln is running

```
curl -s http://localhost:8757/ping
```

- The answer `"pong"` means Kiln is running.
- No answer means Kiln is not running, or not installed. Ask the user to start the Kiln app. If they do not have it, send them to https://kiln.tech/download (macOS, Windows, Linux). Do not install the app yourself. Wait for the user, then check again.

Then check that this version of Kiln has the MCP server:

```
curl -s -o /dev/null -w "%{http_code}" http://localhost:8757/mcp
```

- `405` is the expected answer: the server is there, and it accepts only POST.
- `404` means this Kiln is too old. Ask the user to update it (in Kiln: Settings, then Check for Update), then check again.
- Any other answer: stop and ask the user. Never start a Kiln server yourself.

If you cannot make HTTP requests, ask the user to confirm that Kiln is open, and go on.

## Step 2: Add the Kiln MCP server to your configuration

- Name: `kiln`
- Transport: HTTP (also called streamable HTTP), not stdio and not SSE
- URL: `http://localhost:8757/mcp`
- No authentication, no headers, no OAuth
- Tool timeout: 30 minutes, if you have this setting. Some Kiln calls, such as an eval run, take minutes.

Add it at user level, so that it works in every project. If a server named `kiln` is already there, update it; do not add a second one. Change nothing else in the file. "Notes for each agent" says where and how.

## Step 3: Create the `kiln` skill

Create the file `kiln/SKILL.md` in your personal skills folder (see "Notes for each agent"), with exactly this content:

```
---
name: kiln
description: Kiln is an app for building, evaluating and optimizing AI agents. Use when the user asks for /kiln or wants to work with Kiln.
---

Call the `kiln_skill` tool from the `kiln` MCP server to learn how to use Kiln, then follow what it says.

If the `kiln_skill` tool is not available, Kiln is installed but offline: ask the user to start the Kiln app, then try again.
```

The skill only points at the MCP server, so it never needs an update. If you have no skill system, skip this step: everything else still works.

## Step 4: Confirm it works

Call the `kiln_skill` tool of the `kiln` MCP server with no arguments. It works if it returns Kiln's instructions. You do not need to act on them now.

Most agents load MCP servers and skills only when a session starts. If you do not have the `kiln_skill` tool yet, that is expected: check your edit once, do not change it again, and tell the user that a restart is needed.

## Step 5: Tell the user

- What you changed: each file you created or edited, and each command you ran.
- Whether `kiln_skill` worked, or that they must restart you (or start a new session) first.
- How to use it: "Ask me to work with Kiln, or type `/kiln`" (in Codex: `$kiln`).
- That the Kiln app must be running whenever they want you to use Kiln.

## Notes for each agent

`~` is the user's home folder. If a command or a path below does not match your version, follow your own documentation: the result described in steps 2 and 3 is what matters.

### Claude Code

- MCP server: run `claude mcp add --transport http --scope user kiln http://localhost:8757/mcp`, then check with `claude mcp list`. No timeout setting is needed.
- Or by hand, at user level in `~/.claude.json`: add `"kiln": {"type": "http", "url": "http://localhost:8757/mcp"}` to its top-level `mcpServers` object (create the object if it is missing; keep the other keys). The `"type": "http"` field is required.
- Skill: `~/.claude/skills/kiln/SKILL.md`.

### Codex

- MCP server: add this to `~/.codex/config.toml`. Keep `tool_timeout_sec`: the default is 300 seconds, too short for long Kiln calls.

  ```
  [mcp_servers.kiln]
  url = "http://localhost:8757/mcp"
  tool_timeout_sec = 1800
  ```

- Skill: `~/.agents/skills/kiln/SKILL.md`. If `~/.codex/skills/` exists and `~/.agents/skills/` does not, use `~/.codex/skills/kiln/SKILL.md`.
- Codex has no `/kiln` command. The user types `$kiln`, or picks the skill with `/skills`.

### OpenCode

- MCP server: merge this into `~/.config/opencode/opencode.json` (create the file if it is missing; keep the other keys). Keep `timeout` (milliseconds): the default is 5 seconds, and most Kiln calls take longer.

  ```
  {"mcp": {"kiln": {"type": "remote", "url": "http://localhost:8757/mcp",
                    "enabled": true, "oauth": false, "timeout": 1800000}}}
  ```

- Skill: `~/.config/opencode/skills/kiln/SKILL.md`.

### Any other agent

- You need support for MCP servers over HTTP. Add the server from step 2 in your own MCP configuration. Two known forms:
  - Cursor, `~/.cursor/mcp.json`: `{"mcpServers": {"kiln": {"url": "http://localhost:8757/mcp"}}}`
  - VS Code, `.vscode/mcp.json`: `{"servers": {"kiln": {"type": "http", "url": "http://localhost:8757/mcp"}}}`
- If you can run only stdio MCP servers, stop and tell the user: you need a bridge from stdio to HTTP, and this guide does not cover one.
- If you support Agent Skills (a folder with a `SKILL.md` file), put the skill from step 3 in your personal skills folder; `~/.agents/skills/kiln/SKILL.md` is a common place. If you do not, skip step 3.

## Problems

- The `kiln_skill` tool is missing after a restart: Kiln is probably not running. Ask the user to start the Kiln app, then repeat step 1.
- The connection is refused: compare your URL with the one the Kiln app shows under Settings, Connect Your Agent, Set Up Manually.
- Kiln runs on another machine: `localhost` does not reach it, so ask the user for the URL. Files that Kiln saves for you are on Kiln's machine, not yours.
`````

### 4.4 Status of each detail

Every row that is unverified, or verified only from documents or source, is checked against the real CLI in the manual sanity phase (functional spec 16), and the guide is corrected from what that finds.

| Detail | Status |
|---|---|
| `GET /ping` answers `"pong"`; download link `https://kiln.tech/download` | Verified: `libs/server/kiln_server/server.py:149-157`; `README.md:22,51,71` |
| `GET /mcp` answers 405; an older Kiln answers 404 | By design (binding decision; the web host answers a miss with `404.html`). Not run |
| Claude Code: `claude mcp add --transport http --scope user kiln <url>`, `claude mcp list` | Verified from `--help` of Claude Code 2.1.329. Not run against a live Kiln |
| Claude Code: `.mcp.json` shape with `type` required; default tool timeout about 28 hours | From the Claude Code docs (research `mcp_session_scoping`). Not run |
| Claude Code: personal skill folder `~/.claude/skills/` | Unverified (from memory) |
| Codex: keys `mcp_servers.kiln.url` and `tool_timeout_sec`; default 300 s | Verified from Codex source (`main`). Not run |
| Codex: file location `~/.codex/config.toml`; skill folders `~/.agents/skills/` and older `~/.codex/skills/` | Unverified (from memory) |
| Codex: `$kiln` and `/skills`, no `/kiln` | From the Codex docs (research `skill_tool_conventions`). Not run |
| OpenCode: `type`, `url`, `enabled`, `oauth: false`, `timeout`; default 5 s | Verified from the 1.19.6 binary's config schema. Not run |
| OpenCode: global file `~/.config/opencode/opencode.json`; skill folder `~/.config/opencode/skills/` | Unverified (from memory) |
| Cursor and VS Code forms | From research, not run: unverified |
| A new MCP server needs a new agent session; each agent's fetch tool reads the raw GitHub file whole | Unverified for all three |

Left out of the guide on purpose: `codex mcp add` and `opencode mcp add` (unverified; the second is interactive), and project-level install paths.

## 5. README

A new section after `## App Quickstart` and before `## Demo`:

````
## Use Kiln from your own agent

Kiln has a built-in MCP server. Connect Claude Code, Codex, OpenCode or another agent you already use, and it can work in Kiln for you: create tasks, run evals, compare models and improve the agents you build in Kiln. It is free, and it starts with the Kiln app.

Paste this into your agent:

```
Install Kiln's app, skill, and MCP following the guide here: https://raw.githubusercontent.com/Kiln-AI/Kiln/main/docs/agent_install.md
```

Then ask your agent to work with Kiln, or type `/kiln`. The same prompt is in the app under Settings, Connect Your Agent. To set up an agent by hand, see [docs/agent_install.md](docs/agent_install.md).
````

Also one bullet under "Highlights → Iterate, optimize, and collaborate", after the AI Assistant bullet, in that list's style, with the emoji 🔌: `[**Use Kiln from your own agent**](#use-kiln-from-your-own-agent) - Connect Claude Code, Codex or OpenCode to Kiln over MCP.` When the docs page is live, add it to the `## Docs` list.

## 6. Rename of the existing `kiln_mcp` texts (this repo)

This section is the one source for the rename (functional spec 12): every place, the exact new string, and the line references, which are those of the files as they are today. The server doc points here.

Rules:

- The name is **Kiln project tools MCP server**, in sentence case, also in headings and titles.
- The command name `kiln_mcp`, the module path and the entry point stay.
- The protocol does not change. `server_name` (`runtime.py:30`, the `serverInfo.name` of that server, today `"Kiln MCP Server"`) and `instructions` (`runtime.py:34`) keep their values: functional spec 12 renames docs and `--help` text only, and a client may show or log the protocol name.

Under `libs/server/kiln_server/mcp/`:

| Place | New text |
|---|---|
| `mcp.py:1`, module docstring | `"""CLI entry point for the Kiln project tools MCP server (kiln_mcp)."""` |
| `mcp.py:30-32`, the argparse `description` (the string is on line 31); this is the `--help` text | `"Run the Kiln project tools MCP server: it serves one project's tools (such as search tools) to other apps. It does not connect your own agent, such as Claude Code or Codex, to the Kiln app; for that, use the MCP server built into the Kiln app."` |
| `runtime.py:1`, module docstring | `"""Runtime helpers for the Kiln project tools MCP server."""` |
| `runtime.py:30` and `:34` | no change (rule above) |
| `__init__.py:1`, module docstring | `"""The Kiln project tools MCP server: exposes one project's tools over MCP."""` |
| `tool_selection.py:1`, module docstring | `"""Select the Kiln tools that the Kiln project tools MCP server exposes."""` |
| `mcp_server_tool_utils.py:1`, module docstring | `"""Prepare Kiln tools for the Kiln project tools MCP server."""` |
| `README.md:1`, title | `# Kiln project tools MCP server [Beta]` |
| `README.md:3`, after the existing note | A second note: `> To connect your own agent (Claude Code, Codex, OpenCode) to the Kiln app, use the MCP server built into the app: see docs/agent_install.md in the repo. This server is not the way to do that.` |
| `README.md:5` | ``The Kiln project tools MCP server (the `kiln_mcp` command) lets you call one Kiln project's tools, such as a Kiln Search Tool, from any MCP client.`` |
| `README.md:46-66`, the fenced `--help` block | Replace with the real output of `kiln_mcp --help` after the change. The block is stale today: it lacks `--list-tools` |

Elsewhere:

| Place | New text |
|---|---|
| `libs/server/README.md:64`, heading | `## Kiln project tools MCP server` |
| `libs/server/README.md:66`, sentence (line 68, the link to the README, stays) | ``Also included in this package is the Kiln project tools MCP server (the `kiln_mcp` command). It serves one Kiln project's tools to other apps. It is not the way to connect your own agent, such as Claude Code or Codex, to the Kiln app: the app has its own built-in MCP server for that.`` |
| `.agents/skills/kiln-conventions/references/server_desktop.md:44`, the `kiln_mcp` row of the "Startup" table | First cell: ``Kiln project tools MCP server: `kiln_mcp` script (`kiln_server.mcp.mcp:main`)``. The second cell stays |
| The same file, table "Where things go" | A new row: ``A change to the Kiln MCP server (the one a user's own agent, such as Claude Code or Codex, connects to, at `/mcp` in the app)`` goes in ``app/mcp/kiln_mcp_server/``, mounted by `connect_kiln_mcp_server` in `app/desktop/studio_server/kiln_mcp_mount.py` |

`README.md:17` ("via this MCP server") needs no change. No test asserts the old strings today (checked with a search of the repo); the Python tests for `kiln_mcp` must still pass.

## 7. Docs repo follow-up (`Kiln-AI/docs`, outside this repo)

1. **New page "Connect Your Agent"**, intended URL `https://docs.kiln.tech/docs/connect-your-agent`. Content: what it is; the one prompt; what the agent sets up (MCP server `kiln`, stub skill); `/kiln` (`$kiln` in Codex); manual setup (the URL, and a link to the guide's per-agent notes); a non-default address; Kiln must be running, and the offline message; `save_to_tmpfile` files are on Kiln's machine (functional spec 5.7); no authentication, loopback by default; free, with some functions needing Kiln Pro.
2. **New page "Kiln and MCP: which is which"** (functional spec 12), intended URL `https://docs.kiln.tech/docs/kiln-and-mcp`. Four entries, each with its purpose and a link: Kiln MCP server; Kiln project tools MCP server (`kiln_mcp`), with "not the way to connect your own agent"; remote and local MCP tool servers; an MCP tool as a task.
3. Existing page `tools-and-mcp`: a note at the top that links to page 2. Any page that documents `kiln_mcp`: rename to "Kiln project tools MCP server".
4. When page 1 is live, in this repo: add a "Read the Docs" link to the Connect page (`AppPage` `sub_subtitle` and `sub_subtitle_link`) with its URL, and add it to the README `## Docs` list.

Until page 1 exists, the Connect page has no docs link at all (owner decision): a link is added only when the page it points to is live. The slugs `connect-your-agent` and `kiln-and-mcp` are proposals for the docs owner.

## 8. Test plan

### 8.1 `settings/page.test.ts` (add; existing cases stay unchanged)

- No update (`default_update_state`): `connect-agent-callout` present, `update-available-callout` absent. Its text contains the title "Connect to Claude, Codex, and more" and "Use Kiln from your own agent."; its `a` has `href="/settings/connect_agent"` and text "Connect".
- `has_update: true`: `connect-agent-callout` absent, `update-available-callout` present.
- `update_result: null` with `update_loading: true`: `connect-agent-callout` present. The callout precedes the first `h2`.

### 8.2 `connect_agent.test.ts` (no DOM)

- `mcp_url`: `http://localhost:8757` → `http://localhost:8757/mcp`; a trailing slash is removed; `http://127.0.0.1:9000` → `http://127.0.0.1:9000/mcp`.
- `is_default_address`: true for `http://localhost:8757` (also with a trailing slash), `http://127.0.0.1:8757` and `http://[::1]:8757`; false for `http://localhost:9000`, `http://127.0.0.1:9000`, `https://localhost:8757`, `http://192.168.1.5:8757`, `http://kiln.lan:8757` and a string that is not a URL.
- `build_prompt`: the default origin gives exactly `BASE_PROMPT`, and so does `http://127.0.0.1:8757`; `http://localhost:9000` gives `BASE_PROMPT + "\n\nThe Kiln MCP server is at http://localhost:9000/mcp."`; `BASE_PROMPT` starts with "Install Kiln's app, skill, and MCP following the guide here: " and ends with `AGENT_INSTALL_GUIDE_URL`.
- `app_origin(true)` is `base_url`; `app_origin(false)` is the stubbed origin (`vi.stubGlobal("window", { location: { origin: "http://localhost:9000" } })`, as `lib/agent.test.ts` does).
- Repo files, read with `node:fs` from the repo root (seven folders above the test file):
  - `README.md` has a line equal to `BASE_PROMPT` and the heading `## Use Kiln from your own agent`.
  - `agent_install.md` contains the exact stub text of functional spec 9.2 (pinned in the test), `http://localhost:8757/mcp`, `http://localhost:8757/ping`, `https://kiln.tech/download` and the four headings `### Claude Code`, `### Codex`, `### OpenCode`, `### Any other agent`; it has at most 130 lines; it does not contain `AGENT_INSTALL_GUIDE_URL`.

### 8.3 `connect_agent/page.test.ts` (jsdom)

Setup: `vi.mock("./connect_agent", …)` with `importOriginal`, replacing only `app_origin` with a function that returns a test variable; `navigator.clipboard.writeText` is a `vi.fn()`.

- Default address: `connect-agent-prompt` text equals `BASE_PROMPT`; `connect-agent-mcp-url` text is `http://localhost:8757/mcp`.
- Origin `http://127.0.0.1:8757`: the prompt equals `BASE_PROMPT` (no extra sentence); the URL is `http://127.0.0.1:8757/mcp` (the real origin).
- Origin `http://localhost:9000`: the prompt ends with a blank line and "The Kiln MCP server is at http://localhost:9000/mcp."; the URL is `http://localhost:9000/mcp`.
- Header: title "Connect Your Agent"; the subtitle; no "Read the Docs" link; a breadcrumb link "Settings" to `/settings`. The "Setup Prompt" label and its description are present.
- "Set Up Manually" is closed by default: the collapse checkbox is not checked; the "MCP Server URL" label, its description and `connect-agent-mcp-url` are inside the collapse. No element has class `btn-primary`.
- Copy: clicking the copy button inside `connect-agent-prompt` calls `writeText` once with the full prompt (with the extra sentence on the other address); the one inside `connect-agent-mcp-url` calls it with the MCP URL.

### 8.4 Other checks

- From `app/web_ui`: `npm run check`, `lint`, `format_check`, `test_run`, `build`. `bash .agents/skills/kiln-ui/ui_gate.sh --range <base>..<tip>` with 0 FAIL, and the `kiln-ui` handback (plan, gate output, side-by-side with the Edit Task form, fresh-session screenshot review). `lib/agent_coverage.test.ts` passes. Python tests for `kiln_mcp` pass after the text changes of section 6. Two new cases in `libs/server/kiln_server/mcp/test_mcp_server.py`: the name of the server built by `create_fastmcp_server` still starts with `Kiln MCP Server` (the protocol name did not change), and `build_argument_parser().description` starts with "Run the Kiln project tools MCP server".
- Manual sanity phase (functional spec 16): install from the prompt in a fresh agent, with Claude Code and one other agent, on the default address and on another port; each row of table 4.4; `/kiln`; Kiln not running.

## 9. Open items

To verify during implementation:

- **Per-agent details.** Every unverified row of table 4.4. They are checked against the real CLIs in the manual sanity phase (build step 10), and the guide is corrected from what that finds.
- **The `--help` block.** Paste the real output of `kiln_mcp --help` into the README after the change (section 6).
- **The page under `vite dev`.** Check by hand that the prompt and the URL name the API port, not the Vite port (3.3).

Owner decisions are in [architecture.md](../architecture.md) section 11. Item 3 there concerns this component: whether the app release waits for the docs page, so that the interim README link never ships. Follow-ups outside this repo or this project are in architecture section 8: the docs pages and their slugs, `kiln.tech/agent_install.md` and then the switch of 4.1, and an icon of its own for the callout (`TerminalIcon` is also the icon of the "Application Logs" row).
