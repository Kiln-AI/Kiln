---
status: draft
---

# Component: Kiln measurement APIs

This document designs the Kiln side of [functional spec](../functional_spec.md) sections 3.1 to 3.4, 3.7 and 3.8, under the fixed decisions of the [architecture](../architecture.md) (decisions 5, 7 to 9, 13, 14, section 2.1, and the rulings 1, 2 and 6 of section 10). The noise check is not ported (decision 5): section 5 says what that means here.

**HT** is Kiln Harness Tuner at `b49f159`. `HT/x.py:f` names a function in `harness-tuner/src/kiln_harness_tuner/`. Kiln was read at `325c7cb3`. Marks: **[V]** checked by running code against Kiln's library in this checkout; **[U]** not verified. Everything else was read in the source. Every number and definition is HT's. The rulings of architecture section 10 are applied in the body. Section 10 lists the limits that are accepted.

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
| `eval_power/api.py` | `connect_eval_power_api(app)`: the route of section 4 |
| `app/desktop/studio_server/api_models/eval_power_models.py` | The pydantic models of section 4 |
| `app/desktop/studio_server/eval_api.py` | The `split` parameter (section 7) and the compare route (section 8) |
| `app/desktop/desktop_server.py` | `connect_eval_power_api(app)` before `connect_webhost` |

`train_items.py` and `stored_rows.py` are additions inside the package that architecture 2.1 names. The `eval_power` modules other than `api.py` are service code: they take loaded models, raise no `HTTPException`, and hold no module-level state. Tests sit beside each module as `test_<module>.py`.

**No change to existing lookups.** `task_run_config_from_id` and `eval_from_id` stay in `eval_api.py`. New modules import them from there, as `jobs/api.py` and `jobs/workers/eval.py` do today. Kiln's convention E17 says routers do not import each other, and the lookups raise `HTTPException`, so they cannot move to a service module without a refactor. Convention H24 covers this case: follow the local pattern, do not refactor neighbouring code, and report it in the end-of-task summary with the rule id.

No other existing code is moved.

### 1.2 Shared definitions (`eval_power/stored_rows.py`)

- **Score types.** Binary: `pass_fail`, `pass_fail_critical`. Rating: `five_star`. The paired test of a binary score is `mcnemar_paired`. The paired test of a rating score is `compare_paired` (`HT/analysis.py:_stats_row`). A binary value `>= 0.5` is a pass (the pass line).
- **`ScoreSpec`**: frozen dataclass `key: str` (`EvalOutputScore.json_key()`), `type: TaskOutputRatingType`, `direction: ScoreDirection`.
- **`comparable_scores(eval: Eval) -> tuple[list[ScoreSpec], list[SkippedScore]]`** ports `HT/detectability.py:comparable_specs`. It walks `eval.output_scores` in order. An `informational` score is left out with no entry. A score whose type is not binary or rating gives `SkippedScore(eval_id, score_key, reason="score type '<type>' has no statistics operation")`. On Kiln data today the skipped list is always empty: `EvalOutputScore` refuses a custom type and always has a direction.
- **`rows_by_item(runs: Iterable[EvalRun]) -> dict[ItemKey, ItemRow]`** ports `HT/analysis.py:_runs_by_item`. The item is `eval_run_item_key(run)`. `ItemRow` is a frozen dataclass: `scores: dict[str, float | None]`, `last: EvalRun`, `replicates: int`. One record: its scores. Several records of one item are replicates: each score is the mean of the non-null values, and `last` is the newest record by `created_at`. A binary score is read at the pass line after the mean.
- **`score_room(values, spec) -> int`** ports `HT/detectability.py:score_room`. Binary: an item has room when it is not a pass (a pass has room under `lower_is_better`). Rating: room when `normalize(value) < 1 - 1e-9`, where `normalize` is `(value - 1) / 4` clamped to [0, 1], and `1 -` that under `lower_is_better` (`HT/analysis.py:normalize`).
- **`select_evals(task, eval_ids) -> list[tuple[Eval, EvalConfig]]`** is the eval set of functional spec 3.1. With `eval_ids` absent: every eval of `task.evals(readonly=True)` whose `resolved_status(spec)` is not `archived` (the same test as `run_config_eval_scores`). With `eval_ids`: those evals, in the order given, duplicates dropped. In both cases an eval is kept only when `eval.current_config_id` is set and names an existing config; an eval without one is left out, with no error. The caller checks unknown ids first (404).
- **Stored train rows of an eval:** `rows_by_item(run for run in default_config.runs(readonly=True) if run.task_run_config_id == run_config_id and eval_run_item_key(run) in train.keys)`, where `train` is from section 3.

