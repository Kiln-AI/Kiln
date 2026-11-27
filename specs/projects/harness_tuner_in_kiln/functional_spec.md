---
status: draft
---

# Functional Spec: Harness Tuner in Kiln

Read the [project overview](project_overview.md) first. This document says what each of the seven phases delivers.

Words used here:

- **HT** is Kiln Harness Tuner. Its code is at commit `6780366` of its own repository when this was written.
- **The gateway** is HT's own MCP server for its agents. It has 54 tools. It stays until phase 6.
- **Loop agents** are the agent sessions HT starts (planner, builder, analyst and the others). **Loop code** is HT's own Python.
- **A chat client** is an agent that works with a user over Kiln's MCP server.
- **Scoped** means a request that carries a scope. **Unscoped** means one that does not.

A line marked **Proposed** is a call made while drafting. The owner can overrule it. Section 11 lists the questions that need the owner.

Sources that this document draws on, and replaces where they differ:

- [review_fixes.md](../harness_tuner_switchover/review_fixes.md): the decisions of the switchover review.
- [scope_decisions.md](../harness_tuner_port/scope_decisions.md): the scope rulings.
- The switchover's [functional spec](../harness_tuner_switchover/functional_spec.md), sections 3 and 7: the first form of the Kiln APIs and of the proof.

## 1. What changes, in short

| Area | Today | After |
|---|---|---|
| Where HT lives | Its own repository, its own releases | The Kiln repository, Kiln's releases. The PyPI package `harness-tuner` stays, as a thin launcher of Kiln's copy (phase 7) |
| How a loop agent reaches Kiln | HT's gateway, 54 typed tools | Kiln's MCP server, on a scoped URL: `call_kiln_api` and `kiln_skill` |
| What keeps val and test from an agent | The gateway's rules, for HT's agents only | Scopes in Kiln's API, for every MCP connection. And HT's code, which does not pass those values to its agents |
| Role procedures | Skill files that HT copies into each agent CLI's folder | Files of Kiln's skill, under `references/client_guidance/harness_tuner/` |
| Knowledge, API reference, model information | HT ships copies | Kiln's own. The copies are removed |
| Measurement calculations (floor, detectability, paired comparison, smells) | HT code | Kiln code, one copy, behind standard APIs |
| The REST API for a caller that sends no scope | — | Unchanged |

## 2. Rules for every phase

- **Each phase is complete on its own.** It can be merged and released without the next one.
- **HT's method does not change.** Its numbers, its rules for keeping a candidate and its loop are moved, not redesigned. Where a rule must change, a person signs it off first, in so many words. This document names the changes it knows of.
- **Loop code has minimal rewrites.** HT's own Python keeps its structure and its call sites. Where Kiln and HT must share one calculation, the function moves to a place both import; its callers in HT are not rewritten.
- **One copy.** When a phase gives Kiln a calculation or a rule, the same phase or phase 4 removes HT's copy. No phase ends with a new duplicate that has no planned removal.
- **Every new route** is a standard REST route, reached through `call_kiln_api`. No new MCP tools. Each new or changed route updates the generated web client schema and the skill's API reference in the same phase, because CI checks both.
- **Kiln's conventions apply** to all new code in the Kiln packages.

## 3. Phase 1: Move

HT's code, tests, docs and demo project come into the Kiln repository. HT works as it does today.

- **Same behaviour.** The gateway, HT's own skills, its copies of the knowledge and its REST client stay as they are. A run of HT from the Kiln repository gives what a run from its own repository gives.
- **Same commands.** The command `harness-tuner` and its options do not change. HT's package installs four more commands today, and all four stay in this phase, because nothing changes yet:

  | Command | What it is | Goes in |
  |---|---|---|
  | `harness-tuner-gateway-mcp` | Starts the gateway. HT runs it for each agent session; a person does not | Phase 6, with the gateway |
  | `harness-tuner-skill-installer-mcp` | Starts the skill installer's server. HT runs it for two roles | Phase 4: the skill bundle routes replace it |
  | `harness-tuner-install-agents` | Copies HT's skills into a person's own project, for work by hand with an agent | Phase 4: Kiln's MCP server and skill replace it |
  | `kiln_api_mcp` | HT's own `call_kiln_api` server, for the same work by hand | Phase 4: Kiln's MCP server replaces it |
