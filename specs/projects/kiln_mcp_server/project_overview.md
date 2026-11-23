---
status: complete
---

# Kiln MCP Server

Build an MCP server into the Kiln app, so anyone running Kiln can use it from any agent (Claude Code, Codex, etc). Think "local Kiln assistant": add the MCP to your agent, and your agent knows what Kiln is and how to drive it.

This started as "move the harness-tuner MCP into Kiln". After looking at the code, the plan changed: this project is a clean, general Kiln MCP. Fencing, and everything else harness-tuner needs from the MCP, is a second spec: [harness_tuner_port](../harness_tuner_port/project_overview.md).

## Roadmap

1. **This spec:** the MCP server running in the desktop app, with knowledge and APIs. Gets us to a smart agent fast.
2. **Spec two ([harness_tuner_port](../harness_tuner_port/project_overview.md)):** support for fencing, and everything harness-tuner needs.

Both specs are written together, so the planning is aligned. They are built separately.

Not specced now:

- Adopting spec two in the harness-tuner repo (harness-tuner uses the new MCP, and removes its duplicate `kiln-harness-tuner-knowledge`).
- Moving the tuner code into the Kiln repo, bundled into the app (P2, nice to have).

## MCP Server

- Built into the Kiln app. Starting the app starts the MCP.
  - Can be used by any agent, just by connecting via HTTP MCP.
  - Localhost/loopback only (same security as our regular REST API).
- Lives in its own project under `app/mcp`. The desktop app just imports and runs it.
- **Clean new codebase**, not a port of harness-tuner's servers. It builds on Kiln's existing `call_kiln_api` tool. Content is ported in from harness-tuner and the Kiln Assistant afterwards.
- **Two tools, the same for every agent:**
  - `call_kiln_api`: calls Kiln's REST API. We've had good success with one API tool plus a skill that explains how to use it; this is how Kiln Assistant works.
  - `kiln_skill`: the skill (see below).
  - New capabilities are added as REST endpoints, not as more tools.
- **MCP policy:** a per-endpoint tag, like the tags we use today to say whether Kiln Assistant may call an API, but a separate tag with a separate policy. A user's own agent may do more than our cloud agent: the user is taking responsibility for it. Default is everything allowed, with a block tag for rare exceptions. The exception list is an item for later in the design.
- Great errors (not logged in to Pro, etc), so agents can fix all core issues.
- Not to be confused with existing MCP projects in Kiln: adding remote MCP servers, adding a remote agent over MCP as a task, and the `kiln_mcp` CLI in `libs/server/kiln_server/mcp`. We have many MCP integrations, so docs are key:
  - Rename `libs/server/kiln_server/mcp` in its docs and `--help` for clarity (the `kiln_mcp` CLI name can stay), and make clear what it is and isn't.
- We may want to bump the `mcp` dependency as part of this; the current pin is holding us back elsewhere.

## Skill

- `kiln_skill` is a "skill shaped" tool: it returns the root `SKILL.md` if invoked without a reference file, or a reference file if you give it a path.
  - Just adding our MCP adds Kiln to your agent.
  - The tool description is the prompt we inject into every agent.
  - Upgrading Kiln upgrades the skill contents automatically and in sync: no old skills against a new API/MCP version.
- One general skill tree, shared by every agent: what Kiln is and what it can do, how to use the API, plus levers, techniques and guidance for improving agents. The root tool description and `kiln_skill()` give progressive disclosure.
- No gating of skill files by mode. Anyone can read any file.
- Content:
  - Kiln Assistant's general guidance, ported from its server-side skill. That repo is private: the content comes over as a filtered dump, reviewed by a person before it lands here.
  - `kiln-harness-tuner-knowledge` from harness-tuner. Harness-tuner keeps its own copy until the follow-up project removes the duplicate.
  - The API reference, generated with the OSS OpenAPI-to-skill tool we already use for the Kiln Assistant's skill.
- **Open decision** (functional spec or architecture): `/kiln` isn't a thing with only a tool.
  - Option one: the tool description just says "if the user asks for /kiln, they want you to read this tool". Probably works decently, but no nice UI.
  - Option two: also install a very minimal `SKILL.md`: "Kiln is a tool for evaluating and optimizing agents. Call the kiln_skill tool to learn how to use it whenever asked to use /kiln". Tiny file, not expected to be kept in sync, as it just points to the up-to-date tool docs. A simple one-line prompt can create this.

## Kiln Assistant

- Keep it for now. Steal anything we need from its skill for our new skill.
- Sharing its skill with the new main skill is P2. We'll focus on getting people into the Claude version; we can maintain two in parallel for a bit.

## Must leave room for spec two

This spec builds none of the fencing. Its design must not block it:

- Spec two scopes a connection by its URL path. `/mcp` here is the open default.
- Spec two adds no tools and changes no skill files. A scoped connection gets the same two tools and the same API, and a clear error when it goes outside what it was given. So `call_kiln_api` needs one place where a per-connection policy can be applied later.
