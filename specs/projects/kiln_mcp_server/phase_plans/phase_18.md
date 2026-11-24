---
status: complete
---

# Phase 18: Harness Tuner alignment fixes outside the knowledge trees

## Overview

This phase fixes what the Harness Tuner alignment audits found outside the knowledge trees: `references/knowledge/memory.md`, `references/knowledge/run_an_experiment.md` and the other glue files. The knowledge trees (`references/levers/`, `references/improving_agents/`) belong to Phase 17 ([phase_8_revisit](../phase_8_revisit.md)), and this phase edits none of their files.

The basis is the owner's decisions in [harness_tuner_alignment_decisions.md](../harness_tuner_alignment_decisions.md):
- memory stays one reference for HT and MCP agents, with HT's code-owned records read-only for MCP agents;
- branches are kept to a minimum;
- lanes are cut;
- one guide for MCP clients carries the shared method rules.

**Citations.** The audits are in `research/harness_tuner_alignment_audit/`:
- `HS-` is an item of `ht_skills.md`; `map_<name> Xnn` is a row of `ht_skills_maps/`.
- `CT-n` is row n of the table in section 1 of `contract.md`; `CT-§n` is a section of that file.
- `KT-` is an item of `knowledge_tree.md`.

Kiln paths are from `app/mcp/kiln_mcp_server/skill/`. RX = `references/knowledge/run_an_experiment.md`, MEM = `references/knowledge/memory.md`, TVT = `references/knowledge/train_val_test.md`. Line numbers are at `7af37d1`. HT is Kiln Harness Tuner at `b49f159`.

## Status

The owner set item 5's file and its content list on 2026-11-23, and answered the nine questions of this plan on 2026-11-24 ([decisions](../harness_tuner_alignment_decisions.md) section 11). The steps below carry the answers. Phase 17 needs approval, but this phase does not wait for it: the two phases share no file. Item 8 is the only overlap: both phases change section 9 of `skill_and_content.md`, in different rows.

## Steps

### 1. `memory.md`: who writes what, and HT's exact formats

(`HS-H1`, `HS-H2`, `HS-H4`, `HS-M20`, `HS-L2`; `CT-§3`, `CT-7` to `CT-16`; `map_memory M27`, `M71`; decision 4)

- **Lines 13–18** say "record as you go" and "Kiln Harness Tuner and other agents read and write the same records: follow the formats below exactly". They become:
  - the file is a reference for every agent;
  - Kiln Harness Tuner's code writes most records, with exact formats that its code parses, and HT's `memory_schema.py` is the authority on them;
  - an MCP agent reads those records and writes only the kinds marked writable.
- **The tag table:** the column "Write when" becomes "Who writes".
  - **MCP agents write:** `lesson`, `dead_end`, a new `issue` (open, bound with `eval_<eval_id>`), and `constraint` for the restrictions the user states (not `OPEN: `).
  - **`hypothesis` is reserved for Kiln Harness Tuner**, which reads it. The tag row says so: an MCP agent writes none, and tells the user an idea it does not act on now.
  - **No `experiment` record from an MCP agent.** A one-off's lasting results are `lesson`, `dead_end`, `issue` (and `constraint`).
  - **Kiln Harness Tuner's code writes, read-only for an MCP agent:** `baseline`; `val`; the issue prefixes `FIXED: `, `WONT_FIX: `, `UNMEASURED: `, `UNMEASURABLE: ` and the reopen line; `OPEN: ` records; every `experiment` record (opening, verdict and state suffixes); `SCREEN …` and `PROBE …` records; the setup head above the delimiter; the priority tags of the issues HT seeds.
