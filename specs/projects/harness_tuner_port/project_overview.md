---
status: canceled
---

> # CANCELED
>
> **This spec was canceled before it was built. It is replaced by a simpler one: [harness_tuner_switchover](../harness_tuner_switchover/project_overview.md).**
>
> It still has value. Built, it would do two things:
>
> 1. Get harness-tuner onto one shared API, with no gateway of its own.
> 2. Block MCP clients from reading val and test data.
>
> But it is huge and risky. It puts scope checks through the core of Kiln's eval and data APIs, and it changes the raw API default. Harness-tuner would get a weaker fence and a much larger API than its gateway gives it today. So we chose the simpler plan: harness-tuner keeps its gateway, and moves onto Kiln's skill and shared APIs.
>
> Scopes for MCP callers are still wanted, as a later P2 project. The decisions reached here are its starting point: this overview, and [scope_decisions.md](scope_decisions.md).
>
> Only this overview and the decisions file were written. There is no functional spec.

# Harness-Tuner Port: Fencing, Tools and Adoption

Complete the port of harness-tuner's skill and tools into Kiln core, then update harness-tuner to use them.

This is spec two of two. Spec one, [kiln_mcp_server](../kiln_mcp_server/project_overview.md), is the MCP server itself: built into the Kiln app, with two tools (`call_kiln_api` and `kiln_skill`), knowledge and APIs. Both specs are written together so the planning is aligned. They are built separately, this one second.

This project started as "fencing". It is now broader: think of it as finishing the move of harness-tuner's skill and tools into Kiln core, and then changing harness-tuner to run on the new version. Fencing is one part of that.

## Why

Harness-tuner runs many agent sessions against Kiln. Each one must be held to its job: no reading of val/test data, and no changes to the evals it is measured with, so the test score stays a true measure. Today harness-tuner does this with its own MCP gateway, its own skills and its own tooling. With this spec, Kiln provides all of it, any MCP client can use it, and harness-tuner drops its own copies.

## Part 1: Scopes per connection

- Same two tools and the same API for every connection. A connection gets a clear error when it goes outside its scope.
- The scope is carried in the MCP URL path. It is self-describing: general settings in the path. No token, and no memory on the server.
- Enforced inside the API. The MCP tool passes the connection's scope to the API on its loopback call, and the API enforces it.
- General settings, not harness-tuner roles. Kiln does not need to know harness-tuner's role names; harness-tuner maps each role to settings.
- Four scopes:
  - `fence_eval_data`: withholds the per-item data of the named splits: the items, their result rows and their traces.
  - `fence_eval_results`: withholds the numbers (scores and summaries) of the named splits.
  - `block_eval_changes`: no changes to evals, judges or eval inputs, and no changes to dataset items that are in an eval split. This is also what stops a withheld item from being un-withheld.
  - `readonly`: only GET requests that do not stream. No exceptions per route or per caller.
- Defaults:
  - **MCP default (`/mcp`):** val and test item data is withheld, and test numbers are withheld. A user can opt out on the URL, or ask for more.
  - **Raw API default:** val and test result rows, their traces, and val and test eval inputs are withheld unless the caller sends an override. The one UI page that warns before showing test results sends it. Held-out items stored as dataset runs stay readable on the raw API, because the Dataset page shows them; the MCP default withholds those too.
  - **Harness-tuner** asks for more than the MCP default: val numbers are withheld too, `block_eval_changes` is on, and its val-reading roles are `readonly`.
- The purpose is to prevent accidental disclosure and accidental overfitting. It is not a defence against a caller that works to get around it. The API enforces only what it controls.
- Kiln's skill tells MCP users about the default withholding and why.
- No project/task pin, and no API allow list. Agents pass project and task ids on every call anyway.
- The scope design needs its own design step.
- A clean design in Kiln. Harness-tuner's gateway is the reference for what the scopes must do. We port the rules, not the code.
- Dropped: "only evals this run created can be edited". It only applied behind harness-tuner's experimental eval-building option.

## Part 2: The rest of the tools, as standard Kiln APIs

Everything harness-tuner's own tooling does that a general MCP client could also use becomes a standard Kiln API, reached through `call_kiln_api`. No new MCP tools.

- A "create skill from a folder" API: create a Kiln skill with its reference files in one step. Replaces harness-tuner's skill installer.
- Noise and significance tooling. Harness-tuner has tooling for run-to-run noise and for whether an eval can show a significant change. Move it into standard APIs that harness-tuner calls, so MCP clients can use it as well. To do first: check exactly what exists there and what each piece needs.
- Scores by split. The existing score summary routes are fixed to the test split; they get an optional `split`. One new route gives a paired comparison of two run configs on a split, without the rows. MCP clients need both to confirm on val by metrics only.
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
- Its role prompts are updated for the switch: they know about the `kiln_skill` tool, and every link to a skill or knowledge file points at the file's new place in Kiln's skill.
- Its own loop code sends the raw API override, because it reads val results in code.
- It uses Kiln's APIs for what Part 2 moves (model info, noise and significance, skill from a folder), and removes its own copies.
- It checks versions both ways.
- **A phase that audits the new skill from the harness-tuner side**, and checks for regressions to core harness-tuner concepts.

## Depends on: the cleanup and robustness project

A separate project, run against main, owns a batch of API fixes that this spec relies on:

- The few-shot and repair prompt generators skip every item that is in an eval split (train, val and test).
- `save_sample` no longer trusts a path or an id from the request.
- Deleting a saved prompt or a code tool fails if it is in use. Prompts get archiving.
- A scan for other places where an immutable object can be deleted or edited.

This spec does not own that work. Its last phase checks that the work was done, and that check blocks the merge.

## Not specced now

- Moving the tuner code into the Kiln repo, bundled into the app (P2, nice to have).
