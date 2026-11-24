---
status: draft
---

# Component: Harness Tuner's Switch to Kiln's APIs, the Removals and the Proof

This document designs steps 12 to 17 of the [architecture](../architecture.md) build order, and the start-up checks of step 10. It covers [functional spec](../functional_spec.md) sections 5.6 to 5.10, 6 and 7. The sibling document [ht_skill_reading_and_roles.md](ht_skill_reading_and_roles.md) covers `SkillReader`, the gateway tool `kiln_skill`, the role entry files and the contract list.

Conventions:

- **HT** is the harness-tuner repository at commit `b49f159`. HT paths are under `src/kiln_harness_tuner/` unless they start with `tests/`, `docs/` or `src/`. Line numbers are of that commit. Test counts are collected counts at that commit (3,965 in all).
- A code block with no language is a signature or pseudo-code.
- **"Per the Kiln component doc"** marks an exact name that a sibling Kiln document fixes: [kiln_measurement_apis.md](kiln_measurement_apis.md) or [kiln_smells_skills_version.md](kiln_smells_skills_version.md). Both were written at the same time as this one. The names here were aligned with them after the rulings of architecture section 10. A name can still move: the Kiln document wins, and `contract.py` (section 4) finds a mismatch at start-up.
- The rulings of architecture section 10 are applied in the body. Section 10 lists the limits that are accepted, and section 11 the points that are still open.
- What stays in HT, unchanged: screening and the measurement engine, the model preflight, the integrity, judge-copy, reference and generality checks, probes, latency, the model policy, and HT's own paired comparison (`Analyzer.compare_rows`).

## 1. REST client additions (`kiln.py`)

HT's code reaches Kiln through one call shape (`analysis.KilnApi`): `KilnClient.call`, the gateway's `self.call`, and `FakeKiln.call` in tests. So the new methods are on a small wrapper of that call, not on `KilnClient` alone:

```
class KilnRoutes:
    def __init__(self, call: Callable[..., Awaitable[Any]]) -> None
KilnClient.routes -> KilnRoutes            # property: KilnRoutes(self.call)
```

| Method | Route | Notes |
|---|---|---|
| `version() -> dict` | `GET /api/version` | 5 s, `retries=False` |
| `significance_floor(test, *, confidence=0.95, n=None, room=None, noise_rate=None) -> dict` | `POST /api/statistics`, body `operation: "significance_floor"` and the given fields | `retries=True`: pure. `test` is `mcnemar_paired` or `compare_paired` |
| `eval_detectability(project_id, task_id, run_config_id, *, eval_ids, confidence=0.95) -> dict` | `GET …/run_configs/{run_config_id}/eval_detectability` | `eval_ids` is a repeated query parameter. HT never sends `include_val_size` (2.5) |
| `noise_check_estimate(project_id, task_id, run_config_id, *, items_per_eval, eval_ids, confidence=0.95) -> dict` | `POST …/run_configs/{run_config_id}/noise_check_estimate` | `retries=True`: free, writes nothing |
| `start_noise_check(project_id, task_id, run_config_id, *, items_per_eval, eval_ids, confidence, max_usd=None, concurrency=None) -> str` | `POST /api/jobs/evals/noise_check` | `retries=False`: it spends. Returns the job id |
| `smell_check(project_id, task_id, run_config_id, *, as_of: date) -> dict` | `GET …/run_configs/{run_config_id}/smell_check?as_of=YYYY-MM-DD` | |
| `create_skill_from_folder(project_id, *, folder_path, provenance) -> dict` | `POST /api/projects/{project_id}/skills/from_folder` | `retries=False` |
| `skill_files(project_id, skill_id) -> dict` | `GET …/skills/{skill_id}/files` | `files`, each with `path` and `size_bytes`, and `total_bytes` (per the Kiln component doc) |
| `skill_file(project_id, skill_id, path) -> str \| None` | `GET …/skills/{skill_id}/files/{path}` | Each path segment is URL-quoted. Returns `content`. `None` when `is_text` is false: a binary file, or a file over Kiln's limit of 524,288 bytes (per the Kiln component doc) |
| `model_info_models(**params) -> dict`, `model_info_details(model_id, provider=None) -> dict`, `model_info_providers() -> dict` | `GET /api/model_info/models`, `/model_details`, `/providers` | Built in spec one |

The noise job is followed with the existing job routes, through the calls HT has today (`POST /api/jobs/wait`, `GET /api/jobs/{id}/errors`, `POST /api/jobs/{id}/cancel`).

**Error mapping.** Every method raises what `call` raises today: `KilnAPIError` (4xx at once; 5xx after the retries of a GET) and `KilnTransportError`. No error type is added. The callers decide:

| Caller sees | Meaning for the caller |
|---|---|
| `KilnAPIError` 404 on `version()` | A Kiln older than this spec: the "too old" problem (section 3) |
| `KilnAPIError` 422 on `create_skill_from_folder` | The folder was refused. The body holds every problem (2.1) |
| `KilnAPIError` 404 on a skill, a run config or a model | The id is unknown. The caller's own fallback applies (each section below) |
| Any `KilnError` in detectability, the noise check or the smell check | The documented fallback of that step. None of the three ends a run, except the refusal of 2.5 |

`kiln_error_text` is not changed.

## 2. The switches

### 2.1 Skill bundle install and export: two gateway tools

The tool names stay (decision 15). The server prefix changes from `mcp__skill_installer__` to `mcp__kiln_harness_tuner_gateway__`.

| Part | Design |
|---|---|
| `gateway/models.py` | `SkillBundleInstall(In)`: `bundle_path: str`, `provenance_notes: str`, `derived_from_ids: list[str]`. `SkillBundleExport(In)`: `skill_id: str = Id`, `dest_path: str`. Answers: `SkillBundleInstalled(Out)`: `ok`, `skill_id`, `skill_name`, `tool_id`, `errors`. `SkillBundleExported(Out)`: `ok`, `path`, `files`, `skipped`, `errors` |
| `gateway/ops.py` `OPS` | `install_skill_bundle`, `export_skill_bundle`, with today's tool descriptions, cut to what is still true |
| `ROLE_OPS` | `create_experiment_rc`: both. `probe`: `install_skill_bundle` only. As `SKILL_INSTALLER_TOOLS` today |
| `OP_ROUTES` | install: `POST /api/projects/{project_id}/skills/from_folder`. export: the two `files` routes |
| The scratch root | `(state.run_dir / "scratch").resolve()`. The gateway needs no new argument |

**Install, in order:**

1. **Kept in the gateway** (from `bundle.validate_bundle:196-208`): the resolved `bundle_path` is a directory strictly inside the scratch root, and is not the root. A failure answers `{"ok": false, "errors": […]}` and makes no call to Kiln. `provenance_notes` must not be blank.
2. List the project's skills (`GET …/skills`). The ids of `derived_from_ids` that are skills go in `provenance.derived_from_ids`. The others (a parent run config) are appended to the notes as `Derived from: <ids>.` (functional spec 3.9).
3. `routes.create_skill_from_folder(project_id, folder_path=<resolved path>, provenance={"notes", "derived_from_ids", "origin": "agent"})`.
4. Success: `{"ok": true, "skill_id", "skill_name", "tool_id"}`, from the answer's `id`, `name` and `tool_id` (per the Kiln component doc).
5. HTTP 422: `{"ok": false, "errors": [<each problem as one string>]}`, from the body's `error_messages` list (per the Kiln component doc). HTTP 400 (a parent that is not a skill of the project) answers `ok: false` with Kiln's message. Any other error is a `GatewayError`.

