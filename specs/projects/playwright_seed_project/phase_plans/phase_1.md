---
status: complete
---

# Phase 1: Script mechanics and the foundation fixture

## Overview

Phase 1 delivers the whole mechanism — seeding, `reset`, `snapshot`, the home guard, the
`ui_state` hint, the load check — plus the first content group (Foundation: project, the
structured task, the plain-text task) and the docs section. Everything after this phase
is fixture content authored through the UI and captured with a command that already
exists.

The mechanism comes first because the fixture cannot be authored without it: `snapshot`
is how content gets from the sandbox into the repo, and `start` is how it gets back out.
The Foundation group is authored in this phase both because the fixture directory has to
exist for the script to have anything to copy, and because authoring it is what proves
the round trip works end to end.

No inference provider is needed. A project and two task definitions are pure metadata —
nothing here executes a model call.

## Steps

### 1. `.agents/scripts/playwright_server.sh` — constants

Add beside the existing `RUN_DIR` block:

```bash
FIXTURE_DIR="$PROJECT_ROOT/.agents/playwright_project"
PROJECTS_DIR="$RUN_DIR/Kiln Projects"
SEEDED_PROJECT_DIR="$PROJECTS_DIR/playwright_project"
SEED_STAMP="$RUN_DIR/.playwright_seed"
SETTINGS_FILE="$RUN_DIR/.kiln_ai/settings.yaml"
SEED_CONTACT="playwright@example.com"
```

`SEEDED_PROJECT_DIR` uses the fixture's basename, per architecture.md — cosmetic, and it
cannot drift from the fixture.

Retract the existing comment on `RUN_DIR` inviting `KILN_DEV_HOME` to be pointed "at real
projects": the override chooses where the sandbox lives, not whose data it operates on.

### 2. `guard_not_real_home`

Resolve `$RUN_DIR` and `${HOME:-}` with `cd` + `pwd -P`, falling back to the literal
string, and refuse when they are equal or when `HOME` is unset. Called by `start`,
`reset`, and `snapshot` — not by `stop` or `status`, which are how you recover from a
misconfigured `KILN_DEV_HOME` and would leave a server you cannot stop if guarded.

### 3. `json_field FILE KEY`

```bash
json_field() {
  sed -n "s/^[[:space:]]*\"$2\": *\"\([^\"]*\)\".*/\1/p" "$1" 2>/dev/null | head -1
}
```

### 4. `fixture_present`, `is_seeded`

One-line predicates on `$FIXTURE_DIR/project.kiln` and `$SEED_STAMP`.

### 5. `write_seed_settings PATH`

Whole-file write of the four-line YAML, single-quoted path scalar with internal quotes
doubled.

### 6. `do_seed`

Copy, settings, stamp — stamp last so a mid-seed failure retries next `start`. Every
failure warns and returns 0: seeding never fails the server. The copy is
`cp -R "$FIXTURE_DIR/." "$SEEDED_PROJECT_DIR/"` into a `mkdir -p`'d destination, so the
retry is idempotent rather than nesting a second copy inside the first.

### 7. `seeded_task_lines` and `print_seed_hint`

