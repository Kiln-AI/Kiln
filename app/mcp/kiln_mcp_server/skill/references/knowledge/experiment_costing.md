---
name: experiment_costing
description: Estimate the full cost of any Kiln experiment BEFORE running or proposing it — drives, synthetic-user, judging, third-party MCP/infra, provider quotas, and the replicate that gives the result an error bar. Load before any run_comparison / eval sweep / corpus expansion / candidate-config round / suite redesign, and when "how much will this cost", "budget this", "cost breakdown", "price this experiment".
---

# experiment-costing

Never run — or propose — model-spend work without a pre-run cost estimate that
covers ALL six lanes below.

Three error classes this file guards against. Each is easy to commit:

1. **A cost lane nobody priced.** A lane that has no cost line in the proposal
   goes unseen, and a design change can multiply it without anyone noticing.
   Nothing in the tooling asks you for a lane you did not think of; this list
   is the ask.
2. **A variable nobody measured, hidden by a discount nobody priced.** Two
   estimation errors can cancel, so the invoice lands near the estimate by
   chance. Cancellation is luck, not budgeting: price every variable, and
   check each one against a measurement.
3. **A lane assumed to be unmeasurable.** A stale "you cannot measure this"
   licenses an estimate that nothing will ever challenge, and an
   over-estimate can scope an affordable experiment out. **Where a lane is
   called blind, re-check the source before believing it.** No lane in this
   file is blind.

## First principle: cost is a function, never a constant

Every dollar figure is conditional on (target model and provider, tool surface,
turn count, tool-result sizes, judge model, prompt shape, item counts, eval
filters). A number measured under one configuration is INVALID input for
estimating another — and quoting a cached number without its conditions is
itself the error this file exists to prevent. Estimate by plugging freshly
measured variables into the formulas below; never by recalling a prior cycle's
totals. When you measure a value, record it **with its conditions attached** in
the run's own report, and cite that report rather than the bare number.

## The six cost lanes — price every one, every time

1. **Drives (target inference).**
   `$ ≈ Σ_calls (uncached_in × in_$/M + cached_in × cached_$/M + out × out_$/M)`
   **The cached term usually DOMINATES this lane; it does not correct it.** An
   agentic loop re-sends about the whole context on every LLM call, so most
   input tokens are prefix re-reads, and a naive `input × list_$/M` estimate is
   off by the provider's cache discount times that fraction. Cache hit is a
   **provider** property far more than an agent one: the same corpus measures
   very different hit rates on two providers, and prompt revisions move it
   barely at all. Cached billing runs at a fraction of list that differs by an
   order of magnitude between provider families, and cached rates are often
   absent from a model-info lookup — check the provider's own page. Measure two
   variables off a smoke: `cache_hit = cached_tokens / input_tokens`, and calls
   per conversation. Cost is super-linear in turns and precisely linear in LLM
   CALLS: a scenario that elicits a long failure loop costs what that loop's
   calls cost. Any change to an EvalInput's `data.*` or `turns`, or to run-config
   properties, changes the drive fingerprint → **re-drives and re-pays this
   lane**. Three sub-rules:
   - **Never scale across models by list-price ratio.** A model advertised at a
     fraction of another's price can cost *more* per conversation on the same
     corpus, because its reasoning bills as output tokens and its cache
     economics differ. Estimate from a measured $/conversation smoke ON the
     target model, config AND corpus.
   - **Read the smoke's recorded usage before green-lighting the run.** The eval
     result rows carry native per-conversation usage (`task_run_usage`). The token volume is in the smoke
     before the sweep starts. One minute, mandatory.
   - **Budget by scenario class, not mean × N.** Trap and write scenarios run
     several times the median conversation, and the top decile of scenarios can
     be a quarter to a third of a lane's whole spend. A bait corpus pays for
     every failure loop it successfully elicits.
