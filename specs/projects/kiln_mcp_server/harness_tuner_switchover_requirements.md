---
status: draft
---

# Harness Tuner switchover: requirements

These are the requirements for the **switchover project**, a separate project that updates Kiln Harness Tuner (HT) so that it uses the Kiln skill in place of its own `kiln-harness-tuner-knowledge` copy. This project does not build any of them. They are written down here so that this project and the switchover project agree on the boundary ([decisions](harness_tuner_alignment_decisions.md), sections 1 and 2).

- **The bar for this project:** once HT switches over, its agents get no incorrect guidance from the Kiln skill.
- **The bar for the switchover project:** HT works on the Kiln skill. HT is not expected to switch over without changes on its side; this document lists those changes.

**Citations.** Each requirement cites its audit item, all in `research/harness_tuner_alignment_audit/`:
- `KT-` is `knowledge_tree.md` (for example `KT-A1`).
- `CT-n` is row n of the table in section 1 of `contract.md`; `CT-§n` is a section of that file.
- `HS-` is `ht_skills.md` (for example `HS-H2`).
- `map_<name> Xnn` is a row of a file in `ht_skills_maps/`.
- Backlog items are written `backlog B23`.

HT paths are under HT's `src/kiln_harness_tuner/` at `b49f159`. Kiln skill paths are from the skill root, `app/mcp/kiln_mcp_server/skill/`.

