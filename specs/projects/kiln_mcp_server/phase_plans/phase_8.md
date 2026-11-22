---
status: complete
---

# Phase 8: Content, part 2: import the knowledge and reword it

## Overview

The knowledge set of Kiln Harness Tuner comes into the skill: 7 levers, 30 technique files, 15 smells and 22 playbooks (skill_and_content sections 4.5 and 9, batches 7–9). Batch 7 copies the files, writes their links as full paths from the skill root, turns `gateway_ops` into `api_docs`, drops the detector keys of the smells, renames the lever heading, and writes the two index files. Batch 8 rewrites the loop's vocabulary so that a general agent can follow the text, with no change to what a rule requires (C11). Batch 9 writes `references/knowledge/train_val_test.md`, the one statement of the split rule and the leak rules, and points the other files at it.

Source: harness-tuner at commit `b49f1594620862876d1e515cdda2f2deff018e95`, folder `src/kiln_harness_tuner/agent_files/skills/kiln-harness-tuner-knowledge/references/`. `gateway/ops.py` at the same commit is read as a reference for the operation-to-endpoint map; no code is copied. Each batch is its own commit.

## Steps

1. **Batch 7: import and link rewrite.**
   - A one-off script outside the repository copies `levers/` to `skill/references/levers/`, and `techniques/`, `smells/` and `playbooks/` (with the sub-folder `techniques/guide-skill-for-a-tool-set/`) to `skill/references/improving_agents/`. The role entry files (`planner.md`, `builder.md`, `smells.md`, `analyzer.md`, `report.md`, `technique-index.md`) and the knowledge skill's `SKILL.md` are not copied.
   - Each Markdown link target is resolved against its file's folder in the source and written as the full path from the skill root (`references/improving_agents/techniques/roll-up-tool.md`). The script stops on a link that does not resolve.
   - `OPERATION_ENDPOINTS`: one row per gateway operation (54), from the handler in `gateway/ops.py`: the REST endpoint it calls (the one that makes the change, when it calls several), the endpoint doc path, or `none` (no REST call, or a blocked endpoint). The model operations map to the model info endpoints, the Kiln port of the handler's `model_info` module. The table goes in the batch's summary, not in the repository.
   - Levers: `gateway_ops` becomes `api_docs`, each operation replaced by its endpoint doc path, in order, duplicates removed, `none` dropped. The heading `How the tuner changes it` becomes `How to change it`.
   - Smells: `detected_by` and `detectors` are removed from the front matter.
   - `references/levers/index.md` and `references/improving_agents/index.md`: hand-written prose with the generated blocks of `INDEX_BLOCKS`. The hand-written part of `references/improving_agents/index.md` carries "How to read these documents" from the knowledge skill's `SKILL.md`, and the table of the parts. Then `skill_checks build`.
   - `SKILL.md` part 7 names the two index files, so the trees are reachable.
   - `PENDING_RULES` gets the rules whose problems wait for batch 8 or 9, each with its batch: `tree-banned-term`, `size`, `tree-split-pointer`, and any other rule that the loop vocabulary trips (a path to a harness-tuner skill file), and nothing else.
