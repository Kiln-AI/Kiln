# Driving the UI with playwright-cli

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
data in them — see [seeded_project.md](seeded_project.md). `stop` when you are
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

## Screenshots: never trust the first frame

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

## Let `find` tell you the role

Do not guess a role from how something looks. Kiln styles links as buttons, so
`getByRole("button", { name: "Get Started" })` finds nothing where
`find "Get Started"` returns `link "Get Started" [ref=e9]` — the ref and the true
role in one call. Run `find` first, then write the locator from what it reports.

## One label, two elements — and `>/dev/null` hides the reason

Kiln reuses one label for a menu item and the button that submits the dialog it
opens. On the Dataset screen's bulk tag menu, `Add Tags` is both the item in the
open dropdown and the disabled submit inside the resulting dialog, so

```bash
playwright-cli click "getByRole('button', { name: 'Add Tags', exact: true })"
```

fails with `strict mode violation: … resolved to 2 elements`, naming both matches
and a disambiguating locator for each. The dialog never opens.

**`playwright-cli` reports that failure on stdout, and exits 1.** So the redirection
that hides it is `>/dev/null` — including the `>/dev/null 2>&1` that is easy to put
on every command to keep a transcript readable. Measured against this app:

| Redirection | What you see |
|---|---|
| none, or `2>/dev/null` | the full strict-mode error |
| `1>/dev/null`, or `>/dev/null 2>&1` | nothing at all |

In every case the exit status is `1`. Discard the output if you must, but then test
`$?` — a failed click that looks like a click landing on nothing is how a two-line
locator fix turns into an afternoon of wrong theories.

The locator fix itself is **`find` first, click the ref**: a ref is a single element
by construction, so it cannot go strict-mode ambiguous.

```bash
playwright-cli click "div.dropdown [role=button]"   # opens the menu
playwright-cli find "Add Tags"                      # 3 matches; one carries a ref
playwright-cli click f1e369                         # → the dialog
```

`find` reports three matches for that label, and exactly one of them carries a ref:
the menu item. Take the ref-bearing one. Scoping works too, as long as the scope is
narrow enough to be unique:
`".dropdown-content button >> nth=0"`. Plain `".dropdown-content button"` is itself a
strict-mode violation, since the menu holds both `Add Tags` and `Remove Tags`.

Menus survive between commands, so that sequence is three ordinary processes.
`playwright-cli` keeps one persistent session and the trigger keeps focus, so a
DaisyUI `dropdown` opened by one command is still open, still visible, and still in
the accessibility tree for the next one. Reach for `run-code` to click something
in-page only when a control genuinely cannot be clicked otherwise: it bypasses
Playwright's actionability checks, which is the opposite of what driving the UI
like a user is for.

Open the menu **first**, though. With it closed the menu item is `visibility: hidden`,
so the same locator resolves to exactly one element — the dialog's disabled submit —
and you get a different failure entirely: a 5 s timeout ending in `element is not
enabled`. Same label, same command, unrelated diagnosis.

Not everything on that toolbar is a menu, either. Only the tag control is a
`dropdown`; the delete button beside it opens its modal directly, in one click.

## A collapsed "Advanced Options" hides its fields from `find`

Kiln's `Collapse` is a checkbox plus a hidden panel, and the fields inside a closed
one are in the DOM but `visibility: hidden` — so `snapshot` and `find` do not report
them at all. `find "Extractor Name"` returning nothing means the section is closed,
not that the field does not exist. Confirm with the checkbox rather than the label:

```bash
playwright-cli eval "() => { const d=[...document.querySelectorAll('dialog')].filter(x=>x.open)[0]; return d.querySelector('input[type=checkbox]').checked }"
```

Every click toggles it, so a click that appears not to work followed by a second
click leaves you exactly where you started. Clicking the checkbox inside the open
dialog — `"dialog[open] .collapse input[type=checkbox]"` — is unambiguous where a
label ref can go stale after the surrounding form re-renders.

