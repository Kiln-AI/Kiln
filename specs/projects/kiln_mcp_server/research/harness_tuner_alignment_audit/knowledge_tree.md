---
status: complete
---

# Harness Tuner alignment audit: knowledge tree (HT b49f159 vs Kiln 25157f3)

**Verdict:** the knowledge content keeps HT's method well. About 330 of the 416 changed sentence groups are vocabulary only. HT still cannot be re-pointed as things stand, for two reasons:
- **HT's own code and prompt templates cannot load the port's layout and front matter** (A1, A2).
- **A set of sentences now tell HT's autonomous agents to "ask the user" or "check it yourself", or say a rule "applies when running Kiln Harness Tuner"** (A3–A5, B1–B9). The first two do not work for HT agents, which cannot ask and whose checks HT runs in code. The third conflicts with the owner's model.

## Method
1. I normalised HT's text mechanically: links rewritten to root paths, `gateway_ops`/`api_docs`/`detected_by`/`detectors` dropped, the lever heading renamed. Diffed against the batch-7 import (b4b066e), all 74 files came out byte-identical, so batch 7 was purely mechanical.
2. I then word-diffed and sentence-diffed the normalised HT source against 25157f3 for all 74 files, and walked every one of the 416 changed or deleted sentence groups. A script confirms 189 as vocabulary only; I read the other 227 by hand.

Line numbers are those of the paragraph holding the sentence. Kiln paths are from `app/mcp/kiln_mcp_server/skill/`. HT paths are from `kiln-harness-tuner-knowledge/references/` unless written in full.

## 1. Ranked findings

### A. Would break HT

**A1 — HT's loader cannot read the port (outside the trees, but it decides re-pointing).**
- **HT side:** `src/kiln_harness_tuner/knowledge/schema.py:45` requires the lever section "How the tuner changes it", `:176` expects `gateway_ops`, and `:193` requires `detected_by` (at least one entry) on every smell. `load.py:27` and `:121` look for the skill `kiln-harness-tuner-knowledge` with `references/{smells,techniques,playbooks}/`.
- **Port side:** the levers use `api_docs` and "How to change it", the 15 smells have no `detected_by`, and the folders sit under `improving_agents/`.
- **Effect:** `smells/run.py:439-451` (`_smell_titles`) logs `knowledge_unreadable`, and smell detections and findings are kept unchecked. `python -m kiln_harness_tuner.knowledge check` fails.
- **Fix:** an adapter in HT's loader for the Kiln schema and paths, or carry `detected_by` and `detectors` in Kiln's schema. Today Kiln's schema refuses unknown keys (spec 4.2).

**A2 — HT's prompt templates name entry files the port does not have.**
- `agents/batch_plan.md:8` names `references/planner.md`, `create_experiment_rc.md:7` names `builder.md`, `baseline_review.md:5` names `smells.md`, `analyze_experiment_results.md:5` names `analyzer.md`, `report_writer.md:6` names `report.md`; `technique-index.md` is also gone.
- The port has only `references/improving_agents/index.md` and `references/levers/index.md`.
- The port's Smells table also dropped the "Detected by" column, which the baseline reviewer uses to tell code-detected smells from agent-detected ones.
- **Fix:** HT keeps its role entry files on its side and points them into the shared trees, and the index keeps a "Detected by" column.

**A3 — five smells stop pointing at HT's code detection (CHANGED / CONFLICT with owner point 3).**
- **Kiln:** `smells/very-long-prompt.md:3,19,29,43`, `very-long-skill-description.md:3,19,30,40,45`, `very-long-tool-description.md:3,13,26`, `too-many-tools.md:3,23,35`, `old-model.md:3,23`.
- **HT:** the same files, lines 3, 24–35, 43–48 (old-model.md:3, 27).
- **Source:** "the code detection in your input gives … / Code measures the length / A code detector counts them".
- **Port:** "measure it yourself / Count them yourself".
- **Effect:** the HT baseline reviewer is told to re-measure, which contradicts its own skill ("check each code detection").
- **Fix:** "Kiln Harness Tuner has smell detectors in code; when its detection is in your input, confirm it. Otherwise measure it yourself: …".

