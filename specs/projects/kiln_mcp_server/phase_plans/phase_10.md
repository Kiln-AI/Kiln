---
status: draft
---

# Phase 10: Content, part 4: wire the knowledge in, final checks, tune the texts

## Overview

Batches 13b and 14 of the content plan (skill_and_content section 9; mcp_server_and_api_tool section 2.4). Batch 13b gives each Assistant file of an overlap group (skill_and_content 9.1) one "See also" line with the full paths of its group's knowledge documents, makes the small edits of 9.2 that batches 1, 11 and 13a did not make, checks the membership of 9.1 against the files as edited, enables `test_no_rule_is_pending`, and runs the final checks (`misspell`, `checks.sh`, the wheel's file count). Batch 14 tunes the texts of `texts.py` against the final `SKILL.md`: the same terms and the same example path as the skill, inside the limits of the server doc.

Batch 13a already made three edits of 13b (the eval-playbook pointers in `eval_scores.md` and `specs_and_evals.md`, the problem-to-eval map of `create_spec.md`, and `code_tools.md` naming the lever `new_tool`). They are not redone. The files still get their "See also" line.

Rules: C11 (a port, not a redesign), C12 (one owner per question: a "See also" line gives paths and states no method), C13. Open owner decisions B2, B8, B9, B13 and B14 are not ruled on. The error texts of `api_tool/messages.py` (B2) are not texts of `texts.py`, so batch 14 does not change them. `WHAT_KILN_IS` changes only together with the stub skill text of the install guide (phase 11), so it stays. `PATH_DESCRIPTION` keeps the text of functional spec 6.1.

Each batch is its own commit. After each batch a patch of the working tree is saved in the scratchpad, so that the two can be committed separately.

## Steps

1. **The "See also" line** (batch 13b). Each file below gets, at its end, a section `## See also` with one line: `When and why, in the knowledge: ` and the group's paths in backticks, comma separated. A file in several groups gets one line with the union, in group order. `K/` = `references/knowledge/`, `P/`, `T/`, `S/`, `L/` as in 9.1.

   | File | Groups | Paths |
   |---|---|---|
   | `references/modes/improve_task.md` | 1 | `P/know-the-agent-before-you-plan.md`, `P/ordering-work.md`, `P/spending-the-budget.md` |
   | `K/eval_scores.md` | 2, 8 | the three playbooks of group 2, then the four eval playbooks of group 8 not yet named |
   | `K/benchmark_eval_inputs.md` | 2 | `P/dealing-with-a-noisy-eval.md`, `P/dealing-with-train-wins-rejected-at-val.md`, `P/spending-the-budget.md` |
   | `K/prompt_audit.md`, `K/prompt_rewrite.md` | 3 | `L/prompt.md`, the seven techniques, `S/very-long-prompt.md`, the four playbooks |
   | `K/model_work.md` | 4, 7 | `L/model.md`, the two model techniques, `S/old-model.md`, `P/dealing-with-an-eval-near-zero.md`, `P/cheaper-or-faster.md` and the techniques it links |
   | `K/model_create_configs.md` | 5, 6, 12 | every lever, `T/thinking-level-ladder.md`, `P/output-contract-not-met.md`, `T/state-the-output-contract.md` |
   | `K/specs_and_evals.md`, `K/create_spec.md`, `K/judge_types.md` | 8 | the four eval playbooks |
   | `K/adding_skills.md` | 9 | `L/skill.md`, the five skill techniques, the four skill smells, `P/skill-is-not-read.md` |
   | `K/tools.md`, `K/code_tools.md`, `K/code_tool_authoring.md`, `K/subagents.md` | 10 | `L/tool_config.md`, `L/new_tool.md`, the five tool playbooks, the tool techniques (levers `tool_config` or `new_tool`, not in another group), the tool smells (applies to `tools`, not in group 11) |
   | `K/rag.md` | 11 | `P/answers-not-grounded.md`, the three techniques, `S/document-behind-a-lookup-tool.md` |
   | `K/create_task.md` | 12 | every lever |
   | `K/local_private_on_prem.md` | 13 | `P/working-inside-restrictions.md` |
   | `K/fine_tuning.md` | 14 | `T/model-swap-inside-a-class.md`, `L/model.md` |
   | `K/typesafe_jev.md` | 15 | `T/decision-model-for-a-classifier.md` |

