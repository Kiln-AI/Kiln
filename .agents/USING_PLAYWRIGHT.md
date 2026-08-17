# Using Playwright

Two separate things share one browser install:

- **`npm run tests:e2e`** — the end-to-end suite, in `app/web_ui/tests/e2e`.
- **`playwright-cli`** — a browser you drive from the shell, for looking at the UI
  you are changing and taking screenshots of it.

If neither works, the install is probably missing — see the bottom of this file.

## Running the e2e suite

From `app/web_ui`:

```bash
npm run tests:e2e                                    # everything
npx playwright test tests/e2e/act_sanity.spec.ts     # one spec
npx playwright test tests/e2e/act_sanity.spec.ts -g "install verification"
npx playwright test --reporter=line                  # readable in a terminal
```

You do not start anything first. `playwright.config.ts` boots four servers itself
and shuts them all down at the end:

| Server | What it is |
|---|---|
| `uv run python -m app.desktop.dev_server` | the real Python backend |
| `vite dev` | the web UI |
| `tests/e2e/mock_provider` | a stand-in inference provider, so no test calls a real model |
| `tests/e2e/mock_kiln_server` | a stand-in for api.kiln.tech |

Two consequences worth knowing before you debug a failure:

- **The suite is serial.** `fullyParallel: false` and `workers: 1`, because every
  test shares one backend. A test that leaves state behind can break the next one.
- **It cannot touch your real Kiln data.** The backend runs with `HOME` pointed at
  `app/web_ui/.e2e_home`, which is wiped on every run. The suite also sets
  `reuseExistingServer: false`, so it will not attach to a server you already
  have running — and will fail if one is holding its ports (6534-6537).

### Reading the report

The default reporter is `html`. After a run:

```bash
npx playwright show-report            # opens a browser; needs a display
```

In a container, read the files directly instead. For each failure Playwright
writes an accessibility snapshot of the page at the moment it gave up:

```bash
cat test-results/<test-name>/error-context.md
```

That snapshot is usually enough on its own — it shows whether the element was
missing, renamed, or covered by something else. `--reporter=line` gives you the
failure text without generating a report at all.

### First run on a route can be slow

`vite dev` compiles a route the first time a test navigates to it, and that
compile can take several seconds on a cold checkout. Assertions using the default
5 s `expect` timeout can lose that race, so a test that fails once and passes on a
re-run is usually this rather than a real bug. `--repeat-each=2` tells the two
apart: cold-compile failures fail the first repetition and pass the second.

## Driving the UI with playwright-cli

`playwright-cli` is a browser as a shell command — one persistent session that
each command acts on. Use it to check your own UI work, not as a test framework.
Claude Code has a `playwright-cli` skill installed with the full command list;
`playwright-cli --help` is the same reference.

It needs something to point at, so start a server first:

```bash
.agents/scripts/playwright_server.sh start     # prints http://localhost:6544
```

