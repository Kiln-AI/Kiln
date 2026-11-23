---
status: draft
---

# Harness-Tuner Port: Fencing, Tools and Adoption

Complete the port of harness-tuner's skill and tools into Kiln core, then update harness-tuner to use them.

This is spec two of two. Spec one, [kiln_mcp_server](../kiln_mcp_server/project_overview.md), is the MCP server itself: built into the Kiln app, with two tools (`call_kiln_api` and `kiln_skill`), knowledge and APIs. Both specs are written together so the planning is aligned. They are built separately, this one second.

This project started as "fencing". It is now broader: think of it as finishing the move of harness-tuner's skill and tools into Kiln core, and then changing harness-tuner to run on the new version. Fencing is one part of that.

## Why

Harness-tuner runs many agent sessions against Kiln. Each one must be held to its job: its own project and task, and no reading of val/test data, so the test score stays a true measure. Today harness-tuner does this with its own MCP gateway, its own skills and its own tooling. With this spec, Kiln provides all of it, any MCP client can use it, and harness-tuner drops its own copies.

## Part 1: Scoping/fencing permissions per connection

- Same two tools and the same API for every connection. No changes to skills. A scoped connection just gets a clear error when it goes outside what it was given access to.
- The scope is carried in the URL path. `/mcp` stays the open default: everything allowed, except the MCP denies.
- The scope is self-describing: general settings in the path, such as `fence=train`, `project=`, `task=`, `readonly`. No token, and no memory on the server.
- General settings, not harness-tuner roles. Kiln does not need to know harness-tuner's role names; harness-tuner maps each role to settings.
- A project/task allow list as an option. Defaults to all.
- Train-filtered: select APIs error if you try to access val/test data, with a clear error.
- The fenced session design needs its own design step.
- A clean design in Kiln. Harness-tuner's gateway is the reference for what the fence must do (how the train set is worked out, which names are held out, its tests as a checklist). We port the rules, not the code.
- P2, but track it: "only evals this run created can be edited". This rule needs to know what a run created, which can live in the data (a run id tag) rather than in server memory.

## Part 2: The rest of the tools, as standard Kiln APIs

Everything harness-tuner's own tooling does that a general MCP client could also use becomes a standard Kiln API, reached through `call_kiln_api`. No new MCP tools.

- A "create skill from a folder" API: create a Kiln skill with its reference files in one step. Replaces harness-tuner's skill installer.
- Noise and significance tooling. Harness-tuner has tooling for run-to-run noise and for whether an eval can show a significant change. Move it into standard APIs that harness-tuner calls, so MCP clients can use it as well. To do first: check exactly what exists there and what each piece needs.
- Model info: the endpoints are built in spec one, from harness-tuner's implementation. Here, harness-tuner uses them, and keeps its own model policy (which models a run may use) on its side.
- Version alignment between harness-tuner and Kiln, two ways:
  - Harness-tuner checks the Kiln version meets its minimum expected version. Needs a `/version` endpoint in Kiln. Bump whenever harness-tuner depends on new Kiln features/APIs.
  - Kiln returns a `min_supported_harness_tuner_version`. If we change something in the app that breaks older versions of harness-tuner, we bump this. Harness-tuner checks it, sees it's under the min, and asks for an upgrade.
- Anything else the gateway gives harness-tuner today that the two tools don't cover. To be found by going through the gateway's tools in the functional spec.

## Part 3: The rest of the skill

- Finish the port of harness-tuner's skill content into Kiln's skill, on top of what spec one ports (the knowledge).
- **Open:** where harness-tuner's role procedures (planner, builder, analyst, etc) live. Leave it open; the options, in order of preference:
  - Leaning: they become prompts that harness-tuner sends when it starts a sub-agent. They aren't really general enough for the skill.
  - Alternatively, harness-tuner maintains its own harness-tuner skill and points its agents at it. But removing the skill-copying code is a nice benefit of this project, so the first option is preferred.
  - Or they move into `kiln_skill`, clearly marked.
- The backlog item from spec one, `using_harness_tuner`: a skill file that tells a coding agent with `kiln_skill` how to run the harness-tuner CLI instead of running experiments itself.

## Part 4: Update harness-tuner to use the new version

In the harness-tuner repo:

- Its agents connect to the Kiln MCP, each with the scope its job needs. Its own MCP servers (the gateway, `kiln_api_mcp`, the skill installer) are removed.
- It uses Kiln's skill, and removes its duplicate `kiln-harness-tuner-knowledge` and whatever else Part 3 moves.
- It uses Kiln's APIs for what Part 2 moves (model info, noise and significance, skill from a folder), and removes its own copies.
- It checks versions both ways.
- **A phase that audits the new skill from the harness-tuner side**, and checks for regressions to core harness-tuner concepts.

## Not specced now

- Moving the tuner code into the Kiln repo, bundled into the app (P2, nice to have).