- **Kiln's checks.** HT's tests run in Kiln's CI. HT's code passes Kiln's lint and format checks. **Proposed:** the type check may come in steps, which the architecture sets, because HT has about 57,000 lines that Kiln's type checker has not seen.
- **Not built.** Nothing of the two-repository design: no version route, no minimum-version field, no contract test, no reader of Kiln's skill over MCP.
- **The version.** **Proposed:** from its first release out of the Kiln repository, HT has Kiln's version number.
- **The old repository** keeps working for its users until phase 7. It is made private as the last step of this project (section 9).
- **Packaging.** This phase needs only that a developer can run HT from the repository. Today's PyPI package keeps working, unchanged, until phase 7 replaces it.

Done when: HT's full test suite passes in Kiln's CI, and one run on the demo project from the Kiln repository completes.

## 4. Phase 2: Kiln APIs

The bar for this phase: each route gives the same result that HT's own code gives today. Every number and definition is HT's, unchanged, except where this section says so. Where HT has a test that pins a value, Kiln has a test with the same value. None of these routes spends money.

The owner approved the proposals of this section on 2026-11-27, on that bar.

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
- The confidence is fixed at 0.95.

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
- The route takes no date. It uses today's date.

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
- `split` is required and may be `train`, `val` or `test`. The route itself does not refuse `test`: an unscoped caller, such as the UI, may compare on it. A scope that withholds test numbers refuses it (section 5).
- The name is `paired_comparison`, because the existing `run_comparison` beside it runs evals on the test split and spends money.

### 4.6 Skill bundles

Kiln's API can create a skill today, but only its `SKILL.md`. It cannot add or read a reference file.

**Create from a folder:** `POST /api/projects/{project_id}/skills/from_folder`

- Every MCP client can call it. Creating a skill with reference files over MCP is wanted, not only for HT.

- **In:** `folder_path` (an absolute path on the machine that runs Kiln) and `provenance`.
- The caller writes a skill folder in a place of its own and names the path. Kiln checks that it is a valid skill and copies it into the project. The caller never writes into the project, and never writes a `.kiln` file.
- The folder holds exactly: `SKILL.md`, and optionally `references/` and `assets/`. Nothing else at its root.
- `SKILL.md` has front matter with exactly `name` and `description`, and a body that is not blank. The name follows Kiln's existing skill name rules. The description is 1 to 1,024 characters.
- Every file is UTF-8 text. A binary file is refused. (Binary assets are a P2, outside this spec.)
- No symlinks. Each file is at most 4 MB, and the whole folder at most 25 MB. Inside those limits, a reasonable design is the caller's job.
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

- **A trace as text.** The gateway writes each train trace as a readable file that an agent can search. Kiln returns a trace as JSON. A new route returns one task run's trace as readable text, in the form HT's trace files have today. With `save_to_tmpfile` an agent gets a file to search.
- **Run a run config on a train item, by the item's id.** The gateway takes an item id and reads the input itself, so the agent does not supply the input text. Kiln has this for an eval with a V2 judge: an eval job with `judge: false`, `split: "train"` and `item_ids`. That job is the way for every eval, and the gap for an eval with a legacy judge is closed here.

### 4.9 Skill text for the new routes

- **Creating a skill with reference files.** Kiln's skill tells a chat client today that this needs Kiln Harness Tuner, because no API could do it. After this phase any MCP client can do it with the skill bundle routes. So that text is removed, and the routes are named in its place. The three places:
  - `references/levers/skill.md`: "install with the `install_skill_bundle` tool of Kiln Harness Tuner's skill installer. The skill installer is not a Kiln endpoint".
  - `references/knowledge/adding_skills.md`: "`references/*` files have NO API."
  - The chat guide: the skill installer is listed as a tool that Kiln does not have.