2. **The edits of 9.2 that are left** (batch 13b).
   - `K/tools.md`, "Tool selection guidance", item 2: name `S/too-many-tools.md` and `S/unnecessary-tools.md` for a tool set that may be too large; no number of theirs is repeated.
   - `K/fine_tuning.md`: the list "Try First" (a method of the order of work) becomes the path of `P/ordering-work.md`; the billing fact stays. The comparison after a fine-tune ("After Fine-Tuning Completes", and the hand-off line under the heading) names `K/run_an_experiment.md` ("Variants") in place of `K/eval_scores.md` alone. The line that sends the user to `references/modes/improve_task.md` stays.
   - `K/local_private_on_prem.md`, "Run Experiments": names `P/working-inside-restrictions.md` and `T/model-swap-inside-a-class.md` beside `K/run_an_experiment.md`.
   - `project_status.md`, `create_task.md`, `freeform_help.md` already name `references/modes/improve_task.md` (batch 1): checked, no change.
3. **Membership check** (batch 13b): read the Assistant files outside the groups for a section that advises when or why to use what a knowledge document covers; report a difference from 9.1, do not force it.
4. **Final checks of the tree** (batch 13b).
   - `skill_checks/test_shipped_skill.py`: `OVERLAP_SEE_ALSO` (test data: file → the paths its line holds, from the table of step 1) and `test_each_overlap_file_has_its_see_also_line`; `test_no_rule_is_pending` (`PENDING_RULES` is empty).
   - `misspell` over the skill tree (installed for the run if it is missing; spelling fixes only, in the copied help articles too, per C8).
   - Build the wheel of `app/mcp` into the scratchpad and check that its `kiln_mcp_server/skill/` files are exactly the keys of `skill_files.get_index().files`.
   - `uv run ./checks.sh --agent-mode`.
5. **Tune the texts** (batch 14), in `app/mcp/kiln_mcp_server/texts.py`:
   - `SERVER_INSTRUCTIONS`: the opening list uses the skill's list of what Kiln covers (tasks, prompts, run configs, models, evals, synthetic data, fine-tuning, tools, skills, RAG); "skill file" in place of "reference file"; the rule for valid paths as the skill states it (only paths written in the skill's files exist); "read the endpoint doc before your first call to an endpoint"; the confirmation rule names the operations that run code on the Kiln machine (code trust, a local MCP server), as `SKILL.md` part 5 does. The first paragraph stays under 500 characters and names `kiln_skill` and `/kiln`; the whole stays under 4,000.
   - `SKILL_TOOL_DESCRIPTION`: "skill file" in place of "reference file"; "the instructions list the modes and the entry points, and those files name the others"; the valid-path rule as above. 100 to 150 words; the trigger rule ends inside the first 500 characters; the example path stays `references/knowledge/specs_and_evals.md`.
   - `CALL_KILN_API_DESCRIPTION`: "endpoint doc" and the catalogue index `references/knowledge/api_docs/api_index.md` in place of "the skill's API reference"; "read the endpoint doc before your first call to an endpoint". The other paragraphs keep their facts.
   - `WHAT_KILN_IS`, `PATH_DESCRIPTION`: unchanged.
6. **Tests of the texts** (batch 14).
   - `skill_checks/test_shipped_skill.py`, `test_example_paths_exist`: also over `SERVER_INSTRUCTIONS` and `CALL_KILN_API_DESCRIPTION`; every skill path in each text exists; the texts that must carry an example still have one.
   - `test_texts.py`: `test_the_first_paragraph_of_the_instructions_stands_alone` (it ends inside the first 500 characters); `test_texts_use_the_skill_terms` (no text says "reference file" or "API reference"; each names `skill file` or `endpoint doc` as it applies).
   - The existing tests (`test_texts.py`, the schema snapshot of `test_server.py`, `test_description_is_100_to_150_words_and_front_loaded`) pass.

## Tests

- `test_each_overlap_file_has_its_see_also_line`: each file of `OVERLAP_SEE_ALSO` has exactly one `## See also` section, its line holds exactly the listed paths, and every path is in the tree.
- `test_no_rule_is_pending`: `PENDING_RULES` is empty.
- `test_example_paths_exist` (extended): the skill paths in all five texts exist.
- `test_the_first_paragraph_of_the_instructions_stands_alone`: the first paragraph of `SERVER_INSTRUCTIONS` ends inside the first 500 characters.
- `test_texts_use_the_skill_terms`: the texts use the skill's terms (`skill file`, `endpoint doc`), not "reference file" or "API reference".
- The shipped-tree tests, the knowledge checks, the bundling test and `test_no_skill_file_names_a_blocked_endpoint` pass with no pending rule.