### 1.3 Errors common to the routes of sections 4 and 8

- **404**: an unknown project, task, run config, eval or judge config. The text is the existing lookup's: `task_from_id`, `task_run_config_from_id` (`Task run config not found. ID: <id>`), `eval_from_id` (`Eval not found. ID: <id>`), `eval_config_from_id`. The second and third stay in `eval_api.py`, and `eval_power/api.py` imports them from there (1.1).
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
| `n` | existing `int \| None`, `ge=1` | `None` | The paired items. The constraint is not changed, so `n = 0` is a 422 (architecture ruling 1) |
| `room` | `int \| None`, `ge=0` | `None` | Of `n`, the items not at the best value |

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
| `interpretation` | str | `At <pct>% confidence, <test> needs at least <floor> changed items, all one way, to call a difference significant.` With `n` and `room`, it adds ` With <room> of <n> items not at the best value, <fewest_wins> wins are enough in the best case.` or `..., no outcome can be significant.` |

### 2.3 The arithmetic (`statistics_lib.py`)

All functions are pure. `SIGNIFICANCE_FLOOR_SEARCH_LIMIT = 10_000` ports HT's `_MAX_FLOOR`.

| New function | Ports | Calls in Kiln | Rule |
|---|---|---|---|
| `significance_floor(test, alpha) -> int` | `HT/detectability.py:binary_floor`, `rating_floor`, `wilcoxon_all_positive_p` | `mcnemar_exact_p`, `wilcoxon_signed_rank_p` | `mcnemar_paired`: the smallest `k >= 1` with `mcnemar_exact_p(0, k) < alpha`. `compare_paired`: the smallest `k >= 5` with `wilcoxon_signed_rank_p([1.0] * k) < alpha`. Both stop at the search limit |
| `fewest_significant_wins(test, n, room, alpha) -> int \| None` | `detectability.py:fewest_wins` | the above | The floor when `min(room, n) >= floor`, else None |
| `interval_wins(test, n, room, confidence) -> int \| None` | `detectability.py:interval_wins`, `paired_ci_low`, `bootstrap_ci_excludes_zero` | `paired_proportion_diff_ci`, `z_for_confidence` | None when `n <= 0` or `room <= 0`. Else the smallest `k` in `1..min(room, n)` for which: (`mcnemar_paired`) the lower end of `paired_proportion_diff_ci(n - room, 0, k, room - k, z)` is `> 0`; (`compare_paired`) `((n - k) / n) ** n < alpha / 2` |
| `interval_best_case(test, n, confidence) -> int \| None` | `detectability.py:interval_best_case` | the above | The minimum of `interval_wins` over `room = 1..n`. Stop when it reaches 1 |

- **The bootstrap rule is the closed form on purpose** (decision 8). `interval_wins` for `compare_paired` does not call `paired_bootstrap_diff_ci`. A comment at the rule says: the closed form is HT's definition; the seeded draw can answer either way at the edge; do not replace it. A test pins it.
- The functions that HT copied (`_wilson`, `paired_ci_low`, `_z`, `wilcoxon_all_positive_p`) are not ported. Kiln's own functions give the same values [V].
- No noise function is ported: HT's `noise_adjusted_wins` and `binomial_two_sided_p` stay in `HT/noise.py` (section 5).
- `z` comes from `z_for_confidence` (Acklam), not HT's `NormalDist`. The two differ by 1.6e-9. Every pinned value below is the same with Kiln's `z` [V].
- Cost: `interval_best_case` is about 0.2 s at `n = 10,000` [V]. The existing `compare_paired` costs more at that size. No limit on `n` is added.

### 2.4 Handler and errors

`_op_significance_floor(req)` in `statistics_api.py`, added to `_OPERATIONS`. All errors are 422:

- `test` absent: `'test' is required for significance_floor.` `room > n`: `room must not be greater than n (got room=<room>, n=<n>).`
- **Overflow** (architecture ruling 6). The exact test fails above about 1,030 changed pairs: `mcnemar_exact_p(600, 700)` raises `OverflowError: int too large to convert to float` [V]. The arithmetic is not changed. `_op_significance_floor` catches `OverflowError` and answers 422: `The exact test cannot be computed for this many changed pairs (above about 1,030).` No request reaches this today: the floor search calls the exact test with all changes one way (`mcnemar_exact_p(0, k)`), which does not overflow, and it stops at 55 for the highest `confidence` that a float holds [V]. The catch is a guard, so that a later change to the arithmetic cannot turn a caller's request into a 500.
- A negative `room`, an unknown `test`, and `n < 1` (the existing `ge=1`; `n = 0` stays a 422, architecture ruling 1): pydantic's own text.

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

Also `test_bootstrap_rule_is_the_closed_form_not_the_seeded_draw`: it patches `paired_bootstrap_diff_ci` to raise, and `interval_wins("compare_paired", 20, 10, 0.95)` is still 4. HT's pinned `fewest_wins(0, 0) is None` is tested on the library function only (the `(0, 0)` case above), because the route refuses `n = 0`.

`test_statistics_api.py`: every output key for a full request (`test=mcnemar_paired, n=30, room=6`); every optional output null when only `test` is given, with `floor == 6`; each case of 2.4, with `n=0` as a 422; with `mcnemar_exact_p` patched to raise `OverflowError`, the request is a 422 with the text of 2.4, and the unpatched `mcnemar_exact_p(600, 700)` still raises `OverflowError` (the arithmetic is not changed); `interpretation` is one sentence or two; `test_openapi_exposes_operation_enum_and_agent_allow` lists five operations.

## 3. The train helper (decision 7)

`eval_power/train_items.py`. One helper, used by the detectability read only.

```
@dataclass(frozen=True)
class TrainItems:
    keys: frozenset[ItemKey]      # the train items that are held out nowhere
    left_out: frozenset[ItemKey]  # the train items that are val or test in some eval

class TrainSplits:
    def __init__(self, task: Task) -> None
    def train_items(self, eval: Eval) -> TrainItems | None   # None: the eval has no train split
    def val_size(self, eval: Eval) -> int | None             # None: the eval has no val split
```

- **Split resolution is Kiln's.** Every item set comes from `kiln_ai.datamodel.eval_splits.resolve_split(task, eval, name)`. Items are `ItemKey` pairs `(source, id)`, never a bare id. **Held-out set.** The constructor takes the union of the `val` and `test` split keys of every eval of `task.evals(readonly=True)`. Archived evals count: "any eval of the task".
- **`train_items`**: with `split` the eval's resolved train split, `keys = split.item_keys() - held_out`, `left_out = split.item_keys() & held_out`. **`left_out_held_out`** in a response is `len` of the union of `left_out` over the evals that the call read.
- **Cost.** `resolve_split` reads one whole store (`task.runs()` or `task.eval_inputs()`). The instance keeps a dict keyed `(split_ref.source, split_ref.filter_id)`, so each distinct filter is resolved once, as `eval_api._cached_test_split` does. The helper keeps the item keys of a split only, so a hit needs no new name or eval id. One instance lives for one request. It is never stored at module level.
- **Tests.** An item that is train in eval A and val in eval B is not in A's `keys` and is in `left_out`. The same for test in A itself, and for a val split of an archived eval. A `TaskRun` and an `EvalInput` with the same id do not collide. An eval with no train split gives None. Two evals with the same train filter resolve it once (count the calls to `resolve_split`). `val_size` is the key count, and None with no val split.

## 4. Detectability read

`GET /api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}/eval_detectability`, in `eval_power/api.py`. Tag `Run Configs`. Free. It writes nothing.

### 4.1 Query and response models

Query: `eval_ids: list[str] | None = None` (repeat the key; `None` is the set of 1.2), `confidence: float = 0.95` (`gt=0`, `lt=1`), `include_val_size: bool = False`.

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

### 4.2 Algorithm: `detectability.eval_detectability(task, run_config_id, evals, splits, confidence, include_val_size)`

Ports `HT/detectability.py:train_detectability`, `train_row` and the val half of `build_rows`.

