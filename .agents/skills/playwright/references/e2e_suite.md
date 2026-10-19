# Running the e2e suite

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

## Reading the report

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

## First run on a route can be slow

`vite dev` compiles a route the first time a test navigates to it, and that
compile can take several seconds on a cold checkout. Assertions using the default
5 s `expect` timeout can lose that race, so a test that fails once and passes on a
re-run is usually this rather than a real bug. `--repeat-each=2` tells the two
apart: cold-compile failures fail the first repetition and pass the second.

