---
status: complete
---

# Harness Tuner alignment audit: HT skills vs the Kiln skill's glue files (HT b49f159 vs Kiln 25157f3)

This is the audit of HT's non-knowledge skills against the Kiln skill's glue files at commit 25157f3. The rule-by-rule maps (one line per rule, with class and lines) are in `ht_skills_maps/`:
- `ht_skills_maps/map_memory.md`
- `ht_skills_maps/map_batch_selection.md`
- `ht_skills_maps/map_analysis_promote_build.md`
- `ht_skills_maps/map_other.md`

**Path conventions.** Kiln paths are relative to `app/mcp/kiln_mcp_server/skill/`. RX = `references/knowledge/run_an_experiment.md`, MEM = `references/knowledge/memory.md`, TVT = `references/knowledge/train_val_test.md`. HT paths are relative to `src/kiln_harness_tuner/agent_files/skills/` at b49f159.

**Bottom line: HT cannot be re-pointed safely as committed.** Three things block it:
1. The skill tells MCP agents to write HT's code-owned memory records, and the formats it gives differ from HT's code.
2. The HT-only rules of the memory skill and of the role skills exist nowhere in the Kiln skill. HT keeps only its role entry files, and those say "load skill X and follow it exactly".
3. The exact speed/cost rule is still a branch, and the train-lane concept (model 2) is absent.

## 1. Per HT skill: where it went, and the counts

The counts are of the rules I enumerated in the map files. They are a judgment call, not a mechanical count.

| HT skill (lines) | Where it went | PRESENT | LOST | LOOSENED | TIGHTENED | CHANGED | BRANCH | CONFLICT | N/A |
|---|---|---|---|---|---|---|---|---|---|
| `memory` (96) | MEM. RX writes the records | 47 | 12 | 2 | 2 | 7 | 0 | 6 | 2 |
| `kiln-harness-tuner-batch-selection` (1167) | Spec: role skill, not ported. Method bits in RX "The hypothesis", "Variants", the keep rule, and the knowledge playbooks | 23 | 12 | 1 | 0 | 6 | 3 | 2 | 10 |
| `kiln-harness-tuner-experiment-analysis` (397) | Not ported (role). RX "Measure on train, and judge" | 17 | 10 | 1 | 0 | 1 | 1 | 1 | 2 |
| `kiln-harness-tuner-promote` (268) | Not ported (role). RX "Confirm on val", "Keep or discard" | 10 | 5 | 0 | 1 | 1 | 1 | 1 | 2 |
| `kiln-harness-tuner-experiment-build` (326) | Not ported (role). RX "Build the candidate", the levers | 12 | 6 | 1 | 0 | 4 | 1 | 0 | 1 |
| `…/experiment-build/references/merging.md` (92) | RX "Variants" (two lines) | 1 | 7 | 0 | 0 | 0 | 0 | 0 | 0 |
| `…/experiment-build/references/skill-authoring.md` (193) | Spec: not ported (separate decision). `levers/skill.md`, skill techniques | 4 | 1 | 0 | 0 | 0 | 2 | 0 | 0 |
| `experiment-costing` (264) | Spec: not ported (separate decision). RX "Cost before you spend" (87-96) | 6 | 12 | 3 | 0 | 0 | 0 | 0 | 1 |
| Planner entry file (`kiln-harness-tuner-knowledge/references/planner.md`) | Spec: role entry files not ported. `references/improving_agents/index.md` "How to read" | 5 | 2 | 1 | 0 | 0 | 0 | 0 | 1 |
| `kiln-harness-tuner-code-tool-authoring` (260) | `references/knowledge/code_tool_authoring.md` (batch 11) | 12 | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
| `…/references/wrappers/` (README and 8 `.py`) | `references/knowledge/code_tool_wrappers/*.md` | 2 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| `kiln-task-setup` (60) | Spec: not ported (separate decision). Covered in part by `model_create_configs.md`, `create_task.md`, `improve_task.md` | 5 | 2 | 0 | 0 | 1 | 1 | 0 | 0 |
| `kiln-api` (117 plus docs) | `SKILL.md` "Calling the Kiln API" and Kiln's own `api_docs` pipeline | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| `kiln-harness-tuner-probe` (113) | "a quick check", named in about 14 knowledge files and defined in none | 2 | 6 | 0 | 0 | 0 | 0 | 0 | 0 |
| `kiln-harness-tuner-baseline-review` (126) | `diagnose_an_agent.md` "What the smells measure", the smell documents | 3 | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| `kiln-harness-tuner-report` (329) | RX "Record and report", `improve_task.md` "Reporting" | 2 | 4 | 0 | 0 | 0 | 0 | 0 | 1 |
| `kiln-harness-tuner-gateway` (353) | Not ported: its operations became `api_docs` paths. The train-only fence is HT code, so N/A, but it is what owner model 2 replaces with a soft rule | – | – | – | – | – | – | – | all |
| `kiln-harness-tuner-knowledge` | Another auditor's scope. Only its `planner.md` was audited here. Its other role entry files (`builder.md`, `analyzer.md`, `smells.md`, `report.md`) are not ported either | | | | | | | | |

