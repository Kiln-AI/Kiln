---
status: draft
---

# Functional Spec: Harness Tuner in Kiln

Read the [project overview](project_overview.md) first. This document says what each of the five phases delivers.

Words used here:

- **HT** is Kiln Harness Tuner. Its code is at commit `6780366` of its own repository when this was written.
- **The gateway** is HT's own MCP server for its agents. It has 54 tools. It stays until phase 5.
- **Loop agents** are the agent sessions HT starts (planner, builder, analyst and the others). **Loop code** is HT's own Python.
- **A chat client** is an agent that works with a user over Kiln's MCP server.
- **Scoped** means a request that carries a scope. **Unscoped** means one that does not.

A line marked **Proposed** is a call made while drafting. The owner can overrule it. Section 9 lists the questions that need the owner.

Sources that this document draws on, and replaces where they differ:

- [review_fixes.md](../harness_tuner_switchover/review_fixes.md): the decisions of the switchover review.
- [scope_decisions.md](../harness_tuner_port/scope_decisions.md): the scope rulings.
- The switchover's [functional spec](../harness_tuner_switchover/functional_spec.md), sections 3 and 7: the first form of the Kiln APIs and of the proof.

## 1. What changes, in short

| Area | Today | After |
|---|---|---|
| Where HT lives | Its own repository, its own releases | The Kiln repository, Kiln's releases |
| How a loop agent reaches Kiln | HT's gateway, 54 typed tools | Kiln's MCP server, on a scoped URL: `call_kiln_api` and `kiln_skill` |
| What keeps val and test from an agent | The gateway's rules, for HT's agents only | Scopes in Kiln's API, for every MCP connection |
| Role procedures | Skill files that HT copies into each agent CLI's folder | Files of Kiln's skill, under `references/client_guidance/harness_tuner/` |
| Knowledge, API reference, model information | HT ships copies | Kiln's own. The copies are removed |
| Measurement calculations (floor, detectability, paired comparison, smells) | HT code | Kiln code, one copy, behind standard APIs |
| The REST API for a caller that sends no scope | — | Unchanged |

## 2. Rules for every phase

- **Each phase is complete on its own.** It can be merged and released without the next one.
- **HT's method does not change.** Its numbers, its rules for keeping a candidate and its loop are moved, not redesigned. Where a rule must change, this document says so.
- **One copy.** When a phase gives Kiln a calculation or a rule, the same phase or phase 4 removes HT's copy. No phase ends with a new duplicate that has no planned removal.
- **Every new route** is a standard REST route, reached through `call_kiln_api`. No new MCP tools. Each new or changed route updates the generated web client schema and the skill's API reference in the same phase, because CI checks both.
- **Kiln's conventions apply** to all new code in the Kiln packages.

## 3. Phase 1: Move

HT's code, tests, docs and demo project come into the Kiln repository. HT works as it does today.

- **Same behaviour.** The gateway, HT's own skills, its copies of the knowledge and its REST client stay as they are. A run of HT from the Kiln repository gives what a run from its own repository gives.
- **Same commands.** The command `harness-tuner` and its options do not change. The other four console scripts stay until phase 4.
- **Kiln's checks.** HT's tests run in Kiln's CI. HT's code passes Kiln's lint and format checks. **Proposed:** the type check may come in steps, which the architecture sets, because HT has about 57,000 lines that Kiln's type checker has not seen.
- **Not built.** Nothing of the two-repository design: no version route, no minimum-version field, no contract test, no reader of Kiln's skill over MCP.
- **The version.** **Proposed:** from its first release out of the Kiln repository, HT has Kiln's version number.
- **The old repository.** It gets a pointer to the new place. When, and what happens to its open work, is the owner's call.
- **Packaging** is open (overview). This phase needs only that a developer can run HT from the repository, and that today's way to install it keeps working until a later phase replaces it.

Done when: HT's full test suite passes in Kiln's CI, and one run on the demo project from the Kiln repository completes.

## 4. Phase 2: Kiln APIs

Every number and definition is HT's, unchanged, except where this section says so. Where HT has a test that pins a value, Kiln has a test with the same value. None of these routes spends money.

### 4.1 Significance floor

A new operation, `significance_floor`, on the existing `POST /api/statistics`. Pure arithmetic.

