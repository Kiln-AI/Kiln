---
status: draft
---

# Component: Kiln measurement APIs

This document designs the Kiln side of [functional spec](../functional_spec.md) sections 3.1 to 3.5, 3.7 and 3.8, under the fixed decisions of the [architecture](../architecture.md) (decisions 5 to 9, 13, 14, and section 2.1).

**HT** is Kiln Harness Tuner at `b49f159`. `HT/x.py:f` names a function in `harness-tuner/src/kiln_harness_tuner/`. Kiln was read at `325c7cb3`. Marks: **[V]** checked by running code against Kiln's library in this checkout; **[U]** not verified. Everything else was read in the source.

Every number and definition is HT's. A place where Kiln must differ is listed in section 10 and is not decided here.

## 1. Modules and shared parts

### 1.1 Files

| File | Holds |
|---|---|
| `libs/server/kiln_server/statistics_lib.py` | New pure functions for the floors (section 2) |
| `libs/server/kiln_server/statistics_api.py` | The `significance_floor` operation: request fields and `_op_significance_floor` |
| `app/desktop/studio_server/eval_power/__init__.py` | Empty. It must import nothing, so that `eval_api.py` can import `stored_rows` with no cycle |
| `eval_power/train_items.py` | The train helper (section 3) |
| `eval_power/stored_rows.py` | `ScoreSpec`, `comparable_scores`, `rows_by_item`, `score_room`, `select_evals` (1.2) |
| `eval_power/detectability.py` | `eval_detectability(...)` (section 4) |
| `eval_power/noise_sample.py` | `build_noise_plan`, `estimate_from_plan` (section 5) |
| `eval_power/noise_compare.py`, `noise_cleanup.py` | The comparison (6.4); `delete_job_objects`, `sweep_task`, `sweep_all_projects` (6.6, 6.7) |
| `eval_power/api.py` | `connect_eval_power_api(app)`: the two routes of sections 4 and 5 |
| `app/desktop/studio_server/api_models/eval_power_models.py` | Every pydantic model of sections 4 to 6, except the job's params and result |
| `app/desktop/studio_server/jobs/workers/noise_check.py` | `NoiseCheckJobWorker`, `NoiseCheckJobParams`, `NoiseCheckJobResult` |
| `jobs/workers/eval_errors.py` | `safe_str`, `error_detail`, `item_source`: moved from `workers/eval.py` with no change, so both workers use them |
| `jobs/api.py` | The create route `POST /api/jobs/evals/noise_check`, and the worker registration |
| `app/desktop/studio_server/eval_api.py` | The `split` parameter (section 7) and the compare route (section 8) |
| `app/desktop/desktop_server.py` | `connect_eval_power_api(app)` before `connect_webhost`; the app-start sweep in `lifespan` (6.7) |

`noise_compare.py`, `noise_cleanup.py`, `train_items.py` and `stored_rows.py` are additions inside the package that architecture 2.1 names. The `eval_power` modules other than `api.py` are service code: they take loaded models, raise no `HTTPException`, and hold no module-level state. Tests sit beside each module as `test_<module>.py`.

### 1.2 Shared definitions (`eval_power/stored_rows.py`)

- **Score types.** Binary: `pass_fail`, `pass_fail_critical`. Rating: `five_star`. The paired test of a binary score is `mcnemar_paired`. The paired test of a rating score is `compare_paired` (`HT/analysis.py:_stats_row`).
- **Pass line.** A binary value `>= 0.5` is a pass.
- **`ScoreSpec`**: frozen dataclass `key: str` (`EvalOutputScore.json_key()`), `type: TaskOutputRatingType`, `direction: ScoreDirection`.
- **`comparable_scores(eval: Eval) -> tuple[list[ScoreSpec], list[SkippedScore]]`** ports `HT/detectability.py:comparable_specs`. It walks `eval.output_scores` in order. An `informational` score is left out with no entry. A score whose type is not binary or rating gives `SkippedScore(eval_id, score_key, reason="score type '<type>' has no statistics operation")`. On Kiln data today the skipped list is always empty: `EvalOutputScore` refuses a custom type and always has a direction.
- **`rows_by_item(runs: Iterable[EvalRun]) -> dict[ItemKey, ItemRow]`** ports `HT/analysis.py:_runs_by_item`. The item is `eval_run_item_key(run)`. `ItemRow` is a frozen dataclass: `scores: dict[str, float | None]`, `last: EvalRun`, `replicates: int`. One record: its scores. Several records of one item are replicates: each score is the mean of the non-null values, and `last` is the newest record by `created_at`. A binary score is read at the pass line after the mean.
- **`score_room(values, spec) -> int`** ports `HT/detectability.py:score_room`. Binary: an item has room when it is not a pass (a pass has room under `lower_is_better`). Rating: room when `normalize(value) < 1 - 1e-9`, where `normalize` is `(value - 1) / 4` clamped to [0, 1], and `1 -` that under `lower_is_better` (`HT/analysis.py:normalize`).
- **`select_evals(task, eval_ids) -> list[tuple[Eval, EvalConfig]]`** is the eval set of functional spec 3.1. With `eval_ids` absent: every eval of `task.evals(readonly=True)` whose `resolved_status(spec)` is not `archived` (the same test as `run_config_eval_scores`). With `eval_ids`: those evals, in the order given, duplicates dropped. In both cases an eval is kept only when `eval.current_config_id` is set and names an existing config; an eval without one is left out, with no error. The caller checks unknown ids first (404).
- **Stored train rows of an eval:** `rows_by_item(run for run in default_config.runs(readonly=True) if run.task_run_config_id == run_config_id and eval_run_item_key(run) in train.keys)`, where `train` is from section 3.

### 1.3 Errors common to the routes of sections 4, 5, 6 and 8

- **404**: an unknown project, task, run config, eval or judge config. The text is the existing lookup's: `task_from_id`, `task_run_config_from_id` (`Task run config not found. ID: <id>`), `eval_from_id` (`Eval not found. ID: <id>`), `eval_config_from_id`.
- **422**: a bad value, from pydantic, with the field named.
- **503**: a project file was half written. `A project file was not readable. Another process can be writing it. Please try again.` with `Retry-After: 1`, as `run_eval_job` does.
- Each handler does its reads in one sync function, called through `to_thread_retrying_torn_read`.

## 2. `significance_floor` on `POST /api/statistics`

Route and method do not change. The agent policy stays `ALLOW_AGENT`.

### 2.1 Request: additions to `StatisticsRequest`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `operation` | adds the literal `"significance_floor"` | — | |
| `test` | `Literal["mcnemar_paired", "compare_paired"] \| None` | `None` | Required for this operation |
| `confidence` | existing | 0.95 | `alpha = 1.0 - confidence`, as the other operations compute it |
| `n` | existing `int \| None`, `ge=1` | `None` | The paired items. The constraint is not changed (open point 10.1) |
| `room` | `int \| None`, `ge=0` | `None` | Of `n`, the items not at the best value |
| `noise_rate` | `float \| None`, `ge=0`, `le=1` | `None` | The share of items that change between two runs of one config |

The `n` description becomes `[proportion_ci] sample size (> 0). [significance_floor] paired items.` `_STATISTICS_DESCRIPTION` and the module docstring get one line for the operation.

### 2.2 Response (a `dict[str, Any]`, as the four operations)

