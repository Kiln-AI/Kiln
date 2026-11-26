---
status: draft
---

# Review Fixes: Harness Tuner Switchover

Fixes to make to this spec, from the review pass of 2026-11-24 and 2026-11-25. The spec was checked against the finished build of spec one (branch `claude/kiln-mcp-server-impl` at `1b14901c`) and against harness-tuner's main (`6780366`, version 0.6.0).

Nothing here is applied yet. Part A is corrections of fact. Part B is design changes. Each one says whether the owner has decided it. When a fix is applied to the spec documents, its line is removed from this file. The file is deleted when it is empty.

**HT** is Kiln Harness Tuner. Skill paths are from `app/mcp/kiln_mcp_server/skill/`.

The aim of part B, in the owner's words: no duplicate code after the port, no living with poor design, and no small ask that turned into a large risky change. All valid parts stay.

## A. Corrections of fact

### A1. Spec one moved after the spec was written

1. **The knowledge trees hold HT's own wording again** (spec one, phase 17). `references/levers/` and `references/improving_agents/` name HT's inputs, code checks and outputs. Only `references/knowledge/` and `references/client_guidance/chat/` are written for a chat. The functional spec (5.4, risks) and `ht_skill_reading_and_roles.md` say the opposite.
2. **`references/client_guidance/chat/` is new** (phase 21). Moved there:
   - `references/knowledge/run_an_experiment.md` is now `references/client_guidance/chat/running_an_experiment_from_chat.md`.
   - `references/modes/` is gone; its four files are in the chat folder.
   - `references/knowledge/freeform_help.md` is in the chat folder.
   - The section "How to read these documents over MCP" left `references/improving_agents/index.md`. It is now "How to read the shared documents" in `references/client_guidance/chat/using_kiln_from_chat.md`.
   - `SKILL.md` is a short router. Its section "Who reads this skill" gives a non-interactive agent its rules: its own instructions win, it ignores an instruction to ask the user, and it does not read the chat folder.
   - The API rules are in `references/knowledge/api_docs/calling_the_kiln_api.md`.
3. **HT's roles never read the chat folder** (the build branch's requirement SR19). No role skill, entry file or prompt names a path under `references/client_guidance/`.
4. **Pinned headings changed** (phase 20). In `memory.md`: "Tags" is now "Tags — seed vocabulary (8 + priorities)", and the column "Who writes" is now "Write when". In `code_tool_authoring.md`: "Wrapper templates" is now "Wrapper templates — bake it into code first", and "The allowlist rule" is now "The one hard rule: allowlist hygiene".
5. **The costing and task-setup skills are ported** (phase 19). `experiment-costing` is `references/knowledge/experiment_costing.md`. The facts of `kiln-task-setup` are in `create_task.md`, `model_create_configs.md`, `tools.md`, `adding_skills.md` and `prompt_rewrite.md`. Every "not found" and "not in Kiln's skill yet" line goes: functional spec 2 and 5.5, architecture ruling 22, both HT component docs. The `turn_mode` fact is at `create_task.md`.
6. **The costing port needs two fields that the gateway does not return.** The port reads `synthetic_user_usage` and `cumulative_usage` of a task run. The gateway's `TaskRunView` (`gateway/models.py:341`) carries `usage` only. Add both fields.
7. **Renamed words.** Kiln's trees say "candidate", "quick check" and "confirmation on val". HT's role skills say "arm" (146 times), "probe" and "val gate". The shared rules block gets a short list of these words.
8. **The skill text edits name text that is gone.** The files that still say only HT can install a skill with reference files are listed in the functional spec, section 4. `kiln_smells_skills_version.md` 7.3, 7.4 and 7.6 still name the five smell documents, the four techniques and three playbooks. The edit pass replaces them with the real list.
9. **Spec one's checks already cover part of the contract test.** The headings of each kind (`knowledge_schema.py`, `REQUIRED_SECTIONS`), the front matter keys, and the Smells table (a generated block with its own test) are enforced. Only the named paths and the ids are new.
10. **Limits of spec one that the spec did not know:**
    - `call_kiln_api` indexes the routes once, when `connect_kiln_mcp_server` runs. A new route must be added before that call, not only before `connect_webhost`.
    - `test_route_descriptions.py` fails a route with no description, or with a first sentence over 100 characters. Each new route needs one.
    - The API reference check is skipped below Python 3.13, so a local pass can hide a stale reference.
    - No file of the skill may be over 30,000 characters (`test_no_file_over_body_limit`). `old-model.md` has 3,272 of its 4,000.
    - The 404 text is now "{kind} not found. ID: {id}. Check the ID, or list the {plural} to find the right one."
    - Service code is in `studio_server/services/` and models in `api_models/`. New code follows that layout.
