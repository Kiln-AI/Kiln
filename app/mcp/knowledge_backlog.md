# Knowledge backlog

This file lists the known gaps and the pending ideas of the knowledge of the
Kiln skill: what the knowledge does not teach yet, what Kiln itself cannot do
yet, and the technique, playbook, smell, lever, guide or code change that is
not written yet. It is the one place to debate the next change with the
highest leverage. It is outside the `kiln_mcp_server` package, so no agent on
the Kiln MCP reads it. To add an entry, add it at the end of `Unranked`, in
the format below, and do not rank it: the owners rank, and to move an entry
into `Ranked` is their decision. The order under `Ranked` is the rank. Each
entry has a unique title (`###`), the four fields in this order, and one to
three lines of text, each at most 100 characters. `Kind` is one of gap,
technique, playbook, smell, lever, code or guide (a hand-written file of
`references/knowledge/`). `Where` is one or more of knowledge or kiln, joined
by `, `. `Depends on` is `None`, or the titles of other entries joined by
`; `. `Source` is a link, a short reference or `None`.
`app/mcp/kiln_mcp_server/skill_checks/test_knowledge_backlog.py` checks the
format. The `knowledge-maintenance` skill
(`.agents/skills/knowledge-maintenance/SKILL.md`) says when to add an entry.

## Ranked

### Input transforms

- Kind: gap
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: Kiln gaps note, gap 1; overview 7.3

The lever, and its techniques: keep only the fields the task needs, cut long text, add computed
features, remove a field that misleads. The run config field exists, and nothing in the knowledge
teaches it.

### Sub-agents

- Kind: gap
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: Kiln gaps note, gap 2; overview 7.2

The lever, and its techniques: a stronger model for deep thinking; a specialist with its own tools;
a cheap reader for a large source. A fixed form for what comes back. Limits: one turn, and no fix
for a strong single agent. Tune a critical sub-agent on its own evals, then the main agent.

### Single-turn prompt caching in Kiln

- Kind: gap
- Where: kiln
- Depends on: None
- Source: Kiln Harness Tuner: Kiln gaps note, gap 3

The cost that Kiln measures can be wrong when a single-turn task gets no caching. It also decides
if `skill-into-the-prompt` can save money.

### RAG

- Kind: gap
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: Kiln gaps note, gap 5; overview 7.1

The lever. RAG or skill, and when each wins. Documents and extraction first; extract once and do
not tune it. Test that RAG helps before the chunker and the search type. Reranking. Size in tokens,
not in documents.

### OpenEnv worlds

- Kind: lever
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: Kiln gaps note, gap 9; overview 7.7; owner

A world is hard to change, so you do not change it: you wrap it in Kiln code tools. Teach what a
world is, which worlds and fixtures a project has, and how to read them. The Kiln API reference
has no `/worlds` routes.

## Unranked

### All tools in one general API tool, with a skill

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: knowledge design notes

Replace many narrow tools with one general API tool, and add the skill that describes the API.

### Tool-result clearing

- Kind: technique
- Where: knowledge, kiln
- Depends on: Compaction and tool-result clearing in Kiln
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Clear old tool results from the context. It is separate from compaction.

### A stronger model as an adviser to a cheap one

- Kind: technique
- Where: knowledge
- Depends on: Sub-agents
- Source: Kiln Harness Tuner: Kiln gaps note, gap 14

A cheap model calls a stronger model as a tool when it needs advice.

### A cheap model first, then a stronger one when it is not sure

- Kind: technique
- Where: knowledge
- Depends on: Sub-agents
- Source: Kiln Harness Tuner: V1 coverage note, section 7

A cascade: the cheap model answers, and a stronger model takes the cases where it is not sure.

### Examples chosen for each input

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Few-shot examples selected for the input at hand, not one fixed set.

### Examples from the agent's own successes

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Few-shot examples taken from train items that the agent got right.

### A check of each example against its input

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Check that each example agrees with its input before it is added to the prompt.

### A short index of the reference material, always in context

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

A compact index of the reference material in the prompt, so that the agent knows what exists.

### One prompt for each type of input

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Send each type of input to its own prompt.

### One call for each field

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Fill each field of a structured output with its own call.

### A step outside the model that replaces a model step

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

A calculator, a date anchor or a rule table, in place of a step that the model does badly.

### A helper tool for what the agent works out again and again

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

A tool that returns what the traces show the agent computing on each run.

### A check step with one retry

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

The agent checks its answer once, and tries again once if the check fails.

### Rules for the agent's loop

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Stop when the goal is met. Do not repeat a call that returned nothing.

### A request sent to its own instruction set by its type

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Route each type of request to its own instruction set, with a review of the tool calls.

### A thinking level set by the type of input

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

More thinking for the hard types of input, less for the easy ones.

### A short hand-written version of a promoted change

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Rewrite a promoted change in fewer words, and measure that it keeps its effect.