2. **Synthetic user (driver model).** Same formula, the driver model's prices.
   Small next to drives, never free, and usually on a **different provider** from
   the agent — so it is a separate invoice line, not a rounding error on lane 1.
   ✅ **SU usage is MEASURABLE — read it, don't estimate it.**
   `TaskRun.synthetic_user_usage` carries the same fields as `eval_usage` and is
   populated when the record is a **multi-turn synthetic drive** (the only lane
   with an SU) and the runner is new enough to record it — an older server
   records nothing, so check one record before trusting a sum. It is on the
   scored TaskRun, not on the eval row: the per-item rows of
   `GET …/run_config/{rc}/results?split=train` give `eval_run.scored_run_id`,
   and `GET /api/projects/{project_id}/tasks/{task_id}/runs/{run_id}`
   (`references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_runs_run_id.md`)
   gives that run's `synthetic_user_usage`. The row's `task_run_usage` leaves
   it out. For a drive-only eval job, the run ids are in
   `result.driven_runs[].task_run_id`. **`None` is correct, not missing**, on
   a run that no synthetic user drove, and on a migrated legacy trace whose
   driver cost is already inside `usage`. A reused trace is the same TaskRun
   as the drive that made it, and several eval rows can name one `scored_run_id`:
   sum the field once per TaskRun, never once per row, so it never
   double-counts reuse. ⚠️ **No endpoint aggregates it for a split you may
   read.** The run config eval-score summaries add only its **cost** into
   their `mean_usage`, and they read the test split
   (`references/knowledge/train_val_test.md`): do not use them for this. In a
   Kiln Harness Tuner session the project files are not
   readable and `split=train` is the only split the API lets you name. ⚠️ Drives
   from before the field existed have **no separate SU number**: a migrated
   legacy trace has the driver's cost fused into its `usage`, and it cannot be
   split out, because the SU's calls leave nothing in the stored trace. Two
   things that only show up once you measure: SU input scales with the
   **agent's** verbosity, so a chatty agent makes its own driver expensive; and
   the **last SU call of every drive is discarded by the loop** — the
   largest-context call of the conversation, buying nothing.
3. **Judging — the lane you pay AGAIN on every re-score.**
   `$ ≈ Σ_judge_evals (items_in_scope × (trace_tokens + scaffold_tokens)) × judge_in_$/M`
   Judge cost is input, full stop: output is a rounding error on it. Drives are
   paid once per fingerprint; this lane is paid on **every re-score**, which is
   what makes it the dominant *recurring* cost even when it is a minority of a
   fresh sweep.
   ✅ **Judge usage is MEASURABLE — read it, don't estimate it.**
   `EvalRun.eval_usage` (`cost`, `input_tokens`, `output_tokens`,
   `cached_tokens`, `total_llm_latency_ms`) is populated when the eval is an
   **LLM judge** and the runner is new enough to record it. Every non-judge
   adapter returns `None`, correctly — code evals are $0. ⚠️ **No endpoint
   aggregates it**: read it off the per-item rows of
   `GET …/run_config/{rc}/results?split=train`, the same as medians.
   A judge pass is one of the few reliably predictable costs here, because judge
   input is **deterministic** given (trace, rubric): repeated passes over the
   same traces agree to the cent. Price it as
   `Σ_items trace_tokens × judge_in_$/M` and expect to be right. Never quote a
   per-judgment figure without its judge model — judge models of different
   classes differ by multiples on identical traces.
   Compounders: a full-trace judge re-reads the ENTIRE trace per call, and
   **trace size, not rubric size, sets the price**, so `N × mean` under-prices
   whichever judge your bait corpus routes the fattest traces to. Atomic
   per-criterion evals multiply reads of the same trace **only if inputs carry
   several judge tags**; under targeted tagging each trace is read about once.
   Skeptic and audit configs multiply the whole lane. `items_in_scope` differs
   per eval when tag filters are in play, so never multiply by raw corpus size.
   Traces grow with turn count.
4. **Third-party infrastructure (MCP calls, writes).** Live calls to a server
   someone else operates **always need its operator's agreement per batch**,
   whatever the token cost: the load lands on their servers. If a write lane
   exists, price BOTH the calls and the fixture reset they force, and get a
   separate agreement — write authorization is not read authorization. Against
   a local mock the lane is $0: **state it as $0 rather than omitting it**, so
   a reader can see it was considered.
5. **Provider quotas and keys.** Not dollars, but a hard stop: a key at its
   spend limit zeroes every lane routed through it, mid-run. A key can also
   carry its own total limit, separate from the account balance, so a run can
   die with money still on the account. Before any sizable run, confirm headroom
   on each key involved, and know which provider each config ACTUALLY routes
   through — the same model id rides different lanes on different configs.