**A4 — "ask the user" replaces HT's inputs (CHANGED / CONFLICT with owner point 1).** HT agents cannot ask the user, and their inputs are no longer named.
- **Kiln:** `levers/model.md:70-71` ("Ask the user which models and providers are allowed before you create a run config"), `model.md:84-85`, `playbooks/working-inside-restrictions.md:23`, `know-the-agent-before-you-plan.md:40`, `spending-the-budget.md:22,30`.
- **HT:** model.md:67, 80; working-inside-restrictions.md:23; know-the-agent:40; spending:22–29.
- **Source:** `allowed_models`, `model_policy`, `flagged_models`, `measurement_prices` ("the largest cap that code allows"), `should_wrap_up` ("the code's judgment that this is the last wave").
- **Fix:** "the models the user allows (Kiln Harness Tuner: `allowed_models` and the model policy in your input; otherwise ask the user)", and the same pattern for the other inputs.

**A5 — HT's builder is told to ask before granting code trust (TIGHTENED).**
- **Kiln:** `levers/new_tool.md:42-44`. **HT:** new_tool.md:41.
- **Source:** "Grant trust once in the session: `trust_code_tools`." **Port:** "Ask the user first: the code runs on the machine where Kiln runs."
- **Effect:** an HT builder cannot ask, so it may stall on a `new_tool` item.
- **Fix:** "Kiln Harness Tuner grants it once per run; otherwise ask the user first."

### B. Changes a rule

**B1 — skill bundles are "built when running Kiln Harness Tuner" (BRANCH / CONFLICT with owner point 4).**
- **Kiln:** `levers/skill.md:43,50,67`, `techniques/long-prompt-into-a-skill.md:68`, `document-into-a-skill.md:64`, `rewrite-an-inherited-skill.md:57`, `guide-skill-for-a-tool-set.md:54`.
- **HT:** skill.md:35–39, 59; long-prompt:64; document:59; rewrite:52, 59; guide:50.
- **Source:** "a bundle that the builder writes … installs with the `install_skill_bundle` tool of the skill installer" and "At most 512 KB for one file".
- **Port:** "a skill with reference files is built when running Kiln Harness Tuner"; "A bundle that Kiln Harness Tuner installs has at most 512 KB".
- **Fix:** state the bundle shape as the rule for every agent and name the tool plainly ("Kiln Harness Tuner has a skill installer, `install_skill_bundle`"). This needs an owner decision: the Kiln API creates a skill from name, description and body only, and `working_with_project_files.md` forbids writes to the project folder. So MCP agents have no route to a bundle without a new Kiln capability.

**B2 — noise (BRANCH / NOISE: an HT-only tool / LOOSENED for MCP).**
- **Kiln:** `playbooks/dealing-with-a-noisy-eval.md:28-33`, `spending-the-budget.md:26`. **HT:** noisy:28; spending:26–27.
- **Source:** "When `train_noise` is in your input …, `noise_adjusted_wins` is the bar … When `train_noise` is absent … the stop rules use a flip rate of 10%. Say in `rationale` which case applies."
- **Port:** "Kiln Harness Tuner measures it … This rule applies when running it … Kiln Harness Tuner's stop rules use a flip rate of 10%. Say in your report …"
- **The HT tool** is the run-to-run noise check, `--noise-check N` (`noise.py`). Kiln has no noise endpoint; `POST /api/statistics` is the paired test, not a repeat-noise measure.
- **Fix:** "Kiln Harness Tuner has a run-to-run noise check (`--noise-check N`); its result is `train_noise`, with the bar `noise_adjusted_wins`. Kiln does not measure noise. Without it, the noise is not known: use a flip rate of 10%." Keep `rationale` for HT. Spec 4.5's "Noise" fixed point needs the owner's ruling on whether the 10% applies to everyone.

**B3 — detectability (BRANCH / DETECTABILITY: an HT tool, but computable from what Kiln measures).**
- **Kiln:** `dealing-with-a-noisy-eval.md:34-37`, `dealing-with-a-saturated-eval.md:15-18,22-24`, `spending-the-budget.md:26`.
- **HT:** noisy:34; saturated:15, 20; spending:26.
- **Source:** "`train_detectability` gives the score a `room` of 0 … When `room` is also below `floor` …"
- **Port:** "Kiln Harness Tuner measures it for each score, and this sign applies when running it".
- **The HT tool** is the pre-run detectability check (`detectability.py`). Kiln has no detectability endpoint, but the room is a count over the train results endpoint. The floor follows from the paired test (`POST /api/statistics`): at least 6 changed items, all one way, for p < .05 (6 for pass/fail, from `detectability.py`).
- **Fix:** name the HT check plainly, and give MCP agents the count and the floor.

**B4 — the speed/cost screening and its win rule (BRANCH / LOOSENED for MCP).**
- **Kiln:** `playbooks/cheaper-or-faster.md:17-21`. **HT:** cheaper-or-faster:17.
- **Source:** "The planner's skill opens the run with a screening round in code … its rule decides a win."
- **Port:** "Kiln Harness Tuner holds that screening procedure and its rule, and they apply when running it."
- **Fix:** name HT's planner procedure plainly, and point MCP agents to the keep rule in `run_an_experiment.md` (backlog B14).

