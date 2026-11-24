---
status: draft
---

# Functional Spec: Harness Tuner Switchover

Read the [project overview](project_overview.md) first. This document says what is built, in three places: new Kiln APIs, additions to Kiln's skill, and changes in the harness-tuner repo.

Words used here:

- **HT** is Kiln Harness Tuner, at commit `b49f159` when this was written.
- **The gateway** is HT's own MCP server for its loop agents. It stays.
- **Loop agents** are the agent sessions HT starts (planner, builder, analyst and the others). **Loop code** is HT's own Python.
- **The build branch** is `claude/kiln-mcp-server-impl`, where spec one is being built.

A line marked **Proposed** is a call made while drafting. The owner can overrule it. Section 10 lists the questions that are still open.

## 1. What changes, in short

| Area | Today | After |
|---|---|---|
| Knowledge about improving agents | HT ships its own copy as skill files | Loop agents and loop code read Kiln's skill, through the gateway |
| API reference, `call_kiln_api` server | HT ships both | Removed. Interactive sessions use Kiln's MCP server |
| Model information | HT fetches its own catalogue per run | HT calls Kiln's model info endpoints, and keeps its model policy |
| Installing a skill | HT writes into the project folder | HT calls Kiln's skill bundle API |
| Noise, detectability, significance floor | HT code | Kiln APIs, called by HT and open to any MCP client |
| The five code-detected smells | HT code | One Kiln API |
| The gateway, role skills, model policy, screening, promotion rules | HT | HT, unchanged |

## 2. Before anything starts

Nothing in this spec is built until spec one is done. The first phase of the implementation plan is a pre-flight check:

- Spec one is merged, including its phases 17 and 18, which still move skill text and may move paths.
- Every skill path this document names exists in the merged skill tree. A path that moved is corrected here before work starts.

## 3. Kiln APIs

### 3.1 Rules for all of them

- All are additive. No existing route changes its default behaviour.
- Each is a standard REST route. Any MCP client reaches it through `call_kiln_api`. No new MCP tools.
- Every number and definition is HT's, unchanged. Where HT has a test that pins a value, Kiln gets a test with the same value.
- **Train only means train only.** The detectability read, the noise-check estimate and the noise-check job read and drive train items. **Proposed:** in these three, an item that is also in a val or test split of any eval of the task is left out, and the response says how many were left out. HT's own train set works this way, and without the rule these routes could touch items HT holds out.
- Each of the three takes an optional `eval_ids` list. The default is every eval that is not archived and has a default judge config. HT passes its own active set.
- A route that spends money says so in its description, and carries the same approval note for the Kiln Assistant as the eval job does.

### 3.2 Significance floor

A new operation, `significance_floor`, on the existing `POST /api/statistics`. Pure arithmetic: it reads nothing from a project.

- **In:** `test` (`mcnemar_paired` for pass/fail scores, `compare_paired` for rating scores), `confidence` (default 0.95), and optionally `n` (paired items), `room` (items not at the best value) and `noise_rate` (share of items that change between two runs of one config).
- **Out:** `floor` (the fewest changed items, all one way, that the test can call significant; 6 for pass/fail at 0.95), `fewest_wins`, `best_case_change`, `interval_wins`, `interval_best_case`, `noise_each_way`, `noise_adjusted_wins`, and a one-sentence `interpretation` like the other operations. A value that cannot be computed from what was given is null.
- **Errors:** 422 for `room > n`, a negative number, or an unknown `test`.

### 3.3 Detectability of a run config

`GET /api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}/eval_detectability`

Answers: can this task's evals show an improvement of this run config at all? Free.

- **In:** `eval_ids`, `confidence`, and `include_val_size` (default false).
- **Out:** one row per comparable eval score: `eval_id`, `eval_name`, `eval_config_id`, `score_key`, `score_type`, `direction`, `n`, `room`, `unscored`, `floor`, `fewest_wins`, `best_case_change`, `interval_wins`. Also `skipped` (scores with no statistics operation or no direction, with the reason) and `unread_eval_ids`.
- With `include_val_size`, each row adds a `val` object: the size of the val split, an estimate of its room, and the best-case change. It reads the size of the val split only. It never reads a val or test result.
- **Reads:** the run config's stored train rows on each eval's default judge config, and the train split's size. **Writes:** nothing.
- An eval with no stored train row gives rows with `n = 0`. An eval with no default judge config is left out. Neither is an error.
- HT keeps the decision: whether to refuse an underpowered run is its own rule.