6. **The replicate — the error bar is a cost lane.** Run-to-run noise costs a
   **full extra sweep**, and without it no "we improved it" claim has a bound.
   A byte-identical clone of one config can flip a share of verdicts, and
   cache-hit drift can move corpus-mean metrics on an identical config. The
   null band scales as roughly `2√d` in the criterion's own discordance count.
   **Any round that intends to claim an improvement budgets one replicate at
   the drive lane's full price**, or says up front that its result carries no
   error bar.
   The judge lane has its own, separately priced noise floor, and it matters
   more than the code lane's: tag-routed judges run at small n, where one flip
   moves a row a long way and adjudication error stacks on run-to-run noise.

## Measuring the variables (at estimate time, not from memory)

- **Model prices**: from a live model-info lookup, never from memory — prices and
  provider routings drift. The lookup is `GET /api/model_info/models`
  (`references/knowledge/api_docs/get_api_model_info_models.md`: input and
  output price per entry, and `sort: "price"`) and
  `GET /api/model_info/model_details`
  (`references/knowledge/api_docs/get_api_model_info_model_details.md`: all
  four prices, cache read and cache write included, per provider entry). The
  prices are in USD per million tokens. A listed price is a **list
  price**: it does not show the cache hit, the reasoning tokens or a
  provider's discount. Each model also has `median_input_price` and
  `median_output_price`: the median price across the providers on
  models.dev. When one provider's price is far from the median, it can be
  a price error, for example a cheap host on OpenRouter that does not show
  the typical price. A $0 price is a free tier with rate limits, not the
  paid price: do not budget a run at $0. A null price means that
  models.dev has no price for that pair, or that Kiln could not fetch
  models.dev (`sources.models_dev.state: "unavailable"`). Then use the median
  price first. With no median, call `GET /api/model_info/model_details`
  (`references/knowledge/api_docs/get_api_model_info_model_details.md`) without
  `provider`: it gives the model's entries on every provider, also on
  providers that are not connected. The price on another provider is a
  **proxy**: often close, but not the price you will pay. Say in your
  estimate which you used: the median or a proxy. A local provider
  (Ollama, Docker Model Runner) has no per-token price. Do not use the
  median or another provider's price as a proxy for it. Use the cost that
  the loop measures. **The price that the loop measures on the task wins**
  over a listed price, over the median and over a proxy.
  Direct-provider lanes are typically cheaper than aggregator lanes for the
  same model.
- **Drive sizes and cache behaviour**: read the recorded usage of each
  conversation off the per-item rows of
  `GET …/run_config/{rc}/results?split=train` (`task_run_usage`:
  `input_tokens`, `output_tokens`, `cached_tokens`, `cache_write_tokens`,
  `cost`, …), counted once
  per `scored_run_id`, because several evals' rows can name the same
  TaskRun; or off the scored TaskRun (`usage`). For one drive's own cost on
  a seeded item, read `usage`, not `cumulative_usage`: `cumulative_usage`
  includes the seeded prior trace. It costs **$0** and yields the whole per-conversation distribution. The
  cheapest instrument in the kit; use it instead of eyeballing traces.
  `cache_hit` is `cached_tokens / input_tokens`; the calls per conversation
  are the model's messages in the trace.
  On a Claude model, `cache_write_tokens` are the input tokens a call wrote to
  the cache at about 1.25× the input price; calls in the next 5 minutes read
  them back as `cached_tokens`. A small corpus is mostly such cold calls, so
  its cost per item overstates a larger run: `mean_cache_write_tokens` next to
  `mean_cached_tokens` in `mean_usage` shows how cold the measured runs were.
- **Judge and synthetic-user sizes**: read `eval_usage` (lane 3) off the
  per-item rows of `GET …/run_config/{rc}/results?split=train`, with the
  drive's `task_run_usage` on the same row, and `synthetic_user_usage`
  (lane 2) off the scored TaskRun that each row names. Never read `.kiln` files
  for this: in a Kiln Harness Tuner session the project tree is read-denied, and only
  the train split may be named.
  Distribution matters: means hide the oversized tail that dominates cost and
  breaks weak judges.