| Key | Type | Value |
|---|---|---|
| `operation`, `test`, `confidence` | | Echoed |
| `floor` | int | `significance_floor(test, alpha)` |
| `fewest_wins` | int or null | `fewest_significant_wins`; null without `n` or `room` |
| `best_case_change` | float or null | `floor / n` when `n >= floor`; else null |
| `interval_wins` | int or null | `interval_wins(test, n, room, confidence)`; null without `n` or `room` |
| `interval_best_case` | int or null | `interval_best_case(test, n, confidence)`; null without `n` |
| `noise_each_way` | int or null | `noise_changes_each_way(noise_rate, n)`; null without `noise_rate` or `n` |
| `noise_adjusted_wins` | int or null | `noise_adjusted_wins(noise_rate, n, room, alpha)`; null without `noise_rate`, `n` or `room`, or when even `room` wins cannot show |
| `interpretation` | str | `At <pct>% confidence, <test> needs at least <floor> changed items, all one way, to call a difference significant.` With `n` and `room`, it adds ` With <room> of <n> items not at the best value, <fewest_wins> wins are enough in the best case.` or `..., no outcome can be significant.` |

### 2.3 The arithmetic (`statistics_lib.py`)

All functions are pure. `SIGNIFICANCE_FLOOR_SEARCH_LIMIT = 10_000` ports HT's `_MAX_FLOOR`.

| New function | Ports | Calls in Kiln | Rule |
|---|---|---|---|
| `significance_floor(test, alpha) -> int` | `HT/detectability.py:binary_floor`, `rating_floor`, `wilcoxon_all_positive_p` | `mcnemar_exact_p`, `wilcoxon_signed_rank_p` | `mcnemar_paired`: the smallest `k >= 1` with `mcnemar_exact_p(0, k) < alpha`. `compare_paired`: the smallest `k >= 5` with `wilcoxon_signed_rank_p([1.0] * k) < alpha`. Both stop at the search limit |
| `fewest_significant_wins(test, n, room, alpha) -> int \| None` | `detectability.py:fewest_wins` | the above | The floor when `min(room, n) >= floor`, else None |
| `interval_wins(test, n, room, confidence) -> int \| None` | `detectability.py:interval_wins`, `paired_ci_low`, `bootstrap_ci_excludes_zero` | `paired_proportion_diff_ci`, `z_for_confidence` | None when `n <= 0` or `room <= 0`. Else the smallest `k` in `1..min(room, n)` for which: (`mcnemar_paired`) the lower end of `paired_proportion_diff_ci(n - room, 0, k, room - k, z)` is `> 0`; (`compare_paired`) `((n - k) / n) ** n < alpha / 2` |
| `interval_best_case(test, n, confidence) -> int \| None` | `detectability.py:interval_best_case` | the above | The minimum of `interval_wins` over `room = 1..n`. Stop when it reaches 1 |
| `noise_changes_each_way(noise_rate, n) -> int` | `HT/noise.py:noise_adjusted_wins`, first line | — | `math.floor(noise_rate * n / 2.0 + 0.5)` |
| `noise_adjusted_wins(noise_rate, n, room, alpha) -> int \| None` | `noise.py:noise_adjusted_wins`, `binomial_two_sided_p` | `mcnemar_exact_p` | With `h = noise_changes_each_way`: the smallest `w` in `1..room` with `mcnemar_exact_p(h, w + h) < alpha`. None when no `w` does. It does not depend on `test`: HT reads every change as a sign |

- **The bootstrap rule is the closed form on purpose** (decision 8). `interval_wins` for `compare_paired` does not call `paired_bootstrap_diff_ci`. A comment at the rule says: the closed form is HT's definition; the seeded draw can answer either way at the edge; do not replace it. A test pins it.
- The functions that HT copied (`_wilson`, `paired_ci_low`, `_z`, `binomial_two_sided_p`, `wilcoxon_all_positive_p`) are not ported. Kiln's own functions give the same values [V].
- `z` comes from `z_for_confidence` (Acklam), not HT's `NormalDist`. The two differ by 1.6e-9. Every pinned value below is the same with Kiln's `z` [V].
- Cost: `interval_best_case` is about 0.2 s at `n = 10,000` [V]. The existing `compare_paired` costs more at that size. No limit on `n` is added.

### 2.4 Handler and errors

`_op_significance_floor(req)` in `statistics_api.py`, added to `_OPERATIONS`.

All errors are 422:

- `test` absent: `'test' is required for significance_floor.`
- `room > n`: `room must not be greater than n (got room=<room>, n=<n>).`
- A negative `room` or `noise_rate`, `noise_rate > 1`, an unknown `test`, and `n < 1` (the existing `ge=1`, open point 10.1): pydantic's own text.

### 2.5 Tests

`test_statistics_lib.py` (each test names the HT test in a comment):

| Pinned value | HT test (`tests/test_detectability.py` unless noted) |
|---|---|
| `significance_floor("mcnemar_paired", a)` is 6, 8, 5 for `a` = 0.05, 0.01, 0.1 | `test_the_floor_is_computed_from_alpha` |
| `wilcoxon_signed_rank_p([1.0] * k)`: None at 4; 0.059058229 at 5; 0.036031686 at 6 (`abs=1e-8`) | same |
| `significance_floor("compare_paired", 0.05) == 6`; at 0.01 it is above the binary floor (9 against 8 [V]) | same |
| `fewest_significant_wins("mcnemar_paired", 40, 5, 0.1) == 5`; None at 0.05 | `test_the_default_floor_follows_the_significance_alpha` |
| binary `(30, 5)` None; `(30, 6)` 6; `(30, 30)` 6; rating `(5, 5)` None; binary `(0, 0)` None | `test_fewest_wins_needs_the_room_to_reach_the_floor` |
| `paired_proportion_diff_ci(...)[1]` with `z_for_confidence(0.95)`: `(5,0,3,2)` 0.0335; `(5,0,2,3)` -0.0493; `(15,0,5,0)` 0.0313; `(15,0,4,1)` -0.0171; `(0,0,1,0)` 1.0; `(50,2,6,2)` -0.0415 | `test_the_interval_route_is_the_servers_arithmetic` |
| `interval_wins("mcnemar_paired", 10, 5) == 3`; `(1, 1) == 1`; `interval_wins("compare_paired", 20, 10) == 4`; the closed form is false at `(20, 3)` and true at `(20, 4)` | same |
| `mcnemar_exact_p(6, 0) == 0.03125`; `noise_adjusted_wins(0.0, 40, 40, 0.05) == 6`; at 0.2 the result `w` is above 6 (9 [V]), `mcnemar_exact_p(w + 4, 4) < 0.05`, `mcnemar_exact_p(w + 3, 4) >= 0.05`, and with `room = w - 1` the result is None | `tests/test_noise.py::test_the_noise_adjusted_bar` |

Also: a test named `test_bootstrap_rule_is_the_closed_form_not_the_seeded_draw`, which patches `paired_bootstrap_diff_ci` to raise and checks that `interval_wins("compare_paired", 20, 10, 0.95)` is still 4.

`test_statistics_api.py`: the six output keys for a full request (`test=mcnemar_paired, n=30, room=6, noise_rate=0.1`); every optional output null when only `test` is given, with `floor == 6`; each row of 2.4; `interpretation` is one sentence or two; `test_openapi_exposes_operation_enum_and_agent_allow` lists five operations.

## 3. The train helper (decision 7)

