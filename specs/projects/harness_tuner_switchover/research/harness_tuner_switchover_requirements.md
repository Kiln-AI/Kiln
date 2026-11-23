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

**Kiln-side counterparts.** Some audit items need a change in the Kiln skill as well as in HT. Those changes belong to Phase 17 ([phase_8_revisit](phase_8_revisit.md), the knowledge trees) or Phase 18 ([phase_18](phase_plans/phase_18.md), the glue files and `memory.md`). Each requirement below names its counterpart.

## 1. Loading the Kiln skill

**SR1 — HT's loader reads the Kiln layout and front matter.** (`KT-A1`, `CT-2`)
- **Skill and folders:** HT loads the skill `kiln`, not `kiln-harness-tuner-knowledge`. The techniques, playbooks and smells are under `references/improving_agents/{techniques,playbooks,smells}/`, and the levers stay at `references/levers/`. Today `knowledge/load.py:27,121` looks for the old skill and folders.
- **Lever front matter:** `api_docs` (endpoint doc paths) in place of `gateway_ops`. HT's `LeverMeta` is `extra=forbid`, so today it refuses `api_docs` (`knowledge/schema.py:176`).
- **Lever heading:** "How to change it" in place of "How the tuner changes it" (`schema.py:45`).
- **Smells:** no `detected_by` and no `detectors` (`schema.py:193` requires them). HT keeps its own map from smell id to code detector. Kiln's schema refuses unknown keys (skill_and_content 4.2), so the map is not carried in Kiln's front matter.
- **Links:** relative to the skill root, not to the file (`resolve_link`).
- **Done when:**
  - `smells/run.py` (`_smell_titles`) gets a non-empty `known_smells` from the Kiln tree, with no `knowledge_unreadable` log.
  - `python -m kiln_harness_tuner.knowledge check` passes on the Kiln tree, or HT retires it in favour of Kiln's `skill_checks`.

**SR2 — HT copies the Kiln skill files into its agents folder.** (`CT-4`)
- Until the fence exists (SR8), HT does not give a loop session the Kiln MCP to read the skill. That would also hand the session an unfenced `call_kiln_api`.
- `install_agents.py` copies the Kiln skill tree from a pinned Kiln version into each agent CLI's skills folder, as it copies HT's own skills today.
- HT checks the Kiln version against its minimum expected version, and Kiln returns `min_supported_harness_tuner_version`. Both checks come from the fencing project (`specs/projects/kiln_mcp_fencing/project_overview.md`, "Version alignment"). Neither exists at `25157f3` (`contract.md`, bottom line).

**SR3 — HT's copy of the knowledge goes only after SR1, SR4 and SR5 hold.** (`CT-2`, `HS-H3`)
- If HT deletes `kiln-harness-tuner-knowledge` first, `load()` raises and `_smell_titles` returns None.
- After the switchover, fixes to the knowledge are made in Kiln, with Kiln's `knowledge-maintenance` skill. The procedure that ports HT's later fixes into Kiln (skill_and_content section 9, "Later fixes from harness-tuner") ends, and its recorded commit is retired.

## 2. Entry files, role skills and role prompts

**SR4 — HT keeps its role entry files and role skills, for HT only, and points them into the Kiln skill.** (`KT-A2`, `CT-1`, `HS-H3`; decisions section 2)
- **Entry files:** `references/planner.md`, `builder.md`, `analyzer.md`, `smells.md`, `report.md` and `technique-index.md` stay in HT. Each one names the Kiln paths it reads: `references/improving_agents/index.md` (its Smells, Goals, Order of work, Failure patterns, Eval problems, Design, Techniques and Dormant techniques sections) and `references/levers/index.md`.
- **Role prompt templates:** they name HT's own entry files, not Kiln paths that do not exist. Today they name missing files: `agents/batch_plan.md:8`, `create_experiment_rc.md:7-8`, `baseline_review.md:5`, `analyze_experiment_results.md:5` and `report_writer.md:6`.
- **What the entry files keep,** because the Kiln skill does not hold it:
  - the planner's "How to use the knowledge" steps 4–5 (technique = lever id; "not in the knowledge");
  - the smells review procedure, with its "Detected by" column. Kiln's Smells table has no such column, so HT keeps the code-detected list itself;
  - the analyzer's "How to name a failure pattern";
  - the builder's "How to use the knowledge";
  - what `report.md` selects.