11. **Docstrings that become false.** `eval_api.py:3233` and `:3264` say "test split". They change with the `split` parameter, and they feed the API reference. `train_val_test.md` (its table of calls) tells the reader not to use the summary routes; it changes too.
12. **What the model info endpoints do differently from HT's catalogue.** An unknown `provider` filter is a 422 (HT returns an empty list). Kiln reloads models.dev after 6 hours, so a price can change in a run. The setting that turns models.dev off is `KILN_SKIP_MODELS_DEV`, on the Kiln server. Kiln has three parameters HT lacks: `search`, `featured`, `include_notes`. `include_deprecated=True` does list every entry that `ready_model_count` counts (the spec marked this "not verified").

### A2. Harness-tuner moved after the spec was written

1. HT main is nine commits past `b49f159`. Line numbers in `gateway/ops.py` are 4 lines off, and test lines moved by 32 to 59. Test counts: 3,983 in all, `test_agent_templates.py` 89, `test_gateway.py` 90. The knowledge skill has 81 files, not 78.
2. `pyyaml` stays: a new test imports it (`tests/test_agent_templates.py:15`).
3. `tests/test_baseline_review.py` imports `smells.thresholds`, which the spec deletes. The test is rewritten in the same step.
4. A flat skill goes through `install_skill_bundle` since HT's PR 42. New test: `test_skill_md_only_bundle_installs`.
5. Text that the switch makes false, not yet in the spec's list:
   - `kiln-harness-tuner-experiment-build/references/skill-authoring.md:9`: "the gateway has no create-skill operation for your role".
   - `kiln-harness-tuner-gateway/SKILL.md:293`: "installed with the skill installer tool, not the gateway".
   - The test `test_build_skill_sends_a_flat_skill_through_the_installer`, which pins "You have no tool that sends `POST /skills`".
   - `tests/test_agent_templates.py:1218`, which pins text of `kiln-task-setup`.
6. `trust_code_tools` calls `POST …/add_code_trust`. Kiln's skill has no endpoint doc for it, so the endpoint map gives that tool no row.
7. `gateway/server.py:78` runs `json.dumps` on every answer. The `kiln_skill` tool must return plain text, so `_tool` changes too, not only `dispatch`.
8. `path="SKILL.md"` returns the root file, although a call with no path is refused. Decide one rule.
9. `GATEWAY_RULE` says "no discovering routes". The pass-through serves the endpoint docs. Reword it.

### A3. Wrong in the spec itself

1. **The train rule.** Functional spec 3.1 and architecture decision 7 say that HT leaves out a train item that is val or test in another eval, as one rule. HT has two rules. Its gateway leaves such an item out of what an agent may read (`gateway/trainset.py`). Its loop code counts the item as train (`quarantine.py:26-28`, `:105`), and its detectability code reads the stored rows of Kiln's own train split. The detectability read replaces loop code, so it follows the second rule. See B1.
2. **Functional spec 5.8 and architecture 5.5 disagree** on the OpenAPI probes. See B4.
3. **`MIN_SUPPORTED_HARNESS_TUNER_VERSION` starts at `0.6.0`.** Still right: it is HT's version today. The first switched HT needs a higher number, so that Kiln can tell the two apart later.
4. The facts file `port_ht_adoption_facts.md` that `kiln_smells_skills_version.md` 7.5 cites is not in the repository. Remove the citation.

## B. Design changes

Each item has a type:

- **Duplicate**: the same code or data in two places after the port.
- **Small ask that grew**: a small request that became a large or risky change.
- **Poor shape**: a design that works but should not be kept.

### Decided by the owner (2026-11-25)

**B1. No second copy of the measurement code**
- Type: Duplicate.
- Description: the spec gives Kiln the significance floor, the detectability read and the paired comparison, and HT keeps its own code for all three.
- Decision: HT calls Kiln's routes and removes its copies. B5 and B6 hold the two consequences.
- What follows:
  - HT calls the detectability read for the baseline, at set-up and in each wave. Removed from HT's `detectability.py`: the interval functions, `train_row`, `build_rows`, and the read of the stored rows. The three functions that the noise check imports stay (B5). Kept in HT: the refusal and the warnings (`assess`), the options `--min-effect` and `--allow-underpowered`, and the report.
  - The route is what HT needs, because HT is now its caller. "Train" is the eval's train split, as the results route resolves it; the helper that leaves out held-out items goes, with `left_out_held_out` (A3.1). The val side is always in the answer, and it gains `interval_best_case`; the flag `include_val_size` goes. The replicate fold stays.
  - HT's `Analyzer.compare_rows` and `_stats_row` take their numbers from the comparison route. HT still reads the rows itself for cost, latency and missing items. The fixtures of `contract.py` for the two statistics operations go.
  - Scores by split: HT has no copy. The route change stays for other clients.
  - Not in this fix: the sign tests of HT's stop rules, latency and noise code. They are HT-only tools, and this spec does not move them.