- **Recorded cost ≠ invoice — calibrate per provider.** The correction differs by
  an order of magnitude between lanes. Where the runner's price table has no
  cached-token awareness and the lane runs at a high cache hit, recorded cost can
  overstate the invoice several-fold; where the provider returns a cache-aware
  cost that the runner records verbatim, recorded and invoiced agree to a
  fraction of a percent. The invoice IS computable from lane 1's formula once the
  cached term is real. Quote BOTH numbers in estimates and actuals, and reconcile
  after any sizable run against the provider dashboard or a before/after
  key-usage delta.
- **Item counts per eval**: resolve each eval's filter against the corpus; a
  filtered eval judges fewer items than the corpus size.
- **Prior measured values**: reusable only after checking that the configuration
  they were measured under still holds — and cite that configuration.

## What is FREE (don't over-estimate either)

- Re-scoring stored traces with NEW eval configs (fingerprint trace-reuse): zero
  drives, judge tokens only. Code evals are
  literally $0 — confirmed by unchanged provider key usage across thousands of
  scorings.
- Creating configs, evals and specs: $0 until run. Offline eval validation
  against synthetic fixtures: pennies.
- Cloning a run config: $0 — but the clone **misses the trace-reuse key**, so the
  eval behind it is a full fresh sweep. That is how lane 6 is bought
  deliberately; don't buy it by accident.

## Screening before arms (Kiln Harness Tuner)

A candidate variant that needs no build (a model, provider, thinking level
or sampling change) is cheapest as a code screening round, not an arm. Price
a round as, per candidate: up to 30 judge-free timing drives plus its
drives and judge calls on the round's items (3 per targeted eval in round
1, doubling each round); plus up to 30 baseline timing drives for the
round. The judge lane is usually the larger part: a round of seven
candidates over 8 evals is 168 judge calls. `target_evals` and
`mode: "hard_cases"` shrink it. A candidate a stop rule ends pays only the
chunks it reached (a clearly slower one: its first 15 drives).

An arm goes through the same engine on its whole targeted train split: up
to 30 timing drives for it and the baseline when speed or cost matter (or
the arm swaps the model), then its train items judged in chunks, hard ones first. Price the
full split as the ceiling and expect less: a stop rule ends a failing arm
after its first chunk (the named items, or 8 failures and 4 passes).

Every measured candidate carries a spending cap (`max_usd` with a
`budget_reason`, or code's default; clamped to a share of the remaining run
budget, net of what the candidates already being measured hold). Price it from the planner input's `measurement_prices`. A capped
candidate is inconclusive, not a dead end: its rows are kept and a larger
cap on the same rc goes on from them.

## Rules

1. **Estimate before, actuals after.** Every proposal that spends tokens states
   its per-lane estimate in the proposal itself; every report closes with actuals
   against estimate — recorded AND invoice-reconciled. A post-hoc ledger alone is
   the named failure mode, and so is an actual that lives only in a commit
   message.
2. **Design changes carry cost deltas.** Any suite or architecture change (eval
   splits, extra judge configs, turn-count changes) states its cost multiplier at
   decision time, not in the postmortem. It cuts both ways: a change that cuts
   judge re-reads per trace also cuts any saving that assumed those re-reads.
3. **Human gate.** An estimate above the agreed threshold, or more than a hundred
   judged items, or ANY quota-limit raise → explicit OK from the budget holder,
   first. ANY batch against third-party infrastructure → its operator's
   agreement, first.
4. **Cost levers to consider before scaling** — validate each against the current
   task's own evidence, never assume: cheaper judge models, but gate on a
   measured agreement experiment first, because cheap judges can miss real
   fires and drift from the reference judge; tiered judging where agreement is
   proven; direct-provider routing; provider batch APIs, around half price
   where both the provider and the runner support them.
   ⚠️ **Prompt caching on the judge lane can be worth about zero — measure before
   budgeting a saving for it.** Check `cached_tokens` on the judge rows first:
   if the runner does not set the cache flag, it is zero on every judgment.
   Even with the flag, targeted tagging reads each trace about once, and the
   shared scaffold is a small fraction of a judge call — sometimes below a
   provider's minimum cacheable block. The saving is real for packed or
   universally tagged suites and near zero for targeted-tag ones.

## Related

Kiln Harness Tuner's `kiln-harness-tuner-batch-selection` skill (the planner that
prices a wave with this) · `references/knowledge/api_docs/api_index.md` (the
endpoints behind every measurement above).