- **In:** `test` (`mcnemar_paired` for pass/fail scores, `compare_paired` for rating scores), `confidence` (default 0.95, as the other operations), and optionally `n` (paired items) and `room` (items not at the best value).
- **Out:** `floor` (the fewest changed items, all one way, that the test can call significant; 6 for pass/fail at 0.95), `fewest_wins`, `best_case_change`, `interval_wins`, `interval_best_case`, and a one-sentence `interpretation`. A value that cannot be computed from what was given is null.

### 4.2 Detectability of a run config

`GET …/tasks/{task_id}/run_configs/{run_config_id}/eval_detectability`

Answers: can this task's evals show an improvement of this run config at all?

- **In:** an optional `eval_ids` list. The default is every eval that is not archived and has a default judge config.
- **Out:** one row for each comparable score: `eval_id`, `eval_name`, `eval_config_id`, `score_key`, `score_type`, `direction`, `n`, `room`, `unscored`, `floor`, `fewest_wins`, `best_case_change`, `interval_wins`, and a `val` object: the size of the val split, an estimate of its room, its best-case change and `interval_best_case`.
- **Reads:** the run config's stored train rows on each eval's default judge config, and the sizes of the train and val splits. It reads no val or test result. "Train" is the eval's train split, as the results route resolves it.
- Several stored rows of one item are folded into one, by the mean, as HT does.
- An eval with no stored train row gives rows with `n = 0`. Neither that nor an eval with no default judge config is an error.
- The route returns facts only. Whether a result is too weak to act on is the caller's decision.
- **Proposed:** the confidence is fixed at 0.95.

### 4.3 Smell check

`GET …/tasks/{task_id}/run_configs/{run_config_id}/smell_check`

Checks a run config for the five smells that code can detect. Pure code, no model call.

| Smell id | Limit |
|---|---|
| `very-long-prompt` | 200,000 characters |
| `very-long-tool-description` | 4,096 characters |
| `very-long-skill-description` | 1,024 characters |
| `too-many-tools` | 40 tools (a skill is not counted) |
| `old-model` | 8 months since release |

- **Out:** `detections`, each with `smell`, `detector`, `scope`, `fact`, `value`, `reference` (the limit) and `reference_source`. Also `checked` (the five smell ids, each with its limit), `unread_tools` and `unread_skills`.
- A skill that cannot be read is named in `unread_skills`. The other skills are still checked.
- The model's release date comes from Kiln's model info. A model with no known release date gives no `old-model` detection and is named in the response.
- The limits are fixed in Kiln. No parameter changes one.
- **Proposed:** the route takes no date. It uses today's date.

### 4.4 Scores by split

Four summary routes are fixed to the test split today: the judge config's `score_summary`, the task's `eval_results_summary`, and the two `eval_scores` routes of run configs.

- Each gets an optional `split`: `train`, `val` or `test`. The default stays `test`, so existing callers see no change.
- The judge config's `score_summary` is about one eval: it returns a 422 when the eval has no such split. The other three cover every eval of the task; an eval that has no such split is left out, as happens today for an eval with no test split.
- The owner wants the compare view of the UI to show val and test results. These routes are the source for it. The UI change itself is not in this spec.

### 4.5 Paired comparison of two run configs

`GET …/evals/{eval_id}/eval_config/{eval_config_id}/run_config/{run_config_id}/paired_comparison?baseline_run_config_id=…&split=…`

Compares a candidate with a baseline on one eval, from stored results, without returning any row.

- **Out:** for each score: `score_key`, `score_type`, `direction`, `n_items`, `baseline_score`, `candidate_score`, `delta`, `p_value`, `significant`, `ci_low`, `ci_high`, `headroom`, `fail_to_pass`, `pass_to_fail`. Also how many items each side has a result for.
- No item id and no per-item value is in the response.
- `significant` reads the unrounded p value. HT compared a rounded value until now, so a p between 0.04995 and 0.05 changes side. The owner accepted this.
- One eval for each call. It returns no headline number across evals.
- The confidence is fixed at 0.95.
- **Proposed:** `split` is required and may be `train`, `val` or `test`. The route itself does not refuse `test`: an unscoped caller, such as the UI, may compare on it. A scope that withholds test numbers refuses it (section 5).
- **Proposed:** the name is `paired_comparison`, because the existing `run_comparison` beside it runs evals on the test split and spends money.

### 4.6 Skill bundles

Kiln's API can create a skill today, but only its `SKILL.md`. It cannot add or read a reference file.

**Create from a folder:** `POST /api/projects/{project_id}/skills/from_folder`