Other details:
- **Wrapper templates:** the module code of all 8 is byte-identical to HT's. I diffed each python fence against its `.py` file. Only the docstrings of `actionable_errors`, `context_on_tool_surface` and `readonly_guard` were reworded, and the commit documents that.
- **Code-tool authoring:** this is the cleanest port.

## 2. Ranked findings

Severity: **H** = would break HT, **M** = changes a rule, **L** = wording.

**H1 — CONFLICT (model 3): the skill tells MCP agents to write memory**
- Kiln:
  - MEM 3 ("Read it before you read or write a memory")
  - MEM 13-18 ("record as you go"; "Kiln Harness Tuner and other agents read and write the same records")
  - MEM 49-50 ("record the constraints that the user states")
  - MEM 98-107 (the "Write when" column, including `baseline` "At the first experiment… move the `rc_` tag" and `val` "Right after the `baseline` update")
  - MEM 114-139 (issue prefixes, `OPEN:` and experiment suffixes written by hand)
  - RX 45-47 ("write the `baseline` record")
  - RX 67-68 ("record each answer as a `constraint`")
  - RX 75 ("Write it… as an `experiment` memory ending `— RUNNING`")
  - RX 185-186 ("Record the answer in the `OPEN: ` record")
  - RX 210-217 ("Update the `baseline` record, and the `val` record…", "Close the target issue with `FIXED: `")
  - RX 229-233 ("One record per experiment, written as you go"; "A refuted approach is a `dead_end`")
  - `references/modes/improve_task.md` 95 ("to record each finding")
  - `SKILL.md` 102 ("what to record and how. Read it before you read or write a memory")
- HT sources:
  - `memory/SKILL.md` 82: the format-critical writes ("the `baseline` and `val` records, `FIXED:`/`WONT_FIX:`/reopen prefixes, `OPEN:` records, experiment open/verdict/state suffixes") "are performed by the orchestrator **code**… loop agents make discovery writes only".
  - `memory/SKILL.md` 66: the baseline record is created by "the Kiln Harness Tuner setup phase's pre-flight step".
  - `memory/SKILL.md` 67: the val record is "Written by the promotion apply step".
  - `gateway/ops.py` 860-861 and 873-874: "the `val` tag is written by the loop's code only".
- Why it breaks HT:
  - An MCP agent on the raw API is not fenced.
  - A hand-made `baseline` record seeded before HT's setup becomes HT's trusted pointer.
  - A hand `FIXED:` is terminal: HT "never un-closes" it, so the issue is hidden from every later wave.
  - A hand-written val line lands in HT's only val-metric record.
