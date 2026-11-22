---
name: memory
description: The project's durable memory - what belongs in it, the six Memory endpoints, scopes, what to read at the start of Kiln work, the write discipline, and the tag vocabulary with its overview prefixes. Read it before you read or write a memory, and before an experiment, which records its result there.
---

# Memory

Memory is for **knowledge that outlives a session**: problems worth solving,
things tried and learned, facts about this project's world. It is not for
working state: a thing that matters only until you finish does not belong
here.

The discipline: **check memory first, record as you go, assume
interruption.** A finding only in your context is lost when the context is
summarised. Write it when you learn it, never at the end.

Kiln Harness Tuner and other agents read and write the same records:
follow the formats below exactly.

## The endpoints

Read the endpoint doc before the first call. `{project_id}` is the Kiln
project's id. The records live in the project's `assistant_memory/` folder;
reach them through the API only.

| Operation | Call | Endpoint doc |
|---|---|---|
| Save | `POST /api/projects/{project_id}/memories`, body `overview` (required, at most 280 characters, no newlines), `scope` (required, no default), `content` (at most 4,000 characters), `tags` | `references/knowledge/api_docs/post_api_projects_project_id_memories.md` |
| List | `GET /api/projects/{project_id}/memories` with `scope`, `tags` (all must match), `content_match` (a regex), `limit`, `offset`. Newest first | `references/knowledge/api_docs/get_api_projects_project_id_memories.md` |
| Summary | `GET /api/projects/{project_id}/memories/summary` with `scope`: counts and tag counts, no content | `references/knowledge/api_docs/get_api_projects_project_id_memories_summary.md` |
| Get | `GET /api/projects/{project_id}/memories/by_ids` with `ids`: the full records | `references/knowledge/api_docs/get_api_projects_project_id_memories_by_ids.md` |
| Update | `PATCH /api/projects/{project_id}/memories/{memory_id}`: only the fields you send change; null clears `content`; the last writer wins | `references/knowledge/api_docs/patch_api_projects_project_id_memories_memory_id.md` |
| Delete | `DELETE /api/projects/{project_id}/memories/{memory_id}`: a hard delete, for confirmed junk only. Ask the user first (`SKILL.md`, "Working with the user") | `references/knowledge/api_docs/delete_api_projects_project_id_memories_memory_id.md` |

A repeated parameter is a list:
`query_params={"scope": "project", "tags": ["lesson"]}`.

**Scopes.** Give one on every call; there is no default. `project` is
project-wide knowledge (constraints, lessons). `task::<task_id>` is work on
that task (issues, experiments, hypotheses, dead ends). A scope is an
exact-match string, not a reference. A list, a search or a summary with no
`scope` returns every scope, so one task's experiments show up in another
task's work.

## Orientation

At the start of Kiln work on a project:

1. Call the summary: its counts are the shape of what is known. When it is
   empty, record the constraints that the user states.
2. Project scope: list `constraint`, then `lesson`.
3. Task scope: read the `baseline` record (`tags=baseline`); list `issue`
   (read `p0` and `p1` first), `dead_end` (before you form any plan),
   `hypothesis`, then the recent `experiment` overviews. The `val` record:
   see its row below.
4. A record with `content_length` 0 is all in its overview. Fetch the rest
   by id, in batches, only where the overview says that you need it.

## Write discipline

- **One finding per memory.** The server enforces the caps: an overview
  over 280 characters or content over 4,000 answers 422. A finding that
  does not fit is almost always several: split it. A long document is a
  file that a memory names by path.
- **The overview is a load decision, not a title.** Put the verdict and the
  number first, so a later reader can decide without fetching: `EXP 0715-1
  (prompt): no-refetch rule — accuracy: +12pp, base=64, cand=76, n=40,
  p=.01`, never `Experiment 7 results`. When the overview says everything,
  leave `content` null.
- **Content is observation, conditions and evidence**, never a universal
  rule: "batch API answered 429 at 50 requests a second on 07-04 (2 runs)".
  Say whether the user stated it or you inferred it, and how many cases.
  Name Kiln records by id in prose ("run config 424242901234").
- **Check before you write.** List the tag first; update a match, never
  add a copy.
- **A correction is an update.** Write the new understanding and add a
  one-line note to the content ("corrected 07-14: was the prompt rule,
  actually the judge change"). Delete only confirmed junk: an approach that
  was ruled out is a `dead_end`, not junk.
- **Store no negative claim about the platform.** "X does not work", "the
  API drops Y" is almost always temporary (a bug, an outage, a wrong
  diagnosis). Do not store it, not even as a hedged `lesson`. The one form
  allowed, and rarely, is a mitigation that a quick check confirmed: "if an
  update seems to drop content, send it again with an explicit content key
  - checked 07-30, the second write landed".
- **When a write fails**, retry it; if it still fails, tell the user the
  finding once. Do not store the failure itself.
