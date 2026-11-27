# Functional Spec Questions: API Cleanup and Robustness

Handoff notes for whoever drives this project next. `project_overview.md` is complete and approved. The functional spec has not been drafted yet: it is waiting on answers to the questions below. Once they are answered, write `functional_spec.md` from the overview, these answers and the scan findings in the appendix (spec skill: `/spec continue`).

The scans in the appendix were run during planning (2026-11-23) against main at `c8c1931d`. The item 2 findings were confirmed with real calls through FastAPI's TestClient, writing only into a scratch directory. The item 5 findings come from reading the code. Line numbers will drift; re-check them before relying on them.

## What the scans found beyond the brief

**Item 2: the hole is wider than `save_sample`.**
- **The `id` field is also a way out of the project.** Ids are never format-checked, and the id becomes the record's folder name. Sending `id="../../../evil/x"` to `save_sample` wrote a file outside the project with no `path` field at all. Clearing `path` alone would not close the hole.
- **Two task routes write files outside the project too.**
  - `POST /api/projects/{p}/tasks` honours a `path` at the top level and on nested child records (runs, prompts, evals).
  - `PATCH /api/projects/{p}/tasks/{t}` honours a top-level `path`.
- **Smaller id problems.**
  - `PATCH` on a run can rewrite the run's id.
  - `POST /api/projects` keeps the caller's id, so two projects can share one.
  - `PATCH` on a project can change its id. A `path` there crashes with a 500, so it is safe only by accident.
- **`POST …/runs/bulk_upload` writes the upload anywhere.** It joins the raw upload filename onto the temp directory, so a filename starting with `/` or containing `../` writes anywhere. This is not a datamodel body, but it is the same kind of hole.
- **The UI never sends `path`, nested children, or an id it depends on.** For `save_sample` it already uses the id the server returns. Fixing all of the above won't break the UI.

**Item 5: routes that change or delete records a run config depends on.**
- Already fine:
  - Edits to run configs, saved prompts, code tools, skills, fine-tunes and RAG configs only change cosmetic fields.
  - There is no delete route for run configs, judge configs or fine-tunes.
- Open problems:
  - MCP tool server edits can change the server URL, command, args, headers and env. Every run config pointing at that server then silently uses something else.
  - Editing a Kiln-task tool can change which task and run config it runs.
  - Deleting a tool server, and changing an OpenEnv server's URL, check nothing.
  - Editing a spec can change `definition`/`properties`, which the older g_eval judges read when they run.

**Item 1: one side effect.** Very old run configs that still hold a live generator id (not a frozen copy) will change when they next run. They already change today whenever the dataset changes.

## Questions

Recommendations are from the planning agent. Answer each question on a line, preceded by its number, or say "all recommended" and list only the ones you'd change.

### Item 1: few-shot and repair generators
1. **The golden set**, the human-rated runs used to calibrate judges, is stored apart from train/val/test (`Eval.eval_configs_filter_id`). Should few-shot also skip golden items?
   - Recommended: **no**. The golden set measures judges, not the task prompt. It is usually most of the rated runs, so skipping it would starve few-shot.
2. **The prompt picker** (`app/web_ui/src/lib/ui/run_config_component/prompt_type_selector.svelte`, around lines 95-140) offers few-shot whenever any rated run exists. After this change, a task whose rated runs are all in eval splits would get a few-shot prompt with zero examples.
   - **A (recommended):** the backend reports how many runs are still usable. The picker then disables a generator that has none and says why ("all rated runs are in eval splits").
   - **B:** leave the picker as it is.
3. Are you fine that very old unfrozen run configs change their prompt (the side effect above)? Recommended: **yes**.

### Item 2: request bodies
4. Scope. Recommended: **A**.
   - **A:** fix every route that can write outside the project or overwrite a record: `save_sample`, task create, task patch and `bulk_upload`.
     - Also stop the id changes on run patch, project create and project patch.
     - Add one id format check in the base model, for example letters, digits, `_` and `-`. That closes the traversal everywhere.
     - On the create routes, the server also sets `created_at`/`created_by`.
     - Leave alone the cosmetic metadata stored inside nested objects (the rating and repair output records).
   - **B:** only the routes that write outside the project or overwrite a record.
   - **C:** only `save_sample`, and list the rest for the owner.