- Fix:
  - Make MEM a reader's guide: "Over MCP memory is read-only. Kiln Harness Tuner writes these records with code, and their structure must stay exact. Report findings to the user."
  - Remove every write step from RX "Words", "Before you start", "The hypothesis", "Confirm on val", "Keep or discard" and "Record and report". Replace them with "tell the user" lines.
  - Drop the "Write when" column, or label it "what Kiln Harness Tuner writes".

**H2 — LOST: HT-only memory rules that HT roles depend on are gone from the shared doc**
- Kiln: MEM, whole file. Line 17 offers only raw endpoints.
- HT sources:
  - `memory/SKILL.md` 17: in an HT session "use the gateway's memory operations… the endpoint table is for other sessions".
  - `memory/SKILL.md` 36 and 66: train-side loop agents "**never read**" the `baseline` record.
  - `memory/SKILL.md` 52: `memory_schema.py` "is the authoritative list of what CODE reads".
  - `memory/SKILL.md` 54-56: `val` is an "access class".
  - `memory/SKILL.md` 69, 71, 73: screening records and how to read them; code-written `generality:` and `reference check:` lines.
  - `memory/SKILL.md` 82: "who writes lifecycle state".
- Why it breaks HT: if HT's `memory` skill is replaced by MEM, HT roles reading MEM "Orientation" step 3 (MEM 52) would read `tags=baseline`, which the HT role prompts forbid. They would also see no "discovery writes only" rule. The gateway enforces only the val tag (`gateway/ops.py` 811-812, 860), not the baseline rule.
- Fix:
  - Add an "In a Kiln Harness Tuner role" section: use the gateway's memory operations; train lanes never read `baseline` or `val`; discovery writes only (`lesson`, `dead_end`, new `issue`).
  - Say that `memory_schema.py` is authoritative for structure.
  - Restore the reading rules for `SCREEN …`, `generality:` and `reference check:` lines, and the `— DEAD END (…)` suffix.

**H3 — LOST (spec: "not ported"): the role skills that HT's entry files load do not exist in the Kiln skill**
- HT sources:
  - `src/kiln_harness_tuner/agents/batch_plan.md` 3-4: "Load the `kiln-harness-tuner-batch-selection` skill and follow it exactly".
  - `agents/promote_best.md` 3: the same for `kiln-harness-tuner-promote`.
  - The same pattern holds for the analyzer, builder, probe, baseline-review and report entry files.
- What is lost:
  - The frozen overview format in `kiln-harness-tuner-experiment-analysis/SKILL.md` 262-307. HT's tests string-assert it, and code reads the label and technique (`memory_schema.py` 826-841).
  - The BatchPlan, PromotionDecision and RcBuildResult return conventions.
  - `merging.md`, `skill-authoring.md`, `install_skill_bundle`, `experiment-costing`, and the gateway catalogue.
- Fix: either keep these skills in HT until each is ported, or fold each into a "Kiln Harness Tuner role" file of the shared skill. Re-pointing must not delete them.

**H4 — CHANGED: memory formats differ from HT's code**
- Kiln:
  - MEM 66-67 and 131: `EXP 0715-1`, `EXP 0723-2`. HT's code mints `EXP <MMDD>-w<k>-<n>` (`memory_schema.py` 37, 946-948). The HT planner derives wave numbers from the newest `EXP <MMDD>-w<k>-…` record (`batch-selection/SKILL.md` 790-805).
  - MEM 118-120: the reopen line. HT's code writes "- reopened when promoting baseline {rc}. Issue repros on {rc}." (`memory_schema.py` 640).
  - MEM 123-128: `OPEN:` content is prose. HT's code uses five `key: value` lines, `question/default/gates/source/re-ask when` (`memory_schema.py` 1368-1407). A record with no `question:` line never dedups.
  - MEM 151-152: the eval line is "- eval: <eval_id>". HT uses "- eval: <id> (built <date>, reproduced)", and the planner and promote agent use that line as a join fallback (`batch-selection` 553-556, `promote` 228-231, `merging.md` 63-65).
  - MEM 107: the val record's numberless constant overview is lost (`memory_schema.py` 1424).
  - MEM 143: `— HELD` has lost its exact shape `— HELD (constraint <id>) <MM-DD>` (`memory_schema.py` 822).
  - MEM 102: the `spend` label (and `bundle cost` in the loop) is lost (`memory/SKILL.md` 62; analysis 104-123).
