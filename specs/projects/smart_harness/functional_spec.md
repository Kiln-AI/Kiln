---
status: draft
---

# Functional Spec: Kiln Smart Harness

> **First full draft, for review.** Three kinds of statement appear below:
> - Plain statements restate a decision already made. Each cites its number in the [decision log](#decision-log).
> - Statements that start with **Proposed:** are the author's suggestion and have not been agreed.
> - Two parts are deliberately not designed here: [the interface](#6-the-interface-designed-at-architecture) and [the trace](#8-what-is-recorded).

Inputs: [project overview](project_overview.md), [research on routing and decision layers](research/routing_and_decision_layers/summary.md), [how the harness works today](research/current_harness/summary.md), [probe of harness-initiated tool calls](research/harness_tool_call_probe/summary.md), [middleware-style code in the code sandbox](research/code_sandbox_middleware/summary.md).

## 1. Summary

Today a Kiln agent sends every turn to its main model, which decides everything: whether to answer, which tools to call, and how hard to think. Some of those decisions are known in advance or can be made far more cheaply. Examples from the overview:

- Always fetch the user's details on the first turn. No model needs to decide that.
- "What are your opening hours?" has one correct reply. A decision model such as Jev can recognize the question and the agent can reply without the main model.
- Easy questions can go to a cheap model and hard ones to a strong model with more thinking.

This project adds **middleware** to the Kiln harness: Python code, saved in the project, that runs inside the harness around a turn. A middleware can answer without the model, have the harness run a tool, change the turn's settings, or let the turn through unchanged. A run config carries an ordered stack of them.

## 2. Goals

**Proposed.** These were suggested by the author and have not been confirmed, except the last, which is decision 10.

1. A Kiln agent spends less time and money per turn by handling known situations without the main model, or with a cheaper setting, and quality as measured by the agent's evals does not drop.
2. A middleware stack is part of the run config. It can be compared by evals against the same run config without it.
3. Every decision a middleware makes is recorded on the run, so a person can see what happened and why.
4. A middleware is judged by whether the agent with it still meets the agent's goal, measured by running the whole agent with the agent's evals. The goal of a middleware is the agent's goal (decision 10).

Not goals: a general workflow engine, a replacement for the agent loop, or a configuration language for routing rules (decision 5).

## 3. Terms

- **Turn.** One user message and everything the agent does to answer it. In Kiln that is one `invoke` call and one saved run. A run of a single-turn task is one turn. **Proposed:** when a turn pauses for a tool the client app runs and then resumes, it is still the same turn.
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
- **Elegant.** One concept and few rules. A simple case is a few lines.
- **Code, not configuration.** An agent can write a middleware, and so can a person.
- **Testable.** **Proposed:** a middleware can be unit-tested with the existing pytest fixture that fakes `kiln.tools`, with no sandbox and no model.

### 6.2 Cases the design is judged against

Cases marked *(added)* were added by the author after the project owner approved the first twelve and asked for more. They are open to cutting.

**Must work in the first version**

1. On turn 1, run `get_user_info` with no model call.
2. A rule with no model call, such as a regex check that sends messages containing code straight to the stronger model. *(added)*
3. Ask a decision model, then run the turn on the model and thinking level it picked.
4. Ask a decision model, then answer with a canned reply or let the model answer.
5. A tree of decision-model calls that picks among many canned replies.
6. Several questions in one decision-model request, or several independent calls in parallel. *(added)*
7. Search, then verify: search an FAQ with a search tool, have a decision model confirm the top hit answers the question, then reply with it. *(added)*
8. All of the above in one piece of code, with thresholds on probabilities.
9. Cases 1, 4 and 3 as three independent entries in a stack, in that order.
10. A guard ahead of them in the stack that refuses a message with a fixed reply before anything else runs. *(added)*
11. Code calling other code for complex logic, including a decision tree kept as shared code and used by several agents.
12. The same middleware attached to several run configs. *(added)*
13. An LLM as the router. This should be rare.
14. A call the code made fails, and the code catches the error and lets the turn through. *(added)*
15. The tool in case 1 is one the client app runs, so the turn pauses and resumes. *(added)*
16. Do nothing.

**The design must show where these fit. Whether they are built first is settled at architecture.**

17. Change a tool's result, such as turning a 300k-token result into an error.
18. Check a tool call before it runs, and block it. *(added)*
19. Check or change the model's response, such as a check that it contains no secrets.
20. Run the model, then decide: cheap model first, then a stronger one if a check says the answer is weak. *(added)*
21. If the model call fails, run the turn on another model. *(added)*
22. Observe only: time the turn or note something about it without changing it. *(added)*
23. Remember across turns: once a conversation has been sent to the stronger model, keep it there. *(added)*

**Later. The design leaves room.**

24. Hand the turn to a subagent (P2 in the overview).
25. Change what the model sees this turn, such as trimming old tool results. *(added)*
26. Switch model part-way through a turn, after repeated tool failures. *(added)* This conflicts with decision 3 as it stands.

Case 8 needs probabilities from decision models. See [7.8](#78-probabilities-from-decision-models).

## 7. Behavior

These rules hold whatever shape the interface takes.

### 7.1 When middleware runs

- **Proposed:** a run config's stack runs on every turn of every run that uses that run config: the app's run screen, evals, the API, the library, and when the agent is called as a subagent by another agent.
- **Proposed:** it behaves the same in the streaming and non-streaming paths.
- **Proposed:** middleware can be attached only to agent run configs (the `kiln_agent` type), not to MCP run configs.

### 7.2 What the code is given

The interface is not designed yet, but the cases above need at least this:

- the conversation so far, including the new user message;
- the turn number;
- the settings the turn would use: model, provider, thinking level, temperature, top_p;
- the names of the tools on the agent's tool list.

### 7.3 Answering without the model

- The turn ends with the middleware's reply as the agent's answer.
- **Proposed:** for a task with a structured output schema, the reply must be valid against that schema. If it is not, the turn fails under [7.6](#76-failure).
- **Proposed:** in the streaming path the reply arrives as ordinary text events.

### 7.4 Having the harness run a tool

- The tool must be on the agent's own tool list (decision 11). Naming any other tool is a failure under [7.6](#76-failure).
- **Proposed:** the arguments are checked against the tool's schema, as they are for a model-requested call.
- **Proposed:** the harness runs the call exactly as it runs a model-requested one. That includes a tool the client app runs: the turn pauses and the client resumes it with the result.
- After the result is recorded, the turn continues and the model sees the call and its result in its history. Whether later stack entries still run in that turn is an ordering question for architecture.
- The [probe](research/harness_tool_call_probe/summary.md) found this accepted by 52 models through OpenRouter. Providers' own APIs are not yet checked ([open items](#12-open-items)).

### 7.5 Changing the turn's settings

- The overridable settings and their scope are fixed by decision 3 (see [5.1](#51-effects-on-the-turn)).
- **Proposed:** an override lasts for that turn only. The next turn starts from the run config's own settings.
- **Proposed:** naming a model, provider or thinking level that Kiln cannot run is a failure under [7.6](#76-failure).

### 7.6 Failure

- If a middleware fails, the turn fails (decision 12). This covers the code raising an error, running past its time limit, returning something invalid, and the sandbox itself failing.
- There is no skip-and-continue setting. An author who wants the turn to continue when a call fails catches the error in the code.
- **Proposed:** a turn failed by middleware is reported the same way as a turn failed by a provider error, and names the middleware that failed.

### 7.7 Cost and latency

Cost and latency must be correct (requirement from the project owner).

- **Cost.** If middleware makes model calls, their cost counts toward the turn.
- **Latency.** The time middleware takes counts toward the turn, whether or not it calls a model.

Today neither holds. A run's cost covers only the main model's own calls, so a model call made inside a tool or a subagent is not included. A run's latency is the time spent waiting on the main model, so a turn answered without the model would show zero.

- **Proposed:** a turn's cost is the main model's calls plus every model call its middleware made, inline or through a saved task.
- **Proposed:** a turn reports the time spent in middleware next to the time spent waiting on the main model, and a total of the two.
- **Proposed:** the middleware share of cost and of time is also shown separately, so a reader can see what the stack added and what it saved.

### 7.8 Probabilities from decision models

Thresholds such as "use the canned reply only above 0.9" need the probabilities a decision model returns. Today they do not reach code: the inline model call and the sandbox both return the answer only.

Kiln needs a better general interface to decision models, of which there are now several besides Jev. That work is outside this project. Middleware code uses whatever that interface returns. Until it exists, a middleware can use a decision model's answer but not its probability.

### 7.9 Limits

- **Proposed:** each middleware has a time limit, as code tools do. Its default is set at architecture.
- The sandbox runs at most 16 top-level code runs at once across the process, shared with code tools and code judges. Evals that run many turns in parallel will meet this limit. How to handle it is an architecture question.
- Each sandbox run starts a new process. Measured cost on Linux: about 80 ms per run.

## 8. What is recorded

The project owner set three requirements for the trace:

1. The trace looks normal.
2. It works as the history for the next turn on any model.
3. It shows when there was a settings override, a code-based decision, and so on.

The design of the trace is a large part of this project and has not been started. It is not designed in this draft.

## 9. Storage and API

- **Proposed:** a middleware is saved in the project the way a code tool is, with its Python in a file beside it.
- **Proposed:** a middleware has a name, a description, its code, a time limit, and an allowlist of the tools its code may call privately.
- **Proposed:** the code cannot be changed after the middleware is created. A change is a new middleware. This is the rule code tools follow, and it means a run config always refers to the same code.
- A run config lists the middleware it uses, in order.
- **Proposed:** the desktop API offers the same operations for middleware that it offers for code tools: create, list, read, edit the name and description, and a test run. Saving and testing are behind the same project trust check as code tools.
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
- **Proposed:** a second way to run middleware in-process for library users, outside the sandbox.

## 12. Open items

- **The interface**, with hook points and ordering. Designed at architecture against [section 6](#6-the-interface-designed-at-architecture).
- **The trace.** Not started ([section 8](#8-what-is-recorded)).
- **Harness-run tool calls on providers' own APIs.** The probe ran through OpenRouter only. Docs say Google's own Gemini 3 API and older Claude models with a manual thinking budget reject a tool call the model did not write, and that LiteLLM patches the Gemini case. Checking needs direct Anthropic, Google and OpenAI keys. One model, `thinkingmachines/inkling-small`, stopped reasoning after a harness-written call.
- **Goals.** [Section 2](#2-goals) is not confirmed.
- **Every statement marked "Proposed"** in sections 3, 6, 7, 9 and 11.
- **Cases marked "added"** in [6.2](#62-cases-the-design-is-judged-against).

## Decision log

| # | Topic | Decision | Status |
|---|---|---|---|
| 1 | The middleware interface | Getting this interface right is a key design goal of the project and is not to be glossed over. The overview's sketch (answer, tool call, overrides, do nothing) is rough: the interface must cover those cases, but they are not the interface. The project owner values elegant design and named HTTP middleware's composability and power as the quality to aim for. Earlier lean on style: both decide-and-return and wrap with `next()`. | **Open until architecture**, when signatures are designed. |
| 2 | Hook points (turn start, turn end, each tool call, each LLM call in the tool loop) | None yet. | **Deferred to architecture.** A proposal is wanted there that balances function, complexity and design. Not to be picked in isolation. |
| 3 | Overrides | Overrides chosen at turn start apply to every LLM call in that turn. Overridable: model and provider, thinking level, temperature, top_p. Not overridable: prompt, tools. When the model changes, structured output mode resets to the new model's default. | **Decided** (2026-11-10). Revisit only if architecture adds a per-LLM-call hook. |
| 4 | Harness-initiated tool call (for example "on turn 1, call `get_user_info`") | It is a real tool call. The harness runs the tool and the conversation records the call and its result the same way it would if the model had asked for it. | **Decided** (2026-11-10), and the [probe](research/harness_tool_call_probe/summary.md) supports it: through OpenRouter, 124 of 129 calls with a harness-written call succeeded across 52 models, and none of the 5 failures was caused by the call. Not yet checked: each provider's own API. |
| 5 | A declarative rule table (task plus a table mapping its answers to actions) | **Rejected.** It is a DSL Kiln would extend and maintain forever, and a weaker version of code. Code can do anything and agents already know how to write it. Logic lives in code. | **Decided** (2026-11-10). |
| 6 | What the stack is | An ordered list of independent entries, as the overview describes: first turn → tool call; canned answer works → return it; needs more thinking → override; otherwise run normally. Routing logic is never split across entries. Logic more complex than one check is one entry whose code calls other code. | **Decided** (2026-11-10). It restates the overview. |
| 7 | Where middleware code runs | The existing code sandbox. It runs wherever the Kiln library runs: the desktop app, or a script or server that imports the library. It does not run on Kiln's own hosted servers. | **Fact, checked** (2026-11-10). An earlier note in this project wrongly said the sandbox was limited to the desktop app. |
| 8 | Middleware as the abstraction | Code that runs inside the harness around a turn. | **Decided** (2026-11-10). |
| 9 | Middleware as a task, or as code | **Code.** A middleware is stored Python, a sibling of code tools and code judges. Tasks and inline model calls are things the code calls. Accepted costs: no dataset per middleware; an LLM cannot be a middleware without a few lines of code; no general code-task feature. | **Decided** (2026-11-10). |
| 10 | How a middleware is judged | By whether the agent with it still meets the agent's goal, measured by running the whole agent with the agent's evals. The goal of a middleware is the agent's goal. No dataset or eval per middleware is wanted. | **Decided** (2026-11-10). |
| 11 | Which tools a middleware can have the harness run | Only tools from the agent's own tool list. The call and its result go into the model's history, so the model has that tool's definition. | **Decided** (2026-11-10). |
| 12 | When a middleware fails | The turn fails. This covers the code raising an error, running past its time limit, returning something invalid, and the sandbox itself failing. There is no skip-and-continue setting: an author who wants to continue catches the error in the code. | **Decided** (2026-11-10). |
| 13 | Calls the code makes to decide | They are private. An inline model call, a saved task, or a tool on the middleware's own allowlist is never shown to the main model and is not a message in the conversation. These calls count toward cost and latency and are recorded. | **Stated, no objection** (2026-11-10). |
| 14 | What ships in this project | The library, the API, and a read-only view in the app: a run config shows which middleware it uses, and a run shows what each middleware did on each turn. Authoring in the app is a follow-up project. | **Decided** (2026-11-10). |
| 15 | Cases the interface is judged against | The first twelve cases were approved, and the project owner asked for more to be added. The added cases are marked in section 6.2 and are open to cutting. | **Approved, additions pending review** (2026-11-10). |
