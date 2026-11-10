---
status: complete
---

# Functional Spec: Kiln Smart Harness

> Decisions are made in chat and recorded here with their number in the [decision log](#decision-log). Nothing in this file is a proposal. Two parts are designed at architecture, not in this file: [the interface](#6-the-interface-designed-at-architecture) and [the trace](#8-what-is-recorded). Items that carry over to architecture are listed under [open items](#12-open-items).

Inputs: [project overview](project_overview.md), [research on routing and decision layers](research/routing_and_decision_layers/summary.md), [how the harness works today](research/current_harness/summary.md), [probe of harness-initiated tool calls](research/harness_tool_call_probe/summary.md), [middleware-style code in the code sandbox](research/code_sandbox_middleware/summary.md).

## 1. Summary

Today a Kiln agent sends every turn to its main model, which decides everything: whether to answer, which tools to call, and how hard to think. Some of those decisions are known in advance or can be made far more cheaply. Examples from the overview:

- Always fetch the user's details on the first turn. No model needs to decide that.
- "What are your opening hours?" has one correct reply. A decision model such as Jev can recognize the question and the agent can reply without the main model.
- Easy questions can go to a cheap model and hard ones to a strong model with more thinking.

This project adds **middleware** to the Kiln harness: Python code, saved in the project, that runs inside the harness around a turn. A middleware can answer without the model, have the harness run a tool, change the turn's settings, or let the turn through unchanged. A run config carries an ordered stack of them.

## 2. Goals

1. A Kiln agent spends less time and money per turn by handling known situations without the main model, or with a cheaper setting, and quality as measured by the agent's evals does not drop.
2. A middleware stack is part of the run config. It can be compared by evals against the same run config without it.
3. Every decision a middleware makes is recorded on the run, so a person can see what happened and why.
4. A middleware is judged by whether the agent with it still meets the agent's goal, measured by running the whole agent with the agent's evals. The goal of a middleware is the agent's goal (decision 10).

Not goals: a general workflow engine, a replacement for the agent loop, or a configuration language for routing rules (decision 5).

## 3. Terms

- **Turn.** One user message and everything the agent does to answer it. In Kiln that is one `invoke` call and one saved run. A run of a single-turn task is one turn. When a turn pauses for a tool the client app runs and then resumes, it is still the same turn.
- **Turn number.** Turn 1 is the first user message of a conversation. The harness has no turn counter today and must provide one.
- **Middleware.** Python code saved in the project that runs inside the harness around a turn (decisions 8 and 9).
- **Stack.** The ordered list of middleware on a run config (decision 6).
- **Private call.** A call the middleware's code makes in order to decide what to do (decision 13).

## 4. What a middleware is

- **Stored Python.** A middleware is a sibling of code tools and code judges: Python saved in the project and run in the same code sandbox (decision 9).
- **Where it runs.** Wherever the Kiln library runs: the desktop app, or a script or server that imports the library. Not on Kiln's own hosted servers (decision 7).
- **Not a task.** Tasks and inline model calls are things the code calls. There is no dataset per middleware and no general "code task" feature (decision 9).
- **No rule table.** Logic is written in code, not in a configuration format (decision 5).
- **Attached to a run config.** A run config holds an ordered stack of middleware. An empty stack behaves exactly as Kiln does today.

## 5. What a middleware must be able to do

The overview sketched four effects a middleware can have on a turn. That sketch is rough: these are the minimum the interface must cover, not the interface itself (decision 1).

### 5.1 Effects on the turn

- **Answer without the model.** The middleware supplies the reply and the main model is not called.
- **Have the harness run a tool.** The middleware names a tool and its arguments. The harness runs it, and the conversation records the call and its result the same way it would if the model had asked for it (decision 4). The tool must be on the agent's own tool list (decision 11).
- **Change the turn's settings.** Model and provider, thinking level, temperature and top_p. Not the prompt and not the tool list. The change applies to every model call in that turn. When the model changes, structured output mode resets to the new model's default (decision 3).
- **Do nothing.** The turn runs as if the middleware were not there.

### 5.2 Private calls

To decide, the code can call:

- a model inline, with the prompt and any output schema written in the code and no saved task;
- a saved Kiln task with one of its run configs;
- a tool on the middleware's own allowlist, including search tools and other code.

These calls are private. The main model never sees them and they are not messages in the conversation. They count toward the turn's cost and latency, and they are recorded (decision 13).

All three kinds of call run in the code sandbox today. See the [sandbox research](research/code_sandbox_middleware/summary.md) for what was run and what is missing.

### 5.3 The stack

The stack is an ordered list of independent entries, as the overview describes: first turn → tool call; a canned answer works → return it; needs more thinking → override; otherwise run normally. Routing logic is never split across entries. Logic more complex than one check is one entry whose code calls other code (decision 6).

## 6. The interface (designed at architecture)

Getting the middleware interface right is a key design goal of this project. It is designed at the architecture step, where signatures, hook points and ordering are worked out together (decisions 1 and 2). This section sets what that design is held to.

### 6.1 Design values

- **Composable and powerful, like HTTP middleware.** Small independent pieces that stack. The project owner named HTTP middleware's composability and power as the quality to aim for.
- **Elegant.** One concept and few rules. A simple case is a few lines. The design should be great even for features that do not ship in the first version (decision 20).
- **Code, not configuration.** An agent can write a middleware, and so can a person.
- **Testable.** A middleware can be unit-tested with the existing pytest fixture that fakes `kiln.tools`, with no sandbox and no model.

### 6.2 Cases the design is judged against

**Must work in the first version**

1. On turn 1, run `get_user_info` with no model call.
2. A rule with no model call, such as a regex check that sends messages containing code straight to the stronger model.
3. Ask a decision model, then run the turn on the model and thinking level it picked.
4. Ask a decision model, then answer with a canned reply or let the model answer.
5. A tree of decision-model calls that picks among many canned replies.
6. Several questions in one decision-model request, or several independent calls in parallel.
7. Search, then verify: search an FAQ with a search tool, have a decision model confirm the top hit answers the question, then reply with it.
8. All of the above in one piece of code, with thresholds on probabilities.
9. Cases 1, 4 and 3 as three independent entries in a stack, in that order.
10. A guard ahead of them in the stack that refuses a message with a fixed reply before anything else runs.
11. Code calling other code for complex logic, including a decision tree kept as shared code and used by several agents.
12. The same middleware attached to several run configs.
13. An LLM as the router. This should be rare.
14. A call the code made fails, and the code catches the error and lets the turn through.
15. The tool in case 1 is one the client app runs, so the turn pauses and resumes.
16. Do nothing.

**Checked in design**

The interface design is checked against every case below, whether or not the case ships in the first version. If the design is better for covering one, good. If covering one costs something, the tradeoff is discussed in chat before it is decided (decision 20).

17. Change a tool's result, such as turning a 300k-token result into an error.
18. Check a tool call before it runs, and block it.
19. Check or change the model's response, such as a check that it contains no secrets.
20. Run the model, then decide: cheap model first, then a stronger one if a check says the answer is weak.
21. If the model call fails, run the turn on another model.
22. Observe only: time the turn or note something about it without changing it.
23. An override that holds from here on: once a conversation has been sent to the stronger model, it stays there. Check an option for a middleware to return an override for the rest of the conversation, not just one turn.
24. How often a middleware runs: once per turn, or before every model call in the turn, including after tool results. Check whether a flag on a middleware can make it run more often.
25. Change what the model sees this turn, such as trimming old tool results.
26. Switch model part-way through a turn, after repeated tool failures. This conflicts with decision 3 as it stands.
27. Hand the turn to a subagent. Building it is P2 in the overview.

Case 8 needs probabilities from decision models. See [7.8](#78-probabilities-from-decision-models).

## 7. Behavior

These rules hold whatever shape the interface takes.

### 7.1 When middleware runs

- A run config's stack runs on every turn of every run that uses that run config: the app's run screen, evals, the API, the library, and when the agent is called as a subagent by another agent.
- It behaves the same in the streaming and non-streaming paths.
- Middleware can be attached only to agent run configs (the `kiln_agent` type), not to MCP run configs.

### 7.2 What the code is given

The interface is not designed yet, but the cases above need at least this:

- the conversation so far, including the new user message;
- the turn number;
- the settings the turn would use: model, provider, thinking level, temperature, top_p;
- the names of the tools on the agent's tool list.

### 7.3 Answering without the model

- The turn ends with the middleware's reply as the agent's answer.
- For a task with a structured output schema, the reply must be valid against that schema. If it is not, the turn fails under [7.6](#76-failure).
- In the streaming path the reply arrives as ordinary text events.

### 7.4 Having the harness run a tool

- The tool must be on the agent's own tool list (decision 11). Naming any other tool is a failure under [7.6](#76-failure).
- The arguments are checked against the tool's schema, as they are for a model-requested call.
- The harness runs the call exactly as it runs a model-requested one. That includes a tool the client app runs: the turn pauses and the client resumes it with the result.
- After the result is recorded, the turn continues and the model sees the call and its result in its history. Whether later stack entries still run in that turn is an ordering question for architecture.
- The [probe](research/harness_tool_call_probe/summary.md) found this accepted by 52 models through OpenRouter. Providers' own APIs are not yet checked ([open items](#12-open-items)).

### 7.5 Changing the turn's settings

- The overridable settings and their scope are fixed by decision 3 (see [5.1](#51-effects-on-the-turn)).
- An override lasts for that turn only. The next turn starts from the run config's own settings. The design checks an option for a middleware to return an override that holds from here on (case 23).
- Naming a model, provider or thinking level that Kiln cannot run is a failure under [7.6](#76-failure).

### 7.6 Failure

- If a middleware fails, the turn fails (decision 12). This covers the code raising an error, running past its time limit, returning something invalid, and the sandbox itself failing.
- There is no skip-and-continue setting. An author who wants the turn to continue when a call fails catches the error in the code.
- A turn failed by middleware is reported the same way as a turn failed by a provider error, and names the middleware that failed.

### 7.7 Cost and latency

Cost and latency must be correct (decisions 18 and 21).

Today neither is. A run's cost covers only the main model's own calls, so a model call made by a code tool or by a subagent is not included. A run's latency is the time spent waiting on the main model, so a turn answered without the model would show zero.

- **Cost is reported as line items.** The cost Kiln reports today keeps its meaning: the main model's own calls. Beside it, a turn reports three more: the model calls its middleware made, the model calls its code tools made, and the cost of the subagents it called. Old runs keep their numbers and their meaning.
- **A total.** A turn also reports the sum of the line items. Comparisons between run configs use the total, so a stack that answers with a cheap model call is not shown as free.
- **Precedent.** Kiln already records one cost beside the main one: the synthetic user's spend, kept separate so the main number stays assistant-only.
- **Latency.** The time middleware takes counts toward the turn, whether or not it calls a model. A turn reports the time spent in middleware next to the time spent waiting on the main model, and a total of the two.

### 7.8 Probabilities from decision models

Thresholds such as "use the canned reply only above 0.9" need the probabilities a decision model returns. Today they do not reach code: the inline model call and the sandbox both return the answer only.

Kiln needs a better general interface to decision models, of which there are now several besides Jev. That work is outside this project. Middleware code uses whatever that interface returns. Until it exists, a middleware can use a decision model's answer but not its probability.

### 7.9 Limits

- Each middleware has a time limit, as code tools do. Its default is set at architecture.
- The sandbox runs at most 16 top-level code runs at once across the process, shared with code tools and code judges. Evals that run many turns in parallel will meet this limit. How to handle it is an architecture question.
- Each sandbox run starts a new process. Measured cost on Linux: about 80 ms per run.

## 8. What is recorded

The project owner set three requirements for the trace:

1. The trace looks normal.
2. It works as the history for the next turn on any model.
3. It shows when there was a settings override, a code-based decision, and so on.

The design of the trace is a large part of this project. It is designed at architecture together with the interface, because what a middleware returns and what is recorded are two sides of one design (decision 22). The read-only view in the app depends on it, so the order is: interface and trace, then the UI design step, then the rest of architecture.

## 9. Storage and API

- A middleware is saved in the project the way a code tool is, with its Python in a file beside it.
- A middleware has a name, a description, its code, a time limit, and an allowlist of the tools its code may call privately.
- The code cannot be changed after the middleware is created. A change is a new middleware. This is the standard for Kiln: saved things that runs depend on are immutable, so history stays true and a run config always refers to the same code (decision 17).
- A run config lists the middleware it uses, in order.
- The desktop API offers the same operations for middleware that it offers for code tools: create, list, read, edit the name and description, and a test run. Saving and testing are behind the same project trust check as code tools.
- The same objects are available through the library's datamodel.

## 10. The app

The app gets a read-only view (decision 14). Screens are designed in the UI design step, after the trace is designed.

- A run config shows which middleware it uses, in order, and each one's code can be read.
- A run shows what each middleware did on each turn, with its cost and time.
- Not in this project: writing or editing middleware in the app, and attaching middleware when creating a run config. Middleware is written as files or through the API.

## 11. Out of scope

- Authoring middleware in the app (a follow-up project).
- The optimizer adding, removing or changing middleware.
- Tools for tuning thresholds.
- Routing that accounts for prompt caching.
- Handing the turn to a subagent (P2).
- The general decision-model interface (separate work; see [7.8](#78-probabilities-from-decision-models)).
- A rule table or other configuration language (decision 5).
- Datasets or evals per middleware (decision 10).
- Code tasks (decision 9).
- A setting to skip a failed middleware (decision 12).
- A second way to run middleware in-process for library users, outside the sandbox.

## 12. Open items

Nothing here blocks this spec. Each item carries over to architecture or to other work.

- **The interface**, with hook points and ordering. Designed at architecture against [section 6](#6-the-interface-designed-at-architecture).
- **The trace.** Designed at architecture with the interface ([section 8](#8-what-is-recorded)).
- **Harness-run tool calls on providers' own APIs.** The probe ran through OpenRouter only. Docs say Google's own Gemini 3 API and older Claude models with a manual thinking budget reject a tool call the model did not write, and that LiteLLM patches the Gemini case. Checking needs direct Anthropic, Google and OpenAI keys. One model, `thinkingmachines/inkling-small`, stopped reasoning after a harness-written call.
- **The decision-model interface.** Outside this project. Case 8 (thresholds on probabilities) waits on it.
- **The sandbox's limit of 16 runs at once.** An architecture question ([7.9](#79-limits)).

## Decision log

| # | Topic | Decision | Status |
|---|---|---|---|
| 1 | The middleware interface | Getting this interface right is a key design goal of the project and is not to be glossed over. The overview's sketch (answer, tool call, overrides, do nothing) is rough: the interface must cover those cases, but they are not the interface. The project owner values elegant design and named HTTP middleware's composability and power as the quality to aim for. Earlier lean on style: both decide-and-return and wrap with `next()`. | **Open until architecture**, when signatures are designed. |
| 2 | Hook points (turn start, turn end, each tool call, each LLM call in the tool loop) | None yet. | **Deferred to architecture.** A proposal is wanted there that balances function, complexity and design. Not to be picked in isolation. |
| 3 | Overrides | Overrides chosen at turn start apply to every LLM call in that turn. Overridable: model and provider, thinking level, temperature, top_p. Not overridable: prompt, tools. When the model changes, structured output mode resets to the new model's default. | **Decided** (2026-11-10). An override lasts one turn; the design checks an option for it to hold from here on (case 23). Revisit the per-turn rule only if architecture has middleware run before every model call (case 24). |
| 4 | Harness-initiated tool call (for example "on turn 1, call `get_user_info`") | It is a real tool call. The harness runs the tool and the conversation records the call and its result the same way it would if the model had asked for it. | **Decided** (2026-11-10), and the [probe](research/harness_tool_call_probe/summary.md) supports it: through OpenRouter, 124 of 129 calls with a harness-written call succeeded across 52 models, and none of the 5 failures was caused by the call. Not yet checked: each provider's own API. |
| 5 | A declarative rule table (task plus a table mapping its answers to actions) | **Rejected.** It is a DSL Kiln would extend and maintain forever, and a weaker version of code. Code can do anything and agents already know how to write it. Logic lives in code. | **Decided** (2026-11-10). |
| 6 | What the stack is | An ordered list of independent entries, as the overview describes: first turn → tool call; canned answer works → return it; needs more thinking → override; otherwise run normally. Routing logic is never split across entries. Logic more complex than one check is one entry whose code calls other code. | **Decided** (2026-11-10). It restates the overview. |
| 7 | Where middleware code runs | The existing code sandbox. It runs wherever the Kiln library runs: the desktop app, or a script or server that imports the library. It does not run on Kiln's own hosted servers. | **Fact, checked** (2026-11-10). An earlier note in this project wrongly said the sandbox was limited to the desktop app. |
| 8 | Middleware as the abstraction | Code that runs inside the harness around a turn. | **Decided** (2026-11-10). |
| 9 | Middleware as a task, or as code | **Code.** A middleware is stored Python, a sibling of code tools and code judges. Tasks and inline model calls are things the code calls. Accepted costs: no dataset per middleware; an LLM cannot be a middleware without a few lines of code; no general code-task feature. | **Decided** (2026-11-10). |
| 10 | How a middleware is judged | By whether the agent with it still meets the agent's goal, measured by running the whole agent with the agent's evals. The goal of a middleware is the agent's goal. No dataset or eval per middleware is wanted. | **Decided** (2026-11-10). |
| 11 | Which tools a middleware can have the harness run | Only tools from the agent's own tool list. The call and its result go into the model's history, so the model has that tool's definition. | **Decided** (2026-11-10). |
| 12 | When a middleware fails | The turn fails. This covers the code raising an error, running past its time limit, returning something invalid, and the sandbox itself failing. There is no skip-and-continue setting: an author who wants to continue catches the error in the code. | **Decided** (2026-11-10). |
| 13 | Calls the code makes to decide | They are private. An inline model call, a saved task, or a tool on the middleware's own allowlist is never shown to the main model and is not a message in the conversation. These calls count toward cost and latency and are recorded. | **Decided** (2026-11-10). |
| 14 | What ships in this project | The library, the API, and a read-only view in the app: a run config shows which middleware it uses, and a run shows what each middleware did on each turn. Authoring in the app is a follow-up project. | **Decided** (2026-11-10). |
| 15 | Cases the interface is judged against | The 27 cases in section 6.2. Sixteen must work in the first version. The rest are checked in design whether or not they ship first. | **Decided** (2026-11-10). |
| 16 | How the spec is settled | In chat. The spec file records decisions and carries nothing marked as proposed. | **Decided** (2026-11-10). |
| 17 | Changing a middleware's code | Not allowed after creation. A change is a new middleware. Standard for Kiln: immutable, for history. | **Decided** (2026-11-10). |
| 18 | Cost and latency | Both must be correct. A turn's cost includes every model call its middleware made, and the same applies to model calls made by code tools. A turn's latency includes the time middleware takes, whether or not it calls a model, reported next to main-model time with a total. The middleware share is also shown separately. | **Decided** (2026-11-10). How cost is reported is decision 21. |
| 19 | Remaining behavior in sections 2, 3, 6.1, 7, 9 and 11 | Accepted as written in the first draft: the goals; a paused and resumed turn is one turn; middleware runs on every run that uses the run config, in both streaming and non-streaming paths, on agent run configs only; a reply for a structured task must match its schema; harness-run tool calls are validated and run like model-requested ones, including client-run tools; an unrunnable override fails the turn; a failed turn names the middleware; each middleware has a time limit; storage and API follow code tools, behind the same trust check; a middleware can be unit-tested with the existing pytest fixture; no in-process variant. | **Decided** (2026-11-10). |
| 20 | Design quality | The design should be great, including for features that do not ship in the first version. The later cases are checked in design. If the design is better for covering them, good. If there is a tradeoff, it is discussed. | **Decided** (2026-11-10). |
| 21 | How cost is reported | As line items, so no existing number changes meaning. The cost Kiln reports today stays the main model's own calls. Beside it: middleware model calls, code tool model calls, and subagent cost. A total sums them, and comparisons between run configs use the total. | **Decided** (2026-11-10). |
| 22 | When the trace is designed | At architecture, together with the interface. Then the UI design step, then the rest of architecture. | **Decided** (2026-11-10). |
