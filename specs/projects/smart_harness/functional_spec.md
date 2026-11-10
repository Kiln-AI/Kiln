---
status: draft
---

# Functional Spec: Kiln Smart Harness

> **Working draft.** The design is being settled one direction at a time. This file records each decision as it is made, and the spec sections below fill in as directions close. Nothing outside the decision log is agreed yet.

Inputs: [project overview](project_overview.md), [research on routing and decision layers](research/routing_and_decision_layers/summary.md), [how the harness works today](research/current_harness/summary.md), [probe of harness-initiated tool calls](research/harness_tool_call_probe/), [middleware-style code in the code sandbox](research/code_sandbox_middleware/summary.md).

## Goals (proposed, not yet confirmed)

The overview lists mechanisms but does not say what "better" means. Proposed:

1. A Kiln agent spends less time and money per turn by handling known situations without the main model, or with a cheaper setting, and quality as measured by the task's evals does not drop.
2. Every such shortcut is data on the run config. It shows in the UI, it can be compared by evals against the same run config without it, and the optimizer can change it.
3. Every decision a shortcut makes is recorded on the run, so it can be reviewed and turned into eval data.

Not goals: a general workflow engine, or a replacement for the agent loop.

## Decision log

| # | Topic | Decision | Status |
|---|---|---|---|
| 1 | The middleware interface | Getting this interface right is a key design goal of the project and is not to be glossed over. The overview's sketch (answer, tool call, overrides, do nothing) is rough: the interface must cover those cases, but they are not the interface. Earlier lean on style: both decide-and-return and wrap with `next()`. | **Open until architecture**, when signatures are designed. |
| 2 | Hook points (turn start, turn end, each tool call, each LLM call in the tool loop) | None yet. | **Deferred to architecture.** A proposal is wanted there that balances function, complexity and design. Not to be picked in isolation. |
| 3 | Overrides | Overrides chosen at turn start apply to every LLM call in that turn. Overridable: model and provider, thinking level, temperature, top_p. Not overridable: prompt, tools. When the model changes, structured output mode resets to the new model's default. | **Decided** (2026-11-10). Revisit only if architecture adds a per-LLM-call hook. |
| 4 | Harness-initiated tool call (for example "on turn 1, call `get_user_info`") | Direction: it is a real tool call. The harness runs the tool and the conversation records the call and its result the same way it would if the model had asked for it. | **Direction chosen, probe half done.** The [docs check](research/harness_tool_call_probe/docs_probe.md) found the "breaks with thinking on" claim only partly right: current Claude models with adaptive thinking accept it; older Claude with manual-budget thinking, Gemini 3, DeepSeek and Kimi reject it unless a placeholder is added, and Gemini 3 through OpenRouter has no documented fix. The live check is still running. |
| 5 | A declarative rule table (task plus a table mapping its answers to actions) | **Rejected.** It is a DSL Kiln would extend and maintain forever, and a weaker version of code. Code can do anything and agents already know how to write it. Logic lives in code. | **Decided** (2026-11-10). |
| 6 | What the stack is | An ordered list of independent entries, as the overview describes: first turn → tool call; canned answer works → return it; needs more thinking → override; otherwise run normally. Routing logic is never split across entries. Logic more complex than one check is one entry whose code calls other code. | **Decided** (2026-11-10). It restates the overview. |
| 7 | Where middleware code runs | The existing code sandbox. It runs wherever the Kiln library runs: the desktop app, or a script or server that imports the library. It does not run on Kiln's own hosted servers. | **Fact, checked** (2026-11-10). An earlier note in this project wrongly said the sandbox was limited to the desktop app. |
| 8 | Middleware as the abstraction | Code that runs inside the harness around a turn. | **Decided** (2026-11-10). |
| 9 | Middleware as a task, or as code | **Code.** A middleware is stored Python, a sibling of code tools and code judges, that returns an action. Tasks and inline model calls are things the code calls. Accepted costs: no dataset per middleware; an LLM cannot be a middleware without a few lines of code; no general code-task feature. | **Decided** (2026-11-10). |
| 10 | How a middleware is judged | By whether the agent with it still meets the agent's goal, measured by running the whole agent with the agent's evals. The goal of a middleware is the agent's goal. No dataset or eval per middleware is wanted. | **Decided** (2026-11-10). |
| 11 | Which tools a middleware can have the harness run | Only tools from the agent's own tool list. The call and its result go into the model's history, so the model has that tool's definition. | **Decided** (2026-11-10). |
| 12 | When a middleware fails | The turn fails. This covers the code raising an error, running past its time limit, returning something invalid, and the sandbox itself failing. There is no skip-and-continue setting: an author who wants to continue catches the error in the code. | **Decided** (2026-11-10). |
| 13 | Calls the code makes to decide | They are private. An inline model call, a saved task, or a tool on the middleware's own allowlist is never shown to the main model and is not a message in the conversation. These calls count toward cost and latency and are recorded. | **Stated, no objection** (2026-11-10). |

## Open items

Listed so they are not lost. None of these is being worked on until the project owner picks it up.

- **Cost and latency must be correct.** Cost: if middleware makes model calls, their cost counts. Latency: the time middleware takes counts whether or not it calls a model.
- **Trace.** Three requirements from the project owner: the trace looks normal; it works as the history for the next turn on any model; and it shows when there was a settings override, a code-based decision, and so on. A large part of the design, not yet started.
- **Decision-model interface.** Kiln needs a better general interface to decision models, of which there are now several besides Jev, including getting probabilities back. To be fixed in general, outside this project. Middleware code uses whatever that interface returns.
- **Harness-initiated tool calls.** Close decision 4 when the live probe reports.
- **What middleware code can call, and what comes back.** Inline model calls, saved tasks, tools, and continuing the turn.
- **Failure rules.** Timeouts, and what happens when middleware code or a call it makes fails.
- **Scope of this project.** What ships first, including how much UI.
- **Goals.** The proposed goals at the top of this file are not confirmed.

## Deferred to architecture

- Interface style and signatures (decision 1).
- Hook points (decision 2).
- Ordering and merge rules for a stack of middleware, including whether later entries still run in a turn after an earlier entry makes a tool call.
