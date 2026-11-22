# Improving agents

This is the index of the knowledge on how to improve an agent's harness: the
prompt, the skills, the tools, the model, its settings and its output mode.
It is general knowledge, from the field, from public sources and from other
projects. It holds nothing that was measured on the task that you tune.

## How to read these documents

**These are ideas to try.** The techniques, the playbooks and the smells are
ideas to try as part of experimentation. What actually works varies from
agent to agent. A document says what to try, in what order, and under which
conditions. You know more about this agent than the documents do. Read each
document for the spirit of its guidance. Fit its suggestions to the agent's
goal, its tools and its task, and change a suggestion where the agent needs
it. The hard limits are the exception: the safety and integrity rules in the
lever documents. For example: never attach a tool that can reach the Kiln
server; the allowlist and the shared-tool rules of a code tool; no value
from a train item in a change (the leak rules of
`references/knowledge/train_val_test.md`). No measurement overrides a hard
limit, and you do not change one to fit the agent.

**The documents are not complete.** They are a source of ideas, not a list
of every option. You have context that their authors did not have: this
agent, its goal, its traces and the results of your experiments. When the
evidence of this agent says that a document does not fit, do not follow it
to the letter: that is an error, not care. Propose a new solution when it fits
this agent better than the documents do. A new idea meets the same bar as
a documented one: a hypothesis, a predicted effect, the confirmation on
val and the hard limits.

**A clear measurement outranks a document.** A result measured on this task
outranks what a document suggests only when it is clearly past the noise,
as the measurement on train and the confirmation on val judge it. A result
inside the noise does not refute a technique: see
[dealing with a noisy eval](references/improving_agents/playbooks/dealing-with-a-noisy-eval.md).
When two options tie, the knowledge can settle the choice.

## The parts

| Part | What it is | Where |
|---|---|---|
| Smell | An issue in the design of the agent. It is true whether an eval passes or fails. Its document says how to recognise it and links to its remedies. | `references/improving_agents/smells/` |
| Playbook | How to solve one problem or reach one goal, as an ordered list of things to try. | `references/improving_agents/playbooks/` |
| Technique | One optimisation: when to use it, how, how to check it took effect, and its priors. | `references/improving_agents/techniques/` |
| Lever | One thing in the harness that you can change, and how. | `references/levers/index.md` |

The usual path is: this index, then a smell or a playbook, then a technique,
then the levers it uses. Prefer a playbook or a smell: a choice by goal or by
situation is better than a choice by name. Reach a technique by its name, in
the table "Techniques" below, only when the user names it.

Each table gives the task shapes a document applies to. A document applies
only when the task has every shape in its list. `all` means that the shape
does not matter.

## Smells

<!-- BEGIN GENERATED: smells -->
| Smell | Applies to | Description |
|---|---|---|
| `references/improving_agents/smells/document-behind-a-lookup-tool.md` | tools | A long reference document that the agent can reach only by page, by search or by section, through a lookup tool, with no contents to choose from. |
| `references/improving_agents/smells/faulty-inherited-skill.md` | all | A skill that the baseline attaches is wrong or stale, contradicts the task, or holds an example whose answer contradicts a rule. It can be changed as a new version. |
| `references/improving_agents/smells/fixed-call-chain.md` | tools | The agent calls the same tools in the same order on each run, and passes an id from one result to the next call. The model decides nothing new between the calls. |
| `references/improving_agents/smells/general-query-tool-without-a-guide.md` | tools | The agent has a SQL, GraphQL or general API tool, with no examples and no guide to the schema, so it must learn the data model on each run. |
| `references/improving_agents/smells/old-model.md` | all | The baseline's model was released more than 8 months ago. Read its release date yourself, and give its age and the reference. |
| `references/improving_agents/smells/one-file-skill-with-many-topics.md` | all | An attached skill is one long file that holds many topics, with no reference files. The agent reads all of it to use one part of it. |
| `references/improving_agents/smells/skill-too-small-to-earn-its-place.md` | all | An attached skill holds a few words and no other file. Its description is in every run and opening it costs a call, so it can cost more than it saves. |
| `references/improving_agents/smells/too-many-tools.md` | tools | The run config attaches more than 40 tools, and every tool definition is in the context of every call. Count them yourself. |
| `references/improving_agents/smells/tool-results-flood-the-context.md` | tools | A tool returns a very large result - a list with every field, a full schema, many pages - or the agent makes one call for each item of a list. |
| `references/improving_agents/smells/tool-search.md` | tools | The tools are listed nowhere the model can read, so the agent must guess that a tool exists and guess the raw search terms that find it. |
| `references/improving_agents/smells/tools-on-a-live-server.md` | tools | The agent's tools write to a real system, or read data that changes, so the right answer to an eval item moves and a measurement cannot be repeated. A read of fixed data (RAG) is fine. |
| `references/improving_agents/smells/unnecessary-tools.md` | tools | Tools that overlap - two tools used for the same kind of request - or tools never called in the traces. One tool for each job, and each tool needed. |
| `references/improving_agents/smells/very-long-prompt.md` | all | The system prompt is longer than 200,000 characters, or it holds many unrelated topics and each request needs a few. Measure the length yourself. |
| `references/improving_agents/smells/very-long-skill-description.md` | all | A skill description is longer than 1,024 characters, or it holds rules that the agent needs only after it opens the skill. Measure the length yourself. |
| `references/improving_agents/smells/very-long-tool-description.md` | tools | The description of an attached tool is longer than 4,096 characters. Measure each attached tool yourself, and name each tool that is over. |
<!-- END GENERATED: smells -->

