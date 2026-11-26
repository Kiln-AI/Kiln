---
status: draft
---

# Component: Kiln smell check, skill bundles, version, skill text and contract test

This document gives the detail for functional spec sections 3.6, 3.9, 3.10 and 4. The [architecture](../architecture.md) fixes the decisions; this document changes none of them. Section 9 lists what does not fit.

Words and sources:

- **HT** is harness-tuner at commit `b49f159`. `HT:` before a path means `src/kiln_harness_tuner/` in that repository. `HT-tests:` means its `tests/` folder.
- **The build branch** is `claude/kiln-mcp-server-impl`, read at commit `5522a7b`. Its skill tree is `app/mcp/kiln_mcp_server/skill/`. Paths in it can still move (functional spec, section 2).
- A value marked **Proposed** is a call made here. The owner can overrule it.

## 1. Placement and shared rules

| Part | File (all under `app/desktop/studio_server/` unless a full path is given) |
|---|---|
| Smell check: limits, the five checks, the collection of inputs | `smell_check.py` |
| Smell check: route | `smell_check_api.py`, with `connect_smell_check_api(app, *, model_info)` |
| Smell check: response models | `api_models/smell_check_models.py` (the repository's rule for desktop models) |
| Skill bundle: folder rules, staged write, file list and read | `skill_bundle.py` |
| Skill bundle: routes and their models | `skill_api.py`, beside the existing skill models (`SkillBundleResponse` extends `SkillResponse`, which is there) |
| All failures of a skill name at once | `libs/core/kiln_ai/utils/validation.py`: new `skill_name_errors` (section 3.3; outside architecture 2.1, see 9.2) |
| Version route and model | `version_api.py`, with `connect_version_api(app)` |
| The HT minimum | `compat.py` |
| Tests | `test_smell_check.py`, `test_smell_check_api.py`, `test_skill_bundle.py`, `test_skill_api.py` (added cases), `test_version_api.py` |

Rules that come from `AGENTS.md` and `.agents/skills/kiln-conventions/`:

- `smell_check.py` and `skill_bundle.py` are service modules. They take loaded objects and plain values. They raise their own errors and never `HTTPException`. The route maps each error to a status.
- Disk work runs in a worker thread, not on the event loop: `asyncio.to_thread`, or `kiln_ai.utils.torn_read.to_thread_retrying_torn_read` for reads of project files.
- Each route has `openapi_extra` (section 6) and a docstring. The first sentence of the docstring is the route's row in the skill's API catalogue.
- `connect_smell_check_api` and `connect_version_api` are called from `desktop_server.make_app()` before `connect_webhost`. Any lock or service object is created inside a `connect_*` function, not at module level.
- The GET routes write nothing in the project folder. With git sync in dev mode, a GET that leaves the repository changed answers 500.

## 2. Smell check

### 2.1 Route

`GET /api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}/smell_check`, tag `Run Configs`, summary `Check Run Config For Smells`.

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `as_of` (query) | `date` (`YYYY-MM-DD`) | the server's local date today | The date the model's age is counted to. HT passes the start date of its run (`HT:smells/run.py:493`), so the answer is the same for the whole run |

No parameter changes a limit (functional spec 3.6).

### 2.2 Response models

`SmellCheckResponse`:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `as_of` | `date` | — | The date that was used |
| `detections` | `list[SmellDetection]` | `[]` | In the order of the checks in 2.4; inside one check, in the order of the run config's tools |
| `checked` | `list[SmellCheckLimit]` | — | Always the five checks, in the order of 2.4, also when a check could not measure anything |
| `unread_tools` | `list[str]` | `[]` | The tool ids whose definition could not be read, in the run config's order |
| `model` | `SmellCheckModel \| None` | `None` | `None` when the run config names no model (an MCP run config) |

`SmellDetection`. The names and types are those of `Detection` (`HT:schemas.py:1753`), so `Detection.model_validate(row)` works unchanged. `eval_id` is left out: it is always `None` for these five.

| Field | Type | Meaning |
|---|---|---|
| `smell` | `str` | The id of the smell document |
| `detector` | `str` | The check id. HT matches a review to a detection on (`smell`, `detector`) |
| `scope` | `Literal["harness"]` | Always `harness` |
| `fact` | `str`, `max_length=300` | One sentence with its numbers. No word of judgement |
| `value` | `int` | What was measured |
| `reference` | `int` | The limit |
| `reference_source` | `str` | Where the limit comes from |

`SmellCheckLimit`: `smell: str`, `detector: str`, `reference: int`, `unit: Literal["characters", "tools", "months"]`, `reference_source: str`.

`SmellCheckModel`:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `model_name` | `str` | — | The run config's `model_name` |
| `model_provider_name` | `str` | — | The run config's `model_provider_name` |
| `display_name` | `str` | — | The name in Kiln's model info; the model id when model info does not have the model |
| `release_date` | `date \| None` | `None` | `None`: not known |
| `release_date_estimated` | `bool` | `False` | As model info reports it: the date came from a match on the name only. The smell document tells the reader to state this |
| `release_date_note` | `str \| None` | `None` | Set when `release_date` is `None`. It starts with `release date not known` (2.5) |

### 2.3 The limits

Constants in `smell_check.py`. Each has a comment with its source, and a `<NAME>_SOURCE` string (port of `HT:smells/thresholds.py`). The numbers are HT's. The source strings are HT's with "the tuner" changed to "Kiln", as the functional spec's table says.

| Constant | Value | `_SOURCE` string |
|---|---|---|
| `LONG_PROMPT_CHARS` | `200_000` | `a Kiln default, about 50,000 tokens; no published limit for a system prompt is known` |
| `LONG_TOOL_DESCRIPTION_CHARS` | `4_096` | `Claude Code cuts the description of a tool that loads up front at this length (Claude Code documentation, read 2026-11-13)` |
| `LONG_SKILL_DESCRIPTION_CHARS` | `1_024` | `the maximum length of a skill description in the Agent Skills specification (read 2026-11-13)` |
| `MANY_TOOLS` | `40` | `a Kiln default; not a measured optimum` |
| `OLD_MODEL_MONTHS` | `8` | `a Kiln default; no published value is known` |

### 2.4 The inputs and the five checks

The inputs are collected once (port of `_collect`, `HT:smells/run.py:454`, and of `rc_texts` and `rc_prompt_text`, `HT:prompt_text.py`). HT reads them over REST and from disk. Kiln reads its own datamodel.

1. **The run config.** The handler loads the task with `task_from_id` and the run config with the existing `task_run_config_from_id` (see 9.3). A fine-tune run config id resolves as it does today.
2. **The prompt text**, `str | None`:
   - properties of type `mcp`: the empty string (HT: no prompt id);
   - the run config has a frozen `prompt`: `prompt.prompt`, then `prompt.chain_of_thought_instructions` when it is set, joined with `"\n"`;
   - else: `prompt_builder_from_id(properties.prompt_id, task)`, then `build_prompt(include_json_instructions=False)` and `chain_of_thought_prompt()`, joined the same way. This is what the route `gen_prompt` does;
   - any error while it is built: `None`. HT's extra reads of the property keys `prompt`, `system_prompt` and `instructions` are not ported: Kiln's run config has no such keys.
3. **The tool ids**: `properties.tools_config.tools` in order, or none.
4. **The tool definitions.** For each tool id that does not start with `kiln_tool::skill::`, in order: `tool_from_id(tool_id, task)` then `await tool.toolcall_definition()`, as the route `tools/{tool_id}/definition` does. Keep `tool_id`, `function.name` and `function.description`. On any exception the id goes to `unread_tools`. A skill id is never resolved this way. An OpenEnv tool resolves only during an episode (docstring of `tool_from_id_and_project`), so it is normally unread.
5. **The skills.** For each attached `kiln_tool::skill::<id>`: `Skill.from_id_and_parent_path(id, project.path)` and `skill.skill_md_raw()`. If one skill is missing or its `SKILL.md` cannot be read as UTF-8, the whole skill input is `None` (HT: `RcText.skills is None`; see 9.9).
6. **The model**: section 2.5.

Steps 1, 2, 3 and 5 run in one worker thread call. Step 4 and step 6 are awaited on the event loop.

The checks are pure functions over these inputs, in this fixed order. `value` is compared with `>`: a value equal to the limit gives no detection.

| # | `detector` | `smell` | What it measures (HT file under `HT:smells/detectors/`) | `fact` |
|---|---|---|---|---|
| 1 | `long_prompt` | `very-long-prompt` | `len()` of the prompt text of step 2. `None`: silent. One detection at most (`long_prompt.py`) | `The system prompt has {value:,} characters. The reference is {reference:,}.` |
| 2 | `long_tool_description` | `very-long-tool-description` | `len()` of each definition's `description`, when it is a string. One detection for each tool over the limit. The name is `name`, else `tool_id`, else `?`, cut at 64 characters (`long_tool_description.py`) | ``The description of the tool `{name}` has {value:,} characters. The reference is {reference:,}.`` |
| 3 | `long_skill_description` | `very-long-skill-description` | `len()` of the `description` in the front matter of each attached skill's `SKILL.md`, read by `skill_description()`. Not the `description` of `skill.kiln`. Skill input `None`: silent. The name is the skill's `name`, else its id, cut at 64 (`long_skill_description.py`) | ``The description of the skill `{name}` has {value:,} characters. The reference is {reference:,}.`` |
| 4 | `many_tools` | `too-many-tools` | The count of distinct tool ids of step 3 that do not start with `kiln_tool::skill::`. A skill is not a tool here: Kiln gives every skill through one skill tool. A repeated id counts once. An unread tool still counts (`many_tools.py`) | `The run config attaches {value:,} tools, not counting skills. The reference is {reference:,}.` |
| 5 | `old_model` | `old-model` | The whole calendar months from the release date to `as_of`. It fires when `add_months(release_date, 8) < as_of`. No model or no date: silent (`old_model.py`) | `The run config's model, {display_name[:80]} ({model_name[:80]}), was released on {release_date}, {value} months before {as_of}. The reference is 8 months.` |

Ported helpers, unchanged: `skill_description(skill_md) -> str | None` (first line `---` after `strip()`, the next `---` line, `yaml.safe_load`, a string `description`; else `None`); `add_months(d, months)` (the day is clamped to the last day of the month); `whole_months(start, end)`. Check 5's sentence differs from HT's ("The baseline's model … before this run"), because the route has no baseline and no run (see 9.7). `checked` is built from the same table: one `SmellCheckLimit` for each row.

### 2.5 The model's release date

Port of `_model_facts` (`HT:smells/run.py:499`), with Kiln's model info in place of HT's catalogue (architecture decision 10).

1. Properties that are not `kiln_agent`: `model` is `None`.
2. The smell check asks the model info service of spec one for the model. On the build branch that is `ModelInfoService` in `services/model_info/service.py`. It gets one new method (**find the right place to integrate**, the module can still move):

   ```
   async def release_facts(self, model_id: str) -> ModelReleaseFacts
   # ModelReleaseFacts: in_model_list: bool, display_name: str | None, release_date: str | None,
   #                    release_date_estimated: bool, models_dev_state: str, models_dev_detail: str | None
   ```

   It calls `self._kiln_model_list()`, `await self._models_dev.current()` and `self._catalog(...)`, then `catalog.model(model_id)`: an exact match on Kiln's model id, as HT does. It does not call the provider list.
3. "Waits under that module's own rules" is `ModelsDevCache.current()`: with no data it starts one load and waits at most its `wait_secs` (15 seconds). The smell check adds no fetch and no wait of its own. So a first call on a machine with no network can take 15 seconds; HT's client timeout must allow it.
4. One service per app. `connect_model_info_api` builds the service today and keeps it private. It returns the service, and `make_app` passes it to `connect_smell_check_api(app, model_info=...)` (see 9.4).
5. The date string is parsed with `date.fromisoformat`; a bad string is "not known" (HT `_iso_date`).
6. `release_date_note`, exact texts:
   - the model is not in the model list (a fine-tune, a custom model): `release date not known: the model is not in Kiln's model list`;
   - model info has no models.dev data (`ModelsDevSnapshot.data is None`): `release date not known: Kiln's model info has no data from models.dev ({detail})`;
   - else: `release date not known: models.dev has no release date for this model`.

### 2.6 Errors

| Case | Status | Text |
|---|---|---|
| Unknown project, task or run config | 404 | The existing texts of `project_from_id`, `task_from_id` and `task_run_config_from_id` |
| `as_of` is not a date | 422 | Kiln's standard validation answer, which names `as_of` |
| A tool, a skill or the prompt cannot be read | 200 | Not an error: `unread_tools`, or a silent check |

### 2.7 Tests

`test_smell_check.py`, ported by name from `HT-tests:test_smells.py`, with the same boundary values: `test_long_prompt_is_silent_at_the_reference`, `test_long_prompt_reports_above_the_reference_with_value_and_source`, the same pair for `long_tool_description`, `long_skill_description` and `many_tools`, `test_many_tools_counts_neither_skills_nor_a_repeated_id`, `test_a_detection_names_each_tool_and_each_skill_over_the_reference`, `test_a_detector_is_silent_when_the_text_cannot_be_read`, `test_skill_description_reads_the_front_matter`, `test_a_detection_fact_has_no_judgement_word`, `test_every_registered_detector_has_a_unique_id`, `test_every_threshold_has_a_source_comment`, `test_old_model_fires_after_eight_months`, `test_old_model_is_silent_at_exactly_eight_months`, `test_old_model_is_silent_without_a_date`, `test_old_model_clamps_the_day_at_month_end`, `test_old_model_cuts_a_long_name`.

Pinned values of the old-model tests: released 2025-01-10, `as_of` 2025-09-11 gives 8; 2025-09-10 gives nothing; 2026-03-09 gives 13; released 2025-05-31, `as_of` 2026-02-01 gives 8; `add_months(2025-06-30, 8)` is 2026-02-28 and `add_months(2023-06-30, 8)` is 2024-02-29; released 2025-06-30 gives nothing on 2026-02-28 and 8 on 2026-03-01; released 2024-05-13, `as_of` 2025-02-14 gives 9.

`test_smell_check_api.py`, with a project on disk and a fake model info service:

- `test_run_detectors_reads_the_baseline_and_emits_the_detections` (a long prompt and one long tool description; a skill is never resolved as a tool);
- `test_run_detectors_counts_the_attached_tools_whose_definition_is_unread`;
- `test_run_detectors_skips_when_the_run_config_cannot_be_read`, here as a 404;
- `test_collect_reads_the_release_date_from_the_catalogue`; `test_old_model_is_silent_when_the_catalogue_has_no_date` (four cases: no data, a model it lacks, a bad date, no date), each with its `release_date_note`; `test_a_run_config_without_a_model_gives_no_model_facts`;
- new: `as_of` defaults to today; a bad `as_of` is 422; `checked` has the five rows; an MCP run config gives no detection; one unreadable skill silences check 3 only; each detection validates as HT's `Detection` field set; the project folder is unchanged after the call.

Not ported, because they test HT's loop: the events, the unknown-smell filter, trace stats, `ensure_detections`, the planner input and the report.

## 3. Skill bundle: create from a folder

### 3.1 Route and models

`POST /api/projects/{project_id}/skills/from_folder`, tag `Skills`, summary `Create Skill From Folder`. The docstring says that Kiln reads the folder on the machine that runs Kiln.

`SkillBundleCreateRequest`:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `folder_path` | `str`, 1 to 4,096 characters | — | An absolute path on the machine that runs Kiln |
| `provenance` | `KilnArtifactProvenance \| None` | `None` | As on `POST …/skills`: optional; when given, `origin` is required, `notes` has at most 2,000 characters, and each id of `derived_from_ids` is a skill of the project |

`SkillBundleResponse(SkillResponse)`: every field of `SkillResponse` (`id`, `name`, `description`, `is_archived`, `created_by`, `created_at`, `provenance`), plus `tool_id: str`, which is `build_skill_tool_id(skill.id)` (`kiln_tool::skill::<id>`). HT's tool answer (`skill_id`, `skill_name`, `tool_id`) is filled from `id`, `name` and `tool_id`.

### 3.2 Order of the checks

**Before any read of the folder** (nothing on disk outside the project is touched):

1. The request body is parsed. A bad body or a bad `provenance` shape is Kiln's standard 422.
2. `project_from_id`. Unknown: 404.
3. `validate_provenance_or_400(provenance, None, Skill, project.path)`. An unknown parent is the existing 400. The self id is `None`: the id is not minted yet, and a new id cannot be its own parent.
4. Rule F1 below: the path is absolute. This reads only the string.

**Then the folder**, in one worker thread call, under one `threading.Lock` that `connect_skill_api` creates. The lock covers the name check and the write, so two calls in one Kiln process cannot both take one name.

- Rules F2 to F7 read names, types and sizes only (`os.scandir`, `os.lstat`). No file is opened.
- File content is read after that, each file once, into memory. Only a regular file within F5 is opened, in the order `SKILL.md`, `references/**`, `assets/**`, and reading stops when the bytes read pass 2 MiB. Where the platform has it, a file is opened with `os.O_NOFOLLOW`. The bytes in memory are the bytes that are checked and the bytes that are written.
- A stray entry at the root is reported by name and never opened or walked. So a wrong path, such as a home folder, costs one folder listing.

### 3.3 The folder rules

Port of `validate_bundle` and `parse_skill_md` (`HT:skill_installer/bundle.py:99-284`). Every rule runs and every failure is collected, except where a rule says "stop". HT's location rule (the folder is inside the agent's scratch folder) is not ported: it stays in HT's gateway (functional spec 5.6). HT's two argument rules are replaced by Kiln's provenance rules (3.2).