- **Not memory-worthy:** the working state of the session; notes on one
  trace (Kiln's feedback on that run holds them); why an object was
  created (its provenance, below); craft that is true beyond this project;
  anything that an object or an eval already records.

## Tags

The seed vocabulary: snake_case and open. Add a tag when real use keeps
forcing one kind of finding into these, not before.

| Tag | What it is | Write when | Read when |
|---|---|---|---|
| `issue` | A problem worth solving, with or without a fix in mind. One that waits on a person says what is needed from whom. Bound to its eval by `eval_<eval_id>` (below). | A trace shows a failure; the user reports a problem; a change fixes X and breaks Y (file Y). Update a match first. | Choosing a target: `tags=issue&tags=p0`, then `p1`. |
| `hypothesis` | A change not yet tried; name its issues. | An idea you do not act on now. | Before you choose the next experiment. |
| `experiment` | One thing tried and its outcome; three items give a direction, never a confirmation. Content: hypothesis, lever, run config ids, what it cost, result, verdict and why, next step. | Before you measure (hypothesis and prediction), and again at the verdict. | "What has been tried?"; before a merge. |
| `dead_end` | An approach ruled out, with the conditions and the experiment that showed it. | A lever is used up or an approach refuted. | Before you form a hypothesis. |
| `constraint` | A requirement, preference or decision that binds the work, from the user ("OpenAI models only"), the world or a choice made. Source, how hard, and why, in the content. | Someone states a requirement; a binding choice is made. | The start of work, and before you design a candidate. |
| `lesson` | Something learned about this project's world or how to work in it. Concrete observations only. | A later session would rediscover it the hard way. | The start of work; before you touch what it describes. |
| `baseline` | One record per task: the current best run config. Tags `baseline` and `rc_<run_config_id>`; read the id from the tag. Content: the promotions, one run config id per line, newest first. No val numbers. | At the first experiment on a task (the default run config, else the newest; say which). When a candidate is kept: move the `rc_` tag, add the id at the top. | Orientation, with `tags=baseline`. |
| `val` | One record per task: the val summary of each promotion. Its overview has no number. Content: one line per promotion, newest first, `rc_<new> (07-16, EXP 0716-2) ← rc_<old> — +9% mean win rate vs rc_<old>`. Summary numbers only, never an item or a trace (`references/knowledge/train_val_test.md`). The only memory with val numbers. | Right after the `baseline` update of a promotion; the first promotion creates it. | When you confirm on val and when you report. Never while you design or build a change. |

Priorities are tags too, mostly on `issue`; change one by an update, never
by a copy: `p0` blocks the goal or harms users, work it now; `p1` is a clear
gain on the agreed metrics, the default queue; `p2` is real but minor; `p3`
is tracked so it is not lost. A priority tag stays when the issue closes.

**Issue states** are overview prefixes, changed by an update, with no state
tag. Open is the default. `UNMEASURED: `: no one has checked the baseline on
its eval. `UNMEASURABLE: `: its evals are all gone. `FIXED: ` adds a content
line that names the fix ("fixed 07-15 by rc_207, EXP 0715-1"). `WONT_FIX: `
gives the reason in the content. To reopen, remove the prefix and add a line
("reopened when rc_213 became the baseline; the issue repeats on it"); never
a copy. One prefix at a time. Do not reopen a `FIXED: ` or `WONT_FIX: `
issue on your own: ask the user.

**Open questions** are `constraint` records with the prefix `OPEN: `:
`OPEN: unknown if the graphql endpoint has docs`. Content: the question,
the default you assumed, its source (the user, or an assumption), and when
to ask again. When it is answered, update it: remove
the prefix, add the answer, its source and the date. Read the `OPEN: `
records before you ask the user anything: never ask what is answered.

**Experiment states** are overview suffixes. Open it as
`EXP 0723-2 (prompt): <short hypothesis> — RUNNING`. The verdict replaces
the suffix with the numbers first
(`— accuracy: +18pp, base=62, cand=80, n=34, p=.04`). Other endings:
`— FAILED (infra: <error class>)`, neither a win nor a dead end;
`— ABANDONED (<why>)`, stopped part way, no verdict. Then, appended:
`— PROMOTED <date>` when its run config becomes the baseline;
`— REJECTED AT VAL <date>` when the confirmation on val passed it over
(that run config is never submitted again unchanged; it can still be
merged). A `RUNNING` overview from an earlier session is abandoned work.
Read, never write, what only Kiln Harness Tuner writes: `— NOT LANDED`
(stopped before train was judged in full: untested, not disproven),
`— CAPPED` (the spend cap was hit: inconclusive, never a dead end),
`— HELD` (waiting on an `OPEN: ` question; the same run config goes on
once it is answered), and its `SCREEN SURVIVOR:` and `SCREEN DEAD END:`
records.

## Issues belong to evals

The eval is the parent of an issue, not the spec.

- **The binding is the tag `eval_<eval_id>`**; a content line
  `- eval: <eval_id>` is for people. "Does this eval have an issue?" is
  `tags=issue&tags=eval_<eval_id>`. "Do all evals have issues?" is one
  `tags=issue` list, compared with the list of evals.
- One eval can have several issues, and an issue several bindings. It is
  `UNMEASURABLE: ` only when none of its evals is left.
- **An issue ends up bound.** Tag it when an eval measures it. When none
  does, the eval is missing: tell the user, and build it only when the user
  agrees (`references/knowledge/create_spec.md`). Never guess a binding.
- **Content can have two owners.** Kiln Harness Tuner splits the content
  of an issue it seeds at the line `— setup wrote everything above; lines
  below belong to the loop —` and rewrites everything above it when the
  eval changes. Never edit above that line: add findings and history below
  it. With no such line, the whole content is append-only history.

## Memory and provenance

Why an object exists and what it comes from goes in its `provenance`
(`notes`, `derived_from_ids`, `origin`), written once at creation.
Everything that changes over time, or spans objects, goes in memory: the
trial in an `experiment`, what it taught in a `dead_end` or `lesson`, what
was decided in a `constraint`. A memory names objects by id in prose; an
object never points at a memory.