**Kiln-side counterparts.** Some audit items need a change in the Kiln skill as well as in HT. Those changes were made in Phase 17 ([phase_8_revisit](phase_8_revisit.md), the knowledge trees), Phase 18 ([phase_18](phase_plans/phase_18.md), the glue files and `memory.md`), Phase 19 (the costing and task-setup ports), Phase 20 (the ports of `memory.md`, `code_tool_authoring.md` and the API rules of `SKILL.md` again from HT's text) and Phase 21 (one skill for many kinds of client: the chat client guidance moves to `references/client_guidance/chat/`, and the API rules to their own file; SR19). Each requirement below names its counterpart.

**Phase 20 re-check.** HT worked with its own skills, so a requirement that HT must change for HT to work holds only where HT's code at `b49f159` proves it. Phase 20 re-checked every requirement against HT's code ([decisions](harness_tuner_alignment_decisions.md) section 14). The requirements it dropped keep their numbers, with a one-line note.

## 1. Loading the Kiln skill

**SR1 — HT's loader reads the Kiln layout and front matter.** (`KT-A1`, `CT-2`)
- **Skill and folders:** HT loads the skill `kiln`, not `kiln-harness-tuner-knowledge`. The techniques, playbooks and smells are under `references/improving_agents/{techniques,playbooks,smells}/`, and the levers stay at `references/levers/`. Today `knowledge/load.py:27,121` looks for the old skill and folders.
- **Lever front matter:** `api_docs` (endpoint doc paths) in place of `gateway_ops`. HT's `LeverMeta` is `extra=forbid`, so today it refuses `api_docs` (`knowledge/schema.py:176`).
- **Lever heading:** "How to change it" in place of "How the tuner changes it" (`schema.py:45`).
- **Smells:** no `detected_by` and no `detectors` (`schema.py:193` requires them). HT keeps its own map from smell id to code detector. Kiln's schema refuses unknown keys (skill_and_content 4.2), so the map is not carried in Kiln's front matter.
- **Links:** relative to the skill root, not to the file (`resolve_link`).
- **Done when:**
  - `smells/run.py` (`_smell_titles`) gets a non-empty `known_smells` from the Kiln tree, with no `knowledge_unreadable` log.
  - `python -m kiln_harness_tuner.knowledge check` passes on the Kiln tree, or HT retires it in favour of Kiln's `skill_checks` (the switchover design retires `knowledge/`).

**SR2 — HT reads the Kiln skill files.** (`CT-4`)
- Until the fence exists (SR8), HT does not give a loop session the Kiln MCP to read the skill. That would also hand the session an unfenced `call_kiln_api`.
- How HT reads the files is the switchover's design: a live read of `kiln_skill` through one reader that the gateway and the loop code share (`specs/projects/harness_tuner_switchover/architecture.md`, section 3, decisions 1 and 2). Phase 20 dropped this project's earlier "copy a pinned tree into each agent CLI's skills folder", which the switchover does not do.
- HT checks the Kiln version against its minimum expected version, and Kiln returns `min_supported_harness_tuner_version`. Both checks come from spec two (`specs/projects/harness_tuner_switchover/project_overview.md`, "Version alignment"). Neither exists at `25157f3` (`contract.md`, bottom line).

**SR3 — HT's copy of the knowledge goes only after SR1, SR4 and SR5 hold.** (`CT-2`, `HS-H3`)
- If HT deletes `kiln-harness-tuner-knowledge` first, `load()` raises and `_smell_titles` returns None.
- After the switchover, fixes to the knowledge are made in Kiln, with Kiln's `knowledge-maintenance` skill. The procedure that ports HT's later fixes into Kiln (skill_and_content section 9, "Later fixes from harness-tuner") ends, and its recorded commit is retired.

## 2. Entry files, role skills and role prompts

**SR4 — HT keeps its role entry files and role skills, for HT only, and points them into the Kiln skill.** (`KT-A2`, `CT-1`, `HS-H3`; decisions section 2)
- **Entry files:** `references/planner.md`, `builder.md`, `analyzer.md`, `smells.md`, `report.md` and `technique-index.md` stay in HT. Each one names the Kiln paths it reads: `references/improving_agents/index.md` (its Smells, Goals, Order of work, Failure patterns, Eval problems, Design, Techniques and Dormant techniques sections) and `references/levers/index.md`.
- **Role prompt templates:** they name HT's own entry files, not Kiln paths that do not exist. Today they name the files of the `kiln-harness-tuner-knowledge` skill, which the switchover deletes: `agents/batch_plan.md:8`, `create_experiment_rc.md:7-8`, `baseline_review.md:5`, `analyze_experiment_results.md:5` and `report_writer.md:6`.
- **What the entry files keep,** because the Kiln skill does not hold it:
  - the planner's "How to use the knowledge" steps 4–5 (technique = lever id; "not in the knowledge"). The Kiln skill holds the same two rules, in `references/improving_agents/index.md`, "How to read these documents" ("How to work through a playbook", step 3, and the `technique` paragraph after it), since Phase 17. So the planner may keep its copy or point there; this item is not a gap in the Kiln skill;
  - the smells review procedure, with its "Detected by" column. Kiln's Smells table has no such column, so HT keeps the code-detected list itself;
  - the analyzer's "How to name a failure pattern";
  - the builder's "How to use the knowledge";
  - what `report.md` selects.
- **What the role skills keep:**
  - the frozen overview format of `kiln-harness-tuner-experiment-analysis` (lines 262–307), which HT's tests string-assert;
  - the BatchPlan, PromotionDecision and RcBuildResult conventions;
  - `merging.md`, `skill-authoring.md` and the gateway catalogue.
  - Not `experiment-costing` and `kiln-task-setup`: Phase 19 ports both into the Kiln skill (SR5), and the role skills that load them name those Kiln files.
  - HT's `experiment-costing` is wrong for Kiln's code in two places, and Kiln's port is corrected ([decisions](harness_tuner_alignment_decisions.md) section 13): the synthetic user's usage is on the scored TaskRun, not on the eval row, and Kiln has no `custom`-score metric eval. HT's role skills that rely on either read Kiln's port instead.
  - No gateway field is required for the port. HT's own costing text read `eval_usage` and `synthetic_user_usage` off per-item rows that its gateway never returned (`TrainResultRow`, `gateway/models.py:300-315`, has only `task_cost_usd`), and HT worked: its code measures the cost itself. Phase 20 dropped the earlier requirement that `get_task_run` add `synthetic_user_usage` and `cumulative_usage` (decisions section 14).
  
  Re-pointing does not delete any of these. A shared method rule that the owner ports into the Kiln skill (Phase 18, item 5) is then read from the Kiln skill, and HT's role skill names its path in place of its own copy.

**SR5 — HT depends only on the listed Kiln paths and names.** (`CT-§2`)

| What HT relies on | Kiln location |
|---|---|
| Knowledge skill | skill `kiln`: `references/improving_agents/` and `references/levers/` |
| The knowledge skill's "How to read these documents" | `references/improving_agents/index.md`, same heading |
| Memory skill | `references/knowledge/memory.md` (front matter `name: memory`) |
| Memory endpoint docs | `references/knowledge/api_docs/{post,get,get…summary,get…by_ids,patch,delete}_…memories….md` (same file names) |
| `kiln-api` | `references/knowledge/api_docs/`, with `api_index.md` as the routing index, and the rules for every call in `references/knowledge/api_docs/calling_the_kiln_api.md` (since Phase 21; before, `SKILL.md`, "Calling the Kiln API") |
| Code-tool authoring | `references/knowledge/code_tool_authoring.md` and `references/knowledge/code_tool_wrappers/*.md`. The 8 templates are `.md` files holding a python fence, not `.py` files, and `wrappers/README.md` is gone. HT's template tests read the fences |
| `experiment-costing` | `references/knowledge/experiment_costing.md` |
| `kiln-task-setup` | `references/knowledge/create_task.md`, `references/knowledge/model_create_configs.md`, `references/knowledge/tools.md`, `references/knowledge/adding_skills.md`, `references/knowledge/prompt_rewrite.md` |
| Cited playbooks | `references/improving_agents/playbooks/dealing-with-train-wins-rejected-at-val.md`, `…/dealing-with-a-noisy-eval.md` |
| Ids | levers: model, new_tool, output_mode, params, prompt, skill, tool_config. 27 techniques plus 3 sub-files, 22 playbooks, 15 smells, including the five detector smells (very-long-prompt, very-long-skill-description, very-long-tool-description, too-many-tools, old-model) |
| Front-matter keys | `title`, `description`, `reviewed`; technique `status`, `levers`, `applies_to`, `cost`; playbook `kind`, `applies_to`; lever `api_docs` |
| Section headings | the 9 technique, 4 playbook and 5 smell headings (including "How to confirm it", "What it blocks", "Remedies"); lever "What it is", "How to change it", "Limits", "See also" |

- **Pinned headings follow the Kiln skill's current ones.** The switchover's contract pins headings in its `components/ht_skill_reading_and_roles.md:480-481` (section 8), and this project never edits that spec. Phase 20 restored HT's own headings, so the contract must use these:
  - `references/knowledge/memory.md`: "Tags" is now "Tags — seed vocabulary (8 + priorities)", and its column "Who writes" is now "Write when".
  - `references/knowledge/code_tool_authoring.md`: "Wrapper templates" is now "Wrapper templates — bake it into code first", and "The allowlist rule" is now "The one hard rule: allowlist hygiene".
- **Paths that Phase 21 changed.** None of the contract's `paths` or `ids` moved. These did, and HT's text or the switchover's Kiln-side edits (its `components/kiln_smells_skills_version.md`, section 7) may name them:
  - `references/knowledge/run_an_experiment.md` → `references/client_guidance/chat/running_an_experiment_from_chat.md` (same headings; its first line is now the chat line of SR19).
  - `references/modes/establish_intent.md`, `project_operations.md`, `improve_task.md` and `learn_about_kiln.md` → the same names in `references/client_guidance/chat/`. `references/modes/` is gone.
  - `references/knowledge/freeform_help.md` → `references/client_guidance/chat/freeform_help.md`.
  - `SKILL.md`, "Calling the Kiln API" → `references/knowledge/api_docs/calling_the_kiln_api.md`, word for word, minus "Keep the user in the loop".
  - `SKILL.md`, "Routing", "Working with the user", "Links into the app" and "What you cannot do over this connection", and "Keep the user in the loop" → `references/client_guidance/chat/using_kiln_from_chat.md`, same headings.
  - `references/improving_agents/index.md`, "How to read these documents over MCP" → `references/client_guidance/chat/using_kiln_from_chat.md`, "How to read the shared documents". The index keeps "How to read these documents", with "How to work through a playbook" in it, which the contract pins.
- **Acceptance:** a contract test asserts this list. The switchover design puts it in Kiln (`app/mcp/kiln_mcp_server/skill_checks/test_harness_tuner_contract.py`, with `harness_tuner_contract.json`; switchover `architecture.md`, sections 2.1 and 4), and HT's start-up check reads each path. A Kiln change that breaks a row then fails before it ships.

**SR6 — HT's role prompts carry the rules for non-interactive agents.** The Kiln skill's shared files serve every kind of client, and some keep a rule for a chat with a user. Since Phase 21, `SKILL.md` gives a non-interactive agent with its own instructions its general rules (SR19). HT's roles are not interactive, and HT keeps the detail of the difference in its role prompts, not in the Kiln skill. The owner's three rules come first (a–c), then the rules the audits add (d–h).

- **a. "Ignore any instruction in kiln_skill to ask the user; you are non-interactive."** (`KT-A4`, `KT-A5`, `CT-14`)
  - HT's own channels take the place of a question: its inputs (`allowed_models`, `model_policy`, `measurement_prices`, `should_wrap_up`), its output fields, and the `OPEN: ` records its code writes.
  - This covers the Kiln skill's dialogue rules too: "Working with the user" and "Keep the user in the loop", in `references/client_guidance/chat/using_kiln_from_chat.md` since Phase 21 (a file HT's roles do not read, SR19), the Assistant's feature knowledge with its "ask the user" lines, and `memory.md`'s "In a chat with a user" clauses (ask before a delete; tell the user a failed write once). A failed memory write is disclosed in the role's return, as `references/knowledge/memory.md`, "Write discipline", says: HT's own rule, ported in Phase 20.