**B5 — the train-wins playbook drops HT's record lines (LOST + BRANCH).**
- **Kiln:** `playbooks/dealing-with-train-wins-rejected-at-val.md:13-29,51`. **HT:** 13–31, 50.
- **Source** gives HT's exact lines: "`— REJECTED AT VAL`", "`- rejected at the val gate <MM-DD> vs baseline <rc> — `", "`- blocked at the val gate <MM-DD>: …`", "`no gain at val: no targeted eval improved.`", the fallback "`not promoted at val; details in the run report.`", the legacy "`— did not beat it; details in the run report.`" and the "`— PROMOTED` with the same `<MM-DD>`" heuristic.
- **Port** restates the reasons in words, then says "When running Kiln Harness Tuner, its record … gives the reason in the same words". That claim is inaccurate: HT's wording differs.
- **Fix:** quote HT's lines plainly ("Kiln Harness Tuner writes …"). `knowledge/memory.md:130-145` already uses the suffixes.

**B6 — merge timing (BRANCH / LOOSENED).**
- **Kiln:** train-wins:56-58. **HT:** 56.
- **Source:** "Merge it when the merge timing of your planner skill says so."
- **Port:** "Merge it later. When running Kiln Harness Tuner, its merge timing says when."
- **Fix:** name HT's merge-timing rule and port it, or record it as an open item for the owner.

**B7 — HT's integrity checks are left unnamed (CONFLICT with owner point 3).**
- **Kiln:** `requirement-missing-from-the-prompt.md:45`, train-wins:38, `dealing-with-a-wrong-eval.md:63`, `levers/prompt.md:59`, `levers/tool_config.md:68`, `prune-one-group-at-a-time.md:73`, `remove-or-scope-tools.md:73,82`.
- **Source:** "The judge-copy check finds a copied passage and ends the arm", "the reference check".
- **Port:** "A check for copied judge text finds …" and "search the text yourself". The first implies such a check exists for MCP agents.
- **Fix:** "Kiln Harness Tuner's judge-copy check (a run of 8 or more words) … ; without it, search yourself".

**B8 — "Code …" becomes "check it yourself", and the verdict words go (CHANGED for HT).** About 30 sentences.
- **Kiln:** `levers/params.md:56-61`, `model.md:66,74`, `output_mode.md:62-70`, `skill.md:69-71`, `prompt.md:55`, `new_tool.md:87`, `thinking-level-ladder.md:78`, `model-swap-inside-a-class.md:97`, `decision-model-for-a-classifier.md:82`, `faster-provider-for-the-same-model.md:73`, `add-the-missing-requirement.md:59`, `rewrite-an-inherited-skill.md:68`.
- **Lost:** the verdicts `lever not applied`, `lever unverified` and `applied`, and the stop rule `invalid_output_rate`.
- **Fix pattern:** "Kiln Harness Tuner checks this in code (verdict `lever not applied`); otherwise check it yourself."

**B9 — the screening is now built by hand (CHANGED for HT).**
- **Kiln:** `levers/params.md:38`, `model.md:40`, `output_mode.md:48-50`, `output-contract-not-met.md:43`.
- **Source:** "Code makes each candidate's run config … No agent builds them", with `screen`, `overrides` and `work.existing_rc_id`.
- **Port:** "Make one run config for each candidate".
- **Risk:** an HT builder may build screening run configs itself.
- **Fix:** "Kiln Harness Tuner runs a screening in code; otherwise …".

