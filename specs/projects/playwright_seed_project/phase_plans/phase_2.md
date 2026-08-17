---
status: draft
---

# Phase 2: Runs, ratings, and the small artifacts

## Overview

Phase 2 authors architecture.md's content groups 2 and 3 into the committed fixture:
the runs that make every dataset, comparison, and eval screen show something, and the
four small artifacts that hang off them (a saved prompt, a dataset split, an input
transform, and human feedback on a run).

Nothing in this phase is code. The diff should be JSON under
`.agents/playwright_project/` plus this plan. Everything is created by clicking through
the app at `http://localhost:6544` and captured with
`.agents/scripts/playwright_server.sh snapshot`.

Generation uses `deepseek/deepseek-v4-flash-0731` through OpenRouter, connected through
the UI so the key lands in the sandbox's gitignored `settings.yaml` — which `snapshot`
never reads. That property is the whole reason the key cannot reach the repo, so nothing
in this phase reads or writes settings by hand.

## Steps

Each numbered group ends in a `snapshot` and a `git diff` review, per architecture.md's
resumability rule. A lost session costs at most one group.

### 1. Connect OpenRouter through the UI

Settings → Providers → OpenRouter → paste key → Connect. Phase 1 left a placeholder
Custom API connected in *its* sandbox only; settings are never snapshotted, so a
freshly-seeded sandbox has no providers at all and OpenRouter is the only one this phase
adds. Nothing here reaches the fixture.

### 2. Run config A, and the bulk of the runs

Run the structured **Triage Ticket** task from `/run` with
`deepseek/deepseek-v4-flash-0731`, structured output mode `json_schema`. That first run
mints run config A. Then keep running with varied ticket inputs — different teams,
priorities, plans, and a couple that should escalate — until the structured task has
roughly a dozen runs.

Then run the plain-text **Draft Ticket Reply** task a handful of times, so the
unstructured screens have data too.

Target 15–20 runs total, weighted to the structured task.

### 3. Run config B on the structured task

Change a run option that forks the run config — a different prompt selection (e.g. the
"Chain of Thought" / thinking prompt rather than Basic) at the same model — and run the
structured task several more times. Comparison and eval screens need two run configs on
one task to be worth opening.

### 4. Ratings, spread on purpose

From the Dataset screen, rate runs by opening each and using the rating control:

- Several **high** (4–5 overall, plus any per-requirement ratings the structured task
  offers).
- A couple **low** (1–2), on runs whose output really is wrong or thin.
- **Several left unrated.** This is content, not an omission: the dataset filters and the
  eval split screens have nothing to show without unrated rows.

### 5. A repair

Pick one low-rated structured run, use the repair flow to supply a corrected output, and
save it. At least one run in the fixture must carry `repaired_output` and a repair
instruction.

### 6. Feedback on a run

Leave human feedback (the free-text note on a run) on at least one run.

### 7. Prompt, split, transform

- **Saved prompt** — from the Prompts screen, save a custom prompt for the structured
  task.
- **Dataset split** — from the Dataset screen, create a train/test (or
  train/val/test) split over the tagged runs.
- **Input transform** — create one input transform for the structured task.

### 8. Snapshot, review, and record what was authored

Final `snapshot`, then `git status` / `git diff --stat` for anything unintended, and fill
in the "What was authored" section below with the real ids and counts.

## Tests

No automated tests. Same rationale as phase 1 (architecture.md, "Testing strategy"): no
test loads the fixture, and `verify_seed_loaded` catches rot at the moment it matters.
Verification for this phase is:

- `snapshot` after each group leaves a diff containing only files under
  `.agents/playwright_project/`, reviewed before moving on.
- `reset` from the committed fixture at the end, then land in the app and confirm every
  authored screen renders what was authored: dataset rows with the mixed rating states,
  two run configs on the structured task, the repaired run, the split, the transform, the
  saved prompt.
- No occurrence of the OpenRouter key anywhere in the repo — checked with a grep of the
  working tree before handing off.

## What was authored

All ids are the real ones in the committed fixture. 20 runs, weighted to the structured
task, across four run configs.

### Run configs

Saving options from `/run` mints a config with a random name, and there is no name field
in that flow — but each config's detail page under `/optimize/.../run_config/<id>` has an
Edit dialog that renames it, so all four carry meaningful names. Their **directory** names
still hold the original random name, because Kiln fixes the directory at creation and does
not rename it; that is what a renamed run config looks like on disk.

| Task | Id | Name | Model | Prompt | Runs |
|---|---|---|---|---|---|
| Triage Ticket | `177167545173` | Zero Shot Baseline | deepseek-v4-flash | frozen Basic (Zero Shot) | 10 |
| Triage Ticket | `293284619675` | Chain of Thought | deepseek-v4-flash | frozen Chain of Thought | 4 |
| Triage Ticket | `140414461876` | Playbook with Prose Input | deepseek-v4-flash | saved prompt `281098421169` | 1 |
| Draft Ticket Reply | `228934807381` | Zero Shot Baseline | deepseek-v4-flash | frozen Basic (Zero Shot) | 5 |