5. Should `save_sample` take its own request type (input, output, source, tags) instead of a whole `TaskRun`? Recommended: **yes**. It removes this kind of problem by design. It does change the API contract for MCP clients, and the UI types update with it.

### Items 3–4: delete checks and prompt archiving
6. A saved prompt counts as **in use** if any of these reference it: a run config of the task, the run config stored in a fine-tune, or the task's default run config. Should past runs that recorded the prompt id also block a delete?
   - Recommended: **no**. They are history, and they keep working without the prompt.
7. A code tool counts as **in use** if any of these list it: a run config in any task of the project, a fine-tune's run config, another code tool's allowlist, or a code eval's allowlist. Agreed?
8. Archiving prompts:
   - It follows the skills pattern: an `is_archived` field, set through the existing prompt `PATCH`.
   - Only custom saved prompts (`id::…`) can be archived. Frozen prompts belong to their run configs.
   - Archived prompts are hidden from the picker for new run configs but still work at run time.
   - They show in the prompts list, dimmed with an "Archived" badge.
   - **Delete stays.** It returns a 409 that names what uses the prompt and suggests archiving.

   Agreed?

### Item 5: what to fix and what to leave
9. **Recommended to fix in this project:**
   - **MCP tool servers:**
     - When a run config uses the server, block changes to the URL, command and args.
     - Still allow changes to name, description, headers and env, so keys can be rotated.
     - The delete fails while the server is in use.
   - **Kiln-task tool edits:** only name, description and archive can change. The UI already sends only those.
   - **OpenEnv servers:** block a URL change while in use. The delete also checks run configs, not only eval inputs.
   - **Specs:** `definition`/`properties` can't change once the spec has an eval. The UI only edits name and tags.
10. **Recommended to leave as they are, and list in the spec as owner-reviewed:**
    - **Cascading deletes** of a task, an eval or a spec. These are explicit, destructive user actions, and agents are already blocked from them.
    - **Eval input tag and reference edits.** There is already an approval prompt. Harness-tuner's `block_eval_changes` will cover them.
    - **Provider and custom-model deletes.** These are settings, not records.
    - **Document tag and delete edits.** That is corpus data, not config.

    Override any of these?
11. **Task `PATCH`** can change `instruction`, `requirements` and `thinking_instruction`. Frozen run configs don't change, but live generators, old unfrozen run configs and requirement ratings keyed by requirement id do.
    - **A (recommended):** leave it. A task is meant to evolve, and that is why run configs freeze their prompts.
    - **B:** block removing a requirement once runs have ratings for it.
    - **C:** lock all three once run configs exist.

---

## Appendix A: Item 1 notes (few-shot and repair generators)