- **What the role skills keep:**
  - the frozen overview format of `kiln-harness-tuner-experiment-analysis` (lines 262–307), which HT's tests string-assert;
  - the BatchPlan, PromotionDecision and RcBuildResult conventions;
  - `merging.md`, `skill-authoring.md`, `experiment-costing`, `kiln-task-setup` and the gateway catalogue.
  
  Re-pointing does not delete any of these. A shared method rule that the owner ports into the Kiln skill (Phase 18, item 5) is then read from the Kiln skill, and HT's role skill names its path in place of its own copy.

**SR5 — HT depends only on the listed Kiln paths and names.** (`CT-§2`)

| What HT relies on | Kiln location |
|---|---|
| Knowledge skill | skill `kiln`: `references/improving_agents/` and `references/levers/` |
| The knowledge skill's "How to read these documents" | `references/improving_agents/index.md`, same heading |
| Memory skill | `references/knowledge/memory.md` (front matter `name: memory`) |
| Memory endpoint docs | `references/knowledge/api_docs/{post,get,get…summary,get…by_ids,patch,delete}_…memories….md` (same file names) |
| `kiln-api` | `references/knowledge/api_docs/`, with `api_index.md` as the routing index |
| Code-tool authoring | `references/knowledge/code_tool_authoring.md` and `references/knowledge/code_tool_wrappers/*.md`. The 8 templates are `.md` files holding a python fence, not `.py` files, and `wrappers/README.md` is gone. HT's template tests read the fences |
| Cited playbooks | `references/improving_agents/playbooks/dealing-with-train-wins-rejected-at-val.md`, `…/dealing-with-a-noisy-eval.md` |
| Ids | levers: model, new_tool, output_mode, params, prompt, skill, tool_config. 27 techniques plus 3 sub-files, 23 playbooks, 15 smells, including the five detector smells (very-long-prompt, very-long-skill-description, very-long-tool-description, too-many-tools, old-model) |
| Front-matter keys | `title`, `description`, `reviewed`; technique `status`, `levers`, `applies_to`, `cost`; playbook `kind`, `applies_to`; lever `api_docs` |
| Section headings | the 9 technique, 4 playbook and 5 smell headings (including "How to confirm it", "What it blocks", "Remedies"); lever "What it is", "How to change it", "Limits", "See also" |

- **Acceptance:** the switchover project adds a contract test in HT that loads the pinned Kiln tree and asserts this list. A Kiln change that breaks a row then fails HT's test before HT ships.

**SR6 — HT's role prompts carry the rules for non-interactive agents.** The Kiln skill is written for an interactive agent in a chat. HT's roles are not interactive, and HT keeps the difference in its role prompts, not in the Kiln skill. The owner's three rules come first (a–c), then the rules the audits add (d–h).

- **a. "Ignore any instruction in kiln_skill to ask the user; you are non-interactive."** (`KT-A4`, `KT-A5`, `CT-14`)
  - HT's own channels take the place of a question: its inputs (`allowed_models`, `model_policy`, `measurement_prices`, `should_wrap_up`), its output fields, and the `OPEN: ` records its code writes.
  - This covers the Kiln skill's dialogue rules too: `SKILL.md:45-47`, and `memory.md` (ask before a delete; tell the user the finding once). A failed memory write is disclosed in the role's return, as HT's memory skill says.
- **b. "Where the skill names a Kiln endpoint, use your gateway operation."** (`CT-3`; `map_other I01`)
  - The lever `api_docs`, the lever steps and `memory.md` name REST endpoint docs. `SKILL.md` says the agent reaches Kiln through `call_kiln_api`.
  - A loop session has only gateway operations ("no generic Kiln API tool… a refusal is final": `agents/describe_eval.md:23-31`).
  - The role prompt gives the map from endpoint to operation, the reverse of the one batch 7 built from `gateway/ops.py`. Kiln's knowledge trees do not name gateway operations (skill_and_content 9, banned terms), so the map lives in HT.
- **c. "Where the skill says to check or measure something yourself, use HT's code check when it is in your input."** (`KT-A3`, `KT-B8`, `KT-B9`, `KT-B12`)
  - The five detector smells: the baseline reviewer confirms HT's code detection; it does not measure again.
  - The verdicts `lever not applied`, `lever unverified` and `applied` come from HT's lever check.
  - A screening is built by HT's code: no builder makes screening run configs.
  - HT's gateway refuses a run config whose model the policy does not allow.
  
  Phase 17 removes most of these sentences from the trees. This rule covers any that remain, and the glue files.