- **b. "Where the skill names a Kiln endpoint, use your gateway operation."** (`CT-3`; `map_other I01`)
  - The lever `api_docs`, the lever steps and `memory.md` name REST endpoint docs. `references/knowledge/api_docs/calling_the_kiln_api.md` applies only to an agent that has `call_kiln_api`, and says that HT's loop agents do not.
  - A loop session has only gateway operations ("no generic Kiln API tool… a refusal is final": `agents/describe_eval.md:23-31`).
  - The role prompt gives the map from endpoint to operation, the reverse of the one batch 7 built from `gateway/ops.py`. Kiln's knowledge trees do not name gateway operations (skill_and_content 9, banned terms), so the map lives in HT.
- **c. "Where the skill says to check or measure something yourself, use HT's code check when it is in your input."** (`KT-A3`, `KT-B8`, `KT-B9`, `KT-B12`)
  - The five detector smells: the baseline reviewer confirms HT's code detection; it does not measure again.
  - The verdicts `lever not applied`, `lever unverified` and `applied` come from HT's lever check.
  - A screening is built by HT's code: no builder makes screening run configs.
  - HT's gateway refuses a run config whose model the policy does not allow.
  
  Phase 17 removed most of these sentences from the trees. This rule covers any that remain, and the glue files.
- **d. "Where the skill says to report something to the user, use your output field."** (`KT-B11`) The fields are `open_questions`, `rejected_summary`, `rationale`, `build_notes`, `findings` and the report. The builder writes its reasoning to `build_notes`, not to the `notes` of the tool's `provenance`.
- **e. Code trust.** (`KT-A5`, `HS-M23`) HT grants trust with its own `trust_code_tools` operation, once per run. The skill's steps do not apply to HT roles: explain what will run, give the user the trust page link, and confirm with `GET …/add_code_trust`.
  
  To verify: backlog B23, which came after the audit, made `POST /api/projects/{project_id}/add_code_trust` MCP-blocked. HT's code calls it over REST, which the MCP block does not cover. The switchover project confirms that this call still works.