**B2. Model info: no second copy of Kiln's schema**
- Type: Duplicate.
- Description: the gateway's five answer models (`ModelRow`, `ProviderEntryRow`, `ModelDetailsView`, `ProviderEntryDetails`, `ProviderRow`) repeat Kiln's fields.
- Decision: the gateway returns Kiln's rows as they are, and rewrites only `status`. The five models go. The all-pages read with a policy stays.

**B3. Memory formats**
- Type: Duplicate.
- Description: the strings of HT's records are in HT's `memory_schema.py` and in Kiln's `references/knowledge/memory_formats/`. The text must stay in both places.
- Decision: no new check. The version check covers it. A change to a record format is a breaking change: the side that makes it raises its minimum version of the other side. Kiln's existing test of its own files stays.

**B4. Start-up checks**
- Type: Small ask that grew.
- Description: the ask was a version check both ways. The design added a hand-kept list in HT of every route and about 30 field names, checked against Kiln's OpenAPI document, and 93 skill reads at every start.
- Decision: keep the two version checks, and the environment variable for a Kiln that runs from source. Remove the route and field lists, today's three probes, and the list of skill paths with its 93 reads. No new start-up check is added. Kiln's contract test guards the paths. `OP_ROUTES` is then not needed for the checks (B13).

### Open: from the removal of the duplicates

**B5. The noise check and the detectability code**
- Type: Duplicate.
- Description: `noise.py` imports `comparable_specs`, `fewest_wins` and `score_room` from HT's `detectability.py`: about 80 lines of its 659, with the floor functions that `fewest_wins` needs.
- Decision (owner, 2026-11-25): keep the 80 lines in HT. `noise.py` is not changed. The rest of `detectability.py`'s arithmetic and its read of the stored rows go, as B1 says. A small copy of the floor arithmetic stays in HT for the noise check only.

**B6. The paired comparison changes one number**
- Type: Duplicate.
- Description: the comparison is on the path of every promotion. Kiln's `significant` reads the unrounded p. HT compares the p rounded to 4 places with 0.05. A p between 0.04995 and 0.05 changes side.
- Decision (owner, 2026-11-25): accept the unrounded p. It is the correct test, and one rule then holds for every client.

### Open: small asks that grew, and poor shapes

**B7. The skill bundle create carries HT's installer into Kiln**
- Type: Small ask that grew.
- Description: the ask was "create a skill with its reference files in one step". The design ports the installer's machinery: staging folders, a sweep with an age test, a lock, 100 tries to mint an id, and `SKILL.md` written as raw bytes. HT needed these because it wrote into Kiln's folder from outside. Kiln owns the folder.
- The owner's requirement: the API takes the path of a skill folder and copies a valid skill into the project. A chat agent may have no access to the project's files, and it is told not to write `.kiln` files, so it writes the skill in a folder of its own and names the path.
- Decision (owner, 2026-11-25): the route and its folder rules stay. Only the write inside Kiln changes. Build the skill with Kiln's datamodel, as the existing create route does. Write the files into the skill's own folder, with `skill.kiln` last: Kiln lists a skill by its `skill.kiln`, so the skill is seen only when it is whole. On a failure, remove the folder. `SKILL.md` is written by `save_skill_md`, the one writer Kiln has. No staging, no sweep, no rename, no lock, no retries.

**B8. The name rule**
- Type: Poor shape.
- Description: HT's installer refuses a bundle whose name is taken in the project ("install-once; a new version is a new name"). The spec copied the rule into the new Kiln route only. Kiln's existing create route allows two skills with one name.
- Decision (owner, 2026-11-25): remove the rule, in Kiln and in HT. A new copy of a skill often keeps its name: a new run config attaches the new version in place of the old one, and no prompt that names the skill needs a change. Kiln already refuses a run config that attaches two skills with one name (`base_adapter.py:833`).
- What follows:
  - Rule F17 of the folder rules goes, with the lock that it needed.
  - Text that states the rule changes. In Kiln's skill, `references/levers/skill.md`: "install it under a new name" and "Each name can be installed once". In HT: `kiln-harness-tuner-experiment-build/SKILL.md:49` and `references/skill-authoring.md:109`, `:153`, `:190`. The new text says that a new version may keep the name, and that the new run config attaches the new version and drops the old one.

