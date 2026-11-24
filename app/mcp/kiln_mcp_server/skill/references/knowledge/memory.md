---
name: memory
description: The project's durable memory - what belongs in it, the six Memory endpoints, scopes, what to read at the start of Kiln work, the write discipline, the tag vocabulary with who writes each kind, priorities, how issues bind to evals, and the files with the read-only formats that Kiln Harness Tuner writes. Read it before you read or write a memory.
---

# Memory

Memory is for **knowledge that outlives sessions**: problems worth solving,
things tried and learned, facts about this project's world. It is NOT for
working state — your context window (and session resume) holds the state of
*this* session; if a thing matters only until you finish, it doesn't belong
here.

This file is the reference for every agent. Kiln Harness Tuner's code
writes the format-critical records ("Who writes lifecycle state", below);
agents read them and never write them, and their formats are in the files
that "The formats that Kiln Harness Tuner writes" names.

The discipline (Anthropic memory-tool shape): **check memory first, record
as you go, assume interruption.** A finding that lives only in context dies
at compaction. Write at the moment of learning, never in an end-of-session
batch.

## The API — six REST endpoints on the running Kiln app

In a Kiln Harness Tuner agent session there is no generic Kiln REST tool:
use its gateway's memory operations, which apply the scopes and conventions
below for you; the endpoint table is for other sessions. Elsewhere, no
dedicated memory tool or server exists: call the endpoints with the
generic Kiln REST tool you drive Kiln with (`call_kiln_api`). Records live in the Kiln project's `assistant_memory/`
folder (human-readable `.kiln` files, concurrent-append safe) — reach them
through the API only; in a Kiln Harness Tuner session the project tree is
not readable. `{project_id}` = the Kiln project's id.

Each row names that endpoint's doc — parameters, body fields, response
shape. Read it before the first call.

| Operation | Call | Endpoint doc |
|---|---|---|
| save | `POST /api/projects/{project_id}/memories` — body: `overview` (req, ≤280), `scope` (req — no default), `content?` (≤4000), `tags?` | `references/knowledge/api_docs/post_api_projects_project_id_memories.md` |
| list | `GET /api/projects/{project_id}/memories` with `scope`, `tags`, `content_match` (a regex), `limit=50`, `offset=0` — repeat `tags` = AND; newest-first; truncation nudge includes tag counts | `references/knowledge/api_docs/get_api_projects_project_id_memories.md` |
| summary | `GET /api/projects/{project_id}/memories/summary` with `scope` — omit scope for all scopes; counts + tag cardinalities + newest, no content | `references/knowledge/api_docs/get_api_projects_project_id_memories_summary.md` |
| get | `GET /api/projects/{project_id}/memories/by_ids` with `ids` — full records; unknown ids omitted | `references/knowledge/api_docs/get_api_projects_project_id_memories_by_ids.md` |
| update | `PATCH /api/projects/{project_id}/memories/{memory_id}` — partial: omitted fields untouched; explicit null clears `content`; last-writer-wins | `references/knowledge/api_docs/patch_api_projects_project_id_memories_memory_id.md` |
| delete | `DELETE /api/projects/{project_id}/memories/{memory_id}` — hard delete, confirmed junk only. In a chat with a user, ask the user first (`SKILL.md`, "Working with the user") | `references/knowledge/api_docs/delete_api_projects_project_id_memories_memory_id.md` |

With `call_kiln_api`, a repeated parameter is a list:
`query_params={"scope": "project", "tags": ["lesson"]}`.

**Scopes** (explicit on every call, no defaults): `"project"` =
project-wide knowledge (constraints, lessons); `"task::<task_id>"` = work
on that task (issues, experiments, hypotheses, dead ends). Scope is an
opaque exact-match string — a convention, not a reference. ⚠️ **A list or
search with no `scope` returns every scope**, so an agent on one task can
read another task's experiments and lessons. Inside Kiln Harness Tuner
sessions the gateway refuses any memory list, search or write that does
not name `project` or the run's own `task::<id>`; outside Kiln Harness
Tuner, pass the scope yourself, every time.

## Orientation (session start, before assuming anything is unknown)

1. `summary` — counts by scope/tag = the shape of what's known. Empty ⇒
   first session: seed `constraint` memories from the project's brief
   (in a chat with a user: the restrictions the user states).