`created_at<TAB>id<TAB>name` per task, `sort`ed, so the earliest-created task is first.
`print_seed_hint` prints the project name, the paste-ready `open` →
`localstorage-set` → `goto` sequence (see [Deviations](#deviations-from-architecturemd)
for why all three), and any other tasks compactly. It prints the hint only when
`verify_seed_loaded` confirmed the project with the backend, falling back to the bare
`open` line this script printed before it seeded.

### 8. `verify_seed_loaded`

After both servers answer, on **both** `start` paths, whenever the sandbox has a
`project.kiln`: `GET /api/projects` and match the *installed* copy's quoted project id in
the body. On a match, publish the id in `loaded_project_id` for `print_seed_hint`. On a
miss — including an unreadable id — warn naming all three causes (removed through the UI,
older fixture ⇒ `reset`, stale fixture ⇒ re-author + `snapshot`) and leave
`loaded_project_id` empty so no hint prints. Never fails the server.

### 9. `do_reset`

`guard_not_real_home` → `do_stop` (abort on failure) → `rm -rf "$RUN_DIR"` → `do_start`.

### 10. `do_snapshot`

`guard_not_real_home`, then find exactly one `project.kiln` at depth 2 under
`$PROJECTS_DIR` with `-print0` and a `read -d ''` loop. Zero or multiple is an error that
changes nothing; the multiple-projects listing goes through `sort`. Assert the destination
path shape before the `rm -rf`. Mirror with delete-then-copy, drop `.git` and `.DS_Store`,
print `git status --short` for the destination and a review reminder. Never touches
`settings.yaml`.

### 11. Wire the commands

`start` gains guard → seed → (existing start) → `verify_seed_loaded` → `print_ready_hints`
on the readiness path, and guard → `verify_seed_loaded` → `print_ready_hints` on the
already-running early return, so both print the same block. Add `reset` and `snapshot` to
the `case` and to `usage`.

### 12. Author the Foundation fixture through the UI

Run the server against a scratch `KILN_DEV_HOME`, drive the browser with
`playwright-cli`, and create, in this order:

1. The project — support-ticket triage.
2. The **structured** task, JSON input *and* output schemas. First, because
   `print_seed_hint` points at the earliest-created task.
3. The plain-text task.

Then `snapshot` into `.agents/playwright_project/` and review the diff.

What was authored:

- **Project** `507368061812` "Support Ticket Triage".
- **Task** `235956950045` "Triage Ticket", structured both ways. Input: `subject`
  (string), `body` (string), `customer_plan` (enum free/pro/enterprise). Output: `team`
  (enum), `priority` (enum), `needs_human_review` (boolean), `summary` (string). Enums
  and a boolean deliberately, since the run form renders each differently. Has a
  description and thinking instructions.
- **Task** `280529670660` "Draft Ticket Reply", plain text both ways.

### 13. `.agents/USING_PLAYWRIGHT.md`

A new top-level "The seeded project" section covering: what the seeded project contains,
the `ui_state` commands needed to get past the task picker, that no provider is connected
and what that means for running a task, `reset`, and `snapshot` with the UI-first
authoring rule and the review-the-diff instruction. The existing "Landing on a task's
page directly" section is folded into it rather than repeating the `localstorage-set`
recipe twice, and the `playwright_server.sh start` paragraph gains a pointer to it.

## Tests

`checks.sh` does not lint shell and no automated test loads the fixture (both decisions
in architecture.md). Verification is the matrix below — architecture.md's ten cases plus
four added during review (7b, 11, 12, 13) — run in-container against a disposable
`KILN_DEV_HOME`. All fourteen rows pass:

| # | Case | Result |
|---|---|---|
| 1 | Fresh home, `start` | Seeds; the printed three-command hint lands the browser on `/run` with "Task: Triage Ticket", not `/setup` |
| 2 | `start` again (both already-running and after a `stop`) | No re-seed, stamp unchanged, a task renamed in the UI survives, both paths print the same block including the `stop` line |
| 3 | Remove the project through the UI, `start` | Not resurrected — `settings.yaml` still `projects: []` — **and no `ui_state` hint on either path**, with the warning naming the removal as an expected cause. `project.kiln` confirmed still on disk, which is why disk presence was the wrong gate |
| 4 | `reset` | Stops, wipes, re-seeds; the UI rename is gone |
| 5 | `snapshot` after a UI edit | Fixture mirrors it; `git status` shows only that one file |
| 6 | `snapshot` with zero, then three projects | Errors both times, exit 1, fixture untouched, listing sorted (checked with names that sort differently from `find` order) |
| 7 | `KILN_DEV_HOME=$HOME` for `start`, `reset`, `snapshot` | All three refused, exit 1, nothing written. Also refused for a trailing slash, a symlink, and a `..` path **whose every component exists**; a sibling directory is allowed. `HOME` unset refused with its own message, exit 1. `stop`/`status` still work in that state. **Run with a disposable `HOME`.** |
| 7b | `KILN_DEV_HOME=$HOME/sandbox/..` with `sandbox` **not existing**, for `start`, `reset`, `snapshot` | All three refused, exit 1. Nothing written into the home beyond the empty `sandbox/` the `mkdir -p` creates — no `.kiln_ai`, no `Kiln Projects`. This is the guard-bypass case; before the fix `start` wrote settings and the fixture into the real home. **Run with a disposable `HOME`.** |
| 8 | Fixture moved aside, `start` | Warns, server up, no stamp written so the next `start` retries, hint degrades to the bare `open` line |
| 9 | Seeded copy's `project.kiln` made valid JSON that fails datamodel validation (`name` deleted), `start` | `id` still reads, `/api/projects` returns `[]`, warning fires, **hint suppressed**, server up, exit 0. Verified on both `start` paths |
| 10 | `stop`, `status` | Unchanged; neither is guarded, and both work with `KILN_DEV_HOME=$HOME` |
| 11 | Mid-seed failure (settings write blocked), then `start` again | Re-seeds without nesting; exactly one `playwright_project` directory; a `snapshot` from that sandbox produces no diff |
| 12 | `start` while **another sandbox's** server holds the ports | Warns that the app belongs to a different sandbox, exit 0. Silent before the fix. Verified for a foreign sandbox that is unseeded *and* for one that is already seeded — the stamp test could not catch the second |
| 13 | `start` while **this sandbox's own** server is up, stamp present and stamp removed | No ownership warning in either case. Before the fix, the stamp-removed case (what matrix rows 8 and 11 leave behind) accused the sandbox of driving someone else's app while the hint below named its own project |

Five malformed-task shapes checked against `seeded_task_lines`, since it is the last place
a wrong task id could come from: a task with no `created_at` does not become primary but
*is* still listed under "Other tasks" with its usable id; the same task serves as primary
when it is the only one; an unreadable `id` on the *earliest* task promotes the next one
instead of suppressing the hint; an unreadable `id` on the only task warns and falls back
to the bare `open` line; and a project with no `tasks/` directory does the same.

Two extra properties checked while running the matrix, because they are the reason for
`do_snapshot`'s shape: a task deleted in the sandbox disappears from the fixture
(delete-then-copy, not merge), and `.git` at three depths — as directories *and* as the
regular files `git worktree`/submodules create — plus `.DS_Store` at two are all scrubbed
rather than captured.

Case 9 is the reviewer's stronger version and replaces the original, which mangled the
JSON syntax. That only exercised the unreadable-id branch; the real stale fixture is valid
JSON whose `id` reads fine and whose load fails inside the datamodel, and running the weak
version is what let the wrong-hint and wrong-id findings through the first review. Cases
7b, 11, 12 and 13 were all added during review, covering the guard bypass, the seed-retry
path, the silent already-running path, and the false ownership warning on a sandbox's own
server.

## Deviations from architecture.md

**The `ui_state` hint is three commands, not two.** architecture.md printed
`localstorage-set` then `open`. Both orderings of that pair fail in practice:
`localstorage-set` errors out when no browser is open, and running `open` against an
already-open browser starts a fresh context that discards the value just written. The
working sequence is `open`, then `localstorage-set`, then `goto` — `goto` rather than
`reload` because by then the page is on the task picker it was redirected to, and
reloading that stays there. Verified from a cold browser profile.

**`verify_seed_loaded` reads the installed copy and names three causes, not one.** The
specified text blamed a stale fixture and read the id from the committed fixture. Two
states the design explicitly supports trip the same check: an agent removing the project
through the UI (matrix case 3), and a sandbox seeded from an older fixture after a branch
switch — for which the fix is `reset`, not re-authoring. Both architecture.md and
USING_PLAYWRIGHT.md are updated to match.

**Onboarding was cleared partly outside the UI.** Registration posts to `api.kiln.tech`,
which is unreachable in-container, so `user_type` / `personal_use_contact` were written
into the *sandbox's* `settings.yaml` by hand — which is exactly what `do_seed` writes
anyway, and settings are never captured by `snapshot`. Reaching the create-project screen
also needs a connected provider (the onboarding Continue button is hidden without one, and
a direct URL bounces off `check_needs_setup`), so a placeholder custom OpenAI-compatible
API was added through the UI; it lives only in the sandbox's settings. The fixture data
itself — project, both tasks, both schemas, descriptions, thinking instructions — was
created entirely through the UI forms.

Both constraints are durable and hit every remaining authoring phase, so they are now
recorded in architecture.md's "Fixture authoring" section rather than only here.

**No requirements on the tasks.** Requirements are badged **Deprecated** in
`app/web_ui/src/routes/(fullscreen)/setup/(setup)/create_task/edit_task.svelte` — the
component the settings Edit Task screen also uses — and the whole block is hidden by
`show_requirements = !onboarding && task.requirements.length > 0` — so there is no UI path
to a task's *first* requirement at all, not merely no convenient one. That concern is now
Specs, which the create-eval flow produces in Phase 4.

## Code review round

Fixed, all verified by re-running the matrix:

- **`do_seed` was not idempotent.** `cp -R "$FIXTURE_DIR" "$SEEDED_PROJECT_DIR"` copies
  *into* an existing destination, so the retry the stamp-written-last ordering exists to
  enable produced `playwright_project/playwright_project/…` — invisible in the app, still
  a single match for `snapshot`'s depth-2 `find`, and therefore committed. Now
  `cp -R "$FIXTURE_DIR/." "$SEEDED_PROJECT_DIR/"` after `mkdir -p`, matching
  `do_snapshot`. New matrix case 11 covers it.
- **`print_seed_hint` gated on disk, not on the backend.** Removing a project through the
  UI only unregisters it and leaves `project.kiln` in place, so the hint still printed —
  contradicting the load warning on the cold path, and printing with no warning at all on
  the already-running path, which never called `verify_seed_loaded`. The two now share
  `loaded_project_id`, and `verify_seed_loaded` runs on both paths.
- **`verify_seed_loaded` checked the committed fixture's id.** Reading `$FIXTURE_DIR`
  fires after a branch switch, where the sandbox is healthy and the fix is `reset`, and
  tells you to re-author instead. Now reads the installed copy, matches the id quoted, and
  the message names all three causes. An unreadable id now lands on the warning branch
  instead of returning 0.
- **Guard rationale corrected.** `do_stop` does `rm -f` on two pid files inside
  `$RUN_DIR`, so "stop and status write nothing" was false. The real reason not to guard
  them — they are the recovery path for a misconfigured `KILN_DEV_HOME` — is now stated in
  the script, architecture.md, and step 2 above.
- **`mapfile` replaced with a `read -d ''` loop.** `mapfile -d ''` needs bash 4.4 and
  stock macOS `/bin/bash` is 3.2, which under `set -u` aborts with `unbound variable`
  rather than printing anything — and contradicted the portability argument made two
  sections earlier for avoiding `realpath`. Counting rather than building an array also
  avoids bash's pre-4.4 `${#arr[@]}`-on-empty-array quirk. Taken as a code fix rather than
  the offered alternative of deleting the macOS half of the comment, since that would have
  left a real abort mode in place.
- **`${HOME:-}`** with an explicit message, so an unset `HOME` fails with a sentence
  instead of an unbound-variable abort.
- **`kiln="${dir}task.kiln"`**, no double slash.
- **Already-running `start` printed no `stop` line.** Both paths now go through
  `print_ready_hints`.
- **Multi-project `snapshot` error is sorted.**
- **Docs:** `created_by` carries the snapshotter's OS username into the diff, and `reset`
  discards a hand-connected provider — both now in USING_PLAYWRIGHT.md, which had neither.

Every mild item was taken; none skipped.

## Second code review round

- **Guard bypass closed.** A `KILN_DEV_HOME` with a not-yet-existing component that
  resolves back to `$HOME` — `$HOME/sandbox/..` — passed `guard_not_real_home`, because
  `cd` fails on a missing component and the fallback compares the literal string. `start`
  then `mkdir -p`'d the component and seeded into the real home, overwriting a real user's
  `.kiln_ai/settings.yaml` and adding to their `Kiln Projects`. Reproduced with a
  disposable `HOME`, then fixed by calling the guard a second time immediately after
  `mkdir -p "$RUN_DIR"`, where `cd` cannot fail. `do_reset` needed the same treatment from
  the other direction — its `rm -rf` runs before any `mkdir` — so it now guards again only
  when the directory exists, and skips the delete when there is nothing there, leaving
  `do_start`'s post-mkdir check to catch the rest. `do_snapshot` needs only the one call:
  it writes nothing into `$RUN_DIR`, and `find` cannot traverse a missing component either,
  so the worst a bypass reaches is "no project found" — verified. New matrix case 7b, and
  case 7's recorded `..` coverage corrected to say "whose every component exists".
- **`.git` scrub re-described and made recursive.** The git-sync rationale was wrong:
  clones live at `~/.git-projects/`, outside the searched `Kiln Projects`, so a git-synced
  project can never be `src_dir`. Now described as a repo someone created by hand inside the
  project, in the script and in both docs, and made recursive with a `find … -prune -exec
  rm -rf {} +` so a `.git` inside a task directory no longer survives — the old top-level
  `rm -rf` missed those. (Round 3 also carried a `-type d` on that find; round 4 dropped it,
  below.) That `snapshot` reports "no project found" against a git-synced sandbox is now
  written down in architecture.md and USING_PLAYWRIGHT.md.
- **Already-running `start` now consults `is_seeded`** — superseded in round 4 by an
  ownership check, below. Against a fresh sandbox while
  something else held the ports, it reported success in complete silence and left the agent
  driving another sandbox's app. One warning closes it. New matrix case 12.
- **Primary-task selection.** `seeded_task_lines` drops tasks with an empty `id`, and — as
  of round 4, below — sorts an empty `created_at` last rather than dropping it too. An
  empty `created_at` sorted *first*, which was the last shape that could print a
  confidently wrong task id. Dropping the unreadable-`id` rows also promotes the next task
  when the earliest one is malformed, instead of suppressing the hint entirely.
- **Phase plan counts** corrected: the prose said "10-case matrix … All ten pass" over what
  had grown past ten rows. Kept in step with the table since, and matching
  architecture.md's row for row.

## Third code review round

- **The `! is_seeded` ownership warning misfired on a sandbox's own server.** Every
  `do_seed` bail-out returns 0 without writing the stamp, so after matrix row 8 or 11 a
  second `start` told the agent its own app belonged to a different sandbox — and then
  printed the backend-confirmed hint naming that sandbox's project, the same
  two-statements-disagreeing shape round 1 flagged for `print_seed_hint`. Reproduced, then
  fixed by asking the ownership question directly: `pidfile_process_alive "$BACKEND_PID"`,
  the live-process and command-name filter extracted from `stop_from_pidfile` so the two
  cannot drift. It fixes a second direction the stamp test could not reach either — a
  *seeded* sandbox whose server is somebody else's now warns, where before it stayed
  silent. New rows 12 (extended) and 13.
- **`.git` scrub no longer filters on `-type d`.** `git worktree add` and submodules make
  `.git` a regular file holding `gitdir: …`, which git treats as a repository boundary
  exactly as it does a directory — the gitlink hazard the scrub exists for. `-prune` kept.
  Verified with `.git` files at two depths alongside a real `.git` directory deeper still.
- **A missing `created_at` now sorts last instead of dropping the row.** The two fields are
  not equivalent: `ID_FIELD` mints a fresh id at load, so a task with no readable `id` is
  genuinely unaddressable, but `created_at` has a `default_factory`, so such a task loads
  fine and its readable id yields a working `ui_state`. The old filter hid that id from the
  hint *and* from "Other tasks". A high sentinel keeps the fail-safe ordering — an empty
  sort key would sort first and crown a malformed task "primary" — without discarding a
  usable id.
- **architecture.md's example hint output** used the throwaway probe project's ids while
  the shipped fixture has different ones. Replaced with the real values, and the
  on-disk-format example above it likewise now reproduces the actual committed
  `project.kiln` and both real task directory names, checked byte for byte against the
  files.
- **architecture.md's error table** now says that the post-`mkdir` refusal leaves the empty
  directories `mkdir -p` created in the real home, rather than implying nothing is written
  at all — matching what the matrix row already said.

## Deliberate non-fixes

**`rm -rf "$RUN_DIR"` has only the real-home guard.** The reviewer noted that `reset`
accepts any `KILN_DEV_HOME` that is not exactly `$HOME` — including `/` and
`~/kiln-work` — and proposed an extra precondition refusing to delete a directory this
script never created (no seed stamp, no pid files). The risk is real. It is not being
fixed, because it relitigates a decision the user made explicitly during design:

> "no guard needed if it's properly isolated home for the playwright env. It owns it,
> expected to clobber often with reset. Just a guard it's never real '~'."

Recorded here rather than in architecture.md's error table so it stays visible and
reversible if that judgement changes.