**B9. A binary asset can be created but not read**
- Type: Poor shape.
- Description: the create accepts a binary file under `assets/`. The read route cannot return one, and HT's export skips it and names it. Kiln's skill runtime reads assets as text only.
- Decision (owner, 2026-11-25): text only. The create refuses a file that is not UTF-8. The fields `is_text`, `note` and `skipped` go. Support for binary assets is a P2, outside this spec.

**B10. The overflow of the exact test is worked around three times**
- Type: Poor shape.
- Description: `mcnemar_exact_p` fails above about 1,030 changed pairs (`math.comb(n, k) * 0.5**n` overflows). The spec keeps the fault and adds a 422, a "skipped" score and a ruling for it.
- Decision (owner, 2026-11-25): fix the bug. `math.comb(n, k) / 2**n`, with whole numbers, and a test. The three workarounds go. This is a third allowed change to existing Kiln code.

**B11. One unreadable skill stops the check for every skill**
- Type: Poor shape.
- Description: the smell check ports HT's behaviour: when one attached skill cannot be read, no skill description is checked at all.
- Decision (owner, 2026-11-25): check the skills that can be read, and name the others in `unread_skills`, as `unread_tools` does.

**B12. Branches that cannot run in Kiln**
- Type: Poor shape.
- Description: the comparison and detectability code carry `lower_is_better` and the "skipped" score types. Kiln's datamodel allows neither today, so the code runs only in its own tests.
- Decision (owner, 2026-11-25): leave them out. If Kiln gains such a score, the code is added then.

**B13. The endpoint map needs a route table for every gateway tool**
- Type: Small ask that grew.
- Description: loop agents need a table from each endpoint doc that Kiln's knowledge names to a gateway tool, about 27 rows. The design adds `OP_ROUTES` for all 54 tools, a script, a generated block and three tests.
- Proposal: a hand-kept table in the gateway skill, and one test that every tool it names is a gateway tool.

**B14. Entry-file tables that repeat other things**
- Type: Duplicate.
- Description: two hand-kept tables stay in HT's entry files: "which smells code detects" and "which gateway tools each lever uses". The smell check's answer already lists the first (`checked`), and the endpoint map gives the second. The planner's entry file also repeats the procedure that Kiln's index now holds ("How to work through a playbook").
- Proposal: remove both tables. The planner's entry file keeps only what Kiln's index does not have.

**B15. `as_of` on the smell check**
- Type: Poor shape.
- Description: the parameter exists so that the old-model answer cannot change during one run, when a model passes 8 months of age on that day.
- Proposal: remove it. The check uses today's date.

**B16. The confidence differs between two routes**
- Type: Poor shape.
- Description: the detectability read takes `confidence`. The comparison fixes it at 0.95. HT uses 0.95 everywhere.
- Proposal: fix it at 0.95 on both. The statistics operation keeps its parameter, as its sibling operations have it.

**B17. Names**
- Type: Poor shape.
- Description: the new `…/run_config/{id}/compare` sits beside the existing `…/run_comparison`, which runs the test split and spends money. The detectability code is in a new package named `eval_power`, outside the layout that spec one set.
- Proposal: name the route `paired_comparison`. Put the code under `studio_server/services/` and the models under `api_models/`.

**B18. Kiln's contract test repeats checks that exist**
- Type: Small ask that grew.
- Description: the test has four kinds of entry and its own reader of the Smells table. Spec one's checks already enforce the headings that every document of a kind must have, the front matter keys and the table (A1.9). They do not cover a heading of one named file that HT's role skills cite, such as a section of `memory.md`.
- Proposal: the list holds `paths`, `ids`, and the headings of named files. The per-kind headings, the front matter keys and the reader of the Smells table go.

**B19. The documents**
- Type: Poor shape.
- Description: sections and rulings are marked "not used", and architecture section 10 overrides the component docs.
- Proposal: remove the unused numbers, and fold each ruling into its component doc, so that no document needs an override. The summary table, functional spec 5.6 and `ht_api_switch_and_removals.md` 2.4 and 2.5 follow B1. `kiln_measurement_apis.md` section 12 and architecture 2.1 follow the wiring rule of A1.10.
