---
status: complete
---

# Phase 19: Port Kiln Harness Tuner's `experiment-costing` and `kiln-task-setup`

## Overview

Kiln Harness Tuner (HT) deletes its own skills and points its agents at the Kiln skill ([deep_pr_goals](../deep_pr_goals.md) sections 1 and 8). Two of its shared skills have no home in the Kiln skill yet: `experiment-costing` and `kiln-task-setup`. This phase gives each one a home, complete, with the rules of the port: port, don't rewrite; one text for HT's agents and MCP agents; verify by a sentence diff against HT's source at `b49f159`.

The other project's view of this phase is the pre-flight of [harness_tuner_switchover functional_spec](../../harness_tuner_switchover/functional_spec.md) section 2, its section 5.5 and its architecture decision 22: HT's `experiment-costing` is not removed until its costing method is in the Kiln skill, and the builder's role skill points at Kiln's files on tasks, run configs, skills and tools.

Paths are from `app/mcp/kiln_mcp_server/skill/`. HT's sources are `src/kiln_harness_tuner/agent_files/skills/experiment-costing/SKILL.md` and `src/kiln_harness_tuner/agent_files/skills/kiln-task-setup/SKILL.md` at `b49f159`.

## Steps

1. **`references/knowledge/experiment_costing.md`: a new knowledge file, HT's `experiment-costing` close to as is.**
   - Front matter: `name: experiment_costing` and HT's `description` (the tree check requires exactly these two keys for a file of `references/knowledge/`).
   - The body is HT's text. The file is about 17,000 characters, under the 30,000 body limit, so it is not split.
   - Only mechanical tweaks:
     - "this skill" (the file itself) becomes "this file", because in the Kiln skill "this skill" is the whole skill.
     - The gateway's `list_models` and `get_model_details` become the endpoint docs `references/knowledge/api_docs/get_api_model_info_models.md` and `references/knowledge/api_docs/get_api_model_info_model_details.md`. The gateway's `catalog.models_dev: "unavailable"` becomes the endpoint's `sources.models_dev.state: "unavailable"`.
     - What only HT has stays named as HT's: the sentence about prices fetched at the start of the run, the read-denied project tree, the train-only split, and the section "Screening before arms (Kiln Harness Tuner)".
     - "Related": `kiln-harness-tuner-batch-selection` is named as Kiln Harness Tuner's skill; `kiln-api` becomes `references/knowledge/api_docs/api_index.md`.
   - No rule, number, formula or step changes.
2. **`references/knowledge/run_an_experiment.md`, "Cost before you spend".** The section points to `references/knowledge/experiment_costing.md` and drops the short form. It keeps only the sentences that the port does not cover: the Kiln call that runs the smoke (the eval job with `"split": "train"` and `item_ids`), that a later full run reuses those scores, and "Tell the user the estimate" (the port's "proposal" is HT's planner output).
3. **Links to the new file**, so that it is reachable and found:
   - `SKILL.md`, "Other entry points": one line.
   - `references/modes/improve_task.md`: a row in its "Method" table.
   - `references/knowledge/model_work.md`, "Cost Estimation", and `references/knowledge/benchmark_eval_inputs.md`: their pointers to "Cost before you spend" name the new file.
   - `references/improving_agents/playbooks/spending-the-budget.md`, "Situation": one sentence that names the file for how to price a measurement. No step and no order changes.
4. **`kiln-task-setup`: each fact to its Kiln file.** For each sentence of the source, find where the Kiln skill says it. Add what is missing, as HT wrote it:
   - `references/knowledge/create_task.md`: the Task body with `turn_mode` and the schemas; `turn_mode` is frozen; the multiturn schema rule; setting the task default; a section on driving a multi-turn conversation (run, chain, edit a run, tags, leaves only); HT's verification checklist. The front matter description names multi-turn tasks.
   - `references/knowledge/model_create_configs.md`: `supports_function_calling` for tool-bearing tasks; HT's one-line form of `run_config_properties`, with its required fields; the silent PATCH of `run_config_properties`; re-pointing `default_run_config_id`; a code tool wrapper for 3 or more run configs.
   - `references/knowledge/tools.md`: the tool id forms, with `kiln_tool::call_kiln_api`; the body essentials of the local MCP connect, and that it validates connectivity on create; `call_kiln_api` hidden from the UI's tool pickers, the Local MCP route for UI-driven tasks, and that MCP tools are visible in the UI.
   - `references/knowledge/adding_skills.md`: what the create call writes; `references/` files have no API; strip external doc references and inline the schemas; how the model reads a reference file at runtime (written as the `skill` tool and its parameters, because the tree check bans call syntax).
   - `references/knowledge/prompt_rewrite.md`: the body essentials of the prompt create call.
   - A sentence that disagrees with a Kiln sentence is not added, and Kiln's sentence is not changed. Each one is a question for the owner in the return summary.
5. **Verify by diff.** A script splits each HT source into sentences. For `experiment-costing`, it diffs the source against the new file and lists every changed sentence. For `kiln-task-setup`, a map gives each sentence its place: the file, and verbatim, tweaked (how) or already present (quoted), or held for an owner question. The map is written to the scratchpad folder `p19/`.
6. **Spec.** `components/skill_and_content.md`: section 4.3 part 7 lists the new entry point; section 9 ("Not in this port") and 9.1 (cost estimation) name the two homes; 9.3 row 5 names the new file. `harness_tuner_switchover_requirements.md` SR4: `experiment-costing` and `kiln-task-setup` no longer stay in HT's role skills; SR5 gets their Kiln locations. `implementation_plan.md`: tick Phase 16.

## Tests

In `app/mcp/kiln_mcp_server/skill_checks/test_shipped_skill.py`:

- `ENTRY_POINTS` gets `references/knowledge/experiment_costing.md`, so `test_skill_md_has_the_required_parts` checks the line in `SKILL.md`.
- `test_run_an_experiment_points_to_the_costing_file`: the section "Cost before you spend" names `references/knowledge/experiment_costing.md`.
- `test_the_costing_file_has_every_cost_lane`: the six lane headings of HT's source are in the file, in order, with the "Rules" section.
- `test_task_setup_facts_are_in_their_files` (parametrised): `turn_mode` is frozen in `create_task.md`; `call_kiln_api` is hidden from the UI's tool pickers in `tools.md`; `supports_function_calling: true` for tool-bearing tasks in `model_create_configs.md`.
- The existing tree check covers reachability, front matter and banned terms for the new file.