**B10 — HT input names replaced by by-hand steps (CHANGED; HT's batch-selection skill still defines all of them, so lower risk).**
- `probe_results` from the setup reconnaissance → do a quick check: `output_mode.md:91`, `know-the-agent-before-you-plan.md:17`.
- `lever_attempts` → count from your records: `change-the-surface-not-the-words.md:21`.
- `measure_issue_baseline`: saturated:30, wrong-eval:36.
- `evaluation_target`: `fixed-call-chain.md:43`, `remove-or-scope-tools.md:43`, `roll-up-tool.md:46`, `consolidate-tools.md:46`, train-wins:63, saturated:33.
- **Fix:** keep each name in parentheses for Kiln Harness Tuner.

**B11 — HT's output fields become "report to the user" (CHANGED).**
- `open_questions` / `rejected_summary`: wrong-eval:42, saturated:43, near-zero:67, working-inside-restrictions:47,53,63, change-the-surface:69, tools-on-a-live-server:62.
- `rationale` → "your report": noisy:28.
- `build_notes` → "the `notes` of the tool's `provenance`": `errors-the-agent-can-act-on.md:92`. HT's builder now writes its reasoning to a different place.
- **Fix:** "report it to the user (Kiln Harness Tuner: in `open_questions`)".

**B12 — HT's restriction is now stated as false (CHANGED).**
- **Kiln:** `working-inside-restrictions.md:23-26`. **HT:** 23–26.
- **Source:** "Code refuses a run config whose model the policy does not allow."
- **Port:** "Nothing refuses a run config whose model the user does not allow: check it yourself." This is false under HT, whose gateway refuses it. `model.md:70` drops "The model policy is checked at create" in the same way.
- **Fix:** "Kiln Harness Tuner refuses it at create; Kiln does not, so check it yourself."

**B13 — item-reading steps name no split (CONFLICT risk with owner points 2 and 5).**
- **Kiln:** wrong-eval:27-29 ("For each failing item, read the output, the expected output and the judge's reasoning"), near-zero:42, `add-the-missing-requirement.md` (Name the requirement), `state-the-output-contract.md` (Find the rule), `missing-context-the-agent-could-be-given.md`.
- These sentences are unchanged from HT, where code enforced train-only access. For MCP agents nothing does.
- **Fix:** "failing train items", plus the pointer to `train_val_test.md`.

**B14 — `improving_agents/index.md:32-34` (CHANGED).**
- **HT:** SKILL.md:37–39. **Source:** "as the stop rules and the val gate judge it".
- **Port:** "as the measurement on train and the confirmation on val judge it". HT's stop rules no longer decide "clearly past the noise".
- **Fix:** "as the stop rules of Kiln Harness Tuner, or `references/knowledge/run_an_experiment.md`, and the confirmation on val judge it".

**B15 — the skill installer is atomic (LOST).**
- **HT:** skill.md:52, "**The install is atomic.** A refused bundle writes nothing, and the refusal lists every problem at once."
- **Kiln:** no replacement in `levers/skill.md:60`.
- **Fix:** restore it as a statement about HT's installer.

**B16 — the "Text you add" pointer (LOST).**
- **Kiln:** `one-general-rule-per-edit.md:53`, and the "See also" of `levers/prompt.md:70`.
- **Source** points to HT experiment-build's "Text you add".
- **Lost rules**, which exist nowhere else in the Kiln skill: "say which text it replaced, or why nothing could go", and "a rule you can state only by pointing at one item is a hack".
- **Fix:** port the three bullets into `run_an_experiment.md` or this technique.

**B17 — output-mode details (LOST, minor; in HT's batch-selection skill).**
- **Kiln:** `levers/output_mode.md:50,62,91`. **HT:** output_mode.md:50, 64, 94.
- Lost: "A probe can set the mode. It cannot set a model, a provider or a setting."; the check counts (`count: json_valid`, `attach: probe_tool`); the judge-free timing drives; and "The model preflight does not show this: its test call attaches no tools." The preflight line at `model.md:46` is also gone (it asked nothing of the reader; OK).

**B18 — `levers/new_tool.md` (CHANGED, intended and documented).**
- `:20` "sandbox" became "no resource sandbox", pending the security review.
- `:68` the uniqueness rule changed: HT refuses a function name already used by a tool that is not archived; Kiln refuses two tools with one name in a run config or an allowlist. HT's gateway may still enforce HT's version.

**B19 — added rules (TIGHTENED, consistent with HT).**
- saturated:43-47 and wrong-eval:42-46 add "rare exception / none for a closed issue / won't fix, never reopen", from HT's batch-selection skill.
- train-wins:13 adds "no number, no item id and no trace", from HT's promote and memory skills.

### C. Wording
- **C1 — the front matter of `levers/skill.md` lacks an endpoint.** Its `api_docs` omits `post_api_projects_project_id_skills.md`, which the body uses at line 39.
- **C2 — "See also" pointers dropped, as the spec says.** Lost: `kiln-task-setup`'s "known platform bugs" (prompt), "the rebuild after a dangling reference" (tool_config), and "how to read a screening line" (params).
- **C3 — the root cause is in the spec.** `skill_and_content.md` §4.5 bullet 3 and the last `LOOP_WORDS` row require "the rule applies when running Kiln Harness Tuner". The batch-8 bundle deviation (919fb6a) did the same. Both conflict with owner points 3 and 4; fix the spec first, then the files.
- **C4 — the train lane is missing.** It is not named anywhere in the trees, and `train_val_test.md` at 25157f3 has no "narrow / broad / lane" rule. Not a diff finding, but part of owner point 2 is not in place.

## 2. Counts
Out of 416 changed sentence groups; categories overlap.

| Category | Count |
|---|---|
| OK | ~330 (189 confirmed by script) |
| BRANCH | 15 |
| NOISE | 3 |
| DETECTABILITY | 4 |
| CHANGED | ~45 (B8 about 30, B11 11, plus B12, B14, B18) |
| LOST | ~12 |
| LOOSENED | 4 |
| TIGHTENED | 5 |
| CONFLICT | ~35 (B1 7, B2/B3 6, B4–B6 4, B7 8, plus the A4 "ask the user" group) |

The OK group is endpoint-doc paths, arm → candidate, val gate → confirmation on val, probe → quick check, smoke → run, the See also lines the spec asked for, template paths, leak-rule pointers, and threshold numbers checked against HT's `thresholds.py` (200,000 / 4,096 / 1,024 / 40 / 8 months).

**Files with no findings** (vocabulary-only diffs; B13 is a separate gap):
- **Playbooks:** answers-not-grounded, malformed-tool-calls, missing-context-the-agent-could-be-given, wrong-scope-or-refusal, wrong-tool-chosen, skill-is-not-read, lost-in-long-instructions, fit-the-tool-layer-to-the-agent, ordering-work, failure-at-a-tool-call.
- **Smells:** document-behind-a-lookup-tool, faulty-inherited-skill, general-query-tool-without-a-guide, one-file-skill-with-many-topics, skill-too-small-to-earn-its-place, tool-results-flood-the-context, tool-search, unnecessary-tools.
- **Techniques:** answer-only-from-the-source, cap-and-preview-wrapper, decline-rules-paragraph, directive-in-the-tool-response, guard-tool-calls-at-the-boundary, normalize-inputs-wrapper, new-tool-description, policy-as-step-by-step-procedures, skill-into-the-prompt, state-the-output-contract, structure-a-long-prompt, attach-the-knowledge-source, and the three sub-files of guide-skill-for-a-tool-set (sample-queries, schema-as-leaf-files, timestamps).
- **Index:** `levers/index.md`.
- **No lever is clean.**

## 3. HT rules in the knowledge skill's SKILL.md with no home
None is lost:
- "How to read these documents" (all three paragraphs), the table of parts, the usual path, and "use the technique index only when the guidance names a technique" are all in `improving_agents/index.md:8-51`.
- Only the "Your entry file" table (role entry files, excluded from this check) and "Related" (pointers to HT skills, no rule) have no home.
- One rule is changed: B14, "the stop rules and the val gate".

## Working files
All in `/tmp/claude-0/-home-user-Kiln/2d94edc9-cf88-595e-ad22-306868b3911d/scratchpad/audit/knowledge/`:
- `/tmp/claude-0/-home-user-Kiln/2d94edc9-cf88-595e-ad22-306868b3911d/scratchpad/audit/knowledge/sent/*.txt` — the sentence-level diff for each file, with HT and Kiln line numbers.
- `/tmp/claude-0/-home-user-Kiln/2d94edc9-cf88-595e-ad22-306868b3911d/scratchpad/audit/knowledge/diffs/*.diff` — the word diffs, with counts in `/tmp/claude-0/-home-user-Kiln/2d94edc9-cf88-595e-ad22-306868b3911d/scratchpad/audit/knowledge/diffs/_counts.txt`.
- `/tmp/claude-0/-home-user-Kiln/2d94edc9-cf88-595e-ad22-306868b3911d/scratchpad/audit/knowledge/ht_norm/` — the normalised HT source.
- `/tmp/claude-0/-home-user-Kiln/2d94edc9-cf88-595e-ad22-306868b3911d/scratchpad/audit/knowledge/port/` and `/tmp/claude-0/-home-user-Kiln/2d94edc9-cf88-595e-ad22-306868b3911d/scratchpad/audit/knowledge/b7/` — exports of 25157f3 and b4b066e.
- `/tmp/claude-0/-home-user-Kiln/2d94edc9-cf88-595e-ad22-306868b3911d/scratchpad/audit/knowledge/diff_ht_b7/all.txt` — empty, because batch 7 is byte-identical to the normalised source.
- `/tmp/claude-0/-home-user-Kiln/2d94edc9-cf88-595e-ad22-306868b3911d/scratchpad/audit/knowledge/scripts/` — the normalisation, sentence-diff and classification scripts.