### A rule written as a trigger and an action

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Write each rule as "when X, do Y", in the narrowest place that can hold it.

### A verbosity option on a tool

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

The agent asks for a short or a full result.

### Examples for complex tool parameters

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

An example call in the description of a tool with a complex parameter.

### Readable names in place of opaque ids

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

A tool result gives names that the agent can read, not only ids.

### Namespaced tool names

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Tool names with a common prefix for each service or group.

### A quick check for room to improve

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Before an experiment on the wording, check whether the failing items can pass at all.
Example: the Kiln Harness Tuner planner may run a quick check for room before a wording change.

### Fine-tuning as a late step

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: project overview 7.6

For cost and latency, after the harness is stable. Knowledge does not go in the weights.
Kiln Harness Tuner does not start a fine-tune: an existing one is a model candidate.

### On-device models

- Kind: playbook
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: knowledge design notes; owner, 2026-11-13

How to tune an agent whose model must run on end-user devices (laptops, phones): the small models
that fit, the limits of memory and speed, and the harness changes that help a small model most.

### On-prem open-weight models

- Kind: playbook
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: knowledge design notes; owner, 2026-11-13

How to tune an agent whose model must run on the user's own servers: open-weight models only, often
with a limit on model size, and the harness changes that help when the best hosted models are out.

### The conventions that a model was trained on

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Tool names, formats and the vendor's own prompt guide for the model.

### Prompt lines left from an older model

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Remove the workarounds that an older model needed and the current one does not.

### A small knowledge source in the prompt

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Put a small knowledge source in the prompt, and remove the search tool.

### Playbook: after a change of model

- Kind: playbook
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Order: the same prompt, a new baseline, fix only what got worse, then remove old workarounds.

### Playbook: a first pass on a new agent

- Kind: playbook
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Order: stable failures, items that flip, stable passes, and the spread of cost and latency.

### Playbook: the order of work for a support agent

- Kind: playbook
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Order: the plan of the work for an agent that answers customers.

### Playbook: the order of work for an analyst over data

- Kind: playbook
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Order: the plan of the work for an agent that queries data and reports on it.

### Playbook: a rule ignored in place, followed from a tool result

- Kind: playbook
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Failure: the agent ignores a rule where it is, and follows it when it comes back in a tool result.

### Playbook: a classifier whose answers collapse to one class

- Kind: playbook
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Failure: a classifier gives one class to most inputs.

### Playbook: a change that fixes its target and breaks passing items

- Kind: playbook
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Failure: the change fixes the items it was built for, and items that passed now fail.

### Playbook: a defect outside the harness

- Kind: playbook
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Failure: a broken tool, stale data or a quota. No harness change fixes it.

### Playbook: an eval too small to show the effect

- Kind: playbook
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Eval: the eval has too few items to show a difference of the expected size.

### Playbook: a few items carry all the signal

- Kind: playbook
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Eval: every difference between candidates comes from the same few items.

### Playbook: eval feedback with a score and no reason

- Kind: playbook
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Eval: the judge gives a score and does not say why.

### Playbook: a structural change against plain retries

- Kind: playbook
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Eval: measure a structural change against plain retries with the same number of calls.

### Playbook: outputs that break while the score rises

- Kind: playbook
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

Eval: the score goes up, and the outputs get worse in a way that the eval does not see.

### Smell: very many skills

- Kind: smell
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: project overview 9

The agent has so many skills that their descriptions crowd its context.

### Smell: a long list of "must" and "never" lines

- Kind: smell
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

A prompt that is mostly absolute rules, with no reasons and no conditions.

### Smell: one loop for requests of different kinds

- Kind: smell
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

One prompt and one tool set for requests that need different handling.

### Smell: a low cache hit rate

- Kind: smell
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: V1 coverage note, section 7

The traces show that little of the prompt is read from the cache. Important for a long prompt or a
multi-turn agent, where the cache saves the most; less critical for a single turn with a short
prompt. The diagnosis is the technique `Prompt cache usage`.

### Smell: evals that do not cover the product

- Kind: smell
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: knowledge design notes

The evals test less than the agent does in production.

### Compaction and tool-result clearing in Kiln

- Kind: gap
- Where: kiln
- Depends on: None
- Source: Kiln Harness Tuner: Kiln gaps note, gap 8; overview 7.9

Not in Kiln. Compaction is planned. Tool-result clearing is not planned yet.

### A switch of model or thinking level in mid-conversation

- Kind: gap
- Where: kiln
- Depends on: None
- Source: Kiln Harness Tuner: Kiln gaps note, gap 14; overview 7.9

Not in Kiln. A sub-agent can approximate the advisor pattern today.

### Inline guardrails

- Kind: gap
- Where: kiln
- Depends on: None
- Source: Kiln Harness Tuner: project overview 7.9

Not in Kiln.

### Run config fields

- Kind: gap
- Where: kiln
- Depends on: None
- Source: Kiln Harness Tuner: Kiln gaps note, gap 15

