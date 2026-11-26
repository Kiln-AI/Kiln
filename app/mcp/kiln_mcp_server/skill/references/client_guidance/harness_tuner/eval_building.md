---
name: eval_building
description: Kiln Harness Tuner only, and only when its run turned eval building on - the experimental, not recommended mode in which the loop builds a new eval for an issue that no eval measures. Every other client never reads or follows this file.
---

> **Gate. Read on only if both are true:**
>
> 1. You are a Kiln Harness Tuner agent.
> 2. Your run turned eval building on: the run was started with `--experimental-eval-building`, so your input's `eval_building` is `true`.
>
> Otherwise stop here. Non-Kiln-Harness-Tuner clients never read or follow this file: a chat client creates an eval with `references/knowledge/create_eval.md` and never creates eval data. A Kiln Harness Tuner run with eval building off builds no eval ("When eval building is off" below).

# Experimental eval building (Kiln Harness Tuner)

Eval building is **experimental, off by default, and not recommended**. An eval built inside the loop has no person to answer its questions, review its data or rate its judge. The recommended way to make an eval is the Eval Builder in the Kiln app, with the user (`references/knowledge/create_eval.md`). Turn this mode on only to try it.

## Where the rules live

Kiln Harness Tuner's own instructions hold the rules of this mode, and they win where this file disagrees with them (`SKILL.md`, "Who reads this skill"):

- its batch-plan role and batch-selection skill: when to plan an `eval_only` item or a fix with `needs_eval: true`;
- its eval-build role (`agents/eval_build.md`): how to build the eval. Kiln Harness Tuner has no eval-build skill, on purpose.

This file holds the rules that the shared Kiln documents point to, so that they have one home.

## When eval building is off

This is the default. Plan no `eval_only` item and no fix with `needs_eval: true`: give each fix candidate `needs_eval: false` and the `eval_id` of an eval that exists. Code drops an item that builds an eval before the wave runs. An issue that no eval measures is not a candidate: say so in `rejected_summary`, and the report tells the user to create its eval in the Kiln app. A `smell`, `baseline_audit` or `baseline_judge_copy` issue is not such an issue: it is about the harness, and it is planned on an active eval that the change serves.

## When eval building is on

- **An `eval_only` item** commissions a new eval, through the eval-build agent, for an issue that has none. It is the rare exception, not a routine step: the anti-starvation valve, or a cheap-kill confirmation without committing to a fix this wave. A fix with `needs_eval: true` also builds its eval.
- **An eval for an eval problem.** When an existing eval does not measure the failure that an issue names, an `eval_only` item can commission a new eval for the issue ([dealing with a wrong eval](references/improving_agents/playbooks/dealing-with-a-wrong-eval.md)). When the baseline passes almost every item, it can commission a new eval with harder items for an open issue ([dealing with a saturated eval](references/improving_agents/playbooks/dealing-with-a-saturated-eval.md)). An experiment never changes an existing eval.
- **Closed issues.** Commission none for a closed issue. When the new eval cannot reproduce the issue, the issue is closed as won't fix (`WONT_FIX:`), and an issue that is fixed (`FIXED:`) is never reopened.
- **Binding.** The new eval is bound to its issue with `link_eval` (`references/knowledge/memory.md`, the issue rules).

## The build

The eval-build agent:

- builds an eval that reproduces the issue named in its input. The eval measures the issue, not any planned fix: the agent receives the issue id and the baseline run config only;
- owns the eval's size and type, and sets its priority at creation (a best guess beats a blank);
- gives it pre-sized train, val and test splits: train large enough for paired verdicts, val for the confirmation (`references/knowledge/train_val_test.md`);
- runs the reproduction and baseline pass on the train split only. It never reads val or test results, and never reads the `baseline` memory record;
- freezes the eval at handoff;
- reports `reproduced: false`, with the reason, when it cannot reproduce the issue. That is a valid, useful outcome.