- **f. Dropped in Phase 20.** It asked the role prompts to state that train-side roles never read `baseline` or `val`. HT's memory text states both rules, and `memory.md` carries them again since Phase 20 ("Orientation" step 3, the `baseline` and `val` rows).
- **g. Dropped in Phase 20.** No HT change is needed: HT's role skills hold its procedure, and no HT text names `references/knowledge/run_an_experiment.md` or `references/modes/`. Since Phase 21 the file is `references/client_guidance/chat/running_an_experiment_from_chat.md`; the trees name it only after "In a chat with a user", and its first line tells a non-interactive agent that it does not need the file (SR19).
- **h. HT roles do not read the project tree from disk.** (`HS-M13`) `references/knowledge/working_with_project_files.md` says that reading files directly is fine. The tree holds every split's inputs and results, and HT fences it today. The fence stays (SR8).

## 3. Gateway and fence

**SR7 — HT keeps its gateway until the fence exists.** (`CT-3`, `CT-4`; decisions section 2)
- The gateway (`gateway/`, the `quarantine.py` train-only fence, the per-role operation sets, `VAL_READERS`) stays HT's only route for loop sessions until Kiln's fencing project is built.
- At `25157f3`, `server.py:142-143` registers `kiln_skill` and `call_kiln_api` on every connection, and `api_tool/policy.py:43-51` always returns `OPEN_SCOPE`.