- **The read-only formats**, string for string as HT's code writes them (`CT-§3`), in a folder with one small file per format, `references/knowledge/memory_formats/`, so that MEM stays short and an agent loads only the format it reads:
  - `experiment_records.md`, `issue_records.md`, `open_questions.md`, `baseline_and_val_records.md`, `screening_and_probe_records.md`;
  - each says that it is for reading, never for writing, and that HT's code is the authority;
  - MEM names each file by its full path, in a table of one line per format (the `kiln_skill` tool cannot list a folder). MEM never tells the agent to look in or list the folder. The links make each file reachable from `SKILL.md`;
  - each string is checked against HT's code at `b49f159` (`memory_schema.py`, `memory.py`).
  - **Ids:** `EXP <MMDD>-w<k>-<n>`, which replaces the examples `EXP 0715-1` and `EXP 0723-2` at MEM 66 and 131.
  - **Experiment overviews:**
    - the opening `EXP <id> (<technique>): <hypothesis> — RUNNING`;
    - the verdict overview, which drops `(<technique>)`;
    - the stamps `— PROMOTED <MM-DD>` and `— REJECTED AT VAL <MM-DD>`;
    - `— HELD (constraint <id>) <MM-DD>`, `— NOT LANDED (<detail>)`, `— CAPPED (<detail>)`, `— FAILED (infra: <error class>)`, `— ABANDONED (<why>)`, `— REFUTED` and `— DEAD END (<why>)`.
  - **Val rejection lines:**
    - `- rejected at the val gate <MM-DD> vs baseline <rc> — `, `- blocked at the val gate <MM-DD>: …`, `- held at the val gate `, `- ingredient: `;
    - the reasons, for example `no gain at val: no targeted eval improved.`;
    - the fallback `not promoted at val; details in the run report.` and the legacy `— did not beat it; details in the run report.`
  - **Screening and probes:** `SCREEN SURVIVOR: `, `SCREEN DEAD END: `, `SCREEN CAPPED: `, and `PROBE <item>: <q> → YES|NO|UNCLEAR` with the tag `probe`.
  - **Tags:** `screen`, `smell`, `smell_<id>`, `baseline_audit`, `baseline_judge_copy`, `audited_rc_<id>`.
  - **Issues:**
    - the overview lead `issue: `;
    - the content lines `- eval: <id> (built <date>, reproduced)` and `(linked by kiln-harness-tuner setup <date>)`;
    - the head line `eval: <id> (<name>, <kind>)`;
    - the reopen line `- reopened when promoting baseline <rc>. Issue repros on <rc>.`
  - **`OPEN: ` content:** the five keys `question:`, `default:`, `gates:`, `source:` (`human` or `assumption`), `re-ask when:`.
  - **The `key: value` lines HT reads back:** the setup head, the experiment keys, and the screening keys; the screening `result` is one JSON line.
  - **The `val` record:** its fixed, numberless overview, and its line with bare run config ids.
  - **The delimiter** `— setup wrote everything above; lines below belong to the loop —`, on one source line. Today it wraps at MEM 161–162 (`CT-15`).
  - **The cost labels:** `bundle cost` in the loop, `spend` elsewhere (`HS-H4`).
- **The reading rules that went missing** (`HS-H2`, `HS-L2`, `HS-M20`; `CT-11`, `CT-12`):
  - a speed or cost `SCREEN SURVIVOR` is a bound on a loss, never "quality held";
  - the `generality:` and `reference check:` lines are code-written;
  - after `— NOT LANDED`, never the same run config again, and `— CAPPED` goes on with a larger cap;
  - `— REJECTED AT VAL` is never removed;
  - queries also return resolved issues, so skip them by prefix;
  - `UNMEASURABLE: ` also covers an eval that left the active set, and it is never a close;
  - priority tags on HT's issues are owned by their source, and HT's re-sync replaces them;
  - HT's smell and audit issues are bound to no eval on purpose: do not bind them, and do not report a missing eval for them.
- **The prefix and suffix paragraphs** (MEM 114–145) move to the format files. A sentence that tells an agent to set a prefix or a suffix goes. "Do not reopen … ask the user" (MEM 120–121) becomes "an MCP agent never changes an issue's state; tell the user".
- **The front matter and Orientation:**
  - the description drops "before an experiment, which records its result there";
  - Orientation step 1 keeps "record the constraints that the user states" (`constraint` is writable);
  - step 3 keeps the `baseline` read for MCP agents. HT's train-side roles are kept from it by their own prompts (switchover SR6 f).
