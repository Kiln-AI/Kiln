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
  "id": "312236893393",
  "created_at": "2026-08-17T15:35:08.682167Z",
  "created_by": "root",
  "name": "Support Ticket Triage",
  "description": "Triage inbound support tickets.",
  "model_type": "project"
}
```

Layout, with the project directory named by the seed and the task directory named by
the app:

```
Kiln Projects/playwright_project/project.kiln
Kiln Projects/playwright_project/tasks/847089358761 - Triage Ticket/task.kiln
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
  local resolved_run resolved_home
  resolved_run="$(cd "$RUN_DIR" 2>/dev/null && pwd -P)" || resolved_run="$RUN_DIR"
  resolved_home="$(cd "$HOME" 2>/dev/null && pwd -P)" || resolved_home="$HOME"
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
the comparison meaningful when the directory does not exist yet.

Called by `start`, `reset`, and `snapshot`. Not by `stop` or `status`, which write
nothing.

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
absolute: **when the id cannot be read, print a warning and no hint.** A wrong hint
sends the agent to the task picker, which is exactly the symptom of an unseeded
sandbox, so a confident wrong answer costs more than an admitted unknown.

### `do_seed`

Runs only when `is_seeded` is false, and only from `start` (`reset` wipes the stamp by
deleting the directory). Order matters:

1. `cp -R "$FIXTURE_DIR" "$SEEDED_PROJECT_DIR"`, after `mkdir -p "$PROJECTS_DIR"`.
2. `write_seed_settings "$SEEDED_PROJECT_DIR/project.kiln"`.
3. Write `$SEED_STAMP`, last.

