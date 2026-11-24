---
status: complete
---

# Harness Tuner alignment: owner decisions

Recorded 2026-11-23 in three rounds (sections 1–7 first; sections 8 and 9, then section 10, the same day), and on 2026-11-24 (sections 11 to 15), on branch `claude/kiln-mcp-server-impl` at `7af37d1`, after the three Harness Tuner alignment audits in `research/harness_tuner_alignment_audit/` (`knowledge_tree.md`, `ht_skills.md` with `ht_skills_maps/`, `contract.md`). The audits compare Kiln Harness Tuner (HT) at `b49f159` with Kiln at `25157f3`.

These decisions override the audits where the two differ. An audit "Fix" line that adds a branch, a lane, or a write step for a code-owned record is overridden by the decisions below.

The decisions are copied as the owner gave them. Lines marked *Where it goes* are bookkeeping added when they were recorded. Owner quotes before section 11 say "MCP agents" or "MCP clients" for what Phase 21 calls chat clients: Kiln Harness Tuner reads the skill over MCP too (section 15).

## 1. Goal

> This project ports Kiln Harness Tuner's (HT) skill content into the Kiln skill. HT re-points to it later in a separate **switchover project**, which updates HT. This project's bar is: once HT switches over, its agents do not get incorrect guidance from the Kiln skill. HT switching over without changes on its side is not expected.

*Where it goes:* [harness_tuner_switchover_requirements.md](harness_tuner_switchover_requirements.md) lists what the switchover project must do on HT's side.

## 2. Handled by the switchover project, not blocking here

> - HT's loader and prompts adapting to the Kiln skill's layout and front matter (audit "layout" items);
> - the fence (HT keeps its gateway until then);
> - HT's role skills and role entry files stay in HT, for HT only, and were rightly not ported;
> - HT's own tools (noise, detectability, screening, etc.) "are coming over in the next project";
> - the skill-bundle ("create skill from a folder") API.

*Where it goes:* [harness_tuner_switchover_requirements.md](harness_tuner_switchover_requirements.md). This project does not work on any of these.

## 3. Branches

> Minimize them; branch only when necessary. Share as much of HT's work as possible; most rules are shared, and the rules HT invented apply to MCP agents too.

*Where it goes:* Phase 17 (the knowledge trees) and Phase 18 (the glue files). One consequence: a rule that says it "applies when running Kiln Harness Tuner" is a branch, and it is removed wherever the rule can apply to every agent.

## 4. Memory

> `references/knowledge/memory.md` stays a reference for both HT and MCP agents. Records that HT's code writes with strict formats (baseline, val, `FIXED:`/`WONT_FIX:`/reopen, `OPEN:`, experiment states and suffixes, screening, etc.) are listed as read-only, with their formats given for readers, not for writing. MCP agents may write some records — lessons, dead ends, new issues — and more in future. HT already knows how to write, so the doc's formats must match HT's code exactly (the contract audit lists the strings). Write steps for code-owned records are removed from other skill files (e.g. `run_an_experiment.md`).

*Where it goes:* Phase 18 ([phase_plans/phase_18.md](phase_plans/phase_18.md)), items 1 and 2.

## 5. Lanes

> Cut. Do not add an MCP narrow/broad lane. HT enforces its lanes in code. In a follow-up project the owner removes MCP read access to val/test, so MCP agents cannot read them.

*Where it goes:* no work. Audit items `ht_skills.md` M2 and `knowledge_tree.md` C4 (the missing train lane) are closed by this decision. Backlog B13 is proposed for closing in Phase 18 on this basis, and the owner confirms it.

## 6. Batch 8 (commit `919fb6a`, "loop vocabulary in the knowledge trees")