**SR8 — The fence.** (`CT-4`; `specs/projects/harness_tuner_port/project_overview.md`)
- HT moves loop sessions to fenced Kiln MCP URLs only once these exist: the per-connection scope (`fence=train`, `project=`, `task=`, `readonly`), the train filter, `/api/version` and `min_supported_harness_tuner_version`.
- Each HT role maps to fence settings on HT's side. Kiln does not learn HT's role names.
- The owner's follow-up project, which removes MCP read access to val and test ([decisions](harness_tuner_alignment_decisions.md), section 5), is the same boundary seen from Kiln's side. The switchover checks that HT's `promote_best` and `report_writer` still have a route to val summary numbers.

**SR9 — HT's code keeps REST for feature detection.** (`CT-20`) HT detects features through `GET /openapi.json` (`onboarding/kiln_check.py:44-50,166`; `job_drives.py:236-262`). The MCP route index accepts only `/ping` and `/api/*`. If HT moves its code's calls onto the MCP, it detects features with `/api/version` in place of the OpenAPI document.

## 4. Memory

**SR10 — HT's memory writers keep HT's exact formats.** (`CT-§3`, `HS-H1`, `HS-H4`; `map_memory M27`, `M71`; decisions section 4)
- HT's code stays the writer of the records it owns: `baseline`, `val`, `FIXED: `/`WONT_FIX: `/reopen, `OPEN: `, experiment opening, verdict and state suffixes, `SCREEN …`, `PROBE …`, and the setup head above the delimiter.
- **Kiln counterpart:** Phase 18 item 1 and Phase 20 made `memory.md` list these records as read-only for chat clients. HT's formats, string for string, are in the files of `references/knowledge/memory_formats/`, which `memory.md` names.
- **Acceptance:** the switchover project adds a test in HT that checks each format string in the `memory_formats/` files against `memory_schema.py`. Kiln's `HARNESS_TUNER_FORMATS` in `skill_checks/test_shipped_skill.py` lists the strings. Then a change on either side that breaks the other is caught.

**SR11 — Dropped in Phase 20.** It asked that the `— RUNNING` janitor (`memory.py:1183-1199`) spare other writers' records. The Kiln skill adds no writer of these records: chat clients never write `experiment` records ([decisions](harness_tuner_alignment_decisions.md) section 11.4), and no released Kiln skill told them to. HT's own interactive install (`harness-tuner-install-agents --dest`), which had one, goes in the switchover (its `architecture.md` decision 15).