- **A new version of a skill.** The lever says "install it under a new name" and "Each name can be installed once". Both go. The new text: a new version may keep the name, and this is common. A new run config attaches the new version in place of the old one, so no prompt that names the skill needs a change.
- `references/knowledge/train_val_test.md`, the table of which call reads which split, names the `split` parameter and the paired comparison. It stops telling the reader to use the results call with a `jq_filter` for val numbers.
- The chat guide's section on reading the shared documents names the detectability read and the smell check, where it says today that a chat client does not have them.
- The knowledge trees themselves are not reworded for these routes. Spec one's rule holds: they keep HT's text, and the chat guide explains them.

Done when: each route has tests with HT's pinned values, and the skill's checks pass.

## 5. Phase 3: Scopes

### 5.1 What a scope is

- **A scope is a set of restrictions that a request to Kiln's REST API can carry.** The request names them in one header. The API enforces them.
- A request with no header is today's API, with no new code path. The header can only take away.
- Any REST caller may send the header. The caller that always does is Kiln's MCP server.
- **An MCP connection has one scope for all its calls.** The URL path of the connection names it. The `call_kiln_api` tool puts it in the header of each call it makes to the API. The scope is self-describing: no token, and no memory on the server.
- Scoping adds no tool and hides no tool. A scoped connection has the same two tools and the same API, and gets a clear error when a call goes outside its scope.
- **Proposed:** the forms of the URL:

  | URL | Scope |
  |---|---|
  | `/mcp` | The default (5.3) |
  | `/mcp/open` | No scope. The user opted out |
  | `/mcp/<settings>` | The settings named, for example `fence_eval_data=val,test;fence_eval_results=val,test;block_eval_changes` |

  The architecture sets the exact syntax. A URL that names an unknown setting is refused when the client connects.

### 5.2 The five scopes

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
- **An eval job on a named split is allowed.** The connection cannot read what the job produces, but it can run the job and give the user the link to the page of the UI that shows the result. This is a common case, for example the test result at the end of the work. The docstring of the eval job route names this case as allowed: run, then link. The skill's text on the test split is updated for it, and that wording gets the owner's sign-off, because it touches a rule of the method.
- **A memory record that carries a tag with the name of a named split, for example `val`, is hidden,** and the connection cannot write that tag. HT's code stores the val numbers of each promotion in such a record. This is the gateway's rule of today, kept with the same logic and applied to a scoped connection. (Decided by the owner, 2026-11-27.)

**`block_eval_changes`** The connection cannot:

1. create, edit or delete an eval, a spec or a judge config, or change an eval's default judge;
2. create, edit or delete eval inputs;
3. change a dataset run that is in any eval split: edit, re-tag, rate, repair or delete;
4. give a run a tag that an eval split uses.

This is also what stops a withheld item from being made readable.

**`readonly`** Only GET requests that do not stream. No exception for a route or a caller.

**`block_deletes`** Every `DELETE` request is refused. A simple check of the method, and nothing else.

### 5.3 Defaults

| Connection | `fence_eval_data` | `fence_eval_results` | `block_eval_changes` | `readonly` | `block_deletes` |
|---|---|---|---|---|---|
| REST with no scope | — | — | — | — | — |
| `/mcp` (every MCP client by default) | val, test | test | — | — | — |
| `/mcp/open` | — | — | — | — | — |

HT's connections are in 6.2.

### 5.4 Refusals

- **First: withheld data is never returned.** This rule has no exception.
- **Second, as the goal: a request succeeds in full or fails,** and nothing is dropped in silence. Where that costs too much for a route, the route may leave the withheld items out. Its answer then says how many it left out. The architecture lists each route that does this, with the reason.
- The error says what was withheld, why, and what the caller can do in its place. For example: read the val result by numbers with the paired comparison. It names the skill file that has the rule.
- The error does not tell the reader how to remove the scope.

### 5.5 Complete by test

