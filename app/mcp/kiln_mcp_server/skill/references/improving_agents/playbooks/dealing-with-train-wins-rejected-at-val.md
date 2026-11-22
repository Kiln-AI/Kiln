---
title: Dealing with train wins rejected at validation
description: A train win ends REJECTED AT VAL. Read the reason first - passed over, copied eval text, an eval dropped, no gain, or a gain not clear. Only "no gain" shows that the win did not carry.
reviewed: 2026-11-13
kind: eval
applies_to: all
---

# Dealing with train wins rejected at validation

## Situation

An arm wins on train, and its experiment record ends `— REJECTED AT VAL`.
The stamp does not say why. Code writes the reason on the same record, in
one line with no numbers:

- **C, blocked:** `- blocked at the val gate <MM-DD>: …`. The prompt
  copies eval text. The line names the copied passage and the eval.
- Else a line `- rejected at the val gate <MM-DD> vs baseline <rc> — `
  with one of these reasons:
  - **B, passed over:** `passed over: not promoted; rc <id> was promoted
    instead.` Another candidate won the same gate.
  - **D1, an eval dropped:** `an eval dropped at val: down beyond doubt on
    eval <id>, …`
  - **D2, no gain:** `no gain at val: no targeted eval improved.`
  - **D3, a gain not clear:** `a gain at val, not clear: a targeted eval
    improved, but not beyond doubt.`
  - `not promoted at val; details in the run report.` Code could not
    tell the reason.

Only D2 shows that the arm does not carry to items it was not built on.
One rejection is one case. A pattern is the same reason on several
records.

The causes of D2, in the order in which they are cheapest to check:

- **Copied content.** The arm carries a value, a phrase or a case from the
  train items or from the eval. It fits those items and nothing else. The
  judge-copy check finds some eval copies, not all.
- **Rules for small groups.** Each arm adds a rule for the few items that
  failed. Each rule fits its items and does not transfer.
- **Selection under noise.** Many small arms are measured, and the one
  that wins on train is the one that the noise favoured. Its gain is
  smaller, or gone, on new items.
- **Text where the surface is the problem.** A text rule asks the model
  to avoid a mechanical failure that a tool change would remove.

## What to try, in order

1. Find the reason of each rejection before you plan. A record written
   before the reasons ends its line `— did not beat it; details in the run
   report.` Its reason is not known. When another experiment record
   carries `— PROMOTED` with the same `<MM-DD>`, it is probably B.
   Otherwise, it is not evidence of overfit by itself. Then take the step
   for the case of each record below.
2. **B:** the win stays merge-eligible as an ingredient. Never resubmit
   that rc alone, and never the same combination that lost. Merge it when
   the merge timing of your planner skill says so. Do not rebuild it.
3. **C:** an overfit with a known cause. Remove the copied text, and
   state each rule in new, general words:
   [one general rule per edit](references/improving_agents/techniques/one-general-rule-per-edit.md).
4. **D1:** the change broke the evals that the line names. They dropped
   at val. This is not overfit by itself. In the next arm on the same
   idea, measure each eval that the line names on train (list it in
   `evaluation_target`), so that train shows the break before the val
   gate. When a named eval is one that the arm set out to move (its
   experiment record and your plan say which), the train gain reversed on
   new items: read it as D2. Under the speed or cost objective, the drop
   is a fact on the record, but the arm can also have lost for its speed
   or its cost.
5. **D2:** the train win did not carry to new items. This is the overfit
   case. Check its causes in order:
   - copied content: rebuild with each rule in new, general words, with
     the same [technique](references/improving_agents/techniques/one-general-rule-per-edit.md);
   - rules for small groups: group the failures by cause, and write one
     general rule for the cause that explains the most items;
   - selection under noise: fewer and larger experiments, each with an
     effect that can show above the noise:
     [spending the budget](references/improving_agents/playbooks/spending-the-budget.md) and
     [dealing with a noisy eval](references/improving_agents/playbooks/dealing-with-a-noisy-eval.md);
   - then change the surface, when the failure is mechanical or two text
     arms on one issue ended D2:
     [change the surface, not the words](references/improving_agents/playbooks/change-the-surface-not-the-words.md).
6. **D3:** the val split can be too small to confirm a real gain. Do not
   drop a sound idea on this alone. Merge it with other wins on the same
   eval, so that the combined effect is larger, or plan the next arm on
   the idea with a larger predicted effect:
   [dealing with a noisy eval](references/improving_agents/playbooks/dealing-with-a-noisy-eval.md).

## What not to do yet

- Do not read every `— REJECTED AT VAL` as overfit. B, D1 and D3 do not
  show that an arm fails on new items.
- After D2 on an issue, do not plan another text arm of the same kind for
  that issue.
- Do not read a train win as a result until validation confirms it. A
  train win is a candidate.
- Do not decide from a score alone. The reasons of a judge and the
  failing items say what to change. A score alone says only that
  something changed.

## Budget

On a small budget, step 1 and the cases B and C come first: they cost
reads, and a merge or one rebuild. In D2, the first two causes cost reads
and one rebuild. The third means fewer arms on that eval, not more spend.

## Priors

- **A multi-agent research agent, tuned by a prompt optimiser, on a split
  with no topic shared between train, validation and test.** Over three
  seeds, the gap between the gain on validation and the gain on held-out
  items ranged from 0.034 to 0.160. When the feedback for each criterion
  was reduced to one score, the transfer to held-out items became
  negative. One sample, not a rule.
  Source: public, the paper "Reflective Prompt Optimization of a
  Deep-Research Agent: A Topic-Disjoint, Multi-Seed Protocol for
  Measuring Transferable Gains and Prompt-Level Overfitting". 2026-10-08.
