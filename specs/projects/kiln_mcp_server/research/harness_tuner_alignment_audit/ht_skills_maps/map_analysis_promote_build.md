# experiment-analysis (397 lines) -> RX (run_an_experiment.md) "Measure on train, and judge", eval_scores.md
A01 | 14-18 | train-side only | RX 124, TVT | PRESENT
A02 | 21-30 | gateway only | - | N/A
A03 | 34-47 | delta sign-normalized, base/cand raw; lower_is_better | - | LOST | no rule for reading a falling score as a win
A04 | 49-56 | parent vs prior_baseline screen-out | - | N/A
A05 | 58-66 | coverage fields; job ids for promote | RX 128-130 | PRESENT
A06 | 69-79 | <~95% graded caution, check skew, "no pattern" is a finding | RX 131-133 | PRESENT
A07 | 80-82 | hole on must-not-regress target => usually not successful; side-interest hole acceptable if stated | RX 137-138 | PRESENT
A08 | 83-88 | holes doctrine on the designed-to-move pair | RX 149-151 | PRESENT
A09 | 89-93 | never hand-recover a hole; re-measure | RX 134-136 | PRESENT
A10 | 95-102 | dangling references -> result measures breakage | - | LOST
A11 | 104-123 | spend label "bundle cost"; exclusions; never patch with an estimate | - | LOST
A12 | 125-142 | read failing traces, pair by item id, train only | RX 142-143, diagnose | PRESENT
A13 | 144-157 | latency/cost under quality = information only; never judge success on them | RX 194 | PRESENT | partly ("separate axis")
A14 | 159-185 | speed objective success = clearly faster AND quality equal or better per speed_rule | RX 194-198 | BRANCH
A15 | 187-197 | speed/cost measurement line is a bound; never "held"/"neutral" | - | LOST
A16 | 191-197 | successful = own targeted goals on train; low-significance positive may succeed | RX 146-151 | PRESENT
A17 | 199-202 | power call: NARROW CI around zero = real "didn't work"; WIDE CI = can't tell, enlarge | RX 156-159 | LOOSENED | port's "Refuted" needs "clearly past the noise"; a well-powered null reads as "inconclusive"
A18 | 203-212 | at-ceiling perfect arm is successful (conditions) | RX 152-155 | PRESENT
A19 | 213-217 | replicate rows folded: per-input mean | - | LOST | matters for the by-hand pairing in eval_scores' recipe
A20 | 218-224 | code floor: primary measured+improved, no row ci_high<0, coverage floor | RX 146-147 | PRESENT
A21 | 225-234 | missed prediction = caution; judge vs headroom | RX 162-163 | PRESENT
A22 | 235-242 | priority-weighted; magnitude matters (two up slightly, one collapses = fail) | RX 190-193 (val only) | LOST | not applied to the train verdict
A23 | 243-247 | partial wins honest; merge attribution | - | LOST | see merging
A24 | 248-258 | landed:false when the issue did not close | RX 212-214 | PRESENT
A25 | 262-307 | FROZEN overview format (row shape, pp vs rating, | join, +N more, arrow marker, no " — " in label, no %, labelled numbers) | MEM 66-68 example | LOST | format not stated (moot if MCP is read-only)
A26 | 310-331 | content must cite rc id, issue id, eval id, parent, h2h group, table incl holes, bundle cost, next: for a cold start | MEM 102 | LOST | issue id / eval id / holes / next for a cold start
A27 | 340-347 | name the decision point (before/with/after which tool) | diagnose 91-92 | PRESENT
A28 | 348-361 | failure class config/eval data/judge/environment/noise; expected outputs are the owner's policy | wrong-eval 29-35 | PRESENT | owner-policy half LOST (B27)
A29 | 362-368 | a judge may read the config (skill/tool wording) | - | LOST
A30 | 369-371 | measured negative is normal | RX 156 | PRESENT
A31 | 374-377 | never edit run configs, evals, eval configs, splits after results (eval-freeze, one-crack) | wrong-eval 47; RX 201 | PRESENT
A32 | 378-383 | never val/test; never tags=val/baseline | TVT | CHANGED | owner choice a
A33 | 384-391 | discovery writes only; disclose failed writes | MEM | CONFLICT | port writes lifecycle