- **In:** `folder_path` (an absolute path on the machine that runs Kiln) and `provenance`.
- The caller writes a skill folder in a place of its own and names the path. Kiln checks that it is a valid skill and copies it into the project. The caller never writes into the project, and never writes a `.kiln` file.
- The folder holds exactly: `SKILL.md`, and optionally `references/` and `assets/`. Nothing else at its root.
- `SKILL.md` has front matter with exactly `name` and `description`, and a body that is not blank. The name follows Kiln's existing skill name rules. The description is 1 to 1,024 characters.
- Every file is UTF-8 text. A binary file is refused. (Binary assets are a P2, outside this spec.)
- No symlinks. Each file is at most 512 KiB, and the whole folder at most 2 MiB.
- A name that another skill of the project has is allowed, as on the existing create route. A new version of a skill may keep its name.
- Kiln writes the skill with its own datamodel. The skill is listed only when it is whole. A failure leaves nothing behind.
- **Errors:** every problem with the folder is reported in one answer. Nothing is written on a refusal.
- **Out:** the skill, and its tool id (`kiln_tool::skill::<id>`).

**Read back:**

- `GET /api/projects/{project_id}/skills/{skill_id}/files` lists every file of a skill with its path and size.
- `GET /api/projects/{project_id}/skills/{skill_id}/files/{path}` returns one file as text.

### 4.7 The exact test

`mcnemar_exact_p` fails above about 1,030 changed pairs today. The arithmetic is fixed, with a test. No new route works around it.

### 4.8 What loop agents need that has no endpoint today

Two gateway tools do work that no single API call does. Phase 4 needs an answer for each, and a chat client has the same need.

- **A trace as text.** The gateway writes each train trace as a readable file that an agent can search. Kiln returns a trace as JSON. **Proposed:** a new route returns one task run's trace as readable text, in the form HT's trace files have today. With `save_to_tmpfile` an agent gets a file to search.
- **Run a run config on a train item, by the item's id.** The gateway takes an item id and reads the input itself, so the agent does not supply the input text. Kiln has this for an eval with a V2 judge: an eval job with `judge: false`, `split: "train"` and `item_ids`. **Proposed:** that job is the way for every eval, and the gap for an eval with a legacy judge is closed here.

### 4.9 Skill text for the new routes

- The files that say only Kiln Harness Tuner can install a skill with reference files name the skill bundle routes: `references/levers/skill.md`, `references/knowledge/adding_skills.md`, and the chat guide. The lever also stops saying that a new version needs a new name.
- `references/knowledge/train_val_test.md`, the table of which call reads which split, names the `split` parameter and the paired comparison. It stops telling the reader to use the results call with a `jq_filter` for val numbers.
- The chat guide's section on reading the shared documents names the detectability read and the smell check, where it says today that a chat client does not have them.
- The knowledge trees themselves are not reworded for these routes. Spec one's rule holds: they keep HT's text, and the chat guide explains them.

Done when: each route has tests with HT's pinned values, and the skill's checks pass.

## 5. Phase 3: Scopes

### 5.1 What a scope is

- A scope is a set of settings on one MCP connection. It is in the URL path of the connection. It is self-describing: no token, and no memory on the server.
- The MCP tool passes the scope to the API on its loopback call, as a header. The API enforces it.
- The header can only take away. A request with no header is today's API.
- Scoping adds no tool and hides no tool. A scoped connection has the same two tools and the same API, and gets a clear error when a call goes outside its scope.
- **Proposed:** the forms of the URL:

  | URL | Scope |
  |---|---|
  | `/mcp` | The default (5.3) |
  | `/mcp/open` | No scope. The user opted out |
  | `/mcp/<settings>` | The settings named, for example `fence_eval_data=val,test;fence_eval_results=val,test;block_eval_changes` |

  The architecture sets the exact syntax. A URL that names an unknown setting is refused when the client connects.

### 5.2 The four scopes

**`fence_eval_data=<splits>`** withholds the per-item data of the named splits.

- An item is withheld when it is in a named split of any eval of the task. Whether an item is in a split comes from the eval definitions only, not from the name of a tag.
- Withheld: the item itself (an eval input, or a dataset run), its result rows, its traces and its judge traces.
- The results route looks only at the split that the request names: a request for a named split is refused. An item that is train in one eval and held out in another is still returned in the train rows of the first. This is a known limit, accepted.
- A direct read of a withheld item or of a run made from it is refused.
- The eval-input list is asked with its existing filter for a split the caller can read. It fails in full if the answer would hold a withheld item.
- The two run lists fail in full when the answer would hold a withheld item. Runs are the older form of eval data, so a good error is enough here.
- A dataset run that is in no split is readable.
- Routes that copy many items out at once, such as the dataset download, are refused.