- Fix: if any write survives, copy the exact shapes from HT. Otherwise state that these are HT's shapes, for reading.

**M1 — BRANCH (model 5): the exact speed/cost rule is not ported**
- Kiln: RX 194-198: "Kiln Harness Tuner defines both halves exactly… that exact rule applies when running it". The same branch exists in `references/improving_agents/playbooks/cheaper-or-faster.md` 20-22.
- HT sources: `batch-selection/SKILL.md` 117-130, `promote/SKILL.md` 67-84, `experiment-analysis/SKILL.md` 171-185.
- Suggested text to port:
  - **Win on the objective:** clearly faster (cheaper) means a paired sign test on the same items, a median ratio below 1, and no significant p90 regression. Fewer than 2/3 of the planned pairs is "incomplete", never a verdict.
  - **Quality equal or better:**
    - no eval is down significantly;
    - the net item change, pooled over every eval score, is at least 0, with each eval weighted by priority (p0 = 4, p1 = 3, p2 = 2, p3 = 1, none = 1);
    - no single eval is down more than max(1, round(0.10 × its items)) net items.
  - **Choosing:** the fastest (cheapest) eligible candidate wins. A speed tie goes to the higher pooled net, then the better p90.

**M2 — LOST (model 2): there is no train-lane concept**
- Kiln: TVT, whole file; MEM 54-55 and 107. There is no narrow/broad state and no rule that "val rows in context ⇒ broad for the rest of the session; may confirm and report; refuses optimizer work".
- HT sources: `memory/SKILL.md` 54-56 and 67 (access class; "the train lane never fetches `tags=val`"); `gateway/SKILL.md` 15-22.
- Fix: add a "Lanes" section to TVT, as in the owner's model.

**M3 — CONFLICT (choice "a") and TIGHTENED: the val record may not be read while designing**
- Kiln: MEM 107: "When you confirm on val and when you report. Never while you design or build a change". MEM 54-55 points to it.
- HT source: `memory/SKILL.md` 67 lets the record be read in "human/interactive orientation"; 36 says to read it "when you need the numbers behind those promotions".
- Note: commit fa49d74 records this deviation and backlog B13 holds it.
- Fix: allow val summary metrics and the val record while narrow. Keep "val rows ⇒ broad".

**M4 — TIGHTENED: the keep rule on val requires a clear target gain**
- Kiln: RX 190: "The target eval is clearly better on val".
- HT source: `promote/SKILL.md` 47-57. The headline is mean win rate vs the baseline. Only significant deltas register as changes. "Nothing significant anywhere → headline + cost Pareto decide".
- Note: the spec's row 8 wording led to this.
- Fix: restore the three-number comparison (headline mean win rate; the priority-weighted gate with the magnitude rule; cost and latency as a Pareto position) and the "nothing significant" fallback.

**M5 — CONFLICT: guard evals are measured on train by default**
- Kiln: RX 144: "When the target eval moved, measure the guard evals on train too". This contradicts `references/improving_agents/playbooks/dealing-with-a-saturated-eval.md` 33-37: "Do not add it to a candidate's train measurement as a routine guard".
- HT source: `batch-selection/SKILL.md` 796-813, the lean-target default. Measure the target plus only the couplings with a stated reason to fear; must-not-regress guarding defaults to the val gate; a model swap measures every eval.
- Fix: replace line 144 with the lean-target rule.