| # | Rule | Error text |
|---|---|---|
| F1 | `folder_path` is absolute. Stop | `folder_path must be an absolute path on the machine that runs Kiln` |
| F2 | The resolved path is a folder. Stop | `folder_path is not a folder: {path}` |
| F3 | The root holds only `SKILL.md` (a regular file), `references` and `assets` (real folders, not symlinks). One error for each other entry; after 20, one line with the count | `unexpected entry at the folder root: {name!r}. Allowed: SKILL.md (a file), references/ and assets/ (folders). Kiln writes skill.kiln itself` · `and {n} more unexpected entries at the folder root` |
| F4 | No symlink under `references/` or `assets/`, and every entry is a folder or a regular file. A symlinked folder is not entered | `symlinked folder not allowed: {rel}` · `symlinked file not allowed: {rel}` · `not a regular file: {rel}` |
| F5 | Each file has at most 524,288 bytes (512 KiB) | `file too large: {rel} is {size} bytes (limit 524288)` |
| F6 | All files together, `SKILL.md` included, have at most 2,097,152 bytes (2 MiB) | `folder too large: {total} bytes in all (limit 2097152)` |
| F7 | Guard, not an HT rule (9.8): the walk stops at entry 1,001 | `the folder has more than 1000 files and folders; it is not a skill folder` |
| F8 | Every file under `references/` is UTF-8. `assets/` may be binary. A file that F6 stopped the read for is not decoded | `references file is not UTF-8 text: {rel}` |
| F9 | `SKILL.md` exists at the root. Stop the `SKILL.md` rules | `the folder has no SKILL.md at its root` |
| F10 | `SKILL.md` is UTF-8. Stop the `SKILL.md` rules | `SKILL.md is not UTF-8 text` |
| F11 | It starts with `---\n`. Stop the `SKILL.md` rules | ``SKILL.md must start with a `---` front matter block that holds `name` and `description` `` |
| F12 | The front matter closes with `\n---\n`. Stop the `SKILL.md` rules | ``SKILL.md front matter has no closing `---` line`` |
| F13 | The front matter is YAML, and a mapping. Stop the key rules; F19 still runs | `SKILL.md front matter is not valid YAML: {error}` · `SKILL.md front matter must be a YAML mapping` |
| F14 | The keys are exactly `name` and `description` | ``SKILL.md front matter must hold exactly `name` and `description`; unexpected keys: {sorted keys}`` · ``SKILL.md front matter has no `name` `` · ``SKILL.md front matter has no `description` `` |
| F15 | `description` is a string | ``SKILL.md front matter `description` must be a string`` |
| F16 | `name` follows Kiln's skill name rules. Every failure is listed, from `skill_name_errors(name)` | The existing texts of `skill_name_validator` |
| F17 | The name is new in the project. Checked only when F16 passed. Taken names (port of `_existing_skill_names`): the `name` of every skill that loads, archived ones too, and the text after `" - "` in the name of each folder under `skills/` | `skill name {name!r} is taken in this project. A skill is created once: choose a new name (a new version is a new skill)` |
| F18 | `description` has 1 to 1,024 characters | `description must have 1 to 1024 characters (it has {n})` |
| F19 | The body after the front matter is not blank | `the SKILL.md body, after the front matter, must not be blank` |