## Goals

<!-- BEGIN GENERATED: playbooks-goal -->
| Playbook | Applies to | Description |
|---|---|---|
| `references/improving_agents/playbooks/cheaper-or-faster.md` | all | The user wants the agent to cost less or answer sooner, with quality held - each step is marked cheaper, faster or both, because the two goals do not always agree. |
| `references/improving_agents/playbooks/working-inside-restrictions.md` | all | The user states a restriction - providers, the origin of a model, data retention, a tool that must not change. It is a hard limit on the plan. What to do when the best lever is not allowed. |
<!-- END GENERATED: playbooks-goal -->

## Order of work

Read these before you plan: know the agent first, order the work, and spend
the budget.

<!-- BEGIN GENERATED: playbooks-order -->
| Playbook | Applies to | Description |
|---|---|---|
| `references/improving_agents/playbooks/know-the-agent-before-you-plan.md` | all | Classify the agent before the first plan - its turns, its output, a classifier shape, its tools, skills and model - because each document says which shapes it fits. |
| `references/improving_agents/playbooks/ordering-work.md` | all | How to order the work of an improvement - the priority comes from the smells and the failures of this agent, not from a fixed order of levers. All of it is guidance. |
| `references/improving_agents/playbooks/spending-the-budget.md` | all | How to spend a fixed budget - fewer experiments, each large enough to pass its own test, the cheap techniques first on a small budget, and the scan of models only on a large one. |
<!-- END GENERATED: playbooks-order -->

## Failure patterns

A class of failure seen in the traces of eval items.

<!-- BEGIN GENERATED: playbooks-failure -->
| Playbook | Applies to | Description |
|---|---|---|
| `references/improving_agents/playbooks/answers-not-grounded.md` | all | The answers need knowledge that is not in the agent's context - attach the source, then add scope discipline. A source behind a lookup tool can move into a skill. |
| `references/improving_agents/playbooks/change-the-surface-not-the-words.md` | all | Two text changes failed on one issue, or the failure is mechanical. Change what the model touches before the words it reads. A policy failure comes here only after two text changes failed. |
| `references/improving_agents/playbooks/failure-at-a-tool-call.md` | tools | The failing message comes before or with a tool call - a preamble, or a narration that rides the call. A new tool description, then a directive in the tool's response. |
| `references/improving_agents/playbooks/lost-in-long-instructions.md` | all | The agent misses a part of a long prompt or of a one-file skill. Progressive disclosure when the model reads skills, a prompt structure when it does not. A quick check first. |
| `references/improving_agents/playbooks/malformed-tool-calls.md` | tools | The agent calls a tool with the wrong case, the wrong form of an id, a body on a GET, or a misspelled tool name. A wrapper that normalises, errors the agent can act on, a guard at the tool. |
| `references/improving_agents/playbooks/missing-context-the-agent-could-be-given.md` | tools | The agent fails because it did not know a fact that a tool could give it - if it had known that, it would have done the right thing. A prompt line to always call that tool, or a new tool. |
| `references/improving_agents/playbooks/output-contract-not-met.md` | all | The output breaks its format - broken JSON or JSON that misses the task's schema, a closing block, a layout of free text, an escaping rule, or the form of a field. |
| `references/improving_agents/playbooks/requirement-missing-from-the-prompt.md` | all | The eval checks for something that neither the prompt nor the task instruction asks for. State the requirement in new words - do not copy the eval. |
| `references/improving_agents/playbooks/skill-is-not-read.md` | all | The agent never loads a skill file, guesses a path, or loads the skill and does not follow it. A rewrite of the skill, then a prompt rule. |
| `references/improving_agents/playbooks/wrong-scope-or-refusal.md` | all | The agent answers requests outside its scope, or refuses valid ones. A paragraph of decline rules, then a rebalance for the refusals that remain. |
| `references/improving_agents/playbooks/wrong-tool-chosen.md` | tools | The agent picks the wrong tool, or breaks a rule that the product enforces. Fit the tool layer first when the agent as a whole needs it, then remove and scope tools, descriptions, guards. |
<!-- END GENERATED: playbooks-failure -->

