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
| 1 | Interface style: wrap with `next()`, or decide-and-return-an-action | Lean: both. Decide-style for every kind of middleware; wrap-style for in-process Python. | **Open until architecture**, when signatures are designed. |
| 2 | Hook points (turn start, turn end, each tool call, each LLM call in the tool loop) | None yet. | **Deferred to architecture.** A proposal is wanted there that balances function, complexity and design. Not to be picked in isolation. |
| 3 | Overrides | Overrides chosen at turn start apply to every LLM call in that turn. Overridable: model and provider, thinking level, temperature, top_p. Not overridable: prompt, tools. When the model changes, structured output mode resets to the new model's default. | **Decided** (2026-11-10). Revisit only if architecture adds a per-LLM-call hook. |
| 4 | Harness-initiated tool call (for example "on turn 1, call `get_user_info`") | Direction: it is a real tool call. The harness runs the tool and the conversation records the call and its result the same way it would if the model had asked for it. | **Direction chosen, probe half done.** The [docs check](research/harness_tool_call_probe/docs_probe.md) found the "breaks with thinking on" claim only partly right: current Claude models with adaptive thinking accept it; older Claude with manual-budget thinking, Gemini 3, DeepSeek and Kimi reject it unless a placeholder is added, and Gemini 3 through OpenRouter has no documented fix. The live check is still running. |
| 5 | A declarative rule table (task plus a table mapping its answers to actions) | **Rejected.** It is a DSL Kiln would extend and maintain forever, and a weaker version of code. Code can do anything and agents already know how to write it. Logic lives in code. | **Decided** (2026-11-10). |

## Directions still to settle

Asked one or two at a time, in this order, because each depends on the ones before it.

1. **Is middleware the right abstraction?** Under discussion. The alternatives are code as the agent's front door (a code task that calls the real agent), and fixed built-in features.
2. **Where the code runs.** The existing sandbox is desktop only. Whether agents with middleware must also run in the library or on a server decides whether sandboxed project code can be the form.
3. **What the code can call, and what comes back.** Inline model calls, saved tasks, tools, and continuing the turn. Includes getting probabilities and cost back to the code.
4. **Harness-initiated tool calls.** Close decision 4 using the probe results.
5. **What is recorded.** How middleware decisions appear in the trace and in saved runs, and how they become data for evals.
6. **Failure and latency rules.** Timeouts, what happens when a decider fails, streaming.
7. **Scope of this project.** What ships first, including how much UI.

## Deferred to architecture

- Interface style and signatures (decision 1).
- Hook points (decision 2).
- Ordering and merge rules for a stack of middleware.
