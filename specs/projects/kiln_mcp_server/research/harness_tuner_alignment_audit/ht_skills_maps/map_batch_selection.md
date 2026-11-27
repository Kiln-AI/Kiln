# HT kiln-harness-tuner-batch-selection/SKILL.md (1167 lines) -> run_an_experiment.md, memory.md, knowledge playbooks
RX = references/knowledge/run_an_experiment.md ; MEM = memory.md ; TVT = train_val_test.md
B01 | 43 | never query tags=val on the planner lane | MEM 107 | CHANGED | owner choice "a" lets narrow read it; port forbids "while you design" (see memory M16)
B02 | 46 | never read the baseline record (defence in depth) | MEM 52 | N/A | MCP has no orchestrator; HT lane rule lost for HT (memory M63)
B03 | 53 | never ask for val/test results; enforced by gateway | RX 165-179 | CHANGED | one MCP agent runs and reads val summaries (owner choice "a")
B04 | 57 | never ask a human; open_questions | - | N/A | chat agent asks the user
B05 | 59 | levers exclude fine-tuning AND GEPA-style prompt optimizers unless guidance names one | levers/model.md 89 | LOST | fine-tune kept; prompt-optimizer exclusion absent (Kiln has a prompt_optimization API)
B06 | 64 | model swap is a lever only when allowed list has another model; guidance can forbid | RX 66-67; levers/model | PRESENT
B07 | 76 | plans are working state; discovery writes only; orchestrator writes OPEN | MEM | CONFLICT | port has the agent write OPEN/experiment/baseline (model 3)
B08 | 80 | no new eval unless eval_building | RX 59-61 | CHANGED | user agrees
B09 | 103-107 | latency = per-item total_llm_latency_ms, never tokens/s | model_work 29 | PRESENT | partly
B10 | 117-130 | exact speed/cost win rule (paired sign test, median ratio<1, no sig p90 regression, <2/3 pairs = incomplete; quality: nothing down sig., pooled net>=0 weighted p0=4..p3=1,none=1, no eval down > max(1,round(0.10*items)); best qualifying wins, tie by pooled net) | RX 194-198 | BRANCH | "that exact rule applies when running it"
B11 | 131-147 | measurement engine, chunks, stops | - | N/A | HT code
B12 | 148-152 | an arm that trades any quality is wasted | cheaper-or-faster | PRESENT
B13 | 153-155 | efficiency lever order | cheaper-or-faster | PRESENT
B14 | 156-157 | guard evals matter more under speed/cost | - | LOST
B15 | 158-169 | speed/cost survivor = bound on a loss, never "quality held"; fixes are noise level; swap needs >=24 baseline passes; few hundred items cannot rule out a few points | - | LOST
B16 | 173-334 | screening rounds, stop rules, settled survivors, prices | cheaper-or-faster 20 | BRANCH | HT tool; "applies when running it"
B17 | 179-189 | output mode on a model change; tool/skill + function_calling refusal | levers/model, output_mode | PRESENT
B18 | 325 | thinking levels only from provider list | levers/params 46 | PRESENT
B19 | 336-352 | read order of memory before planning | MEM 45-57 | PRESENT
B20 | 354-365 | read failing traces, name decision point | diagnose 88-107 | PRESENT
B21 | 367-379 | generality: no train entity/id/expected answer, NO CASE-BY-CASE RULE, NO WORDING AIMED AT A GRADER; naming a tool/skill fine | TVT 97-104 | LOOSENED | case-by-case + grader-aimed wording missing
B22 | 388-401 | judge copy = run of 8 words or eval's full name; baseline prompt/task instructions exempt; parent NOT exempt | TVT 100-102 | CHANGED | "no passage", no exemption, parent rule lost
B23 | 403-417 | gate blocks ("- blocked at the val gate" line) | - | LOST | reading the line
B24 | 418-424 | two scopes only; another task's records are other evidence | MEM 38-43 | PRESENT
B25 | 426-436 | all of the baseline is in the action space; inherited skill/tool failure -> change THAT | levers, playbooks | PRESENT
B26 | 437-443 | only config failures get arms; eval-data/judge -> report; env/noise nothing until recur | wrong-eval 29-35 | PRESENT
B27 | 445-462 | expected outputs are the owner's policy: an unstated rule they follow is a CONFIG failure; eval data only on contradiction | - | LOST
B28 | 464-485 | failure class before lever; decision point -> surface; tool text over prompt line; mechanical -> wrapper first | playbooks, code_tool_authoring 20-29 | PRESENT
B29 | 487-495 | two failed text arms -> change surface class | change-the-surface playbook | PRESENT
B30 | 497-505 | >=2x candidates, wildcard | - | N/A | loop
B31 | 507-523 | probes before arms; count vs read | "quick check" in 14 knowledge files | LOST | no file defines a quick check
B32 | 525-560 | fix arm types; params identical; thinking ladder; model lever only when allowed | levers/techniques | PRESENT
B33 | 572-603 | UNMEASURED triage | MEM 115 | N/A | HT setup
B34 | 605-638 | a smell is evidence; reference is a default; an experiment decides | smells | PRESENT
B35 | 647-653 | the cheapest arm is a probe, not a question | - | LOST
B36 | 655-666 | eval economics, anti-starvation | - | N/A | eval building
B37 | 668-687 | detectability: n measured not nominal; missing != 0; judgment never a formula; moves = predict larger and say why / other target / grow eval | RX 82-85 | CHANGED | port: "fix the measurement first"
B38 | 689-705 | floor per score (room, floor 6, room 0 -> guard; room<floor nominal only) | saturated playbook 15-24 | BRANCH | "Kiln Harness Tuner measures it"; computable by hand
B39 | 707-711 | cap prediction at headroom | RX 80-82 | PRESENT
B40 | 711-716 | no baseline rows -> conditional fraction; never carry a magnitude from another task | - | LOST
B41 | 718-732 | mergeable batch; mutually exclusive -> sequence; head-to-head groups | RX 246-248 | LOST | exclusivity rule lost
B42 | 735-755 | build-cost order; price on THIS task | spending-the-budget 28-35 | PRESENT
B43 | 757-786 | assemble, wildcard, deferral | - | N/A
B44 | 790-805 | EXP <MMDD>-w<k>-<n> id | MEM 66,131 | CHANGED | EXP <MMDD>-<n>
B45 | 796-813 | lean-target default: target + stated couplings; guards default to the val gate; model swap -> every eval | RX 144 | CONFLICT | port measures guard evals on train whenever the target moved; saturated playbook 33-37 says the opposite
B46 | 821-835 | target items; NOT LANDED = build missed; never resubmit same rc | RX 78 | LOST | second half
B47 | 836-878 | discriminating block, futility | - | N/A | HT engine (should say so plainly)
B48 | 879-900 | per-candidate spending cap with reason | RX 94-95 | LOST | only one overall limit
B49 | 901-918 | hypothesis + predicted effect required; unpredicted = exploration | RX 75-85 | PRESENT
B50 | 919-938 | fork of a REJECTED AT VAL rc only for a different change, rationale line | MEM 137-139 | PRESENT
B51 | 957-967 | never rebuild a duplicate rc to re-run evals | RX 135-136 | PRESENT
B52 | 998-1000 | no probe answers speed or cost | - | LOST
B53 | 1007-1029 | reuse a built rc; HELD resubmit | MEM 143 | PRESENT
B54 | 1032-1039 | merge rc from content; truncated -> leave out, never guess | - | N/A | loop merges
B55 | 1041-1069 | val rejection reasons and reading | rejected-at-val playbook | PRESENT
B56 | 1071-1107 | merge timing, wrap-up | - | N/A
B57 | 1109-1163 | plan return fields; record reading RUNNING/FAILED/ABANDONED | MEM 134-139 | PRESENT