**M6 — LOST: the integrity checks at keep**
- Kiln: RX 165-206.
- HT source: `promote/SKILL.md` 181-200.
  - A prompt that quotes a judge, spec or eval description verbatim, or names an eval, is BLOCKED.
  - Signs to weigh: output length moved more than 2×, top-level JSON keys changed, a new kind of write action, an instruction that paraphrases a judge criterion.
  - A kept candidate needs an "Integrity:" line for each flag.
- Fix: add these checks before "Then apply the keep rule". The length, key and write checks can be done on train outputs.

**M7 — LOOSENED and CHANGED: the leak rules and the judge-copy definition**
- Kiln: TVT 97-104.
- HT sources: `batch-selection/SKILL.md` 367-379 and 388-401; `experiment-build/SKILL.md` 189-233.
  - The generality check also refuses "a case-by-case rule, wording aimed at a grader". Naming a tool or a skill is fine.
  - A copy is "a run of eight or more words… or the eval's name". Text that the baseline's prompt or the task's instructions already carry is exempt. "The parent is not exempt."
- Port text: "no passage… and no name of an eval". There is no exemption and no parent rule.
- Fix: restate both rules exactly.

**M8 — LOOSENED and LOST: costing**
- Kiln: RX 87-96.
- HT source: `experiment-costing/SKILL.md`.
  - 8-9: estimate "ALL six lanes".
  - 116-122: "Live calls to a server someone else operates **always need its operator's agreement per batch**".
  - 123-128: provider quotas and keys.
  - 129-136: "budgets one replicate… or says up front that its result carries no error bar".
  - 89-94: judging is paid again on every re-score.
  - 243-246: human gate: above the threshold, OR more than 100 judged items, OR any quota raise.
  - 204-206: a cloned run config misses trace reuse.
- Fix: port the six lanes and the human gate into RX "Cost before you spend". The third-party rule is a safety rule.

**M9 — LOST: "a quick check" is undefined**
- Kiln: used in `references/improving_agents/playbooks/know-the-agent-before-you-plan.md` 20, 34, 73, `skill-is-not-read.md`, `lost-in-long-instructions.md`, `techniques/*`, and others. No file defines it.
- HT source: `kiln-harness-tuner-probe/SKILL.md`.
  - 41-49: fork ONE change, name it "PROBE <id>: <what>" so nobody forks or measures it, stamp provenance.
  - 50-56: at most 6 train drives, default 3.
  - 64-70: keep the parent's model, provider, thinking level and sampling; answer no speed or cost question.
  - 79-80: drive the parent too for a parameter or mode question.
  - 81-84: 2/3 is yes, 0/3 is no, 1/3 is unclear.
  - `batch-selection` 998-1000: "No probe answers a speed or cost question".
- Fix: add "A quick check" to RX.

**M10 — LOOSENED: the power call**
- Kiln: RX 156-159. "Refuted: clearly past the noise"; "Inconclusive: inside the noise".
- HT source: `experiment-analysis/SKILL.md` 199-202: "a well-powered null (decent n, a NARROW CI around zero) is a real 'didn't work'; … a WIDE CI that straddles zero is 'can't tell'".
- Fix: add the narrow-CI null to "Refuted".

**M11 — LOST and LOOSENED: how a playbook step's outcome sets what comes next**
- Kiln: RX 221-222 ("a refuted or inconclusive step goes back to its playbook") and `references/improving_agents/index.md`.
- HT source: `kiln-harness-tuner-knowledge/references/planner.md` 13-32.
  - The smells of the present baseline come first; "a smell that blocks other work comes first".
  - Steps are in order, each with a condition: skip a step whose condition fails, start at the first that holds; the order can change on evidence.
  - Landed: go to the next step only if the issue is still open. Refuted: go to the next step. Capped: run again. Inconclusive: not refuted, the step stays open, and the next step can run in parallel.
  - 41-42: an own idea is marked "not in the knowledge".