2. **Batch 8: loop vocabulary.** For each knowledge file, under C11 (vocabulary only):
   - A gateway operation becomes its endpoint doc path from `OPERATION_ENDPOINTS` (or the call it names); an operation that maps to `none` becomes what the agent does instead, or the sentence says that the rule applies when running Kiln Harness Tuner.
   - A role becomes "you"; "the tuner", "the loop", "this run" become the general words; the names of harness-tuner skills that are not ported go, and the levers' "See also" gets the Assistant files of the table in 4.5 (the two paths of later batches are added by those batches).
   - The rows of `LOOP_WORDS`: "arm" → candidate or experiment, "the val gate" → the confirmation on val, "a probe" → a quick check, "a screening round" → a screening, "the owner" → the user, loop inputs and outputs → what the agent asks the user or reports, "code checks" → "check … yourself", reason codes → the outcome in words, the noise inputs → Kiln Harness Tuner measures them and the rule applies when running it.
   - The four playbooks that name loop inputs (`dealing-with-train-wins-rejected-at-val`, `spending-the-budget`, `dealing-with-a-noisy-eval`, `dealing-with-a-saturated-eval`) get the same rule for their Situation and steps.
   - 5 smells get "how to measure this yourself" with the number (prompt over 200,000 characters; tool description over 4,096; skill description over 1,024; more than 40 tools; model older than 8 months), from the detector defaults at the pinned commit.
   - `levers/output_mode.md` and `smells/tools-on-a-live-server.md` are shortened in their wording to their size limits; no rule is dropped.
   - The hand-written part of the two index files gets the same rewording.
   - A sentence that cannot be reworded without a change to its rule is left as close to the source as the banned terms allow and reported.
   - `tree-banned-term`, `size` and the batch-7 path rule leave `PENDING_RULES`.
3. **Batch 9: train/val/test.**
   - `TEST_SPLIT_READERS` in `tree_check.py`: one entry per call and per app page that reads an eval's test split when the caller asks for no split, checked against `app/desktop/studio_server/eval_api.py` and the endpoint docs.
   - New `references/knowledge/train_val_test.md` (front matter `name`, `description`): harness-tuner's rule unchanged (tune on train; confirm on val by metrics only; never read test), with "metrics only" as harness-tuner defines it at the pinned commit; (a) which call and which app page reads which split, and how to ask for train or val, with every `TEST_SPLIT_READERS` entry; (b) an eval with only a test split: add the train and val splits first, with the user, and do not go on with the test split (with the endpoint, or the C10 wording if it is blocked); (c) the leak rules of the levers.
   - Each mode and knowledge-tree file with split wording names the path; a statement of the rule elsewhere is replaced by the path. The levers name the path for the leak rules. The other split mentions of the skill are reviewed.
   - `SKILL.md` part 7 names `references/knowledge/train_val_test.md`.
   - `tree-split-pointer` leaves `PENDING_RULES`. `tree-test-split` stays pending (batch 13a).
4. **Snapshots.** After each batch, a patch of the whole working tree against `HEAD` is saved in the scratchpad, so that each batch can be committed on its own.

After batch 9, `PENDING_RULES` holds only `tree-test-split` (batch 13a).

## Tests

- `test_the_generated_blocks_are_current`: every generated block of the two index files equals `render_blocks` of the shipped tree.
- `test_a_document_of_each_type_exists`: the shipped tree has at least one lever, technique, playbook and smell, and a sub-file.
- `test_the_knowledge_was_imported_whole`: the shipped trees hold 7 levers, 30 technique files, 15 smells and 22 playbooks.
- `test_every_lever_names_its_api_docs`: each lever's `api_docs` is not empty and names only endpoint docs (with the rule `lever-api-docs` doing the rest).
- `test_the_split_rule_file_states_the_rule`: `train_val_test.md` names train, val and test, "metrics only", the leak rules, and every `TEST_SPLIT_READERS` entry.
- `test_test_split_readers_read_the_test_split`: each `TEST_SPLIT_READERS` endpoint doc is a file of the tree (and each app link is an app link).
- The existing shipped-tree tests (`test_the_shipped_tree_passes_every_check`, `test_the_shipped_knowledge_passes_every_check`, `test_the_full_check_passes`, `test_skill_md_has_the_required_parts`, `test_no_file_over_body_limit`, `test_no_skill_file_names_a_blocked_endpoint`, the bundling test) pass after every batch with its `PENDING_RULES`.

## Notes for the reviews by people

- Sandbox wording (functional spec 15), for the security owner: batch 8 changed `references/levers/new_tool.md`. Its text and description said that Kiln runs a code tool in a sandbox; they now say that it runs with no resource sandbox, to match `references/knowledge/code_tools.md` and `references/knowledge/judge_types.md` (phase 7). Review the three files together.
