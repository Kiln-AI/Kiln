---
title: Policy as step-by-step procedures
description: Rewrite a policy that is written as prose into numbered procedures, one for each type of request, with yes-or-no conditions and a check after each fix.
reviewed: 2026-11-13
status: active
levers:
  - prompt
  - skill
applies_to: all
cost: low
---

# Policy as step-by-step procedures

## When to use

- The agent follows a policy: the rules of a support desk, an operations
  team or a compliance process. The policy is written as prose: long
  statements, with the conditions inside the sentences.
- The traces show the agent skip a check, do the steps in the wrong order,
  stop after a part of the fix, or choose a branch that the policy does
  not allow.
- The model is small or medium. A small model has more difficulty with a
  long policy in prose than with explicit steps.

## When not to use

- **The policy is short and the agent follows it.** A rewrite changes the
  words and fixes nothing.
- **The failure is at a tool call**: a malformed call, a wrong argument, a
  call to the wrong tool. Change the tool surface first, and put the rule
  in the tool's own text, not in prompt steps. This is a very strong
  preference: text in a tool moves with the tool, so a later change of the
  tool set needs no prompt change.
- **A rule is missing from the policy.** A procedure for a rule that does
  not exist cannot help:
  [add the missing requirement](references/improving_agents/techniques/add-the-missing-requirement.md).
- **A very capable model already follows the prose.** Check the traces
  first. The gain is likely smaller on a strong model.

## Alternatives

- [Long prompt into a skill](references/improving_agents/techniques/long-prompt-into-a-skill.md), when there are
  many procedures and each run needs one or two of them.
- [Add the missing requirement](references/improving_agents/techniques/add-the-missing-requirement.md), when the
  agent follows the policy and the policy does not cover the case.

## How

The change is an edit of the [prompt](references/levers/prompt.md), or a new
version of the [skill](references/levers/skill.md) that holds the policy.

1. **List the types of request** that the policy covers. Write one
   procedure for each type.
2. **Write each procedure as numbered steps.** One action for each step.
   Use imperative verbs: "check X", "if Y, do Z".
3. **Make each condition a yes-or-no branch.** Write the branches out, not
   a sentence with "unless" or "in some cases".
4. **Add a check step after each fix**: the agent confirms that the step
   worked before it goes on. Say what to do when it did not.
5. **Keep the content of the rules. Change only the form.** Each rule of
   the old policy is in a procedure, or its removal is stated in the
   hypothesis.
6. **Remove the prose version on the same edit.** Two versions of one
   policy can disagree.
7. A strong model can draft the rewrite from the policy text. It writes from
   the policy, never from the train items (the leak rules of
   `references/knowledge/train_val_test.md`).

## Check that it took effect

Run the candidate on two or three train items that need a procedure. In each
trace, find the steps of the procedure in the order it gives, and the check
step after a fix. When the agent still skips the same step, the procedure
did not reach it, or the step is not the cause.

## Budget

Low cost to build: one prompt edit, or one skill version. Measure it on its
target evals. When it fixes its target, the confirmation on val measures
every eval before a candidate becomes the baseline, the evals that the
policy touches too. That matters here, because a rewrite changes many
behaviours at once. On a small budget, take it when the traces show steps
skipped or out of order.

## If it does not move the evals

It depends. Keep it when the procedures are shorter than the prose and no
eval falls, because a shorter and explicit policy is easier to maintain and
to extend. When it is not shorter and no eval moves, it adds nothing.

## Priors

- **A telecom support agent on a small model, with a simulated user.** A
  frontier model rewrote the agent's domain policy into step-by-step
  procedures, with yes-or-no conditions and a check step after each fix.
  On a subset of 20 scenarios, each run twice, the pass rate rose from
  0.55 to 0.675. One sample, not a rule.
  Source: public, the Quesma post "Tau² benchmark: how a prompt rewrite
  boosted GPT-5-mini by 22%". 2025-09-12.

## Confidence

Low to medium. One public case, on one benchmark, with a small sample. It
agrees with model vendors' prompt guidance, which says that explicit and
ordered steps help smaller models. No case on a strong model is recorded
here.