1. The handler loads the task and the run config (404), checks each id of `eval_ids` with `eval_from_id` (404), calls `select_evals`, and builds one `TrainSplits(task)`.
2. For each eval: `comparable_scores`. Add its skipped entries. With no comparable score, go to the next eval.
3. `train = splits.train_items(eval)`. None, or a read that raises `ValueError` or `OSError` (but not `json.JSONDecodeError`, which the torn-read helper must see): add the id to `unread_eval_ids` and go on. This is HT's rule: a failed read drops that eval, never the call.
4. Read the stored train rows (1.2). For each spec, build the row of 4.1. An eval with no stored row gives rows with `n = 0`.

### 4.3 Tests (`eval_power/test_detectability.py`, `test_api.py`)

- `score_room`: `[1,1,0,0,0]` pass_fail → 3 (2 under `lower_is_better`); `[1,0,-1]` pass_fail_critical → 2; `[5,5,4,1]` five_star → 2; `[1,2,5]` five_star `lower_is_better` → 2 (`test_room_is_the_items_not_at_the_best_value`). The `lower_is_better` cases use a hand-built `ScoreSpec`.
- An informational score gives no row and no skipped entry; a score built with `model_construct` and a custom type gives the skipped reason text (`test_informational_scores_never_count`).
- A row on a held-out item is not counted in `n`, and `left_out_held_out` counts the item. No val or test result is read: a test makes every `EvalRun` of a val item raise on access to `scores`.
- `n = 0` rows for an eval with no stored row; an eval with no default judge config is absent; an eval with no train split is in `unread_eval_ids`; an unknown eval id is 404.
- `val` is absent without the flag. With it: the size, `round(val_n * room / n)`, and `floor / val_n`.
- Replicates of one item fold by the mean: `1, 0, 1` is a pass. A second call returns the same body, and the project folder has no changed file.

## 5. The noise check is not ported

Architecture decision 5, and functional spec 3.4. HT's noise check stays in HT as it is, behind `--noise-check`, off by default.

- Kiln gets no noise-check estimate route and no noise-check job. So there is no new job worker, no temporary object, no clean-up and no sweep. `jobs/api.py` and `desktop_server.lifespan` are not changed.
- The `significance_floor` operation has no noise input and no noise output (section 2).
- The train helper (section 3) is used by the detectability read only.

Section 6 is not used.

## 7. Scores by split

Each of the four routes gets the same query parameter: `split: Annotated[EvalSplitName, Query(description="Which of the eval's dataset splits to summarise: train, val or test. Default test.")] = "test"`. The three task-wide routes add one sentence to the description (below).

| Route | Handler | Change |
|---|---|---|
| `GET …/evals/{eval_id}/eval_config/{eval_config_id}/score_summary` | `get_eval_config_score_summary` | `resolved_split_or_422(task, eval, "test")` becomes `(task, eval, split)`. The 400 text for an empty split names the split: `This eval's {split} split is empty. Add items matching the {split} split's filter — …`. With `test` the text is the same as today |
| `GET …/tasks/{task_id}/eval_results_summary` | `get_eval_results_summary` | `_cached_test_split(task, eval, cache)` becomes `_cached_split(task, eval, split, cache)`, which reads `eval.splits.get(split)` and calls `resolve_split(task, eval, split)`. The `if … is None: continue` after it stays |
| `GET …/run_configs/{run_config_id}/eval_scores` | `get_run_config_eval_scores` | Passes `split` to `run_config_eval_scores(task, run_config_ids, split)` |
| `GET …/run_configs/eval_scores` | `get_all_run_configs_eval_scores` | The same |

`run_config_eval_scores` gets `split: EvalSplitName = "test"`, and its `resolve_split(task, eval, "test")` becomes `resolve_split(task, eval, split)`. No response model changes. `dataset_size` is the size of the split asked for.

**An eval that has no such split** (architecture ruling 2):

- `score_summary` works on one eval. A missing split is a 422 with the results route's text, from `resolved_split_or_422`: `Eval '<id>' has no '<split>' split.`
- The three other routes work on every eval of the task, and the train and val splits of an eval are optional. An eval that has no such split is left out of the answer. The call does not fail. The code does this today for a missing test split (`if test_split is None: continue`, in `get_eval_results_summary` and in `run_config_eval_scores`), and the same line now reads the split asked for. With a split that no eval of the task has, the answer has no eval.
- The parameter description of the three routes ends with: `An eval that has no such split is left out.`