No `max_tokens`, seed, `tool_choice`, `top_k` or penalties. Low value: settings are a late lever.

### OpenRouter routing controls

- Kind: gap
- Where: kiln
- Depends on: None
- Source: Kiln Harness Tuner: Kiln gaps note, gap 13

Kiln sets a fixed provider order and never sends `zdr` or `sort`. So a zero-data-retention
restriction cannot be enforced through OpenRouter. To confirm.

### The `llm` tool inside code tools

- Kind: gap
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: Kiln gaps note, gap 11

A code tool can probably call the built-in `llm` tool: a cheap reader inside a wrapper. Confirm,
then teach.

### Prompt generators and few-shot

- Kind: gap
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: Kiln gaps note, gap 12

Reachable and not taught. A few-shot generator can copy split items into the prompt. Confirm the
leak risk before anything teaches it.

### Code files in skills

- Kind: gap
- Where: kiln
- Depends on: None
- Source: Kiln Harness Tuner: Kiln gaps note, gap 17

Kiln skills read text only and cannot run code. Code goes in code tools. The knowledge states it.

### Other decision-model providers

- Kind: gap
- Where: kiln
- Depends on: None
- Source: Kiln Harness Tuner: Kiln gaps note, gap 16

Only one decision-model provider exists. This matters when a restriction excludes it.

### Decision models for uses other than a classifier

- Kind: gap
- Where: kiln
- Depends on: None
- Source: Kiln Harness Tuner: project overview 7.4; Kiln gaps note, gap 7

Kiln supports decision models for tasks with a classifier shape only.

### Conflicting requirements

- Kind: smell
- Where: knowledge
- Depends on: None
- Source: owner, 2026-11-13

Two texts that the agent reads ask for things that cannot both hold: the prompt, a tool description,
a skill, a tool's response. The agent then follows one at random. The remedy can need the user.

### A repeat measurement on request

- Kind: code
- Where: knowledge
- Depends on: None
- Source: Kiln Harness Tuner: repeat-measurement project

A way to ask for an existing run config to run and be judged again on train items. In Kiln
Harness Tuner today only `--noise-check` repeats a measurement, one time, before wave 1.
Example: the Kiln Harness Tuner planner may request a repeat measurement to analyze noise.

### Feature engineering on the data that reaches the model

- Kind: technique
- Where: knowledge
- Depends on: Input transforms
- Source: owner, 2026-11-18; Kiln Harness Tuner: feature-engineering project

Fix the data before the model reads it: via the input transform, or a code wrapper on a tool result.
Drop and dedupe fields, compute `is_open`, cut long text, wrap user text in tags, rename a wrong
field. The owner's notes, moves, risks and research to do are in Kiln Harness Tuner.

### Prompt cache usage

- Kind: technique
- Where: knowledge
- Depends on: None
- Source: owner, 2026-11-19; see also `Smell: a low cache hit rate`

On a long multi-turn trace that can use it, check that the prompt cache is used. If not, find why:
caching is off; the account or provider does not have it; the agent edits its own history. That
edit saves a few tokens, but it breaks the cache and can cost 10x more.

### Mike's review of `references/knowledge/train_val_test.md`

- Kind: guide
- Where: knowledge
- Depends on: None
- Source: kiln_mcp_server backlog B8; API enforcement of the rule is tracked as the scopes item (P2) in `specs/projects/kiln_mcp_server/project_overview.md`

Mike signs it off or improves it. Open: val is summary numbers only, yet "whether it is significant"
is one; that needs per-item val scores, and the spec planned the paired statistics call on val.
Absent: Kiln Harness Tuner's zero-number val→train signals (rejection reason, regressed-issue flag).

### A manual review of four files against the port rules

- Kind: guide
- Where: knowledge
- Depends on: None
- Source: kiln_mcp_server backlog B31; `specs/projects/kiln_mcp_server/phase_plans/phase_13.md`, section 3

Review `SKILL.md`, `train_val_test.md` and `diagnose_an_agent.md` (knowledge/), and
`running_an_experiment_from_chat.md` (client_guidance/chat/), against the port rules: Kiln Harness
Tuner's method unchanged (vocabulary only); one owner per question; nothing selects on test.

### Shared knowledge files that lean on the chat modes by name

- Kind: guide
- Where: knowledge
- Depends on: None
- Source: Phase 21 code review

`project_status.md` (17, 28, 34), `model_work.md:155` and `provider_setup.md:32` name a mode's step
("the mode's bootstrap", "Task Context Discovery"): a non-interactive reader meets `agent_overview`
with no source. Name the step in the file itself, or label it "in a chat with a user".

### using_harness_tuner

- Kind: guide
- Where: knowledge
- Depends on: None
- Source: owner

A knowledge file, `references/knowledge/using_harness_tuner.md`: how the user's own agent,
connected to Kiln with the skill, runs the Kiln Harness Tuner CLI in place of running the
experiments itself.