### 3.4 Noise check: the estimate

`POST /api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}/noise_check_estimate`

Says what a noise check would sample and cost, before anything is spent. Free. It is a POST because its body is the same object that starts the job.

- **In:** `items_per_eval` (required, at least 1), `eval_ids`, `confidence`.
- **Out:** `estimate_usd`, `drive_usd_per_item`, `judge_usd_per_item`, `distinct_items`, and per eval the sampled `item_ids`, whether its judge is checked again, and why not when it is not. `skipped` is set when there is no stored train row to compare with.
- The estimate comes from the cost recorded on stored rows. A stored row with no cost counts as zero, so an old baseline gives a low estimate; the response says how many rows had no cost.

### 3.5 Noise check: the job

`POST /api/jobs/evals/noise_check`

Measures run-to-run noise: it drives the sampled train items again and judges them again, then compares with the stored results. It costs money.

- **In:** `project_id`, `task_id`, `run_config_id`, the estimate's fields, `max_usd` (optional) and `concurrency` (optional).
- With `max_usd`, the job computes the estimate again when it starts. Above the cap, it makes no model call and succeeds with `skipped` set.
- The caller follows it with the existing job routes (wait, status, errors, cancel).
- **Result:** `estimate_usd`, `spend_usd`, `rows`, `warnings`, `skipped`, `errors`, and the pooled `flip_rate`. Each row is one eval score, with HT's field names: the sample size, how many results changed on a second drive, how many changed on a second judgment alone, the rates, `noise_adjusted_wins` and `train_room`.
- **It leaves nothing behind.** When the job ends, by success, failure or cancel, the project holds no run config, judge config, eval run or task run that the job made. The measured run config, its stored results and its traces are unchanged. How the server does this is an architecture decision.
- A pass that fails on one eval does not fail the job. The failure is in `errors` with the provider's own text, because HT must tell a dead key from a noisy eval.
- Train only, by construction. There is no `split` parameter.
- **Proposed:** nothing is stored for reuse. Noise moves with the provider and the day.

### 3.6 Smell check

`GET /api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}/smell_check`

Checks a run config for the five smells that code can detect. Free, pure code, no model call.

| Smell id | Limit | Source of the limit |
|---|---|---|
| `very-long-prompt` | 200,000 characters | A Kiln default, about 50,000 tokens |
| `very-long-tool-description` | 4,096 characters | Claude Code cuts a tool description at this length |
| `very-long-skill-description` | 1,024 characters | The maximum in the Agent Skills specification |
| `too-many-tools` | 40 tools (a skill is not counted) | A Kiln default |
| `old-model` | 8 months since release | A Kiln default |

- **In:** `as_of` (a date, default today). HT passes the start date of its run, so the old-model answer does not change during a run.
- **Out:** `detections`, each with HT's fields: `smell`, `detector`, `scope`, `fact` (at most 300 characters), `value`, `reference` (the limit) and `reference_source`. Also `checked`: the five smell ids with the limit each was checked against. Also `unread_tools`: tools whose definition could not be read.
- The model's release date comes from Kiln's model info. A model with no known release date gives no `old-model` detection and is named in the response.
- **Proposed:** the limits are fixed in Kiln, and the route takes no parameter to change them.

### 3.7 Scores by split

Four summary routes are fixed to the test split today: the judge config's `score_summary`, the task's `eval_results_summary`, and the two `eval_scores` routes of run configs.

- Each gets an optional `split` parameter: `train`, `val` or `test`. The default stays `test`, so existing callers see no change.
- 422 when the eval has no such split, with the same text the results route uses today.

### 3.8 Paired comparison of two run configs

`GET …/evals/{eval_id}/eval_config/{eval_config_id}/run_config/{run_config_id}/compare?baseline_run_config_id=…&split=train|val`

Compares a candidate with a baseline on one eval, from stored results, without returning any row. Free.

- **Out:** per score: `score_key`, `score_type`, `direction`, `n_items`, `baseline_score`, `candidate_score`, `delta`, `p_value`, `significant`, `ci_low`, `ci_high`, `headroom`, `fail_to_pass`, `pass_to_fail`. Also how many items each side has a result for, and `skipped` scores with the reason.
- No item id and no per-item value is in the response.
- `split` is required. `split=test` is refused: the method never compares on test.
- This route is for MCP clients. **Proposed:** HT's loop keeps its own comparison code, which also folds replicates, counts gaps and weighs priorities.
- Open: whether it returns a headline across evals, and whether one call covers all of a task's evals (section 10).