**Tests** (`test_eval_api.py`), on a fixture whose train, val and test splits hold different items with different scores:

- For each of the four routes: the body with no `split` equals the body with `split=test`, and equals a body recorded from the code before the change. The existing tests of the four routes pass unchanged.
- `split=train` and `split=val` give that split's means and `dataset_size`.
- `score_summary` with a split that the eval does not have: 422 with the text. A value that is not a split name: 422 from FastAPI. The empty-split 400 names the split.
- Each of the three task-wide routes with `split=val`, on a task where one of two evals has no val split: status 200, the eval with a val split is in the answer, and the other eval is absent.

## 8. Paired comparison

`GET /api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}/run_config/{run_config_id}/compare`, in `eval_api.py`, beside the results route. Tag `Evals`. Free. It writes nothing. One eval per call. It returns no number across scores or evals. Query: `baseline_run_config_id: str` (required), `split: EvalSplitName` (required). The path's run config is the candidate. The confidence is fixed at 0.95.

### 8.1 Response models (in `eval_api.py`)

`RunConfigComparison`: `rows: list[RunConfigComparisonRow]`, `n_baseline_items: int`, `n_candidate_items: int`, `skipped: list[SkippedScore]`. The two counts are the distinct items of the split with a stored row that is not a skip record. No item id and no per-item value is in the response.

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

### 8.2 Algorithm

Two functions in `eval_api.py`, beside `compute_score_summary`. They port `HT/analysis.py:compare_rows` and `_stats_row`. They import `rows_by_item` and `comparable_scores` from `eval_power/stored_rows.py`, so build step 6 needs step 3 (architecture section 8).

`compare_run_configs(eval, eval_config, split, candidate_id, baseline_id) -> RunConfigComparison`:

1. **Rows of each side:** `rows_by_item(run for run in eval_config.runs(readonly=True) if run.task_run_config_id == <id> and eval_run_item_key(run) in split)`.
2. **Replicates:** folded by `rows_by_item` (1.2), as HT does: the mean per score, then the pass line.
3. `comparable_scores(eval)`. Its skipped entries go to `skipped`.
4. **Pairing**, per score: the items, sorted by key, where both sides have a non-null value. With none: `SkippedScore(reason="no paired items")`, and no row.
5. `compare_score(spec, values_a, values_b)`, with `a` the baseline and `b` the candidate.
6. **Overflow** (architecture ruling 6, and 2.4): when `compare_score` raises `OverflowError` (a binary score with more than about 1,030 changed pairs), the score gets `SkippedScore(reason="the exact test cannot be computed for this many changed pairs")`, and no row. The other scores keep their rows. The arithmetic is not changed.

`compare_score(spec, values_a, values_b, confidence=0.95) -> RunConfigComparisonRow`. It calls the library functions that the two statistics operations call. It does not call `_op_mcnemar_paired` or `_op_compare_paired`, which round.

| Score type | Statistics | `significant` |
|---|---|---|
| Binary | Outcomes `1 if v >= 0.5 else 0`. The table `(n11, n10, n01, n00)`. `p_value = mcnemar_exact_p(n10, n01)`. `(_, low, high) = paired_proportion_diff_ci(n11, n10, n01, n00, z_for_confidence(confidence))`. `fail_to_pass = n01`, `pass_to_fail = n10` | `p_value < 1.0 - confidence` |
| Rating | `p_value = wilcoxon_signed_rank_p([b - a ...])` (None under 5 non-zero differences). `(_, low, high) = paired_bootstrap_diff_ci(values_a, values_b, confidence=confidence)` | `p_value < 1.0 - confidence` when there is a p; else `low > 0 or high < 0`, on the unrounded ends |