**`fence_eval_results=<splits>`** withholds the numbers of the named splits.

- The four summary routes of 4.4 and the paired comparison of 4.5 are refused for a named split. A call to a summary route with no `split` means `test`, so it is refused when `test` is named.
- The existing routes that run a comparison or a calibration over the test split are refused when `test` is named.
- **Proposed:** an eval job on a named split is refused, because the connection could read nothing of what it produces.
- **Proposed:** a memory record that carries a tag with the name of a named split, for example `val`, is hidden, and the connection cannot write that tag. HT's code stores the val numbers of each promotion in such a record. See question 2.

**`block_eval_changes`** The connection cannot:

1. create, edit or delete an eval, a spec or a judge config, or change an eval's default judge;
2. create, edit or delete eval inputs;
3. change a dataset run that is in any eval split: edit, re-tag, rate, repair or delete;
4. give a run a tag that an eval split uses.

This is also what stops a withheld item from being made readable.

**`readonly`** Only GET requests that do not stream. No exception for a route or a caller.

### 5.3 Defaults

| Connection | `fence_eval_data` | `fence_eval_results` | `block_eval_changes` | `readonly` |
|---|---|---|---|---|
| REST with no scope | — | — | — | — |
| `/mcp` (every MCP client by default) | val, test | test | — | — |
| `/mcp/open` | — | — | — | — |

HT's connections are in 6.2.

### 5.4 Refusals

- A request succeeds in full or fails. Nothing is dropped in silence.
- The error says what was withheld, why, and what the caller can do in its place. For example: read the val result by numbers with the paired comparison. It names the skill file that has the rule.
- The error does not tell the reader how to remove the scope.

### 5.5 Complete by test

- Every route of the API is classified for each scope: not affected, refused, or checked by a named rule.
- A test fails the build for a route with no classification. So a new route cannot be added without a decision.
- Each rule of 5.2 has tests on the REST API with the header, and one test through the MCP URL.

### 5.6 What the scopes do not do

Stated so that nobody assumes more:

- They prevent accidental disclosure. They are not a defence against a caller that works to get around them.
- They do not control file access. An agent that can read the project folder can read every item.
- Not mitigated, by decision: a task that uses Kiln's own API tool, a tool server at Kiln's own address, code that a code tool or a code judge runs, and the job error log read by run id.
- The prompt generators that copy stored runs into a prompt can copy a held-out item. The cleanup and robustness project fixes the generators. See question 5.

### 5.7 What users see

- **The MCP server is live.** After this phase a chat client on `/mcp` can no longer read val or test rows, or test numbers. The release notes say so.
- **The skill** explains the default and its reason: the rule in `references/knowledge/train_val_test.md`, and one line in the root `SKILL.md`. The val numbers come from the routes of 4.4 and 4.5, which is why phase 2 comes first.
- **The Connect page.** **Proposed:** one sentence says what an MCP client cannot read by default, with a link to the help article that gives the opt-out URL. No new control.

Done when: the tests of 5.5 pass, and a chat client on `/mcp` can do a one-off experiment by the skill's guide with no refused call.

## 6. Phase 4: Harness-tuner on Kiln's MCP server and skill

### 6.1 The role files

- HT's seven role skills, the reference files of the build skill, and the hand-written parts of its role entry files move into Kiln's skill, under `references/client_guidance/harness_tuner/`.
- They are ported as written. The changes are: a gateway tool becomes the endpoint doc of the call it made; a link to HT's knowledge copy becomes the path in Kiln's skill; a removed skill (`memory`, `kiln-api`, the code tool skill, `experiment-costing`, `kiln-task-setup`) becomes the Kiln file that replaced it.
- **Proposed:** in prose, the words follow the renames that Kiln's knowledge already uses ("candidate", "quick check", "confirmation on val"). The names of HT's input and output fields do not change.
- One file holds what every role shares: you are not interactive; your role file wins over any other file; never read the chat guidance; which calls your connection will refuse and why. It takes the place of the gateway skill.
- Where the gateway did several calls for one tool, the role file teaches the sequence. Examples: the list of available tools (three calls), a sub-task's prompt (four calls).
- A generated table in an entry file becomes a pointer to the same table in Kiln's index. The two hand-kept tables of the entry files go: the smell check lists the smells that code detects, and the lever documents name their endpoints.
- A file over Kiln's limit of 30,000 characters is split. The planner's file has 75,000.
- A role's prompt names its role file by path. The agent reads it with `kiln_skill`.
- HT's code that copies skills into each agent CLI's folder is removed, with the skill files.

