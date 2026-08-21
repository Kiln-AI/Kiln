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

## A provider may or may not be connected

Seeded data is just files the screens read, so every page renders it whether or
not a provider is connected. *Executing* anything — a new run, a data gen, an
eval, a search query — needs a live model call, and that depends on the sandbox.

`playwright_server.sh start` tells you which sandbox you have. If it says
OpenRouter is connected, it is: the seed wrote a key from `OPENROUTER_QA_KEY` into
this sandbox's `settings.yaml`, which is the same setting the app's Settings
screen writes, so calls work exactly as a user's would. If it says nothing about
OpenRouter, nothing is connected and you either connect a provider by hand through
the UI or stop at the gate.

**When a key is there, it is a real key spending real money**, against a hard
low limit that a runaway loop will hit. Use it when a live call is the only way to
check the thing you are working on, and keep it cheap:

- **Default to GPT-5.6 Luna** (`openai/gpt-5.6-luna` on OpenRouter). Pick another
  model only when the thing under test is about that model.
- Run the smallest thing that answers the question — one sample, not fifty; one
  eval row, not a full sweep.
- Never point a paid test suite at it: `pytest --runpaid` and `--runprerelease`
  read `OPENROUTER_API_KEY`, which is deliberately not the variable this uses.
- A 402 or a 429 means the budget is gone. Stop and say so — retrying is how a
  small limit becomes a blocked afternoon for everyone.

`reset` deletes the sandbox and reseeds it, which re-reads `OPENROUTER_QA_KEY`; a
sandbox seeded before that variable existed keeps having no provider until then.

The search tool has its own split: the index rebuilds with no key, and searching
it needs one. See [search_tool.md](search_tool.md).