`eval_power/train_items.py`. One helper, used by the detectability read, the estimate and the job.

```
@dataclass(frozen=True)
class TrainItems:
    split: ResolvedSplit          # the eval's whole train split, for EvalRunner
    keys: frozenset[ItemKey]      # the train items that are held out nowhere
    left_out: frozenset[ItemKey]  # the train items that are val or test in some eval

class TrainSplits:
    def __init__(self, task: Task) -> None
    def train_items(self, eval: Eval) -> TrainItems | None   # None: the eval has no train split
    def val_size(self, eval: Eval) -> int | None             # None: the eval has no val split
```

- **Split resolution is Kiln's.** Every item set comes from `kiln_ai.datamodel.eval_splits.resolve_split(task, eval, name)`. Items are `ItemKey` pairs `(source, id)`, never a bare id.
- **Held-out set.** The constructor takes the union of the `val` and `test` split keys of every eval of `task.evals(readonly=True)`. Archived evals count: "any eval of the task".
- **`train_items`**: `keys = split.item_keys() - held_out`, `left_out = split.item_keys() & held_out`. `split` is the full resolved split with this eval's `eval_id`, because `EvalRunner` refuses a split of another eval.
- **`left_out_held_out`** in a response is `len` of the union of `left_out` over the evals that the call read.
- **Cost.** `resolve_split` reads one whole store (`task.runs()` or `task.eval_inputs()`). The instance keeps a dict keyed `(split_ref.source, split_ref.filter_id)`, so each distinct filter is resolved once, and a hit is re-stamped with `dataclasses.replace(cached, name=..., eval_id=...)`, as `eval_api._cached_test_split` does. One instance lives for one request or one job run. It is never stored at module level.
- **Tests.** An item that is train in eval A and val in eval B is not in A's `keys` and is in `left_out`. The same for test in A itself, and for a val split of an archived eval. A `TaskRun` and an `EvalInput` with the same id do not collide. An eval with no train split gives None. Two evals with the same train filter resolve it once (count the calls to `resolve_split`). The returned `split.eval_id` is the eval asked for. `val_size` is the key count, and None with no val split.

## 4. Detectability read

`GET /api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}/eval_detectability`, in `eval_power/api.py`. Tag `Run Configs`. Free. It writes nothing.

### 4.1 Query parameters

`eval_ids: list[str] | None = None` (repeat the key; `None` is the set of 1.2), `confidence: float = 0.95` (`gt=0`, `lt=1`), `include_val_size: bool = False`.

### 4.2 Response models

`EvalDetectability`: `rows: list[EvalDetectabilityRow]` (in eval order, then score order), `skipped: list[SkippedScore]` (`eval_id: str`, `score_key: str`, `reason: str`), `unread_eval_ids: list[str]`, `left_out_held_out: int`.

`EvalDetectabilityRow`:

| Field | Type | Definition |
|---|---|---|
| `eval_id`, `eval_name`, `eval_config_id` | `str` | `eval_config_id` is the default judge config that was read |
| `score_key`, `score_type`, `direction` | `str` | From the `ScoreSpec` |
| `n` | `int` | Train items with a non-null value for the score |
| `room` | `int` | `score_room` of those values |
| `unscored` | `int` | `max(len(train.keys) - n, 0)` |
| `floor` | `int` | `significance_floor(test, 1 - confidence)` |
| `fewest_wins` | `int \| None` | `fewest_significant_wins(test, n, room, alpha)` |
| `best_case_change` | `float \| None` | `floor / n` when `n >= floor` |
| `interval_wins` | `int \| None` | `interval_wins(test, n, room, confidence)` |
| `val` | `EvalDetectabilityVal \| None` | Null without `include_val_size` |

`EvalDetectabilityVal`: `n: int | None` (`TrainSplits.val_size`), `room_estimate: int | None` (`round(val_n * room / n)` when `val_n` is not null and `n > 0`), `best_case_change: float | None` (`floor / val_n` when `val_n >= floor`). It reads the size of the val split only.

### 4.3 Algorithm: `detectability.eval_detectability(task, run_config_id, evals, splits, confidence, include_val_size)`

Ports `HT/detectability.py:train_detectability`, `train_row` and the val half of `build_rows`.

1. The handler loads the task and the run config (404), checks each id of `eval_ids` with `eval_from_id` (404), calls `select_evals`, and builds one `TrainSplits(task)`.
2. For each eval: `comparable_scores`. Add its skipped entries. With no comparable score, go to the next eval.
3. `train = splits.train_items(eval)`. None, or a read that raises `ValueError` or `OSError` (but not `json.JSONDecodeError`, which the torn-read helper must see): add the id to `unread_eval_ids` and go on.
4. Read the stored train rows (1.2). For each spec, build the row of 4.2. An eval with no stored row gives rows with `n = 0`.

Step 3 is HT's rule: a failed read drops that eval, never the call.

### 4.4 Tests (`eval_power/test_detectability.py`, `test_api.py`)

- `score_room`: `[1,1,0,0,0]` pass_fail → 3 (2 under `lower_is_better`); `[1,0,-1]` pass_fail_critical → 2; `[5,5,4,1]` five_star → 2; `[1,2,5]` five_star `lower_is_better` → 2 (`test_room_is_the_items_not_at_the_best_value`). The `lower_is_better` cases use a hand-built `ScoreSpec`.
- An informational score gives no row and no skipped entry; a score built with `model_construct` and a custom type gives the skipped reason text (`test_informational_scores_never_count`).
- Replicates of one item fold by the mean; `1, 0, 1` is a pass.
- A row on a held-out item is not counted in `n`, and `left_out_held_out` counts the item. No val or test result is read: a test makes every `EvalRun` of a val item raise on access to `scores`.
- `n = 0` rows for an eval with no stored row; an eval with no default judge config is absent; an eval with no train split is in `unread_eval_ids`; an unknown eval id is 404.
- `val` is absent without the flag. With it: the size, `round(val_n * room / n)`, and `floor / val_n`.
- A second call returns the same body, and the project folder has no changed file.

## 5. Noise-check estimate

`POST /api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}/noise_check_estimate`, in `eval_power/api.py`. Tag `Run Configs`. Free. It writes nothing.

### 5.1 Models

`NoiseCheckRequest`: `items_per_eval: int` (required, `ge=1`), `eval_ids: list[str] | None = None`, `confidence: float = 0.95` (`gt=0`, `lt=1`).

`NoiseCheckEstimate`:

| Field | Type | Definition |
|---|---|---|
| `estimate_usd` | `float` | The total of 5.3 |
| `drive_usd_per_item` | `float` | The median drive cost; 0.0 when no row has one |
| `judge_usd_per_item` | `float` | The median over evals of each eval's median judge cost |
| `distinct_items` | `int` | Distinct `ItemKey`s over all samples |
| `evals` | `list[NoiseCheckEvalSample]` | `eval_id`, `eval_name`, `eval_config_id`, `item_ids: list[str]` (in sample order), `rejudge: bool`, `rejudge_note: str \| None` |
| `rows_without_drive_cost`, `rows_without_judge_cost` | `int` | Stored rows of the sampled evals with no recorded cost. Each counts as zero |
| `left_out_held_out` | `int` | Section 3 |
| `skipped` | `str \| None` | `no stored baseline train row to compare with` when no eval has a sample |

### 5.2 The sampling rule: `noise_sample.build_noise_plan(task, run_config_id, evals, splits, items_per_eval) -> NoisePlan`

