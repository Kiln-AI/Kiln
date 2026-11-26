# experiment-costing (264) -> RX "Cost before you spend" (87-96). Spec: "not ported", part 5 takes "read the recorded usage, never scale a list price"
C01 | 8-9 | never run/propose spend without a pre-run estimate covering ALL SIX lanes | RX 89-96 | LOOSENED | three model lanes only
C02 | 13-25 | three error classes (unpriced lane; cancelling errors; "unmeasurable" lane) | - | LOST
C03 | 29-36 | cost is a function of its conditions; record a measured value with its conditions | - | LOST
C04 | 40-56 | drives formula; cached term dominates; cache hit is a provider property; cost linear in LLM calls; fingerprint change re-pays | RX 89-90 | PRESENT | partial ("misses cached tokens")
C05 | 57-61 | never scale across models by list-price ratio; smoke on the target model+config+corpus | RX 89 | PRESENT
C06 | 62-64 | read the smoke's recorded usage before green-lighting | RX 91-93 | PRESENT
C07 | 65-68 | budget by scenario class, not mean x N (top decile 1/4-1/3) | - | LOST
C08 | 69-88 | synthetic-user lane measurable; None on reuse correct; no endpoint aggregates; last SU call discarded | RX 92-93 | PRESENT | details lost
C09 | 89-115 | judge lane paid again on every re-score; deterministic; trace size sets price; never quote per-judgment figure without its judge model | RX 92 | LOST | re-score rule lost
C10 | 116-122 | THIRD-PARTY infra: live calls to someone else's server need the operator's agreement per batch; writes need separate agreement; state $0 lane explicitly | - | LOST
C11 | 123-128 | provider quotas/keys: confirm headroom; which provider each config routes through | - | LOST
C12 | 129-139 | the replicate is a cost lane; a claim of improvement budgets one replicate or says it has no error bar | - | LOST | (noise playbook may cover in part)
C13 | 143-166 | prices from a live lookup; median/proxy rules; $0 = free tier; null price; local provider has no per-token price; measured task price wins | model_work | PRESENT | partial; "$0 is a free tier" lost
C14 | 169-173 | custom-score metric eval over stored traces re-scores at $0 | - | LOST
C15 | 182-190 | recorded cost != invoice; quote both; reconcile | - | LOST
C16 | 191-194 | item counts per eval from filters; prior values only with their configuration | RX 93-94 | PRESENT
C17 | 196-206 | what is free; a clone misses trace reuse (full fresh sweep) | - | LOST
C18 | 208-230 | screening and arm pricing | - | N/A | HT engine
C19 | 234-238 | estimate before, actuals after (recorded and invoice) | RX 94 | LOOSENED | estimate only
C20 | 239-242 | design changes carry cost multipliers | - | LOST
C21 | 243-246 | human gate: over threshold, OR >100 judged items, OR any quota raise; third-party batch -> operator | RX 94-95 | LOOSENED | spend limit only
C22 | 247-259 | cost levers: cheap judges gated on an agreement experiment; judge caching ~0 | - | LOST

# planner entry file (kiln-harness-tuner-knowledge/references/planner.md) -> improving_agents/index.md (+ RX "Next")
N01 | 3-6 | documents are ideas; clear measurement outranks | index 8-36 | PRESENT
N02 | 10-12 | read every `order` playbook before planning | index 88-89; improve_task 136 | PRESENT
N03 | 13-16 | read the smells of the present baseline; a smell that blocks other work comes first | - | LOST
N04 | 17-22 | playbook: steps in order, each with a condition; order is the default priority, change on evidence; skip a step whose condition fails; start at the first that holds; next steps may run in parallel | - | LOST
N05 | 23-32 | outcome of a step: Landed -> next step only if the issue is still open; Refuted -> next; Capped -> rerun larger cap; Inconclusive -> not refuted, step stays open, next can run in parallel | RX 221-222 | LOOSENED | "goes back to its playbook" only
N06 | 33-37 | reach a technique through a playbook/smell; technique-index only when named | index 51-54 | PRESENT
N07 | 38-42 | own idea when documents do not fit; write "not in the knowledge" in the hypothesis | index 26-31 | PRESENT | "not in the knowledge" marker lost (report rule uses it)
N08 | 44-46 | technique field = lever id | - | N/A
N09 | 48-50 | applies-to shapes | index 56-58 | PRESENT