**Sign normalisation** (HT's rule): under `lower_is_better`, `delta = -delta`, and `(ci_low, ci_high) = (-ci_high, -ci_low)`. The scores, the headroom rule above and the two counts are not turned. Kiln does not allow `lower_is_better` on these three score types today, so the branch runs only in its unit test.

**Errors:** 1.3, with the baseline run config checked by `task_run_config_from_id`. A split that the eval does not have: 422, `Eval '<id>' has no '<split>' split.` `split=test`: 422, `The compare route does not compare on the test split. Use split=train or split=val.`, raised before any read.

### 8.3 Tests (`test_eval_api.py`)

HT's tests of this code run against a fake statistics answer, so they pin behaviour, not numbers. Kiln's tests pin the numbers against the statistics route: for one binary and one rating fixture, `p_value` equals `p_exact` or `wilcoxon_p` of `POST /api/statistics` before rounding, and the CI ends are equal.

| Case | HT test (`tests/test_analysis.py`) |
|---|---|
| Baseline replicates `1, 0, 1` and `0, 0`, candidate `1` and `1`: `n_items == 2`, `baseline_score == 0.5`, `candidate_score == 1.0`, `fail_to_pass == 1`, `pass_to_fail == 0` | `test_replicate_baseline_rows_fold_per_item_and_coverage_counts_items` |
| A null baseline value: the pair is left out, `n_items == 1`, `delta == 1.0` | `test_null_score_values_are_skipped_in_pairing` |
| No paired item: a `skipped` entry and no row | `test_no_paired_items_is_a_hole_not_a_row` |
| `compare_score` with a hand-built `lower_is_better` rating spec, baseline 4 and candidate 2: `delta == 2.0`, and the CI ends are swapped and negated | `test_ci_is_sign_normalized_with_the_delta_on_lower_is_better` |
| A rating score with fewer than 5 non-zero differences: `p_value is None`, and `significant` follows the interval | `test_compare_paired_small_n_uses_the_ci_when_wilcoxon_is_omitted` |

Also: `split=test` is 422 and reads nothing; a missing val split is 422; an unknown baseline is 404; the response body holds no item id of the fixture (search the JSON text); items outside the split are not paired; an informational score has no row; `mcnemar_exact_p` patched to raise `OverflowError` gives a `skipped` entry with the overflow reason, no row for that score, and status 200.

## 9. Policies and generated files

### 9.1 Agent policy of each route (decision 13)

Every route here is allowed for MCP: none gets an `x-mcp-policy` tag, and absent means allowed (spec one).

| Route | `openapi_extra` |
|---|---|
| `POST /api/statistics`, and the four routes of section 7 | `ALLOW_AGENT`, unchanged |
| `GET …/eval_detectability`, `GET …/compare` | `ALLOW_AGENT` |

### 9.2 Regeneration, in the phase that adds or changes the route (decision 14)

1. Start the dev server on port 8757.
2. `make schema`: rewrites `app/web_ui/src/lib/api_schema.d.ts`. CI checks it with `check_schema.sh`. Every phase here changes it: the statistics request, four new parameters, two new routes.
3. `make annotations`: writes one JSON file per new route under `libs/server/kiln_server/utils/agent_checks/annotations/`: `get_…_run_configs_run_config_id_eval_detectability.json` and `get_…_run_config_run_config_id_compare.json`. A file holds the method, the path and the policy only, so the statistics route and the four routes of section 7 give no new file.
4. `make api_docs` (`uv run python -m app.desktop.skill_api_reference generate`): regenerates the API reference of Kiln's skill [U].
5. Commit the generated files with the code. Run `uv run ./checks.sh --agent-mode`.

## 10. Accepted limits

Each of these is settled. Nothing here waits for a decision.

1. **The exact test overflows above about 1,030 changed pairs.** The comparison skips the score, and the `significance_floor` operation answers 422 if it ever meets the error (ruling 6; 2.4). The existing `mcnemar_paired` operation has the same failure today and is not changed.
2. **Dead branches.** `skipped` is always empty, and `lower_is_better` never occurs, on a project that loads today. Both are kept because the functional spec names them. The overflow catch of `significance_floor` is also not reached today (2.4). It is kept because ruling 6 names it.

## 11. Open points

None.

## 12. Not verified

- `make api_docs` and the `app/mcp` tree are on the build branch, not in this checkout.
- That `resolve_split` and HT's on-disk reader give the same train count for every eval; `unscored` depends on it. Also the order of `eval_config.runs()`: HT keeps the last record of a replicate set in served order; 1.2 uses the newest by `created_at`.