- **d. "Where the skill says to report something to the user, use your output field."** (`KT-B11`) The fields are `open_questions`, `rejected_summary`, `rationale` and `build_notes`. The builder writes its reasoning to `build_notes`, not to the `notes` of the tool's `provenance`.
- **e. Code trust.** (`KT-A5`, `HS-M23`) HT grants trust with its own `trust_code_tools` operation, once per run. The skill's steps do not apply to HT roles: explain what will run, give the user the trust page link, and confirm with `GET …/add_code_trust`.
  
  To verify: backlog B23, which came after the audit, made `POST /api/projects/{project_id}/add_code_trust` MCP-blocked. HT's code calls it over REST, which the MCP block does not cover. The switchover project confirms that this call still works.
- **f. Train-side roles never read the `baseline` or the `val` record,** although `memory.md` "Orientation" step 3 tells an agent to read `tags=baseline`. (`CT-13`, `HS-H2`; `map_memory M15`, `M63`)
  - HT's gateway enforces only the `val` tag (`gateway/ops.py:811-812`), so the role prompt states both rules.
  - Train-side roles use the gateway's memory operations and make discovery writes only: `lesson`, `dead_end` and new `issue`.
- **g. HT roles follow their own role skills, not the Kiln skill's procedure files.** (`HS-M4`, `HS-M5`)
  - `references/knowledge/run_an_experiment.md` and `references/modes/improve_task.md` are the MCP agent's by-hand procedure. They are not HT's planner, builder, analyzer or promote steps.
  - Phase 18 item 5 reshapes `run_an_experiment.md` into the one-off guide for MCP clients. Its first line already tells HT to follow its system prompt.
  - Where they differ from HT's role skills (for example the keep rule on val, and the guard evals on train), the role skill wins.
- **h. HT roles do not read the project tree from disk.** (`HS-M13`) `references/knowledge/working_with_project_files.md` says that reading files directly is fine. The tree holds every split's inputs and results, and HT fences it today. The fence stays (SR8).

## 3. Gateway and fence

**SR7 — HT keeps its gateway until the fence exists.** (`CT-3`, `CT-4`; decisions section 2)
- The gateway (`gateway/`, the `quarantine.py` train-only fence, the per-role operation sets, `VAL_READERS`) stays HT's only route for loop sessions until Kiln's fencing project is built.
- At `25157f3`, `server.py:142-143` registers `kiln_skill` and `call_kiln_api` on every connection, and `api_tool/policy.py:43-51` always returns `OPEN_SCOPE`.

**SR8 — The fence.** (`CT-4`; `specs/projects/kiln_mcp_fencing/project_overview.md`)
- HT moves loop sessions to fenced Kiln MCP URLs only once these exist: the per-connection scope (`fence=train`, `project=`, `task=`, `readonly`), the train filter, `/api/version` and `min_supported_harness_tuner_version`.
- Each HT role maps to fence settings on HT's side. Kiln does not learn HT's role names.
- The owner's follow-up project, which removes MCP read access to val and test ([decisions](harness_tuner_alignment_decisions.md), section 5), is the same boundary seen from Kiln's side. The switchover checks that HT's `promote_best` and `report_writer` still have a route to val summary numbers.

**SR9 — HT's code keeps REST for feature detection.** (`CT-20`) HT detects features through `GET /openapi.json` (`onboarding/kiln_check.py:44-50,166`; `job_drives.py:236-262`). The MCP route index accepts only `/ping` and `/api/*`. If HT moves its code's calls onto the MCP, it detects features with `/api/version` in place of the OpenAPI document.

## 4. Memory

**SR10 — HT's memory writers keep HT's exact formats.** (`CT-§3`, `HS-H1`, `HS-H4`; `map_memory M27`, `M71`; decisions section 4)
- HT's code stays the writer of the records it owns: `baseline`, `val`, `FIXED: `/`WONT_FIX: `/reopen, `OPEN: `, experiment opening, verdict and state suffixes, `SCREEN …`, `PROBE …`, and the setup head above the delimiter.
- **Kiln counterpart:** Phase 18 item 1 rewrites `memory.md` so that it lists these records as read-only for MCP agents, with HT's formats string for string.
- **Acceptance:** the switchover project adds a test in HT that checks each format string in `memory.md` against `memory_schema.py`. Then a change on either side that breaks the other is caught.