`skill_name_errors(name: object) -> list[str]` is new in `validation.py`. It holds the checks of `skill_name_validator` in the same order and returns every failure. `skill_name_validator` then raises `ValueError(errors[0])`, so its behaviour and its tests do not change. Without it, a name with two faults would need two calls.

### 3.4 The answer on a refusal

Any failed rule raises `SkillBundleInvalid(errors: list[str])`. The route answers **422** with the body `{"message": "<the errors joined with \n>", "error_messages": [<each error>]}`. These are the two keys of Kiln's validation 422. Nothing was written.

| Case | Status | Text |
|---|---|---|
| Unknown project | 404 | Existing |
| Bad body or `provenance` shape | 422 | Kiln's standard validation answer |
| A `derived_from_ids` entry is not a skill of the project | 400 | Existing: `derived_from_ids references unknown sibling: {id}` |
| One or more folder rules | 422 | The list above, all at once |
| The write failed after the rules passed | 500 | `The skill was not created: {error}. Nothing was written.` |

### 3.5 The staged write

Port of `mint_skill_id` and the write half of `install_bundle` (`bundle.py:287-373`), through Kiln's datamodel (architecture decision 11). `skills_dir` is `<project folder>/skills`.

1. Create `skills_dir` when it is missing. Remove each `skills_dir/.staging-*` folder that has no `skill.kiln` and is more than one hour old (port of `sweep_staging`; the age test is new, see 9.8).
2. **Mint.** At most 100 times: build `Skill(name=…, description=…, provenance=…, parent=project)`. The datamodel mints `id` (`generate_model_id`) and sets `created_by` and `created_at`. `final = skill.build_path()` gives `skills/<id> - <name>/skill.kiln`, with Kiln's own `build_child_dirname`. When `final.parent` exists or a folder `<id> - *` exists, try again. Else `mkdir(skills_dir / f".staging-{id}", exist_ok=False)`; on `FileExistsError` try again. After 100 tries: the 500 above.
3. **Stage**, inside `try`: write `SKILL.md` with the exact bytes that were read (not rebuilt, so `save_skill_md` is not called); write each `references/` and `assets/` file from memory; create `references/` and `assets/` when the folder had none, as `save_skill_md` does.
4. **The model file last**: set `skill.path = staging / "skill.kiln"` and call `skill.save_to_file()`. The datamodel writes the file, so its fields and format are Kiln's.
5. **Commit**: `os.rename(staging, final.parent)`. Then set `skill.path = final` and call `ModelCache.shared().invalidate` for both paths.
6. On any exception in 3 to 5: `shutil.rmtree(staging, ignore_errors=True)`, then raise `SkillBundleWriteError`.

