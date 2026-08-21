# The seeded project

`start` copies `.agents/playwright_project` into the sandbox, so you get an app
with a project and tasks already in it instead of an onboarding wizard. It is a
copy: click around, break things, delete things — the checkout is untouched.

The fixture is a support-ticket-triage project with two tasks, one with JSON input
and output schemas and one plain text, because structured and unstructured tasks
render differently in a lot of places.

It is not only task definitions. If a screen you are working on comes up empty, check
this list before assuming the screen is broken.

| Screen | What the fixture holds |
|---|---|
| Dataset, Run | 20 runs, weighted to the structured task. Ratings spread deliberately across high, low and **unrated** — filters need all three. One repaired run, one run carrying human feedback |
| Run configurations | Four, three of them on the structured task: zero-shot, chain-of-thought, and one pairing a custom saved prompt with a Jinja input transform |
| Prompts | One saved prompt, "Triage Playbook" |
| Fine Tune | A train/test/val split over the runs tagged `fine_tune_triage`. No fine-tune job — no provider for one |
| Evals, Specs | One eval, `Escalation Flagging`, with its spec, a judge, human ratings on a golden set, and eval runs scoring all three structured run configs |
| Skills | Two, each with a `SKILL.md` body |
| Docs & Search | Three markdown documents, and a search tool over them with all five configs in its chain |

## Landing in the app

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

## No provider is connected

A seeded sandbox has no API keys, so you cannot *execute* a new run in it. Seeded
data is just files the screens read, so the pages render it with nothing connected
— but if the feature you are working on needs a live model call, you have to
connect a provider by hand through the UI first.

The search tool is the exception in one direction and not the other: its index
rebuilds with no key, and searching it needs one. See
[search_tool.md](search_tool.md).

