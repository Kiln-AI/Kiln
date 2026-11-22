---
title: Dealing with a wrong eval
description: The judge fails right answers or passes wrong ones, or the eval does not measure the issue. Classify each fire, arm only the config failures, report the rest. Do not tune toward the judge.
reviewed: 2026-11-13
kind: eval
applies_to: all
---

# Dealing with a wrong eval

## Situation

The measurement is the problem, not the agent. Signs:

- the eval fails items, and the outputs are right: the judge's reasoning
  ends in a pass and its score is a fail, or the judge fails an answer for
  a reason that the criteria do not state;
- the judge passes outputs that are wrong;
- the expected outputs cannot be met, or they disagree with each other or
  with the task's instructions;
- an issue says the agent fails in some way, and the eval does not
  measure that way at all.

No change to the run config fixes an eval. A fix arm on a false fire
tunes the agent toward the judge, not toward the task.

## What to try, in order

1. Read the fires. For each failing item, read the output, the expected
   output and the judge's reasoning. When the sign is false passes, read
   a sample of passing items too. Name each fire as a config failure, an
   eval-data failure or a judge failure. Only a config failure is a
   candidate for an arm. An environment failure (a tool server, the
   provider) or noise (the same config passes it on another run) gets
   nothing until it recurs.
2. When it is not clear that the baseline still fails in the way an
   issue says: measure the issue on the current baseline (a
   `measure_issue_baseline` item).
3. A judge that gives different verdicts on the same output is a judge
   failure. Report it as in step 4. To plan arms against that noise in
   the meantime:
   [dealing with a noisy eval](references/improving_agents/playbooks/dealing-with-a-noisy-eval.md).
4. For the eval-data failures and the judge failures: report them in
   `open_questions` for the eval's owner. Give the items that show them
   and what is wrong in each: the reasoning against the score, or the
   expected output against the instructions. The fix is a change to the
   eval: corrected expected outputs, or a judge calibrated against human
   labels. The tuner does not change an existing eval. When the eval does
   not measure the failure that an issue names, report that too. Only
   when `eval_building` is `true`, an `eval_only` item can commission a
   new eval for the issue, under the rules of the planner's skill for
   that item.
5. Take the config failures that remain to their playbook:
   [ordering work](references/improving_agents/playbooks/ordering-work.md).

## What not to do yet

- No fix arm aimed at a judge failure or an eval-data failure. No config
  change can fix it, so its spend is lost.
- Do not read a judge's score without its reasoning. A score that
  disagrees with the reasoning is a judge failure.
- Do not change the prompt to please the judge. Such an arm fits the
  judge, not the task. The judge-copy check catches only copied text: a
  run of 8 or more words shared with the text of an eval. Judge-pleasing
  in new words passes that check.

## Budget

The order does not change with the budget. Steps 1 and 2 cost little.

## Priors

- **A merchant assistant agent of a commerce platform, scored by LLM
  judges.** The team calibrated each judge against human labels, by
  iterative changes to the judge's prompt. The agreement with the human
  labels (Cohen's kappa) went from 0.02, near chance, to 0.61, against
  a human baseline of 0.69. One sample, not a rule.
  Source: public, the Shopify post "Building production-ready agentic
  systems: Lessons from Shopify Sidekick". 2025-08-26.
- **A data-analysis agent, scored by an LLM judge.** One eval had a trap:
  a common wrong method gave 2.03%, and the right answer was 2.04%. The
  judge accepted the wrong answer 35% of the time. One sample, not a rule.
  Source: public, the Hex post "How we built a lab to evaluate data
  agents". 2026-05-22.