That script runs the backend and the web UI on 6544/6545 — deliberately not the
suite's ports, so it can stay up while you run e2e tests. It keeps its data in
`app/web_ui/.agent_dev_home`, so it will not touch real Kiln projects. On the
first `start` it seeds that sandbox with a committed project so the screens have
data in them — see [The seeded project](#the-seeded-project). `stop` when you are
done; `status` if you are not sure; `reset` for a clean sandbox and `snapshot` to
capture one back into the repo.

Then:

```bash
playwright-cli open http://localhost:6544   # start the browser and navigate
playwright-cli snapshot                     # the page as an accessibility tree
playwright-cli find "Generate Eval Data"    # search a big snapshot instead
playwright-cli click e44                    # refs (e44) come from the snapshot
playwright-cli screenshot --filename=/tmp/ui.png
playwright-cli console                      # console messages
playwright-cli requests                     # network activity
playwright-cli close
```

If `open` fails saying Chromium distribution `chrome` was not found, the config
below is missing. Without it playwright-cli launches a branded Google Chrome,
which no container has. `--browser=chromium` is the one-off workaround; the fix
is `setup_env.sh --add-playwright`.

That config lives at `~/.playwright/cli.config.json` — playwright-cli's global
config, not a file in the repo, because which browser is installed is a fact
about your machine. Both setup scripts write it, and only when it is missing, so
your own edits survive. Being global is also what makes the commands above work
from any directory rather than only the repo root.

### Screenshots: never trust the first frame

A screenshot taken immediately after `open` or `goto` is very often **blank
white**, and nothing in the output says so. The DOM is complete by then —
`snapshot` returns the full page and `document.readyState` is `"complete"` — but
Chromium has not painted yet, so `snapshot` is *not* a usable gate for it.

This matters because a blank frame is the normal signal that an app failed to
start, so a false blank will have you reporting a working app as broken. Settle
the page first:

```bash
playwright-cli run-code "async page => await page.waitForLoadState('networkidle')"
playwright-cli screenshot --filename=/tmp/ui.png
```

`networkidle` is the right default here: Kiln's pages fetch from the API after
hydrating, so it waits for the data as well as the paint. If you only need the
paint and not the data, two animation frames are enough:

```bash
playwright-cli run-code "async page => await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))))"
```

`snapshot` is the one to reach for by default: it is the page as structure and
text, which is both cheaper to read than an image and closer to what the e2e
locators actually match. Take a **screenshot when the question is visual** —
spacing, alignment, color, whether something overlaps — then read the PNG back
with the Read tool, which renders it.

### Let `find` tell you the role

Do not guess a role from how something looks. Kiln styles links as buttons, so
`getByRole("button", { name: "Get Started" })` finds nothing where
`find "Get Started"` returns `link "Get Started" [ref=e9]` — the ref and the true
role in one call. Run `find` first, then write the locator from what it reports.

### A dropdown menu will not survive two commands

Kiln's bulk actions — the tag and delete menus on the Dataset screen, and anything
else with `class="dropdown"` — are DaisyUI dropdowns, which open on focus and close
on blur. Each `playwright-cli` command is its own process, so `click` the trigger
and then `click` the item never works: the menu is already gone. Nothing in the
output says so; you just get no dialog.

Click the item in-page instead, in the same command that has it open:

```bash
playwright-cli click "div.dropdown [role=button]"
playwright-cli run-code "async page => await page.evaluate(() => \
  [...document.querySelectorAll('.dropdown-content button')] \
    .find(b => b.innerText.trim() === 'Add Tags').click())"
```

Only the menu item needs this. A dialog the item opens is an ordinary dialog once
it is up, and `find` plus `click` work on it normally.

## The seeded project

`start` copies `.agents/playwright_project` into the sandbox, so you get an app
with a project and tasks already in it instead of an onboarding wizard. It is a
copy: click around, break things, delete things — the checkout is untouched.

The fixture is a support-ticket-triage project with two tasks, one with JSON input
and output schemas and one plain text, because structured and unstructured tasks
render differently in a lot of places.

It is not only task definitions. Both tasks carry runs — 20 of them, weighted to the
structured task — so the dataset, prompt and run-configuration screens have something
in them before you touch anything. On the structured task that means three saved run
configurations (zero-shot, chain-of-thought, and one pairing a custom saved prompt
with a Jinja input transform), ratings spread deliberately across high, low and
unrated, one repaired run, one run carrying human feedback, and a train/test/val
dataset split over the runs tagged `fine_tune_triage`. If a screen you are working on
comes up empty, check what the fixture holds before assuming the screen is broken.

### Landing in the app

Getting past the app's setup gate takes browser state as well as disk state: the
selected project and task live in `localStorage`, and the layout redirects to a
task picker on mount without them — whatever URL you asked for. `start` prints the
exact commands, with the seeded ids filled in:

```bash
playwright-cli open http://localhost:6544
playwright-cli localstorage-set ui_state \
  '{"current_project_id":"<id>","current_task_id":"<id>","selected_model":null}'
playwright-cli goto http://localhost:6544
```

All three, in that order. `localstorage-set` fails outright with no browser open,
and running `open` a second time starts a fresh context that throws away what you
just wrote — so `open` first, then write, then navigate again. Use `goto` for that
last step rather than `reload`: by then the page is sitting on the task picker it
was redirected to, and reloading that just stays there.

Once `ui_state` is set, `goto` any deep link you like — `/dataset/<project_id>/<task_id>`,
`/generate/<project_id>/<task_id>`, and so on.

If `start` warns that the seeded project is not loaded, it also stops printing the
hint — a hint for a project the app does not have would just land you on `/setup`.
The warning names the three causes: you removed the project yourself (nothing to
fix), the sandbox was seeded from an older fixture (`reset`), or the committed
fixture has gone stale against this branch's datamodel (re-author through the UI,
then `snapshot`).

### No provider is connected

A seeded sandbox has no API keys, so you cannot *execute* a new run in it. Seeded
data is just files the screens read, so the pages render it with nothing connected
— but if the feature you are working on needs a live model call, you have to
connect a provider by hand through the UI first.

### `playwright_server.sh reset` — start over

```bash
.agents/scripts/playwright_server.sh reset
```

Stops the server, deletes the sandbox, seeds it again, starts. This is the only
command that re-seeds: an ordinary `start` never reverts changes you made, however
many times you stop and start. Use `reset` when you want the committed fixture
back, or after pulling a branch whose fixture differs.

It deletes the whole sandbox home, `settings.yaml` included — so any provider you
connected by hand goes with it, and you will need to paste the key again.

### `playwright_server.sh snapshot` — improve the fixture

Not to be confused with `playwright-cli snapshot`, which prints the page.

When you have built state through the UI that future sessions should start from:

```bash
.agents/scripts/playwright_server.sh snapshot
```

It mirrors the sandbox's project over `.agents/playwright_project` and prints
`git status` for it. **Read that diff before committing.** A snapshot captures
whatever was in the sandbox, including files you did not mean to create, and a
deletion in the sandbox is a deletion in the repo.

Two rules if you are extending the fixture:

- **Create the data through the UI**, not by hand-editing files under
  `.agents/playwright_project` and not through the REST API. This is the project we
  look at through a browser, and state created the way a user creates it looks the
  way a user's looks. A manual edit is fine with a good reason — say so in the
  commit message.
- **Create the task you want agents to land on first.** The `ui_state` hint points
  at the earliest-created task in the project.

`snapshot` never reads or writes `settings.yaml`, which is where connecting a
provider puts your API key — so a key cannot reach the repo this way. It also
drops any `.git` it finds inside the project, at any depth and whether it is a
directory or the plain file a worktree or submodule leaves: if you initialized a
repo in there while experimenting, committing it would land a gitlink in the
fixture and break the checkout for everyone. Git-synced projects
are a different thing and never the source here — their clones live under
`~/.git-projects`, outside the `Kiln Projects` tree `snapshot` searches, so a
sandbox whose only project is git-synced reports "no project found".

One thing it does not scrub: Kiln stamps `created_by` with your OS username on
everything you create, so anything you author shows up in the diff under your
account name. The committed fixture says `root` because it was authored in a
container. If that is not what you want in a public repo, edit those fields before
committing.

## Nothing is installed

Neither the browser nor `playwright-cli` ships by default — together they are
~800 MB. `bash .config/utils/setup_env.sh --add-playwright` adds both; see that
script's `--help` for what it does and what a cloud environment needs.
