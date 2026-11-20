---
status: draft
---

# Kiln MCP Server

Move the MCP server in harness-tuner into the Kiln repo, under the `app/desktop` folder. The goal is to enable anyone running the Kiln app to use the MCP server in any agent (Claude Code, Codex, etc).

This is cross repo: moving a bunch from harness-tuner and server into the Kiln main repo. The spec lives in the Kiln repo.

## Scope

This project is focused on moving the harness-tuner MCP into Kiln, and updating harness-tuner to use it from there. Not "expand the MCP to be better at general purpose questions" yet — that will be a follow-up.

## MCP Server

- The MCP server is built into the Kiln app. Starting the app starts the MCP.
  - Can be used by any agent, just by connecting via HTTP MCP.
  - Localhost/loopback only (same security as our regular REST API). Would have simplified harness-tuner too: just installing Kiln gets the needed MCP services.
- MCP server code lives under `app/desktop` — source available but not open source. Moved from harness-tuner, then enhanced.
- Great errors (Kiln not running, not logged in to Pro, etc), so agents can fix all core issues.
- MCP modality: the harness tuner spins up various subsets of the MCP API, depending on the agent using it. How we support that on this MCP is TBD: separate endpoints, per-session filter, port per role, etc. Need to look at how the MCP lib works.
- Not to be confused with existing MCP projects in Kiln: adding remote MCP servers, and adding a remote agent over MCP as a task.

## Skill

- Unify a few skills we have:
  - Harness-tuner: move into the core repo, one shared location.
  - Server-side Assistant skill: borrow anything we need from there.
- Add some "general" skill files: what Kiln is, etc. The harness-tuner skill is very focused at specific agents with very focused prompts. Kiln inside Claude Code is much more general. This is probably mostly solved by the Assistant skill merge, as it has a lot of that.
- Distribution:
  - Packaging with the app would make sense: the skill version should be aligned to the MCP/API version. But that creates a maintenance task to update the skill on app updates… unless it's not a "real" skill (copied around).
  - Better(?): a `kiln_skill()` tool built into our MCP that's "skill shaped" (returns the root `SKILL.md` if invoked without a reference file, or a reference file if you give it a path). Benefits:
    - Just adding our MCP adds Kiln to your agent.
    - The tool description is the prompt we inject into every agent.
    - Upgrading Kiln upgrades skill contents automatically and in sync: no worrying about old skills against a new API/MCP version.
    - Downside: `/kiln` isn't a thing.
      - Option one: the tool description just says "if the user asks for /kiln, they want you to read this tool". Probably works decently, but no nice UI.
      - Option two: install a very minimal `SKILL.md` to make this work: "Kiln is a tool for evaluating and optimizing agents. Call the kiln_skill tool to learn how to use it whenever asked to use /kiln". Tiny file, not expected to be kept in sync with the MCP, as it just points to the up-to-date tool docs. A simple one-line prompt can create this.

## Kiln Assistant

- Keep it for now. Steal anything we need from its skill for our new skill.
- Sharing its skill with the new main skill is P2 for now. We'll focus on getting people into the Claude version; we can maintain two in parallel for a bit.

## Harness-tuner

- It gets simpler. It uses the MCP and skill from the Kiln app itself. Remove them from that repo.
- It needs to check that the installed version of HT works with the installed version of Kiln, two ways:
  - Harness tuner checks the Kiln version meets its minimum expected version (>1.2.1 now). Might need to add a `/version` endpoint to Kiln. Bump whenever harness tuner depends on new Kiln features/APIs.
  - Kiln app adds an API that returns `min_supported_harness_tuner_version`. If we change something in the app that breaks older versions of harness tuner, we bump this. HT checks it, sees it's under the min, asks for an upgrade.
- There's a case for building harness tuner into Kiln too… but not required in V1.
