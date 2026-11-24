---
name: memory
description: The project's durable memory - what belongs in it, the six Memory endpoints, scopes, what to read at the start of Kiln work, which records you may write and the write discipline, the tag vocabulary, and the files with the read-only formats that Kiln Harness Tuner writes. Read it before you read or write a memory.
---

# Memory

Memory is for **knowledge that outlives a session**: problems worth solving,
things tried and learned, facts about this project's world. It is not for
working state: a thing that matters only until you finish does not belong
here.

This file is a reference for every agent. Kiln Harness Tuner's code writes
most records, in exact formats that its code parses back, and its code is
the authority on them. You read those records, and you write only the
kinds that the tag table marks as yours.

The discipline: **check memory first, record a lasting finding when you
learn it, assume interruption.** A finding only in your context is lost
when the context is summarised. Write it when you learn it, never at the
end.

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
that task (issues, experiments, dead ends). A scope is an exact-match
string, not a reference. A list, a search or a summary with no `scope`
returns every scope, so one task's experiments show up in another task's
work.

## Orientation

At the start of Kiln work on a project:

1. Call the summary: its counts are the shape of what is known. When it is
   empty, record the constraints that the user states.
2. Project scope: list `constraint` (the `OPEN: ` records among them),
   then `lesson`.
3. Task scope: read the `baseline` record (`tags=baseline`); list `issue`
   (read `p0` and `p1` first), `dead_end` (before you form any plan),
   `hypothesis`, then the recent `experiment` overviews. The `val` record:
   see its row below.
4. A record with `content_length` 0 is all in its overview. Fetch the rest
   by id, in batches, only where the overview says that you need it.

## Write discipline

These apply to the kinds you write.

- **One finding per memory.** The server enforces the caps: an overview
  over 280 characters or content over 4,000 answers 422. A finding that
  does not fit is almost always several: split it. A long document is a
  file that a memory names by path.
- **The overview is a load decision, not a title.** Put the verdict and the
  number first, so a later reader can decide without fetching:
  `few-shot block for tone: accuracy -4pp on train, n=40, p=.30, rc 424242901234`,
  never `Experiment 7 results`. When the overview says everything, leave
  `content` null.
- **Content is observation, conditions and evidence**, never a universal
  rule: "batch API answered 429 at 50 requests a second on 07-04 (2 runs)".
  Say whether the user stated it or you inferred it, and how many cases.
  Name Kiln records by id in prose ("run config 424242901234"). A cost is
  labelled `spend`.
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

| Tag | What it is | Who writes | Read when |
|---|---|---|---|
| `issue` | A problem worth solving, with or without a fix in mind. One that waits on a person says what is needed from whom. Bound to its eval by `eval_<eval_id>` (below). | You: a new, open issue, when a trace shows a failure, the user reports a problem, or a change fixes X and breaks Y (file Y). Update a match first. Kiln Harness Tuner's code: the issues it seeds, and every state prefix. | Choosing a target: `tags=issue&tags=p0`, then `p1`. |
| `dead_end` | An approach ruled out, with the conditions and the run config ids that showed it. | You, when an approach is refuted clearly past the noise or a lever is used up. Kiln Harness Tuner's code also writes `SCREEN DEAD END` records: never edit them. | Before you form a hypothesis. |
| `lesson` | Something learned about this project's world or how to work in it. Concrete observations only. | You, when a later session would rediscover it the hard way. Kiln Harness Tuner's code also writes `SCREEN` and `PROBE` lessons. | The start of work; before you touch what it describes. |
| `constraint` | A requirement, preference or decision that binds the work, from the user ("OpenAI models only"), the world or a choice made. Source, how hard, and why, in the content. | You, for the restrictions the user states. The `OPEN: ` records are Kiln Harness Tuner's code. | The start of work, and before you design a candidate. |
| `hypothesis` | A change not yet tried, with the issues it names. | Reserved for Kiln Harness Tuner, which reads it. Do not write one: tell the user an idea you do not act on now. | Before you choose a change. |
| `experiment` | One thing tried and its outcome. | Kiln Harness Tuner's code only. A one-off over MCP writes none: its lasting results are a `lesson`, a `dead_end` or an `issue`. | "What has been tried?"; before a merge. |
| `baseline` | One record per task: the current best run config, in its `rc_<run config id>` tag. No val numbers. | Kiln Harness Tuner's code only. | Orientation, with `tags=baseline`. |
| `val` | One record per task: the val summary of each promotion, the only memory with val numbers. Summary numbers only. | Kiln Harness Tuner's code only. | At orientation, when you need the numbers behind the promotions; when you confirm on val; when you report. Nothing in it goes into a change (`references/knowledge/train_val_test.md`). |

