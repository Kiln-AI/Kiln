---
status: draft
---

# Review Fixes: Harness Tuner Switchover

Fixes to make to this spec, from the review pass of 2026-11-24 and 2026-11-25. The spec was checked against the finished build of spec one (branch `claude/kiln-mcp-server-impl` at `1b14901c`) and against harness-tuner's main (`6780366`, version 0.6.0).

Nothing here is applied yet. Part A is corrections of fact. Part B is design changes, and each waits for the owner. When a fix is applied to the spec documents, its line is removed from this file. The file is deleted when it is empty.

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

1. **The train rule.** Functional spec 3.1 and architecture decision 7 say that HT leaves out a train item that is val or test in another eval. It does not: such an item counts as train (`quarantine.py:26-28`, `:105`). See B1.
2. **Functional spec 5.8 and architecture 5.5 disagree** on the OpenAPI probes. See B5.
3. **`MIN_SUPPORTED_HARNESS_TUNER_VERSION` starts at `0.6.0`.** Still right: it is HT's version today. The first switched HT needs a higher number, so that Kiln can tell the two apart later.
4. The facts file `port_ht_adoption_facts.md` that `kiln_smells_skills_version.md` 7.5 cites is not in the repository. Remove the citation.

## B. Design changes (each waits for the owner)

### B1. No second copy of the measurement code

The spec gives Kiln the significance floor, the detectability read and the paired comparison, and HT keeps its own code for all three. That is two copies. The fix: HT calls Kiln's routes and removes its copies.

- **Detectability and the floor.** HT calls the detectability read for the baseline, at set-up and in each wave. Removed from HT's `detectability.py`: the floors, the interval functions, `score_room`, `train_row`, `comparable_specs`, `build_rows`, and the read of the stored rows. Kept in HT: the refusal and the warnings (`assess`), the options `--min-effect` and `--allow-underpowered`, and the report.
- **The route is what HT needs, because HT is now its caller:**
  - "Train" is the eval's train split, as the results route resolves it. The helper that leaves out held-out items goes, with `left_out_held_out` (A3.1).
  - The val side is always in the answer, and it gains `interval_best_case`. The flag `include_val_size` goes.
  - The replicate fold stays, as specified.
- **The noise check** imports `comparable_specs`, `fewest_wins` and `score_room` from `detectability.py`. It takes the same three facts from the detectability answer. This is the one change to `noise.py`. The check stays behind its option, and is still not ported.
- **The paired comparison.** HT's `Analyzer.compare_rows` and `_stats_row` pair the rows and call `POST /api/statistics`. HT calls the comparison route for the numbers. It still reads the rows itself for cost, latency and missing items. This is on the path of every promotion.
  - One number changes: Kiln's `significant` reads the unrounded p. HT compares the p rounded to 4 places with 0.05. A p between 0.04995 and 0.05 changes side.
  - The fixtures of `contract.py` for the two statistics operations go.
- **Scores by split.** HT has no copy. The route change stays for other clients.
- **Not in this fix:** the sign tests of HT's stop rules, latency and noise code. They are HT-only tools, and this spec does not move them.

### B2. Model info: no second copy of Kiln's schema

The gateway's five answer models (`ModelRow`, `ProviderEntryRow`, `ModelDetailsView`, `ProviderEntryDetails`, `ProviderRow`) repeat Kiln's fields. The fix: the gateway returns Kiln's rows as they are, and rewrites only `status`. The five models go. The all-pages read with a policy stays.

### B3. Memory formats: one check binds the two sides

The strings of HT's records are in HT's `memory_schema.py` and in Kiln's `references/knowledge/memory_formats/`. Kiln has a test of its side. HT has none, because its tests are offline. The fix: HT's start-up check, which reads the five format files, also checks that each string its code writes is in its file. A text must stay in both places; the check stops them from drifting apart.

### B4. The skill bundle create carries HT's installer into Kiln