- Every route of the API is classified for each scope: not affected, refused, or checked by a named rule.
- A test fails the build for a route with no classification. So a new route cannot be added without a decision.
- Each rule of 5.2 has tests on the REST API with the header, and one test through the MCP URL.
- **Kept over time.** Kiln's code review guidance gains a check for val and test leaks: a new or changed route that returns eval items, their results or their numbers has a scope classification and a test, and a reviewer looks for a new way that such data can leave. The guidance for coding agents that write API code says the same.
- **Documented.** A README in `app/mcp` describes the scopes: what each one does, the URL forms, the defaults, the header, and how to classify a new route.

### 5.6 Files that `call_kiln_api` saves

`call_kiln_api` can save a large answer to a file (`save_to_tmpfile`). Today every connection saves into one folder, so an agent that may read that folder can read a file that a connection with a weaker scope saved there.

- **A folder for each scope.** A connection saves into a sub-folder of Kiln's temp folder. The name of the sub-folder is worked out from the connection's scope, and from nothing else, so the server keeps no memory of a connection. A connection with no scope has a sub-folder too.
- Connections with the same scope share a sub-folder. They may read the same data, so nothing is disclosed.
- The clean-up of old files covers every sub-folder, as it covers the one folder today.
- The tool's answer gives the full path of the saved file, as today.
- Kiln gives a caller a way to learn the folder of a scope before any file is saved, so that a sandbox can be set up first. The architecture sets how.

### 5.7 What the scopes do not do

Stated so that nobody assumes more:

- They prevent accidental disclosure. They are not a defence against a caller that works to get around them.
- They do not control file access. An agent that can read the project folder can read every item.
- Not mitigated, by decision: a task that uses Kiln's own API tool, a tool server at Kiln's own address, code that a code tool or a code judge runs, and the job error log read by run id.
- The prompt generators that copy stored runs into a prompt can copy a held-out item. The cleanup and robustness project fixes the generators. This project does not work around it. When this project is done, a check says whether that fix is on main; if it is not, the owner is warned (section 8).

### 5.8 What users see

- **The MCP server is live.** After this phase a chat client on `/mcp` can no longer read val or test rows, or test numbers. The release notes say so.
- **The skill** explains the default and its reason: the rule in `references/knowledge/train_val_test.md`, and one line in the root `SKILL.md`. The val numbers come from the routes of 4.4 and 4.5, which is why phase 2 comes first.
- **The Connect page does not change.** The opt-out URL is in the docs.

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

| Roles | `fence_eval_data` | `fence_eval_results` | `block_eval_changes` | `readonly` | `block_deletes` |
|---|---|---|---|---|---|
| Planner, builder, probe, analyst | val, test | val, test | yes | — | yes |
| Baseline review, describe eval | val, test | val, test | yes | yes | yes |
| Promote, report (the val readers) | val, test | test | yes | yes | yes |
| Integrity review, generality review | no connection, as today | | | | |

- **Each agent can read the saved files of its own scope, and no others.** HT gives the agent's sandbox read access to the folder of the agent's scope (5.6), for each agent CLI it supports: Claude Code, Codex and OpenCode. It gives no access to Kiln's temp folder as a whole. Without this an agent cannot open a trace or a long answer that it saved.
  - To verify on each platform: that HT and the Kiln app resolve the same temp folder. They run as the same user.
  - The proof of phase 6 tests both sides: an agent opens a file it saved, and it cannot open a file in another scope's folder.
- There is no list of tools or routes for a role. A planner can call the route that creates a run config, which the gateway did not give it. Its role file says what its role does. This was decided with the scopes.
- **The val readers** read val by numbers: the summary routes with `split=val` and the paired comparison. They cannot read a val row. They write nothing.
- **The experimental eval-building role is removed.** It creates evals, which `block_eval_changes` refuses. The option `--experimental-eval-building` goes, with the role, its prompt, and the instructions in role files and docs that exist only for it. The loop then never builds an eval, which is what it does today when the option is off. Kiln's knowledge keeps its text on new evals: a chat client can build one with its user.

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

A file that `call_kiln_api` saves must be readable inside the agent's sandbox. Sections 5.6 and 6.2 say how: a folder for each scope, and read access to that folder only.

### 6.4 What the gateway does that the scopes do not

**Reviewed by the owner on 2026-11-27.** Each item carries the decision. One item waits: item 4, for an explanation.