- Kiln lists a skill by scanning every sub-folder of `skills/` for `skill.kiln`, folders with a dot name included (`basemodel.py`, `iterate_children_paths_of_parent_path`). So the staged skill is visible between step 4 and step 5. It is complete at that moment. This is why the model file is last.
- Git sync needs no code here. `GitSyncMiddleware` wraps every POST under `/api/projects/{project_id}` in its write lock and commit. A refusal leaves no file, so nothing is committed.
- The route never changes an existing folder.

### 3.6 Tests

`test_skill_bundle.py`, ported by name from `HT-tests:test_skill_installer.py`:

- `TestValidateBundle`: `test_happy_path`, `test_bundle_is_a_file`, `test_missing_skill_md`, `test_stray_root_entries_rejected`, `test_symlinks_rejected`, `test_frontmatter_missing`, `test_frontmatter_unclosed`, `test_frontmatter_extra_and_missing_keys`, `test_bad_name_reported` (two name errors in one answer), `test_name_collision_via_sidecar_and_dirname`, `test_description_bounds`, `test_empty_body`, `test_non_utf8_reference_rejected_binary_asset_accepted`, `test_size_caps`, `test_all_errors_reported_at_once`.
- `TestInstall`: `test_installed_tree_and_sidecar` (`SKILL.md` is byte-identical; the skill loads with `Skill.from_id_and_parent_path`; `created_by` and the provenance are set), `test_rejection_writes_nothing`, `test_id_collision_retries`, `test_failure_after_staging_cleans_up`.
- `TestSweep`: `test_sweeps_staging_only` (a young staging folder and one with `skill.kiln` stay), `test_tolerates_missing_skills_dir`.
- New: a relative path; a root with 25 stray entries gives 20 lines and one count line, and no stray folder is walked; the 1,001-entry guard; a file that changes after the size check is written as it was read.