- `MultiShotPromptBuilder.collect_examples` (`libs/core/kiln_ai/adapters/prompt_builders.py`, around lines 204-234) is the one place to change. `FewShotPromptBuilder`, `RepairsPromptBuilder` and the chain-of-thought builders inherit it. `CustomExamplePromptBuilder` overrides it to return `[]` and takes caller-supplied examples, so it is out of scope.
- Splits are `Eval.splits` (`libs/core/kiln_ai/datamodel/eval.py`, around line 1494), keyed by plain `str` (unknown fourth split names are preserved). Each is a `TaskRunSplit` (dataset filter over `TaskRun`s) or an `EvalInputSplit` (over `EvalInput`s, which are not task runs and can't appear in few-shot). `resolve_split` in `libs/core/kiln_ai/datamodel/eval_splits.py` resolves one. The golden set is `Eval.eval_configs_filter_id` and is deliberately not a split.
- Live callers of `prompt_builder_from_id` (all get the new behaviour):
  - the adapter at run time (`libs/core/kiln_ai/adapters/model_adapters/base_adapter.py`, around line 164)
  - repair (`libs/core/kiln_ai/adapters/repair/repair_task.py`)
  - prompt previews (`libs/server/kiln_server/prompt_api.py`, `app/desktop/studio_server/prompt_api.py`)
  - data gen (`app/desktop/studio_server/data_gen_api.py`, around line 1401)
  - fine-tune system message (`app/desktop/studio_server/finetune_api.py`, around line 640)
  - the judge chain-of-thought check (`libs/core/kiln_ai/adapters/eval/eval_runner.py`, around line 212)
  - the package CLI (`libs/core/kiln_ai/cli/commands/package_project.py`)
- Run config creation (`app/desktop/studio_server/eval_api.py`, around lines 2536-2595) freezes generator prompts into `TaskRunConfig.prompt`, so existing run configs keep their examples. Only legacy run configs can still hold a live generator id.
- Prompt generator copy lives in `app/web_ui/src/lib/prompt_generators.ts` ("Includes up to 4 examples from your dataset."). It probably needs to say that eval items are excluded.

## Appendix B: Item 2 scan (routes taking datamodel bodies)

Method: enumerated every route on the desktop `make_app()` (270 routes, 116 with a body), walked each body type recursively for `KilnBaseModel` subclasses, and grepped for `**x.model_dump()`, `model_copy(update=...)` and `model_validate(body)`. Found 4 typed datamodel bodies and 4 `Dict[str, Any]` bodies merged into datamodels.

Severity: **A** = write outside the project, **B** = overwrite an existing record, **C** = caller-controlled metadata only, **D** = safe.

| # | Route | What happens | Sev |
|---|---|---|---|
| 1 | `POST /api/projects/{p}/tasks/{t}/save_sample` (`app/desktop/studio_server/data_gen_api.py:689`, save at 710-711). Body: whole `TaskRun` | Sets `parent=task`, calls `save_to_file()`. Caller `path` is honoured. Caller `id` becomes the folder name: `id="../../../../../../evil/traversal_by_id"` with no `path` wrote outside the project (confirmed). An existing id overwrites that run. Caller also controls `created_at`/`created_by`, `v`, `eval_source` (PATCH run forbids it, this route does not) and `parent_task_run_id`. | A, B |
| 2 | `POST /api/projects/{p}/tasks` (`libs/server/kiln_server/task_api.py:77`, 91, 98). Body: `Dict` into `Task.validate_and_save_with_subrelations` | Only a top-level `id` is rejected. A top-level `path` is honoured, because `_validate_nested` only overrides path when a `path` arg is passed (`basemodel.py:1010-1016`); confirmed outside write. Nested children (`_runs`, `prompts`, `evals`, …) are saved with their caller `path`/`id` (`basemodel.py:1037-1042`); confirmed. A nested `id` can also traverse. | A |
| 3 | `PATCH /api/projects/{p}/tasks/{t}` (`libs/server/kiln_server/task_api.py:114`, 155-157). Body: `Dict` → `model_copy(update)` → `model_dump` → validate_and_save | `id` must equal the task id, but `path` is honoured; confirmed outside write, and the real `task.kiln` was not updated. `created_at`/`created_by` and `v` are stored. | A |
| 4 | `PATCH /api/projects/{p}/tasks/{t}/runs/{r}` (`libs/server/kiln_server/run_api.py:836` → `update_run_util` :1027). Body: `Dict`, `deep_update` onto the dump, `TaskRun.model_validate` | Path is reset to `run.path` (:1054), so no outside write. `id` is rewritten in the file; it can duplicate another run's id (`from_id_and_parent_path` returns the first match). `created_at`/`created_by` and `v` are stored. | B-lite, C |
| 5 | `POST /api/projects` (`libs/server/kiln_server/project_api.py:47`, 63). Body: `Project` | Path is forced to `~/Kiln Projects/{name}/project.kiln`, and `name` is filename-validated. Caller `id` is kept; confirmed a second project with a duplicate id, and lookups by id return the first match. `created_at`/`created_by` stored. | B-lite, C |
| 6 | `PATCH /api/projects/{p}` (`libs/server/kiln_server/project_api.py:72`, 89-92). Body: `Dict` → `model_copy(update)`, no validation, then save | A `path` arrives as a `str`, so `save_to_file` crashes with a 500 and nothing is written (safe by accident). `id` can be changed to collide with another project. `created_by` and `v` stored. | B-lite, C |
| 7 | `POST …/runs/{r}/save_repair` (`libs/server/kiln_server/repair_api.py:160`, 195, 199). Body: `RepairRunPost.repair_run: TaskRun` | Only `repair_run.output` is copied in, path is reset to `run.path`. The nested `TaskOutput`'s id, path string, `created_by` and `created_at` are stored inside `repaired_output`. | C |
| 8 | `POST /api/projects/{p}/tasks/{t}/runs` (`libs/server/kiln_server/run_api.py:597`, 628, 638). Body: `CreateTaskRunRequest.rating: TaskOutputRating` | Run is built fresh with a fresh id. The nested rating's `id`, `path` and `created_by` are stored verbatim (never used for writing). | C |

Checked and safe (D): `/save_qna_pair` (`data_gen_api.py:1036-1071`, builds a fresh TaskRun); `ClaimReview(**claim_review.model_dump())` (`copilot_utils.py:541`, no persistence fields); `create_eval_input` (`eval_api.py:2332`, builds fresh); `update_memory` (whitelists 4 fields); `UserModelEntry.id` (a settings entry); job params models (`EvalJobParams`, `NoopJobParams`, no datamodels).

Side finding (A, not a datamodel body): `POST /runs/bulk_upload` (`libs/server/kiln_server/run_api.py:954-961`) does `os.path.join(tempfile.gettempdir(), file.filename)` with the raw multipart filename. Absolute and `../` filenames both wrote outside the temp dir (confirmed). The document upload routes use the filename only as metadata.

How `save_to_file`, `path` and `id` work (`libs/core/kiln_ai/datamodel/basemodel.py`):
- `save_to_file` (:497-527) writes to `self.build_path()`. `KilnParentedModel.build_path` (:658-679) returns `self.path` **if set, regardless of parent**; otherwise `parent_folder/relationship/build_child_dirname()/base_filename`, where the dirname is `"{id}"` or `"{id} - {name}"` (:638-656).
- The dump excludes `path` only at the top level (:513). Nested `KilnBaseModel`s (`TaskOutput`, `TaskOutputRating`) serialise their own `path`.
- `path` is a plain `Optional[Path]` (:324) with no input validator. `id` is `Optional[str]` with a default factory and **no format validation** (:45-49). `parent` is `exclude=True` but can be set on input; a wrong parent type fails `check_parent_type` (:626).
- `model_type` is computed, so caller input is ignored. `v` is stored as given; a `v` above `max_schema_version` makes the record unloadable (:458).
- So a fix has to reset or validate `id` as well as `path`. A pattern validator on `id` in the base model closes the traversal everywhere.

What the web UI sends:
- `save_sample` (`routes/(app)/generate/[project_id]/[task_id]/synth/+page.svelte:693`, `kiln_pro_inputs.svelte:562`) posts the whole TaskRun returned by `generate_sample`. It carries a server-generated id that was never persisted, and no `path`. The UI then uses the **returned** `data.id` (synth:713, kiln_pro:573). Regenerating the id server-side and clearing `path` will not break it.
- `save_repair` (`run.svelte:221`, `output_repair_edit_form.svelte:65`) sends `{repair_run, evaluator_feedback}`.
- PATCH run sends only `{tags}` or `{output: {rating: {...}}}` (`run_sidebar.svelte:149-188`).
- POST and PATCH task send name, description, instruction, requirements, thinking_instruction, turn_mode and schemas (`edit_task.svelte:132-185`), or subsets such as `{instruction, thinking_instruction}` and `{default_run_config_id}`.
- POST and PATCH project send `{name, description}` (`edit_project.svelte:46`).
- The UI never sends `path`, never sends nested children on task create, and never calls POST `/runs`.

## Appendix C: Items 3-5 scan (immutable records)

Paths: `S` = `app/desktop/studio_server`, `K` = `libs/server/kiln_server`, `D` = `libs/core/kiln_ai/datamodel`, `UI` = `app/web_ui/src/routes/(app)`. Read from the code, not run.

### What a run config references

`TaskRunConfig` (D/task.py:65-92): name, description, `run_config_properties`, a frozen `prompt: BasePrompt` (84), `starred` (88), provenance.

`KilnAgentRunConfigProperties` (D/run_config.py:48-89):
- **Model** (`model_name`, `model_provider_name`, 56-57): can name a **Finetune** (provider `kiln_fine_tune`, model `proj::task::ft_id`; `libs/core/kiln_ai/adapters/provider_tools.py:194, 287-310`), a **user model** `user_model::<id>` (provider_tools.py:477-497) or an openai_compatible provider. The last two are Config settings, not records.
- **Prompt** (`prompt_id`, 60; formats at D/prompt_id.py:58-107):
  - `id::<prompt>` → a saved **Prompt**, by reference (not copied).
  - `task_run_config::…` → the run config's own frozen `prompt`.
  - `fine_tune_prompt::…` → `Finetune.system_message` / `thinking_instructions` (D/finetune.py:70-76).
  - Generator ids are frozen at creation (S/eval_api.py:2538-2595); only legacy run configs still hold a live one.
- **Tools** (`tools_config.tools`, 78; prefixes at D/tool_id.py:40-48):
  - `mcp::remote|local::<server_id>::<tool>` → ExternalToolServer
  - `kiln_task::<server_id>` → ExternalToolServer of type kiln_task, which stores another task's `task_id` + `run_config_id` (D/external_tool_server.py:55-60)
  - `kiln_tool::rag::<id>` → RagConfig (D/rag.py:13), which references extractor, chunker, embedding, vector store and reranker config ids (rag.py:39-55) and document `tags` (60)
  - `kiln_tool::skill::<id>` → Skill (D/skill.py:20)
  - `kiln_tool::code::<id>` → CodeTool (D/code_tool.py:39); its own `tool_allowlist` (77) is transitive
  - `kiln_tool::openenv::<server_id>::<tool>` → OpenEnvServer (D/openenv.py:137, `url` 148)
  - `kiln_tool::memory::<op>` → no record
- **Input transform** (82): an inline Jinja template, not a record.

`McpRunConfigProperties.tool_reference` (D/run_config.py:113-121; `MCPToolReference` 22-35) references an MCP ExternalToolServer by id plus a tool schema snapshot.

Other references:
- `LlmJudgeRunConfig` (D/eval.py:113-143) does **not** embed a run config; it only holds thinking_level, temperature and top_p.
- `EvalConfig.properties` references a judge `model_name`/`model_provider` (eval.py:146-162) and, for code evals, a `tool_allowlist` (276-285).
- `EvalRun.task_run_config_id` (eval.py:1023) → a run config.
- `EvalInput.openenv_reset.openenv_server_id` (eval.py:704-724) → an OpenEnvServer.
- **Spec**: legacy g_eval tool-call judges read `spec.properties` at eval time (`libs/core/kiln_ai/adapters/eval/g_eval.py:172-182`).
- **RAG document corpus**, through RagConfig tags.

### Routes that edit or delete these records

| Route | Fields / behaviour | Protections today | UI usage | Recommendation |
|---|---|---|---|---|
| K/prompt_api.py:296 PATCH `/tasks/{t}/prompts/{p}` | name, description only (`PromptUpdateRequest` 185-191) | Only `id::` prompts; frozen get 400 (68-82) | UI/prompts/…/saved/[prompt_id]/+page.svelte:124-129 EditDialog | OK |
| K/prompt_api.py:323 DELETE same | Hard delete, no usage check | DENY_AGENT | Same EditDialog `delete_url` (129) | **fix: fail-if-in-use + archive** (users then fail with "Prompt ID not found", `prompt_builders.py:358`) |
| K/task_api.py:114 PATCH task | Arbitrary dict: name, description, **instruction, requirements, thinking_instruction**, default_run_config_id | Blocks schemas (137-141), id (142-146), turn_mode (148-156; also `frozen`, D/task.py:182-186) | edit_task.svelte:131-137,172; prompts/…/edit_base_prompt/+page.svelte:64; lib/stores/run_configs_store.ts:184 | owner decision (Q11); also the `path` hole (Appendix B #3) |
| K/task_api.py:172 DELETE task | Cascades all children | DENY_AGENT; archives kiln_task tools pointing at it (187-200) | settings/edit_task/[…]/+page.svelte:20 | owner decision (Q10) |
| S/eval_api.py:2596 PATCH `/run_configs/{id}` | name, starred, frozen `prompt_name` (`UpdateRunConfigRequest` 586-596) | No delete route exists | optimize/…/+page.svelte:293; optimize/…/run_config/[id]/+page.svelte:156 | OK |
| S/tool_api.py:720 `edit_remote_mcp` / :794 `edit_local_mcp` | **server_url, headers, command, args, env** | Connectivity check only | edit_remote_tool.svelte:167, edit_local_tool.svelte:196 | **fix** (Q9) |
| S/tool_api.py:917 `edit_kiln_task_tool` | **task_id, run_config_id** | Validates run config exists (863-878) | Archive/unarchive only; UI resends same values (kiln_task/[id]/+page.svelte:274) | **fix: name/description/is_archived only** (Q9) |
| S/tool_api.py:957 DELETE `tool_servers/{id}` | Hard delete plus secrets | DENY_AGENT, no usage check | No UI caller | **fix: fail-if-in-use** (Q9) |
| S/code_tool_api.py:349 PATCH CodeTool | name, description only (`extra=forbid`, 96-102) | — | code_tools/[id]/+page.svelte:417-422 | OK |
| S/code_tool_api.py:402 DELETE CodeTool | Hard delete, no usage check | DENY_AGENT | Same EditDialog `delete_url` (422) | **fix: fail-if-in-use** ("Code tool not found", `tools/tool_registry.py:197`) |
| S/skill_api.py:179 PATCH Skill | `is_archived` only (39-44); no DELETE route | Fully immutable | skills/[p]/[id]/+page.svelte:102-121,154-158 | OK (reference pattern) |
| S/openenv_server_api.py:176 PATCH | name, description, **url** | Approval prompt | No UI | **fix: block url change if in use** (Q9) |
| S/openenv_server_api.py:202 DELETE | 409 if eval inputs reset into it (217-240) | Eval inputs only, not run-config tools | No UI | **fix: add run-config check** (Q9) |
| K/document_api.py:2196 PATCH rag_config / :1937 PATCH extractor_config | name, description, is_archived | No delete routes for rag/chunker/embedding/vector/reranker configs | rag_config/+page.svelte:121,631-638; extractor/+page.svelte:73 | OK |
| K/document_api.py:1250,1289 (doc tags), 1705/1731 (doc delete), 1860 (extraction delete) | Changes what a RAG tool retrieves | — | docs/library/[p]/[d]/+page.svelte:477-495 | owner decision (Q10) |
| S/finetune_api.py:382 PATCH | name, description only (195-201); no DELETE route | — | fine_tune/…/[id]/+page.svelte:347-350 | OK |
| S/eval_api.py:2152 PATCH eval | name, description, priority, status, display names; `train_set_filter_id` set-once (2181-2192) | Guarded | specs/…/[eval_id]/+page.svelte:997-1001 etc. | OK |
| S/eval_api.py:2133 DELETE eval / K/spec_api.py:318 DELETE spec (also deletes its eval) | Cascades configs and scores | DENY_AGENT, no check | eval page delete_url (1001); spec page (759) | owner decision (Q10) |
| S/eval_api.py:2381 PATCH eval_input | **tags** (split membership), **reference** (ground truth); `data` rejected 422 | Approval prompt (893-930) | No UI | owner decision (Q10) |
| S/eval_api.py:2431 DELETE eval_input | 409 if traces or scores reference it | Guarded | No UI | OK |
| K/spec_api.py:234 PATCH spec | name, tags, priority, status, **definition, properties** | Syncs to the eval | UI sends only name and tags (spec page 469, 755) | **fix: lock definition/properties once an eval exists** (Q9) |
| S/eval_api.py:2952 POST set_current_eval_config | Pointer change | — | evals_store.ts:14 | OK |
| S/provider_api.py:594, 740 DELETE openai_compatible / user_models | Settings, not records | DENY_AGENT | connect_providers.svelte:954; settings/providers/add_models/+page.svelte:289 | owner decision (Q10) |

No edit or delete routes exist for: TaskRunConfig delete, EvalConfig, DatasetSplit, Finetune delete, or chunker, embedding, vector-store and reranker configs.

### Existing archiving pattern (to copy for Prompt)
- **Datamodel:** top-level `is_archived: bool = False` on Skill (D/skill.py:39), CodeTool (code_tool.py:52), RagConfig (rag.py:20), ExtractorConfig (extraction.py:151). ExternalToolServer keeps it in `properties["is_archived"]` (external_tool_server.py:235-237). Eval and Spec use `status = archived` (datamodel_enums.py:23).
- **Routes, two shapes:** a PATCH taking `is_archived` (skill_api.py:179, document_api.py:1937/2196), or a dedicated `POST …/{id}/archive` (code_tool_api.py:382 with `{archived}`; tool_api.py:830 with `{is_archived}`).
- **Meaning:** hidden from pickers for *new* run configs (S/tool_api.py:344, 359, 415, 471, 1008). Runtime never checks `is_archived`, so existing run configs keep working.
- **UI:** an AppPage `action_buttons` "Archive"/"Unarchive" entry with `loading`, an error `Warning`, a `Warning` banner while archived (skills/[p]/[id]/+page.svelte:144-187; code_tools/[id]/+page.svelte:69-95, 235-256); lists filter or dim archived items (docs/rag_configs/[p]/+page.svelte:69-77; skills/[p]/+page.svelte:144-165 with an "Archived" badge); `lib/ui/table_toolbar.svelte` (`action_type="archive"`, `show_archived`) used by the specs list.
- The prompts list (`UI/prompts/[project_id]/[task_id]/+page.svelte`) also shows frozen run-config prompts (`task_run_config::…`), built in `get_prompts` (K/prompt_api.py:251-291). The picker is `app/web_ui/src/lib/ui/run_config_component/prompt_type_selector.svelte` (around line 217).

### Existing in-use-check patterns
- Eval input delete: `eval_input_references()` + `references_conflict_detail()` (S/eval_api.py:212-276) count references and return a 409 naming the counts and the alternative. Best template for the new checks.
- OpenEnv server delete: inline count + 409 (S/openenv_server_api.py:217-240).
- Run delete: 409 for eval traces (`EVAL_TRACE_DELETE_MESSAGE`, K/run_api.py:553-554), and collected failure reasons for bulk delete (667+).
- Immutable-by-API: `editable_prompt_from_id` (K/prompt_api.py:68-82), frozen `turn_mode` (D/task.py:182-186), schema block in task PATCH (task_api.py:137-141), set-once `train_set_filter_id` (eval_api.py:2181-2192).
- Cascade-archive on delete: task delete archives kiln_task tools pointing at it (task_api.py:187-200).

There is no shared helper that scans run configs for a prompt id or tool id. Every fail-if-in-use fix needs one: scan `task.run_configs()` and each `finetune.run_config` across `project.tasks()`, plus code-tool and code-eval allowlists.
