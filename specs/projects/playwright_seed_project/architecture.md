---
status: complete
---

# Architecture: Playwright Seed Project

Single architecture doc, no component designs. The whole change is one shell script,
one committed fixture directory, and a docs section — there is no component with
enough internal complexity to deserve its own file.

## Files touched

| Path | Change |
|---|---|
| `.agents/scripts/playwright_server.sh` | Seeding, `reset`, `snapshot`, the home guard, the `ui_state` hint, the load check |
| `.agents/playwright_project/` | New. The committed fixture |
| `.agents/USING_PLAYWRIGHT.md` | New section on the seeded project and the new commands |

Nothing in `.config/utils/` changes. No new dependency, no new language: the script
stays pure bash.

## Ground truth about Kiln's on-disk format

Verified by building a project with the datamodel rather than by reading code, because
every algorithm below depends on it.

`.kiln` files are **JSON**, not YAML, pretty-printed at 2-space indent:

```json
{
  "v": 1,
  "id": "507368061812",
  "created_at": "2026-08-17T16:10:56.657538Z",
  "created_by": "root",
  "name": "Support Ticket Triage",
  "description": "Route inbound customer support tickets to the right team, and draft first replies.",
  "model_type": "project"
}
```

Layout, with the project directory named by the seed and the task directory named by
the app:

```
Kiln Projects/playwright_project/project.kiln
Kiln Projects/playwright_project/tasks/235956950045 - Triage Ticket/task.kiln
Kiln Projects/playwright_project/tasks/280529670660 - Draft Ticket Reply/task.kiln
```

Three consequences:

- `id` is the second key at top level, and every nested object sits deeper, so the
  first indentation-tolerant `"id"` match in a file is always the model's own id.
  Likewise `name` precedes `requirements`, whose entries also carry names.
- The task directory name embeds the id, but the seed does **not** parse it. Directory
  naming is an app implementation detail that can change; the JSON keys are the
  datamodel. Reading `task.kiln` costs nothing extra and does not rot.
- `created_by` records the OS username. Left as-is, by decision.

Settings live at `<home>/.kiln_ai/settings.yaml` and are real YAML. The `projects`
entry is the path to the `project.kiln` **file**, not its directory — matching
`add_project_to_config(project_file)`.

`UIState` in `app/web_ui/src/lib/stores.ts:45` is exactly three nullable strings:
`current_project_id`, `current_task_id`, `selected_model`.

## Script structure

New constants beside the existing ones:

```bash
FIXTURE_DIR="$PROJECT_ROOT/.agents/playwright_project"
PROJECTS_DIR="$RUN_DIR/Kiln Projects"
SEEDED_PROJECT_DIR="$PROJECTS_DIR/playwright_project"
SEED_STAMP="$RUN_DIR/.playwright_seed"
SETTINGS_FILE="$RUN_DIR/.kiln_ai/settings.yaml"
SEED_CONTACT="playwright@example.com"
```

The destination directory name is the fixture's basename. It is cosmetic — the name the
UI shows comes from `project.kiln` — and using the basename avoids both parsing JSON to
get the name and a constant that can silently drift from the fixture.

New functions, in dependency order:

| Function | Responsibility |
|---|---|
| `guard_not_real_home` | Refuse to operate on the invoking user's home |
| `json_field FILE KEY` | First indentation-tolerant `"KEY": "value"` in a `.kiln` file |
| `fixture_present` | `$FIXTURE_DIR/project.kiln` exists |
| `is_seeded` | `$SEED_STAMP` exists |
| `write_seed_settings PATH` | Write `settings.yaml` whole |
| `do_seed` | Copy fixture, write settings, write stamp |
| `seeded_task_lines` | `created_at<TAB>id<TAB>name` per task, sorted |
| `print_seed_hint` | The `ui_state` command and task list |
| `verify_seed_loaded` | Assert the backend actually loaded the fixture |
| `do_reset` | Stop, wipe, start |
| `do_snapshot` | Mirror the sandbox's project back into the fixture |

## Key algorithms

### `guard_not_real_home`

```bash
guard_not_real_home() {
  local resolved_run resolved_home home="${HOME:-}"
  if [ -z "$home" ]; then
    echo "error: HOME is not set, so this script cannot tell whether $RUN_DIR is" >&2
    echo "       your real home. Export HOME and re-run." >&2
    return 1
  fi
  resolved_run="$(cd "$RUN_DIR" 2>/dev/null && pwd -P)" || resolved_run="$RUN_DIR"
  resolved_home="$(cd "$home" 2>/dev/null && pwd -P)" || resolved_home="$home"
  if [ "$resolved_run" = "$resolved_home" ]; then
    echo "error: KILN_DEV_HOME is your real home ($resolved_home)." >&2
    echo "       This sandbox writes settings and a fixture project into the home it" >&2
    echo "       is given, and reset deletes it. Point it somewhere disposable." >&2
    return 1
  fi
}
```