Not ported: `test_bundle_outside_scratch`, `test_bundle_is_scratch_root_itself` and `test_provenance_args` (HT's gateway keeps these rules); `TestSanitizeParity` (Kiln's own function is called); `TestServer` (the server is removed). `TestValidateSkillName.test_each_branch` becomes a test of `skill_name_errors` in `libs/core/kiln_ai/utils/test_validation.py`.

`test_skill_api.py`: create end to end and read the skill back; the 422 body has both keys; an unknown parent is 400; unknown project is 404; the existing `POST …/skills` still accepts a name that is taken.

## 4. Skill bundle: read

### 4.1 The list

`GET /api/projects/{project_id}/skills/{skill_id}/files`, tag `Skills`, summary `List Skill Files`.

`SkillFileList`: `files: list[SkillFileEntry]`, `total_bytes: int`. `SkillFileEntry`: `path: str` (POSIX, from the skill's folder), `size_bytes: int`.

- Listed: `SKILL.md`, then every regular file under `references/`, then under `assets/`, each group sorted by path. A binary asset is listed.
- Never listed: `skill.kiln`, and any other entry at the skill's root (HT's export never copies the identity file).
- A symlink is not followed and not listed (as `read_skill` in `HT:prompt_text.py`).
- Unknown skill: the 404 of the existing `_get_skill`.

### 4.2 One file

`GET /api/projects/{project_id}/skills/{skill_id}/files/{path}`, declared as `{path:path}` so that the path can hold `/`. Tag `Skills`, summary `Get Skill File`.

`SkillFileContent`:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `path` | `str` | — | As asked |
| `size_bytes` | `int` | — | The size on disk |
| `is_text` | `bool` | — | `True` when the file was returned as text |
| `content` | `str \| None` | `None` | The text, decoded as strict UTF-8 |
| `note` | `str \| None` | `None` | Why `content` is `None` |

A file that is not returned is a 200, not an error, so that a caller that copies a whole skill can go on:

- over 524,288 bytes (the limit a file has at create): `note` is `the file has {size} bytes, over the limit of 524288: not returned`. The file is not opened;
- not UTF-8: `note` is `binary file: not returned as text`.

Path safety, in this order. The path arrives decoded once by the server.

1. Refuse (422, `Skill file path is not valid: {reason}`) when the path is empty, holds a backslash or a character below `0x20`, starts with `/`, or has an empty, `.` or `..` segment.
2. Refuse (422, `Only SKILL.md and files under references/ and assets/ can be read`) unless the path is exactly `SKILL.md` or its first segment is exactly `references` or `assets`. So `skill.kiln` cannot be read.
3. Walk the segments from the skill's folder with `os.lstat`. A missing entry: 404 with Kiln's not-found text, kind `Skill file`, list `skill's files`. A symlink at any segment: 422, `{path} is a symlink: not read`. A folder at the end: 422, `{path} is a folder, not a file`.
4. Last, check that the resolved file is inside the resolved skill folder, as `Skill._read_resource` does.

### 4.3 Tests

In `test_skill_bundle.py` and `test_skill_api.py`. From `TestExport`: `test_copies_the_bundle_without_the_identity_file` (the list has no `skill.kiln`, and reading it is 422), `test_refuses_an_unknown_or_malformed_id` (404), `test_refuses_a_symlink_inside_the_skill` (not listed; 422 on read). `test_refuses_a_destination_that_is_not_new_inside_scratch` stays in HT. New: each refusal of step 1 and 2, with `..`, `%2e%2e`, a backslash and an absolute path; a nested reference file; a binary asset is listed and returns `is_text: false` with the note; a file over the limit; a skill made by `POST …/skills` lists `SKILL.md` only; a round trip: every file of a created bundle reads back equal.

## 5. Version route and `compat.py`

`GET /api/version`, tag `Settings & Utilities`, summary `Get Version`. No parameter, no project, no secret.

`VersionResponse`:

| Field | Type | Meaning |
|---|---|---|
| `version` | `str` | The Kiln app version |
| `min_supported_harness_tuner_version` | `str` | The lowest HT version that works with this Kiln |

- `version` is `app.desktop.studio_server._version.__version__`. The MCP mount of spec one reports the same value as its server version (`kiln_mcp_mount.py` on the build branch).
- **Packaged build:** `app/desktop/build_desktop_app.sh` rewrites `_version.py` from `app/desktop/pyproject.toml` before it builds, so the route gives the release version.
- **Dev server:** nothing rewrites the file, so the route gives the committed value (`1.2.1` today). See 9.5.
- `compat.py` holds one constant and its comment: `MIN_SUPPORTED_HARNESS_TUNER_VERSION = "0.6.0"`. The comment says: edited by hand; raise it in the same change that breaks older HT versions, which includes a change to the skill that breaks `harness_tuner_contract.json` (section 8); the packaging script does not write this file.
- **Starting value** (architecture decision 16): the lowest HT version that runs against this Kiln. **Proposed:** `0.6.0`, the version of HT at `b49f159`. See 9.6. The format is `MAJOR.MINOR.PATCH`, digits only, so HT can compare it as a version.

Tests (`test_version_api.py`): the route returns both fields; `version` equals `_version.__version__`; the constant matches `^\d+\.\d+\.\d+$`; the text of `build_desktop_app.sh` does not name `compat.py`.

## 6. Policies and generated files