2. Project scope: list `constraint`, then `lesson`.
3. Task scope: read the singleton `baseline` record (`tags=baseline` — the
   authoritative current-baseline pointer: the rc id is the `rc_<id>` tag,
   and content is the promotion chain; ⚠️ Kiln Harness Tuner train-side
   loop agents skip this read — the orchestrator hands you the rc id; see
   the `baseline` row), and, when you need the numbers behind those
   promotions, the `val` record (`tags=val` — ⛔ never on a train-side
   lane; see the `val` row); then list `issue` (read `p0`/`p1` first),
   `dead_end` (before forming any plan), `hypothesis`, then recent
   `experiment` overviews (the accepted merge's experiment also names the
   baseline — kept as redundancy; the `baseline` record is what you
   trust).
4. Memories with `content_length: 0` are consumed from the listing alone —
   don't fetch. Fetch the rest by id, in batches, only where the overview
   says you need the body.

## Write discipline

These apply to every memory an agent writes; the kinds each agent may
write are in the tag table's "Write when".

- **One finding per memory.** The caps (280/4000) are the discipline — and
  both are **API-enforced at write time**, not advisory: the server answers
  422 (`string_too_long`) to any POST/PATCH past overview 280 or content
  4000. If it doesn't fit, it's almost always several findings — split it.
  A genuinely long-form artifact (analysis doc, comparison) is a workspace
  file, cited by path from a memory — noting workspace files don't outlive
  the project.
- **`overview` is a load-decision signal, not a title.** Front-load the
  verdict/number so a future reader can decide without fetching:
  `"EXP 0715-w3-1 (prompt): no-refetch rule — accuracy: +12pp, base=64, cand=76, n=40, p=.01"`,
  never `"Experiment 7 results"`. If the overview says everything, leave
  `content` null. (Inside the Kiln Harness Tuner loop the measurement row
  after the ` — ` has an exact frozen shape with **one owner** — the
  "Frozen format" block of Kiln Harness Tuner's experiment-analysis skill.
  Examples here illustrate front-loading, never that format; go read it
  rather than copying one of these.)