**Note:** the owner is weighing another design for how connections are limited: a few roles, each an allow list of routes, in place of the write-side scopes. If that is chosen, items 2, 8 and 9 change. This section is not restructured until that is decided.

The gateway does more than keep val and test away. Each item below is something it does today that no scope does. For each: what it does today, what happens after phase 4, and a proposal.

1. **The model policy.** *Decided (question 1).*
   - Today: the gateway refuses a run config with a model that the user's policy does not allow, when an agent creates one or runs one.
   - After: the role files state the allowed models. Loop code checks each run config an agent made, before anything else uses it.
   - What is lost: an agent can create a run config with another model and run it itself, in a quick check, before loop code sees it. The task's data then goes to a provider the user did not allow.

2. **No deletes, and no edits of what exists.**
   - Today: the gateway has no tool that deletes a record, edits the task, changes a setting or a provider, or changes an existing run config or prompt (it can rename a run config). "New objects only, and the parent is never changed" is true because the tools do not exist.
   - After: a train-side agent can call any route that is not blocked for MCP. That includes the routes that delete a task, a run, a run config's prompt or a memory record, and the route that edits the task and its default run config. `block_eval_changes` covers evals, eval inputs and dataset items in a split, and nothing else. A `readonly` role is safe.
   - Decided: one more scope, `block_deletes`. It is a simple check of the method: it refuses every `DELETE` request. HT's connections set it. Two routes delete with a `POST` (many runs, many documents); the simple check does not cover them, and the role files say not to call them. Edits of the task stay a rule of the role files, checked in the audit.

3. **Code trust.**
   - Today: the builder and the probe call a gateway tool that tells Kiln to trust the project's code tools.
   - After: that route is blocked for every MCP connection, on purpose: only the user grants trust. So an agent cannot call it.
   - Decided: loop code grants trust, from code, at the point where an agent does it today.

4. **An answer holds only named fields.**
   - Today: the gateway copies named fields from Kiln's answer. A field that Kiln adds later cannot reach an agent.
   - After: the agent gets Kiln's whole answer.
   - What is lost: a guard against a future field that carries held-out content, for example a new field of a result row. The scope rules work on items, not on fields.
   - Proposal: accept. The code review check of 5.5 covers a new field on a route that returns eval data. *Waits for the owner, after an explanation.*

5. **Tags that are named like a held-out split.**
   - Today: an item with a tag named `val`, `test`, `val_*`, `test_*`, `holdout*` or `heldout*` is kept from agents, also when no eval uses that tag. The reason: the test items of a deleted eval are still test items.
   - After: held-out status comes from eval definitions only (5.2). Such an item is readable.
   - Decided: accept the loss. HT's start-up check still finds such tags and warns the user before a run.

6. **An item that is train in one eval and held out in another.**
   - Today: the gateway keeps such an item from agents in every read.
   - After: the item is returned in the train rows of the first eval (5.2). A direct read of the item is still refused.
   - Decided: accept. HT's start-up check still reports each overlap, so the user can fix the split design.

7. **One project and one task.**
   - Today: every gateway call is built for the run's project and task. An agent cannot name another.
   - After: the agent names both ids on each call, from its input. It can read another task or project.
   - Decided: accept, and it is wanted: a sub-agent is another task, and an agent must be able to read it.

8. **The input of a run comes from the item.**
   - Today: to run a run config, an agent names a train item. The gateway reads the item's input itself. The agent cannot run free text.
   - After: the eval job of 4.8 does the same, by item id. But the plain run route is open too, and it takes any input text.
   - Decided: accept. The role files name the eval job as the way.

9. **Who may start what, and how much at once.**
   - Today: the planner and the analyst cannot create a run config, run an item or start an eval job. Only the builder exports a skill. The runs that agents start are limited to four at once in each session.
   - After: no tool lists (decided with the scopes). Every train-side role can start a run or an eval job, with a concurrency it chooses, up to Kiln's limit of 100.
   - What is lost: a limit on spend that an agent starts by mistake.
   - Decided: guidance is enough. The role files say which roles do not start runs or eval jobs, and with what concurrency the others do. HT does not track the cost of what agents start.