- Fix: copy these into `references/improving_agents/index.md` "How to read".

**M12 — LOST: the expected outputs are the owner's policy**
- Kiln: `references/improving_agents/playbooks/dealing-with-a-wrong-eval.md` 29-35 and 44-46.
- HT sources: `batch-selection/SKILL.md` 445-462; `experiment-analysis/SKILL.md` 355-360. "An expected output that applies a rule the task's instructions do not state is not eval data… a config that misses that rule is a config failure". Call it eval data only on a contradiction.
- Fix: add this to `diagnose_an_agent.md` or RX "Read the failing items".

**M13 — CONFLICT (models 2 and 6): reading the project files and test scores**
- Kiln:
  - `references/knowledge/working_with_project_files.md` 28-37: "Reading files directly is fine… search every task run… read a trace". That includes val and test items and runs.
  - `references/knowledge/eval_scores.md` 10 and 78: "Prefer the aggregated `eval_results_summary`", which reads test.
  - `references/modes/improve_task.md` 69 routes "How did my evals go" there.
- HT source: `skill-authoring.md` 123-124: "The project tree… also holds every split's eval inputs and results". HT fences it.
- Note: these files are outside my list, but they defeat the lane and "never read test" rules.
- Fix: in `working_with_project_files.md`, say that the tree holds val and test items and that reading them counts as val or test data. Decide (owner) whether test scores may be reported at all over MCP.

**M14 — BRANCH (model 5): skill bundles**
- Kiln: `references/levers/skill.md` 40-51 and 67; `references/improving_agents/techniques/guide-skill-for-a-tool-set.md` 54, `document-into-a-skill.md` 64, `long-prompt-into-a-skill.md` 68, `rewrite-an-inherited-skill.md` 57 ("built when running Kiln Harness Tuner").
- HT sources: `experiment-build/SKILL.md` 87-95; `skill-authoring.md` 5-12; `kiln-task-setup/SKILL.md` 39 (outside HT, "write them to disk").
- Fix: the owner must decide how an MCP agent makes a skill with `references/`. One option is a Kiln endpoint; another is the disk write of `kiln-task-setup`, which `working_with_project_files.md` 43-49 now forbids. Then remove the branch.

**M15 — LOST: experiment-build hygiene**
- Kiln: RX 98-120.
- HT source: `experiment-build/SKILL.md`.
  - 175-178: "A rule replaces text. The prompt and the skills do not grow by default".
  - 179-181: when a tool takes over a step, delete the prompt rule.
  - 182-185: each rule names its source; a rule stated by pointing at one item is a hack.
  - 107-117: the consistency check of every text the model sees about the changed artifact.
  - 261-265: on a detach, rename or replace, update every mention.
  - 96-106: provenance `origin: "agent"`; a merge's `derived_from_ids` = the baseline plus every ingredient; a prompt's `derived_from_ids` = the parent's prompt id without `id::`.
- Fix: add these to RX "Build the candidate".

**M16 — LOST: merging**
- Kiln: RX 246-248.
- HT source: `merging.md`.
  - 10-17: write the combined config by hand, not by diff.
  - 18-26: same-layer scrutiny; same nouns with opposite modality is a conflict.
  - 31-35: never combine two candidates of one head-to-head group (also `batch-selection` 718-732: mutually exclusive fixes are sequenced).
  - 38-42: a reopened issue is rebuilt, never replayed.
  - 46-49: measure the ingredients' targeted evals first.
  - 53-59: a merge need not land 100% of its ingredients; mark each one landed or not.
- Fix: expand RX "Variants".

**M17 — LOST: reading the analysis**
- Kiln: RX "Measure on train"; `references/knowledge/eval_scores.md` paired recipe (lines 42-46).
- HT sources:
  - `experiment-analysis` 34-47 and `promote` 90-100: the delta is sign-normalized and the absolutes are not; on `lower_is_better` a falling pair is a win.
  - `experiment-analysis` 213-217: replicate rows are folded to the per-input mean before pairing.
  - 362-368: "A judge may read the config".
  - 95-102: dangling references.
  - 235-242: magnitude matters ("two up slightly while one collapses" is a fail) on the train verdict too.