The stamp is written last so that a failure at any earlier step leaves it absent and
the next `start` retries. Its contents are informational only — the date and the repo's
`git rev-parse --short HEAD` at seed time, so someone can find out how old a sandbox
is. **Nothing ever reads it back for comparison**; presence is the entire signal.

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
  local dir kiln
  for dir in "$SEEDED_PROJECT_DIR"/tasks/*/; do
    kiln="$dir/task.kiln"
    [ -f "$kiln" ] || continue
    printf '%s\t%s\t%s\n' \
      "$(json_field "$kiln" created_at)" \
      "$(json_field "$kiln" id)" \
      "$(json_field "$kiln" name)"
  done | sort
}
```

Sorted by `created_at`, which is ISO-8601 with a `Z` suffix and therefore sorts
correctly as text. The earliest-created task is the primary one, the one the
paste-ready command uses. That rule is deterministic and, unlike sorting by id, it is
**controllable by whoever authors the fixture**: create the task you want an agent to
land on first. The rest are listed compactly with their ids so a different one is one
edit away.

`print_seed_hint` emits, alongside the existing ready message:

```
  Seeded project: Support Ticket Triage

  Land in the app (the layout redirects to a task picker without this):
    playwright-cli localstorage-set ui_state '{"current_project_id":"312236893393","current_task_id":"847089358761","selected_model":null}'
    playwright-cli open http://localhost:6544

  Other tasks: 193847562011 (Draft Reply)
```

This exists because the four-step gate in `routes/+layout.svelte` has two steps that
disk cannot satisfy. It is printed on every `start`, seeded or not, because the browser
profile is independent of the sandbox and an agent on a fresh profile needs it whether
or not this particular `start` did the seeding.

### `verify_seed_loaded`

Runs after both servers answer, and only when `fixture_present && is_seeded`:

```bash
verify_seed_loaded() {
  local id body
  id="$(json_field "$FIXTURE_DIR/project.kiln" id)"
  [ -n "$id" ] || return 0
  body="$(curl -fsS --max-time 5 "$BACKEND_URL/api/projects" 2>/dev/null)"
  case "$body" in
    *"$id"*) return 0 ;;
  esac
  echo "warning: the seeded project did not load." >&2
  echo "         .agents/playwright_project is probably stale against this branch's" >&2
  echo "         datamodel. The app will show no projects and send you to /setup." >&2
  echo "         Re-author it through the UI and run 'playwright_server.sh snapshot'." >&2
}
```

Matching the id rather than checking for a non-empty array, so it also catches the case
where some *other* project loaded. Never fails the server.

This check earns its place because `get_projects` in `libs/server/kiln_server/project_api.py`
catches every per-project load exception and continues. Without it, a stale fixture is
an app with zero projects and an agent redirected to `/setup` — visually identical to
seeding never having run, and the hardest possible thing to diagnose from the outside.
One assertion against a server we already wait for turns it into a sentence naming the
cause and the fix.

### `do_reset`

```
guard_not_real_home  → abort on failure
do_stop              → abort if it reports something still answering
rm -rf "$RUN_DIR"    → the stamp goes with it
do_start             → seeds, because the stamp is gone
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
mapfile -d '' -t found < <(
  find "$PROJECTS_DIR" -mindepth 2 -maxdepth 2 -name project.kiln -print0 2>/dev/null
)
```

`-print0` with `mapfile -d ''` because project directory names contain spaces by
construction. Exactly one match is required: zero is "nothing to capture", more than one
lists what it found and stops, since picking one silently would be a coin flip over
which state gets committed.

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
rm -rf "$FIXTURE_DIR/.git"
find "$FIXTURE_DIR" -name .DS_Store -delete
```

Delete-then-copy rather than a merge: a run deleted through the UI must disappear from
the repo, and a merge would strand it there forever. `cp -R` plus a post-clean rather
than `tar --exclude` — the exclusion list is two entries and the intent reads plainly.

`.git` matters more than it looks: git-sync can put a repository inside a project
directory, and a nested `.git` committed here becomes a gitlink that breaks the fixture
for everyone who checks it out.

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
| `snapshot` finds zero or multiple projects | Error, change nothing | non-zero |
| `snapshot` destination path fails the shape assertion | Error, change nothing | non-zero |
| `reset` cannot stop a running server | Abort before the wipe | non-zero |
| Fixture missing or has no `project.kiln` | Warn, start empty | 0 |
| Copy or settings write fails mid-seed | Warn, no stamp written, start anyway | 0 |
| Project id unreadable | Warn, print no `ui_state` hint | 0 |
| Seeded project does not load | Warn naming stale fixture and `snapshot` | 0 |

## Testing strategy

No automated test loads the fixture — a decision, not an oversight. The rot it would
catch is instead surfaced at the moment it matters by `verify_seed_loaded`.

`checks.sh` covers Python and web; it does not lint shell. So these changes are
verified by running them, against this matrix, in-container:

| # | Setup | Expected |
|---|---|---|
| 1 | Fresh home, `start` | Seeds; `ui_state` + `open` lands in the app, not `/setup` |
| 2 | `start` again | No re-seed; a change made in the UI survives |
| 3 | Delete the project through the UI, `start` | Not resurrected |
| 4 | `reset` | Fixture back, UI changes gone |
| 5 | `snapshot` after a UI edit | Fixture mirrors it; `git status` shows only intended files |
| 6 | `snapshot` with zero, then two projects | Errors both times, fixture untouched |
| 7 | `KILN_DEV_HOME=$HOME start` (and `reset`, `snapshot`) | Refused, nothing written |
| 8 | Fixture directory moved aside, `start` | Warns, server still comes up |
| 9 | `project.kiln` corrupted, `start` | Warns with the stale-fixture message, server up |
| 10 | `stop`, `status` | Unchanged from today |

Cases 7 and 9 need care: 7 must be checked with a disposable `HOME`, never the real
one, and 9 by corrupting the *seeded copy* rather than the committed fixture.

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
   RAG config.

Group 5 carries the project's two open risks, which is why it is last:

- **OpenRouter embeddings are unproven.** Kiln rewrites the slug `openrouter/…` to
  `openai/…` and calls OpenRouter as an OpenAI-compatible endpoint, because LiteLLM has
  no native OpenRouter embedding support. That is read from the code, not run. If
  OpenRouter does not serve `/embeddings`, this group needs a second key — ask the user
  rather than substituting a provider.
- **The RAG index must be shown to rebuild.** It lives at
  `.kiln_ai/rag_indexes/lancedb/<id>`, outside the project directory, so `snapshot`
  captures configs and never the index — by design, the index being derived data. The
  obligation is to prove it: `reset` to a seeded sandbox, rebuild from the seeded
  config, and confirm it indexes and queries. A config whose index cannot be rebuilt
  only looks configured, and shipping one would be worse than shipping none.

Documents are real files committed as attachments, so they stay small and textual.

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