`$HOME` is the invoking shell's, and stays that way: the script never exports `HOME`,
it only passes `env HOME="$RUN_DIR"` to the backend child. `cd`+`pwd -P` rather than
`realpath` because `realpath` is not dependably present across the Linux containers and
macOS machines this repo is developed on, and the fallback to the literal string keeps
the comparison meaningful when the directory does not exist yet. `${HOME:-}` because a
bare `$HOME` under `set -u` aborts with `unbound variable` in the shells that do not set
it, and this guard is the last thing that should fail open.

**The literal-string fallback is also the guard's one hole, so callers check twice.** `cd`
fails on a path with a missing component, so `$HOME/sandbox/..` — which resolves to the
real home the instant `sandbox` exists — compares as its literal self and passes. `start`
then creates the component and seeds into the real home. Every caller that writes therefore
re-checks once the directory is known to exist, where `cd` cannot fail:

- `start` calls it again immediately after `mkdir -p "$RUN_DIR"`, before seeding.
- `reset` deletes only when `[ -d "$RUN_DIR" ]`, and re-checks first. Nothing to delete is
  not an error — `reset` on a never-started sandbox is just a seeded `start`, which does
  its own post-`mkdir` check.
- `snapshot` needs only the one call: it writes nothing into `$RUN_DIR`, and `find` cannot
  traverse a missing component any more than `cd` can, so a bypass reaches "no project
  found" and stops.

Called by `start`, `reset`, and `snapshot`. Not by `stop` or `status` — those two are how
you recover from a misconfigured `KILN_DEV_HOME`, so guarding them would leave a server
you cannot stop. Between them they write only `rm -f` of the two pid files the script
created itself.

### `json_field`

```bash
json_field() {
  sed -n "s/^[[:space:]]*\"$2\": *\"\([^\"]*\)\".*/\1/p" "$1" 2>/dev/null | head -1
}
```

Indentation-tolerant so a change to `json.dumps` formatting cannot break it, and
`head -1` because the model's own scalars always precede any nested object carrying the
same key.