Ports `HT/noise.py:_sample`, `sample_items` and `judge_copy_note`. `NoisePlan` is a dataclass: the list of `EvalSample` (`eval`, `default_config`, `specs`, `train: TrainItems`, `baseline: dict[ItemKey, ItemRow]`, `items: list[ItemKey]`, `train_values: dict[str, list[float]]`, `rejudge: bool`, `rejudge_note: str | None`).

1. For each eval of `select_evals`, in order: `comparable_scores`. No comparable score: the eval has no sample.
2. `baseline` = the stored train rows (1.2), on the default judge config.
3. **Covered items**: the items whose folded row has a non-null value for every comparable score.
4. **The sample**: `sorted(covered, key=lambda k: hashlib.sha256(k[1].encode()).hexdigest())[:items_per_eval]`. There is no seed and no random draw. The order is the hash of the item id, so every call returns the same items.
5. An empty sample: the eval is left out.
6. **Items shared between evals.** Each eval is sampled alone, by the same order, so two evals over the same items take the same items. A shared item is one distinct item: it is driven once and costed once.
7. `train_values[key]` = every non-null folded value of the score over the whole train set of section 3, not only the sample.
8. **Is the judge checked again?** The default config's properties are `CodeEvalProperties`: no, `a code eval is deterministic: no judge noise`. Else `config_type == EvalConfigType.v2`: yes. Else: no, `a legacy judge config (<config_type>) drives inside its own job, so a copy would re-drive: judge noise alone cannot be measured`.

### 5.3 The estimate: `noise_sample.estimate_from_plan(plan, task) -> NoiseCheckEstimate`

Ports `HT/noise.py:estimate_usd`.

- **Drive cost of a stored row.** With a `scored_run_id`: `usage.cost` of that `TaskRun`, loaded in one `TaskRun.from_ids_and_parent_path(ids, task.path, readonly=True)` call (skipped when there is no id). Without one: `eval_run.task_run_usage.cost`. This is what the results route serves as `task_run_usage`, which HT reads.
- `drive` = the median of the non-null drive costs over all folded rows of the sampled evals; 0.0 with none.
- `judge_e` = the median over an eval's folded rows of `eval_usage.cost`, with a missing cost as 0.0; 0.0 with no row.
- `estimate_usd = distinct_items * drive + sum(passes_e * len(items_e) * judge_e)`, with `passes_e` 2 when the judge is checked again, else 1.

Errors: 1.3, and 422 for `items_per_eval < 1`.

### 5.4 Tests (`test_noise_sample.py`, `test_api.py`)

- 6 rows at a drive cost of 0.01 and a judge cost of 0.002, V2 judge, `items_per_eval=6`: `estimate_usd == 6 * 0.01 + 2 * 6 * 0.002` (`tests/test_noise.py::test_the_estimate_is_printed_before_any_spend_and_the_spend_is_booked`).
- `items_per_eval=3` of 6 covered items: 3 ids, all of the 6, and the same list on a second call (`test_the_sample_is_n_train_items_by_a_fixed_hash`). One more test pins the order against `hashlib.sha256` on fixed ids.
- No stored row: `skipped` is the text, `estimate_usd == 0`, `evals == []` (`test_no_stored_rows_means_no_spend`).
- A legacy config and a code eval give `rejudge == False` with the two notes, and one judge pass in the estimate (`test_judge_noise_is_skipped_where_a_copy_cannot_measure_it`).
- An item with a null value for one of two comparable scores is not covered. A held-out item is never sampled. Two evals over the same items give `distinct_items == items_per_eval`. Rows with no cost raise the two counts.

## 6. Noise-check job

### 6.1 Worker, models, registration

`NoiseCheckJobWorker(JobWorker[NoiseCheckJobParams, NoiseCheckJobResult])` in `jobs/workers/noise_check.py`.

- `type_name = "eval_noise_check"`; `create_path = "/api/jobs/evals/noise_check"`, so `POST /api/jobs/{type}` refuses the type; `supports_pause = False`.
- `dedupe_key`, `describe` and `compute_state` are not overridden: no dedupe, no properties, and the registry keeps the progress that the job reports.
- `NoiseCheckJobParams(NoiseCheckRequest)` adds `project_id: str`, `task_id: str`, `run_config_id: str` (required), `max_usd: float | None = None` (`ge=0`), and `concurrency: int | None = None` (`ge=1`, `le=JOB_MAX_CONCURRENCY`; `None` is `DEFAULT_EVAL_CONCURRENCY`).

`NoiseCheckJobResult`:

| Field | Type | Definition |
|---|---|---|
| `estimate_usd` | `float` | Computed when the job starts (5.3) |
| `spend_usd` | `float` | 6.5 |
| `rows` | `list[NoiseRow]` | One per eval score, 6.4 |
| `warnings` | `list[str]` | 6.4, and one line for each object that the clean-up could not delete |
| `skipped` | `str \| None` | The whole check did not run, and why |
| `errors` | `list[NoiseCheckPassError]` | `eval_id: str`, `noise_pass: Literal["redrive", "rejudge"]`, `item_id: str \| None`, `message: str` (the provider's text, whole) |
| `flip_rate` | `float \| None` | 6.4 |
| `left_out_held_out` | `int` | Section 3 |

`NoiseRow` keeps HT's field names (`HT/schemas.py:NoiseRow`): `eval_id`, `eval_name`, `score_key`, `score_type`, `items: int`, `redrive_changed: int`, `redrive_rate: float | None`, `redrive_mean_abs_change: float | None`, `rejudge_items: int`, `rejudge_changed: int | None`, `rejudge_rate: float | None`, `rejudge_mean_abs_change: float | None`, `rejudge_note: str`, `noise_adjusted_wins: int | None`, `train_room: int | None`. HT's `baseline_rc_id` and `clone_rc_id` are not served: the run config is in the params, and the copy does not exist when the job ends.

**Create route**, in `jobs/api.py`, placed beside `POST /api/jobs/evals/run` and before `POST /api/jobs/{type}`:

```
POST /api/jobs/evals/noise_check   -> 201 CreateJobResponse
async def run_noise_check_job(params: NoiseCheckJobParams) -> CreateJobResponse
```

It checks the task, the run config and each id of `eval_ids` (404; 503 on a half-written file), then calls `job_registry.create(type_name="eval_noise_check", params=params, project_id=params.project_id)`. `connect_jobs_api` adds `job_registry.register_type(NoiseCheckJobWorker)`. The docstring says that the job costs money, that the estimate route is free, and what `max_usd` does. Progress, the result, the error log, wait and cancel are the existing job routes, unchanged.

### 6.2 The sequence of `run(params, ctx)`

**The core eval runner is not changed.** The job builds `EvalRunner` objects itself, as `EvalJobWorker._build_eval_runner` does, with constructor parameters that exist today: `eval_configs`, `run_configs`, `eval_run_type="task_run_eval"`, `split`, `save_context`, `item_ids`, `judge=True`, `trace_index_registry`. It starts no child job: a child would need a second job slot while the parent holds one. Runners run one after the other.

1. `save_context = save_context_for_project(project_id, context=f"noise check job {ctx.job_id}") or default_save_context`, on the event loop. Load the task, the run config and the evals in a thread. A missing one fails the job: this is the only way it fails.
2. Sweep the task (6.7). A failure is logged and does not stop the job.
3. `plan = build_noise_plan(...)`. No sample: return with `skipped = "no stored baseline train row to compare with"`.
4. `estimate_from_plan`. With `max_usd` set and `estimate_usd > max_usd`: return with `skipped = f"the estimate ${estimate_usd:.2f} is above max_usd ${max_usd:.2f}"`. No object is made and no model is called.
5. Open `try`. **Temporary run config**: inside `save_context`, `TaskRunConfig(parent=task, name=f"NOISE-CHECK {ctx.job_id}", description=f"Temporary copy of run config {run_config_id}, made by noise check job {ctx.job_id}. Kiln deletes it when the job ends.", run_config_properties=measured.run_config_properties.model_copy(deep=True), prompt=None, provenance=None)`, then `save_to_file()`. The id is recorded before the save. The properties are copied as they are, so a frozen prompt id still names the measured run config's prompt (`HT/noise.py:_create_clone`). If the save raises: `skipped = f"the temporary run config could not be made ({exc})"[:300]`, and go to the clean-up.
6. **Second drive.** One `TraceIndexRegistry()` is made for this run and given to every runner, so a V2 drive of an item is shared by the evals that sample it. For each sample: `EvalRunner(eval_configs=[default_config], run_configs=[temp_rc], eval_run_type="task_run_eval", split=train.split, save_context=save_context, item_ids={id of each sampled key}, judge=True, trace_index_registry=registry)`, built in a thread; then `validate_multi_turn_drive_readiness()` and `validate_openenv_readiness()`; then iterate `runner.run(concurrency=params.concurrency, observers=[observer], max_retries=JOB_TRANSIENT_ERROR_MAX_RETRIES, retry_delay=JOB_TRANSIENT_ERROR_RETRY_DELAY_SECONDS)`. The temporary run config has no stored row, so every item is driven and judged. A legacy judge config drives inside its own job, as today.
7. **Second judgment.** For each sample with `rejudge`: inside `save_context`, `EvalConfig(parent=eval, name=f"NOISE-CHECK {ctx.job_id}", config_type=default.config_type, properties=<deep copy of default.properties>, model_name=default.model_name, model_provider=default.model_provider, provenance=None)`, id recorded, then `save_to_file()`. `eval.current_config_id` is not touched. Then a runner as in step 6 with `eval_configs=[copy]` and `run_configs=[measured]`. The trace index is keyed by item and run config, so the copy scores the stored trace and drives nothing.
8. Read the new rows from disk: `rows_by_item` of the default config's runs with `task_run_config_id == temp_rc.id`, and of the copy's runs. Build rows and warnings (6.4) and the spend (6.5).
9. `finally`: the clean-up (6.6). Then return the result.

**Errors.** `_NoiseErrorObserver(AsyncJobRunnerObserver[EvalJob])` gets each final item failure. It appends a `NoiseCheckPassError` with `error_detail(error)` (the provider's own text, from `KilnRunError.original`) and calls `ctx.report_error(message, eval_id=..., noise_pass=..., dataset_id=job.item.id, item_source=item_source(job.item))`, so `GET /api/jobs/{id}/errors` shows it. A runner that cannot be built or validated (`ValueError`), and a copy that cannot be saved, give one entry with `item_id=None`; the job goes on with the next eval.

**Progress.** `total = sum(len(items_e) * passes_e)`. After each runner event: `ctx.report_progress(success=<done before> + progress.complete, error=<errors before> + progress.errors, total=total, message="second drive: eval 2 of 5")` (or `second judgment: ...`).

### 6.3 `max_usd` and `concurrency`

- `max_usd` is checked once, against the estimate, before any object is made (step 4). It does not stop a job that costs more than its estimate.
- `concurrency` is the number of items one runner works in parallel, as in the eval job. Runners are serial, so it is also the job's total. The job takes one slot of the job registry (`KILN_JOBS_MAX_CONCURRENT`).

### 6.4 The comparison (`eval_power/noise_compare.py`)

| Function | Ports | Rule |
|---|---|---|
| `changes(spec, before, after, items) -> (compared, changed, mean_abs)` | `HT/noise.py:changes` | Over the sampled items where both rows have a value. Binary: changed when `(a >= 0.5) != (b >= 0.5)`; `mean_abs` None. Rating: changed when `abs(b - a) > 1e-9`; `mean_abs` is the mean of `abs(b - a)` |
| `same_outputs(baseline, copied) -> bool` | `noise.py:same_outputs` | False with no copied row. For each copied row: the baseline row exists; when both name a `scored_run_id`, they are equal; else both `EvalRun.output` values are equal and not None |
| `noise_rows(sample, redrive, rejudge, note, confidence) -> list[NoiseRow]` | the loop at the end of `noise.py:run_noise_check` | Below |
| `noise_warnings(row, test, n, confidence) -> list[str]` | `noise.py:_warnings` | Below |
| `flip_rate(rows) -> float \| None` | `HT/stop_rules.py:noise_flip_rate`, no eval filter | Over the binary rows: `sum(redrive_changed) / sum(items)`; None when the sum of `items` is 0 |

**`same_outputs` is checked for every eval that was judged again.** When it is false, the copied rows are not used and the note is `the copy judged other outputs than the stored ones (the server drove again), so judge noise alone is not separable here`.

**A row**, per spec of a sample, with `values = train_values[key]` and `alpha = 1 - confidence`:

- `items, redrive_changed, redrive_mean_abs_change = changes(spec, baseline, redrive, items)`; `redrive_rate = changed / items`, or None when `items == 0`.
- `rejudge_items` from `changes(spec, baseline, rejudge, items)`. When it is 0: `rejudge_changed`, `rejudge_rate` and `rejudge_mean_abs_change` are None, and `rejudge_note` is the reason: the note of 5.2, or the `same_outputs` text, or `f"the re-judge failed ({message})"[:200]`, or `no re-judged row`. Else the note is `""`.
- `train_room = score_room(values, spec)`.
- `noise_adjusted_wins = statistics_lib.noise_adjusted_wins(redrive_rate, len(values), train_room, alpha)`, or None with no rate.

**Warnings.** None unless `redrive_changed > 0` and `train_room > 0`. With `n = len(values)`, `best = fewest_significant_wins(test, n, train_room, alpha)` and `each_way = noise_changes_each_way(redrive_rate, n)`:

```
head = f"{eval_id}/{score_key}: {redrive_rate:.0%} of items change between two runs of the same config — about {each_way} change(s) each way on the {n}-item train split"
noise_adjusted_wins is None      -> f"{head}; even fixing all {train_room} item(s) with room is not enough to show a win through that noise"
best is None or wins > best      -> f"{head}; a win on it needs about {noise_adjusted_wins} wins, more than the best-case {best if best is not None else '—'} ({train_room} item(s) have room)"
```

### 6.5 Spend

`spend_usd` is the cost that the job's own records carry, each record once:

- every `TaskRun` whose `output.source.run_config_id` is the temporary run config: `usage.cost` plus `synthetic_user_usage.cost`;
- every `EvalRun` of the temporary run config under a default judge config: `eval_usage.cost`; for a legacy config, which stores no task run, also `task_run_usage.cost`;
- every `EvalRun` of a judge copy: `eval_usage.cost`;
- every task run that 6.6 step 3 removes: as the first bullet.

A missing cost counts as 0. A drive shared by two evals is one `TaskRun`, so it is counted once. A model call that failed left no record, so `spend_usd` is a lower bound when `errors` is not empty. The sum is taken before the clean-up, from the same lists that the clean-up deletes. See open point 10.7.

### 6.6 Clean-up: `noise_cleanup.delete_job_objects(task, temp_rc_ids, judge_copies)`

It runs in the `finally` of step 9, on success, failure and cancel. It deletes only objects of this job, found by the ids that the job recorded. It reads fresh from disk.

All deletes run in one `async with save_context():` block, in one worker thread. Each delete is `KilnBaseModel.delete()` on an instance loaded for the delete (not a read-only cached one). `delete()` removes the object's folder and clears its cache entry.

| Step | What | How it is found |
|---|---|---|
| 1 | The eval runs of the temporary run config | Every `EvalRun` with `task_run_config_id == temp_rc_id`, over every config of every eval of the task |
| 2 | The task runs of the second drive | Every run of `task.runs(readonly=True, include_intermediate_runs=True, include_eval_generated=True)` with `output.source.run_config_id == temp_rc_id` |
| 3 | A task run that a second judgment drove (rare) | For each judge copy: a `scored_run_id` of the copy's runs that no baseline row names, whose `TaskRun.created_at >= copy.created_at`, and that no `EvalRun` outside `NOISE-CHECK` configs names (open point 10.5) |
| 4 | Each judge copy | `EvalConfig.from_id_and_parent_path(copy_id, eval.path)`. Its folder holds its eval runs, so they go with it |
| 5 | The temporary run config | `TaskRunConfig.from_id_and_parent_path(temp_rc_id, task.path)`. Only when steps 1 and 2 had no failure |

- **Why this order.** The temporary run config is deleted last because its id is the only way to find the objects of steps 1 and 2. If the app dies in the middle, what is left still has a `NOISE-CHECK` object that the sweep finds.
- **When one delete fails.** The exception is caught inside the block, logged with `logger.exception`, written with `ctx.report_error(..., cleanup=True)`, and added to `warnings` as `clean-up could not delete <kind> <id>: <error>`. The other deletes go on. The job does not fail. The object stays for the sweep. No exception leaves the block, because `GitSyncManager.atomic_write` rolls back every write of the block on an exception.
- **When the block itself fails** (the write lock, or the push): the roll-back restores the deleted files. The failure is logged and reported in the same way, and the sweep does the work later.
- **Git sync.** With auto sync, each save of the job is a commit and a push, as for an eval job, so other clones see the temporary objects while the job runs. The clean-up is one more commit, with the context `noise check job <id>`. The objects stay in the git history.
- A second call to `Task.runs(include_eval_generated=True)` outside the eval runner is deliberate here: the clean-up must see eval traces.

### 6.7 The sweep of left-overs

A left-over is a `TaskRunConfig` or an `EvalConfig` whose name starts with `NOISE-CHECK ` and that no live job owns.

- **Ownership.** The name is `NOISE-CHECK <job id>`. The owner id is the text after the prefix, up to the next space. The object is owned when the job registry holds a job of type `eval_noise_check` with that id whose status is not terminal: `{j.id for j in job_registry.list_jobs(type_name="eval_noise_check") if not j.status.is_terminal}`. The job's own id is in that set while it runs, so a job never sweeps itself, and two jobs on one task do not touch each other. A name with no id that matches is not owned.
- **`sweep_task(task, live_job_ids) -> int`** lists `task.run_configs(readonly=True)` and each eval's `configs(readonly=True)`. With no left-over it reads nothing else. Else it calls `delete_job_objects` with the left-over ids, under the same rules as 6.6.
- **When.** (a) Step 2 of every noise job, for the job's task. (b) App start: `desktop_server.lifespan` starts `asyncio.create_task(sweep_all_projects(...))` after `_start_background_syncs()`, keeps the task on `app.state`, and cancels and awaits it at shutdown. `sweep_all_projects` loads each path of `Config.shared().projects`, and for each task calls `sweep_task` in a thread, inside `save_context_for_project(project.id, context="noise check sweep")`. A project or task that does not load is skipped. An error is logged and never stops the start. At app start the registry is empty, so every prefixed object is a left-over. See open points 10.3 and 10.4.

### 6.8 Cancel

`POST /api/jobs/{id}/cancel` cancels the supervising task. The loop body of steps 6 and 7 has no suspension point of its own (`ctx.report_progress` does not suspend), so the `CancelledError` arrives inside `runner.run()`. `AsyncJobRunner.run` then cancels and awaits its item workers in its own `finally`, before the exception reaches the job. So no item is still writing when the clean-up starts [U]. The runner is also wrapped in `contextlib.aclosing`.

The clean-up is protected from a second cancel: it runs as a task that the `finally` awaits through `asyncio.shield`, in a loop that goes on until the task is done. The cancel request returns after the clean-up, because the registry awaits the task. The job ends as `cancelled`, with no result. The error log keeps what was reported.

### 6.9 Tests (`jobs/workers/test_noise_check.py`, `eval_power/test_noise_compare.py`, `test_noise_cleanup.py`)

All with fake model adapters and a real project in `tmp_path`. Six train items with scores `[0, 0, 1, 1, 1, 1]`.

| Case | Pinned from `HT tests/test_noise.py` |
|---|---|
| Second drive gives `[1, 0, 1, 0, 1, 1]`: `items == 6`, `redrive_changed == 2`, `redrive_rate == 1/3`, `rejudge_items == 6`, `rejudge_changed == 0`. The measured run config file and its eval runs are byte-identical after the job, and `current_config_id` is unchanged | `test_the_redrive_is_a_clone_and_the_baseline_is_never_touched` |
| The judge copy has the default's `config_type`, properties and model, and a name with the prefix; one flipped judgment gives `rejudge_changed == 1`, `rejudge_rate == 1/6`, `redrive_changed == 0` | `test_the_judge_copy_is_a_non_default_copy_of_the_default_config` |
| Copy rows that name other task runs: `rejudge_changed is None`, and `not separable` is in the note | `test_a_copy_that_drove_again_is_not_judge_noise` |
| Legacy config, code eval: no copy is made, the notes hold `legacy judge config` and `deterministic`, `items == 6` | `test_judge_noise_is_skipped_where_a_copy_cannot_measure_it` |
| `spend_usd == 6 * 0.01 + 6 * 0.002 + 6 * 0.002` | `test_the_estimate_is_printed_before_any_spend_and_the_spend_is_booked` |
| `max_usd` under the estimate: `skipped` is set, no object is made, the fake adapter has no call, `spend_usd == 0` | `test_an_estimate_past_the_run_budget_skips_the_check` |
| Second drive gives `[1, 1, 0, 0, 1, 1]`: `train_room == 2`, `noise_adjusted_wins is None`, one warning that holds `67% of items change between two runs` and `even fixing all 2 item(s) with room is not enough` | `test_noise_large_for_the_room_warns_and_never_refuses` |
| No stored row: `skipped` text, nothing made | `test_no_stored_rows_means_no_spend` |

Also:

- **Leaves nothing.** After success, after a failing adapter, and after a cancel in the middle of each pass: the set of files under the project folder equals the set before the job. `test_the_judge_copy_leaves_the_project_after_use` is the HT origin.
- One eval whose adapter raises a provider error: the job succeeds, the other eval has rows, `errors` holds the provider's text whole, and `GET /api/jobs/{id}/errors` holds it too.
- A shared item of two V2 evals is driven once (count the adapter calls), and `spend_usd` counts it once.
- A delete that raises (patched): the other objects are deleted, the temporary run config stays, `warnings` names the object, and the job succeeds. The next `sweep_task` removes the rest.
- Sweep: a left-over run config with eval runs and task runs, and a left-over judge copy, are removed; an object whose job is live in the registry is kept; an object with another name is never touched; a task with no left-over causes no read of runs.
- A second cancel during the clean-up does not stop it.
- `POST /api/jobs/eval_noise_check` is refused with the `create_path` text. The create route gives 404 for an unknown run config or eval id, and 422 for `items_per_eval=0`.
- `flip_rate` pools binary rows only, and is None with no compared item.

## 7. Scores by split

Each of the four routes gets one query parameter, with one description:

```
split: Annotated[EvalSplitName, Query(description="Which of the eval's dataset splits to summarise: train, val or test. Default test.")] = "test"
```

| Route | Handler | Change |
|---|---|---|
| `GET …/evals/{eval_id}/eval_config/{eval_config_id}/score_summary` | `get_eval_config_score_summary` | `resolved_split_or_422(task, eval, "test")` becomes `(task, eval, split)`. The 400 text for an empty split names the split: `This eval's {split} split is empty. Add items matching the {split} split's filter — …`. With `test` the text is the same as today |
| `GET …/tasks/{task_id}/eval_results_summary` | `get_eval_results_summary` | `_cached_test_split(task, eval, cache)` becomes `_cached_split(task, eval, split, cache)`, which reads `eval.splits.get(split)` and calls `resolve_split(task, eval, split)` |
| `GET …/run_configs/{run_config_id}/eval_scores` | `get_run_config_eval_scores` | Passes `split` to `run_config_eval_scores(task, run_config_ids, split)` |
| `GET …/run_configs/eval_scores` | `get_all_run_configs_eval_scores` | The same |

`run_config_eval_scores` gets `split: EvalSplitName = "test"`, and its `resolve_split(task, eval, "test")` becomes `resolve_split(task, eval, split)`. No response model changes. `dataset_size` is the size of the split asked for.

**422.** `score_summary` works on one eval, so a missing split gives the results route's text from `resolved_split_or_422`: `Eval '<id>' has no '<split>' split.` The three other routes work on every eval of the task: see open point 10.2.

**Tests** (`test_eval_api.py`), on a fixture whose train, val and test splits hold different items with different scores:

- For each of the four routes: the body with no `split` equals the body with `split=test`, and equals a body recorded from the code before the change. The existing tests of the four routes pass unchanged.
- `split=train` and `split=val` give that split's means and `dataset_size`.
- `score_summary` with a split that the eval does not have: 422 with the text. A value that is not a split name: 422 from FastAPI.
- The empty-split 400 names the split.

## 8. Paired comparison

`GET /api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}/run_config/{run_config_id}/compare`, in `eval_api.py`, beside the results route. Tag `Evals`. Free. It writes nothing. One eval per call. It returns no number across scores or evals.

Query: `baseline_run_config_id: str` (required), `split: EvalSplitName` (required). The path's run config is the candidate. The confidence is fixed at 0.95.

### 8.1 Response models (in `eval_api.py`)

`RunConfigComparison`: `rows: list[RunConfigComparisonRow]`, `n_baseline_items: int`, `n_candidate_items: int`, `skipped: list[SkippedScore]`. The two counts are the distinct items of the split with a stored row that is not a skip record.

`RunConfigComparisonRow`:

| Field | Type | Definition |
|---|---|---|
| `score_key`, `score_type`, `direction` | `str` | |
| `n_items` | `int` | The paired items |
| `baseline_score`, `candidate_score` | `float` | Binary: the pass rate. Rating: the mean. Never sign-normalised |
| `delta` | `float` | `candidate_score - baseline_score`, sign-normalised |
| `p_value` | `float \| None` | Not rounded (decision 9) |
| `significant` | `bool` | Below |
| `ci_low`, `ci_high` | `float \| None` | Rounded to 4 places, as the statistics route serves them; sign-normalised |
| `headroom` | `float \| None` | Binary: `1 - baseline_score` (`baseline_score` under `lower_is_better`). Rating: null |
| `fail_to_pass`, `pass_to_fail` | `int \| None` | Binary: the raw counts. Rating: null |

No item id and no per-item value is in the response.

### 8.2 Algorithm

Two functions in `eval_api.py`, beside `compute_score_summary`. They port `HT/analysis.py:compare_rows` and `_stats_row`.

`compare_run_configs(eval, eval_config, split, candidate_id, baseline_id) -> RunConfigComparison`:

1. **Rows of each side:** `rows_by_item(run for run in eval_config.runs(readonly=True) if run.task_run_config_id == <id> and eval_run_item_key(run) in split)`.
2. **Replicates:** folded by `rows_by_item` (1.2), as HT does: the mean per score, then the pass line.
3. `comparable_scores(eval)`. Its skipped entries go to `skipped`.
4. **Pairing**, per score: the items, sorted by key, where both sides have a non-null value. With none: `SkippedScore(reason="no paired items")`, and no row.
5. `compare_score(spec, values_a, values_b)`, with `a` the baseline and `b` the candidate.

`compare_score(spec, values_a, values_b, confidence=0.95) -> RunConfigComparisonRow`. It calls the library functions that the two statistics operations call. It does not call `_op_mcnemar_paired` or `_op_compare_paired`, which round.

| Score type | Statistics | `significant` |
|---|---|---|
| Binary | Outcomes `1 if v >= 0.5 else 0`. The table `(n11, n10, n01, n00)`. `p_value = mcnemar_exact_p(n10, n01)`. `(_, low, high) = paired_proportion_diff_ci(n11, n10, n01, n00, z_for_confidence(confidence))`. `fail_to_pass = n01`, `pass_to_fail = n10` | `p_value < 1.0 - confidence` |
| Rating | `p_value = wilcoxon_signed_rank_p([b - a ...])` (None under 5 non-zero differences). `(_, low, high) = paired_bootstrap_diff_ci(values_a, values_b, confidence=confidence)` | `p_value < 1.0 - confidence` when there is a p; else `low > 0 or high < 0`, on the unrounded ends |

**Sign normalisation** (HT's rule): under `lower_is_better`, `delta = -delta`, and `(ci_low, ci_high) = (-ci_high, -ci_low)`. The scores, the headroom rule above and the two counts are not turned. Kiln does not allow `lower_is_better` on these three score types today, so the branch runs only in its unit test.

### 8.3 Errors

1.3, with the baseline run config checked by `task_run_config_from_id`. A split that the eval does not have: 422, `Eval '<id>' has no '<split>' split.` `split=test`: 422, `The compare route does not compare on the test split. Use split=train or split=val.`, raised before any read.

### 8.4 Tests (`test_eval_api.py`)

HT's tests of this code run against a fake statistics answer, so they pin behaviour, not numbers. Kiln's tests pin the numbers against the statistics route: for one binary and one rating fixture, `p_value` equals `p_exact` or `wilcoxon_p` of `POST /api/statistics` before rounding, and the CI ends are equal.

| Case | HT test (`tests/test_analysis.py`) |
|---|---|
| Baseline replicates `1, 0, 1` and `0, 0`, candidate `1` and `1`: `n_items == 2`, `baseline_score == 0.5`, `candidate_score == 1.0`, `fail_to_pass == 1`, `pass_to_fail == 0` | `test_replicate_baseline_rows_fold_per_item_and_coverage_counts_items` |
| A null baseline value: the pair is left out, `n_items == 1`, `delta == 1.0` | `test_null_score_values_are_skipped_in_pairing` |
| No paired item: a `skipped` entry and no row | `test_no_paired_items_is_a_hole_not_a_row` |
| `compare_score` with a hand-built `lower_is_better` rating spec, baseline 4 and candidate 2: `delta == 2.0`, and the CI ends are swapped and negated | `test_ci_is_sign_normalized_with_the_delta_on_lower_is_better` |
| A rating score with fewer than 5 non-zero differences: `p_value is None`, and `significant` follows the interval | `test_compare_paired_small_n_uses_the_ci_when_wilcoxon_is_omitted` |

Also: `split=test` is 422 and reads nothing; a missing val split is 422; an unknown baseline is 404; the response body holds no item id of the fixture (search the JSON text); items outside the split are not paired; an informational score has no row.

## 9. Policies and generated files

### 9.1 Agent policy of each route (decision 13)

| Route | `openapi_extra` | MCP |
|---|---|---|
| `POST /api/statistics`, and the four routes of section 7 | `ALLOW_AGENT`, unchanged | Allowed |
| `GET …/eval_detectability`, `POST …/noise_check_estimate`, `GET …/compare` | `ALLOW_AGENT` | Allowed |
| `POST /api/jobs/evals/noise_check` | `agent_policy_require_approval("Run a noise check in the background? This runs the run config and its judges again on a sample of train items and uses AI credits.")` | Allowed |

"Allowed" for MCP means that the route has no `x-mcp-policy` tag. Absent is allowed (spec one).

### 9.2 Regeneration, in the phase that adds or changes the route (decision 14)

1. Start the dev server on port 8757.
2. `make schema`: rewrites `app/web_ui/src/lib/api_schema.d.ts`. CI checks it with `check_schema.sh`. Every phase here changes it: the statistics request, four new parameters, four new routes.
3. `make annotations`: writes one JSON file per new route under `libs/server/kiln_server/utils/agent_checks/annotations/`: `get_…_run_configs_run_config_id_eval_detectability.json`, `post_…_run_configs_run_config_id_noise_check_estimate.json`, `post_api_jobs_evals_noise_check.json`, `get_…_run_config_run_config_id_compare.json`. A file holds the method, the path and the policy only, so the statistics route and the four routes of section 7 give no new file.
4. `make api_docs` (`uv run python -m app.desktop.skill_api_reference generate`): regenerates the API reference of Kiln's skill [U].
5. Commit the generated files with the code. Run `uv run ./checks.sh --agent-mode`.

## 10. Conflicts and open points

None of these is decided here. Each has the evidence and a proposal for the owner.

1. **`n = 0` on the statistics route.** The functional spec lists 422 for a negative number only. The shared field `n` has `ge=1` today (`statistics_api.py`, used by `proportion_ci`), so `n = 0` is a 422. Proposed: keep the constraint, because no existing behaviour may change. HT's pinned `fewest_wins(0, 0) is None` is then tested on the library function, which the detectability read calls directly.
2. **`split` on the three task-wide summary routes.** The functional spec says "422 when the eval has no such split". `eval_results_summary` and the two `eval_scores` routes cover every eval of the task, and train and val splits are optional. A 422 would fail the whole call when one eval has no val split. Proposed: such an eval is left out of the answer, which is what the code already does for a missing test split (`if test_split is None: continue`).
3. **The sweep and a second Kiln.** Decision 6 says the sweep removes what no live job owns. A job record is in memory of one process (`JobRecord`, "never persisted"). With git auto sync, the temporary objects are pushed (`atomic_write` commits and pushes each save). A second machine that pulls them has no such job, so its app start, or its next noise job, deletes the objects of a job that still runs elsewhere. Proposed: the sweep also skips an object whose `created_at` is less than 24 hours old. This needs a ruling, because it changes when a left-over goes.
4. **The prefix is reserved but not enforced.** A run config or judge config that a person names `NOISE-CHECK …` is deleted by the sweep, with its eval runs. Proposed: the create and rename routes of run configs and judge configs refuse the prefix with a 422. This touches existing routes.
5. **A second judgment that drives.** When the stored trace of a baseline row cannot be reused (it was deleted, or the item's environment version changed), the runner drives the measured run config again. The new task run is under the measured run config, and it becomes the newest trace of its key. The runner does not say which traces it generated (`TraceIndex.get_or_create` returns `was_generated`, and `EvalRunner._trace` drops it). The rule of 6.6 step 3 finds such a run without a runner change, but it can also remove a drive that another job made in the same seconds and that nothing has scored yet. The smallest runner change that makes it exact: `EvalRunner` records the runs it generates in a judged run, as `driven_runs` does for a drive-only run. Not required; flagged.
6. **The exact test fails above about 1,030 changed pairs.** `mcnemar_exact_p(600, 700)` raises `OverflowError: int too large to convert to float` [V]. HT's `binomial_two_sided_p` has the same limit. It is reached by `noise_adjusted_wins` on a large, noisy train split (`n = 2000`, rate 0.5 [V]) and by the compare route. Proposed, with no change to the arithmetic: the statistics route maps `OverflowError` to a 422; the noise job gives `noise_adjusted_wins = None` for that row with a warning that says the value could not be computed; the compare route puts the score in `skipped`. The existing `mcnemar_paired` operation has the same failure today, as a 500.
7. **`spend_usd` and the synthetic user.** 6.5 adds `synthetic_user_usage.cost`, because it is money the job spent. HT's own figure, and the estimate formula, read `task_run_usage.cost` only, which leaves it out. For a multi-turn task the spend is then above the estimate. The other choice is HT's figure exactly.
8. **Build order.** The compare route imports `eval_power/stored_rows.py`. The architecture says steps 2 to 9 are free in order except "4 needs 3". So step 6 also needs step 3, or whichever is built first creates that file.
9. **Convention E17.** `eval_power/api.py` and the worker import `task_run_config_from_id` and `eval_from_id` from `eval_api.py`, as `jobs/api.py` and `workers/eval.py` do today. The rule says routers do not import each other. The fix is to move the lookups to a service module, which is outside this spec. It is reported under rule H24.
10. **"One line" for scores by split.** Two of the four changes are more than one line: the empty-split message, and the split cache helper.
11. **Dead branches.** `skipped` is always empty, and `lower_is_better` never occurs, on a project that loads today. Both are kept because the functional spec names them.

## 11. Unverified

- `make api_docs` and the `app/mcp` tree are on the build branch, not in this checkout.
- That a cancel always arrives inside `runner.run()` (6.8). It follows from asyncio's rules and the code read; the cancel test of 6.9 proves it.
- That a drive writes nothing in the project folder besides its `TaskRun` and `EvalRun`, for multi-turn and environment items. The "leaves nothing" test must have one item of each kind.
- That work in a worker thread inside `atomic_write` is safe. The eval runner saves on the event loop inside it.
- What HT's `Analyzer.judge_items` returns when only some items fail. 6.4 compares the items that have a row.
- That `resolve_split` and HT's on-disk reader give the same train count for every eval. `unscored` depends on it.
- The order of `eval_config.runs()`. HT keeps the last record of a replicate set in served order; 1.2 uses the newest by `created_at`.
