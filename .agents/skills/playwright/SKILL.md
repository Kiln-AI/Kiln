---
name: playwright
description: Look at Kiln's UI in a real browser, and run its end-to-end tests. Use when checking UI you are changing, taking a screenshot of the app, driving the app with playwright-cli, starting the dev sandbox with playwright_server.sh, running or debugging `npm run tests:e2e`, or working with the seeded fixture project that gives the app's screens data to render.
---

# Using Playwright with Kiln

Two separate things share one browser install:

- **`playwright-cli`** — a browser you drive from the shell, for looking at the UI
  you are changing and taking screenshots of it. This is what you want when
  building UI.
- **`npm run tests:e2e`** — the end-to-end suite, in `app/web_ui/tests/e2e`.

If neither works, the install is probably missing: `bash .config/utils/setup_env.sh
--add-playwright` adds the browser and `playwright-cli` (~800 MB together). See that
script's `--help` for what a cloud environment needs.

## Looking at the UI

Start a server, open the app, and land on a page with data in it:

```bash
.agents/scripts/playwright_server.sh start     # prints http://localhost:6544
```

`start` prints the next three commands with the seeded ids already filled in. Run
all three, in that order — the app redirects to a task picker without the
`localStorage` state, whatever URL you ask for:

```bash
playwright-cli open http://localhost:6544
playwright-cli localstorage-set ui_state \
  '{"current_project_id":"<id>","current_task_id":"<id>","selected_model":null}'
playwright-cli goto http://localhost:6544
```

Then `goto` any deep link you like. `stop` when you are done, `status` if you are
not sure what is running.

The sandbox keeps its data in `app/web_ui/.agent_dev_home` and is seeded from a
committed fixture project, so the screens have content instead of an onboarding
wizard. It never touches real Kiln projects.

## A provider may be connected — spend it carefully

If `OPENROUTER_QA_KEY` is set in the environment, seeding writes it into the
sandbox's settings and the app comes up with OpenRouter connected, so live model
calls work. `start` reports it when it is there — assume nothing is connected
until it says so.

When it is connected, it is a real key on a hard, low limit — a runaway loop hits
it and the next person gets nothing. Use it when a live call is the only way to
check what you are working on, and:

- **Default to GPT-5.6 Luna.** The `ui_state` hint `start` prints already
  preselects it in the model dropdown, so running as-is costs you nothing and
  picks the cheap model. Change it only when the model itself is what you are
  testing.
- Keep every run minimal — one sample, one eval row, one query.
- Never aim a paid test suite at it (`pytest --runpaid` / `--runprerelease` read
  `OPENROUTER_API_KEY`, which is deliberately a different variable).
- Treat a 402 or 429 as budget exhausted: stop and report it, don't retry.

[references/seeded_project.md](references/seeded_project.md) has the details.

## Three rules that will cost you an afternoon otherwise

**Never trust the first frame.** A screenshot taken right after `open` or `goto` is
very often blank white, and nothing says so. `snapshot` is not a usable gate — the
DOM is complete before Chromium paints. Settle the page first:

```bash
playwright-cli run-code "async page => await page.waitForLoadState('networkidle')"
playwright-cli screenshot --filename=/tmp/ui.png
```

**Never redirect a `playwright-cli` failure into `/dev/null`.** It reports failures
on **stdout** and exits 1, so `>/dev/null 2>&1` — the thing you add to keep a
transcript readable — hides the entire reason a command failed. Discard output if
you must, but then test `$?`.

**Never guess a locator's role.** Kiln styles links as buttons. Run `find` first and
write the locator from what it reports — and prefer clicking the ref it gives you,
which is a single element by construction and cannot go strict-mode ambiguous.

## Reference

Load only what the task needs.

| File | When |
|---|---|
| [references/driving_the_ui.md](references/driving_the_ui.md) | The command surface, and the locator traps in Kiln's UI specifically — duplicate labels, dropdowns, collapsed sections |
| [references/e2e_suite.md](references/e2e_suite.md) | Running, reading, or debugging `npm run tests:e2e` |
| [references/seeded_project.md](references/seeded_project.md) | What the fixture contains, screen by screen, and whether a model provider is connected. Check here before concluding a screen is broken because it came up empty |
| [references/search_tool.md](references/search_tool.md) | The Docs & Search / RAG part of the fixture, and what a sandbox with no API key can still do with it |
| [references/extending_the_fixture.md](references/extending_the_fixture.md) | `reset` and `snapshot` — changing what future sessions start from |