**SR12 — Dropped in Phase 20.** It asked HT to read other writers' `OPEN: ` and experiment records without harm. The Kiln skill adds no writer of these records: chat clients write neither (decisions sections 4, 11.3 and 11.4). HT's own interactive install (`harness-tuner-install-agents --dest`), which had one, goes in the switchover (its `architecture.md` decision 15).

**SR13 — Priorities and smell issues keep HT's ownership rules.** (`CT-11`, `CT-12`; `HS-M20`)
- HT's re-sync owns the priority tags of the issues it seeds, from `spec.priority`. HT's smell and audit issues are deliberately bound to no eval.
- No HT change is needed. **Kiln counterpart:** `memory.md` (Phase 18 item 1, Phase 20) tells chat clients not to change those priorities or bind those issues.

## 5. HT's tools come over

**SR14 — The switchover project brings over HT's measurement and check tools.** (`CT-§4`; `KT-B2`, `KT-B3`, `KT-B4`, `KT-B7`, `KT-B9`; decisions section 2)

The owner named: noise, detectability, screening, model preflight, integrity, judge-copy and reference check.

| HT module | What it measures | Kiln today |
|---|---|---|
| `noise.py` (`--noise-check N`) | Run-to-run noise: re-drive and re-judge N train items through a clone; the flip rate (`train_noise`, `noise_adjusted_wins`) | None. `POST /api/statistics` is the paired test, not a repeat-noise measure |
| `detectability.py` | Per eval and score: `room` and `floor` (McNemar 2·0.5^k, Wilcoxon; floor 6 for pass/fail) | None. Room is a count over the train results endpoint |
| `viability.py`, `measure.py`, `stop_rules.py`, `estimate.py` | Successive-halving screening, stratified estimates, early stops | None |
| `model_preflight.py` | One test call per allowed model | Partial: model info `status`; `POST …/run` for a test call |
| `integrity.py`, `judge_copy.py`, `reference_check.py`, `generality.py` | Reward hacking, copied judge text (a run of 8 or more words), dangling references, leaks | None; `train_val_test.md` tells the agent to check by hand |

The contract audit's table also lists `latency.py`, `objective.py`, `budget.py`, `probes.py`, `levers.py`, the five smell detectors and model age. The switchover project decides each with the ones above. For each tool it decides:
- **Where it runs:** in HT's code calling Kiln, or as a Kiln endpoint that chat clients can use too.
- **Which Kiln text changes:** the knowledge text that names the tool (after Phase 17) and the glue files. For example, once Kiln measures noise, the text no longer says that the noise is not known without HT.

**SR15 — Dropped in Phase 20.** It asked HT's model preflight to read Kiln's `message` key. It already does: its text comes from `job_drives.error_text`, which reads `message` first (`job_drives.py:153`; `model_preflight.py:72,313`).

**SR16 — Dropped in Phase 20.** It asked HT's calls to stay inside Kiln's limits. They do: `POST /api/jobs/wait` gets only `ids` and a `timeout` within Kiln's cap of 3600 (1800 in `job_drives.py:61,365`; 3600 in `analysis.py:98,1568`), and HT matches 404 by status (`setup.py:342`; `gateway/ops.py:937`). The replacement of HT's `kiln-api` reference is SR5's `kiln-api` row.

**SR17 — Dropped in Phase 20.** It said HT's gateway keeps a stricter function-name rule. HT's gateway has no such rule. HT's sentence "Duplicate non-archived function names are rejected (400)" is wrong for Kiln, and `references/knowledge/code_tool_authoring.md` states Kiln's rule (decisions section 14).

## 6. The skill-bundle API

**SR18 — A "create skill from a folder" API replaces HT's skill installer.** (`CT-22`, `CT-§5`; `KT-B1`, `KT-B15`; `HS-M14`; decisions section 2)

Kiln today:
- `POST /api/projects/{project_id}/skills` takes `name`, `description`, `body` (at least 1 character) and `provenance`. It writes `skill.kiln`, SKILL.md and empty `references/` and `assets/` folders (`Skill.save_skill_md`, `libs/core/kiln_ai/datamodel/skill.py`), and no reference file.
- `GET …/skills/{id}/content` returns only `skill_md` and `body`.
- So a new version made over the API loses its reference files.