- Fix: add these to RX step 3 and the verdict.

**M18 — LOST: reading speed and cost results, and report wording**
- Kiln: RX 235-238; `references/modes/improve_task.md` 77-82.
- HT sources:
  - `batch-selection` 158-169, `experiment-analysis` 187-197, `report` 238-252: "lost k of n baseline passes (no loss rate above X% at 95%)", never "quality held"; a fix of a baseline failure is noise level; a promotion is "no clear loss", never "no loss".
  - `report` 271-284: source every claim; no inferred composition; no unsourced quantifiers.
- Fix: add these to RX "Record and report".

**M19 — CHANGED: the detectability moves**
- Kiln: RX 82-85: "fix the measurement first".
- HT source: `batch-selection` 668-687. Predict a larger effect and say why, OR pick a target whose eval can carry it, OR grow the eval. "This is judgment, never a formula". Also lost: 711-716 (no baseline rows ⇒ give a conditional fraction; "Never carry a magnitude over from another task") and 689-705 (floor = 6 wins; room 0 ⇒ plan the eval as a guard).
- Note: the saturated playbook (17, 24) has the floor only as a branch.
- Fix: restore the three moves and the two lost sentences. Port the floor (6 wins at p<.05) as computable by hand.

**M20 — LOOSENED: issue priorities and UNMEASURABLE**
- Kiln: MEM 109-112 ("change one by an update") and MEM 116 ("its evals are all gone").
- HT source: `memory/SKILL.md` 60. Priority is "source-owned (from `spec.priority`)… a re-sync replaces the tag rather than an agent re-prioritizing". UNMEASURABLE also covers an eval that "left the active set", and it is "never a close".
- Fix: restore both.

**M21 — LOST: reading val job errors item by item**
- Kiln: RX 128-130 reads job errors, and RX 167-170 does not limit that to train.
- HT source: `promote/SKILL.md` 149-157: "Per-item job errors are not available to you: they name val items one by one".
- Fix: say that on val only the coverage and the error classes are read.

**M22 — LOST: no prompt optimizers**
- Kiln: none.
- HT source: `batch-selection` 59-63: "Levers exclude **fine-tuning and GEPA-style prompt optimizers**" unless the guidance names one. Kiln exposes a prompt optimization API.
- Fix: one line in `references/levers/index.md` or RX.

**M23 — CHANGED and BRANCH (model 4): the code-trust grant for HT roles**
- Kiln: `references/knowledge/code_tool_authoring.md` 156-158: "ask the user before you grant it".
- HT source: `code-tool-authoring/SKILL.md` 105-108: trust is HT's `trust_code_tools` operation, and HT roles never ask a human.
- Fix: "In a Kiln Harness Tuner role, Kiln Harness Tuner grants trust with its own operation."

**L1 — BRANCH (model 5): other "when running Kiln Harness Tuner" conditions**
These are outside my list; listed for completeness:
- `references/improving_agents/playbooks/dealing-with-a-noisy-eval.md` 28-36 (spec 4.5 sanctioned the noise wording; the owner now wants it removed)
- `references/improving_agents/playbooks/dealing-with-a-saturated-eval.md` 17, 24
- `references/improving_agents/playbooks/spending-the-budget.md` 27-28, 86
- `references/improving_agents/playbooks/dealing-with-train-wins-rejected-at-val.md` 29, 58
- `references/improving_agents/playbooks/cheaper-or-faster.md` 20-22
- `references/improving_agents/techniques/one-general-rule-per-edit.md` 86-87
- `references/improving_agents/techniques/new-tool-description.md` 119