All four run OpenRouter's `deepseek/deepseek-v4-flash-0731` at thinking level high, so
every run also carries reasoning content.

### Runs

**Triage Ticket (structured) — 15 runs.** Inputs cover all three `customer_plan` values and
produce every `team` the enum offers except `account_management`, which appears only in the
repair below; `needs_human_review` comes out both ways. Two tickets are deliberate
escalations (a cross-tenant data leak, a suspicious admin login).

**Draft Ticket Reply (plain text) — 5 runs**, five of the same tickets rewritten as prose,
so the unstructured screens have data too.

### Ratings

| State | Count | Structured | Plain text |
|---|---|---|---|
| High (4–5) | 6 | 4 | 2 |
| Low (1–2) | 3 | 2 | 1 |
| Unrated | 11 | 9 | 2 |

Only the overall five-star rating exists: the task carries no requirements, because there
is no UI path to a task's first requirement (recorded as a phase 1 deviation), so the
per-requirement ratings the plan anticipated are not available to author.

The table above is the final state and is the one to trust. `d95458e`'s message says "10
unrated: 8 structured, 2 plain text", which was true when it was written; the next commit
added run `141021632869`, which is unrated. Counts read from a single commit in the middle
of the phase will not match the fixture.

### Repair

Run `189009782155` (Zero Shot Baseline, rated 1) routed a workspace-ownership transfer to
`technical_support` at low priority. Repaired through Attempt Repair with an instruction
naming the right team and priority; the accepted repair is `account_management` / `medium`.
Accepting does not overwrite the original rating, so the run keeps its 1 star alongside
`repair_instructions` and `repaired_output` — the one run in the fixture whose Repair State
column reads "Repaired".

### Feedback

Run `170843774961` (Chain of Thought, rated 2) carries one free-text feedback note. Feedback
is its own child model, at `runs/170843774961/feedback/148834163100/feedback.kiln`.

### Prompt, split, transform

- **Saved prompt** `281098421169` "Triage Playbook" on the structured task — explicit
  routing rules per team plus chain-of-thought instructions, written on the Prompts screen.
- **Dataset split** `240478987760` "Dapper Moss" — 80/10/10 train/test/val (10/1/1) over
  the filter `tag::fine_tune_triage`. 12 of the 15 structured runs carry that tag, applied
  from the Dataset screen's bulk selection. It keeps its random auto-generated name, unlike
  the run configs, for the plain reason that it cannot be renamed: there is no update route
  for `dataset_splits` in `libs/server/kiln_server/` or `app/desktop/studio_server/`, and
  hand-editing the file would break the UI-first rule for a cosmetic gain.
- **Input transform** — a Jinja template on run config `140414461876` that renders the
  ticket as prose. Transforms are a field of `RunConfigProperties`, not a standalone task
  child, so "one input transform" is one run config carrying one. Run `141021632869`
  exercises it: `TaskRun.input` holds the raw structured input while the trace shows the
  rendered user message, which is the transform contract.

### Deviations from the plan

- **Splits are not creatable from the Dataset screen.** The only UI that creates a
  `DatasetSplit` is step 3 of the fine-tune flow, reached by picking a JSONL download format
  in step 1 — no fine-tune provider is connected and no fine-tune job was started. That flow
  also only offers tags beginning with `fine_tune`, which is why the tag is
  `fine_tune_triage` rather than something shorter.