### 3.9 Skill bundles

Kiln's API can create a skill today, but only its `SKILL.md`. It cannot add or read a reference file.

**Create from a folder:** `POST /api/projects/{project_id}/skills/from_folder`

- **In:** `folder_path` (an absolute path on the machine that runs Kiln) and `provenance`.
- The folder must hold exactly: `SKILL.md`, and optionally `references/` and `assets/`. Nothing else at its root.
- `SKILL.md` has front matter with exactly `name` and `description`, and a body that is not blank. The name follows Kiln's existing skill name rules. The description is 1 to 1,024 characters.
- Files under `references/` are UTF-8 text. Files under `assets/` may be binary.
- No symlinks anywhere. Each file is at most 512 KiB, and the whole folder at most 2 MiB.
- The name must be new in the project. A skill is installed once; a new version is a new name. **Proposed:** this rule applies to this route only, and the existing create route keeps its behaviour.
- All or nothing: the skill exists whole or not at all. Kiln mints the id and records who made it, as for any skill. `SKILL.md` is stored exactly as given.
- **Errors:** every problem with the folder is reported in one answer, so the caller fixes them in one pass. Nothing is written on a refusal.
- **Out:** the skill, and its tool id (`kiln_tool::skill::<id>`).
- Provenance follows Kiln's existing rules. **Proposed:** `derived_from_ids` still accepts only skills of the project. HT's gateway passes the skill ids, and names a parent run config in the notes.

**Read back:**

- `GET /api/projects/{project_id}/skills/{skill_id}/files` lists every file of a skill with its path and size.
- `GET /api/projects/{project_id}/skills/{skill_id}/files/{path}` returns one file as text. A binary asset is listed but is not returned as text; the answer says so.

These routes are open to every MCP client. The create route reads a folder the caller names, and the read routes return its files. The folder rules above are the limit on that: only a valid skill folder is accepted.

### 3.10 Version

`GET /api/version` returns:

- `version`: the Kiln app version.
- `min_supported_harness_tuner_version`: raised when a Kiln change breaks older HT versions.

No project id, no secret. Section 5.8 says how HT uses it.

### 3.11 Model info

No new work in Kiln. The endpoints are built in spec one. Section 5.6 says how HT uses them.

## 4. Kiln's skill

The skill is still changing on the build branch. Each item below says what must be true. The place is found when the work is done: "find the right place to integrate".

- **A statistics file.** One file that explains noise, detectability and the significance floor, and names the call for each (3.2 to 3.5, and 3.8). The run-experiments doc links to it. It adds the calls to HT's method; it does not change the method.
- **The five smell documents** that code can detect name the smell check call, in place of telling the reader to measure by hand.
- **The skill lever and the skill techniques** say today that a skill with reference files "is built when running Kiln Harness Tuner". They name the skill bundle routes as the way for every agent.
- **`using_harness_tuner`.** Tells a coding agent with `kiln_skill` how to run the HT command line, in place of running a large experiment itself. It covers: when to use it; the checks to make first; install; the non-interactive command and the options that matter; cost and time, and asking the user before starting a paid run; starting it in the background, watching it and stopping it; reading the result; what to do when the start refuses; limits.
- **A contract test.** HT names certain paths, ids, front matter keys and headings of Kiln's skill (5.2). Kiln gets a test that pins that list. When a change to the skill breaks the list, the test fails in Kiln, and the fix is either to keep the name or to raise `min_supported_harness_tuner_version`.

## 5. Harness-tuner

### 5.1 Reading Kiln's skill through the gateway

- The gateway gets one new tool that passes a `kiln_skill` request through to the running Kiln app. Nothing is copied to disk, so the skill always matches the app version.
- Roles that read the knowledge today get the tool: planner, builder, analyst, baseline reviewer and report writer. A role that reads the memory reference gets it too.
- The answer is the file's text, as Kiln serves it.
- Loop code that needs the knowledge uses the same call. Today that is one place: the list of known smells (ids and titles) that the baseline review uses.
- When the call fails, a loop agent gets a clear error that says Kiln's skill could not be read. Loop code keeps today's fallback: the review runs with no known-smell list, and the log says so.
- **Proposed: the gateway limits the paths.** Kiln's skill has more than 400 files, written for a chat agent: the chat instructions, the modes, and a file that says reading project files directly is fine. The gateway passes through only what a loop agent needs: the knowledge trees (`references/improving_agents/`, `references/levers/`), the memory reference, the code tool authoring file and its templates, the train/val/test file, and the statistics file. A call with no path, or a path outside the list, gets an error that names what can be read.