- **Content = observation + conditions + evidence.** "Batch API 429'd at
  50rps on 07-04 (n=2 runs, staging)" — never universal rules, never
  platitudes. State evidence level and source (human-stated vs inferred,
  n, what wasn't controlled) as prose. Cite Kiln records as prose ids
  ("run_config 424242901234").
- **Check before writing:** list the relevant tag first — if a memory on
  this finding exists, update it, don't duplicate.
- **Corrections = update the memory** with the new understanding, appending
  a one-line correction note in content ("corrected 07-14: was attributed
  to prompt rule, actually the judge swap"). Newer wins; keep history
  honest inside the record. Delete only confirmed junk — a *ruled-out
  approach* is not junk, it's a `dead_end`.
- **Negative platform claims are BLOCKED — never stored.** "X doesn't work
  / isn't stored / is ignored / the API drops Y" is almost always temporary
  (a bug, an outage, a stale build, a wrong diagnosis) and unfit for
  forever-memory — do not store it at all, not even hedged as a `lesson`.
  The one adjacent allowed form is **mitigation-shaped and confirmed by a
  quick check**: "if X is flaky, try Y to mitigate" — stored only after you
  actually checked that Y works, citing the quick check, and still used
  sparingly (temp information in permanent storage). Example — blocked:
  "memory PATCH drops the content field"; allowed (after a quick check):
  "if a memory PATCH seems to drop content, re-send with an explicit
  content key — checked 07-30, second write landed".
- **If a memory write fails, disclose it in your return** — record the
  failure and the intended content in the prose field your role hands back
  (`findings` / `build_notes` / `rejected_summary` / your report), so the
  finding survives in the run record even though the store never got it.
  Do not memory-store the failure itself (that would be a negative platform
  claim — see above); retry the write, and if it keeps failing the
  disclosure is the record. A disclosure rides **once** — the return where
  the failure happened — as a summary (the finding's gist + what the full
  content was for), not the verbatim 4,000-char body, and it is **exempt
  from any length budget on that field** (e.g. the planner's ~1,200-char
  `rejected_summary` budget); later waves never re-carry it. In a chat with
  a user: tell the user the finding once.
- **Not memory-worthy:** session working state (context/resume covers it)
  · per-trace annotations (Kiln feedback model, child of the trace) ·
  why-an-artifact-was-created (its frozen `provenance`, written once at
  creation) · generalizable craft that is true beyond this project (put it
  in a skill instead) · anything restating what an artifact/eval already
  records.

## Tags — seed vocabulary (8 + priorities)

> **Code reference.** Inside the Kiln Harness Tuner loop, every convention
> in this section and the two below — the kind tags, the issue prefixes,
> the experiment suffixes, the `key: value` content lines code reads back,
> the issue head and tail layout, the five open-unknown lines — is typed in
> Kiln Harness Tuner's `memory_schema.py` (`RecordKind`, `IssueState`,
> `ExperimentState`, one view per kind). That module is the authoritative
> list of what CODE reads from a record; this file and the format files it
> names stay the authoritative guide for what an AGENT writes and reads.

Free-form beyond this seed, snake_case, never a closed enum. Governance:
if real usage keeps awkwardly cramming a recurring kind of finding into
these eight, that observed usage is the evidence for adding a tag — extend
by evidence, not speculation. (`baseline` earned its row this way: the
singleton needs a direct query key — orientation fetches it by tag, no
list-and-scan. `val` earned its own by being an **access class** rather
than a topic: the boundary between train-visible state and val metrics has
to be queryable, and a substring of an overview is not.)

Two shapes appear here beyond the plain topic tag. **Faceted tags** carry
an id — `eval_<eval_id>` on an `issue`, `rc_<rc_id>` on the `baseline`
record: they are the structured slot a memory record otherwise lacks, and
code reads ids from them rather than parsing prose. **Access-class tags** —
today just `val` — mark what a record may not be shown to; see the `val`
row.

| Tag | What it is | Write when | Query when |
|---|---|---|---|
| `issue` | A problem worth solving — needs no solution idea to be recorded. Includes problems blocked on a human (state what's needed from whom in content). **An eval-derived issue is a derived child of that eval**, bound by an `eval_<eval_id>` tag; an issue filed before any eval measures it is bound later, when one is built — see "Issues are derived children of evals" below. **Lifecycle = overview prefixes, update-based — no state tags**: open is the default (a priority tag, nothing more); the prefixes `UNMEASURED: `, `UNMEASURABLE: `, `FIXED: ` and `WONT_FIX: ` and the reopen line are in `references/knowledge/memory_formats/issue_records.md`. Reopened = strip the prefix + append the provenance line — never a duplicate memory. One prefix at a time: setting a new one strips the old — but **never out of a terminal state**: `FIXED:`/`WONT_FIX:` are the loop's own decisions and it does not un-close them (a human re-opens by stripping the prefix and appending the provenance line). The Kiln Harness Tuner writers refuse rather than overwrite. Priority tags are **never removed**, even on close — the severity record stays, and priority is **source-owned** (from `spec.priority` where a Spec exists), so a re-sync replaces the tag rather than an agent re-prioritizing. | Trace analysis finds a failure mode; the user reports a problem in chat; an iteration fixes X but regresses Y (keep the config, file the regression). Dedup at ingestion: list existing `issue` memories first, update a match. Agents never set or strip a prefix and never reopen an issue; in a chat with a user, tell the user what you found. | Session start and target-picking: `tags=issue&tags=p0`, then `p1` — queries return resolved issues too (AND-only API can't exclude); skip by overview prefix at read time. One eval's issues: `tags=issue&tags=eval_<eval_id>`. Round end: surface human-blocked issues. |
| `hypothesis` | A candidate change/approach not yet run — including ideas for later. Cite the issue ids it addresses in content. | No agent writes one: Kiln Harness Tuner's code records each hypothesis in its experiment record (`references/knowledge/memory_formats/experiment_records.md`). In a chat with a user, tell the user an idea that you do not act on now. | Choosing the next experiment; before inventing a plan that may already exist. |
| `experiment` | One thing tried + outcome — any size, from full eval-gated runs to quick n=3 checks (state evidence level; small n gives direction, never validation). Opened before running (hypothesis + prediction), updated with the verdict; updatable forever as interpretation evolves. Its content fields, overview state suffixes and val stamps: `references/knowledge/memory_formats/experiment_records.md`. | Kiln Harness Tuner's code, when something is about to run with a predicted effect, and again at verdict. In a chat with a user, write none: a one-off's lasting results are a `lesson`, a `dead_end` or an `issue`. | "What's been tried?"; merge-eligible wins = verdicts since the last promotion without `— PROMOTED` (a `— REJECTED AT VAL` one is an ingredient only — never re-submitted unchanged); a `— RUNNING` overview from a dead run means abandoned work, not a result. |
| `dead_end` | An approach ruled out — don't retry (with the conditions under which it's dead, citing the experiment id; in a chat with a user, where no experiment record is written, the run config ids that showed it). | A lever is exhausted or an approach refuted. | BEFORE forming hypotheses — this is the map that stops re-exploration. |
| `constraint` | A requirement, preference, or committed decision binding our work — from the task owner ("OpenAI models only"), the world, or our own choices ("optimize cost before quality — agreed 07-04"). Source, hardness, and rationale in content. **Open unknowns are `constraint` memories with an `"OPEN: "` overview prefix** — `"OPEN: unknown if API docs exist for the graphql endpoint"`; content: the verbatim question, the default assumed, source (`human` vs `assumption` — assumptions promote on confirmation), and a re-ask condition (`references/knowledge/memory_formats/open_questions.md`). Answered = update in place: strip the prefix, append answer + source + date — never a duplicate. | Someone states a requirement; a binding choice is made; a question arises mid-work that can't be asked now — apply a default, record the `OPEN:` unknown, keep working. In a chat with a user: record the restrictions the user states; ask the user rather than record an `OPEN:` unknown, and never edit an `OPEN:` record. In the rare case that the user answers one in the chat, you may record the answer as a `constraint` that cites the `OPEN:` record's id. | Session start, and before designing any candidate. Kickoff/frontload: `OPEN:` records first — they are pre-generated question candidates; never ask what's already answered. |
| `lesson` | Something learned about this project's world or how to work in it effectively: API/data/infra behavior and quirks, effective procedures ("judge batches >200 items flake — chunk to 100"). Concrete observations only. | You learn something the next session would otherwise rediscover the hard way. | Session start (project scope); before touching the part of the world it describes. |
| `baseline` | **The singleton task-scope record naming the current baseline run-config** — the authoritative pointer session startup reads. The rc id is its faceted tag `rc_<rc_id>`; read the id from there, never from prose. **It carries NO val metrics.** Its format: `references/knowledge/memory_formats/baseline_and_val_records.md`. | Kiln Harness Tuner's code only: created by its setup phase on a cold task, then updated by the promotion apply step (the format file says how it is seeded). | Orientation: fetch directly via `tags=baseline`. ⚠️ Kiln Harness Tuner train-side loop agents (batch planner, rc-build, analyzer, eval-build) **never read it** — the orchestrator hands them the rc id, so the read buys nothing, and it sits beside the `val` record in the same task scope. |
| `val` | **The singleton task-scope validation-stats record** — the val summary of every baseline promotion. `val` is an **access class**, not the record's name: the rule it exists to support is "the train lane never fetches `tags=val`", and it generalizes to any future val-grade record. Summary numbers only, **never item/trace-level val detail**. This is the **only** memory allowed to carry val-split metrics (Kiln Harness Tuner split guarantees). Its format: `references/knowledge/memory_formats/baseline_and_val_records.md`. | Kiln Harness Tuner's code only: the promotion apply step, right after the `baseline` write. | The promotion agent, the report writer at exit, and human/interactive orientation. ⛔ **Never on a train-side lane** — this record IS val metrics, so a read is the leak the split guarantees exist to prevent. Nothing in it goes into a change (`references/knowledge/train_val_test.md`). |

**Screening records (Kiln Harness Tuner).** Code records every screened
candidate's result in task scope with the `screen` tag, so a later run
starts from it: a survivor is a `lesson`, a dead end a `dead_end`. Agents
read these records and never write them. Their formats, and those of the
quick-check (`PROBE`) records:
`references/knowledge/memory_formats/screening_and_probe_records.md`.

**Generality and reference-check lines (Kiln Harness Tuner).** An
experiment record may carry a code-written `generality:` line and a
`reference check:` line (`references/knowledge/memory_formats/experiment_records.md`).

**Priorities** — composable tags, primarily on `issue`; re-prioritize via
update, never a duplicate memory:

- `p0` — blocks the project goal or causes user-visible harm; work it now.
- `p1` — material win on the agreed metrics (quality/cost/latency); the
  default queue.
- `p2` — real but minor; picked up when nothing above it remains.
- `p3` — tracked so it isn't lost (often: someone asked us to note it); no
  intent to work it in this project — revisit only if asked or it becomes
  trivial in passing.

**Who writes lifecycle state (Kiln Harness Tuner loop runs):** the
format-critical writes above — the `baseline` and `val` records,
`FIXED:`/`WONT_FIX:`/reopen prefixes, `OPEN:` records, experiment
open/verdict/state suffixes — are performed by the orchestrator **code**
from structured agent returns (the formats are frozen in code, in its
`memory_schema.py`); loop agents make discovery writes only (`lesson` /
`dead_end` / new `issue`, at the moment of learning). The Kiln Harness
Tuner **setup phase** (a pre-flight step of the same code) owns the
derived-child writes: seeding the `baseline` record on a cold task,
seeding and re-syncing eval-derived `issue` records, the `eval_<id>`
binding tag, `UNMEASURABLE:` flags, and — from a `measure_issue_baseline`
batch item — clearing `UNMEASURED:` or setting `WONT_FIX:`. In a chat with a
user there is no orchestrator, and these records stay read-only: you make
the same discovery writes, plus a `constraint` for a restriction the user
states.

## The formats that Kiln Harness Tuner writes

Read-only: each file gives the strings that its code writes, and what each
means for a reader. Read the file before you read a record of its kind.

| Records | File |
|---|---|
| `experiment` records: the id, the opening and verdict overviews, the content fields, the state suffixes, the val stamps and lines, the content lines code reads back | `references/knowledge/memory_formats/experiment_records.md` |
| `issue` records: the state prefixes, the setup head and the delimiter line, the appended lines, the smell and audit tags | `references/knowledge/memory_formats/issue_records.md` |
| `OPEN: ` records: the open questions and their five content lines | `references/knowledge/memory_formats/open_questions.md` |
| The `baseline` and `val` records, and how the baseline is seeded | `references/knowledge/memory_formats/baseline_and_val_records.md` |
| `SCREEN` and `PROBE` records: the screenings and the quick checks | `references/knowledge/memory_formats/screening_and_probe_records.md` |

## Issues are derived children of evals

**The eval is the parent.** Not the Spec: not every eval has one, and where
a Spec does exist it is optional enrichment (usually the best
human-authored description), never the key. An `issue` memory is the
*derived child* — the planner-readable statement of the problem an eval
measures — so the two never drift into independently-edited twins.

- **Binding = the tag `eval_<eval_id>`** (e.g. `eval_424242966189`) —
  snake_case, no separator characters. Not the content line:
  `- eval: <id> (built <date>, reproduced)` stays as the human-readable
  record, but the tag is what machines read. Both directions are one call:
  *does this eval have an issue?* → `tags=issue&tags=eval_<id>`; *do all
  evals have issues?* → one `tags=issue` listing, set-difference the
  binding tags against the eval list.
- **Cardinality is one eval → N issues.** Setup seeds one per active eval;
  the loop adds more as it discovers sub-mechanisms of the same criterion.
  An issue MAY carry several bindings (a problem found on eval X that later
  gets a purpose-built narrower eval Y) — it is only `UNMEASURABLE:` when
  *none* of its bindings is active.
- **An issue must *end up* bound** — tag it when an eval already measures
  it. When none does, the eval is missing. Eval building is experimental
  and off by default: only when a run turns it on does the loop's
  `eval_only` item build the eval and bind the issue via `link_eval`. While
  it is off, the issue stays unbound, and the run's report tells the owner
  to create its eval in the Kiln app. Setup repairs the mechanical cases
  (exactly one eval id in the content, and that eval exists) and reports
  the rest. It never guesses a binding. In a chat with a user: tell the
  user that the eval is missing, and build it only when the user agrees
  (`references/knowledge/create_spec.md`).
- **Kiln Harness Tuner's smell and audit issues are bound to no eval on
  purpose** (the tags `smell`, `baseline_audit`, `baseline_judge_copy`).
  Do not bind them, and do not report a missing eval for them.
- **Content has two owners, split by one delimiter line**
  (`references/knowledge/memory_formats/issue_records.md`). Above it, setup
  owns the head and replaces it when the eval changes; the delimiter and
  everything below are loop-owned and append-only. **Never edit above the
  delimiter by hand** — the next sync overwrites it; findings and history
  go below.
- A record with **no delimiter** (legacy, or written by an agent) is
  treated as entirely loop-owned: setup prepends its head and touches
  nothing else.

## Division of labor with artifact provenance (never write the same fact twice)

Facts about one artifact, known at its creation (why it exists, what it
derives from, whose judgment) → the artifact's `provenance`, stamped at
creation, **immutable, written once**. Everything that *evolves* or spans
artifacts → memory. The pipeline: an `experiment` memory records the trial
and its evolving interpretation → `dead_end`/`lesson` distill what it
taught → `constraint` records what we committed to because of it. Memories
cite artifact ids as prose; artifacts never point at memories.