The ask was "create a skill with its reference files in one step". The design ports the installer's machinery: staging folders, a sweep with an age test, a lock, 100 tries to mint an id, and `SKILL.md` written as raw bytes. HT needed these because it wrote into Kiln's folder from outside. Kiln owns the folder. The fix:

- Build the skill with Kiln's datamodel, as the existing create route does. Write the files into the skill's own folder, with `skill.kiln` last. Kiln lists a skill by its `skill.kiln`, so the skill is seen only when it is whole. On a failure, remove the folder. No staging, no sweep, no rename.
- `SKILL.md` is written by `save_skill_md`, the one writer Kiln has. A later rename through the existing route rewrites the file anyway.
- **The name rule.** "The name must be new in the project" holds on this route only, and the existing create route allows a repeat. One object, two rules. Either Kiln has the rule on both routes, or the rule stays in HT's gateway, beside its scratch-folder check. The lock exists only for this rule.
- **Text only.** The create accepts a binary asset, the read cannot return one, and HT's export skips it. Kiln's skill runtime reads assets as text. Refuse a file that is not UTF-8 at create. `is_text`, `note` and `skipped` go.

The folder path stays, as decided.

### B5. Version alignment grew three layers of start-up checks

The ask was a version check both ways. The design adds a hand-kept list in HT of every route and about 30 field names, checked against Kiln's OpenAPI document, and 93 skill reads at every start. The fix:

- Keep the two version checks, and the environment variable for a Kiln that runs from source.
- Remove the route and field lists. A released Kiln at or above the minimum has them. Today's three probes go too.
- Replace the 93 reads by one read of `references/improving_agents/index.md`, which proves the reader works. Kiln's contract test guards the paths.
- `OP_ROUTES` (a route for each of the gateway's tools) is then not needed for the checks. See B6.

### B6. The endpoint map

The design adds `OP_ROUTES` for every gateway tool, a script, a generated block and three tests, to make a table of about 27 rows. The fix: a hand-kept table in the gateway skill, and one test that every tool it names is a gateway tool.

Two tables of the entry files then repeat other things, and go:
- "which smells code detects": the smell check's answer lists them (`checked`).
- "which gateway tools each lever uses": the endpoint map gives the same answer.

The planner's entry file repeats the procedure that Kiln's index now holds ("How to work through a playbook"). It keeps only what Kiln's index does not have.

### B7. Smaller shapes in the Kiln routes

1. **The exact test overflows above about 1,030 changed pairs** (`mcnemar_exact_p`: `math.comb(n, k) * 0.5**n`). The spec works around it in three places. Fix the arithmetic (`math.comb(n, k) / 2**n` with whole numbers), with a test, and remove the three workarounds. This changes existing statistics code.
2. **Dead branches.** The comparison and detectability code carry `lower_is_better` and the "skipped" score types, which cannot occur in Kiln today. Remove them.
3. **One unreadable skill** stops the skill-description check for every skill (HT's behaviour, kept by ruling 9). Check the skills that can be read, and name the others in `unread_skills`, as `unread_tools` does.
4. **`as_of` on the smell check** exists so that the old-model answer cannot change in a run. Remove the parameter. The check uses today's date.
5. **Confidence.** The detectability read takes `confidence`, and the comparison fixes it at 0.95. Fix it at 0.95 on both. The statistics operation keeps its parameter, as its sibling operations have it.
6. **Names.** `…/run_config/{id}/compare` sits beside the existing `…/run_comparison`, which runs the test split and spends money. Name the new route `paired_comparison`. Put the detectability code under `services/`, not in a package named `eval_power`.
7. **The contract test** holds only `paths` and `ids` (A1.9).

### B8. The documents

1. Sections and rulings marked "not used" go. Architecture section 10 (the rulings) is folded into the component docs, so that no document needs an override.
2. The four routes for other clients become routes that HT calls (B1). The summary table, functional spec 5.6 and the two "is not changed" sections of `ht_api_switch_and_removals.md` (2.4, 2.5) follow.
3. `kiln_measurement_apis.md` section 12 and architecture 2.1 follow the wiring rule of A1.10.