### 5.2 What HT names in Kiln's skill

HT depends on these and nothing else:

- The folders `references/improving_agents/{techniques,playbooks,smells}/` and `references/levers/`, and the two index files.
- The ids: 7 levers, 27 techniques and 3 sub-files, 22 playbooks, 15 smells.
- The section headings its role skills cite, such as "How to confirm it", "How to recognise it", "What it blocks" and "Check that it took effect".
- The memory reference, the code tool authoring file and its 8 templates, the train/val/test file, and the playbooks its code quotes.

Two checks keep this honest, because HT's tests run offline and cannot see Kiln's skill:

- Kiln's contract test (section 4).
- A start-up check in HT. Before a run spends anything, HT reads each named path through the pass-through and stops with the path's name when one is missing.

### 5.3 Role entry files

HT has six role entry files (planner, builder, analyzer, smells, report, technique index). They live inside the knowledge copy, which is removed, and most of each file is a generated table.

- The entry files stay in HT, in a new home among its own skills.
- Their hand-written parts stay as they are.
- Each generated table is replaced by a pointer to the matching section of Kiln's index files.
- Two tables that only HT can own stay in HT: which smells code detects, and which gateway tools each lever uses.

### 5.4 Role skills and role prompts

The role skills stay as they are. Every link and named path in them, in the role prompt templates and in the entry files is re-pointed:

| Old | New |
|---|---|
| The skill `kiln-harness-tuner-knowledge` | Kiln's skill, read with the gateway tool |
| `levers/<id>.md` | `references/levers/<id>.md` |
| `techniques/<id>.md`, `playbooks/<id>.md`, `smells/<id>.md` | the same names under `references/improving_agents/` |
| "How to read these documents" | the same heading in `references/improving_agents/index.md` |
| The skill `memory` | `references/knowledge/memory.md` (see 5.5) |
| The skill `kiln-harness-tuner-code-tool-authoring` and its templates | `references/knowledge/code_tool_authoring.md` and `references/knowledge/code_tool_wrappers/` (see 5.5) |
| The skill `kiln-api` | `references/knowledge/api_docs/`, for interactive sessions only |

Kiln's skill is written for an agent in a chat with a person. A loop agent is not in a chat. Every role that reads Kiln's skill gets one shared block of rules:

1. You are not interactive. Where the skill says to ask the user, use your inputs and your output fields.
2. Where the skill names a Kiln endpoint, use the gateway tool for it. The gateway skill carries the map from endpoint to tool. An endpoint with no tool is not available to you.
3. Where the skill says to check or measure something yourself, use the code's result when it is in your input.
4. Where the skill says to tell or report to the user, use your output field.
5. Your role skill wins over any procedure file in Kiln's skill.
6. Never read the `baseline` or the `val` memory record, if your role is on the train side.
7. Never read the project folder from disk.

The map in rule 2 is built from the gateway's own tool list, and a test fails when a tool has no entry. It covers 24 of the 27 endpoint docs the knowledge names. The other three have no gateway tool, and the map says "not available".

### 5.5 HT's memory skill and code tool authoring skill

Both have a port in Kiln's skill.

**Proposed:** HT removes both and its agents read Kiln's files.

- For memory, this follows the owner's decision on the build branch: Kiln's memory reference serves HT and MCP agents, and its formats match HT's code exactly.
- For code tools, Kiln's file has steps that only fit a chat (explaining trust to the user, and opening the trust page). Rule 1 above covers them, and the builder's role skill says that HT grants trust itself, once per run.
- HT's 36 tests of the code tool templates move to Kiln, where the templates now live, unless Kiln already has the same tests.

### 5.6 Gateway tools and loop code that switch to Kiln's APIs