# promote (268 lines) -> RX "Confirm on val", "Keep or discard"
P01 | 19-30 | the one mid-loop agent that may read baseline+val records | MEM 107 | PRESENT
P02 | 47-48 | headline = mean win rate vs baseline across evals | MEM 107 (example only) | LOST
P03 | 49-57 | only significant deltas register; priority dominates; magnitude (95%->2% reject); lexicographic default; NOTHING SIGNIFICANT ANYWHERE -> headline + cost Pareto decide | RX 190-193 | TIGHTENED | port requires "the target eval is clearly better on val"
P04 | 58-65 | cost/latency as Pareto, information when not paired | RX 194 | PRESENT
P05 | 67-84 | speed/cost eligibility + fastest/cheapest wins, ties by quality wins then p90 | RX 194-198 | BRANCH
P06 | 86-88 | promote session read-only | - | N/A
P07 | 90-100 | magnitude off absolutes, direction off delta; lower_is_better | - | LOST
P08 | 102-109 | ineligible cannot win; never "no regressions" for an eval in errors | RX 177-178 | PRESENT
P09 | 111-128 | hole on primary target disqualifies unless 3 conditions; guard holes = missing evidence | RX 172-177 | PRESENT
P10 | 130-139 | train table clamped => condition 1 unmet; never infer from overview | - | LOST | minor
P11 | 141-147 | <95% coverage: graded caution; prefer fully measured near-peer | RX 178-179 | PRESENT
P12 | 149-157 | per-item val job errors are NOT available (they name val items); read only code's summary | - | LOST | RX tells agent to read job errors (128-129) and never limits it to train; on val that is item-level
P13 | 159-179 | OPEN escalation: guidance answers => answered; else hold, not loss | RX 181-186 | PRESENT
P14 | 181-200 | integrity flags: verbatim judge/spec/eval text or eval name = BLOCKED; output length moved >2x, top-level JSON keys changed, new kind of write action, reviewer paraphrase => winner needs an "Integrity:" line per flag | - | LOST
P15 | 202-207 | one winner or none; promote exactly what was measured; no post-measurement surgery | RX 199-202 | PRESENT
P16 | 217-227 | rationale -> val line, summary numbers only | MEM 107 | PRESENT | but written by MCP agent (CONFLICT, see memory)
P17 | 228-237 | regressed_issues: code REOPENS a FIXED issue / adds a repro line to an open one, metric-free | RX 215-217 | CHANGED | port: add line, ask the user about reopening; open-issue repro line lost
P18 | 241-245 | no jobs, no split params in the gate | - | N/A | one agent does both
P19 | 246-248 | val item/trace detail out of everything | TVT 30-36 | PRESENT
P20 | 249-258 | losers stamped by code with metric-free reason | RX 231-232 | CONFLICT | MCP agent writes it
P21 | 259-260 | never touch the default run config | RX 217-218 | PRESENT