Every caller must treat empty output as failure. The rule for the `ui_state` hint is
absolute: **unless the backend confirms the project, print a warning and no hint.** A
wrong hint sends the agent to the task picker, which is exactly the symptom of an
unseeded sandbox, so a confident wrong answer costs more than an admitted unknown. An
unreadable id is only one way to earn that warning — see
[`verify_seed_loaded`](#verify_seed_loaded), which owns the decision, because a project
the app does not have is the more common cause and disk cannot see it.

### `do_seed`

Runs only when `is_seeded` is false, and only from `start` (`reset` wipes the stamp by
deleting the directory). Order matters:

1. `cp -R "$FIXTURE_DIR/." "$SEEDED_PROJECT_DIR/"`, after `mkdir -p "$SEEDED_PROJECT_DIR"`.
2. `write_seed_settings "$SEEDED_PROJECT_DIR/project.kiln"`.
3. Write `$SEED_STAMP`, last.

The stamp is written last so that a failure at any earlier step leaves it absent and
the next `start` retries. Its contents are informational only — the date and the repo's
`git rev-parse --short HEAD` at seed time, so someone can find out how old a sandbox
is. **Nothing ever reads it back for comparison**; presence is the entire signal.

Step 1 copies `$FIXTURE_DIR/.` into an existing directory rather than `$FIXTURE_DIR`
into a missing one, which makes it idempotent. This matters precisely because of the
retry the stamp ordering creates: `cp -R src dst` with `dst` already present copies
*into* it, so a second attempt after a mid-seed failure would produce
`playwright_project/playwright_project/…`. The nested copy is invisible in the app — the
outer `project.kiln` is what settings point at — and `snapshot`'s depth-2 `find` still
matches exactly one project, so it would be captured and committed. Same form
`do_snapshot` already uses.

Seeding happens before the backend launches. `Config` is a process-lifetime singleton
that caches settings on first read, so a backend started against an unseeded home holds
empty settings until it dies.

### `write_seed_settings`

```bash
write_seed_settings() {
  local escaped
  escaped="$(printf '%s' "$1" | sed "s/'/''/g")"
  mkdir -p "$(dirname "$SETTINGS_FILE")" || return 1
  cat >"$SETTINGS_FILE" <<EOF
projects:
- '$escaped'
user_type: personal
personal_use_contact: $SEED_CONTACT
EOF
}
```

Written whole, never merged — the sandbox's settings are ours to define. A
single-quoted YAML scalar with internal quotes doubled is the YAML escaping rule, and
it makes the path safe whatever it contains: `Kiln Projects` has a space, and a
developer's checkout path can hold `#` or `:`, both of which would change the meaning
of a plain scalar.

`user_type: personal` plus `personal_use_contact` is what clears the registration
check; the address is deliberately an `@example.com` placeholder.

### `seeded_task_lines` and `print_seed_hint`

```bash
seeded_task_lines() {
  local dir kiln created id name
  for dir in "$SEEDED_PROJECT_DIR"/tasks/*/; do
    kiln="${dir}task.kiln"
    [ -f "$kiln" ] || continue
    id="$(json_field "$kiln" id)"
    [ -n "$id" ] || continue
    created="$(json_field "$kiln" created_at)"
    name="$(json_field "$kiln" name)"
    [ -n "$created" ] || created="9999-12-31T23:59:59Z"
    printf '%s\t%s\t%s\n' "$created" "$id" "$name"
  done | sort
}
```

Sorted by `created_at`, which is ISO-8601 with a `Z` suffix and therefore sorts
correctly as text. The earliest-created task is the primary one, the one the
paste-ready command uses. That rule is deterministic and, unlike sorting by id, it is
**controllable by whoever authors the fixture**: create the task you want an agent to
land on first. The rest are listed compactly with their ids so a different one is one
edit away.

The two malformed shapes are handled differently, because they are not equally bad:

- **No readable `id` — drop the row.** `ID_FIELD` mints a fresh id when the datamodel loads
  a file without one, so the on-disk value is unknowable and no `ui_state` can name that
  task. Dropping also lets an unreadable *earliest* task promote the next one rather than
  suppressing a hint that would have worked.
- **No readable `created_at` — sort last, keep the row.** That field has a
  `default_factory`, so the task loads fine and the id above still addresses it. An empty
  sort key sorts *first*, which would crown a malformed task "primary" — the one remaining
  shape of confidently wrong task id — so it gets a high sentinel instead. Dropping it
  would have been the safer-looking choice and the wrong one: the id works, and the row is
  what puts it in "Other tasks" where someone can use it.

`print_seed_hint` emits, alongside the existing ready message — verbatim from the shipped
fixture, so the ids below are the real ones:

```
  Seeded project: Support Ticket Triage / Triage Ticket

  Land in the app (the layout redirects to a task picker without this):
    playwright-cli open http://localhost:6544
    playwright-cli localstorage-set ui_state '{"current_project_id":"507368061812","current_task_id":"235956950045","selected_model":null}'
    playwright-cli goto http://localhost:6544

  Other tasks: 280529670660 (Draft Ticket Reply)
```

This exists because the four-step gate in `routes/+layout.svelte` has two steps that
disk cannot satisfy. It is printed on every `start`, seeded or not, because the browser
profile is independent of the sandbox and an agent on a fresh profile needs it whether
or not this particular `start` did the seeding — and from the already-running early
return as well as the readiness loop, since an agent that runs `start` twice must not get
different instructions the second time.

The already-running return also warns when the running server is **not this sandbox's**,
which it decides with `pidfile_process_alive "$BACKEND_PID"` — the same live-process and
command-name filter `stop_from_pidfile` uses before it signals anything, factored out so
the two cannot drift. Seeding runs only on the path below the early return, so somebody
else's server on these ports would otherwise report success in silence and leave the agent
driving a different sandbox's app, with `verify_seed_loaded` quietly querying the wrong
backend.

Ownership is the question, so it is asked directly rather than inferred from the seed
stamp. A stamp test gets this wrong in both directions: absent after any `do_seed`
bail-out — no fixture on this branch, a failed copy — it accuses a sandbox of driving
someone else's app while the hint below correctly names that sandbox's own project, two
statements contradicting each other in one block; and present on a seeded sandbox whose
server is somebody else's, where the warning is wanted and never comes.

**Three commands, in that order**, which is a correction against the two this document
originally specified. Verified from a cold browser profile: `localstorage-set` fails
outright when no browser is open, and re-running `open` against an already-open browser
starts a fresh context that discards what was just written — so neither ordering of that
pair works. The last step is `goto` and not `reload` because by then the page is sitting
on the task picker it was redirected to, and reloading that stays there.

The hint is gated on [`verify_seed_loaded`](#verify_seed_loaded) having confirmed the
project with the backend, not on `project.kiln` being on disk. `delete_project` in
`app/desktop/git_sync/git_sync_api.py` only deregisters the project — "does not delete the
files from disk", as its own docstring and the UI's confirm dialog both say — so a
disk-presence gate prints a hint naming a project the app does not have, and the agent
lands on `/setup`. That is the exact symptom the no-wrong-hint rule exists to prevent.

### `verify_seed_loaded`

Runs after both servers answer, on both `start` paths, whenever the sandbox has a
`$SEEDED_PROJECT_DIR/project.kiln` to ask about:

```bash
loaded_project_id=""

verify_seed_loaded() {
  local id body
  loaded_project_id=""
  [ -f "$SEEDED_PROJECT_DIR/project.kiln" ] || return 0
  id="$(json_field "$SEEDED_PROJECT_DIR/project.kiln" id)"
  body="$(curl -fsS --max-time 5 "$BACKEND_URL/api/projects" 2>/dev/null)"
  if [ -n "$id" ]; then
    case "$body" in
      *"\"$id\""*)
        loaded_project_id="$id"
        return 0
        ;;
    esac
  fi
  echo "warning: the seeded project is not loaded, so the app will show no projects" >&2
  echo "         and send you to /setup. Three things cause this:" >&2
  echo "           - you removed the project through the UI — expected, nothing to fix" >&2
  echo "           - this sandbox was seeded from an older fixture: run 'reset'" >&2
  echo "           - .agents/playwright_project is stale against this branch's" >&2
  echo "             datamodel: re-author it through the UI and run 'snapshot'" >&2
  echo "         No ui_state hint is printed below, because it would name a project" >&2
  echo "         the app does not have and land you on /setup anyway." >&2
}
```

Matching the id rather than checking for a non-empty array, so it also catches the case
where some *other* project loaded — and quoted, so one id cannot match inside another.
Never fails the server.

The id comes from the **installed copy**, not the committed fixture, which is a
correction against this document's original form. The question the check asks is "did the
thing in this sandbox load", and reading `$FIXTURE_DIR` asks a different one: after a
branch switch whose fixture has a different project id, the sandbox is perfectly healthy
and the check would fire and recommend re-authoring, when the answer is `reset`. That
scenario is not hypothetical — `USING_PLAYWRIGHT.md` tells people to `reset` "after
pulling a branch whose fixture differs".

The message names three causes rather than one, because two of them are states an agent
reaches on purpose and only the third is a stale fixture. An unreadable id lands here too:
it is a project the app cannot have loaded either.

`loaded_project_id` is the single source of truth shared with `print_seed_hint`. Having
each decide for itself was the original bug: the check warned that nothing had loaded
while the hint confidently named a project, in the same output.

This check earns its place because `get_projects` in `libs/server/kiln_server/project_api.py`
catches every per-project load exception and continues. Without it, a stale fixture is
an app with zero projects and an agent redirected to `/setup` — visually identical to
seeding never having run, and the hardest possible thing to diagnose from the outside.
One assertion against a server we already wait for turns it into a sentence naming the
cause and the fix.

### `do_reset`

```
guard_not_real_home       → abort on failure
do_stop                   → abort if it reports something still answering
if [ -d "$RUN_DIR" ]      → nothing to delete is not an error
  guard_not_real_home     → again, where cd cannot fail; abort on failure
  rm -rf "$RUN_DIR"       → the stamp goes with it
do_start                  → seeds, because the stamp is gone
```

Stopping precedes the wipe because the backend holds the directory open, and a failure
to stop aborts before anything is deleted rather than wiping the home out from under a
live server.

`reset` is the only path that re-seeds. There is deliberately no drift detection: an
agent must be able to make a mess across many `start`/`stop` cycles without the next
`start` quietly reverting it, and pulling in an updated fixture is a rare deliberate
act.

### `do_snapshot`

```bash
while IFS= read -r -d '' kiln; do
  count=$((count + 1))
  [ "$count" -eq 1 ] && first="$kiln"
  listing="$listing         $kiln
"
done < <(find "$PROJECTS_DIR" -mindepth 2 -maxdepth 2 -name project.kiln -print0 2>/dev/null)
```

`-print0` with `read -d ''` because project directory names contain spaces by
construction. A read loop rather than `mapfile -d ''`, which this document originally
specified: `-d` needs bash 4.4, stock macOS `/bin/bash` is 3.2, and under `set -u` the
resulting unset array aborts with `unbound variable` rather than printing a message —
which contradicts the portability argument made for avoiding `realpath` a few sections up.
Counting instead of building an array also sidesteps bash's pre-4.4 quirk where
`${#arr[@]}` on an empty array is itself an unbound-variable error.

Exactly one match is required: zero is "nothing to capture", more than one lists what it
found and stops, since picking one silently would be a coin flip over which state gets
committed. The listing goes through `sort` so that whoever is deciding which project to
delete sees a stable order rather than whatever the filesystem handed back.

Then, before deleting anything:

```bash
case "$FIXTURE_DIR" in
  */.agents/playwright_project) ;;
  *) echo "error: refusing to mirror into $FIXTURE_DIR" >&2; return 1 ;;
esac
```

An assertion on the shape of the path, because the next statement is `rm -rf` on a
variable and a mistake there deletes something that is not this fixture.

The mirror itself:

```bash
rm -rf "$FIXTURE_DIR"
mkdir -p "$FIXTURE_DIR"
cp -R "$src_dir/." "$FIXTURE_DIR/"
find "$FIXTURE_DIR" -name .git -prune -exec rm -rf {} +
find "$FIXTURE_DIR" -name .DS_Store -delete
```

Delete-then-copy rather than a merge: a run deleted through the UI must disappear from
the repo, and a merge would strand it there forever. `cp -R` plus a post-clean rather
than `tar --exclude` — the exclusion list is two entries and the intent reads plainly.

A `.git` committed here becomes a gitlink that breaks the fixture for everyone who checks
it out, so it is scrubbed at any depth — the same recursive form as the `.DS_Store`
cleanup, since a top-level-only `rm -rf` would leave one inside a task directory. No
`-type` filter either: `git worktree add` and submodules make `.git` a regular *file*
holding `gitdir: …`, and git treats that as a repository boundary exactly as it does a
directory, so filtering on directories would let the same hazard through in its other
shape.

The originally documented reason for the scrub, that git-sync can put a repository inside
a project directory, is **wrong** and is corrected here: git-sync clones live at
`~/.git-projects/<id> - <name>/`, outside the `Kiln Projects` tree `snapshot` searches, so
a git-synced project can never be `src_dir`. The scrub stays anyway, because someone
experimenting by hand inside the sandbox project can create one and it costs a single
`find`.

The same fact has a consequence worth writing down while git-sync is out of scope:
`snapshot` against a sandbox whose only project is git-synced reports "no project found
under …/Kiln Projects".

`settings.yaml` is never read or written by `snapshot`. It lives outside the project
directory anyway, and this is the property that keeps the authoring provider's API key
out of the repo by construction rather than by anyone remembering.

Afterwards it prints `git status --short -- "$FIXTURE_DIR"` and a reminder to review the
diff for files that were not meant to be captured. It does not refuse to run against a
dirty destination; git is the safety net and the printed status is how you see what
happened.

## Error handling

The governing rule: **seeding never fails the server.** An agent that asked for a
browser gets one, and a warning on stderr explains why the app looks emptier than
expected. Only the two genuinely destructive preconditions abort.

| Situation | Behavior | Exit |
|---|---|---|
| Run directory is the real home | Refuse before touching anything | non-zero |
| Run directory resolves to the real home only once created | Refuse at the post-`mkdir` re-check, before any content is written. The `mkdir -p` that makes the path resolvable does leave its empty directories (`$HOME/sandbox`, `$HOME/a/b`) behind — no settings, no project, nothing overwritten | non-zero |
| `HOME` unset, so the guard cannot compare | Refuse before touching anything | non-zero |
| Ports already answering, but this sandbox was never seeded | Warn that the app belongs to another sandbox | 0 |
| `snapshot` finds zero or multiple projects | Error, change nothing | non-zero |
| `snapshot` destination path fails the shape assertion | Error, change nothing | non-zero |
| `reset` cannot stop a running server | Abort before the wipe | non-zero |
| Fixture missing or has no `project.kiln` | Warn, start empty | 0 |
| Copy or settings write fails mid-seed | Warn, no stamp written, start anyway | 0 |
| Seeded project not in `/api/projects` — removed, older fixture, or stale | Warn naming all three causes, print no `ui_state` hint | 0 |
| Project id unreadable | Same path as above: it cannot have loaded either | 0 |
| Project loaded but no task id readable | Warn, print no `ui_state` hint | 0 |

## Testing strategy

No automated test loads the fixture — a decision, not an oversight. The rot it would
catch is instead surfaced at the moment it matters by `verify_seed_loaded`.

`checks.sh` covers Python and web; it does not lint shell. So these changes are
verified by running them, against this matrix, in-container:

| # | Setup | Expected |
|---|---|---|
| 1 | Fresh home, `start` | Seeds; the printed three-command hint lands the browser in the app, not `/setup` |
| 2 | `start` again, both already-running and after a `stop` | No re-seed; a change made in the UI survives; both paths print the same block |
| 3 | Remove the project through the UI, `start` | Not resurrected, **and no `ui_state` hint printed** on either path |
| 4 | `reset` | Fixture back, UI changes gone |
| 5 | `snapshot` after a UI edit | Fixture mirrors it; `git status` shows only intended files |
| 6 | `snapshot` with zero, then three projects | Errors both times, fixture untouched |
| 7 | `KILN_DEV_HOME=$HOME start` (and `reset`, `snapshot`) | Refused, nothing written |
| 7b | `KILN_DEV_HOME=$HOME/sandbox/..` with `sandbox` **not existing** | Refused, nothing written into the home |
| 8 | Fixture directory moved aside, `start` | Warns, server still comes up |
| 9 | Seeded copy's `project.kiln` made **valid JSON that fails datamodel validation**, `start` | Warns, no hint, server up |
| 10 | `stop`, `status` | Unchanged from today |
| 11 | Mid-seed failure, then `start` again | Re-seeds without nesting a second copy; `snapshot` stays clean |
| 12 | `start` while **another sandbox's** server holds the ports, seeded or not | Warns that the app belongs to a different sandbox |
| 13 | `start` while **this sandbox's own** server is up, with and without a seed stamp | No ownership warning either way |

Cases 7 and 9 need care. 7 and 7b must be checked with a disposable `HOME`, never the real
one — 7b in particular writes into that home if the guard is wrong, which is the whole
point of the case.
9 must corrupt the *seeded copy* rather than the committed fixture, and must do it by
deleting a required key rather than mangling the syntax: syntax damage only exercises the
unreadable-id branch, while the real stale fixture is valid JSON whose `id` reads fine and
whose load fails inside the datamodel. That distinction matters — the weaker version of
this case is what let a confidently-wrong `ui_state` hint through review.

## Fixture authoring

The authoring phase is the bulk of the wall-clock time and needs a shape, not just a
list.

**The agent asks the user for the OpenRouter key when the phase begins.** It is not
recorded in any planning artifact. It is connected through the UI like a user would,
which writes it to the sandbox's `settings.yaml` — inside the gitignored
`.agent_dev_home`, and outside anything `snapshot` reads.

All generation uses `deepseek/deepseek-v4-flash-0731`.

**Everything is created through the UI.** Not by hand-editing fixture files, not
through the REST API, wherever the UI can do it. This is the project we look at through
a browser, and state created the way a user creates it looks the way a user's looks. A
deviation is allowed with a good reason and is worth a line in the commit message.

**Two things about onboarding that every authoring phase hits**, discovered in phase 1 and
durable, not a phase-1 anecdote:

- **Registration cannot be completed in-container.** `/setup/register_personal` posts to
  `api.kiln.tech`, which the container cannot reach, so the form fails with "Unexpected
  error: Failed to fetch". The way past it is to write `user_type: personal` and
  `personal_use_contact` into the *sandbox's* `settings.yaml` — which is exactly what
  `write_seed_settings` does, so a seeded sandbox is already past this gate and only a
  from-scratch sandbox needs the manual write. Settings are never captured by `snapshot`,
  so this cannot reach the repo.
- **Reaching the create-project screen requires a connected provider.** The Continue
  button on `/setup/connect_providers` is bound to `has_connected_providers`, and a full
  page load of any `/setup/*` URL bounces to `/setup` because the root layout's
  `check_needs_setup` runs on mount — so there is no way to skip the step by navigating.
  A placeholder **Custom API** (name plus base URL, no key, no validation call on save)
  satisfies it without an external service. It lives only in the sandbox's settings.

Neither applies once the fixture exists: a seeded sandbox starts past both gates. They
matter when authoring from an empty home, and they are why "everything through the UI"
has this one standing exception.

**Two things about driving the app that every authoring phase hits**, discovered in phase 2
and durable, not phase-2 anecdotes:

- **One label can match a menu item and the submit button of the dialog it opens.** On the
  Dataset screen's bulk tag menu, `getByRole('button', { name: 'Add Tags' })` resolves to two
  elements and the click fails with a strict-mode violation; the dialog simply never appears.
  `find` first and click the returned ref, which is a single element by construction, or scope
  the locator tightly enough to be unique — `.dropdown-content button >> nth=0`, since plain
  `.dropdown-content button` matches both menu items and violates strict mode in its own
  right. **`playwright-cli` prints that failure on stdout and exits 1**, so `>/dev/null` (or
  `>/dev/null 2>&1`) discards the one message that names both matches and the fix; `2>/dev/null`
  alone does not. Keep the output, or at least check `$?`. There is no exception to "everything
  through the UI" here: the ordinary two-command path works, including across a DaisyUI
  `dropdown`, because `playwright-cli` holds one persistent session and the trigger keeps focus,
  so an open menu is still open in the next process.
- **The Repair Output section never renders for an already-rated run until the rating is
  changed — which looks like a bug in the app, not a fact about authoring.** On a run loaded
  from disk with `output.rating.value` of 1–4, `output.source.type` of `synthetic` and no
  `repaired_output`, every condition `should_offer_repair` and `repair_enabled_for_source`
  test in `app/web_ui/src/routes/(app)/run/run.svelte` is satisfied, and the star widget
  renders the stored rating — yet `document.body.innerText` contains no "Repair Output" and
  there is no `#repair_instructions` field. Three things were measured, and they narrow it:

  - Waiting does not help. Reproduced after `waitForLoadState('networkidle')`, so it is not a
    paint race.
  - An unrelated interaction does not help either. Toggling "Show Raw Data" schedules an
    update pass and the section still does not appear — so this is *not* "any later event
    recomputes it".
  - Only invalidating the rating helps. That points at `overall_rating` being assigned inside
    `load_server_ratings()` rather than syntactically within a `$:` block, so the statements
    derived from it keep a stale value until something dirties `overall_rating` again.

  The workaround therefore costs a rating round trip. The star widget **toggles**: clicking the
  star a run already carries *clears* the rating (and still shows nothing, since the section
  also needs a non-null rating); clicking it a second time re-sets the original value and the
  section appears. The rating record keeps its `id` and `created_at` throughout — verified by
  round-tripping run `122030456526` from 4 to unrated and back and confirming the fixture was
  byte-identical afterwards — so this is recoverable, but a phase that does it must put the
  original value back and re-`snapshot` to prove it did. Treat this as working around a defect
  worth fixing, not as the way the screen is meant to behave.

**Resumability comes from `snapshot` itself**, which needs no new mechanism: author a
group, `snapshot`, commit. A session that dies loses at most one group, and the
repetition exercises `snapshot` far harder than a single capture at the end would. The
phase plan file the coding agent writes holds the checklist and the progress marks.

Content groups, in order — each one ends in `snapshot` and a commit:

1. **Foundation.** Project, the structured task (JSON input *and* output schemas), the
   plain-text task. Create the structured task first: `print_seed_hint` uses the
   earliest-created task, and that is the one an agent should land on.
2. **Runs and ratings.** 15–20 runs weighted to the structured task; ratings spread
   high, low, and deliberately absent, because unrated runs are what dataset filters
   and split screens need in order to show anything; at least one repair; two run
   configs on the structured task, since comparison screens need two.
3. **Prompt, split, transform, feedback.** One saved prompt, one dataset split, one
   input transform, feedback on a run.
4. **Evals.** One eval with a judge config and results across both run configs. Carries
   specs with it: the create-eval flow produces a `Spec` child of the task, which
   `Eval.associated_spec()` matches back by `eval_id`, and only that flow yields a
   non-legacy one.
5. **Skills and RAG.** One or two skills with `SKILL.md` bodies. Then the chain:
   documents, extractor config, chunker config, embedding config, vector store config,
   RAG config — **and the outputs of running that chain**, per the section below.

Documents are real files committed as attachments, so they stay small and textual.

### What group 5 commits, and what it deliberately does not

A user directive during phase 3 corrects an understatement in the original text of this
document, which said only that `snapshot` "captures configs and never the index". That is
right about the index and wrong about everything else the chain produces. Running a RAG
config produces four kinds of artifact, and **three of them live inside the project
directory**:

| Artifact | Where it lands | Captured by `snapshot` |
|---|---|---|
| `Extraction` + its output attachment | `documents/<doc>/extractions/<id>/` | yes |
| `ChunkedDocument` + a content attachment per chunk | `…/extractions/<id>/chunked_documents/<id>/` | yes |
| `ChunkEmbeddings` — the vectors | `…/chunked_documents/<id>/chunk_embeddings/<id>/` | yes |
| The LanceDB index | `<home>/.kiln_ai/rag_indexes/lancedb/<rag_config_id>` | no — outside the project |

The nesting is the datamodel's: `Project` is `parent_of` `documents`, `Document` of
`extractions`, `Extraction` of `chunked_documents`, `ChunkedDocument` of
`chunk_embeddings`. The index path is `LanceDBAdapter.lancedb_path_for_config`.

So the split is: **extraction and embedding are run in this repo and their outputs are
committed; the index is not.** In the user's framing, "the same approach is used by sync:
the embeddings and extracted docs are synced, but index is locally cached artifact."

The obligation on group 5 is therefore not merely "prove the index rebuilds". It is to
**run extraction and then embedding creation so their outputs land in the fixture**, and
then prove that a seeded sandbox rebuilds the index from those committed outputs. A
fixture holding only the five configs would leave the rebuild depending on live extraction
and embedding calls — which is exactly what a seeded sandbox with no API key cannot make.

`RagIndexingStepRunner.collect_records` is what makes the offline rebuild possible: it
walks documents → extractions → chunked documents → chunk embeddings on disk and inserts
what it finds, calling no model. A `lancedb_hybrid` or `lancedb_vector` *search* is a
different matter — `RagTool.search` embeds the query for those two store types — so a
keyless sandbox rebuilds the index but cannot query a vector-backed one.

Group 5 also carries the project's two open risks, which is why it is last:

- **OpenRouter embeddings were unproven** at design time. Kiln rewrites the slug
  `openrouter/…` to `openai/…` and calls OpenRouter as an OpenAI-compatible endpoint,
  because LiteLLM has no native OpenRouter embedding support, and that was read from the
  code rather than run. Phase 4 ran it: OpenRouter serves `/embeddings` for
  `openai/text-embedding-3-small`. Should a future model or provider fail here, ask the
  user for another key rather than substituting a provider — the models the fixture is
  built with are the user's call, as phase 2 established for generation.
- **The RAG index must be shown to rebuild**, from the committed extractions and
  embeddings above and with no provider connected. `reset` to a seeded sandbox, run the
  seeded RAG config, and confirm it indexes and then queries. A config whose index cannot
  be rebuilt only looks configured, and shipping one would be worse than shipping none.

One more fact about extraction that any future authoring phase hits: the create-extractor
form posts `passthrough_mimetypes: ["text/plain", "text/markdown"]` and offers no control
over it, so a markdown or plaintext document is copied through by
`BaseExtractor._should_passthrough` and the extractor's model is never called. Extraction
still produces a full `Extraction` record and output attachment. A fixture of markdown
documents therefore names an extraction model it does not exercise.

## Rejected alternatives

**A pytest that loads the fixture.** Declined. `verify_seed_loaded` catches the same rot
at the moment an agent would be confused by it, without a test whose failure mode is a
red CI on an unrelated PR.

**Re-seeding when the fixture changes.** An explicit anti-goal. An agent has to be free
to make a mess without the next `start` reverting it.

**A generator script instead of committed data.** Considered seriously: it cannot go
schema-stale, since it runs against the current datamodel. Rejected because it would
duplicate in code what the app already does, and every feature author would have to
learn the datamodel to extend the fixture. Nobody would. Committed data plus `snapshot`
makes extending it "click around, run one command, commit."

**A separate `demo_project` repo.** The fixture is coupled to the datamodel and has to
version with it in lockstep. In-repo, a required new field breaks in the PR that adds
it. Across repos you need a pin, the pin goes stale, and the fix becomes two PRs.

**A Python helper for parsing and settings.** The two fragile operations are reading
JSON and writing YAML, and a real parser would remove both risks. Rejected once the
on-disk probe showed how narrow the parsing actually is — one scalar from a
pretty-printed file, guarded by "no hint rather than a wrong hint" — and the YAML being
written is four lines with one escaping rule. Not worth a second language, a venv
dependency in `snapshot`, or the cross-language handoff.

**Overriding `HOME` for the frontend too.** `npm run dev` deliberately keeps the real
home so it can use the real npm cache. It writes no Kiln data. Worth stating so nobody
assumes total process isolation and is surprised.