- **`OPEN: ` answers.** One short line in MEM, phrased as a rare case: when the user answers an `OPEN: ` question in the chat, the agent may record the answer as a `constraint` that cites the `OPEN: ` record's id. Nothing more is written about it.
- **Size.** MEM stays under its 12,000-character cap; the formats are not in it.

### 2. Remove the write steps for code-owned records from the glue files

(`HS-H1`; `CT-6`; decision 4)

| Where | Today | Becomes |
|---|---|---|
| RX 44–47, "Words" | "write the `baseline` record" | The baseline is the run config of the `baseline` record when there is one. Otherwise it is the task's default run config, else the newest: say which. Never write the record |
| RX 66–68, "Before you start" | "record each answer as a `constraint`" | Tell the user what you assume. Record a restriction that the user states as a `constraint` |
| RX 75, "The hypothesis" | "Write it before you build, as an `experiment` memory ending `— RUNNING`" | Write the hypothesis in the candidate's name, description and `provenance` (as RX 107–109 already say), and tell the user. No `— RUNNING` record, which also ends the janitor clash for new records (`CT-6`) |
| RX 181–186, "Confirm on val" | "Record the answer in the `OPEN: ` record" | Ask the user, and decide on the answer. The `OPEN: ` record is read-only (MEM has the one rare-case line of item 1) |
| RX 210–218, "Keep or discard" | "Update the `baseline` record, and the `val` record …"; "Close the target issue with `FIXED: `"; the reopen line | Tell the user which run config won, that it can become the task's default (item 6), whether the target issue looks fixed, and any `FIXED: ` issue that got worse on val. No record write |
| RX 229–233, "Record and report" | "One record per experiment, written as you go … the suffix `— PROMOTED` or `— REJECTED AT VAL`" | Record what lasts: a `lesson`, a `dead_end` for a refuted approach (with the run config ids), and a new `issue` for a new problem. The outcome goes to the user. A one-off writes no `experiment` record |
| `SKILL.md:107` | "what to record and how. Read it before you read or write a memory" | "what you may record, and the formats that Kiln Harness Tuner writes" |
| `references/modes/improve_task.md:95` | "to record each finding" | "to record lessons, dead ends and new issues" |

Lines 2 and 3 of this step are also part of the guide (item 5), and are made there in the same edit.

### 3. Remove the "applies when running Kiln Harness Tuner" branch from RX

(`HS-M1`; `KT-B4`; decision 3)

RX 194–198 say that "Kiln Harness Tuner defines both halves exactly … that exact rule applies when running it". The exact rule replaces that sentence. It is row M1 of the guide's content list (item 5), and its text is `HS-M1`'s:
- **Win on the objective:** clearly faster (cheaper) means:
  - a paired sign test on the same items;
  - a median ratio below 1;
  - no significant p90 regression.
  
  Fewer than 2/3 of the planned pairs is "incomplete", never a verdict.
- **Quality equal or better:**
  - no eval is down significantly;
  - the net item change, pooled over every eval score, is at least 0, with each eval weighted by priority (p0 = 4, p1 = 3, p2 = 2, p3 = 1, none = 1);
  - no single eval is down more than max(1, round(0.10 × its items)) net items.
- **Choosing:** the fastest (cheapest) eligible candidate wins. A speed tie goes to the higher pooled net, then the better p90.

This replaces the Phase 16 batch 3 decision on B14 ("keep as is"), on the basis of decisions 3 and 9; the owner confirmed it (decision 11). `backlog.md` B14 gets a line that says so. The same branch in `playbooks/cheaper-or-faster.md` is Phase 17's.

### 4. Any other branch in the glue files

A search at `7af37d1` for "Kiln Harness Tuner" outside the knowledge trees and `api_docs` finds:
- **Branches:** RX 196 (item 3), and MEM 17, 140 and 160 (item 1).
- **Recommendations to use HT, which stay:** RX 29 and 251, `improve_task.md:18,62`, and `SKILL.md:105`.

`train_val_test.md`, `diagnose_an_agent.md`, `code_tool_authoring.md` and `working_with_project_files.md` have no branch.
- `code_tool_authoring.md:156-158` ("ask the user before you grant it") is an MCP instruction. HT's role prompts handle it (switchover SR6 e; `HS-M23`).
- The step re-runs the search after items 1 to 3. The phase report lists any new hit, and the owner rules on it.