> It put procedural instructions ("ask the user", "measure it yourself", "applies when running Kiln Harness Tuner", dropped HT record strings and check names) into the levers, techniques, playbooks and smells, following the spec's `LOOP_WORDS` table and §4.5. The fix needs a new spec phase: **"Revert and revisit phase 8"**, which requires the owner's approval before any work. Likely approach (to be approved): revert the knowledge trees to batch 7 (`b4b066e`, byte-identical to HT's normalised text), keep only the mechanical changes (root-relative links, `api_docs`) and changes the owner already approved (e.g. the B30 "no sandbox" wording), re-apply better rules, and add one short "how MCP agents read these documents" section to `references/improving_agents/index.md` instead of rewriting 74 files.

*Where it goes:* Phase 17 ([phase_8_revisit.md](phase_8_revisit.md)). The owner approved it on 2026-11-24 (section 12). Backlog B7, B11 and B12 move there.

## 7. Shared method rules that lived only in HT's role skills

> Audit `ht_skills.md` M-items: keep rule on val, exact cost/speed rule, integrity checks at keep, leak/judge-copy definitions, costing lanes and the third-party-operator rule, the quick-check definition, reading results/report wording, the lean-target guard default, merging, build hygiene, playbook-step flow, and the smaller ones. Decided **case by case** by the owner.

*Where it goes:* superseded by decision 9 below. The case-by-case table is replaced by one guide for chat clients.

## 8. Confirmations (2026-11-23, second round)

The owner answered "ok" to three of the decisions above:
- **Memory** (section 4): read-only code-written records; writable lessons, dead ends and issues: "ok".
- **The Phase 8 revert-and-revisit phase** (section 6), which needs the owner's approval before any work: "ok". The approach itself, and the questions in [phase_8_revisit.md](phase_8_revisit.md) section 7, were answered on 2026-11-24 (section 12).
- **Lanes cut** (section 5): "ok".

## 9. One guide for chat clients in place of the case-by-case table (2026-11-23, second round)

The owner's words:

> Let's make a new doc for MCP clients integrating most of these? Something like 'on_off_experimetnation_guide.md' or something like that. It heavily pushes user to harness tuner for advanced optimization (saying it enforces the loop and these principals in code, and is much more robust), but carries the key lessons for more one-off ideas from MCP. It also says 'if you are harness tuner, follow your system prompt. It has similar concepts, but better enforcement.'

The manager's proposal to the owner, confirmed by the owner in section 10:
- Make this guide by reshaping `references/knowledge/run_an_experiment.md`, rather than by adding a second file. Then one file owns the method (C12), and the 25 or so existing links to it stay.
- Rename it to `one_off_experimentation_guide.md` only if the owner prefers.

*Where it goes:* Phase 18 ([phase_plans/phase_18.md](phase_plans/phase_18.md)), item 5. The table of shared method rules, with each rule's HT source and audit id, becomes the guide's content list. Each row is marked "include" by default, for the owner to adjust. The exact cost/speed rule (M1) is one of the rows. Including it removes the "applies when running Kiln Harness Tuner" branch from the file, which replaces the Phase 16 batch 3 decision on B14 ("keep as is").

## 10. The one-off experimentation guide: its file and its content (2026-11-23, third round)

The owner approved the manager's recommendations:
- **The file.** Reshape `references/knowledge/run_an_experiment.md` into the guide, and keep that name. There is no rename to `one_off_experimentation_guide.md`. This confirms the proposal in section 9.
- **The content list.** The "Include / leave out" column of the table in Phase 18 item 5 is set as below. The row ids are the table's: `M` rows are `HS-M` items of `ht_skills.md`, and `S` rows are smaller rules from `ht_skills_maps/`.

| Decision | Rows |
|---|---|
| Include | M1, M5, M6, M7, M9, M10, M12, M18, M21, M22, S3, S5 |
| Include, short form | M4: the headline mean win rate against the baseline, plus no eval clearly down; leave out the priority-weighted gate |
| | M8: keep the third-party operator's agreement rule, the human gate and "judging is paid again on every re-score"; leave out the six-lane detail |
| | M15: keep the writing rules; leave out the provenance and `derived_from_ids` mechanics, which the levers already cover |
| | M17: leave out replicate folding |
| | M19: keep "never carry a magnitude over from another task" and the floor of 6 wins for p < .05; leave out the planning moves |
| Fold into M1 | S4 |
| Move to the "How to read" section of `references/improving_agents/index.md` (Phase 17) | M11 |
| Leave out | M16, keeping one line: "combine by hand; never combine two candidates of one head-to-head group" |
| | S1, S2 |

One question stays open, and Phase 18 asks it (question 9): does the follow-up project's removal of MCP read access to val and test cover all of val, summary metrics included, or only val rows? If all of val, the val parts of M1, M4, M6 and M21 say "confirming on val needs Kiln Harness Tuner" instead.

*Where it goes:* Phase 18 ([phase_plans/phase_18.md](phase_plans/phase_18.md)), item 5 and its questions. M11 goes to Phase 17 ([phase_8_revisit.md](phase_8_revisit.md)), whose files Phase 18 does not edit.

## 11. Answers to the questions of Phase 18 (2026-11-24)

The owner answered the nine questions of [phase_plans/phase_18.md](phase_plans/phase_18.md). The owner's words are quoted where the owner gave them.

1. **Writable kinds.** `constraint`: yes, for the restrictions the user states. `hypothesis`: "reserved for harness-tuner". Kiln Harness Tuner reads it, so the docs must say this clearly.
2. **`memory.md`'s size.** `memory.md` stays short. The read-only formats move out of it into a folder with one small file per format, `references/knowledge/memory_formats/`, so that an agent's context is not flooded. `memory.md` links to the files and says which file covers what. The formats are for reading, not for writing, and they must match Kiln Harness Tuner's code exactly (`contract.md` section 3).
   - **Correction (same day):** "memory.md needs to link to docs individually or an index. There's no folder list tool." `memory.md` names each file by its full path, and never tells the agent to look in or list the folder.
3. **`OPEN: ` answers.** Allowed: a `constraint` that cites the `OPEN: ` record's id. But "don't really suggest this like it's common. Not a recommended flow, don't want to write a bunch about it and make it happen." At most one short line, phrased as a rare case.
4. **One-off records.** No `experiment` records from chat clients. A one-off's lasting results are `lesson`, `dead_end`, `issue` (and `constraint`).
5. **B14.** Yes: porting the exact cost/speed rule (Phase 18 item 3, row M1) replaces the earlier "keep as is".
6. **Project files** (`HS-M13`). Add the sentence now, in `working_with_project_files.md`: the project tree holds val and test items, and reading their rows counts as reading val or test data.
7. **B19.** Yes, the proposed text of Phase 18 item 6 is approved: never change the task's default run config on your own initiative, only when the user asks. Both files say so.
8. **B13.** Resolved by allowing chat clients to read the `val` memory record, which holds only summary metrics. Close B13. No extra fence is needed for the val record.
9. **What the val fence covers.** The follow-up project's val and test fence covers only rows; val summary metrics stay readable. So the val parts of M1, M4, M6 and M21 stay as written, with no "needs Kiln Harness Tuner" wording.

**The one-off headline (2026-11-24).** Owner decision: the one-off headline is eval-level, how many evals the candidate is ahead on by summary scores, the target eval included; Kiln Harness Tuner's item-level mean win rate is the loop's version.

*Where it goes:* Phase 18 ([phase_plans/phase_18.md](phase_plans/phase_18.md)), items 1 to 8.

## 12. Answers to the questions of Phase 17 (2026-11-24)

The owner answered the questions in section 7 of [phase_8_revisit.md](phase_8_revisit.md) and approved its approach.

1. **Approach.** Revert the knowledge trees (`references/levers/`, `references/improving_agents/`) to batch 7 and re-apply (section 5.2 there), not a targeted patch.
2. **Vocabulary renames.** Re-apply them: role → you, gateway operation → endpoint doc path, arm → candidate, val gate → the confirmation on val, probe → a quick check, screening round → a screening, owner → the user.
3. **Banned terms.** Allow Kiln Harness Tuner's input and output names, `install_skill_bundle` and `REJECTED AT VAL` in the trees. Keep the gateway operation names and the role names banned.
4. **Index section.** Approved as drafted (section 5.4 there), in `references/improving_agents/index.md` only, with the M11 playbook-step flow and the `KT-B14` fix that points to `references/knowledge/run_an_experiment.md`.
5. **"train".** Add "train" to the item-reading steps that name no split (`KT-B13`).
6. **The rules that batch 8 added from Kiln Harness Tuner's role skills.** Re-add the commissioning rules to the saturated-eval and wrong-eval playbooks: building a new eval is the rare exception; none for a closed issue; close the issue as won't fix when the new eval cannot reproduce it; never reopen a fixed issue. Do not re-add the "no number, no item id and no trace" recording rule: only Kiln Harness Tuner's code writes experiment records after Phase 18.
7. **Keep list.** The table of section 5.2 there is the full list of changes to re-apply after the revert. Nothing else since batch 7 touches the trees.

Decided with them:
- **Noise and detectability.** Say plainly that Kiln Harness Tuner has a noise check and a detectability check. For chat clients, the document's rule for an absent input applies: the flip rate of 10% for noise, and the floor of 6 wins for detectability.
- **Screening and skill bundles.** "Tell the user it needs Kiln Harness Tuner", for now. The bundle API comes in the next project.
- **Memory.** The record lines that Kiln Harness Tuner writes are read-only (Phase 18).
- **"The tuner"** (option B, decided after the code review): an approved rename. Where "the tuner" is the subject of a rule that limits what may be changed (the task, an eval, a fine-tune, a RAG config), the subject becomes "an experiment" or "this lever"; everywhere else, "the tuner" becomes "you". The owner's reason: Kiln Harness Tuner's agents act only through experiments, so for them the meaning is the same; for chat clients it limits the rule to experiments, so an agent does not refuse a user who asks it to change a task or an eval.
- **B7.** Drop "Smell: an old model" from `app/mcp/knowledge_backlog.md`. Keep the renames "A repeat measurement on request" and "A quick check for room to improve", each with a Kiln Harness Tuner example line.
- **B11.** The revert brings back the `output_mode` sentence on the test call with no tools attached and the `params` wording. Add `post_api_projects_project_id_skills.md` to the `api_docs` of `levers/skill.md`. Close B11.
- **B12.** Close it as moot. Instead, `.agents/skills/knowledge-maintenance/SKILL.md` 4.6 describes the new rules: Kiln Harness Tuner's text is ported as written, with only the mechanical changes and the approved renames, and the index section explains its inputs, code checks, outputs and tools to chat clients.

*Where it goes:* Phase 17 ([phase_plans/phase_17.md](phase_plans/phase_17.md)).

## 13. Phase 19 corrections (2026-11-24)

The owner's rule for the port of `experiment-costing` and `kiln-task-setup`: once HT switches over, no agent gets incorrect guidance. Where HT's text is wrong for Kiln's code, the code wins, and the change is an approved correction. The same holds for Kiln's own text. Line numbers are at the Phase 19 working tree.

HT's text, corrected in `references/knowledge/experiment_costing.md`:

- **The synthetic user's usage is on the TaskRun.** HT: "`EvalRun.synthetic_user_usage`", "No endpoint aggregates it (the eval API sums the task-run usage only)", read it off the per-item result rows. Code: the field is `TaskRun.synthetic_user_usage` (`libs/core/kiln_ai/datamodel/task_run.py:113`). The result rows' `task_run_usage` is `trace.usage` and leaves it out (`app/desktop/studio_server/eval_api.py:740-743`). The port reads it from the scored TaskRun: `eval_run.scored_run_id`, then `GET /api/projects/{project_id}/tasks/{task_id}/runs/{run_id}`; for a drive-only job, `result.driven_runs[].task_run_id` (`app/desktop/studio_server/jobs/workers/eval.py:170-182`). The run config eval-score summaries add only its cost into `mean_usage` (`scored_trace_usage`, `eval_api.py:1197-1234`), and they read the test split, so the port says not to use them. A reused trace is the same TaskRun (`TraceIndex.get_or_create`, `libs/core/kiln_ai/adapters/eval/eval_runner.py:1178-1189`): the port sums the field once per TaskRun. `None` on a run with no synthetic user, and on a migrated legacy trace whose driver cost is fused into `usage` (the field's description). The row's per-conversation usage is the row's `task_run_usage`, not `EvalRun.task_run_usage`, which is deprecated and set only on legacy inline records (`libs/core/kiln_ai/datamodel/eval.py:1061`). HT: drives from before the field existed are "unrecoverable". Code: a migrated legacy trace has the driver's cost fused into `usage` (the field's description, `task_run.py:113-120`), so the port says they have "no separate SU number".
- **No `custom`-score metric eval.** HT measured drive sizes with a `custom`-score metric eval and called it $0. Code: `EvalOutputScore` rejects a custom score (`libs/core/kiln_ai/datamodel/eval.py:927-931`). The port reads drive sizes off `task_run_usage` on the result rows, counted once per `scored_run_id` because several evals' rows can name the same TaskRun, or off the TaskRun's `usage`. For one drive's own cost on a seeded item it reads `usage`, not `cumulative_usage`, which includes the seeded prior trace (`libs/core/kiln_ai/datamodel/task_run.py:104-110`). "Code evals are $0" stays.
- **Model prices are a live read.** Removed: "A Kiln Harness Tuner run fetched these prices at its start" (the switchover reads model info live). "The run could not fetch models.dev" became "Kiln could not fetch models.dev". The lookups are named as `GET /api/model_info/models` and `GET /api/model_info/model_details`, with their endpoint docs.

HT's text, corrected or dropped in the `kiln-task-setup` port:

- **`kiln_api_mcp`.** Dropped from `references/knowledge/tools.md`: "For UI-driven tasks, attach the tool via a Local MCP server instead (`command: "kiln_api_mcp"`, …)". The switchover removes that command; Kiln's `/mcp` is not offered in its place, as it is untested.
- **Schemas after create.** HT: "expect the schema to be immutable post-create — that rule is inherited and was not re-verified here". Code: PATCH of a task refuses `input_json_schema` and `output_json_schema` with a 400 (`libs/server/kiln_server/task_api.py:136-140`). `references/knowledge/create_task.md` states the fact.
- **Disk writes.** Dropped on purpose (component skill_and_content section 9): the writes of `references/*` files and `task.kiln` to disk.
- **Scope.** "Batch-creating 3+ run configs: use a code tool wrapper" holds for a task whose own agent creates run configs, with `references/knowledge/code_tool_wrappers/batch_with_errors.md`. An agent that creates run configs itself calls `call_kiln_api` once for each.

Kiln's text, corrected to the code, with HT's clauses restored:

- **`POST /prompts` returns `id::<id>`.** Kiln said it returns the bare id. Code: `api_prompt_from_prompt` builds `id::{prompt.id}`, and `create_prompt` returns it (`libs/server/kiln_server/prompt_api.py:117`, `:236-256`). Fixed in `references/knowledge/model_create_configs.md` (prerequisite 3), `references/knowledge/create_task.md` and `references/knowledge/prompt_rewrite.md`; HT's "returns prefixed `id::<pid>` (use as-is)" holds.
- **A generator name is a valid `prompt_id`.** Kiln said it returns 422. Code: the run config create freezes a prompt that is not frozen yet into the config, and points `prompt_id` at the frozen copy, `task_run_config::…` (`app/desktop/studio_server/eval_api.py:2545-2596`). HT's parenthesis is restored in `references/knowledge/model_create_configs.md`; prerequisite 1, `references/knowledge/create_task.md` and `references/knowledge/model_work.md` agree.
- **`structured_output_mode` is required.** The run config example of `references/knowledge/create_task.md` sets it.

*Where it goes:* Phase 19 ([phase_plans/phase_19.md](phase_plans/phase_19.md)).

## 14. Phase 20 (2026-11-24)

The owner's principle: Kiln Harness Tuner (HT) worked with its own skills. A claim that the Kiln skill, or HT, must change for HT to work is presumed wrong unless HT's code at `b49f159` proves it. HT's own text is the source of truth for what HT's agents need. The full evidence table is in [phase_plans/phase_20.md](phase_plans/phase_20.md), "Step 0". HT paths are under HT's `src/kiln_harness_tuner/`.

**Kept, with code evidence.** Every correction of section 13 holds: the synthetic user's usage on the TaskRun (`task_run.py:113`; HT's own code reads it there, `job_drives.py:396`); no `custom`-score metric eval (`eval.py:926-931`); the schema 400 (`task_api.py:136-140`); `id::` prompt ids and generator names (`prompt_api.py:117`, `eval_api.py:2545-2596`). The live model-price read and the dropped `kiln_api_mcp` are not requirements on HT: the switchover removes HT's model catalogue and `kiln_api_mcp` itself (`harness_tuner_switchover/project_overview.md:55`, `functional_spec.md:285`). In the requirements, SR1, SR3, SR4 (role files), SR5, SR6 a–e and h, SR7–SR10, SR13, SR14 and SR18 stay.

**Dropped.** Each has a one-line note in [harness_tuner_switchover_requirements.md](harness_tuner_switchover_requirements.md), so the numbers hold:
- The SR4 gateway fields (`synthetic_user_usage`, `cumulative_usage` on `get_task_run`) and the review's further gateway fields. HT's costing text read the same fields off rows its gateway never returned (`TrainResultRow`, `gateway/models.py:300-315`), and HT worked.
- SR2's "copy a pinned tree": the switchover reads the skill live (its `architecture.md`, section 3, decisions 1 and 2). The need to read the Kiln skill stays.
- SR6f (HT's memory text states the train-side read rules, and `memory.md` carries them again). SR6g: no HT change is needed; HT's role skills hold its procedure, and `run_an_experiment.md`, which the trees link to, opens with "If you are Kiln Harness Tuner, follow your system prompt" (Phase 21 replaced that line with the chat line, section 15).
- SR11 and SR12: the Kiln skill adds no writer of `— RUNNING`, `OPEN: ` or experiment records; HT's own interactive install (`harness-tuner-install-agents --dest`), which had one, goes in the switchover (its `architecture.md` decision 15).
- SR15: HT's preflight already reads `message` (`job_drives.py:153`, `model_preflight.py:72,313`). SR16: HT's calls already fit Kiln's limits (`job_drives.py:61,365`; `setup.py:342`). SR17: HT's gateway has no function-name rule.
- The review's claim that HT's agents write `hypothesis` records: HT's code records each hypothesis in the `experiment` record (`schemas.py:188`, `memory_schema.py:1182-1184`), and its roles make discovery writes only (`kiln-harness-tuner-batch-selection/SKILL.md:79-81`). Section 11.1's "reserved for Kiln Harness Tuner" becomes the `hypothesis` row of `memory.md`: no agent writes one; HT's code records each hypothesis in its experiment record; in a chat with a user, tell the user an idea you do not act on now. No requirement.
- The review's claim that `code_tool_authoring.md` added "put that line in the tool's description": HT's skill has it (code-tool-authoring `SKILL.md:22-24`).

Fixed facts in the requirements: 22 playbooks, not 23 (SR5); the role prompts name files of `kiln-harness-tuner-knowledge`, which exist at `b49f159` (SR4); the contract test lives in Kiln, as the switchover designs it (SR5); SR6a names `memory.md`, "Write discipline"; SR6d adds `findings` and the report.

**The three ports, again from HT's text.** `references/knowledge/memory.md` with `memory_formats/` (from HT's `memory/SKILL.md`), `references/knowledge/code_tool_authoring.md` (from `kiln-harness-tuner-code-tool-authoring/SKILL.md` and `references/wrappers/README.md`), and `SKILL.md`, "Calling the Kiln API" (from `kiln-api/SKILL.md`, beside the rules from the Assistant's skill). Each HT sentence is verbatim, mechanical (paths, endpoint docs in place of gateway operations, file names, approved renames), changed under a decision, corrected by Kiln's code, or dropped because it is only about HT's own tooling. Where an agent in a chat with a user acts differently, an "In a chat with a user: …" clause sits beside HT's sentence, which stays the main text. Owner rule (same day): condition a branch on the real condition (a chat with a user; having a tool or an operation), never on the client's name, and add no "if you are Kiln Harness Tuner" label where the sentence's own words (your role's return field, your input) show who it is for. `SKILL.md`'s API section opens with "These rules apply if you have the `call_kiln_api` tool. If you do not, you need not read them.", the condition HT's own text uses. Sentence maps: a script, run on the two texts, gives only verbatim, near and changed (`memory` 126/23/36, code-tool authoring 58/13/17, `kiln-api` 13/13/21). The split of the near and changed sentences into Mechanical, Decision, Correction and Dropped was sorted by hand:

| Port | HT sentences | Verbatim | Mechanical | Decision | Correction | Dropped | Verbatim before this phase |
|---|---:|---:|---:|---:|---:|---:|---:|
| `memory` | 185 | 126 | 44 | 11 | 0 | 4 | 1 |
| code-tool authoring | 88 | 58 | 20 | 7 | 1 | 2 | 7 |
| `kiln-api` | 47 | 13 | 24 | 0 | 4 | 6 | 0 |

The decisions applied: sections 4 and 11 (one reference; code-written records read-only, their formats in `memory_formats/`; chat clients write lessons, dead ends, new issues and user-stated constraints, never `hypothesis`, `experiment`, `baseline`, `val` or `OPEN: `; the rare `constraint` answer to an `OPEN: ` record); sections 4 and 11 again for the `hypothesis` row of `memory.md`, the tag row's "Write when" (no agent writes one; HT's code records each hypothesis in its experiment record; the evidence is HT's role skills, not Kiln's code); section 3 (no HT-only heading on a shared rule: "The one hard rule", "the experiment deltas", "In an experiment the old tool stays live"); backlog B23 and `HS-M23` (in a chat with a user only the user grants code trust; an agent with a trust operation uses it); component skill_and_content section 9, row 11 (an agent that can run code on its own machine can run a tool's module with a stub first); and the standing rule (no name of the Assistant's skill's source: "for an agent that works on Kiln itself").

Corrections, where HT's text is wrong for Kiln's code:
- **Function names** (`code_tool_authoring.md`, build discipline 2). HT: "Duplicate non-archived function names are rejected (400)". Code: names may repeat in a project (`libs/core/kiln_ai/tools/tool_registry.py:236-246`); Kiln rejects an allowlist with two tools of one name (`app/desktop/studio_server/code_tool_api.py:257`) and a run whose tools share one fails (`libs/core/kiln_ai/adapters/model_adapters/base_adapter.py:838-845`).
- **The HTML-body 404 tell** (`SKILL.md`). HT: "Nothing stops you getting this wrong. A `url_path` carrying a `?` is forwarded as-is … the studio web page". Code: Kiln's tool refuses `?` and `#` in `url_path` (`libs/core/kiln_ai/tools/built_in_tools/kiln_api_call_tool.py:101-105`), and the MCP pipeline refuses an unknown route (`app/mcp/kiln_mcp_server/api_tool/pipeline.py:102-108`). Four sentences dropped.

Dropped under decision 11, small clauses: "(a hand-run n=3 check has no bundle)", "elsewhere, any labelled numbers", "or this session's equivalent" after `call_kiln_api`, "One `Read`, no catalog hop." (the port says "Read it before the first call."), and "write them when you open experiments".

Dropped as HT-only tooling (none is an instruction an HT role needs from the Kiln skill):
- `memory`: "Those links are Claude-Code-side …" and "drop or repoint the links if this file is ever promoted into a Kiln skill tree" (notes on HT's own file layout, done by the port itself); "Keep the two in step: a new prefix, suffix or code-read line lands in both" (a maintainer rule for HT's repository; its Kiln-side home is the format test of SR10); the clause "that's what makes these conventions portable between Claude Code and the Kiln assistant".
- Code-tool authoring: "each tested by `tests/test_wrapper_templates.py` against a stub of `kiln.tools`", in the skill and in the README (HT's test suite, which the switchover moves to Kiln or removes: `harness_tuner_switchover/components/ht_api_switch_and_removals.md:318`).
- `kiln-api`: the four sentences of the generated reference's header (265 endpoints in 25 catalogs; the hand-removed Judge Feedback Batches endpoints and the `spec_sha256` note; "the control surface of a Kiln workspace"), which describe HT's own copy of the reference that the switchover deletes, and whose Kiln counterpart is the generated `api_index.md`; "Everything below the routing index is a file you `Read`. You load this skill once; after that you never invoke a skill again to reach an endpoint" (how HT's agents load that skill; `SKILL.md`, "Reading skill files", says how the Kiln skill's files are read). The tool name `mcp__kiln_api_mcp__call_kiln_api` is a mechanical change: HT's `kiln_api_mcp`, which loop sessions never get, goes in the switchover (its `functional_spec.md:285,306`).
- Names of HT's gateway operations and of its gateway skill, in all three: mechanical (the approved rename "gateway operation → endpoint doc path", section 12, item 2), since SR6 b gives HT's roles the map from endpoint doc to operation, and the gateway skill stays in HT.

**Words (owner rule, same day).** HT reads the skill over MCP too, so "MCP client", "MCP agent(s)" and "over MCP" never mean the interactive client. The distinction is chat clients (interactive agents such as Claude Code or Codex, working with a user) versus Kiln Harness Tuner (a non-interactive agent with its own instructions). Phase 20 applies it to the files it changes; Phase 21 sweeps the rest (section 15). Owner quotes above keep their words.

**Two spec fixes.** `architecture.md` section 3, decision 10, now says "The source of the Assistant's skill stays outside the repository". Its decision 3 and `functional_spec.md` section 5.5 now say that the `x-mcp-policy` deny list covers direct calls through the MCP only: a task run whose tools include Kiln's built-in `call_kiln_api` reaches every blocked endpoint, because the core tool checks no policy. The follow-up scopes project (`project_overview.md`, P2) enforces that route. No code changes.

Not in this phase: the owner is redesigning where the guidance for chat clients lives (the "How to read these documents over MCP" section of `references/improving_agents/index.md`, and SR4's stale reason for keeping the planner's steps 4–5), in a phase of its own. Done in Phase 21 (section 15).

*Where it goes:* Phase 20 ([phase_plans/phase_20.md](phase_plans/phase_20.md)).

## 15. One skill, many kinds of client (2026-11-24)

The owner approved the design of Phase 21 ([phase_plans/phase_21.md](phase_plans/phase_21.md)).

**The principle.** The Kiln skill is one body of knowledge, read by more than one kind of client. Two today, and more may come: chat clients (interactive agents working with a user: Claude Code, Claude Desktop, Codex, OpenCode) and Kiln Harness Tuner (non-interactive agents with their own instructions, which deep-link into the skill). Shared files serve every client. A branch states its real condition ("In a chat with a user: …", "if you have the `call_kiln_api` tool"), never a client's name. Chat-only guidance lives in `references/client_guidance/chat/`. Never say "MCP client", "MCP agent" or "over MCP" for the interactive client: HT is an MCP client too.

**The decisions.**

- `SKILL.md` becomes a short router for every client, which trusts the reader's intelligence: what the skill is (served over MCP) and what Kiln is; how to read its files; the kinds of client; the layout of the skill, each part with a link to the next file of its chain (Kiln's features, with the feature table moved from the Learn About Kiln mode; improving agents; memory; the API; the chat client guidance); and the rules for every client. It names no chat file but `references/client_guidance/chat/using_kiln_from_chat.md`, which a chat client always reads at the start of a session.
- **HT's rule** becomes: a non-interactive agent with its own instructions follows them on any conflict, ignores an instruction to ask the user, and never reads `references/client_guidance/`; if it reads a file there, it fits any lesson to its own process. Its instructions win.
- `references/client_guidance/chat/` holds `using_kiln_from_chat.md` (new: the routing table, working with the user, keeping the user in the loop, links into the app, what this connection cannot do, the translation of HT's words from `references/improving_agents/index.md`, the folder's index), the four modes, `freeform_help.md` and `running_an_experiment_from_chat.md` (the renamed `references/knowledge/run_an_experiment.md`). Each file opens: "For chat clients working with a user. A non-interactive agent with its own instructions does not need this file." `references/modes/` goes.
- The API rules of `SKILL.md` move to `references/knowledge/api_docs/calling_the_kiln_api.md`, which opens: "These rules apply if you have the `call_kiln_api` tool. If you do not, you need not read them." Endpoint docs carry no such line.
- Everything else stays at its path, with path fixes only. No `using_kiln` folder and no `references/knowledge/index.md`.
- The words "MCP client", "MCP agent(s)" and "over MCP" meaning the interactive client become "chat client(s)" or the real condition, across the skill and this project's specs. Owner quotes keep their words, with a note (the top of this file). The phase plans and the research audits are dated records and keep theirs.

*Where it goes:* Phase 21 ([phase_plans/phase_21.md](phase_plans/phase_21.md)); the skill component doc, section 4.6; [harness_tuner_switchover_requirements.md](harness_tuner_switchover_requirements.md), SR4, SR5, SR6 and SR19.

## Related

- [phase_8_revisit.md](phase_8_revisit.md): Phase 17, approved on 2026-11-24 (section 12); its plan is [phase_plans/phase_17.md](phase_plans/phase_17.md).
- [phase_plans/phase_18.md](phase_plans/phase_18.md): Phase 18, the fixes outside the knowledge trees, including the one-off experimentation guide.
- [harness_tuner_switchover_requirements.md](harness_tuner_switchover_requirements.md): what the switchover project must do in HT.