| Kiln API | What switches in HT | What HT keeps |
|---|---|---|
| Skill bundle create | The install tool of the skill installer becomes a gateway tool that calls the API | The check that the folder is inside the agent's scratch folder |
| Skill bundle read | The export tool becomes a gateway tool that writes the files into scratch; loop code that reads a skill's files for its checks | — |
| Model info | The gateway's model tools, and the catalogue fetch at run start | The model policy, and the `blocked_by_policy` status it adds to each answer |
| Significance floor | The floor and fewest-wins arithmetic | — |
| Detectability | The train-side read | The refusal of an underpowered run, and the val side |
| Noise-check estimate and job | The sampling, the clone run config, the judge copy and the comparison | The budget decision, booking the spend, and the stop rule that reads the rows |
| Smell check | The five detectors and their limits | The baseline review step, and how findings are recorded and reported |
| Version | The start-up check | — |

Notes:

- Kiln pages the model list before HT applies its policy. HT reads every page and pages again, so its counts stay right.
- The per-run model snapshot goes. Model information becomes a live read, and the run log records the Kiln version.
- Scores by split and the paired comparison are not used by HT's loop (3.8).

### 5.7 What HT removes

- The knowledge copy, the code that loads, checks and indexes it, its maintenance skill for coding agents, and its backlog file. Fixes to the knowledge are made in Kiln from then on.
- The `kiln-api` reference docs.
- `kiln_api_mcp`: the package, its console script and its tests.
- The model catalogue, and the `--no-model-catalog` option.
- The skill installer: the package, its console script and its tests.
- The noise, detectability and significance-floor code that moved, and the five smell detectors with their limits.
- The memory skill and the code tool authoring skill, if 5.5 is accepted.

The knowledge copy goes last, after the pass-through, the entry files and the re-pointed links all work.

### 5.8 Version checks

HT checks both ways at start-up, before any spend:

- Kiln's `version` against HT's own minimum. Too old: HT stops and says to update Kiln, with the steps it gives today.
- HT's own version against Kiln's `min_supported_harness_tuner_version`. Too old: HT stops and says to update HT, with the command.
- No version endpoint at all means a Kiln older than this spec: the "too old" message.
- An HT run from a source tree has no real version. The second check is skipped, with a note.
- HT's minimum is raised with every Kiln feature it starts to depend on. This spec raises it once.
- Today's feature probes of Kiln's OpenAPI document are removed once the minimum version covers them.

### 5.9 Interactive sessions and `harness-tuner-install-agents`

Today this command installs HT's skills and the `kiln_api_mcp` server into a user's project, for a person who works with an agent by hand.

**Proposed:**

- It no longer installs an MCP server or the `kiln-api` docs. It tells the user to connect Kiln's own MCP server, and points at Kiln's Connect page.
- It still installs HT's two interactive skills, `kiln-task-setup` and `experiment-costing`. Their links to the API reference are re-pointed at Kiln's skill.

### 5.10 Small fixes found on the way

- HT's error text helper prints a raw dump for every Kiln error, because it does not read the `message` key. It reads `message`.
- HT's text says Kiln refuses a tool function name that another tool already uses. Kiln refuses only two tools with one name in the same run config. The text is corrected, or goes with the skill in 5.5.
- **Proposed:** HT's start-up clean-up marks every running experiment record of the task as abandoned, including one that another writer opened. It marks only records HT opened.

### 5.11 Docs and command line

- The docs that name removed parts are updated: install, command line, architecture, agents, limitations, and the contributor guide.
- Two console scripts and one option go (5.7). The command-line reference and its tests follow.

## 6. Tests

- HT's test suite stays offline: no live server and no model spend.
- About 310 HT tests read the knowledge copy or its layout today. The tests of the knowledge's own content go, because Kiln's checks cover it. The tests of HT's code that happen to read the copy are rewritten against a fake.
- HT's fake Kiln gains a fake `kiln_skill` and a fake of each new route.
- Three tests bind HT's code to knowledge text: the lever ids, a playbook against the planner's input fields, and the output-mode lever against Kiln's list of modes. They cannot run offline after the switch. The ids move into Kiln's contract test (section 4). The other two are kept as review items in the audit (section 7).
- Each new Kiln API has tests, with HT's pinned values where HT has them.

## 7. Proof that HT still works

No reference run exists, runs differ each time, and the skills change. So the proof is not a before-and-after comparison. It has three parts:

1. **The audit.** A read of the switched HT against a checklist of its core concepts. Each item is checked in the place that now carries it: Kiln's skill, a role skill, a role prompt or HT's code. The checklist:
   - tune on train, confirm on val, never read test;
   - val is read by summary numbers only;
   - the promotion rule;
   - one change per experiment; new objects only, and the parent is never changed;
   - provenance is stamped when an object is made;
   - no train item value, and no eval or judge text, in a prompt, skill or tool;
   - hard limits hold, whatever a measurement says;
   - only allowed models;
   - cost comes from recorded usage;
   - the memory conventions, and who may write which record;
   - val readers write nothing;
   - the builder has one attempt per idea, and does not edit the eval that measures it;
   - the task's default run config is never changed;
   - the verdict words;
   - the loop never asks a person.

   The audit also checks that every role's first instruction names a file that exists, and that no role prompt names a removed skill.
2. **The tests.** HT's suite and Kiln's checks pass.
3. **One run on the demo project.** A full run against a Kiln build that has spec one and this spec. It passes when it finishes without an error from a missing file, a missing tool or a refused call, and its report is written.

## 8. The switchover requirements doc

[research/harness_tuner_switchover_requirements.md](research/harness_tuner_switchover_requirements.md) was checked item by item against the code and the build branch. It was written before the gateway was kept, and several of its claims about owner decisions are not in the recorded decisions.

| Item | Outcome here |
|---|---|
| SR1 loader reads Kiln's layout | Changed: there is no tree in HT to load. Covered by 5.1 and 5.2 |
| SR2 copy a pinned skill tree | Dropped. The gateway passes `kiln_skill` through |
| SR3 remove the copy last | Kept (5.7), with the maintenance skill and backlog added |
| SR4 entry files and role skills stay | Kept (5.3, 5.4). Its line about reading shared rules from Kiln's skill is not followed: the role skill wins |
| SR5 the list of names HT depends on | Kept (5.2), with the count corrected to 22 playbooks. The pinned-tree test becomes the two checks of 5.2 |
| SR6 rules for non-interactive agents | Kept as the shared block (5.4). They are this spec's rules, not earlier owner decisions |
| SR7, SR8 gateway until the fence | Dropped. The gateway stays, and there is no fence project |
| SR9 feature detection over REST | Mostly dropped. HT stays on REST; the version endpoint replaces the probes (5.8) |
| SR10 memory formats | No HT change. Kiln's side is spec one's phase 18 |
| SR11 the start-up clean-up | Proposed as a small fix (5.10) |
| SR12 reading other writers' records | No change. Listed as a risk (section 9) |
| SR13 priorities and smell issues | No HT change |
| SR14 tools that come over | Changed: only noise, detectability, the significance floor and the smells move. The rest stay in HT |
| SR15 the `message` key | Not a break. A display fix (5.10) |
| SR16 job limits and 404 texts | Verified: nothing to do |
| SR17 unique tool function names | The claim is wrong: HT has no such rule. A text fix (5.10) |
| SR18 skill bundle API | Kept (3.9), with a folder path, not an upload |

## 9. Out of scope, and risks

Out of scope:

- Scopes for MCP connections. Until that project exists, nothing stops an MCP client from reading val or test data; Kiln's skill tells it not to.
- Moving any other HT tool into Kiln: screening and the measurement engine, model preflight, the integrity, judge-copy and reference checks, the generality review, probes, and the latency comparison.
- Turning HT's role skills into prompts sent at sub-agent start.
- The API cleanup and robustness project.

Risks:

- **The skill can change under HT.** The knowledge now changes with the Kiln app, not with HT. The contract test, the start-up check and the version checks are the guard.
- **Two vocabularies.** Kiln's knowledge speaks of endpoints and a user; loop agents have gateway tools and no user. The shared rules and the map carry this. Text that fits neither will be found by the audit and the demo run, not before.
- **Records by other writers.** With Kiln's MCP in use, another agent can write memory records in a shape HT does not expect. HT reads such a record as unknown and acts only on its own.
- **HT still reads the project folder** for split membership, split sizes and code tool files. This spec does not change that.

## 10. Open for the owner

1. **Headline for the paired comparison (3.8).** Should the comparison return a headline mean win rate? No code defines it today. Two readings: (a) the mean across evals of the candidate's score minus the baseline's; (b) the mean across evals of wins divided by wins plus losses.
2. **One call for all evals (3.8).** Should one comparison call cover every eval of a task? As written it handles one eval.
3. **Limiting what loop agents can read (5.1).** Should the gateway pass through only the listed paths, or the whole skill with prompt rules alone?
4. **Memory and code tool skills (5.5).** Should HT remove its own two skills and read Kiln's?
5. **`harness-tuner-install-agents` (5.9).** Is the proposed behaviour right?