## Eval problems

The measurement is the problem.

<!-- BEGIN GENERATED: playbooks-eval -->
| Playbook | Applies to | Description |
|---|---|---|
| `references/improving_agents/playbooks/dealing-with-a-noisy-eval.md` | all | A score moves between repeats with no change to the agent. Read the noise, predict effects larger than it, confirm on val, and do not let a decision turn on one or two items. |
| `references/improving_agents/playbooks/dealing-with-a-saturated-eval.md` | all | The baseline passes almost every item of an eval, so a candidate has no room to show a gain on it. Keep the eval as a guard, put the effort elsewhere, and ask the user for harder items. |
| `references/improving_agents/playbooks/dealing-with-a-wrong-eval.md` | all | The judge fails right answers or passes wrong ones, or the eval does not measure the issue. Classify each fire, try changes only on the config failures, report the rest. Do not tune toward the judge. |
| `references/improving_agents/playbooks/dealing-with-an-eval-near-zero.md` | all | The baseline passes almost no item of an eval. Read the raw outputs first - text fixes a missing requirement or a wrong format. Try a smarter model only on evidence that the model cannot do the task. |
| `references/improving_agents/playbooks/dealing-with-train-wins-rejected-at-val.md` | all | A train win is rejected at the confirmation on val. Read the reason first - passed over, copied eval text, an eval dropped, no gain, or a gain not clear. Only "no gain" shows no carry. |
<!-- END GENERATED: playbooks-eval -->

## Design

The response to a smell that needs more than one technique.

<!-- BEGIN GENERATED: playbooks-design -->
| Playbook | Applies to | Description |
|---|---|---|
| `references/improving_agents/playbooks/fit-the-tool-layer-to-the-agent.md` | tools | The agent's tools are the company's software APIs, and a good API can be a poor agent tool. Wrap them, do not rewrite them - which wrapper for which problem, and where its rules go. |
<!-- END GENERATED: playbooks-design -->

## Techniques