### 6.2 The connections

Each agent session connects to Kiln's MCP server on the URL for its role. It has no other route to Kiln: as today, its shell has no network and it cannot read the project folder.

| Roles | `fence_eval_data` | `fence_eval_results` | `block_eval_changes` | `readonly` |
|---|---|---|---|---|
| Planner, builder, probe, analyst | val, test | val, test | yes | — |
| Baseline review, describe eval | val, test | val, test | yes | yes |
| Promote, report (the val readers) | val, test | test | yes | yes |
| Integrity review, generality review | no connection, as today | | | |

- There is no list of tools or routes for a role. A planner can call the route that creates a run config, which the gateway did not give it. Its role file says what its role does. This was decided with the scopes.
- **The val readers** read val by numbers: the summary routes with `split=val` and the paired comparison. They cannot read a val row. They write nothing.
- **The experimental eval-building role** creates evals, which `block_eval_changes` refuses. **Proposed:** that role's connection does not have `block_eval_changes`, and its role file tells it to change only the evals it created. The option that starts it stays experimental. See question 3.

### 6.3 What replaces each group of gateway tools

| Gateway tools | After |
|---|---|
| Reads of the task, run configs, prompts, evals, specs, tools, skills, documents | The same reads through `call_kiln_api` |
| Train results | The results route with `split=train`. The agent names the split; the scope refuses any other |
| One task run, with its trace | The run route, and the trace as text (4.8) |
| Train items and their expected outputs | The eval-input routes, asked for the train split |
| Run a run config on a train item | The eval job of 4.8 |
| Run a train eval | The eval job route with `split=train`, and the wait route |
| Create a run config, a prompt, a code tool; archive | The same writes through `call_kiln_api` |
| Install and export a skill bundle | The skill bundle routes (4.6) |
| Model information | Kiln's model info routes |
| Memory | Kiln's memory routes, by the rules of `references/knowledge/memory.md` |
| Statistics | `POST /api/statistics`. A `readonly` role uses the paired comparison in its place |
| The val summary | Loop code puts it in the val readers' input. No call |
| Paging of a long answer | `body_limit`, `jq_filter` and `save_to_tmpfile` of `call_kiln_api` |

A file that `call_kiln_api` saves must be readable inside the agent's sandbox.

### 6.4 Rules of the gateway that are not scopes

| Gateway rule | After |
|---|---|
| The model policy on a run config an agent creates or runs | See question 1 |
| An answer holds only named fields | Not kept. The agent gets Kiln's answer. Accepted |
| A tag named like `holdout` marks an item as held out, also when no eval uses it | Not kept. Held-out status comes from eval definitions only (5.2). HT's start-up check still warns about such tags |
| An item that is train in one eval and held out in another is kept from agents | Not kept (5.2). HT's start-up check still reports the overlap |
| One project and one task for a session | Not kept. The role's input names both |
| Which role may write which memory record | Role files, and the rules of `memory.md` |
| Val readers write nothing, on disk too | `readonly` on the connection. The file rule is HT's, as today |

### 6.5 Loop code

Loop code is trusted. It calls Kiln with no scope, and it keeps val and test data away from its agents itself, as today.

- It uses Kiln's one copy of each calculation: the detectability read and the floor, the paired comparison for the numbers of a comparison, the smell check, model information, and the skill bundle routes. It calls the route or imports the code; the architecture chooses, by the packaging.
- Kept in HT: the refusal of an underpowered run and its options, the stop rules, the promotion rules, the screening and measurement engine, the latency comparison, the integrity, judge-copy and reference checks, the generality review, the model policy, and the noise check behind its option.
- The noise check is not changed in what it does. It uses Kiln's floor functions where it used HT's copy.
- It still reads the rows itself for cost, latency and missing items.

### 6.6 Removed from HT in this phase

- Its copy of the knowledge, with the code that loads, checks and indexes it, and its maintenance skill for coding agents.
- Its API reference docs, and its `call_kiln_api` server.
- Its model catalogue, and the option `--no-model-catalog`.
- Its skill installer.
- Its five smell detectors, and its own floor, detectability and comparison arithmetic.
- The skills `memory`, `kiln-harness-tuner-code-tool-authoring`, `experiment-costing` and `kiln-task-setup`. Kiln's skill has each.
- The command `harness-tuner-install-agents`, and three more console scripts: the skill installer's server, `kiln_api_mcp`, and (in phase 5) the gateway's server.
- Its start-up probes of Kiln's API list. One release has both.