# code-tool-authoring (260) + wrappers/ (README + 8 .py) -> code_tool_authoring.md + code_tool_wrappers/*.md
T01 | 8-12 | experiment lever on ONE new rc | 8-16 | PRESENT
T02 | 14-24 | mechanical vs behavioural; directive in the tool's description | 18-29 | PRESENT
T03 | 26-57 | four families; tool_config overlap; new description = new tool | 31-56 | PRESENT
T04 | 59-87 | templates first for mechanical failures; table; three edits | 58-83 | PRESENT
T05 | 89-101 | THE hard rule: allowlist only subject tools; never call_kiln_api; any tool kind except skills; depth 10 | 103-114, 137 | PRESENT | no longer labelled the hard rule here (levers/new_tool keeps it as a hard limit)
T06 | 105-108 | trust: gateway op, per server process; not_trusted check | 156-158 | CHANGED | MCP: ask the user first; HT roles (never ask a human) get no word that HT has its own trust op
T07 | 110-141 | contract (64KB, run(), schema match, nested calls, accepted/refused ids, unique names, caps, envelope, timeout, description for the model) | 116-141 | PRESENT
T08 | 143-153 | operations | 143-154 | PRESENT | as endpoint docs
T09 | 157-163 | additive; never archive/PATCH a tool another rc uses; replace => drop old id | 162-167 | PRESENT
T10 | 164-167 | fresh function name; duplicates of non-archived names rejected (400) | 168-172 | CHANGED | documented deviation (Kiln checks per allowlist/run config)
T11 | 168-170 | clone and modify; stamp rc provenance | 173-176 | PRESENT
T12 | 171-177 | dry-run reads only; read tool_call_log | 177-185 | PRESENT | adds local stub test (spec row 11)
T13 | 178-182 | a tool nobody is told about goes unused | 186-190 | PRESENT
T14 | 184-254 | worked example (payload + module) | 195-230 | PRESENT | module moved to the wrapper file
W01 | README 3-15 | each template tested against a kiln.tools stub (success/error/raise/coercion) | 177-179 | CHANGED | port test only compiles; agent may run a stub itself
W02 | README 28-50 | rules for all templates | 85-101, 162-185 | PRESENT
W03 | *.py | module code of all 8 templates | code_tool_wrappers/*.md | PRESENT | byte-identical code; docstrings of actionable_errors, context_on_tool_surface, readonly_guard reworded (documented)

# kiln-task-setup (60). Spec: not ported, separate decision
S01 | 15 | verify the (model, provider) pair; supports_function_calling for tool tasks | model_create_configs 52-55 | PRESENT | function-calling check not verified
S02 | 19-33 | endpoint table, run_config_properties, tool id forms | model_create_configs, tools, api_docs | PRESENT
S03 | 37 | multiturn tasks need null schemas; schema immutable | create_task | not verified
S04 | 39 | skill references/* have NO API: write them to disk (HT: installer) | levers/skill 40-51; working_with_project_files 43-49 | BRANCH | port forbids the disk write and defers bundles to HT
S05 | 45 | turn_mode frozen | - | LOST | minor
S06 | 46 | PATCH run_configs silently drops properties | improve_task 45 | PRESENT
S07 | 47 | call_kiln_api hidden from UI pickers | - | LOST | minor
S08 | 48 | name traps | model_create_configs 78 | PRESENT
S09 | 49 | batch-creating 3+ rcs: code tool wrapper | model_work 45 | CHANGED | ask before 3+
S10 | 51-56 | verification checklist (every tool fires in a trace; skill loads before dependent calls) | RX 113-120 | PRESENT

# kiln-api (117 + generated docs) -> SKILL.md "Calling the Kiln API" + references/knowledge/api_docs (own pipeline)
I01 | 27-30 | HT loop agents have no call_kiln_api (gateway) | - | N/A for MCP; HT roles pointed at SKILL.md need to be told
I02 | 32-46 | query_params never "?"; HTML body = path never reached the API | SKILL.md 37 | PRESENT | HTML-body tell lost (minor)
I03 | 48-60 | read the endpoint doc before calling | SKILL.md 34 | PRESENT
I04 | 92-102 | jq_filter rules | SKILL.md 39 | PRESENT
I05 | 104-117 | diagnose before retry; cite the doc line; never abandon the tool for a shell | SKILL.md 39 | PRESENT | shell clause lost (minor)

# gateway (353) -> not ported (operations -> api_docs). Train-only answers, role table, traces are files: N/A to MCP (HT code). The train fence is what owner model 2 replaces with a soft rule.
# probe (113) -> "a quick check" (named in 14 knowledge files, never defined)
Q01 | 13-18 | a probe answers one yes/no mechanism question before an arm | knowledge mentions | PRESENT (concept)
Q02 | 41-49 | fork ONE change; name it "PROBE <id>: <what>" so nobody forks or measures it; provenance; never edit parent | - | LOST
Q03 | 50-56 | drive at most max_drives (<=6, default 3) TRAIN items | - | LOST
Q04 | 64-70 | keep model/provider/thinking/sampling; no speed or cost question | - | LOST
Q05 | 79-80 | for a parameter/mode question drive the parent on the same items too | - | LOST
Q06 | 81-84 | decision: 2 of 3 yes, 0 of 3 no, 1 of 3 unclear unless "ever" | - | LOST
Q07 | 94-97 | discovery writes only after listing | MEM | PRESENT
Q08 | 103-105 | a probe that needs an hour is an experiment | - | LOST
# baseline-review (126) -> diagnose_an_agent "What the smells measure" + smell docs
R01 | 14-23 | a smell is a design issue, not a failure reason; state facts, no fix | index 41 | PRESENT
R02 | 64-70 | read sampled traces chosen by order, not by score; do not judge answers | - | LOST | minor for MCP
R03 | 71-77 | check each detection: holds / not / null | - | N/A (no code detector)
R04 | 78-92 | apply "How to recognise/confirm"; a smell with no evidence is not returned | smell docs | PRESENT
R05 | 98-112 | train only; no writes; no plan | diagnose 10-11 | PRESENT
# report (329) -> RX "Record and report" 235-238, improve_task "Reporting" 77-82
X01 | 172-176 | banner: numbers are train-side attribution or val-grade; test is the owner's; loop never reads test | RX 235-238 | PRESENT | split per number
X02 | 238-252 | speed/cost: "lost k of n ... no loss rate above X%", never "quality held"; a promotion is "no clear loss", never "no loss" | RX 177 | LOST | port only forbids "no regressions" for unmeasured evals
X03 | 266-270 | label every number val-grade or train attribution; never as shipped/test truth | RX 237 | PRESENT
X04 | 271-284 | source every claim; no inferred composition; no unsourced quantifiers; say when the books don't explain a number | - | LOST
X05 | 295-316 | this run vs cumulative counts; holes vs infra vs eval-job errors | - | N/A (run report)
X06 | 320-322 | report honestly: failures, holes, abandoned items | - | LOST | minor
X07 | 256-262 | next steps incl. changes marked "not in the knowledge" | - | LOST | depends on N07