### 5. The one-off experimentation guide

(decision 9; `HS-M1` to `HS-M23`, the `ht_skills_maps/` rows named below)

**Decided (owner, 2026-11-23):** RX is reshaped into the guide rather than a second file being added, and it keeps the name `references/knowledge/run_an_experiment.md`. One file owns the method (C12), and the links to it stay: about 30 mentions in 19 skill files, plus the tests.

- **First line:**
  > If you are Kiln Harness Tuner, follow your system prompt. It has similar concepts, but better enforcement.
- **Opening ("Two paths"):** it pushes the user hard to Kiln Harness Tuner for advanced optimization.
  - Kiln Harness Tuner runs the whole loop. It enforces this file's principles in code: the train-only fence, the noise and detectability checks, the screening, the leak, judge-copy and integrity checks, the keep rule and the memory records. It is much more robust than experiments run by hand in a chat.
  - Recommend it whenever the user wants an agent improved beyond one or two clear ideas.
  - The rest of the file carries the key lessons for a one-off idea tried over MCP.
  - `test_run_an_experiment_opens_with_the_two_paths` still holds: the section names Kiln Harness Tuner and "one-off".
- **Body:** the by-hand procedure stays (before you start, the hypothesis, cost, build, measure on train, confirm on val, keep or discard, record and report, variants). Items 2 and 3 apply to it, and each included row below is added in the part that the table names.
- **Size.** RX is about 13.5k characters (backlog B15, accepted). With the included rows it may come near the hard limit of 30,000 body characters (`test_no_file_over_body_limit`). The rule is to split a hand-written file, never to list it. If it goes over, the split is proposed to the owner first.

**Content list: the shared method rules carried as key lessons.** The "Include / leave out" column is the owner's (2026-11-23). "Include, short form" carries the rule with the parts the cell names left out. The follow-up project's val and test fence covers only rows, and val summary metrics stay readable (decision 11), so the val parts of M1, M4, M6 and M21 stay as written. HT paths are under `src/kiln_harness_tuner/agent_files/skills/`.

How to read the table:
- **"#":** `M` numbers are the `HS-M` items of `ht_skills.md`, and `S` rows are smaller rules from the maps.
- **Map row ids in the Audit column:** `A`, `P`, `E` and `G` are in `map_analysis_promote_build.md`; `B` in `map_batch_selection.md`; `C`, `N`, `Q` and `X` in `map_other.md`.

