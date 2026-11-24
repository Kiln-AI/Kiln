---
name: run_an_experiment
description: How to measure a change to an agent, judge it and keep it - why Kiln Harness Tuner is the path for real optimization, then the key lessons for a one-off idea in the chat - before you start, the hypothesis, a quick check, cost, build, measure on train, confirm on val, keep or discard, record and report, and comparisons the user asks for.
---

If you are Kiln Harness Tuner, follow your system prompt. It has similar concepts, but better enforcement.

# Run an experiment

The one statement of how a change to an agent is measured, judged and
kept; other files name this path. What to try is in the playbooks, smells
and techniques (`references/improving_agents/index.md`); how to change each
part of a run config is in its lever (`references/levers/index.md`); the
split rule and the leak rules are in
`references/knowledge/train_val_test.md`.

Endpoint docs (read each before its first call):

| Step | Endpoint doc |
|---|---|
| Create a run config | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md` |
| Run the task once | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run.md` |
| Start an eval job; wait; read its errors | `references/knowledge/api_docs/post_api_jobs_evals_run.md`, `references/knowledge/api_docs/post_api_jobs_wait.md`, `references/knowledge/api_docs/get_api_jobs_id_errors.md` |
| Per-item results of one split | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_run_config_run_config_id_results.md` |
| Paired statistics | `references/knowledge/api_docs/post_api_statistics.md` |
| Memory records | `references/knowledge/memory.md` |

## Two paths

Choose the path before anything else, and push hard for the first one.

- **Kiln Harness Tuner**, for advanced optimization. It runs the whole
  loop: many waves of experiments, managed automatically. It enforces the
  principles of this file in code: the train-only fence, the noise and
  detectability checks, the screening, the leak, judge-copy and integrity
  checks, the keep rule and the memory records. It is much more robust
  than experiments run by hand in a chat. It takes a while and can use
  many tokens. Recommend it, and say what it does, whenever the user wants
  an agent improved beyond one or two clear ideas: taken as far as it
  goes, many rounds, or a search over many ideas. Even in a chat, never
  take over the management of many waves of experiments yourself.
- **A one-off**, when the user wants to try one or two clear ideas. Do it
  in the chat, with the procedure of this file, and do not start Kiln
  Harness Tuner.

When it is unclear which the user wants, ask. The rest of this file is the
one-off path: the key lessons, by hand. Nothing here enforces them but you.

## Words

- **Baseline**: the run config that the experiment starts from, its parent.
  It is the run config in the `baseline` record of
  `references/knowledge/memory.md` when there is one. Otherwise it is the
  task's default run config, else the newest: say which. After a candidate
  is kept in this work, the baseline is the kept candidate. Never write the
  `baseline` record.
- **Candidate**: a new run config, the baseline with one change.
- **Target eval**: the eval that the change is built to move.
- **Guard eval**: every other eval of the task, which the change must not
  break.

## Before you start

- **The agent is known**: `references/knowledge/diagnose_an_agent.md` has
  the calls, and
  [know the agent before you plan](references/improving_agents/playbooks/know-the-agent-before-you-plan.md)
  what to look for.
- **An eval measures the problem**, with a default judge (the eval's
  `current_config_id`). When there is none, an eval comes first:
  `references/knowledge/create_spec.md`, and the user agrees to it.
- **The eval has a train and a val split.** With only a test split, the
  splits come first (`references/knowledge/train_val_test.md`, "An eval
  with only a test split"); do not go on with the test split.
- **The baseline run config is known**, and it has scores on train.
- **The user gave** the goal, the restrictions (providers, models, data),
  the models allowed, and a spend limit. Ask for what is missing, and tell
  the user what you assume. Record a restriction that the user states as a
  `constraint` (`references/knowledge/memory.md`).
- **No fine-tuning and no prompt optimizer as a change**, unless what the
  user asked names one. Kiln has a prompt optimization API; it is not a
  lever of this procedure.

The order is fixed: an eval with a judge, then a run on each split you
need, then a comparison.

## The hypothesis

Write it before you build, and tell the user. It goes in the candidate's
name, description and `provenance` (below):

- **One change**, through one lever.
- **The failure it fixes**: the issue, and the train items that show it.
- **The target eval**, and the guard evals.
- **The predicted effect** on the target eval, never larger than the room
  the baseline leaves on train (a pass/fail score cannot gain more than the
  baseline's failures). Never carry a magnitude over from another task. A
  significant result on a pass/fail score needs at least 6 changed items,
  all one way, for p < .05: with less room than that, the target eval can
  only show a nominal gain. When the effect is smaller than what the eval
  can show, or than its noise, read
  [spending the budget](references/improving_agents/playbooks/spending-the-budget.md)
  and [dealing with a noisy eval](references/improving_agents/playbooks/dealing-with-a-noisy-eval.md).

What a cheap candidate can measure is not a question for the user: when
the cheapest change is the only one that reaches every target failure,
try it.

## A quick check

A quick check answers one question about the mechanism ("does the model
call the new tool?") on a few train items. It is not a measurement.

- **Fork one change** from the parent, and name the fork
  `PROBE <id>: <what>`, so that nobody forks it or measures it. Give it
  `provenance` like any candidate. Never change the parent.
- **Keep the parent's model, provider, thinking level and sampling.** A
  variant of those is a candidate for the evals, not a quick check.
- **Run it on at most 6 train items, 3 by default**, and read each trace.
  For a question about a parameter or a mode, run the parent on the same
  items too, and compare.
- **The answer:** 2 of 3 is yes, 0 of 3 is no, 1 of 3 is unclear, unless
  the question was "ever". Give the counts.
- **It answers no speed or cost question.** Speed and cost are measured
  only against the baseline, on the same items (below).
- A quick check that needs an hour is an experiment.

## Cost before you spend

Price every cost lane before you spend, with
`references/knowledge/experiment_costing.md`: the lanes, their formulas,
how to measure each variable, and when to ask first. Run the target eval
on a few train items first: the eval job with `"split": "train"` and
`item_ids`. A later full run reuses the scores of these items. The
estimate covers the runs on train and the confirmation on val. Tell the
user the estimate.

## Build the candidate

- **New objects only.** Never change the baseline, or anything it uses, in
  place (`references/knowledge/working_with_project_files.md`).
- **Copy every property of the parent, and change one.** The lever of the
  change gives its rules (`references/levers/index.md`); the calls are in
  `references/knowledge/model_create_configs.md`,
  `references/knowledge/prompt_rewrite.md`,
  `references/knowledge/adding_skills.md` and
  `references/knowledge/code_tool_authoring.md`.
- **The hypothesis goes in the run config**: its name says the change, and
  its description and `provenance` give the hypothesis, with the parent in
  `derived_from_ids`.
- **Text you add:**
  - A rule replaces text. The prompt and the skills do not grow by
    default: a new rule replaces or deletes text that said it less well,
    or that a tool now does.
  - When a tool takes over a step, delete the prompt rule for that step.
  - Each rule names its source: the task's instructions, a tool's
    behaviour that a trace shows, the product's documentation, or a
    general principle. A rule that you can state only by pointing at one
    item is a hack.
  - Read every text the model sees about what you changed (the tool's
    description and each parameter's, the skill's `SKILL.md`): it must not
    contradict the change, and it must cover what the target items need.
  - When you detach, rename or replace a skill or a tool, find each
    mention of its name in the prompt and the skills, and update it.
- **Follow the leak rules** of `references/knowledge/train_val_test.md`
  before you measure: search the change for any value of a train item,
  any text of an eval, a judge or a spec, and any rule aimed at a grader.
- **Check that the change took effect**, with the check of its technique
  ("Check that it took effect"): run the candidate once or twice on train
  items that show the failure
  (`references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run.md`)
  and read the trace. A tool never called, a skill never read, an output
  the same as the parent's: the change did not reach the agent. Do not
  measure it; its verdict is "not applied". Fix the build or drop the
  idea.

## Measure on train, and judge

1. Start the eval job on the **train** split for the candidate, the target
   eval first (`"split": "train"`). Run the baseline on the same items when
   it has no scores on them. Wait for the jobs
   (`references/knowledge/api_docs/post_api_jobs_wait.md`).
2. Read the errors of each job
   (`references/knowledge/api_docs/get_api_jobs_id_errors.md`) and the
   coverage: items scored out of items in the split, for each side.
   - Below about 95%, adopt graded caution and check the missing items for
     skew: say which went dark and whether they share anything ("no
     pattern" is a finding too).
   - An eval with no results is missing evidence, never a zero. The same
     job again measures only the missing items; never fill a gap by
     estimate.
   - A guard eval that you chose to measure (step 5) and that has no
     results means the candidate usually cannot pass: you cannot show
     that it did not break it.
3. Compare the candidate with the baseline item by item, with the paired
   statistics call: the recipe of `references/knowledge/eval_scores.md`, on
   the train split. Read each eval's direction before you call a change a
   gain or a loss: on a `lower_is_better` eval, a falling pair of scores
   is a gain.
4. Read the candidate's failing and broken items: output, expected output,
   judge's reasoning, trace.
   - **The expected outputs are the user's policy.** An expected output
     that applies a rule the task's instructions do not state is not an
     eval fault: a run config that misses the rule has a config failure.
     Call it the eval's fault only when the expected output contradicts
     the instructions, or the expected outputs of the same kind of input.
   - **A judge may read the config.** A judge that scores the full trace
     sees the tool results, a loaded skill among them. When only skill or
     tool-description wording changed and a judged score moved, check
     whether the judge grades the config's own words.
   - **A dangling reference**: when the build names a skill or a tool that
     the run config does not attach, the failures that use that name
     measure the build's breakage, not the lever.
5. **Measure the target eval, and only the guard evals that you have a
   stated reason to fear** (name the reason in the hypothesis). The
   confirmation on val measures every eval: that is where the other guard
   evals are checked. A swap to another model changes every item, so
   measure every eval on train for it.
6. Give the verdict:
   - **Candidate**: the target eval improved on train and no eval is
     clearly worse. Size matters, not only the count: two evals up a
     little while one collapses is not a candidate. A gain with low
     significance can be a candidate, with the caution said: the
     confirmation on val is the real test. When the target eval has no
     results, or too few to read, it is a candidate only with direct
     evidence that you cite (the traces you read) and a re-measure as the
     next step: never on absent numbers alone.
   - **At the ceiling**: when the baseline leaves room for only one or two
     items, a significant result is impossible. A candidate that passes
     every target item, breaks none, and fixes items the baseline always
     fails, with a mechanism you traced, is a candidate; say the caution.
   - **Refuted**: clearly past the noise, the change did not help, or it
     broke an eval. A null with enough items and a narrow interval around
     zero is a real "did not work".
   - **Inconclusive**: inside the noise; not refuted. A wide interval that
     straddles zero is "cannot tell": the eval may be too small. Say
     "enlarge the eval", not "it does not work".
   - **Not applied**: the change did not reach the agent (above).

A missed prediction is a caution, not a verdict. Judge the size of a gain
against the room that the baseline left, not against the prediction.

## Confirm on val

For a candidate only. Run the evals on the **val** split, for the candidate
and for the baseline (`"split": "val"`), and read the result by metrics
only: the summary numbers that `references/knowledge/train_val_test.md`
lists, coverage included, and nothing at item or trace level. Of a job's
errors on val, read only the coverage and the classes of error, never the
errors item by item: they name val items one by one.

Missing val results are missing evidence, not zeros. When the target eval
has none on val, the candidate is not kept, unless all three hold: its
train evidence on that eval is overwhelming and significant; every guard
eval measured on val holds; and your report says that val is missing and
that the decision rests on train. A guard eval with no val results is
weighed as missing evidence. Never write "no regressions" for an eval that
was not measured. With low coverage on the eval that decides, prefer a
fully measured candidate close behind.

Before you decide, read the project's `OPEN: ` records
(`references/knowledge/memory.md`). When keeping the candidate would
settle, contradict or bet on the default assumed for an open question that
the user has not answered, ask the user first. Until the answer, keep no
winner and do not call the candidate rejected: it waits unchanged. Then
decide on the user's answer and the numbers.

**The integrity checks**, before the keep rule:

- A candidate whose prompt quotes a judge prompt, a spec or an eval
  description word for word, or names an eval, is blocked: it cannot win.
- These are signs to weigh, not verdicts: the median output length moved
  more than 2× either way; the top-level keys of a JSON output changed; a
  kind of write action appears that the baseline never took; an
  instruction paraphrases a judge's criterion. A real fix can do each of
  these; so can a candidate that games a judge. Check the length, the keys
  and the writes on train outputs.
- A kept candidate with a sign gets one line per sign in your report,
  starting `Integrity:`, that answers it.

Then apply the keep rule:

- **The headline**: for each eval, compare the candidate's mean score on
  val with the baseline's, from the val summary numbers
  (`references/knowledge/train_val_test.md` says which call reads which
  split). The headline is how many of the evals the candidate is ahead on,
  and the target eval must be one of them. Kiln Harness Tuner's mean win
  rate (the share of paired val items won, averaged across evals) is the
  loop's stronger version; an agent here reads summary numbers, never val
  items.
- **No eval is clearly worse.** Only a significant change counts as a
  change. A higher-priority eval comes before a lower one: no number of
  small wins on low-priority evals makes up for a drop on a high-priority
  eval.
- **Cost and latency are a separate axis**, never folded into a score.
  When nothing changed significantly, the headline and the position on
  cost and latency decide.
- **When the user's goal is speed or cost**, the candidate must be both:
  - **Clearly faster (cheaper):** a paired sign test of the per-item
    latency (cost) on the same items, a median ratio below 1, and no
    significant regression at p90. Fewer than 2/3 of the planned pairs is
    "incomplete", never a verdict.
  - **Equal or better on quality:** no eval down significantly; the net
    item change, pooled over every eval score, is at least 0, with each
    eval weighted by its priority (p0 = 4, p1 = 3, p2 = 2, p3 = 1, none =
    1); and no single eval down more than max(1, round(0.10 × its items))
    net items. The guard evals matter more here.

  The fastest (cheapest) candidate that meets both wins. A tie on speed
  goes to the higher pooled net, then the better p90.
- **One winner, or none.** None is a valid outcome.

Confirm a candidate once, and keep exactly what was measured. Do not tune
on val: nothing that you see on val goes into a change. When val rejects a
train win, read
[dealing with train wins rejected at validation](references/improving_agents/playbooks/dealing-with-train-wins-rejected-at-val.md).

The user may waive the confirmation on val. Then mark every result of the
work "train only".

## Keep or discard

- **Keep**: the candidate becomes the baseline of the next experiment.
  Tell the user which run config won, and that the `baseline` record,
  which Kiln Harness Tuner writes, is unchanged. Never change the task's
  default run config on your own initiative; tell the user that it can
  become the default, and change it only when the user asks. Tell the
  user whether the target issue looks fixed (a partial win, or a gain
  from elsewhere, does not close it), and name any closed issue whose
  eval got worse on val. Do not change an issue's state
  (`references/knowledge/memory.md`).
- **Discard**: the objects stay, as the history of what was tried. Do not
  archive or delete them.
- **Next**: a refuted or inconclusive step goes back to its playbook; a
  rejection at val goes to
  [dealing with train wins rejected at validation](references/improving_agents/playbooks/dealing-with-train-wins-rejected-at-val.md);
  when the eval itself looks wrong, saturated, near zero or noisy, read the
  eval playbooks of `references/improving_agents/index.md`.

## Record and report

Record what lasts, as you learn it (`references/knowledge/memory.md`): a
`lesson`; a `dead_end` for a refuted approach, with its run config ids; a
new `issue` for a new problem, such as a guard eval that broke. The
outcome of the experiment goes to the user. Never write a val number to
memory.

To the user: the recommendation first; then a table per eval with both
scores, the coverage, the significance and the split of each number; then
the links to each run config, and the Compare page with the note that it
shows test scores. No number of the test split.

- **Source every claim**: each number and each "because" names the call,
  the row or the record it comes from. No composition you inferred
  ("mostly judge cost") and no quantifier without a source ("most",
  "nearly all"). Report the failures, the holes in coverage and the work
  you stopped, as they are.
- **A cost is the recorded usage**, labelled `spend`, quoted with the
  invoiced number as `references/knowledge/experiment_costing.md` says
  ("Recorded cost ≠ invoice"). Never patch a
  missing cost with an estimate: say that it is missing.
- **Speed and cost wording:** a candidate kept on speed or cost has "no
  clear loss" of quality, never "no loss": a few hundred paired items or
  fewer cannot rule out a drop of a few points. A result on the baseline's
  passes is "lost k of n baseline passes (no loss rate above X% at 95%)",
  never "quality held". A swap to another model or provider needs at least
  24 baseline passes judged before it can be kept on speed or cost. A fix
  of a baseline failure there is at the noise level, and it does not make
  up for a loss.

## Variants

- **A comparison of run configs that the user named** ("which model is
  best"): run each on the same train items, compare with the paired
  statistics call, then confirm the best one on val. Ask the user before you
  create 3 or more run configs.
- **Two candidates at once**: each is one change from the same parent.
  When both win, the two changes together are a new candidate, built and
  measured as one, and confirmed on val like any other. Combine them by
  hand; never combine two candidates that were built as alternatives for
  one head-to-head comparison.
- **No eval yet**: an eval comes first (`references/knowledge/create_spec.md`).
- **More than this** (many waves, many ideas, a search over models): the
  Kiln Harness Tuner path of "Two paths" above.
