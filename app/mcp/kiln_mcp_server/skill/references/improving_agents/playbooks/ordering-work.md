---
title: Ordering work
description: How to order the work of a run - the priority comes from the smells and the failures of this agent, not from a fixed order of levers. All of it is guidance.
reviewed: 2026-11-16
kind: order
applies_to: all
---

# Ordering work

## Situation

Read this before each plan. There is no fixed order of levers that fits
every agent. The priority comes from what this agent shows: the smells of
its design, the failures in its traces, and the problems of its evals. A
measured result on this task replaces any order that a document suggests.

Three facts shape the order:

- **The model and the harness are a pair.** A harness that is good for a
  large model can be poor for a small one, and the reverse. Each change to
  the harness is measured with one model. A change of model changes what
  each of those changes does.
- **The prompt is tuned with the other parts, not alone.** A prompt rule
  that a tool or a skill makes unnecessary is text that the agent reads on
  every call.
- **Some problems hide all other signals.** When a tool result sometimes
  floods the context, a small fix elsewhere cannot show its effect until
  the flood is gone. Each smell says in "What it blocks" which work waits
  for its fix.

## What to try, in order

1. [Know the agent before you plan](references/improving_agents/playbooks/know-the-agent-before-you-plan.md),
   when the shapes of the agent are not yet known.
2. When the model is a lever (`allowed_models` lists another model, and
   the guidance does not forbid a model change) and the baseline model
   passes almost nothing across the evals: find a model with some aptitude
   for the task. This case may need a smarter model before the harness
   tuning. Read the outputs first: a missing requirement or a wrong format
   can put a capable model near zero, and text fixes it. Change the model
   only on evidence that it cannot do the task. That evidence is one of
   two things: the reads show answers wrong in substance, or repeated arms
   on sound fixes did not move the score. See
   [dealing with an eval near zero](references/improving_agents/playbooks/dealing-with-an-eval-near-zero.md).
   Lock that model, then tune the harness. When the model is not a lever,
   it is the environment of the task, and this step does not apply.
3. A problem of the measurement, when an eval cannot show the change that
   an arm predicts. A fix measured on such an eval teaches nothing. Take
   it to its playbook:
   [a saturated eval](references/improving_agents/playbooks/dealing-with-a-saturated-eval.md),
   [a wrong eval](references/improving_agents/playbooks/dealing-with-a-wrong-eval.md),
   [a noisy eval](references/improving_agents/playbooks/dealing-with-a-noisy-eval.md), or
   [train wins rejected at validation](references/improving_agents/playbooks/dealing-with-train-wins-rejected-at-val.md).
4. A smell that blocks the work you plan. Its document, in the planner's
   entry file, names its remedies. For a smell of the tools:
   [fit the tool layer to the agent](references/improving_agents/playbooks/fit-the-tool-layer-to-the-agent.md).
5. Each failure to its playbook, in the table of failure patterns of the
   planner's entry file. One technique in one experiment. A technique can
   be a set of changes (a tool, its prompt line and its guide skill), and
   the set is measured as one. When two text arms failed on one issue:
   [change the surface, not the words](references/improving_agents/playbooks/change-the-surface-not-the-words.md).
6. A short screen of the settings:
   [thinking level ladder](references/improving_agents/techniques/thinking-level-ladder.md). It is
   low cost, and it fits a small budget, for example when no known harness
   problem is open. A setting changes how the same model reads the same
   harness, so it teaches little while the harness has a known problem.
7. A scan of the model class again, after the harness is tuned, when the
   model is a lever:
   [model swap inside a class](references/improving_agents/techniques/model-swap-inside-a-class.md).
8. Cost and latency, after quality is stable, when the guidance of a
   quality run asks for them: [cheaper or faster](references/improving_agents/playbooks/cheaper-or-faster.md).
   Under a `speed` or `cost` objective, quality is held, not tuned: the
   screening round of the planner's skill comes first, and that playbook
   applies from the start of the run.

## What not to do yet

- No settings scan and no model scan while a smell blocks the work, or
  while the failures have a cause in the harness, on a quality run. The
  result would not transfer to the fixed harness. Under a `speed` or
  `cost` objective, the screening round of the planner's skill scans the
  thinking levels and the models first, and that procedure replaces this
  line.
- Do not change many unrelated things in one arm. When it wins, nothing
  says which part helped. When it loses, a good part is lost with a bad
  one. A search over every part at once grows too fast to measure.
- Do not tune the harness on a very large model and expect the result to
  hold on a small one. A change of class is a new start.
- Do not follow this order against a measured result. Each step holds
  only when its condition holds, and the smells and the failures of
  this agent set the priority.

## Budget

On a small budget, step 7 is often left out: pick a model of the right
class with some aptitude for the task, and tune the harness. On a large
budget, a scan of the models of the class before the lock becomes
reasonable, when the model is a lever. The settings screen of step 6 is
low cost, and it fits a small budget too. See
[spending the budget](references/improving_agents/playbooks/spending-the-budget.md).

## Priors

- **A customer-support agent in production, at a large company.** The
  first version had a knowledge-base search tool and a tool that hands the
  conversation to a person, and it could not act in the domain. Later
  versions added, in turn: a routine made from the operating procedures
  of the human agents, tools for the domain and escalation, then rules for
  which tool to choose and a limit on the length of answers. Each change
  came from failures that the offline evals showed. One sample, not a
  rule.
  Source: public, the paper "Building Customer Support AI Agents at
  100M-User Scale: An Evaluation-Driven Framework". 2026-06-07.
- **A general assistant agent with tools, in a simulated phone
  environment, tuned by an automatic harness optimiser.** The optimiser
  put its changes in two groups: changes to code (new tools, the agent
  loop, the infrastructure), and changes to text only (prompts, tool
  descriptions, reminder texts). A schedule made the code changes first
  and the text changes after them. In an ablation, the test pass rate was
  60.7% with the schedule and 54.8% without it. One sample, not a rule.
  Source: public, the paper "AutoSaddler: Automatic Harness Optimization
  with Durable Updates from Agent Execution Traces". 2026-08-24.