# experiment-build (326) + merging.md (92) + skill-authoring.md (193) -> RX "Build the candidate", levers, adding_skills
E01 | 36-41 | read parent; build the hypothesized change only (one mutation) | RX 102-103 | PRESENT
E02 | 42-64 | additive only; never mutate parent/shared; rewrite skill = new version | RX 100-101; working_with_project_files | PRESENT
E03 | 54-60 | tool/skill attach + function_calling refusal -> set mode | levers/model, output_mode | PRESENT
E04 | 60-63 | run_config_properties immutable (PATCH silently drops) | improve_task 45 | PRESENT
E05 | 65-80 | params / output_mode arms; new model default mode | levers | PRESENT
E06 | 81-82 | invalid output after a swap -> wrong mode first, not a weaker model | levers/model | PRESENT (assumed by grep of mode text)
E07 | 87-95 | skill WITH resource files = bundle via install_skill_bundle | levers/skill 40-51, techniques | BRANCH | "built when running Kiln Harness Tuner"
E08 | 96-106 | provenance: notes = hypothesis+evidence, derived_from_ids = [parent rc] (merge: baseline+ingredients), origin "agent"; prompt derived_from = parent prompt id without id:: | RX 107-109 | LOST | origin, merge list and the prompt-id rule lost
E09 | 107-117 | consistency check: every text the model sees about the changed artifact agrees with the change and covers the target routes | - | LOST
E10 | 118-140 | smoke on target items; mechanism ENGAGED or it is not built; partial engagement -> ship with counts | RX 113-120 | PRESENT | partial-engagement rule lost
E11 | 130-133 | not engaged -> dead_end "NOT VIABLE: ..." | RX 119 | CHANGED | verdict "not applied" (fine)
E12 | 141-155 | change block | - | N/A
E13 | 157-171 | rule not value; invented examples | TVT 97-104 | PRESENT
E14 | 175-178 | a rule REPLACES text; prompts/skills don't grow by default | - | LOST
E15 | 179-181 | when a tool takes over a step, delete the prompt rule | - | LOST
E16 | 182-185 | each rule names its source; a rule stated by pointing at one item is a hack | - | LOST
E17 | 189-202 | rebuild after leak: drop case-by-case rule / grader wording | TVT | LOOSENED (=B21)
E18 | 206-233 | judge copy definition and parent-not-exempt | TVT 100-102 | CHANGED (=B22)
E19 | 235-265 | dangling references: when you detach/rename/replace a skill or tool, update every mention | - | LOST
E20 | 269-280 | never write target item specifics; naming a tool/skill is not a leak | TVT 97-99 | PRESENT
E21 | 282-285 | eval-freeze | wrong-eval 47 | PRESENT
E22 | 286-291 | no val/test, no tags=val/baseline | - | CHANGED | owner choice a
E23 | 292-293 | never set default_run_config_id | RX 217 | PRESENT
E24 | 294-302 | one crack; unbuildable -> record why | RX 119-120 | CHANGED | "fix the build or drop the idea"
E25 | 303-313 | discovery writes; read lessons first | MEM 74 | PRESENT
merging.md:
G01 | 10-17 | not diff-based; write the combined config by hand | RX 246-248 | LOST
G02 | 18-26 | layer the config; same-layer scrutiny; same nouns opposite modality = conflict | - | LOST
G03 | 31-35 | never combine two from one head-to-head group | - | LOST
G04 | 36-37 | merge provenance = baseline + every ingredient | - | LOST
G05 | 38-42 | reopened issues rebuilt, never replayed | - | LOST
G06 | 46-49 | ingredients' targeted evals first, on train | RX 247-248 | LOST
G07 | 53-59 | a merge need not land 100%; per-ingredient landed rows | - | LOST
G08 | 69-75 | culprit reading cheap; merge minus culprit = fresh experiment | RX 201 | PRESENT
skill-authoring.md (spec: not ported, separate decision):
K01 | 5-12 | flat via POST /skills; bundle via installer | levers/skill 40-51 | BRANCH
K02 | 34-59 | progressive disclosure: description indexes paths; body is a map; 6-8 topic files | techniques long-prompt-into-a-skill etc. | PRESENT (knowledge, not checked line by line)
K03 | 61-82 | lost-in-long: router must not narrate an order of operations | lost-in-long playbook | not verified
K04 | 102-105 | name rules | adding_skills 29+ | PRESENT
K05 | 107-119 | description contract: inline full path index, "No other resource paths exist" | adding_skills | not verified
K06 | 121-158 | clone/rewrite an inherited skill: export with files | levers/skill 45-51 | BRANCH | "keeps them is built when running HT"
K07 | 179-185 | install is atomic, immutable | levers/skill 61-62 | PRESENT