**L2 — LOST: minor items**
- Memory and HT memory rules:
  - MEM 100: queries return resolved issues; skip them by prefix.
  - MEM 140-142: "NOT LANDED: never the same rc again"; "CAPPED: the same rc with a larger cap goes on".
  - MEM 139: "REJECTED AT VAL is never removed".
  - HT `memory/SKILL.md` 67: a failed val write is logged and skipped.
- `kiln-task-setup` rules:
  - `turn_mode` is frozen.
  - `call_kiln_api` is hidden from the UI tool pickers.
  - Check `supports_function_calling` for tool tasks.
- Skill and API wording:
  - `adding_skills.md` lacks "No other resource paths exist — never guess one" (`skill-authoring.md` 111-115).
  - `SKILL.md` 37 lacks the HTML-body 404 tell (`kiln-api` 39-43).

**Correctly done**
- Coverage and holes, the at-ceiling rule, OPEN escalation, "one winner or none", "promote exactly what was measured", "never change the default run config", the waiver marked "train only", headroom-capped predictions, "not applied", and the whole code-tool authoring file are PRESENT.

## 3. What HT's train lane may see today (b49f159)

**No val summary metrics and no `val` memory record.** Only two roles are val readers: `promote_best` and `report_writer`.

- `gateway/ops.py` 67: `VAL_READERS = frozenset({"promote_best", "report_writer"})`
- `gateway/ops.py` 811-812: `if VAL_MEMORY_TAG in req.tags and not self.s.val_reader: raise GatewayError("the `val` memory record is not available to this role")`
- `gateway/ops.py` 297-298 and 826: val-tagged rows are filtered out of every listing for non-readers.
- `gateway/ops.py` 1415-1419: `get_val_summary` reads `val_summary.json`, "the read fence must deny it from the first session on". The operation is granted only to `promote_best` and `report_writer` (`gateway/SKILL.md` 315-320; `ROLE_OPS` `gateway/ops.py` 1662-1676).
- `memory/SKILL.md` 67: "`val` is an **access class**… the rule it exists to support is 'the train lane never fetches `tags=val`'… Query when: The promotion agent, the report writer at exit, and human/interactive orientation. ⛔ **Never on a train-side lane** — this record IS val metrics, so a read is the leak the split guarantees exist to prevent."
- `memory/SKILL.md` 36: "the `val` record (`tags=val` — ⛔ never on a train-side lane…)"
- `batch-selection/SKILL.md` 43-45: "**Never query `tags=val`.** That singleton record *is* the val-split metrics of every promotion — reading it leaks val into train-side context". Lines 53-56: "Never ask for val or test results… This is enforced".
- `agents/batch_plan.md` 20-23 and `agents/analyze_experiment_results.md` 13-15: "never query `tags=val`… never pass `split=val|test`".
- `gateway/SKILL.md` 15: "**Every answer is train-only.**"
- `gateway/SKILL.md` 270: "The loop's `val` record is not listed or fetched, except by the promotion agent and the report writer."

**What the train lane does see from val: metric-free outcomes in words.**
- The `— PROMOTED` / `— REJECTED AT VAL <MM-DD>` / `— HELD` stamps on experiment records.
- One rejection reason line, for example "no gain at val: no targeted eval improved." or "an eval dropped at val: down beyond doubt on eval <id>". See `memory_schema.py` 963-1008 ("Metric-free by construction… the experiment record it goes on is train-readable") and `batch-selection` 1041-1060.
- The `gate_blocks` input (copied-eval-text reasons, "never from val", `batch-selection` 403-417).
- The train lanes also never read the `baseline` record (`batch-selection` 46-52).

**Interactive sessions (not a loop lane) may read the val record for orientation** (`memory/SKILL.md` 36 and 67).

**So owner choice "a" (a narrow agent may read val summary metrics and the val record) is wider than what HT's train lane sees today.** It matches only what HT already allows interactive sessions. The committed MEM 107 is narrower than both.