10. **Memory.**
    - Today: the gateway limits memory calls to the project scope and the task's scope, and it lets only some roles update a record. It writes one line for each memory write to a file, from which HT shows the write in its log and its screen.
    - After: Kiln's memory routes, by the rules of `references/knowledge/memory.md`. Which role writes which record is a rule of the role files. The `val` tag stays protected (5.2).
    - Decided: accept the first two. For the third, loop code reads the memory list after each session and reports what is new, so the log and the screen keep their lines.

11. **Val readers write nothing, on disk too.**
    - Today: the promote and report roles have no write tool, and their sandbox cannot write a file.
    - After: `readonly` on the connection. The file rule is HT's own, unchanged.
    - Decided: no loss.

12. **Small things that go.** The gateway repairs a name that Kiln would refuse, checks a request before it reaches Kiln, and limits an answer to 40,000 characters. After: Kiln refuses a bad name or a bad request with its own error, and `call_kiln_api` limits a body with `body_limit`. Decided: accept.

### 6.5 Loop code

Loop code is trusted. It calls Kiln with no scope, and it keeps val and test data away from its agents itself, as today.

- **Minimal rewrites.** Loop code keeps its structure and its call sites. Where Kiln and HT share a calculation (the floor, detectability, the numbers of a paired comparison, the smells), the function moves into Kiln's code, and both Kiln's route and HT's loop code import it. HT's callers are not rewritten to make HTTP calls.
- It uses Kiln's routes where it used a copy of data: model information and the skill bundle routes.
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
- Three console scripts: `harness-tuner-install-agents`, the skill installer's server, and `kiln_api_mcp` (section 3 has the table). The gateway's server goes in phase 6.
- Its start-up probes of Kiln's API list. One release has both.
- The option `--experimental-eval-building` and the eval-building role (6.2).

The gateway's code is not removed in this phase. It is no longer used. It goes at the end of phase 6.

Done when: HT's tests pass, and a run on the demo project completes with every agent on a scoped connection.

## 7. Phase 5: Coherence check

Phase 4 changes many things at once. This phase builds nothing. It checks that every needed update was made, and fixes what it finds.

- **No name of a removed thing is left.** A search of both the code and every text for: each gateway tool name, each removed skill, each removed command and option, the paths of HT's old knowledge copy, and the words "gateway" and "skill installer" where they describe how things work now.
- **Every pointer resolves.** Each path that a role file, a role prompt or HT's code names in Kiln's skill is a file that exists. Each endpoint doc that a role file names exists, and the route is one the role's connection may call.
- **Each role, end to end.** For each role: its prompt names its role file; the role file names only calls that its scope allows; the calls it needs for its job are all named; and its sandbox can read the folder of its scope's saved files.
- **Kiln's skill reads right for both readers.** The files that changed for this project are read once as a chat client and once as a loop agent.
- **The docs match.** HT's docs (install, command line, architecture, agents, limitations, the contributor guide), the README of `app/mcp`, Kiln's help articles on the MCP server, and the command line's own help text.
- **The tests match.** No test is skipped or deleted without a reason written beside it. No fake of a route differs from the real route.
- **The decisions of this spec.** Each decision of this document and of [review_fixes.md](../harness_tuner_switchover/review_fixes.md) that still applies is found in the result.

Done when: the list is worked through, each finding is fixed or recorded with a reason, and the owner has seen the record.

## 8. Phase 6: Proof, then the gateway goes

