---
status: complete
---

# Kiln MCP Fencing

Support for fencing in the Kiln MCP server, and everything harness-tuner needs from it.

This is spec two of two. Spec one, [kiln_mcp_server](../kiln_mcp_server/project_overview.md), is the MCP server itself: built into the Kiln app, with two tools (`call_kiln_api` and `kiln_skill`), knowledge and APIs. Both specs are written together so the planning is aligned. They are built separately, this one second.

## Why

Harness-tuner runs many agent sessions against Kiln. Each one must be held to its job: its own project and task, and no reading of val/test data, so the test score stays a true measure. Today harness-tuner does this with its own MCP gateway. With this spec, the Kiln MCP can do it, and harness-tuner can drop its gateway.

## Scoping/fencing permissions per connection

- Same two tools and the same API for every connection. No changes to skills. A scoped connection just gets a clear error when it goes outside what it was given access to.
- The scope is carried in the URL path. `/mcp` stays the open default: everything allowed, except the MCP denies.
- The scope is self-describing: general settings in the path, such as `fence=train`, `project=`, `task=`, `readonly`. No token, and no memory on the server.
- General settings, not harness-tuner roles. Kiln does not need to know harness-tuner's role names; harness-tuner maps each role to settings.
- A project/task allow list as an option. Defaults to all.
- Train-filtered: select APIs error if you try to access val/test data, with a clear error.
- The fenced session design needs its own design step.
- A clean design in Kiln. Harness-tuner's gateway is the reference for what the fence must do (how the train set is worked out, which names are held out, its tests as a checklist). We port the rules, not the code.
- P2, but track it: "only evals this run created can be edited". This rule needs to know what a run created, which can live in the data (a run id tag) rather than in server memory.

## Everything else harness-tuner needs

- A "create skill from a folder" API: create a Kiln skill with its reference files in one step. Replaces harness-tuner's skill installer.
- Version alignment between harness-tuner and Kiln, two ways:
  - Harness-tuner checks the Kiln version meets its minimum expected version. Needs a `/version` endpoint in Kiln. Bump whenever harness-tuner depends on new Kiln features/APIs.
  - Kiln returns a `min_supported_harness_tuner_version`. If we change something in the app that breaks older versions of harness-tuner, we bump this. Harness-tuner checks it, sees it's under the min, and asks for an upgrade.
- Model info APIs. Harness-tuner added a model info API (`list_models`, `get_model_details`, `list_providers`), ported from kiln_server: Kiln's published model file joined with models.dev (prices and other details).
  - Consider implementing these as API endpoints in the Kiln desktop server instead of MCP tools, so agents reach them through `call_kiln_api` and we add no more tools.
  - Might need lazy reloading of stale models.dev info. Harness-tuner fetches it once per run, which is fine as its sessions are short lived. Kiln desktop can run for weeks.
- Anything else the gateway gives harness-tuner today that the two tools don't cover. To be found by going through the gateway's tools in the functional spec.

## Open

- Whether harness-tuner's role procedures (planner, builder, analyst, etc) move into `kiln_skill`, clearly marked, or stay in harness-tuner's prompts. Both work.

## Not specced now

- Adopting this in the harness-tuner repo: harness-tuner uses the new MCP, and removes its duplicate `kiln-harness-tuner-knowledge`.
- Moving the tuner code into the Kiln repo, bundled into the app (P2, nice to have).