The gateway's code is not removed in this phase. It is no longer used.

Done when: HT's tests pass, and a run on the demo project completes with every agent on a scoped connection.

## 7. Phase 5: Proof, then the gateway goes

1. **Scope tests.** Each of the gateway's fence tests has a test of the same intent on a scoped connection: a held-out row cannot be read, a val number cannot be read by a train-side role, an eval cannot be changed, a val reader cannot write. A gateway test with no scope test is listed, with the reason (6.4).
2. **The audit.** A read of the moved HT against the checklist of its core concepts. Each item is checked in the place that now carries it: a scope, a role file, Kiln's skill or HT's code. The checklist is the switchover's (its functional spec, section 7): tune on train, confirm on val, never read test; val by numbers only; the promotion rule; one change for each experiment; new objects only; provenance; no train item value or judge text in a prompt, skill or tool; hard limits; only allowed models; cost from recorded usage; the memory conventions; val readers write nothing; one attempt for each idea; the task's default run config is never changed; the verdict words; the loop never asks a person.
3. **Runs on the demo project.** Full runs with default options. A run passes when it finishes without an error from a missing file, a refused call that the role needed, or a wrong call that the agent could not correct, and its report is written. **Proposed:** the owner reads the runs and decides whether agent sessions on the generic API work well enough, by the number of failed calls and the cost of each session against a run from phase 1.
4. **Then:** the gateway, its tests and its console script are deleted.

If the proof fails and cannot be fixed, phase 4 is taken back. HT stays on its gateway. Phases 1 to 3 stand.

## 8. Out of scope, and risks

Out of scope:

- Withholding on the raw API by default.
- A port of the noise check into Kiln.
- A UI for HT, and the compare view's display of val and test results.
- Binary assets in a skill.
- A guide that tells a chat client how to start HT. It stays in Kiln's knowledge backlog until the packaging is decided.
- Moving any other HT tool into Kiln's API: the screening and measurement engine, the model preflight, the integrity, judge-copy and reference checks, the generality review, probes and the latency comparison.

Risks:

- **Loop agents on the generic API.** A typed tool is hard to call wrongly. On `call_kiln_api` an agent reads a doc, then builds a path and a body. More tokens and more wrong calls are likely. Phase 5 measures it, and the gateway is the fallback until then.
- **A weaker fence in known places** (6.4). Each is accepted under "accidental, not adversarial". HT's public promise says the test set is never read; its docs must say what enforces that after the move.
- **A route that is missed.** A route with the wrong classification leaks under a scope, in silence. The test of 5.5 covers a new route. It does not check that a classification is right; the scope tests of phase 5 do that for the gateway's cases.
- **A scope that leaks into background work.** An eval job that a scoped request starts must run unscoped, or it filters its own reads. The architecture keeps the scope on the request.
- **A live default changes** (5.7).
- **Size of the move.** About 57,000 lines and 4,000 tests come under Kiln's checks and CI.

## 9. Questions for the owner

1. **The model policy.** The gateway refuses a run config with a model the policy does not allow, when an agent creates one or runs one. Without the gateway, an agent can create and run such a run config before loop code sees it, and the task's data goes to a provider the user did not allow. Loop code re-checks only before its own eval jobs. Options: (a) a fifth setting on the connection that names the allowed models; (b) role files state the allowed models, and loop code checks each run config an agent made before anything else uses it, which leaves the agent's own quick runs unchecked; (c) Kiln gets a project-level list of allowed models, which every caller obeys. **Proposed:** (a).
2. **The `val` memory record.** HT's code stores the val numbers of each promotion in a memory record tagged `val`. Train-side roles must not read it, and a chat client may. The proposal in 5.2 makes `fence_eval_results` hide a record that carries a named split's name as a tag. That puts a tag convention into Kiln's API. The other choice: HT stops storing val numbers in memory, and chat clients read them from the summary routes.
3. **The experimental eval-building role** (6.2): leave it without `block_eval_changes`, as proposed, or remove the option until scopes can say "only evals this connection created".
4. **The paired comparison and the test split** (4.5): the route allows `test` for an unscoped caller, as proposed, so that the UI's compare view can use it.
5. **The cleanup and robustness project.** The prompt generators copy stored runs into a prompt by rating, not by split, so a held-out item can reach an agent. Does phase 3 wait for that project's fix, or does a scope with `fence_eval_data` refuse those generators until it lands?