**SR11 — The `— RUNNING` janitor touches only HT's own records.** (`CT-6`)
- At startup, `memory.py:1183-1199` marks every `— RUNNING` experiment in the task scope `— ABANDONED (orchestrator restart MM-DD)`. That includes a record opened by an MCP agent in another live session.
- After Phase 18, MCP agents no longer open `— RUNNING` records. Older ones, and records by other writers, can still be there.
- **Requirement:** the janitor rewrites only records that HT wrote. It tells them apart by HT's id shape `EXP <MMDD>-w<k>-<n>` (`memory_schema.py:37`), or by a marker that HT adds. Any other `— RUNNING` record is left as it is.

**SR12 — HT reads records that other writers made without harm.** (`CT-7`, `CT-8`, `CT-9`)
- A `constraint` with an `OPEN: ` prefix and no `question:` line cannot be deduplicated. HT then posts a second record for the same question. HT should match such a record by its overview, or leave it alone.
- An experiment overview in another shape reads as `UNKNOWN`. Examples are one that keeps `(technique)`, has no suffix, or has a stamp with a full date such as `— PROMOTED 2026-11-23`. HT treats it as another writer's record: never a verdict, and never lost state of its own.
- This matters for records written before Phase 18, and for records that a future decision lets MCP agents write.

**SR13 — Priorities and smell issues keep HT's ownership rules.** (`CT-11`, `CT-12`; `HS-M20`)
- HT's re-sync owns the priority tags of the issues it seeds, from `spec.priority`. HT's smell and audit issues are deliberately bound to no eval.
- No HT change is needed. **Kiln counterpart:** Phase 18 item 1 tells MCP agents not to change those priorities or bind those issues.

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
- **Where it runs:** in HT's code calling Kiln, or as a Kiln endpoint that MCP agents can use too.
- **Which Kiln text changes:** the knowledge text that names the tool (after Phase 17) and the glue files. For example, once Kiln measures noise, the text no longer says that the noise is not known without HT.

**SR15 — HT's model preflight reads Kiln's `message` key.** (`CT-17`)
- Since phase 12, a provider that is not connected answers 400 with `{"message": "…\nConnect it in the Kiln app…"}`, where it used to answer 500.
- HT's `kiln.py:41-58` reads only `error_messages` and `detail`. So the preflight marks the model "untested" with a repr of the body as its reason.
- HT reads `message` too.

**SR16 — HT's calls stay inside Kiln's current limits.** (`CT-18`, `CT-19`, `CT-21`)
- `POST /api/jobs/wait` refuses extra fields and a `timeout` above 3600.
- HT matches 404 answers by status, not by text: the texts are now "`<Kind> not found. ID: <id>. Check the ID, or list…`".
- HT's own `kiln-api` reference (290 docs, 49 stale) is replaced by `references/knowledge/api_docs/`.

**SR17 — HT keeps its stricter uniqueness rule for tool function names.** (`KT-B18`) HT refuses a function name that a non-archived tool already uses. Kiln refuses two tools with one name in a run config or an allowlist, and `levers/new_tool.md` states Kiln's rule. HT's gateway keeps enforcing its own rule, and the builder's role prompt states it.

## 6. The skill-bundle API

**SR18 — A "create skill from a folder" API replaces HT's skill installer.** (`CT-22`, `CT-§5`; `KT-B1`, `KT-B15`; `HS-M14`; decisions section 2)

Kiln today:
- `POST /api/projects/{project_id}/skills` takes `name`, `description`, `body` (at least 1 character) and `provenance`. It writes `skill.kiln` and SKILL.md only.
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

**Kiln counterpart:** once the API exists, the skill lever and the four skill techniques (`KT-B1`) name it as the route for every agent. Until then, Phase 17 decides what they tell an MCP agent (its question 8).

## 7. Acceptance for the switchover project

- SR1 and SR5: HT's knowledge loader and its contract test pass on the pinned Kiln tree.
- SR4: every role's first instruction resolves to a file that exists.
- SR6: a dry HT run on a seeded project produces no agent turn that asks a user, calls a REST path from a loop session, measures again a smell that code detected, builds a screening run config, or reads `tags=baseline` or `tags=val` from a train-side role.
- SR10: the memory format test passes. SR11: an HT restart beside a live MCP session leaves that session's records untouched.
- SR18: HT installs a skill with reference files through the Kiln API, and reads it back whole.