Priorities are tags too, mostly on `issue`: `p0` blocks the goal or harms
users, work it now; `p1` is a clear gain on the agreed metrics, the default
queue; `p2` is real but minor; `p3` is tracked so it is not lost. Give a
new issue one. On an issue that Kiln Harness Tuner seeded, the priority
comes from its source, and its re-sync replaces the tag: do not change it.

**Issue states** are overview prefixes (`UNMEASURED: `, `UNMEASURABLE: `,
`FIXED: `, `WONT_FIX: `), and Kiln Harness Tuner's code writes them. You
never change an issue's state, and never reopen one: tell the user what
you found. A list returns closed issues too: skip them by their prefix.
`UNMEASURABLE: ` is a status, never a close.

**Open questions** are `constraint` records with the prefix `OPEN: `,
which Kiln Harness Tuner's code writes. Read them before you ask the user
anything: never ask what is answered. In the rare case that the user
answers one in the chat, you may record the answer as a `constraint` that
cites the `OPEN: ` record's id.

## Issues belong to evals

The eval is the parent of an issue, not the spec.

- **The binding is the tag `eval_<eval_id>`**. "Does this eval have an
  issue?" is `tags=issue&tags=eval_<eval_id>`. "Do all evals have
  issues?" is one `tags=issue` list, compared with the list of evals.
- One eval can have several issues, and an issue several bindings.
- **An issue you write ends up bound.** Tag it when an eval measures it.
  When none does, the eval is missing: tell the user, and build it only
  when the user agrees (`references/knowledge/create_spec.md`). Never
  guess a binding.
- **Kiln Harness Tuner's smell and audit issues are bound to no eval on
  purpose** (the tags `smell`, `baseline_audit`, `baseline_judge_copy`).
  Do not bind them, and do not report a missing eval for them.
- **A finding on an existing issue** is a line added to its content. On an
  issue that Kiln Harness Tuner seeded, add it below the delimiter line,
  never above it
  (`references/knowledge/memory_formats/issue_records.md`).

## The formats that Kiln Harness Tuner writes

Read-only: each file gives the strings that its code writes, and what each
means for a reader. Read the file before you read a record of its kind.

| Records | File |
|---|---|
| `experiment` records: the id, the opening and verdict overviews, the state suffixes, the val stamps and lines, the content lines | `references/knowledge/memory_formats/experiment_records.md` |
| `issue` records: the state prefixes, the setup head and the delimiter line, the appended lines, the smell and audit tags | `references/knowledge/memory_formats/issue_records.md` |
| `OPEN: ` records: the open questions and their five content lines | `references/knowledge/memory_formats/open_questions.md` |
| The `baseline` and `val` records | `references/knowledge/memory_formats/baseline_and_val_records.md` |
| `SCREEN` and `PROBE` records: the screenings and the quick checks | `references/knowledge/memory_formats/screening_and_probe_records.md` |

## Memory and provenance

Why an object exists and what it comes from goes in its `provenance`
(`notes`, `derived_from_ids`, `origin`), written once at creation.
Everything that changes over time, or spans objects, goes in memory: what
was learned in a `dead_end` or `lesson`, what was decided in a
`constraint`. A memory names objects by id in prose; an object never
points at a memory.