HT today (`skill_installer/bundle.py`, `skill_installer/mcp_server.py`, `prompt_text.py`) writes to disk. The API must do the following, copied from `contract.md` section 5:

**Input**
- **SKILL.md:** front matter with exactly `name` and `description`, no other keys, and a non-empty body.
  - **Name rules:** `^[a-z0-9-]+$`, at most 64 characters, starts with a lowercase letter, no `--`, no leading or trailing `-`, not `skill`.
  - **Description:** 1 to 1024 characters.
- **`references/**`:** nested folders allowed, UTF-8 text only.
- **`assets/**`:** any bytes.
- **Nothing else at the root.** No symlinks, no `skill.kiln` from the caller.
- **Size:** at most 512 KB per file and 2 MB per bundle.
- **Provenance:** non-empty `notes`, `derived_from_ids` (a list of strings), `origin: "agent"`.

**Semantics**
- **Install-once:** a name that already exists, in a `skill.kiln` or a folder suffix, is refused. A new version means a new name.
- **Atomic:** staged, then one rename. A skill either does not exist or exists whole.
- **Ids and files:** the id is minted with Kiln's scheme. SKILL.md is stored byte-identical. `references/` and `assets/` are always created, even when empty.
- **Errors:** every error at once (`{"ok": false, "errors": [...]}`), and nothing is written on a refusal.
- **Success returns:** `skill_id`, `skill_name` and `tool_id` = `kiln_tool::skill::<id>`.

**Transport**
- **Upload the tree:** HT agents write the bundle in a scratch folder that the Kiln server may not be able to read. The API should take the tree itself, either multipart or a JSON map of path to content with binary assets base64-encoded, not a local path.

**Also needed: a read lane**
- **Export a skill:** HT's `export_skill_bundle` returns SKILL.md, `references/**` and `assets/**`, but not `skill.kiln`, up to 4 MB.
- **Read every file of a skill:** `prompt_text.py` reads every reference file and every text asset of attached skills, and code-tool files, for the generality and integrity checks.
- **Effect:** with both, HT can stop reading the project tree from disk.

**Kiln counterpart:** once the API exists, the skill lever, the four skill techniques (`KT-B1`) and `references/knowledge/adding_skills.md` ("`references/*` files have NO API", in "Workflow: create + wire") name it as the route for every agent. Until then they tell a chat client that the work needs Kiln Harness Tuner (Phase 17, question 7).

## 6a. Client guidance

**SR19 — HT's roles never read the chat client guidance.** (Phase 21; [decisions](harness_tuner_alignment_decisions.md) section 15)
- The Kiln skill is one body of knowledge for every kind of client. Guidance only for chat clients is in `references/client_guidance/chat/`, and each file there opens: "For chat clients working with a user. A non-interactive agent with its own instructions does not need this file."
- `SKILL.md`, "Who reads this skill", gives a non-interactive agent with its own instructions its rules: its instructions win on any conflict; it ignores an instruction to ask the user; it does not read `references/client_guidance/chat/`, and if it reads a file there, it fits any lesson to its own process.
- HT's role prompts and role files name no path under `references/client_guidance/`. A shared file names a chat file only in a sentence for a chat with a user (a Kiln test checks the words "in a chat with a user" beside each such path), so a role that follows a link there by mistake is told what it is for.

## 7. Acceptance for the switchover project

- SR1 and SR5: HT reads the Kiln tree, and the contract test passes.
- SR4: every role's first instruction resolves to a file that exists.
- SR6: a dry HT run on a seeded project produces no agent turn that asks a user, calls a REST path from a loop session, measures again a smell that code detected, builds a screening run config, or reads `tags=baseline` or `tags=val` from a train-side role.
- SR19: no HT role prompt or role file names a path under `references/client_guidance/`.
- SR10: the memory format test passes.
- SR18: HT installs a skill with reference files through the Kiln API, and reads it back whole.