- **Two clicks went through `page.evaluate` rather than the CLI's `click`** — and did not
  need to. The `fine_tune_triage` tags were applied by clicking "Add Tags" and the dialog's
  submit in-page. Same elements, same handlers, no API call by hand, so the fixture is what
  the UI would have produced either way; but the reason recorded at the time was wrong, and
  the detour was avoidable. See ["What actually went wrong with the tag menu"](#what-actually-went-wrong-with-the-tag-menu)
  below. This deviation is also missing from `a6d621d`'s commit message, which says only
  "tagged from the Dataset screen's bulk selection"; architecture.md asks for a line per
  deviation there. The commit is pushed, so rather than rewrite history the corrected finding
  is recorded in architecture.md and USING_PLAYWRIGHT.md, where it is more use anyway.
- **The Repair Output section only appears after an interactive rating change.** On a fresh
  load of an already-rated run the section is absent even though every condition the
  component tests is satisfied, so the repair was reached by clicking the star twice — off,
  then back on. A single re-click *clears* the rating and the section stays hidden, so one
  click looks like the finding failing to reproduce. On re-examination this looks like a
  defect in `run.svelte` rather than an authoring quirk — see architecture.md's "Fixture
  authoring" section for the reproduction, the toggle behaviour, and what it costs.

Both of the last two bullets are things any authoring phase that drives a bulk menu or
repairs an already-rated run will hit, not phase-2 anecdotes. Following phase 1's precedent
with the onboarding gates, both are recorded in architecture.md's "Fixture authoring" section
(the locator one in USING_PLAYWRIGHT.md too, under "Driving the UI"), because the
coding-phase prompt's context loading names architecture.md and never a prior phase plan.

### What actually went wrong with the tag menu

Recorded because the first explanation was confident and false, and it nearly bought a
standing exception to the UI-first rule on the strength of it.

The claim was that a DaisyUI `dropdown` closes on blur before the next `playwright-cli`
command lands, so the menu item can only ever be clicked in-page. Re-tested against the live
sandbox, that is not what happens. After `click "div.dropdown [role=button]"`, a separate
process reports `document.activeElement` still on the trigger, `.dropdown-content` visible at
`opacity: 1` and 88px tall, and `find "Add Tags"` returning `button "Add Tags" [ref=…]` inside
the open list. Clicking that ref opens the dialog. So does `click ".dropdown-content button
>> nth=0"`. The menu survives; there is no blur problem.

What actually failed was the locator. `getByRole('button', { name: 'Add Tags', exact: true })`
matches **two** elements — the menu item and the disabled submit inside the Add Tags dialog —
so Playwright raises a strict-mode violation and clicks nothing.

Why the error was invisible took a second correction. The first write-up blamed `2>/dev/null`,
which would not have hidden anything. Measured against this app, `playwright-cli` prints
failures on **stdout** and exits 1:

| Redirection | Output |
|---|---|
| none, or `2>/dev/null` | full strict-mode violation, both matches named |
| `1>/dev/null`, or `>/dev/null 2>&1` | nothing at all |

That table is the durable part and does not depend on what was typed during authoring. The
shell history is gone, so which redirection was actually used is not something this document
can establish; `>/dev/null 2>&1` is the form that reproduces the silence, and it is the form
these transcripts tend to carry, but that is a plausible reconstruction rather than a
measurement.

Two lessons, both now in USING_PLAYWRIGHT.md: `>/dev/null` on a `playwright-cli` call throws
away the failure text, so keep it or check `$?`; and prefer `find` then the ref, which cannot
go ambiguous. The `page.evaluate` fallback keeps no special blessing — it bypasses Playwright's
actionability checks, and the ordinary path works here.

### The method lesson, which is the durable one

Three times in review this phase, a true observation was written up with an invented mechanism
attached, and each mechanism was falsified by a reviewer who ran the experiment:

| Observation (true every time) | Mechanism asserted | What testing showed |
|---|---|---|
| The click did nothing and no dialog opened | The DaisyUI menu closed on blur between processes | Menu still open — `activeElement` on the trigger, `.dropdown-content` visible, `find` returning its ref |
| The error was invisible | `2>/dev/null` suppressed it | Failures print on stdout; `2>/dev/null` shows them in full |
| `find` returns three matches and one carries a ref | Only the menu item is rendered, so only it carries a ref | Both elements measured visible with the menu open; it also contradicted this document's own closed-menu paragraph |

None of the three came from bad observation. All three came from writing down the first
explanation that fit rather than the one experiment that would separate it from the
alternatives — and in the first case that nearly bought a standing exception to the UI-first
rule on the strength of it.

The third is the one worth dwelling on: it shipped **in the commit written to end this
pattern**, a few lines from the table describing the first two. Recognising a habit is not the
same as having stopped it, and an explanation is most tempting exactly when it is a throwaway
half-sentence attached to something already verified.

The rule this phase ends on: **state the observation, and state a mechanism only with the
experiment that distinguishes it.** Where the experiment has not been run, say so — "the click
failed and the reason was not visible" is publishable; a confident wrong reason is worse than
no reason, because it stops the next reader from looking.

## Roadblock (resolved): OpenRouter was unreachable from the container

Kept as history. The prior attempt at this phase was blocked at step 1 and recorded the
finding below; the egress denial has since been lifted, `curl https://openrouter.ai/api/v1/models`
returns 200 from this container, and the plan above ran as written. Nothing about it needs
to change — it is recorded because the same symptom will look identical if the policy ever
changes back.

Connecting OpenRouter through the UI failed with:

```
Failed to connect to OpenRouter. Error: HTTPSConnectionPool(host='openrouter.ai', port=443):
Max retries exceeded with url: /api/v1/chat/completions
(Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')))
```

That was not the key and not Kiln. All outbound HTTPS from the session went through the
agent egress proxy, and `openrouter.ai:443` was denied by policy at the gateway — the
proxy's own status endpoint recorded it as `connect_rejected … gateway answered 403 to
CONNECT`, and a bare `curl https://openrouter.ai/api/v1/models` failed the same way with
no Kiln in the picture. The proxy README is explicit that a 403 is an organization egress
denial that must be reported rather than retried or routed around.

The denial was not OpenRouter-specific: `api.openai.com`, `api.deepseek.com` and
`api.fireworks.ai` (the other provider serving `deepseek-v4-flash`) were all denied the
same way. `generativelanguage.googleapis.com` did answer, and no local model runtime was
installed (`ollama` absent).

The key never reached disk in that attempt — Kiln only stores a provider key after the
validation call succeeds.

The lasting lesson: every step of this phase depends on real generation, so an egress
denial blocks all of it, and the correct response is to report it rather than substitute a
provider — the model every run in the fixture is generated with is the user's call.