**Export, in order:**

1. **Kept in the gateway** (from `bundle.export_bundle:425-438`): `dest_path` is absolute, strictly inside the scratch root, and does not exist.
2. `routes.skill_files(project_id, skill_id)`. A 404 answers "no installed skill with id …". `total_bytes` must be at most 4 MiB (`EXPORT_MAX_BYTES`, kept in the gateway).
3. For each file: `routes.skill_file(…)`, then write the text under `dest_path`, UTF-8. A path that is absolute or holds `..` is refused before any write.
4. **A binary asset is not copied** (architecture ruling 16). A file that Kiln does not return as text (`is_text` false: a binary asset, or a file over Kiln's size limit) is not written. Its path goes in `skipped`, so the answer names each file that the export skipped. Today's export copies a binary asset byte for byte. Kiln's skill runtime reads assets as text only, so a binary asset was of no use to the agent. The tool description says: "A binary asset is not copied. `skipped` names each file that was left out."
5. Answer `{"ok": true, "path", "files", "skipped"}`. On a failure after the first write, the gateway removes `dest_path` and answers `ok: false`.

**Deleted:** `skill_installer/` (575 lines), the `skill_installer` server entry and `INSTALLER_MODULE` in `cli.render_run_configs` (`:837`, `:945-967`), `SKILL_INSTALLER_TOOLS` in `gateway/hook.py` and its use in `cli.py:57` and `dispatch/codex_cli.py:64,222-232`, `_SKILL_INSTALLER_TOOL` and `_SKILL_EXPORT_TOOL` in `dispatch/claude_cli.py:148-167`, and `sweep_staging` at run start (`cli.py:146,1482-1486`): Kiln stages the write and removes its own left-overs.

### 2.2 Loop code that reads a skill's files

`prompt_text.read_skill` (`:181-222`) reads the project folder today. It feeds `rc_texts`, which the integrity, judge-copy, reference and generality checks, the model preflight and the smell step use.

```
async def read_skill(kiln: KilnApi, project_id: str, skill_id: str) -> SkillText | None
```

1. `GET …/skills/{skill_id}`: the name, and `provenance.derived_from_ids` for `derived_from`.
2. `routes.skill_files`: the paths and sizes.
3. `routes.skill_file` for `SKILL.md`, each `references/` file, and each `assets/` file of at most `ASSET_MAX_BYTES` (256 KiB). A binary asset is left out, as today.
4. Any `KilnError`, or a missing `SKILL.md`, returns `None`. Each reader already says what it does with an unreadable skill.

- `rc_texts` awaits it and keeps its per-call cache. `SkillText` and `whole_texts` do not change, so no checker changes.
- `read_code_tool` (`:245-290`) stays on disk. No Kiln route serves a code tool's files (functional spec section 9).
- **Deleted:** the import of `installed_skill_dir` (`:37`). `_tree_files` stays: `read_code_tool` uses it.

### 2.3 Model info

| Part | Design |
|---|---|
| `gateway/model_info.py` | Rewritten, about 120 lines. Pure functions that take Kiln's answers and the policy. `Offered`, `_merged`, `SERVER_FIELDS` and every sort and filter go: Kiln does the join, the filters and the sort |
| The status | Kiln's entry status is `ready`, `not_offered` or `not_connected`. HT changes a `ready` entry to `blocked_by_policy` when `policy.decide(provider, model).allowed` is false. Nothing else is changed |
| `list_models` | (a) Send the agent's filters to `routes.model_info_models` with `limit=200` and `offset=0, 200, …` until `offset >= total`. (b) Apply the status. (c) Unless `include_not_available`, drop each `blocked_by_policy` entry, then each row with no entry left. (d) `total` is the count after (c). (e) Return the page `[offset : offset + limit]` of the agent's request, in Kiln's order. HT's default `limit` stays 50 |
| `get_model_details` | `routes.model_info_details(req.model, req.provider)`, then the status on each provider entry. Kiln's 404 becomes today's `GatewayError` texts. The tool argument stays `model`; Kiln's parameter is `model_id` |
| `list_providers` | `routes.model_info_providers()`. With no policy, the rows are Kiln's. With a policy, `ready_model_count` is counted again from an all-pages `model_info_models(include_deprecated=True)` read with the status applied. `include_not_available=false` drops `not_connected` rows, as today |
| Answer models | `ModelRow`, `ProviderEntryRow`, `ModelDetailsView`, `ProviderEntryDetails`, `ProviderRow` keep their fields: Kiln's rows were built from them. `CatalogState` (`catalog: {kiln, models_dev, fetched_at}`) is replaced by `sources`, copied from Kiln's answer |
| With no policy | The policy is `None`. Each answer is Kiln's, paged by Kiln: no all-pages read |

**One flag of a list row is not exact** (architecture ruling 20, accepted). Kiln sets `has_thinking_levels` of a model row from every listed provider entry. After HT drops a blocked entry, the flag can be true because of that entry. A list row has no per-entry data to correct it. `get_model_details` is exact.

**Deleted:** `model_catalog/` (777 lines); `load_catalog` and `State.catalog` (`gateway/server.py:31,63`, `gateway/ops.py:44,131`); `_offered` (`ops.py:481-484`); `fetch_catalog`, `write_catalog`, `log_catalog`, `CATALOG_FILE` in `RUN_DIR_ENTRIES`, and the option `--no-model-catalog` (`cli.py:87-92,417-419,820,1157,1206,1219-1233,1466-1472,1520,1546`); `Ctx.model_catalog` (`orchestrator.py:110,337-341`); `tests/fixtures/model_catalog/`.

**The run log.** At run start, `cli._run` logs one event `kiln_version` with Kiln's `version` and `min_supported_harness_tuner_version`. It replaces the `model_catalog` events. Model information is a live read from then on.

**Kept:** `model_policy.py`, the policy copy in the run folder, the check in `create_run_config` and `run_task`, and every loop-code check of the policy.

### 2.4 The significance floor

| | |
|---|---|
| Deleted from `detectability.py` | `binary_floor`, `wilcoxon_all_positive_p`, `rating_floor`, `significance_floor`, `fewest_wins`, `_z`, `_wilson`, `paired_ci_low`, `bootstrap_ci_excludes_zero`, `interval_wins`, `interval_best_case` (`:114-264`), `WILCOXON_MIN_NONZERO`, `_MAX_FLOOR` |
| Deleted from `noise.py` | `binomial_two_sided_p`, `noise_adjusted_wins` (`:117-141`) |
| New helper in `detectability.py` | `async def floors(ctx, alpha) -> Floors`: two calls of `routes.significance_floor`, one per `test`, with no `n`. It gives `floor_binary` and `floor_rating` for `DetectabilityReport` |
| New helper | `async def val_interval_best_case(ctx, score_type, val_n, alpha) -> int \| None`: one call with `n=val_n`, cached per `(test, val_n)` for the run. It reads `interval_best_case`. With `val_n < 1` it makes no call and returns `None`: the route refuses `n = 0` |
| Score type to `test` | A type in `BINARY_SCORE_TYPES` is `mcnemar_paired`. A type in `RATING_SCORE_TYPES` is `compare_paired` |
| `confidence` | `1 - SIGNIFICANCE_ALPHA` |
| Not changed | The gateway tool `compute_statistics` and its request model. No role needs the new operation: the planner gets the numbers in its input |

### 2.5 Detectability

| Function | After |
|---|---|
| `train_detectability(ctx, rc_id, active, …)` (`:334`) | One call: `routes.eval_detectability(…, eval_ids=[the active eval ids], confidence=…)`. Each row of the answer fills `schemas.TrainDetectability` field by field: `eval_id`, `eval_name`, `score_key`, `score_type`, `direction`, `n`, `room`, `unscored`, `floor`, `fewest_wins`, `best_case_change`. The row's `interval_wins` is kept beside it for `build_rows`. A `KilnError` returns `[]`: advisory, as today. The `runs=` and `train_sizes` arguments go |
| `train_row`, `score_room`, `comparable_specs` (`:266-331`) | Deleted. `skipped` comes from the answer |
| `run_detectability_check` (`:604`) | (1) the active evals, by HT's own rule; (2) `train_detectability`; (3) `floors`; (4) `build_rows`; (5) `assess`; (6) the same events, lines and refusal. `left_out_held_out` and `unread_eval_ids` go in the `detectability` event. `ctx.train_split_sizes` is no longer set |
| `build_rows` (`:370`) | **Kept: the val side is HT's.** `val_n` comes from `split_sizes(ctx, "val")`, read from disk as today. `val_room_estimate` and `val_best_case_change` keep their one-line formulas, on the row's `floor`. `train_interval_wins` is the row's `interval_wins`. `val_interval_best_case` comes from the helper of 2.4 |
| `assess`, `_row_warnings`, `row_line`, `val_certainly_undetectable`, `val_estimate_undetectable`, `UnderpoweredEvalsError`, `--allow-underpowered`, `--min-effect` | **Kept, unchanged.** The refusal is HT's rule |
| The per-wave read (`orchestrator.py:2674-2680`) | One call of `train_detectability` for the baseline, after the loop over the evals. Free |

HT does not send `include_val_size`. Kiln never reads a val result for HT, and HT's val sizes stay its own.

**Counts can differ from today's** (architecture ruling 17, accepted). HT also holds out an item that carries a tag named `val`, `test`, `val_*`, `test_*`, `holdout*` or `heldout*`, used by an eval or not (`gateway/trainset.py:16-21`). Kiln's train helper removes only an item that is in a val or test split of an eval. On a task with such tags, Kiln's `n`, `room` and `unscored` can count an item that HT holds out by name. The answer holds counts only: no item id and no row reaches an agent.

### 2.6 The noise check

`run_noise_check(ctx, rc_id)` (`noise.py:391`) keeps its name, its result type and its events. New sequence:

| # | Step | Owner |
|---|---|---|
| 1 | `routes.noise_check_estimate(…, items_per_eval=ctx.noise_check_items, eval_ids=[active], confidence=…)` | Kiln |
| 2 | The answer has `skipped`: set `result.skipped` and finish, as today | HT |
| 3 | Log `noise_estimate` with `estimate_usd`, `distinct_items`, the two per-item prices, and `rows_without_drive_cost` and `rows_without_judge_cost` | HT |
| 4 | **The train-set guard** (architecture ruling 17). HT checks the estimate's sample against its own train set before it starts a job. The train set is `TrainSet.load(ctx.train_set_path)` (`gateway/trainset.py`), the set that `orchestrator.run_quarantine` wrote at start-up. Every id of every `evals[].item_ids` must be in `TrainSet.ids`. With `k` ids outside it, the check is skipped: `result.skipped = f"{k} sampled item(s) are not in the tuner's train set, so the noise check did not run"`. With no train set file, it is skipped with `the tuner's train set is not known, so the noise check did not run`. Today the train read refuses such rows (`HeldOutLeakError`). The job samples the same items as the estimate: both use one rule with no random draw (per the Kiln component doc) | HT |
| 5 | **The budget decision:** `left = remaining_run_budget(ctx)`. `estimate_usd > left` skips the check with today's text | HT |
| 6 | `routes.start_noise_check(…, max_usd=left, concurrency=ctx.max_concurrent_evals)`. `max_usd` is left out when the run has no budget | Kiln |
| 7 | Wait with `POST /api/jobs/wait` (`timeout` 3600, repeated until the job ends). When the run is stopped, cancel the job | HT calls, Kiln runs |
| 8 | Read the job record's `result`: `estimate_usd`, `spend_usd`, `rows`, `warnings`, `skipped`, `errors`, `flip_rate`. Kiln sets `result` only when the job succeeded. A job over `max_usd` succeeds with `skipped` set | Kiln |
| 9 | **Book the spend:** one `spend` event, source `noise_check`, provider lane, `cost_usd = spend_usd`. `spend_usd` is HT's figure of today: the task run usage and the judge usage, without the simulated user (per the Kiln component doc). A failed or cancelled job has no `result` and reports no spend (architecture ruling 8): HT books nothing, sets `result.skipped`, and logs `noise_spend_unknown`. Today an interrupted check is not booked either | HT |
| 10 | `errors`: `provider_errors.diagnose_job_errors` on each entry's `message`. A quota class raises `ProviderQuotaError` after step 9, as today. The other errors are logged | HT |
| 11 | Each row fills `schemas.NoiseRow` (`model_validate`; the fields are HT's). `baseline_rc_id` is set by HT. `warnings` are Kiln's. A row can have a null `noise_adjusted_wins` with a warning that the exact test could not be computed. A row can have a `rejudge_note` together with re-judged counts: Kiln's second judgment never drives, and it leaves out a sampled item whose stored trace cannot be reused (per the Kiln component doc). `rejudge_items` is then below `items` | HT |
| 12 | `_finish`: `ctx.train_noise`, the `noise_row`, `noise_warning` and `noise_check` events | HT |

- **Deleted:** `_EvalSample`, `sample_items`, `_values`, `changes`, `_row_output`, `same_outputs`, `judge_copy_note`, `_sample`, `estimate_usd`, `_create_clone`, `_create_judge_copy`, `archive_eval_config`, `_warnings`, `NOISE_NAME_PREFIX`, and the `noise_clone` event. The noise judge-copy archive no longer writes into the project folder.
- **Kept:** `noise_line`, `_finish`, `SPEND_SOURCE`, and `stop_rules.noise_flip_rate` (`:126`), which still reads the rows and filters them by eval. HT does not use the pooled `flip_rate`. `noise_line` prints `rejudge_note` only when nothing was re-judged, as today; the note of a partly measured row is in the `noise_row` event.
- `NoiseCheckResult.clone_rc_id` stays in the schema and is always `None`: the temporary run config is Kiln's and is gone when the job ends. The report line (`report.py:320-321`) drops the word "clone".
- `ctx.policy_exempt_rcs.add(clone)` goes with the clone.
- A failure of step 1, 6 or 7 sets `result.skipped` with the reason. The check never ends a run, except for a quota error.

### 2.7 The smell check

| Function | After |
|---|---|
| `run_detectors(ctx, rc_id)` (`smells/run.py:387`) | `answer = await routes.smell_check(project, task, rc_id, as_of=ctx.run_started_at.date())`. With no run start time, `as_of` is today's date. Each entry of `detections` is validated as `schemas.Detection`. Then today's filter on the known smell ids, and the `smell_unknown` and `smell_detections` events. `unread_tools` is logged as today. The answer's `model.release_date_note` (per the Kiln component doc), when set, is logged in the same event |
| `ensure_detections` (`:364`) | Not changed. A failed call logs `smell_detection_skipped` and gives no detection |
| How the answer fills `Detection` (`schemas.py:1753-1767`) | `smell`, `detector`, `scope`, `fact` (at most 300 characters), `value`, `reference`, `reference_source` are the fields of the same names. `eval_id` stays `None`. Needed from Kiln: the `detector` values `long_prompt`, `long_tool_description`, `long_skill_description`, `many_tools`, `old_model` (per the Kiln component doc). `DetectionCheck`, `planner_detections` and the report match on `(smell, detector)` |
| `as_of` | The run's start date, so the old-model answer does not change during a run. Today's `DetectorInputs.run_date` is the same date |

- **Deleted:** `smells/detectors/` (5 detectors and `detector_smells`), `smells/thresholds.py`, `smells/model.py`, and in `smells/run.py`: `_collect`, `_model_facts`, `_iso_date`, `_definition`, `_train_trace_stats`, the `detectors=` argument and the `smell_detector_failed` event.
- **Kept:** `ensure_baseline_reviewed`, `_review`, `_valid_findings`, `baseline_trace_samples`, `planner_detections`, and how findings are recorded and reported.

## 3. Version checks and the start-up order

All of it is in `onboarding/kiln_check.check_kiln`, which every run calls first (`onboarding/flow.py:182`). New signature: `check_kiln(kiln, host, *, skill: SkillSource, own_version: str = __version__)`. `onboarding/flow._check_kiln` passes `SkillReader(host)`. A failure in steps 1 to 4 is a `Problem`: the run stops before any spend.

| # | Step | Failure |
|---|---|---|
| 1 | `GET /ping` | Today's two problems, unchanged |
| 2a | `routes.version()`; `version` against `MIN_KILN_VERSION`. Skipped when `KILN_HARNESS_TUNER_SKIP_KILN_VERSION_CHECK` is set (below) | "Too old for the tuner" |
| 2b | `own_version` against `min_supported_harness_tuner_version` | "The tuner is too old" |
| 3 | `GET /openapi.json`, then `contract.missing_api(openapi)` | "Kiln does not have an API the tuner needs" |
| 4 | `contract.missing_skill_paths(skill)` | "Kiln's skill does not have a file the tuner needs" |
| 5 | The rest of today's start-up, with `contract_preflight` before wave 1 | As today |

**The constant.** `MIN_KILN_VERSION` in `onboarding/kiln_check.py`: the first Kiln release that has all of this spec. Its value is set at the release point between the two halves of the build. It is raised with each Kiln feature HT starts to depend on.

**Comparison.** `parse_version(text) -> tuple[int, ...] | None` in the same module: remove a leading `v`, take the leading `\d+(\.\d+)*`, and give the numbers as a tuple. A suffix is ignored (`1.4.0rc1` is `(1, 4, 0)`). Two tuples are compared after the shorter one is padded with zeros. No text that starts with a digit gives `None`. No new dependency.

**Messages.** The steps and the two actions (`u`, `d`) of the "too old" problem are today's (`kiln_check.py:127-147`).

| Case | Title | First line |
|---|---|---|
| `version` is below the minimum | `Kiln {version} is too old for the tuner` | `The tuner needs Kiln {MIN_KILN_VERSION} or newer.` Then today's steps 1 and 2 |
| `GET /api/version` answers 404 | `This Kiln is too old for the tuner` | The same |
| `own_version` is below Kiln's minimum | `The tuner {own_version} is too old for Kiln {version}` | `Kiln {version} needs harness-tuner {min} or newer.` Then `  1. Update the tuner: uv tool upgrade harness-tuner` and `  2. Run the same command again.` |
| A route or a field is missing | `Kiln {version} does not have an API the tuner needs` | `Missing: {names}.` Then `Update Kiln, or update the tuner: uv tool upgrade harness-tuner.` |
| A skill path is missing | `Kiln's skill does not have a file the tuner needs` | `Missing: {path}` (and the count of the others). Then the same line |
| The skill cannot be read at all | `Kiln's skill could not be read` | The `KilnSkillError` text |
| `version` cannot be parsed | No problem. A warning: `Kiln reports version {text}, which the tuner cannot read. Its version was not checked.` | |
| `KILN_HARNESS_TUNER_SKIP_KILN_VERSION_CHECK` is set | No problem. The warning of "A Kiln run from source", below | |
| `/openapi.json` cannot be read | No problem. Today's warning (`UNREADABLE_API_LIST_WARNING`) | |

**The source-tree case.** `own_version == "0+unknown"` means HT is imported from a tree that is not installed (`__init__.py:13-17`). Step 2b is skipped, with the warning: `The tuner runs from a source tree and has no version, so Kiln's minimum tuner version ({min}) was not checked.` An editable install made by `uv sync` has a real version and is checked.

**A Kiln run from source** (architecture ruling 21). A Kiln dev server reports the version committed in `_version.py`, which is the version of its last release (`1.2.1` today; per the Kiln component doc). Step 2a would refuse every such server, also one that has every route. HT reads one environment variable:

```
SKIP_KILN_VERSION_CHECK_ENV = "KILN_HARNESS_TUNER_SKIP_KILN_VERSION_CHECK"     # in onboarding/kiln_check.py
```

- It is set when its value, stripped, is not empty and is not `0`. The name follows HT's other variables (`KILN_HARNESS_TUNER_HOME`, `KILN_HARNESS_TUNER_LOG_LEVEL`).
- When it is set, the comparison of step 2a is not made. HT still calls the version route, shows `version` on the "Kiln" step line, and logs it. The warning is: `KILN_HARNESS_TUNER_SKIP_KILN_VERSION_CHECK is set: Kiln's version ({version}) was not checked against the minimum ({MIN_KILN_VERSION}).`
- It skips nothing else. A 404 from the version route is still the "too old" problem: a Kiln that has this spec has the route. Step 2b still runs. Steps 3 and 4, the contract checks, still run, so a missing route, field or skill path is still caught.
- It is for developers. It is not a command-line option, and `docs/cli.md` does not list it. `.github/CONTRIBUTING.md` documents it (section 7).

**The OpenAPI probes that go.**

| Probe today | After |
|---|---|
| `REQUIRED_APIS`, `RequiredApi`, `missing_apis`, `_is_present` (`kiln_check.py:33-88`) | Removed. The minimum version covers the three APIs, and they are also entries of `contract.py` (section 4) |
| `_version(openapi)` (`:91-96`), the version shown on the "Kiln" step line | Removed. The line shows `version` of the version route |
| `EvalJobDriver.judge_free()` (`job_drives.py:236-263`): reads `EvalJobParams.judge` | The read of the document is removed, and the field is an entry of `contract.py`. The fallback for one eval that refuses a judge-free job (`_judged_evals`, the "V2 judge" text) is not a probe of the document and stays |
| The 404 and 405 probe of `openenv_servers` (`gateway/ops.py:934-939`), and the two shapes of the evals list | Not probes of the document. No change |

## 4. `contract.py`

Two new pure-or-free checks, and one new fixture in today's `contract_preflight`.

```
def missing_api(openapi: dict) -> list[str]                     # names, in list order
async def missing_skill_paths(skill: SkillSource) -> list[str]   # paths, in list order
```

**Routes.** A route is present when its path template is a key of `openapi["paths"]` and that entry has the method. The list is:

| Group | Routes |
|---|---|
| The gateway's | Every route of `gateway.ops.OP_ROUTES` (sibling document, section 7) |
| New in this spec, called by loop code | `GET /api/version`; `POST /api/statistics`; `GET …/run_configs/{run_config_id}/eval_detectability`; `POST …/run_configs/{run_config_id}/noise_check_estimate`; `POST /api/jobs/evals/noise_check`; `GET …/run_configs/{run_config_id}/smell_check`; `POST /api/projects/{project_id}/skills/from_folder`; `GET …/skills/{skill_id}/files`; `GET …/skills/{skill_id}/files/{path}`; the three `/api/model_info/` routes |
| Today's required APIs | `/api/projects/{project_id}/memories`; `/api/jobs/evals/run` |

**Fields.** A field is present when the named schema of `openapi["components"]["schemas"]` has the property. The schema names in the left column are per the Kiln component docs. HT needs these properties:

| Answer or request | Properties |
|---|---|
| `CreateTaskRunConfigRequest`, `EvalJobParams` | `provenance`; `judge` (today's two) |
| `VersionResponse` | `version`, `min_supported_harness_tuner_version` |
| `EvalDetectabilityRow`; `EvalDetectability` | `eval_id`, `eval_name`, `eval_config_id`, `score_key`, `score_type`, `direction`, `n`, `room`, `unscored`, `floor`, `fewest_wins`, `best_case_change`, `interval_wins`; `skipped`, `unread_eval_ids`, `left_out_held_out` |
| `NoiseCheckEstimate`; `NoiseCheckEvalSample` | `estimate_usd`, `drive_usd_per_item`, `judge_usd_per_item`, `distinct_items`, `rows_without_drive_cost`, `rows_without_judge_cost`, `skipped`, `left_out_held_out`, `evals`; `eval_id` and `item_ids` of each entry |
| `NoiseCheckJobResult`; `NoiseRow`; `NoiseCheckPassError` | `estimate_usd`, `spend_usd`, `rows`, `warnings`, `skipped`, `errors`, `flip_rate`; every field of `schemas.NoiseRow` except `baseline_rc_id`; `eval_id`, `message` |
| `SmellCheckResponse`; `SmellDetection`; `SmellCheckModel` | `detections`, `checked`, `unread_tools`, `model`; `smell`, `detector`, `scope`, `fact`, `value`, `reference`, `reference_source`; `release_date_note` |
| `SkillBundleCreateRequest`; `SkillBundleResponse` | `folder_path`, `provenance`; `id`, `name`, `tool_id` |
| `SkillFileList`; `SkillFileEntry`; `SkillFileContent` | `files`, `total_bytes`; `path`, `size_bytes`; `content`, `is_text` |
| `ModelInfoRow`; `ModelInfoProviderEntryRow` (spec one) | The fields of `gateway.models.ModelRow` and `ProviderEntryRow` |

**The statistics operation.** `contract_preflight` (`contract.py:62`) calls the pure statistics route on two fixtures today. It gains a third: `{"operation": "significance_floor", "test": "mcnemar_paired"}`, with the required keys `floor`, `fewest_wins`, `best_case_change`, `interval_wins`, `interval_best_case`, `noise_each_way`, `noise_adjusted_wins`.

**The skill paths.** `KILN_SKILL_PATHS` is the constant of the sibling document (section 8): 93 paths today. `missing_skill_paths` reads each one with `skill.read`, at most 8 at a time, and collects the paths whose read raises `KilnSkillError` with Kiln's "No skill file" text. Any other `KilnSkillError` stops the check at once with the "could not be read" problem. Then it runs `smell_ids` on the index text: no id is reported as a missing path named `references/improving_agents/index.md (the Smells table)`. Kiln's contract test guards the same table from its side: each smell id of the contract list must be in the Smells table as its backticked path (architecture ruling 14; per the Kiln component doc).

## 5. Removals

The order is the build order. "Before" is what must be true first.

| Step | Removed | Before |
|---|---|---|
| 12 | `src/kiln_harness_tuner/skill_installer/`; console script `harness-tuner-skill-installer-mcp` (`pyproject.toml:41`); the code named in 2.1; `tests/test_skill_installer.py` | The two gateway tools and the new `read_skill` pass their tests against the fake |
| 13 | `src/kiln_harness_tuner/model_catalog/`; the option `--no-model-catalog`; the code named in 2.3; `tests/test_model_catalog.py`, `tests/fixtures/model_catalog/` | The three model tools pass their tests against the fake model info routes |
| 14 | The functions named in 2.4 to 2.6; `smells/detectors/`, `smells/thresholds.py`, `smells/model.py` | The Kiln tests that pin HT's values exist (architecture section 7). The callers pass their tests against the fake |
| 15a | `src/kiln_api_mcp/`; console script `kiln_api_mcp` (`pyproject.toml:44`); `packages` loses `src/kiln_api_mcp` (`:61`); the ruff per-file ignore (`:113-121`); `agent_files/claude/` (`.mcp.json`, `settings.json`); the command `harness-tuner-install-agents`, whole (architecture ruling 15): its console script (`pyproject.toml:43`), and `install_agents.install_into`, `_claude_configs`, `_read_object`, `agent_cli_name`, `build_parser`, `main`; `tests/test_kiln_api_tool.py`, `tests/test_kiln_api_server.py` | Nothing. No loop session uses it. The deny rule `mcp__kiln_api_mcp` (`cli.py:1040`) stays: it costs nothing |
| 15b | `agent_files/skills/kiln-api/` (291 files) | No agent text names it (sibling document, section 9) |
| 15c | `agent_files/skills/memory/`, `agent_files/skills/kiln-harness-tuner-code-tool-authoring/`, `agent_files/skills/kiln-task-setup/` | The links are re-pointed. The 36 tests of `tests/test_wrapper_templates.py` are in Kiln, or Kiln has the same tests (functional spec 5.5) |
| 15d | `agent_files/skills/experiment-costing/` | The pre-flight found its port in Kiln's skill, and the planner's skill points at it. Until then the skill is not removed and the planner's pointer is not changed (architecture ruling 22; sibling document, 5.2) |
| 15e, last | `agent_files/skills/kiln-harness-tuner-knowledge/` (78 files); `src/kiln_harness_tuner/knowledge/` (1,334 lines; `python -m kiln_harness_tuner.knowledge`); `.agents/skills/knowledge-maintenance/`; the knowledge entries of `specs/backlog.md` (below); `tests/test_knowledge.py`, `tests/test_knowledge_checks.py` | `SkillReader`, the gateway tool, the five entry files, the re-pointed links, the shared block and both start-up checks work, and the suite passes without the copy. `resolve_link` is in `tests/test_docs.py` |

**Console scripts.** Three go, not two (architecture ruling 15): `harness-tuner-skill-installer-mcp` (step 12), `kiln_api_mcp` and `harness-tuner-install-agents` (step 15a). After the removals two are left: `harness-tuner` and `harness-tuner-gateway-mcp`.

**`harness-tuner-install-agents` is removed whole.** `--dest` is its only form: the option is `required=True` (`install_agents.py:330-335`). The functional spec removes the `--dest` form (5.9), so nothing is left of the command. Its console script, its parser and its `main` go. No command is kept that only prints where Kiln's MCP server is: `docs/cli.md` says it (section 7).

**`install_agents.py`** keeps `install_for_run` and what it needs: a run still installs its skills into the state folder. `expected_files` needs no change; it copies fewer files.

**`specs/backlog.md` stays and loses its knowledge entries** (architecture ruling 18). The knowledge lives in Kiln now. The file has 88 entries, and each has a `Where` field (`knowledge`, `tuner`, `kiln`, or two of them):

- An entry whose `Where` is `knowledge` alone goes (50 today). Before it goes, someone confirms that it is in Kiln's `app/mcp/knowledge_backlog.md` or is not needed.
- An entry about HT's own code stays: `Where` holds `tuner` (28 today). When its `Where` also holds `knowledge`, that word is removed from the field. A `Depends on` title of a removed entry is removed from the entry that stays.
- The other entries (`kiln`, or `knowledge, kiln`: 10 today) are not knowledge entries alone and are not about HT's code. They stay (section 11, point 2).
- `tests/test_backlog.py` stays: it checks the format of the file. `WHERE` loses `knowledge`, and the small texts of the test change with it.
- The file's intro, and the `AGENTS.md` layout line, say "the known gaps and the pending ideas of the tuner's own code".

**Dependencies that lose their last importer** (`pyproject.toml:17-33`):

| Dependency | Last importers | Outcome |
|---|---|---|
| `jq` | `src/kiln_api_mcp/tool.py:8` | Removed |
| `kiln-ai` | `src/kiln_api_mcp/tool.py:9`; `tests/test_knowledge.py:122,373` | Removed |
| `pyyaml` | `knowledge/load.py:15`, `skill_installer/bundle.py:35`, `smells/detectors/long_skill_description.py:10` | Removed |
| `mcp` | Stays: `gateway/server.py`, and the new `kiln_skill.py`. The floor rises (sibling document, 1.2). The comment about `kiln-ai` (`:20-24`) is rewritten |

`pyproject.toml` also loses the ruff exclude of `.agents/skills/**`, and the comments that name the removed parts. `uv.lock` is regenerated.

## 6. Tests

### 6.1 `tests/fake_kiln.py` additions

| Addition | Behaviour |
|---|---|
| `FakeSkillReader` | Sibling document, 1.7 |
| `GET /api/version` | `fake.version = {"version": …, "min_supported_harness_tuner_version": …}`; `None` answers 404 |
| `GET /openapi.json` | The fake's document lists every route and field of section 4 by default. A test removes one |
| `POST /api/statistics`, `significance_floor` | Answers from a table `fake.floors[(test, n)]`. The fake computes nothing: the arithmetic is Kiln's and is tested there |
| `GET …/eval_detectability` | `fake.detectability[rc_id]`: canned rows, `skipped`, `unread_eval_ids`, `left_out_held_out`. It records the `eval_ids` it was asked for |
| `POST …/noise_check_estimate` | `fake.noise_estimate[rc_id]` |
| `POST /api/jobs/evals/noise_check` | Makes a job in the fake's existing job table. `POST /api/jobs/wait` returns it with `fake.noise_result[rc_id]`. It records `max_usd`. A test can make it fail or hold |
| `GET …/smell_check` | `fake.smell_check[rc_id]`; it records `as_of` |
| `POST …/skills/from_folder` | Reads the folder, makes a skill row and its files in the fake, answers the id and tool id. `fake.bundle_errors` makes it answer 422 with a list. It does not repeat Kiln's folder rules |
| `GET …/skills/{id}/files`, `…/files/{path}` | From the fake's skill files. A file marked binary answers as Kiln does |
| `GET /api/model_info/models`, `/model_details`, `/providers` | From `fake.model_rows`, with real paging by `limit` and `offset`, and the `include_not_available` filter |

**The packaging smoke test.** `tests/packaging/fake_kiln_server.py` is a stdlib HTTP server that answers GET only. The installed wheel now calls the version route and reads 93 skill paths at start-up, so the server gains: `GET /api/version`; the routes of section 4 in its `/openapi.json`; and `POST /mcp`, answered by hand as plain JSON over HTTP/1.1 with a `Content-Length`: `initialize` gets a result with the client's protocol version, `notifications/initialized` gets HTTP 202, `tools/call` for `kiln_skill` gets one text block (the fixture index for the index path, a short stand-in text for any other contract path), and `tools/list` gets the one tool. A stdlib server of this shape was tried with the SDK client of `mcp` 1.30.0, and the read worked. `smoke_installed_wheel.py` changes `COMMANDS` (two console scripts are left), `WHEEL_FILES`, `WHEEL_PACKAGES`, the `kiln_api_mcp` checks (`:63-87,331`) and drops `--no-model-catalog` (`:435`).

### 6.2 The fate of today's tests

| File (tests) | Fate |
|---|---|
| `test_knowledge.py` (108), `test_knowledge_checks.py` (103) | Go, last. Kiln's `skill_checks` tests cover the content and the checker. The tests that bind HT's code to knowledge text become contract ids or audit review items (8.2) |
| `test_backlog.py` (26) | Stays: `specs/backlog.md` stays (section 5). `WHERE` loses `knowledge`, and the small test texts change with it |
| `test_smells.py` (44) | Rewritten against the fake smell check and `FakeSkillReader`. The tests of each detector and each limit go: Kiln pins the same values |
| `test_baseline_review.py` (55) | Stays, on `FakeSkillReader` |
| `test_detectability.py` (30) | The arithmetic tests (floors, Wilcoxon, intervals, bootstrap) go: their pinned values move to Kiln's tests, which name them. The tests of `build_rows`, `assess`, the refusal, the lines and `run_detectability_check` stay, on canned rows |
| `test_noise.py` (13) | The tests of the sample, the clone, the judge copy, the comparison and `noise_adjusted_wins` go to Kiln. New tests: the estimate skip; the train-set guard (an id outside HT's train set, and no train set file: no job is started and `skipped` has the text of 2.6); the budget skip; `max_usd`; the spend event; a quota error; the rows as `NoiseRow`, with a null `noise_adjusted_wins` and with a `rejudge_note` beside re-judged counts; a failed job and a cancelled job book no spend |
| `test_stop_rules.py` (46) | Stays. `noise_flip_rate` reads the same rows |
| `test_gateway_model_info.py` (27) | Rewritten: the status, both `include_not_available` values, paging over more than 200 rows with blocked entries, `total`, the provider count with a policy |
| `test_model_catalog.py` (41), `test_skill_installer.py` (45), `test_kiln_api_tool.py` (73), `test_kiln_api_server.py` (19) | Go. From `test_skill_installer.py`, the cases "outside scratch", "the root itself", "a file" and the export destination cases are written again in `test_gateway.py`. New there: an export of a skill with a binary asset writes the text files only, and `skipped` names the asset |
| `test_wrapper_templates.py` (36) | Moves to Kiln, or goes when Kiln has the same tests |
| `test_onboarding_kiln_check.py` (46) | Rewritten: each row of the message table of section 3, the source-tree case, `parse_version`, the order of the four steps. With `KILN_HARNESS_TUNER_SKIP_KILN_VERSION_CHECK` set: a Kiln below the minimum passes step 2a with the warning; step 2b still stops a tuner that is too old; a missing route still stops at step 3; a missing skill path still stops at step 4; a 404 from the version route is still "too old". With the value `0` or empty, step 2a runs |
| `test_install_agents.py` (46) | The cases of the removed command go: `--dest`, the parser, `main`, `agent_cli_name` and `kiln_api_mcp`. The run-install cases stay, with the new file set |
| `test_prompt_text.py` (8) | `read_skill` cases use the fake's skill files |
| `test_gateway.py` (89), `test_cli.py` (154), `test_cli_reference.py` (18), `test_docs.py` (55), `test_job_drives.py` (20), the three dispatcher files (124, 39, 40) | Updated where they name a removed part: the catalogue, the staging sweep, the installer server, tool lists, console scripts, the `judge_free` probe, the layout blocks |
| `test_integrity.py`, `test_judge_copy.py`, `test_reference_check.py`, `test_generality.py`, `test_model_preflight.py` | Stay. A test that writes a skill folder on disk writes it into the fake |

## 7. Docs and command line

| File | Change |
|---|---|
| `docs/cli.md` | The command table (`:7-18`) loses three commands: `kiln_api_mcp`, `harness-tuner-skill-installer-mcp` and `harness-tuner-install-agents`; "installs all five" becomes two. `--no-model-catalog` (`:121`) moves to "Removed flags". The section `harness-tuner-install-agents` (`:140-183`) is removed. One paragraph takes its place: for work by hand, connect Kiln's own MCP server, which carries Kiln's skill. "Internal commands" (`:185-210`) keeps the gateway only |
| `docs/install.md` | Section 2 (`:84-145`): the executables, what a run starts, no `kiln_api_mcp`. Section 3 (`:165-230`): the minimum Kiln version, from `MIN_KILN_VERSION`. "The Kiln check at start-up" (`:231-358`): the four steps and each message of section 3. "Where the tuner keeps its files" (`:869-953`): no `model_catalog.json` |
| `docs/architecture.md` | Section 5.1 and 5.2: the checks call Kiln; what HT keeps. Section 12: the skill installer is two gateway tools; the gateway reads Kiln's skill. Section 13: the layout. Section 14, item 1: `mcp` client code in one module. Section 15: the fakes. Section 17.1 (the catalogue) is replaced by a short "Model information" section. Sections 18.1 to 18.4 are replaced by "Kiln's skill, the entry files and the smell check" |
| `docs/agents.md` | The intro and the tables (`:13-58`): each role's entry file is `references/knowledge-entry.md` of its skill; `kiln_skill` in the tool lists; no `kiln-api`, `experiment-costing`, `kiln-task-setup` |
| `docs/agent-cli.md` | Sections 6, 7, 10 and 11: no skill installer server; the two tools are the gateway's |
| `docs/limitations.md` | "Containment": the installer items; a new item: a loop agent can read all of Kiln's skill. "The Kiln API reference can go stale" (`:400-405`) is removed. A new item: the knowledge changes with the Kiln version |
| `docs/how-it-works.md`, `docs/concepts.md` | The sentences that name the knowledge skill or the detectors in HT's code |
| `docs/costs.md` (`:12`), `docs/your-own-task.md` (`:760`), `docs/limitations.md` (`:438`) | The `experiment-costing` link points at Kiln's file |
| `AGENTS.md` | The layout block loses `knowledge/`, `model_catalog/`, `skill_installer/`, `src/kiln_api_mcp/` and `.agents/skills/`. Its `specs/` line keeps `backlog.md`, as "the known gaps and the pending ideas of the tuner's own code". The working rule "The knowledge system is the place for general knowledge" becomes: general knowledge is fixed in Kiln's skill, in the Kiln repository. The rule "Nothing measured on the target goes in `agent_files/`" stays |
| `.github/CONTRIBUTING.md` | The layout lines (`:69-73`) and the knowledge rule (`:92-96`). New: how to run the tuner against a Kiln from source, with `KILN_HARNESS_TUNER_SKIP_KILN_VERSION_CHECK=1`, and what the variable does not skip (section 3) |
| `README.md` | The layout lines, if any name a removed part |

`tests/test_docs.py` and `tests/test_cli_reference.py` check the layout blocks, the links and the option table. They are updated in the same change as each doc.

## 8. The audit

A person or an agent reads the switched HT against this table. Each row passes or fails. "Role skill" paths are under `agent_files/skills/`. "Kiln:" paths are read from the Kiln build of the demo run.

### 8.1 The checklist

| # | Concept | Where it lives after the switch | How the auditor checks it |
|---|---|---|---|
| 1 | Tune on train, confirm on val, never read test | Code: `gateway/trainset.py`, the gateway's train-only reads. Every train-side prompt template. Kiln: `references/knowledge/train_val_test.md` | `tests/test_gateway.py` passes. Read each template for the three bans. Read Kiln's file for a sentence that lets an agent read val or test |
| 2 | Val is read by summary numbers only | `…-promote/SKILL.md` hard rules; `agents/promote_best.md`; `get_val_summary` | Read the promote rule. Confirm that `kiln_skill` is the only new tool of `promote_best` and `report_writer` |
| 3 | The promotion rule | Code: `orchestrator.decide_single_candidate`. `…-promote/SKILL.md` "The comparison" | The orchestrator tests pass. The promote skill does not send the role to a Kiln procedure file for the rule |
| 4 | One change per experiment; new objects only; the parent is never changed | `…-experiment-build/SKILL.md` hard rules. Kiln: each lever's "How to change it" and "Limits" | Read the 7 levers for a step that edits an object in place |
| 5 | Provenance is stamped at creation | `agents/create_experiment_rc.md`; the build skill; `contract.py` (`provenance`); the install tool | Read the template. In the demo run, each run config and skill the builder made has `provenance` |
| 6 | No train item value, and no eval or judge text, in a prompt, skill or tool | Code: `generality.py`, `integrity.py`, `judge_copy.py`, now on `read_skill` of 2.2. The build skill hard rules. Kiln: lever "Limits" | Their test files pass. One test proves that a reference file of a skill, served by the fake, reaches the checkers |
| 7 | Hard limits hold, whatever a measurement says | Kiln: `references/improving_agents/index.md`, "How to read these documents". The entry files cite that section | The section holds "No measurement overrides a hard limit". Each entry file names the section |
| 8 | Only allowed models | Code: `model_policy.py`, `create_run_config`, `run_task`, `require_policy`. `gateway/model_info.py` | `tests/test_model_policy.py` passes. The rewritten model info tests show `blocked_by_policy`. The map row for the three model docs names HT's tools |
| 9 | Cost comes from recorded usage | The planner's skill and the costing file in Kiln. Code: `budget.py`; the noise spend of 2.6 | Read the costing file for the method. The noise spend test passes |
| 10 | The memory conventions, and who may write which record | Kiln: `references/knowledge/memory.md` and `memory_formats/`. Code: `memory_schema.py`. Each role skill's own write rules | Each role skill still says what the role writes. Compare the strings of the five format files with `memory_schema.py` by hand |
| 11 | Val readers write nothing | Code: `READ_ONLY_ROLES`, `ROLE_OPS` of the two val readers | `ROLE_OPS` of `promote_best` and `report_writer` holds no write and no bundle tool |
| 12 | One attempt per idea; the builder does not edit the eval that measures it | The build skill hard rules. `ROLE_OPS["create_experiment_rc"]` has no eval write | Read the rules. Read Kiln's eval playbooks for a step that tells the reader to change a judge during an experiment; rule 5 of the shared block must cover it |
| 13 | The task's default run config is never changed | The build and promote hard rules. No gateway tool patches the task | `OP_ROUTES` holds no `PATCH` of a task |
| 14 | The verdict words | `…-experiment-analysis/SKILL.md` "The judgment"; the entry file of the planner | Read both. Read Kiln's index and the noisy-eval playbook for other words used for the same verdicts |
| 15 | The loop never asks a person | The planner's hard rule; rule 1 of the shared block | The block is in the 7 prompts (a test). Count "ask the user" in the Kiln files that the contract names; rule 1 must fit each case |

### 8.2 The other checks

Each test that binds HT's code to knowledge text, and cannot run offline after the switch, is a review item here (architecture ruling 19). The functional spec names three; the sibling document (section 9) lists the others that were found. The lever ids are not a review item: they are in Kiln's contract test.

| Check | How |
|---|---|
| Every role's first instruction names a file that exists | For each template in `agents/`, the first file it names is in the installed agents folder, or is in `KILN_SKILL_PATHS` |
| No role prompt names a removed skill | `grep` the templates and the role skills for `kiln-harness-tuner-knowledge`, `kiln-api`, the `memory` skill, `kiln-harness-tuner-code-tool-authoring`, `experiment-costing`, `kiln-task-setup`, `skill_installer`. A test does the same |
| Review item: `spending-the-budget` against the planner's input fields | Read the "Situation" section of the Kiln playbook. Each input it names must be a field of `schemas.BatchPlanInput`, or the planner's skill must say which field carries it |
| Review item: the output-mode lever against Kiln's modes | Each value of Kiln's `StructuredOutputMode` is in "What it is" of `references/levers/output_mode.md` |
| Review item: the output-mode lever against the code | The lever says that a change of the mode is a model-level swap, that a screen and a probe can set it, and that a probe cannot set a model. Compare with `items.SWAP_KEYS`, `schemas.SCREEN_ONLY_OVERRIDES` and `schemas.ProbeCheck` |
| Review item: the output-contract playbook against Kiln's modes | The section "The output modes, ranked" of `references/improving_agents/playbooks/output-contract-not-met.md` names each value of `StructuredOutputMode` except `unknown` |
| Review item: the val-rejection playbook | The planner's skill quotes each reason line that `memory_schema.rejection_note` writes (a test). The Kiln playbook names the same five cases |
| Review item: the new-tool lever and the wrapper templates | `references/levers/new_tool.md` sends its reader to the wrapper templates: it names `references/knowledge/code_tool_authoring.md` or a file of `references/knowledge/code_tool_wrappers/` |
| Review item: the memory vocabulary | Kiln's `references/knowledge/memory.md` and its format files state the rejection stamp that code appends, and the spend slot of an experiment record, in words that fit the analysis skill's `bundle cost` |
| Review item: the two hand-kept tables | The five rows of the smell table match the `checked` list of a live smell check. The lever table test passes |
| The map | For each of the 27 docs, the tool does what the doc's endpoint does |

## 9. The demo run

**The build it needs.** A Kiln build with spec one merged and with steps 2 to 9 of this spec, whose version is at least `MIN_KILN_VERSION` and whose `min_supported_harness_tuner_version` is at most HT's version. A Kiln dev server reports the version committed in `_version.py`, which is below the minimum today. The demo run does not set `KILN_HARNESS_TUNER_SKIP_KILN_VERSION_CHECK` (section 3): the version check is part of the proof. So use a packaged build, or a build whose `_version.py` holds the release version. HT is installed from the switched branch as a wheel (`uv tool install`), not run from a source tree, so the second version check runs. An OpenRouter key is in Kiln: the demo's baseline calls its model through OpenRouter.

**The command.**

```
harness-tuner --demo-project --budget-usd 20 --timeout-mins 60 --noise-check 5
```

`--noise-check 5` is not a default. It is here so that the run calls the noise estimate and the noise job. Every other new call is on the default path.

**Pass conditions.** All must hold:

| # | Condition | Where to look |
|---|---|---|
| 1 | The four start-up steps pass, and the step line shows Kiln's version | The terminal |
| 2 | The run ends by its own stop rule, its budget or its time limit, not by an error | The exit code and the closing block |
| 3 | No error from a missing file: no `knowledge_unreadable` event, and no `kiln_skill` call that ends in "No skill file" for a path that an HT file named | `wave_log.jsonl`; the transcripts |
| 4 | No error from a missing tool: no "not available to the … role" answer, and no hook block | The transcripts; the hook's messages |
| 5 | No refused call that the switch caused: no 404 or 422 from a new route | `kiln-harness-tuner.log` |
| 6 | The detectability event, the `smell_detections` event and the `noise_check` event are in the log, and the noise check has rows | `wave_log.jsonl` |
| 7 | After the noise job, the project holds no object whose name starts with `NOISE-CHECK ` | The Kiln project |
| 8 | A builder session read a lever through `kiln_skill`. Record whether one called `install_skill_bundle`; a run may not need a skill | The transcripts |
| 9 | The report is written | The reports folder |

The run proves the mechanics. It does not prove quality: runs differ each time (functional spec section 7).

## 10. Accepted limits

Each of these is settled. Nothing here waits for a decision.

1. **HT's held-out rule by tag name is not in Kiln's train helper** (ruling 17). The noise check is guarded: step 4 of 2.6 skips it when a sampled item is not in HT's train set. Detectability counts can differ from today's on a task that has such tags (2.5).
2. **A skill export loses binary assets** (ruling 16). The export does not copy one, and `skipped` names it. A builder that clones such a skill gets a clone without it.
3. **`has_thinking_levels` of a model list row can be true because of an entry that the policy drops** (ruling 20). `get_model_details` is exact.
4. **A cancelled or failed noise job reports no spend** (ruling 8). HT books nothing for it, as today.
5. **`contract.py` does not list every older route of loop code** (results, jobs wait, runs and others). They are older than `MIN_KILN_VERSION`, and the version check covers them. The list holds the gateway's routes, the routes of this spec and today's required APIs.
6. **With the skip variable set, the Kiln version is not compared** (ruling 21). The contract checks still catch a missing route, field or skill path. They do not catch a route that is present with an older meaning.

## 11. Open points

1. **The costing port** is not in Kiln's skill yet (ruling 22; sibling document, section 11). Step 15d waits for the pre-flight.
2. **The backlog entries that are about Kiln.** Ruling 18 names two groups: knowledge entries go, and entries about HT's own code stay. Ten entries of `specs/backlog.md` are in neither group (`Where` is `kiln`, or `knowledge, kiln`). Section 5 keeps them. The owner can move them to Kiln's backlog.

## 12. Not verified

- The names marked "per the Kiln component doc" were read from the two sibling drafts. Those drafts can change, and no Kiln code exists yet.
- That each schema of section 4 is in Kiln's OpenAPI document under the name given. A job result may not be a named schema of the document; then its fields are checked on the first live result instead.
- That `model_info_models(include_deprecated=True)` lists every entry that Kiln's `ready_model_count` counts.
- `MIN_KILN_VERSION`: no Kiln release has this spec yet.
- That `reconcile.py` needs no change when the noise job's task runs are deleted. Its spend is booked from `spend_usd`.
- Which old spec files under HT's `specs/projects/` link an entry of `specs/backlog.md` that goes, and whether `tests/test_docs.py` checks them.
- That `ctx.train_set_path` is set on every real run, so that the train-set guard of 2.6 has a file to load.
- The split of each rewritten test file into "goes" and "stays", test by test. The rule is in 6.2; the counts are whole files.
- The line counts of removed source (taken from the fact files, not recounted).
