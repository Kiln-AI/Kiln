---
status: complete
---

# Harness Tuner Switchover

Move harness-tuner onto Kiln's skill and shared APIs. Harness-tuner keeps its gateway.

This is spec two of two. Spec one, [kiln_mcp_server](../kiln_mcp_server/project_overview.md), is the MCP server itself: built into the Kiln app, with two tools (`call_kiln_api` and `kiln_skill`), knowledge and APIs.

It replaces [harness_tuner_port](../harness_tuner_port/project_overview.md), which was canceled. That spec removed harness-tuner's gateway and put scope checks through Kiln's core APIs in its place. It was huge and risky, and harness-tuner would have got a weaker fence and a much larger API than it has today. This spec is the simpler plan.

## Why

After spec one, harness-tuner holds copies of things Kiln now owns: the knowledge about improving agents, the API reference, a `call_kiln_api` server, the model catalogue. It also has tools of its own that any MCP client could use, such as the noise and significance checks, and it installs skills by writing to the project folder.

With this spec, harness-tuner drops the copies and reads Kiln's. Its general tools become standard Kiln APIs. What is special to the loop stays in harness-tuner.

## What stays in harness-tuner

- **The gateway.** It is the loop's fence: per-role typed tools, train-only reads, frozen evals. It works, it is tested, and nothing in Kiln replaces it.
- The role procedures (planner, builder, analyst and the others), and the baseline review step that looks for the smells code cannot detect.
- The model policy: which models a run may use.
- The loop's own policy: refusing an underpowered run, the stop rules, the promotion rules, and the CLI options.

## Part 1: Kiln APIs

All additive. Each is a standard Kiln API that any MCP client reaches through `call_kiln_api`. No new MCP tools.

- **Noise and significance**, with every number and definition kept as harness-tuner has it:
  - a significance-floor calculation on the existing statistics route;
  - a detectability read for a run config: can its evals show an improvement at all;
  - a noise-check estimate: the sample and the expected cost, before anything is spent;
  - a noise-check job: runs the whole check on the server, on train only, with a spending cap.
- **Smell check.** One API checks a run config for the five smells that harness-tuner detects in code today: a very long prompt, a very long tool description, a very long skill description, too many tools, and an old model. It returns what it found, with each limit and its source. The limits move with it.
- **Scores by split.** The score summary routes are fixed to the test split today; they get an optional `split`. One new route gives a paired comparison of two run configs on a split, without the rows.
- **Skill bundles.** Create a Kiln skill with its reference files in one step, and read every file of a skill back. Replaces harness-tuner's skill installer, which writes to the project folder.
- **Version alignment**, two ways:
  - Harness-tuner checks that the Kiln version meets its minimum. Needs a version endpoint in Kiln.
  - Kiln returns a `min_supported_harness_tuner_version`. Harness-tuner checks it, and asks for an upgrade when it is under the minimum.
- **Model info.** The endpoints are built in spec one, from harness-tuner's implementation. Here, harness-tuner uses them.

## Part 2: Kiln's skill

- A new skill file about statistics: noise, detectability and significance, and the calls for each. Linked from the run-experiments doc. The skill is still changing on another branch, so this spec says "find the right place to integrate", not a fixed path.
- The five smell documents that code can detect name the smell check call.
- `using_harness_tuner`: tells a coding agent with `kiln_skill` how to run the harness-tuner CLI instead of running experiments at scale itself.

## Part 3: Update harness-tuner

In the harness-tuner repo:

- It reads Kiln's skill in place of its own `kiln-harness-tuner-knowledge` copy.
- Its role prompts are updated for the switch: they know about `kiln_skill`, every link to a skill or knowledge file points at the file's new place, and they carry the rules a non-interactive agent needs when it reads a skill written for a chat.
- It removes its duplicates: the knowledge copy, the `kiln-api` reference docs, `kiln_api_mcp`, the model catalogue and the skill installer.
- Its gateway tools and loop code call the new Kiln APIs where one exists, and its own copies of that code go: the noise and significance code, and the smell detectors.
- It checks versions both ways.
- **A phase that audits the result from the harness-tuner side**, and checks for regressions to core harness-tuner concepts.

## Must be integrated before speccing is complete

[research/harness_tuner_switchover_requirements.md](research/harness_tuner_switchover_requirements.md) was written during the build of spec one. It lists what to watch for in the switchover (SR1 to SR18). The functional spec must work each one in, or say why not.

## Decided

- **How loop agents read Kiln's skill.** The gateway passes `kiln_skill` through to the running Kiln, so the skill always matches the app version and nothing is copied. Harness-tuner's own code reads the knowledge through the same call.
- **Where the role procedures live.** Harness-tuner keeps its role skills as they are, with their links re-pointed at Kiln's skill. Turning them into prompts sent at sub-agent start is left for later; it is recorded as a goal in the canceled spec.

## Not in this spec

- Scopes for MCP connections, such as withholding val and test data from MCP clients. Wanted, as a later P2 project. The canceled spec holds the decisions reached so far.
- The API cleanup and robustness project. It is a separate project, and this spec does not depend on it.
- Moving the tuner code into the Kiln repo, bundled into the app (P2, nice to have).