Architecture decisions 13 and 14.

| Route | `openapi_extra` | MCP |
|---|---|---|
| `GET …/smell_check` | `ALLOW_AGENT` (a free read) | Allowed: no `with_mcp_deny` |
| `POST …/skills/from_folder` | `ALLOW_AGENT`, as `POST …/skills` has today | Allowed |
| `GET …/skills/{skill_id}/files` and `…/files/{path}` | `ALLOW_AGENT` | Allowed |
| `GET /api/version` | `ALLOW_AGENT` | Allowed |

Each route changes the OpenAPI document. In the same phase as the route, regenerate and commit:

1. The agent policy annotations: `make annotations`, against the dev server on port 8757. One new JSON file for each route under `libs/server/kiln_server/utils/agent_checks/annotations/`.
2. The web client schema: `make schema` (`app/web_ui/src/lib/generate_schema.sh`). CI runs `check_schema.sh`.
3. The skill's API reference: `make api_docs` (`uv run python -m app.desktop.skill_api_reference generate`). CI runs the same module with `check`. It adds these endpoint docs under `references/knowledge/api_docs/`, and rows in three catalogues:
   - `get_api_projects_project_id_tasks_task_id_run_configs_run_config_id_smell_check.md`
   - `post_api_projects_project_id_skills_from_folder.md`
   - `get_api_projects_project_id_skills_skill_id_files.md`
   - `get_api_projects_project_id_skills_skill_id_files_path.md`
   - `get_api_version.md`

No web UI code changes. The skill text of section 7 names these files, so it is written after they exist (architecture build step 9).

## 7. Skill text

The tree is still changing. Each item says what must be true and where it goes on the build branch now. When the work is done: **find the right place to integrate**. Paths below are from the skill root.

### 7.1 The checks that new and changed files must pass

From `skill_checks/` and its tests on the build branch:

- **Front matter.** A file under `references/knowledge/` has exactly `name` (the file stem) and `description`. A smell, lever or technique keeps its schema keys; `description` is one line of 40 to 200 characters with no `|`, and `reviewed` is the date of the edit.
- **Links.** A skill file is named by its full path from the skill root (`references/…`), never by a bare name or a relative path. Every path must exist, endpoint docs included.
- **Reachable.** A new hand-written file is listed in `SKILL.md` or a mode, with its full path and one line.
- **Size.** Every file has at most 30,000 characters. A smell has at most 4,000, a lever 6,000, a technique 12,000.
- **Banned strings, every file:** `kiln_skill` and `skill(name=`. A file says "this skill", never the tool's name. `call_kiln_api` may be named. Also banned in every file: `model_info` outside an endpoint path, `requires approval` and `approval-gated`.
- **Banned terms in `references/levers/` and `references/improving_agents/`:** among others `harness-tuner`, `the tuner`, `gateway`, `install_skill_bundle`, `probe`, `arm`. The product is written `Kiln Harness Tuner`. Under `references/knowledge/` the command name `harness-tuner` is allowed.
- **Split wording.** No line holds `split=test` or `"split": "test"`. A file that speaks of a val or test split names `references/knowledge/train_val_test.md`.
- **Branch phrases.** Outside the two knowledge trees, no file holds `applies when running` or `when running Kiln Harness Tuner`.
- **Pinned headings.** `references/knowledge/run_an_experiment.md` and `references/knowledge/diagnose_an_agent.md` have a fixed list of `##` headings. Add text inside a section; add no section.
- **Generated blocks.** After a change to a smell, lever or technique description: `make skill_index`.
- **Style.** The two knowledge trees are in Simplified Technical English. App pages are written `http://localhost:8757/<path>`.
- **Run:** `uv run python -m kiln_mcp_server.skill_checks check`, and the pytest files of `skill_checks/`.

### 7.2 The statistics file

One new file. **Proposed** path: `references/knowledge/eval_statistics.md`. It names the calls of functional spec 3.2 to 3.5 and 3.8. It adds calls to HT's method and no rule: spec one's ruling stands that the skill gives no guidance of its own on how to read the noise of an eval. Each definition is copied from the playbook or from `run_an_experiment.md`, not written new.

Outline:

1. **What this file is.** The calls behind three questions. The method stays in `references/knowledge/run_an_experiment.md` and the playbooks; the split rule in `references/knowledge/train_val_test.md`. The detectability read, the noise estimate and the noise job use train only, and leave out an item that is also in a val or test split (`left_out_held_out`).
2. **Words**, as the knowledge has them: room, floor, fewest wins, best-case change, flip rate, noise-adjusted wins.
3. **The significance floor.** `POST /api/statistics` with `operation: significance_floor` (`references/knowledge/api_docs/post_api_statistics.md`): the inputs, the outputs, and the pinned example (6 for a pass/fail score at 0.95).
4. **What the evals can show.** The `eval_detectability` read of a run config: one row per score, `skipped`, and `include_val_size`, which reads a size and no result.
5. **Noise.** First the free `noise_check_estimate`. Tell the user the estimate and ask before the paid job. Then `POST /api/jobs/evals/noise_check` with `max_usd`, the job routes to wait and to read errors, the result fields, and that the job leaves nothing in the project.
6. **Two run configs on one split.** The `compare` route: train or val only (say in words that test is refused), no rows in the answer, one eval per call. For a comparison from rows, name `references/knowledge/eval_scores.md`.
7. **What these calls do not decide.** The verdict rules are in `references/knowledge/run_an_experiment.md`.

Files that link to it:

| File | Change |
|---|---|
| `references/knowledge/run_an_experiment.md` (required by the functional spec) | One row in the endpoint doc table at the top. One sentence in "The hypothesis", where it gives the 6 changed items and the room. One sentence in "Cost before you spend" for the noise estimate |
| `references/modes/improve_task.md` | One row in its table of eval files, so the file is reachable |
| `references/knowledge/eval_scores.md` | One line that names the file, beside its paired statistics recipe |

### 7.3 The five smell documents

Files: `references/improving_agents/smells/` `very-long-prompt.md`, `very-long-tool-description.md`, `very-long-skill-description.md`, `too-many-tools.md`, `old-model.md`. In each, three kinds of sentence change:

| Where (build branch now) | Today | After |
|---|---|---|
| Front matter `description`, last sentence | "Measure the length yourself." / "Measure each attached tool yourself, and name each tool that is over." / "Count them yourself." / "Read its release date yourself, and give its age and the reference." | A sentence that says the smell check call reports it |
| "How to recognise it", first bullet of "In the harness" | "measure it yourself: …" / "count it yourself: …" / "read it yourself: the release date … in `references/knowledge/api_docs/get_api_model_info_model_details.md` …" | "the smell check call (`references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs_run_config_id_smell_check.md`) reports it: …", with the rest of the bullet kept |
| "How to confirm it": "The reference is a default of Kiln Harness Tuner" (in `very-long-prompt.md`, `too-many-tools.md`, `old-model.md`) | The limit is HT's | "The reference is a default of Kiln" |

Also: `very-long-tool-description.md` says that a tool in `unread_tools` was not measured. `old-model.md` says that `as_of` sets the date, and that `model.release_date_note` gives the reason when there is no date; its other bullets (newer models, `agent_notes`) stay. Then `make skill_index`.

### 7.4 The skill lever and the skill techniques

`references/levers/skill.md`:

| Where | Today | After |
|---|---|---|
| Front matter `api_docs` | Five docs | Add the three skill bundle docs of section 6 |
| "How to change it", "Read" | Three read docs | Add the file list and the file read |
| "A new skill" | "The Kiln API takes no `references/` files: a skill with reference files is built when running Kiln Harness Tuner, which installs a whole bundle." | A skill with `references/` or `assets/` files is written as a folder on the machine that runs Kiln and created with `references/knowledge/api_docs/post_api_projects_project_id_skills_from_folder.md` (`folder_path`, `provenance`). The answer gives the `tool_id` |
| "A new version of an inherited skill" | "The content endpoint returns the body only, so a new version made this way over the API loses the inherited skill's reference files. A new version that keeps them is built when running Kiln Harness Tuner." | Read every file of the old skill with the two file calls, change the copy in a new folder, and create it from the folder under a new name |
| "Limits" | "A bundle that Kiln Harness Tuner installs has at most 512 KB for one file, and 2 MB for one bundle. Text files only in `references/`." | The same limits as limits of the create call, plus: no symlinks, and the name must be new |