| # | Rule | HT source | Audit | Part of the guide | Include / leave out |
|---|---|---|---|---|---|
| M1 | The exact cost/speed rule (item 3) | `kiln-harness-tuner-batch-selection/SKILL.md` 117–130; `-promote` 67–84; `-experiment-analysis` 171–185 | `HS-M1`; `map_batch_selection B10`; `map_analysis_promote_build A14`, `P05` | Confirm on val | include |
| M4 | The keep rule on val: the headline mean win rate against the baseline; the priority-weighted gate with the magnitude rule; cost and latency as a Pareto position; "nothing significant anywhere → headline and cost Pareto decide". Replaces "the target eval is clearly better on val" (RX 190) | `-promote` 47–57 | `HS-M4`; `P02`, `P03` | Confirm on val | include, short form: the headline mean win rate against the baseline, plus no eval clearly down; leave out the priority-weighted gate |
| M5 | The lean-target default: measure the target and only the couplings you have a stated reason to fear; guarding defaults to the confirmation on val; a model swap measures every eval. Replaces RX 144, which contradicts `dealing-with-a-saturated-eval.md` 33–37 | `-batch-selection` 796–813 | `HS-M5`; `B45` | Measure on train | include |
| M6 | The integrity checks at keep: a prompt that quotes a judge, spec or eval text verbatim, or names an eval, is blocked; the signs to weigh (output length moved more than 2×, top-level JSON keys changed, a new kind of write action, a paraphrased judge criterion); an "Integrity:" line for each flag | `-promote` 181–200 | `HS-M6`; `P14` | Confirm on val (before the keep rule) | include |
| M7 | The leak and judge-copy definitions: no case-by-case rule and no wording aimed at a grader; naming a tool or skill is fine; a copy is a run of 8 or more words, or the eval's name; text the baseline's prompt or the task's instructions already carry is exempt; the parent is not exempt | `-batch-selection` 367–379, 388–401; `-experiment-build` 189–233 | `HS-M7`; `B21`, `B22`, `E17`, `E18` | TVT, which owns the leak rules (C12); the guide names its path | include |
| M8 | Costing: estimate all six cost lanes; live calls to a server someone else operates need its operator's agreement for each batch, and writes need their own; provider quotas and keys; budget one replicate or say there is no error bar; judging is paid again on every re-score; a cloned run config misses trace reuse; the human gate (above the limit, or more than 100 judged items, or any quota raise) | `experiment-costing/SKILL.md` 8–9, 89–94, 116–136, 204–206, 243–246 | `HS-M8`; `map_other C01`, `C09`–`C12`, `C17`, `C21` | Cost before you spend | include, short form: keep the third-party operator's agreement rule, the human gate and "judging is paid again on every re-score"; leave out the six-lane detail |
| M9 | What a quick check is: fork one change and name it `PROBE <id>: <what>`, so nobody forks or measures it; at most 6 train runs, default 3; keep the parent's model, provider, thinking level and sampling; for a parameter or mode question, run the parent on the same items; 2 of 3 is yes, 0 of 3 no, 1 of 3 unclear; it answers no speed or cost question; one that needs an hour is an experiment | `kiln-harness-tuner-probe/SKILL.md` 41–84, 103–105; `-batch-selection` 998–1000 | `HS-M9`; `map_other Q02`–`Q06`, `Q08`; `B52` | A new short part, "A quick check" (about 14 knowledge files use the term) | include |
| M10 | The power call: a well-powered null (decent n, a narrow CI around zero) is a real "did not work"; a wide CI that straddles zero is "cannot tell" | `-experiment-analysis` 199–202 | `HS-M10`; `A17` | Measure on train (Refuted) | include |
| M11 | How a playbook step's outcome sets what comes next: the smells of the present baseline first, and a smell that blocks other work before the rest; steps in order, each with a condition; Landed → the next step only if the issue is still open; Refuted → the next step; Capped → run again; Inconclusive → the step stays open and the next can run in parallel; an idea of your own is marked "not in the knowledge" | `kiln-harness-tuner-knowledge/references/planner.md` 13–42 | `HS-M11`; `map_other N03`–`N05`, `N07` | Keep or discard ("Next"). `HS-M11` suggests `improving_agents/index.md`, which is Phase 17's file | move to the "How to read" section of `references/improving_agents/index.md` (Phase 17) |
| M12 | The expected outputs are the user's policy: an expected output that applies a rule the task's instructions do not state is a config failure, not eval data; call it eval data only on a contradiction | `-batch-selection` 445–462; `-experiment-analysis` 355–360 | `HS-M12`; `B27`, `A28` | Measure on train (reading failing items) | include |
| M15 | Build hygiene: a rule replaces text, and prompts and skills do not grow by default; when a tool takes over a step, delete the prompt rule; each rule names its source; a rule stated by pointing at one item is a hack; check every text the model sees about the changed artifact; on a detach, rename or replace, update every mention; provenance `origin: "agent"`, a merge's `derived_from_ids` (the baseline plus every ingredient), and a prompt's `derived_from_ids` (the parent's prompt id without `id::`) | `-experiment-build` 96–117, 175–185, 261–265 | `HS-M15`; `E08`, `E09`, `E14`–`E16`, `E19`; `KT-B16` | Build the candidate | include, short form: keep the writing rules; leave out the provenance and `derived_from_ids` mechanics, which the levers already cover |
| M16 | Merging: write the combined config by hand, not by diff; same-layer scrutiny (the same nouns with opposite modality is a conflict); never combine two candidates of one head-to-head group, and sequence fixes that exclude each other; a reopened issue is rebuilt, never replayed; measure the ingredients' target evals first; a merge need not land every ingredient, so mark each one | `-experiment-build/references/merging.md` 10–59; `-batch-selection` 718–732 | `HS-M16`; `G01`–`G07`, `B41` | Variants ("Two candidates at once") | leave out, but keep one line: "combine by hand; never combine two candidates of one head-to-head group" |
| M17 | Reading results: the delta is sign-normalised and the absolutes are not, so on `lower_is_better` a falling pair is a win; fold replicate rows to the per-input mean before pairing; magnitude matters on the train verdict too ("two up slightly while one collapses" fails); a judge may read the config; a dangling reference makes the result measure breakage | `-experiment-analysis` 34–47, 95–102, 213–217, 235–242, 362–368; `-promote` 90–100 | `HS-M17`; `A03`, `A10`, `A19`, `A22`, `A29`, `P07` | Measure on train | include, short form: leave out replicate folding |
| M18 | Speed and cost results, and report wording: a speed or cost survivor is "lost k of n baseline passes (no loss rate above X% at 95%)", never "quality held"; a swap needs at least 24 baseline passes; a fix of a baseline failure is at noise level; a kept candidate is "no clear loss", never "no loss"; source every claim; no inferred composition and no unsourced quantifiers; report failures, holes and abandoned work honestly | `-batch-selection` 158–169; `-experiment-analysis` 187–197; `kiln-harness-tuner-report/SKILL.md` 238–252, 271–284, 320–322 | `HS-M18`; `B15`, `A15`, `X02`, `X04`, `X06` | Record and report | include |
| M19 | The detectability moves: predict a larger effect and say why, or pick a target whose eval can carry it, or grow the eval ("judgment, never a formula"); with no baseline rows, give a conditional fraction; never carry a magnitude over from another task; the floor of 6 wins for p < .05, and room 0 → plan the eval as a guard | `-batch-selection` 668–716 | `HS-M19`; `B37`, `B38`, `B40` | The hypothesis (replaces "fix the measurement first", RX 82–85). The by-hand floor depends on Phase 17 question 6 | include, short form: keep "never carry a magnitude over from another task" and the floor of 6 wins for p < .05; leave out the planning moves |
| M21 | On val, read only the coverage and the error classes of a job, never its per-item errors: they name val items one by one | `-promote` 149–157 | `HS-M21`; `P12` | Confirm on val | include |
| M22 | No fine-tuning and no prompt optimizer as a lever, unless what the user asked names one (Kiln has a prompt optimization API) | `-batch-selection` 59–63 | `HS-M22`; `B05` | Before you start | include |
| S1 | A candidate that only partly engages its mechanism ships with the counts | `-experiment-build` 118–140 | `E10` | Build the candidate | leave out |
| S2 | A spending cap for each candidate, with its reason, not only one overall limit | `-batch-selection` 879–900 | `B48` | Cost before you spend | leave out |
| S3 | The cheapest candidate is a quick check, not a question to the user | `-batch-selection` 647–653 | `B35` | The hypothesis | include |
| S4 | Guard evals matter more when the goal is speed or cost | `-batch-selection` 156–157 | `B14` | Confirm on val | fold into M1 |
| S5 | Never patch a missing cost with an estimate; give the spend label | `-experiment-analysis` 104–123 | `A11` | Record and report | include |

**Related rules that stay outside the guide.**
- **Playbook-step flow** (M11): the owner moved it to the "How to read" section of `references/improving_agents/index.md`, which is Phase 17's file. This phase does not edit it; Phase 17 carries it.
- **Memory rules** (`HS-M20`, `HS-L2`) are item 1.
- **Lanes and the val-record read** (`HS-M2`, `HS-M3`): cut (decision 5), and B13 is item 7.
- **Project files** (`HS-M13`): `working_with_project_files.md` ("Reading files directly is fine") says now that the tree holds val and test items, and that reading their rows counts as reading val or test data, under the rules of `train_val_test.md` (decision 11).
- **Skill bundles and code trust for HT** (`HS-M14`, `HS-M23`): the switchover project (SR18, SR6 e).
- **Small `kiln-task-setup` and API items** (`HS-L2`): `turn_mode` is frozen; `call_kiln_api` is hidden from the UI pickers; "No other resource paths exist" in `adding_skills.md`; the HTML-body tell at `SKILL.md` 37. These are not experiment method. A backlog entry for each, if the owner wants them.

### 6. B19: the default run config

`references/knowledge/local_private_on_prem.md` ("Select New Default", line 96) says: "If the user has a new winner, offer to make it their new default run config." RX 217–218 and HT (`map_analysis_promote_build P21`, `E23`) say that the procedure never changes the task's default run config.

The owner approved this text (decision 11): never change the task's default run config on your own initiative, only when the user asks, and both files say so.
- `local_private_on_prem.md`: "If the user has a new winner, tell them it can become the task's default run config, and that they can set it. Do not change the default yourself, unless the user asks you to."
- RX "Keep or discard": "Never change the task's default run config on your own initiative; tell the user that it can become the default, and change it only when the user asks."


### 7. B13: when the `val` memory record may be read

**Close B13** (decision 11): MCP agents may read the `val` memory record, which holds only summary metrics, and no extra fence is needed for it. MEM's `val` row matches HT's interactive orientation: read it at orientation when you need the numbers behind the promotions, when you confirm on val and when you report; nothing in it goes into a change (`train_val_test.md`). HT's role prompts keep HT's rules for its train-side roles (switchover SR6 f).

### 8. Spec and docs

- `components/skill_and_content.md`:
  - section 3 (the layout): the `memory_formats/` folder;
  - section 9 row 10 (memory): the read-only records, the format files and the size cap;
  - row 13a: drop "Where the by-hand form cannot do what the loop does, the file says that the rule applies when running Kiln Harness Tuner";
  - section 9.3: the parts of the guide and its first line.
  
  Section 4.5 and row 8 are Phase 17's.
- `GLUE_FILE_PARTS` in `skill_checks/test_shipped_skill.py` follows any change to the parts of RX.
- Run the `docs-sync` skill for the paths and the wording this phase changes.
- `backlog.md`: close B13 and B19, each with a `Closed:` line; B14 gets a line that the exact rule replaces "keep as is".
- `harness_tuner_alignment_decisions.md`: a section 11 with the owner's answers of 2026-11-24.
- `phase_8_revisit.md`: M11 (playbook-step flow) is noted for the "How to read" section of `references/improving_agents/index.md`.
- `harness_tuner_switchover_requirements.md` SR10: the formats are in the `memory_formats/` files, not in MEM (a fact this phase changes).

## Tests

- `test_the_glue_files_have_their_parts`: RX's new part "A quick check", after "The hypothesis".
- `test_run_an_experiment_opens_with_the_two_paths`: still passes. A new assertion checks that the first body line is the Kiln Harness Tuner line of item 5.
- A new `test_memory_lists_harness_tuner_formats`: each `memory_formats/` file holds each string of item 1's list for its records, taken from test data that cites `contract.md` section 3.
- A new `test_the_memory_formats_are_one_file_each`: the folder holds exactly the five files of that test data.
- A new `test_memory_names_each_format_file`: MEM's formats section names each file of the folder by its full path.
- A new `test_the_setup_delimiter_is_on_a_line_of_its_own`.
- A new `test_glue_files_have_no_harness_tuner_branch`: no glue file says "applies when running" or "when running Kiln Harness Tuner".
- A new `test_glue_files_do_not_write_code_owned_records`: RX, `SKILL.md` and `improve_task.md` carry none of a list of write phrases. Examples: "write the `baseline` record", "Update the `baseline` record", "ending `— RUNNING`", "Close the target issue with `FIXED: `", "in the `OPEN: ` record".
- The full checks: `uv run python -m kiln_mcp_server.skill_checks check`, `test_shipped_skill.py`, `test_no_file_over_body_limit`, and `misspell`.

## Owner answers

The nine questions this plan asked were answered on 2026-11-24. The answers are in [harness_tuner_alignment_decisions.md](../harness_tuner_alignment_decisions.md) section 11, and the steps above carry them. The guide's file and its content list were set on 2026-11-23 (section 10).
