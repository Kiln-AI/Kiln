---
status: draft
---

# Prototype results: grounding with `claude -p`

The checkpoint after phase 2 (`implementation_plan.md`). The prototype command planned cases with
kiln_server's batch planner, drafted simulated users with kiln_server, and grounded each case with
`ground --engine claude` on `claude-opus-5-5`. Runs were made 2026-11-17 and 2026-11-18. The raw
outputs are in a scratch folder, not in the repo.

## Setup

- Three OpenEnv servers, all on a local Seahaven branch that merges Kiln-AI/Seahaven#51 and #52
  (`in-flight.md`):
  - the customer world (the eb3 harness's world), nine fixtures, an `acting_user` startup keyword;
  - a payments-API world, three fixtures, no acting user;
  - a commerce world, three fixtures, no acting user.
- The customer world was run on the four eval definitions from the eb3 runs in the integration-tests
  repo: each run's specification text, Data Guide and task prompt. The other two worlds got a short
  task prompt, specification and Data Guide written for the test.
- Base guidance: `multiturn_plan_guidance` with the OpenEnv wording of the "you can't see the
  system" paragraph from the plan page.
- kiln_server ran locally. Production's batch planner returned 500 for every request on
  2026-11-17, including a one-line control request.

## Results

After the prompt changes in `6c448ca8b` and with setup notes in the customer world's `setup_sql`
description (below):

| World | Eval | Grounded | Used setup SQL | Tool calls, mean (range) | Resets, mean (max) | Input tokens per case |
|---|---|---|---|---|---|---|
| customer | Apps, 2-case smoke | 2/2 | 1 | 12 (10-14) | 2.5 (3) | 0.99M |
| customer | Apps | 4/6 | 3 | 22 (17-27) | 7.7 (9) | 1.48M |
| customer | Records | 6/6 | 2 | 15 (10-21) | 2.8 (4) | 1.64M |
| customer | Data accuracy | 6/6 | 1 | 11 (5-20) | 1.8 (5) | 1.32M |
| customer | How-to | 6/6 | 2 | 14 (5-22) | 2.3 (5) | 1.31M |
| payments | Billing operations | 6/6 | 1 | 12 (7-18) | 2.0 (3) | 0.34M |
| commerce | Store operations | 6/6 | 0 | 9 (5-18) | 1.7 (3) | 0.38M |

36 of 38 cases grounded. Both drops were `unrepresentable` (below). No case failed for a tooling
reason. Input tokens were 93% cached; on a subscription that is plan usage, and on an API key it is
roughly $1 to $1.50 per customer-world case on Opus.

The references were specific and backed by tool results: exact ids, counts, totals and dates; a
confirmation turn before a destructive change; the records that must stay unchanged; and the
plausible wrong answers named under `must_not_happen` (for example the subset of jobs whose titles
match, presented as the whole list). Simulated users were filled in with real people and values and
kept their wording.

## How we got there

| Run | Change | Result |
|---|---|---|
| 1 | Phase 2 as built | 1/2. The grounded case switched from the feature the spec tests to an unrelated one. The dropped case looked only at the starting state the planner named. |
| 2 | Grounding agent gets the specification, the target task's prompt and the Data Guide; prompt rules on subject, starting states, `seed`, `read_state` (`6c448ca8b`) | 0/2, both drops sound: it kept the subject and tried other starting states, but couldn't write setup data. |
| 3 | The customer world's setup notes appended to the `setup_sql` description | 2/2, then 4/6, then 18/18 on the other specs |

## Findings

1. **The grounding agent needs the eval's inputs.** Without the specification it changes a case's
   subject to make it fit. Now in the functional spec (`Grounding agent → Input`).
2. **Setup instructions belong in the reset schema, and some worlds need them.** The customer
   world stores rows under names that differ from its API, and an App record needs companion index
   rows. Without notes the agent either guessed by trial and error (run 1) or dropped (run 2). The
   payments world needed none: its storage mirrors its API, and the agent wrote correct setup SQL
   from the API's own answers. A world adds them with `World(setup_sql_notes=...)`, new in
   Kiln-AI/Seahaven#52.
3. **The planner names starting states.** 14 of the 38 scenarios name a fixture: every scenario in
   the data-accuracy, how-to and first Apps plans, none in the other four, despite the guidance. The grounding agent
   treats it as a hint, so nothing dropped, but it narrows the plan. The planner guidance needs a
   firmer rule or an example.
4. **A refusal the server doesn't enforce.** The customer world lets every role change App records.
   A case that expects a refusal there was dropped twice and grounded once ("the refusal has to come
   from the assistant"). The eb3 harness avoided this upstream: its planner and agent were told the
   world's role conventions, and its rule was "the world decides: do not write the refusal case".
   Specific to that spec and world. Our current behavior (drop) is the safe one; the prompt should
   say so explicitly so it stops varying.
5. **Effort.** The reset limit is tight on harder cases (9 of 10 in three cases). Repeated discovery
   after every reset drives most calls; the eb3 harness avoided it by giving the agent the company,
   users and Apps up front. Simpler worlds used a quarter of the tokens.
6. **Seed.** Seahaven worlds refuse a reset without `seed`, which the reset-arguments brief hides as
   an OpenEnv field. The grounding agent now always passes one, and it is saved in `openenv_reset`.

## Compared with the eb3 harness, same spec (Apps)

- eb3 attempted 141 items and made 100 cases. Leaving out 30 crashes (mostly a usage limit), it
  served 90%; 2 items were dropped as not fitting the data. We grounded 6 of 8.
- Facts are comparable. eb3's expected changes are keyed by row and replayed by code, so they catch
  mistakes ours can't: ours are prose. One of ours is likely wrong (inferred, not run): it forbids
  "updating any entry", but this world records a delete as an update.
- eb3 used about 0.45M input tokens, 10 calls and 2 resets per case; we used 0.8M to 1.7M, 10 to 27
  and 2 to 9.
- Its agent prompt is 63 KB against our 5.7 KB, mostly world conventions, pagination traps and a
  per-role style guide for the simulated user.

## The measured run: Haiku through Kiln

`ground --engine kiln` on Claude Haiku 5.5 (Anthropic provider), the same 38 cases and plans, run
2026-11-18. Prompt caching was off in the first attempt (fixed in `57a70d58f`); every number below
is with it on, 84-93% of input tokens cached, no case with incomplete usage.

| Prompt | Grounded | Cost | Notes |
|---|---|---|---|
| Phase 3 prompt | 28/38 | $3.85 | 4 sound refusal drops; about 6 drops where Opus used a similar item or setup data |
| + "use one of the same kind, or add it" rule | 33/38 | $4.64 | One case changed what it tests ("delete my entry from today" became a not-found case) |
| + "keep the scenario's situation" rule | Apps 3/6, Records 6/6 (the two plans rerun) | $2.21 | The changed case now adds today's entry with setup and keeps the delete; every remaining Apps drop is a sound `unrepresentable` |

- About $0.14 per grounded case, against about $0.98 for Opus through `claude -p`.
- Haiku's references are usable but thinner: fewer facts and fewer named wrong answers. On one
  data-accuracy case it counted 29 work orders by name match where Opus counted 28 and named the
  edge case.
- Both rules go into the grounding prompt in phase 4. Opus was not rerun through Kiln.

## Open for the next checkpoint

- Measure the cheaper model on the same plans (phase 3's measured run).
- Prompt: the refusal rule (finding 4) and a rule against changing more than the user asked
  (`must_not_happen` should not forbid how the server records the expected change).
- Planner guidance: stop naming starting states (finding 3).
- Whether references should carry expected changes in a checkable form. Out of scope for v1 unless
  the judge results show prose isn't enough.

## Follow-ups outside Kiln

- Seahaven: `World(setup_sql_notes=...)`, added to Kiln-AI/Seahaven#52. The runs above used a
  local testing hook that appended the same text.
- The customer world: its setup notes on a local branch, waiting for a Seahaven release.