The four techniques each have one passage that ends in "is built when running Kiln Harness Tuner", with a following sentence that a new version made over the API loses its reference files: `guide-skill-for-a-tool-set.md` ("How"), `document-into-a-skill.md` (step 1), `long-prompt-into-a-skill.md` (step 2), `rewrite-an-inherited-skill.md` (the "restructure" bullet), all under `references/improving_agents/techniques/`. After: the passage says that a skill with reference files is created from a folder, and that every file of an existing skill can be read, and names the lever `references/levers/skill.md` for the calls. The technique does not repeat the endpoint docs: the lever owns how (spec one's owner rule).

### 7.5 `using_harness_tuner`

New file `references/knowledge/using_harness_tuner.md`, front matter `name: using_harness_tuner` and a `description`. The facts are in the facts file (`port_ht_adoption_facts.md`, section 8), from HT's docs. Outline:

1. **When to use it, and when not.** Many rounds, or a search over many ideas: the command line. One or two clear ideas stay in the chat (`references/knowledge/run_an_experiment.md`, "Two paths").
2. **Before you start.** Checks the agent makes itself with `call_kiln_api`: a run config exists; at least one eval that is not archived has a default judge; each such eval has a train and a val split; the item counts (a significant win needs 6 changed items); Kiln has a key for each provider the run calls. What to ask the user: the goal, the restrictions, the models allowed, a budget, a time limit, and which agent CLI is signed in. Platform: Linux or macOS on Apple silicon, WSL 2 on Windows; Python 3.11 or later and `uv`; Kiln runs on the same machine, because HT also reads the project folder.
3. **Install and verify.** `uv tool install harness-tuner`, then `harness-tuner --help`; or `uvx harness-tuner …`.
4. **The command.** The form with no terminal: `harness-tuner --project-id <id> --task-id <id> --guidance "…" --timeout-mins 60 --budget-usd 20 --no-interaction --no-progress`. The options that matter: `--objective`, `--models keep|any` or `--model-policy FILE`, `--guidance`, `--budget-usd` (default 50), `--timeout-mins` (default 720), `--agent-cli`, `--agent-model`, `--kiln-host`, `--min-effect`, `--noise-check N`, `--allow-underpowered`, `--demo-project`. Do not pass `--no-recon` or `--skip-model-preflight` on a first run. The installed version's `--help` wins over this file.
5. **Cost and time.** Two costs: provider calls (inside the budget) and the agent CLI's own tokens (shown, not in the budget). No measured figure exists. Never start a paid run without a budget that the user gave. Tell the user the command before it starts.
6. **Start, watch, stop.** Start it in the background. The first line gives the run id and the run folder. Watch the log and `wave_log.jsonl` there. Stop with `kill <pid>`. Exit codes: 1 a start error, 2 a usage error, 130, 143, 129 for the signals. A stopped run writes no report. One run per task at a time.
7. **Read the result.** The report under `~/.kiln_ai/harness_tuner/reports/`; the `baseline` memory record and its chain of promotions. The loop never reads test: take the test number afterwards, on request. The task's default run config is never changed: the user decides.
8. **When the start refuses.** Each refusal names its fix. Kiln too old: the user updates Kiln. HT too old: upgrade HT with the command the message gives. Missing splits, a missing key, an agent CLI that is not signed in: say what the agent may fix and what goes to the user.
9. **Limits.** No resume in the middle; it does not create or repair splits; small evals are underpowered; the model policy does not cover judges; code an agent writes runs on the Kiln machine.

Facts that the switchover changes, against the facts file:

- The Kiln version check is the two-way check of functional spec 5.8, not "Kiln v1.3, read from `/openapi.json`".
- `--no-model-catalog` is removed. Do not name it.
- The `--dest` form of `harness-tuner-install-agents` is removed. Do not name it. An agent that works by hand uses this skill and `call_kiln_api`.
- Do not name `kiln_api_mcp` or the skill installer.

Integration: `references/knowledge/run_an_experiment.md`, "Two paths", and `references/modes/improve_task.md` (its line on experiments at scale) name the file. `app/mcp/knowledge_backlog.md` has an entry `using_harness_tuner`, and `test_the_using_harness_tuner_entry_is_in_unranked` pins it: remove both when the file is written.

## 8. The contract test

Architecture section 4. Files: `app/mcp/kiln_mcp_server/skill_checks/test_harness_tuner_contract.py` and `harness_tuner_contract.json` beside it.

**This document defines the shape and the test. It does not define the content.** [ht_skill_reading_and_roles.md](ht_skill_reading_and_roles.md) owns every entry of the list.

The JSON object has exactly these four keys:

| Key | Type | Meaning |
|---|---|---|
| `paths` | list of strings | File paths from the skill root. Each must exist |
| `ids` | map: kind to a list of ids | The kinds are `levers`, `techniques`, `playbooks`, `smells`. Each id must be a file `<folder of the kind>/<id>.md` |
| `headings` | map: a file path, or `kind:<kind>`, to a list of headings | Each heading must be present in the file, or in every document of the kind |
| `front_matter_keys` | map: `kind:<kind>` to a list of keys | Each key must be present in the front matter of every document of the kind |

How the test reads the tree:

- It reads the files that the skill tool serves, with `get_index()` and `read_file(key, index)` of `kiln_mcp_server.skill_files`. This is the text HT gets.
- The folder of a kind is `COMPONENT_ROOTS[kind]` of `knowledge_schema.py`. "Every document of the kind" is every file directly in that folder, except `index.md`. A sub-file of a technique is not a document; HT names a sub-file in `paths`.
- A heading is present when a line outside a fenced block starts with one to six `#` and a space, and the rest of the line, stripped, equals the heading. The level is not checked.
- Front matter is read with `read_front_matter` of `skill_checks/front_matter.py`.

Tests:

- `test_the_contract_file_has_the_four_keys`: exactly the four keys; every kind is one of the four; every `headings` key is a path or `kind:<kind>`; no list has a repeat.
- `test_the_shipped_skill_meets_the_harness_tuner_contract`: it collects every miss, then fails once. Each miss is one line: `path <path>: not in the skill`, `id <kind>/<id>: no file <path>`, `heading "<heading>": not in <path>`, or `front matter key <key>: not in <path>`. The message ends with: `Kiln Harness Tuner reads these names. Keep the name in the skill, or change harness_tuner_contract.json and raise MIN_SUPPORTED_HARNESS_TUNER_VERSION in app/desktop/studio_server/compat.py.`
- Synthetic cases with a small tree in `tmp_path`: one for each kind of miss, and one for a heading inside a fenced block.

The PyInstaller hook of spec one collects every file of the package that is not Python. Add `skill_checks/*.json` to its `DATA_EXCLUDES`, so that the list does not ship in the app.

## 9. Conflicts and open points

1. **Binary assets are lost on a copy.** The functional spec says a binary asset is not returned. HT's export copies assets byte for byte today (`bundle.py`, `export_bundle`). After the switch, a builder that clones a skill with a binary asset gets a copy without it. The HT document must say what the export tool does then.
2. **`validation.py` is outside architecture 2.1.** Reporting every name failure at once needs `skill_name_errors` in `libs/core`. Without it, the route reports one name failure per call, against "every problem in one answer".
3. **A router imports a router.** `task_run_config_from_id` is in `eval_api.py`. `kiln-conventions` forbids a new import from another `*_api.py`; three modules do it today. The measurement APIs have the same need. One decision for both documents: import it, or move it to a service module first.
4. **Model info needs a two-line change in spec one's code.** `connect_model_info_api` must return its `ModelInfoService`, and the service gets `release_facts`. Otherwise the smell check builds a second catalogue.
5. **A dev server reports the last release.** `_version.py` is `1.2.1` on the build branch, and HT's docs already call the features on it "Kiln v1.3". HT's minimum will be the first release with this spec. Against a dev server, HT stops with "Kiln too old" until `app/desktop/pyproject.toml` and `_version.py` are raised. The demo run (functional spec 7) needs a build with the raised version.
6. **The starting value of the constant** cannot be read from the code. `0.6.0` is proposed. No HT version before the switch reads the route, so any value at or below the first switched HT version has the same effect.
7. **Reworded strings.** The old-model sentence and three source strings are HT's with Kiln's words (2.3, 2.4). HT's planner reads the new sentence. If the owner wants HT's exact text, it is one string.
8. **Guards added for an open route.** Not in HT: stray root entries are not walked; content is read once and at most to the 2 MiB limit; the 1,000-entry guard; the one-hour age test of the staging sweep. Each limits what a caller-named path can make Kiln do.
9. **One unreadable skill silences the skill check for all skills.** This is HT's behaviour, kept as an exact port. A check per skill is a small change if wanted.
10. **Skill text the functional spec does not list.** `references/knowledge/diagnose_an_agent.md` ("What the smells measure") tells the reader to measure by hand. `references/knowledge/adding_skills.md` lists the skill endpoints without the three new ones. Three playbooks (`dealing-with-a-noisy-eval.md`, `dealing-with-a-saturated-eval.md`, `spending-the-budget.md`) say that noise and room are measured only when Kiln Harness Tuner runs. Left unchanged here; the owner decides.
11. **A crash between the model file and the rename** leaves a whole, usable skill in `skills/.staging-<id>/`. The sweep does not remove it. Accepted, as in HT.

## 10. Not verified

- Nothing here was run. `Skill.save_to_file()` with a preset `path`, then a rename, was read in `basemodel.py` only. The same holds for `ModelCache` after the rename.
- A `{path:path}` parameter with the agent policy annotations, with the Kiln Assistant's policy lookup, and the generated doc name `…_files_path.md`.
- The `DATA_EXCLUDES` pattern for the JSON file, and that an OpenEnv tool is unread outside an episode (a docstring, not a test).
- The facts of 7.5: taken from the facts file. Spot-checked in HT's docs: the install command, the option table, `--no-model-catalog`, `--dest`. The text of HT's "update HT" message does not exist yet.
- Every build-branch path and sentence is as of commit `5522a7b`; spec one's phases 17 and 18 can move them. Which HT versions before `0.6.0` work with this Kiln.
