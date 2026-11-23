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
- Or by hand, in a project's `.mcp.json`: `{"mcpServers": {"kiln": {"type": "http", "url": "http://localhost:8757/mcp"}}}`. The `"type": "http"` field is required.
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
