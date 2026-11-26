# HT memory/SKILL.md (b49f159) -> Kiln references/knowledge/memory.md (25157f3)
Format: id | HT line | rule | port line | CLASS | note
M01 | 11 | memory = knowledge that outlives sessions, not working state | 8-11 | PRESENT
M02 | 13 | check first, record as you go, assume interruption | 13-15 | CONFLICT | "record as you go" is a write instruction (model 3)
M03 | 17 | HT sessions use gateway memory_* ops; endpoints are for other sessions | 17-18 | LOST | port says HT and others read and write the same records; no word that HT roles use gateway ops; breaks HT roles that are pointed here
M04 | 17 | records in assistant_memory/, API only; HT project tree not readable | 23-24 | PRESENT | HT tree fence dropped (N/A for MCP)
M05 | 19 | links are Claude-Code-side | - | N/A | repo layout note
M06 | 23 | save: overview<=280, scope required no default, content<=4000, tags | 28 | PRESENT | adds "no newlines" (true per memory_schema.one_line)
M07 | 24 | list: repeat tags = AND, newest first, truncation nudge has tag counts | 29 | PRESENT | truncation nudge detail lost (minor)
M08 | 25 | summary: omit scope = all scopes; counts + tag cardinalities + newest | 30 | PRESENT
M09 | 26 | get by ids; unknown ids omitted | 31 | LOST | "unknown ids omitted" (minor)
M10 | 27 | update: partial, null clears content, last-writer-wins | 32 | PRESENT
M11 | 28 | delete: hard, confirmed junk only | 33 | TIGHTENED | adds ask user first (fine)
M12 | 30 | scopes explicit every call; no-scope list returns every scope | 38-43 | PRESENT | gateway refusal N/A
M13 | 34 | orientation 1: summary; empty => seed constraint memories from the project's brief | 49-50 | CONFLICT | "record the constraints the user states" = write
M14 | 35 | project scope: constraint then lesson | 51 | PRESENT
M15 | 36 | task scope: baseline singleton; HT train-side loop agents skip this read | 52 | LOST | skip rule for HT train lanes gone; HT roles pointed at Orientation would read tags=baseline
M16 | 36 | val record read at orientation when you need the numbers; never on a train-side lane | 54-55,107 | CONFLICT | port forbids it "while you design or build" = tighter than HT interactive and than owner choice "a"
M17 | 36 | order issue(p0,p1), dead_end before plan, hypothesis, experiment overviews | 52-54 | PRESENT
M18 | 37 | content_length 0 consumed from listing; fetch rest by id in batches | 56-57 | PRESENT
M19 | 41 | one finding per memory; 422 string_too_long; split; long artifact = workspace file cited by path (does not outlive project) | 61-64 | PRESENT
M20 | 42 | overview front-loads verdict/number; example EXP 0715-w3-1; loop row frozen in experiment-analysis | 65-69 | CHANGED | example id EXP 0715-1 (no wave); pointer to the frozen format lost
M21 | 43 | content = observation+conditions+evidence; evidence level and source; ids as prose | 70-73 | PRESENT
M22 | 44 | check before writing; update, don't duplicate | 74-75 | PRESENT
M23 | 45 | correction = update + one-line note; delete only junk; ruled-out = dead_end | 76-79 | PRESENT
M24 | 46 | negative platform claims blocked; only probe-confirmed mitigation | 80-85 | PRESENT
M25 | 47 | failed write: disclose once in the return, summary, exempt from budgets | 86-87 | PRESENT | adapted to "tell the user once"
M26 | 48 | not memory-worthy list | 88-91 | PRESENT
M27 | 52 | memory_schema.py is the authority for what code reads; keep in step | - | LOST | port gives no pointer; its formats are hand-restated and differ (see M20,M33,M44,M54,M57,M58)
M28 | 54 | free-form snake_case tags; extend by evidence | 95-96 | PRESENT
M29 | 54,56 | val = ACCESS CLASS: marks what a record may not be shown to; boundary between train-visible state and val metrics must be queryable | - | LOST | the lane concept of owner model 2
M30 | 56 | faceted tags eval_<id>, rc_<id>; code reads ids from tags | 100,106,151 | PRESENT
M31 | 60 | issue = problem; human-blocked says what from whom | 100 | PRESENT
M32 | 60 | UNMEASURED: seeded per active eval by setup; measuring is a spend decision | 115-116 | PRESENT
M33 | 60 | UNMEASURABLE: eval gone OR left the active set; a status, never a decision, never a close; cause line | 116 | LOOSENED | "its evals are all gone" only; "never a close" and "left active set" lost
M34 | 60 | FIXED: prefix + content one-liner citing fix | 116-117 | PRESENT
M35 | 60 | WONT_FIX: deliberate or not reproduced, reason, cite which | 117-118 | PRESENT
M36 | 60 | reopen = strip prefix + "- reopened when promoting baseline rc_213. Issue repros on rc_213." | 118-120 | CHANGED | wording/format differs from code's IssueNote.reopened
M37 | 60 | one prefix at a time; never out of terminal state; HT writers refuse rather than overwrite | 120-121 | PRESENT | "ask the user"
M38 | 60 | priority tags never removed; priority is SOURCE-OWNED (spec.priority); a re-sync replaces the tag rather than an agent re-prioritizing | 109-112 | LOOSENED | port: "change one by an update"; source-owned lost
M39 | 60 | write issue when trace failure / user report / fix X breaks Y (file Y); dedup | 100 | PRESENT
M40 | 60 | query: p0 then p1; queries return resolved issues too (AND-only), skip by prefix at read time | 100 | LOST | resolved-issues note lost
M41 | 60 | one eval's issues: tags=issue&tags=eval_<id>; round end: human-blocked | 153 | PRESENT | round end N/A
M42 | 61 | hypothesis; cite issue ids | 101 | PRESENT
M43 | 62 | experiment any size; small n = direction never validation; opened before running; updatable forever | 102 | PRESENT
M44 | 62 | content fields; code lines rc:/change:/reused rc:; label "bundle cost" in loop, "spend" elsewhere | 102 | CHANGED | "what it cost"; both labels lost
M45 | 62 | RUNNING opening shape "EXP 0723-w4-2 (prompt): ... — RUNNING" | 130-131 | CHANGED | id EXP 0723-2
M46 | 62 | verdict replaces suffix, front-loaded numbers; loop row frozen elsewhere | 131-133 | PRESENT
M47 | 62 | FAILED (infra: <error_class>) retryable | 134 | PRESENT
M48 | 62 | ABANDONED (<why>) no verdict | 135 | PRESENT
M49 | 62 | NOT LANDED forms (k/n targets; discriminating block; stopped at n= by rule); untested not disproven; different build ok, SAME rc not | 140-141 | LOST | "same rc is not" and the forms lost (read-only kept)
M50 | 62 | CAPPED: inconclusive; rows kept; same rc with larger cap goes on | 142 | LOST | resume rule lost
M51 | 62 | PROMOTED <date> | 136 | PRESENT
M52 | 62 | HELD (constraint <id>) <date>; resubmit unchanged when answered | 143-144 | PRESENT | exact "HELD (constraint <id>) <MM-DD>" shape lost
M53 | 62 | REJECTED AT VAL <date>; never removed; never resubmitted unchanged; ingredient; same design re-enters as a new experiment | 137-139 | PRESENT | "never removed" lost
M54 | 62 | merge-eligible wins = verdicts since last promotion w/o PROMOTED; RUNNING from dead run = abandoned | 102,139 | PRESENT | merge-eligible definition lost (one-off N/A)
M55 | 63 | dead_end with conditions + experiment id; read before hypotheses | 103 | PRESENT
M56 | 64 | constraint; source/hardness/rationale | 104 | PRESENT
M57 | 64 | OPEN: content = question, default, source (human/assumption), re-ask condition (code: five key:value lines incl. gates) | 123-128 | CHANGED | no key names, no "gates"; a hand-written OPEN without a "question:" line never dedups in HT (OpenUnknownContent.parse)
M58 | 64 | OPEN write: mid-work question that can't be asked: default + OPEN + keep working | - | N/A | MCP agent can ask the user
M59 | 64 | OPEN records first; never ask what's answered | 127-128 | PRESENT
M60 | 65 | lesson | 105 | PRESENT
M61 | 66 | baseline singleton; tags baseline + rc_<id> (prefix to the id, never to a prefixed name); overview free; content chain one id/line; NO val metrics | 106 | PRESENT
M62 | 66 | baseline CREATED by HT setup pre-flight (default rc else most recently created; rule in provenance; zero rcs = fatal); updated only by promotion apply step (code); loop never sets default; newer user default never moves baseline | 106 | CONFLICT | port: the MCP agent creates it "at the first experiment" and moves it on keep
M63 | 66 | train-side loop agents never read baseline record | 106 | LOST | (HT)
M64 | 67 | val: numberless overview (exact constant); line "rc_213 (07-16, EXP 0716-w4-2) ← rc_207 — +9% mean win rate vs rc_207"; summary only; only val-metric memory | 107 | CHANGED | constant overview text lost; EXP id in line changed
M65 | 67 | val written by promotion apply step (code) after baseline; created at first promotion; a failed write is logged and skipped | 107 | CONFLICT | port tells the MCP agent to write it
M66 | 67 | val readers: promotion agent, report writer, human/interactive orientation; never train-side lane | 107 | TIGHTENED | port: only when confirming on val and reporting; vs owner choice "a"
M67 | 69 | screening records SCREEN SURVIVOR/DEAD END: formats; speed/cost survivor is a bound on a loss, never "quality held"; quality vs that run's baseline; latency orientation only; agents never write; older 6-line records | 144-145 | LOST | names only; the reading rules lost
M68 | 71 | generality: lines (code-written leak-check result) | - | LOST
M69 | 73 | reference check: lines (skill/tool named but not attached => failure may be build breakage) | - | LOST
M70 | 75-80 | priorities p0..p3 | 109-112 | PRESENT
M71 | 82 | who writes lifecycle: orchestrator CODE writes baseline/val/FIXED/WONT_FIX/reopen/OPEN/experiment suffixes; loop agents discovery writes only; setup owns derived-child writes; interactive sessions follow same formats by hand | 17-18 | CONFLICT | port makes the MCP agent the writer of all of it (run_an_experiment 47,68,75,186,211-217,229-233); HT "discovery writes only" lost
M72 | 86 | eval is the parent of an issue, not the spec | 149 | PRESENT
M73 | 88 | binding tag; content line "- eval: <id> (built <date>, reproduced)" | 151-152 | CHANGED | port line "- eval: <eval_id>"; HT planner/promote use the full line as a join fallback
M74 | 89 | one eval -> N issues; several bindings; UNMEASURABLE only when none active | 155-156 | PRESENT
M75 | 90 | must end up bound; eval building off by default; report tells owner; setup repairs mechanical cases; never guess | 157-159 | PRESENT | adapted to "tell the user"
M76 | 91 | two owners split by the exact delimiter; never edit above | 160-164 | PRESENT
M77 | 92 | no delimiter => entirely loop-owned; setup prepends head | 164 | PRESENT
M78 | 96 | provenance vs memory | 166-173 | PRESENT