1. **Scope tests.** Each of the gateway's fence tests has a test of the same intent on a scoped connection: a held-out row cannot be read, a val number cannot be read by a train-side role, an eval cannot be changed, a val reader cannot write. Also: an agent opens a file that it saved, and it cannot open a file in the folder of another scope (6.2). A gateway test with no scope test is listed, with the reason (6.4).
2. **The audit.** A read of the moved HT against the checklist of its core concepts. Each item is checked in the place that now carries it: a scope, a role file, Kiln's skill or HT's code. The checklist is the switchover's (its functional spec, section 7): tune on train, confirm on val, never read test; val by numbers only; the promotion rule; one change for each experiment; new objects only; provenance; no train item value or judge text in a prompt, skill or tool; hard limits; only allowed models; cost from recorded usage; the memory conventions; val readers write nothing; one attempt for each idea; the task's default run config is never changed; the verdict words; the loop never asks a person.
3. **Runs on the demo project.** Full runs with default options. A run passes when it finishes without an error from a missing file, a refused call that the role needed, or a wrong call that the agent could not correct, and its report is written. **Proposed:** the owner reads the runs and decides whether agent sessions on the generic API work well enough, by the number of failed calls and the cost of each session against a run from phase 1.
4. **Then:** the gateway, its tests and its console script are deleted, and the searches of phase 5 are run again.
5. **A warning, if it applies.** The prompt generators that copy stored runs into a prompt are fixed by the cleanup and robustness project, not by this one. At the end of this phase, check main. If the fix is not there, tell the owner in plain words: a held-out item can still reach an agent through such a generator.

If the proof fails and cannot be fixed, phase 4 is taken back. HT stays on its gateway. Phases 1 to 3 stand.

## 9. Phase 7: The launcher package, and the old repository

- **`harness-tuner` stays on PyPI.** A person who runs `harness-tuner` today, for example with `uvx`, still can.
- **The package becomes a thin launcher.** It holds no tuner code. It gets Kiln's release, installs it, and starts the copy of HT that the release holds. The real code ships with Kiln only.
- The launcher lives in the Kiln repository, in a folder of its own. Its README for PyPI is in that folder. The text is the README HT has today, or very close.
- **Proposed:** the launcher takes the same options as `harness-tuner` and passes them on unchanged. It says which Kiln version it started.
- How it finds, downloads and installs Kiln's release on each platform is for the architecture.
- **Last, by hand:** when the launcher is published and works, the owner makes the old repository private. This is the final step of the project.

Done when: `harness-tuner` from PyPI starts HT from a Kiln release on each platform Kiln supports, and the old repository is private.

## 10. Out of scope, and risks

Out of scope:

- Withholding on the raw API by default.
- A port of the noise check into Kiln.
- A UI for HT, and the compare view's display of val and test results.
- Binary assets in a skill.
- A guide that tells a chat client how to start HT. It stays in Kiln's knowledge backlog.
- Moving any other HT tool into Kiln's API: the screening and measurement engine, the model preflight, the integrity, judge-copy and reference checks, the generality review, probes and the latency comparison.

Risks:

- **Loop agents on the generic API.** A typed tool is hard to call wrongly. On `call_kiln_api` an agent reads a doc, then builds a path and a body. More tokens and more wrong calls are likely. Phase 6 measures it, and the gateway is the fallback until then.
- **A weaker fence in known places** (6.4). Each is accepted under "accidental, not adversarial". HT's public promise says the test set is never read; its docs must say what enforces that after the move.
- **A route that is missed.** A route with the wrong classification leaks under a scope, in silence. The test of 5.5 covers a new route. It does not check that a classification is right; the scope tests of phase 6 do that for the gateway's cases.
- **A scope that leaks into background work.** An eval job that a scoped request starts must run unscoped, or it filters its own reads. The architecture keeps the scope on the request.
- **A live default changes** (5.8).
- **Size of the move.** About 57,000 lines and 4,000 tests come under Kiln's checks and CI.

## 11. Questions, answered

The owner answered these on 2026-11-27. Each answer is written into the section it belongs to.

1. **The model policy without the gateway.** Role files state the allowed models. Loop code checks each run config that an agent made, before anything else uses it. An agent's own quick runs are not checked by code (6.4).
2. **The `val` memory record** is hidden by `fence_eval_results`, as the gateway hides it today (5.2).
3. **The experimental eval-building option** is removed, with its role and its instructions (6.2).
4. **The paired comparison** allows the test split for a caller with no scope (4.5).
5. **The prompt generators.** This project does not work around them. It warns the owner at the end if the cleanup project's fix is not on main (section 8).
