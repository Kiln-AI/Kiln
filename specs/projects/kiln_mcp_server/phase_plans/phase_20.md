---
status: complete
---

# Phase 20: Deep review fixes

## Overview

A deep review of the branch (git-ignored, `reviews/projects/kiln_mcp_server/`) found that "port, don't rewrite" ([deep_pr_goals](../deep_pr_goals.md) section 1) was applied to the knowledge trees (Phase 17) and to the two skills of Phase 19, but not to three earlier ports: `references/knowledge/memory.md` with `memory_formats/`, `references/knowledge/code_tool_authoring.md`, and the "Calling the Kiln API" rules of `SKILL.md` (from Kiln Harness Tuner's `kiln-api` skill). Those were written new in Phase 9 and only aligned in Phase 18. This phase ports them again from HT's sentences, the Phase 17 way.

The owner's principle for this phase: HT worked with its own skills. A claim that the Kiln skill, or HT, must change for HT to work is presumed wrong unless HT's code at `b49f159` proves it. Step 0 re-checks every such claim this project made, and the evidence table below is the base for the rest of the phase.

HT paths are under HT's `src/kiln_harness_tuner/` at `b49f159`, read as data only. Kiln skill paths are from `app/mcp/kiln_mcp_server/skill/`. "Requirements" is [harness_tuner_switchover_requirements.md](../harness_tuner_switchover_requirements.md); "decisions" is [harness_tuner_alignment_decisions.md](../harness_tuner_alignment_decisions.md).

## Step 0: the claims, re-checked

Each row is a place where this project says HT's text is wrong for Kiln, or that HT must change. **Keep** rows have code evidence. **Drop** rows are applied in this phase: HT's text is restored or the requirement is deleted.

| # | Claim (source) | Outcome | Evidence |
|---|---|---|---|
| 1 | The synthetic user's usage is on the TaskRun, not the eval row (decisions 13) | Keep | `libs/core/kiln_ai/datamodel/task_run.py:113`; the rows' `task_run_usage` is `trace.usage` (`app/desktop/studio_server/eval_api.py:740-743`). HT's own code reads it off the TaskRun (`job_drives.py:396`) |
| 2 | Kiln has no `custom`-score metric eval (decisions 13) | Keep | `EvalOutputScore.validate_type` refuses `custom` (`libs/core/kiln_ai/datamodel/eval.py:926-931`) |
| 3 | Model prices are a live read; HT's "fetched at its start" sentence removed; `sources.models_dev.state` (decisions 13) | Keep | Not a requirement on HT: the switchover project removes HT's model catalogue and copies Kiln's `sources` into its answers (`harness_tuner_switchover/project_overview.md:55`, `components/ht_api_switch_and_removals.md:104-109`). At `b49f159` HT fetches once per run (`model_catalog/fetch.py:1`), which that project retires |
| 4 | `kiln_api_mcp` dropped from `tools.md` (decisions 13) | Keep | The switchover removes the package (`harness_tuner_switchover/functional_spec.md:285,306-308`) |
| 5 | Task schemas cannot change after create (decisions 13) | Keep | `libs/server/kiln_server/task_api.py:136-140` |
| 6 | Disk writes of `references/*` and `task.kiln` dropped (decisions 13) | Keep | Recorded decision, component `skill_and_content` section 9 |
| 7 | 3+ run configs by a code tool wrapper, scoped to a task's own agent (decisions 13) | Keep | A scope note on HT's sentence; no claim on HT |
| 8 | `POST /prompts` returns `id::<id>`; a generator name is a valid `prompt_id`; `structured_output_mode` required (decisions 13) | Keep | Kiln's text corrected to HT's: `libs/server/kiln_server/prompt_api.py:117`; `eval_api.py:2545-2596` |
| 9 | HT's gateway `get_task_run` must add `synthetic_user_usage` and `cumulative_usage` (requirements SR4) | Drop | HT's own costing text named fields its gateway never returned either: `TrainResultRow` has only `task_cost_usd` (`gateway/models.py:300-315`), and its text read `eval_usage` and `synthetic_user_usage` off those rows. HT worked without them: its code measures cost (`job_drives.py:396`, `budget.py:266`) and the planner prices from `measurement_prices`. The Kiln port gives no worse guidance |
| 10 | The review's gateway fields (token breakdown, `eval_usage`, `driven_runs`, `sources`) need a new SR (review phase 5) | Drop | Same as row 9. `sources` is the switchover's own change (row 3) |
| 11 | SR2: HT copies the Kiln skill tree into its agents' folders | Drop the mechanism | HT must read the Kiln skill (its loader names `kiln-harness-tuner-knowledge`, `knowledge/load.py:27`), but how is the switchover's design: a live read through `kiln_skill` (`harness_tuner_switchover/architecture.md:70-71`). SR2 keeps the need and points at that design |
| 12 | SR1: loader layout and front matter; SR4: role prompts name HT's entry files; SR5 contract list | Keep, two facts fixed | `knowledge/load.py:27`, `knowledge/schema.py:45,176,193`; the role prompts name files of `kiln-harness-tuner-knowledge` (`agents/batch_plan.md:8`), which the switchover deletes ("today they name missing files" was wrong: the files exist at `b49f159`). SR5: 22 playbooks, not 23; the contract test lives in Kiln (`harness_tuner_switchover/architecture.md:46,94`) |
| 13 | SR4: the planner's steps 4–5 stay in HT because the Kiln skill does not hold them | Not changed here | Stale (the Kiln skill holds them in `references/improving_agents/index.md`), but it belongs to the owner's redesign of where the guidance for chat clients lives, a later phase |
| 14 | SR6a: a failed memory write is disclosed "as HT's memory skill says" | Keep, re-pointed | HT's rule (memory skill line 47) is ported into `memory.md` (step 1); SR6a names it there. SR6d lists `findings` and the report too |
| 15 | SR6f: train-side roles never read `baseline` or `val`; the role prompt states both | Drop | HT's memory skill states both rules (its lines 36, 66, 67); the port restores them in `memory.md` |
| 16 | SR6g: HT roles follow their role skills, not `run_an_experiment.md` | Drop | No HT change is needed: HT's role skills hold its procedure, and no HT text names that file or `references/modes/`. The trees link to `run_an_experiment.md`, and its first line already says "If you are Kiln Harness Tuner, follow your system prompt" (`run_an_experiment.md:6`) |
| 17 | SR6e: HT grants trust with its own operation; its REST call still works | Keep | `gateway/ops.py:1245`, `probes.py:275` call `POST …/add_code_trust` over REST; the block is the MCP tag only (`app/desktop/studio_server/eval_api.py:3551`) |
| 18 | SR11: the `— RUNNING` janitor must spare other writers' records | Drop | No other writer exists: chat clients never write `experiment` records (decisions 11.4), and no released Kiln skill told them to |
| 19 | SR12: HT must read other writers' `OPEN: ` and experiment records | Drop | Same: Chat clients write neither (decisions 4, 11.3, 11.4) |
| 20 | SR15: HT's preflight must read Kiln's `message` key | Drop | The preflight's text comes from `job_drives.error_text`, which reads `message` first (`job_drives.py:153`; `model_preflight.py:72,313`) |
| 21 | SR16: HT's calls must stay inside `jobs/wait` limits and match 404 by status | Drop | HT already sends only `ids` and `timeout` within Kiln's cap of 3600 (1800 in `job_drives.py:61,365`; 3600 in `analysis.py:98,1568`) and matches 404 by status (`setup.py:342`, `gateway/ops.py:937`). The `kiln-api` replacement is SR5's row |
| 22 | SR17: HT's gateway keeps a stricter function-name rule | Drop | HT's gateway has no such rule (no uniqueness check in `gateway/ops.py`). HT's sentence "Duplicate non-archived function names are rejected (400)" is wrong for Kiln: names may repeat in a project (`libs/core/kiln_ai/tools/tool_registry.py:236-246`); Kiln refuses an allowlist with two (`code_tool_api.py:257`) and a run with two fails (`base_adapter.py:838-845`). `code_tool_authoring.md` keeps that correction |
| 23 | SR13, SR14, SR18; SR3, SR7–SR10 | Keep | Owner decisions (decisions 2, 4) or no change on HT's side |
| 24 | HT's agents write `hypothesis` records and lost their write rule (review phase 2) | Drop | HT's code records each hypothesis in the `experiment` record (`schemas.py:188`; `memory_schema.py:1182-1184`); its roles make discovery writes only (`kiln-harness-tuner-batch-selection/SKILL.md:79-81`). `memory.md`'s tag row says so; no requirement |
| 25 | `code_tool_authoring.md:27-29` adds a rule HT does not have (review phase 3) | Drop the finding | HT's skill has it (code-tool-authoring `SKILL.md:22-24`) |
| 26 | HT's HTML-body 404 tell does not hold for Kiln (review phase 3) | Keep, recorded | Kiln's tool refuses `?` and `#` in `url_path` (`libs/core/kiln_ai/tools/built_in_tools/kiln_api_call_tool.py:101-105`); the MCP pipeline refuses an unknown route (`app/mcp/kiln_mcp_server/api_tool/pipeline.py:102-108`) |

## Steps

1. **Step 0 in the specs.**
   - `harness_tuner_switchover_requirements.md`: delete the SR4 gateway-field sentence, SR6f, SR6g, SR11, SR12, SR15, SR16 and SR17, each with a one-line "dropped in Phase 20" note so the numbering holds; reword SR2 to the switchover's live read; fix SR4's "today they name missing files"; SR5's count and acceptance location; point SR6a at `memory.md`, "Write discipline", and add `findings` and the report to SR6d; update the tense of the Phase 17/18 lines touched; the acceptance section loses the dropped items.
   - `harness_tuner_alignment_decisions.md`: new section 14 "Phase 20" with the table above in short form, the corrections of step 2 and step 3, the list of dropped (e) sentences, and the sentence-map counts.
2. **Port `memory.md` and `memory_formats/` from HT's `memory/SKILL.md`.** Start from HT's sentences, keep decisions 4 and 11 (one reference for both readers; code-written records read-only, their formats in `memory_formats/`, each file named by full path; chat clients write lessons, dead ends, new issues and user-stated constraints; never `hypothesis`, `experiment`, `baseline`, `val`). Each HT sentence is verbatim, mechanical (endpoint doc paths, gateway names dropped, file names), changed under a decision, corrected with evidence, or dropped as HT-only tooling. Where an agent in a chat with a user must act differently, an "In a chat with a user: …" clause sits next to HT's sentence, which stays the main text, unlabelled; a branch is conditioned on the real condition (a chat with a user, having a tool or an operation), never on the client's name. `SKILL.md`'s API section opens with "These rules apply if you have the `call_kiln_api` tool. If you do not, you need not read them." Known gaps closed: the failed-write rule; the missing-eval rule with its chat case; `p2`/`p3`; priority tags never removed and source-owned; merge-eligible; "small n gives direction, never validation"; `dead_end` cites the experiment id (in a chat with a user, the run config ids); the train-side read rules; the residual lines in `experiment_records.md`; the baseline seeding and the `default` flag in `baseline_and_val_records.md`; the `hypothesis` row (Step 0 row 24).
3. **Port `code_tool_authoring.md` from HT's `kiln-harness-tuner-code-tool-authoring/SKILL.md` and `references/wrappers/README.md`**, the same way: HT's headings and sentences, gateway operations as endpoint docs, "grant it with your trust operation when you have one" with the user-grants steps beside it, `build_notes` with "in a chat with a user, in your report", the README's table and shared rules, HT's complete worked-example module restored inline, and the function-name correction (Step 0 row 22). The eight wrapper files do not change.
4. **Port `SKILL.md` "Calling the Kiln API" from HT's `kiln-api/SKILL.md`.** Add HT's rules beside the Assistant's: method and path from the catalogue row exactly as printed; the body from the doc, never guessed from a name; the three finding steps and "calling from memory … one extra read costs less than one wrong call"; "filter every call"; never `.items[]` unless the shape has it; no shell quotes, no quoted field paths; "a failed call is a reading problem", the aggregate-snapshot sentence, cite before retry, no second guess from memory and no shell after one failure; and HT's note that its loop agents reach Kiln through its gateway. The HTML-body tell is dropped (Step 0 row 26).
5. **Small items.**
   - `architecture.md:111`: "The source of the Assistant's skill stays outside the repository."
   - `architecture.md` section 3, decision 3 (the policy seam), and `functional_spec.md` section 5.5: the `x-mcp-policy` deny list covers direct MCP calls only. A task run whose tools include Kiln's built-in `call_kiln_api` reaches every blocked endpoint, because the core tool checks no policy; the follow-up scopes project (`project_overview.md`, P2) is where that is enforced.
   - In every file this phase changes (the skill files, the specs, the decisions, the requirements and the tests), "MCP agent(s)", "MCP client" and "over MCP" meaning the interactive client become "chat client(s)": Kiln Harness Tuner reads the skill over MCP too. The owner's quoted words and the existing heading "How to read these documents over MCP" stay.
6. **Checks.** `uv run python -m kiln_mcp_server.skill_checks check` (fix with `make skill_index`), the app/mcp tests, and `uv run ./checks.sh --agent-mode` until clean.

Out of scope: the "How to read these documents over MCP" section of `references/improving_agents/index.md`, `run_an_experiment.md`'s structure, `SKILL.md`'s routing and "Other entry points", and `references/modes/` stay as they are. The owner is redesigning where the guidance for chat clients lives, in its own phase.

Sentence maps for steps 2–4 are kept in the scratchpad (`p20/`), not in the repository; their counts go into decisions section 14.

## Tests

In `app/mcp/kiln_mcp_server/skill_checks/test_shipped_skill.py`:

- `test_memory_keeps_harness_tuners_rules` (parametrised): `memory.md` holds HT's failed-write rule (return field, once, exempt from the budget), the missing-eval rule (`eval_only`, `link_eval`) with the chat case (`create_spec.md`), the `p2`/`p3` meanings, "never removed, even on close", the merge-eligible definition, "small n gives direction, never validation", and the train-side read rules.
- `HARNESS_TUNER_FORMATS` gains the three `residual …:` lines (`experiment_records.md`), from HT's `memory.py:1053-1055`.
- `test_the_baseline_record_says_how_it_is_seeded`: `baseline_and_val_records.md` names `default_run_config_id`, the most recently created run config, and that the loop never sets the `default` flag.
- `test_the_api_rules_keep_harness_tuners_discipline` (parametrised): `SKILL.md` "Calling the Kiln API" holds "exactly as printed", "Filter every call", "`.items[]`", "reading", the cite-before-retry rule and the shell rule.
- `test_the_authoring_guide_keeps_harness_tuners_sections`: `code_tool_authoring.md` has HT's sections in order, the inline worked example compiles and defines `run`.
