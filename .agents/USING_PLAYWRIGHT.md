# Using Playwright

Two separate things share one browser install:

- **`npm run tests:e2e`** — the end-to-end suite, in `app/web_ui/tests/e2e`.
- **`playwright-cli`** — a browser you drive from the shell, for looking at the UI
  you are changing and taking screenshots of it.

If neither works, the install is probably missing. See
[Installing](#installing) at the bottom.

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
.agents/scripts/dev_server.sh start     # prints http://localhost:6544
```

That script runs the backend and the web UI on 6544/6545 — deliberately not the
suite's ports, so it can stay up while you run e2e tests. It keeps its data in
`app/web_ui/.agent_dev_home`, so it will not touch real Kiln projects.
`stop` when you are done; `status` if you are not sure.

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

Kiln stores the selected project and task in `localStorage`, and redirects to a
task picker without it. To land directly on a task's page, do what the e2e
fixtures do:

```bash
playwright-cli localstorage-set ui_state \
  '{"current_project_id":"<id>","current_task_id":"<id>","selected_model":null}'
playwright-cli goto http://localhost:6544/generate/<project_id>/<task_id>
```

## Installing

Neither the browser nor `playwright-cli` is installed by default — together they
are ~800 MB, and most work in this repo needs neither. To add them:

```bash
bash .config/utils/setup_env.sh --add-playwright
```

The e2e suite needs the exact Chromium revision `app/web_ui`'s `@playwright/test`
pins. This is the failure worth recognizing: when some *other* Chromium is
installed, Playwright reports a browser that was never installed and tells you to
run `npx playwright install` — the real problem is a version mismatch, not a
missing install. `setup_startup.sh` checks for the pinned revision at the start of
every session and names it, so you should see that before you see Playwright's
version of the story.

Nothing in the repo overrides the browser path. `--add-playwright` installs the
revision Playwright already looks for, which is what keeps sandbox results the
same as CI's.

### Cloud sandboxes

Two things have to be true, and neither is visible from inside a session:

1. **The environment needs Custom network access** with `cdn.playwright.dev` in
   its allowed domains (`playwright.download.prss.microsoft.com` too, for the
   Firefox and WebKit fallbacks). On the default Trusted policy the downloads get
   a 403 from the proxy.
2. **The environment's setup script must install the browsers.**
   `.config/utils/setup_cloud.sh` is what belongs in that field: it fetches
   `setup_env.sh` from `main` and runs it with `--add-playwright`, so later
   changes to `setup_env.sh` take effect without anyone re-pasting anything. An
   environment still holding a pasted copy of `setup_env.sh` needs that copy
   replaced with `setup_cloud.sh` once — or, failing that, re-pasted with
   `ADD_PLAYWRIGHT=true` in its CONFIGURATION block.

Installing during the VM build is what puts the browser in the environment's
filesystem snapshot, so every later session starts with it already on disk.