<!-- BEGIN GENERATED: techniques -->
| Technique | Levers | Applies to | Cost | Description |
|---|---|---|---|---|
| `references/improving_agents/techniques/add-the-missing-requirement.md` | prompt | all | low | One prompt rule, in new words, for a requirement that the eval checks and that neither the prompt nor the task instruction asks for. |
| `references/improving_agents/techniques/answer-only-from-the-source.md` | prompt | all | low | A short prompt rule of scope discipline - answer from the attached source, and say so when the source does not cover the question. |
| `references/improving_agents/techniques/attach-the-knowledge-source.md` | tool_config, skill | all | medium | Give the agent the knowledge its answers need - attach an existing search or RAG tool, or write the knowledge into a skill - when the answers are not grounded. |
| `references/improving_agents/techniques/cap-and-preview-wrapper.md` | new_tool | tools | medium | A wrapper that returns only what this agent needs from a large tool result - a trim that says when it cut and how to get more, a capped preview with a follow-up, or an error when it is too large. |
| `references/improving_agents/techniques/consolidate-tools.md` | new_tool, tool_config | tools | high | Replace many narrow or overlapping tools with a few general wrappers by job, each with the product's policy inside - its permission checks, guards and defaults. |
| `references/improving_agents/techniques/decision-model-for-a-classifier.md` | model | single_turn, structured_output, classifier, no_tools | medium | Run a classifier-shaped task on a decision model - a fast, cheap model that returns a prediction from a fixed set, not text - when cost or latency matters. |
| `references/improving_agents/techniques/decline-rules-paragraph.md` | prompt | all | low | One prompt paragraph that states the agent's scope as rules - what it does, what it declines, how it declines, and what is not a reason to decline. |
| `references/improving_agents/techniques/directive-in-the-tool-response.md` | new_tool | tools | medium | A wrapper whose response states the tool's own status for the reply - derived facts, a fixable error, or how the tool works - as facts about the result, not as orders to the agent. |
| `references/improving_agents/techniques/document-into-a-skill.md` | skill, tool_config | tools | medium | Move a long reference document that sits behind a lookup tool into a skill - a contents body with key terms, one reference file per section - and drop the tool. |
| `references/improving_agents/techniques/errors-the-agent-can-act-on.md` | new_tool | tools | medium | A wrapper that turns a raw tool error into an error the agent can correct from - what was wrong, the valid values or nearest matches, and what to do next. |
| `references/improving_agents/techniques/faster-provider-for-the-same-model.md` | model | all | low | Serve the same model from another provider - a faster one, or a cheaper one - with the harness unchanged, when the user allows that provider and the goal is latency or cost. |
| `references/improving_agents/techniques/guard-tool-calls-at-the-boundary.md` | new_tool, prompt | tools | medium | A check in a wrapper that refuses a call which breaks a rule the product enforces, with an error that says why, and the rule moved from the prompt into the tool's description. |
| `references/improving_agents/techniques/guide-skill-for-a-tool-set.md` | skill | tools | medium | A side skill that describes the agent's tools by progressive disclosure - which tool for which work, then one leaf file per tool or per query area. |
| `references/improving_agents/techniques/long-prompt-into-a-skill.md` | skill, prompt | all | medium | Move the topics of a long prompt into a skill by progressive disclosure - a short prompt, a router body, one reference file per topic, a path index. |
| `references/improving_agents/techniques/model-swap-inside-a-class.md` | model | all | high | Lock one model of the class the task needs, tune the harness on it, then scan the class again for a model that is better, cheaper or faster with that harness. |
| `references/improving_agents/techniques/new-tool-description.md` | new_tool | tools | low | A new description for a tool - a code-tool clone, or a wrapper - for a failure at a call. A rule in the tool moves with the tool, so the prompt does not change with the tool set. |
| `references/improving_agents/techniques/normalize-inputs-wrapper.md` | new_tool | tools | medium | A wrapper that accepts the input forms the agent sends - case, aliases, display numbers, types - maps each to what the tool needs, and names the valid values when it cannot. |
| `references/improving_agents/techniques/one-general-rule-per-edit.md` | prompt, skill | all | low | A text edit states one general rule, with its reason and its source, and replaces text - not one rule for each failing case. |
| `references/improving_agents/techniques/policy-as-step-by-step-procedures.md` | prompt, skill | all | low | Rewrite a policy that is written as prose into numbered procedures, one for each type of request, with yes-or-no conditions and a check after each fix. |
| `references/improving_agents/techniques/prune-one-group-at-a-time.md` | prompt, skill, tool_config | all | low | Find what helps in a large harness - remove one group (a prompt section, a skill, a set of tools) on each candidate and measure it, or add groups one at a time to a bare base. |
| `references/improving_agents/techniques/remove-or-scope-tools.md` | tool_config | tools | low | Drop the attached tools that this task does not need, or that overlap, so the agent chooses among fewer tools and reads fewer descriptions on every call. |
| `references/improving_agents/techniques/rewrite-an-inherited-skill.md` | skill | all | medium | A new version of a skill that the baseline attaches - split, merged, restructured or scrubbed - attached in place of the old one on a new run config. |
| `references/improving_agents/techniques/roll-up-tool.md` | new_tool, prompt | tools | medium | One code tool that does what the agent does in many calls - a fixed chain that passes an id along, a loop of one call per item, or the context the agent needs at the start. |
| `references/improving_agents/techniques/skill-into-the-prompt.md` | prompt, skill | all | low | Move the content of a skill into the prompt and drop the skill - for a small skill, content that most runs need, or a skill the agent does not open. |
| `references/improving_agents/techniques/state-the-output-contract.md` | prompt | all | low | One prompt line that states a format rule the model gets in no other way - a layout of free text, a closing block, an escaping rule, or a rule about a field. |
| `references/improving_agents/techniques/structure-a-long-prompt.md` | prompt | all | low | Give a long prompt a structure - topics under headings, the must-include parts marked, and a last step that checks each required property before the answer. |
| `references/improving_agents/techniques/thinking-level-ladder.md` | params | all | low | Change the thinking level one rung at a time from the baseline's level - up only for hard cases, down for cost or latency once quality is stable - and temperature at most once. |
<!-- END GENERATED: techniques -->

## Dormant techniques

These are not suggested. They stay so that you can see what was tried and why
it is not suggested.

<!-- BEGIN GENERATED: techniques-dormant -->
None yet.
<!-- END GENERATED: techniques-dormant -->
