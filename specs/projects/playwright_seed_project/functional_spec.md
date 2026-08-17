---
status: complete
---

# Functional Spec: Playwright Seed Project

## Purpose

An agent driving Kiln with `playwright-cli` currently lands on an empty app: no
account, no project, no task, no data. Before it can look at the screen it came to
work on, it has to click through onboarding, create a project, create a task, and
then find that most screens are still empty because there are no runs.

This project ships a committed Kiln project and the glue to install it, so
`playwright_server.sh start` produces an app where the screens an agent needs to
look at already have plausible data in them.

## Out of scope

- Changes to `setup_env.sh` or the VM build. The seed is a start-time concern.
- Any automated test that loads the committed fixture.
- Wiring an inference provider into the dev server so new runs can execute. See
  [Providers](#providers) — this turns out to be an authoring-time need only.
- Fixture content that depends on an external service: fine-tunes, tool servers,
  prompt optimization jobs, and git sync. See [Deferred content](#deferred-content).

## What the app requires before it will show you a screen

`app/web_ui/src/routes/+layout.svelte:72` runs `check_needs_setup` on mount for every
app route and redirects away in four ordered checks:

| Check | Redirects to | Satisfied by |
|---|---|---|
| `projects.length == 0` | `/setup` | `projects` in `settings.yaml` |
| `!$current_project` | `/setup/select_task` | `ui_state` in **localStorage** |
| `!$current_task` | `/setup/select_task` | `ui_state` in **localStorage** |
| `!user_type`, or type without matching contact | `/setup/select_account` | `user_type` + contact in `settings.yaml` |

The second and third are browser state, not disk state. A correctly seeded home is
therefore **not sufficient** — without a `ui_state` write the agent still lands on the
task picker, and navigating straight to a deep URL does not help, because the layout
redirects on mount regardless of the URL.

Seeding is thus three parts: `settings.yaml`, the project directory, and a
`ui_state` value the agent writes into the browser.

## Artifacts

### `.agents/playwright_project/`

A Kiln project directory, committed to the repo. `project.kiln` sits at its root,
with `tasks/<task_id>/…` beneath it, exactly as the app writes it.

It is never loaded in place. It is a source to copy from.

The project and task IDs inside it are fixed by virtue of being committed, which is
what lets the `ui_state` value be printed as a constant rather than discovered.

## Commands

`playwright_server.sh` keeps `start`, `stop`, and `status`, and gains `reset` and
`snapshot`.

### `start`

Unchanged except that it seeds first:

1. Refuse to continue if the run directory is the real home. See [Isolation](#isolation).
2. Create the run directory if missing.
3. If the seed stamp is absent, seed it. If present, skip seeding silently.
4. Start the backend and frontend as today, and wait for both.
5. Verify the seeded project actually loaded, by asking the backend that is now up:
   `GET /api/projects` returning an empty list means it did not. Warn loudly, naming
   the stale-fixture explanation. Do not fail the server.
6. Print the URL, the seeded project's name, and the `ui_state` command.

Step 5 exists because `get_projects` catches every load exception per project and
continues, so a fixture that has gone stale against the current datamodel produces an
app with zero projects and an agent redirected to `/setup` — indistinguishable from
seeding never having run. This is the whole reason a stale fixture would be hard to
diagnose, and one assertion against a server we already wait for turns it into a
sentence that names the cause.

Seeding must happen **before** the backend starts. `Config` is a process-lifetime
singleton that caches settings on first read, so a backend started against an
unseeded home would hold empty settings for its whole life.

Seeding is skipped whenever the stamp exists — including when the agent has since
deleted the project through the UI. Deleting it is a thing the agent chose to do, and
`start` does not undo the agent's choices.

### `reset`

Throw the sandbox away and get a clean one:

1. Refuse if the run directory is the real home.
2. `stop`, if anything is running. The backend holds the directory open, so this
   comes before the wipe.
3. Delete the run directory entirely.
4. Seed it.
5. `start`.

This is the only command that re-seeds. There is deliberately no drift detection:
an agent must be free to make a mess without the next `start` silently reverting it.
Pulling in an updated fixture is a rare, deliberate act, and `reset` is how you ask
for it.

### `snapshot`

Capture the running sandbox's project back into the repo, for when you have built
better initial state through the UI and want future sessions to start from it.

1. Find projects in the run directory's `Kiln Projects/`. Require **exactly one**:
   - zero → error, nothing to capture
   - more than one → error, listing what it found, and stop. The agent should delete
     the ones it does not want through the UI and re-run.
2. Mirror it over `.agents/playwright_project/`: delete the destination, then copy.
   A merge would leave a run deleted in the UI sitting in the repo forever.
3. Exclude `.git` and `.DS_Store`. A nested `.git` would be committed as a gitlink
   and corrupt the fixture for everyone who checked it out.
4. Never read or write `settings.yaml`. Settings are generated by the seed step, and
   a captured `settings.yaml` could carry an API key into the repo.
5. Print `git status --short` for the destination afterwards, and remind the reader
   to review the diff for files they did not mean to capture.

`snapshot` does not refuse to run against a dirty destination. Git is the safety net,
and the printed status is how you see what happened.

## The seed step

Given a run directory that has no stamp:

1. Copy `.agents/playwright_project/` to `<run_dir>/Kiln Projects/playwright_project/`.

   The destination folder name is the source's basename. It is cosmetic — the name the
   UI shows comes from `project.kiln` — and using the basename avoids both parsing YAML
   in bash and a constant that can drift from the fixture.

2. Write `<run_dir>/.kiln_ai/settings.yaml` containing:

   | Key | Value | Why |
   |---|---|---|
   | `projects` | `["<run_dir>/Kiln Projects/playwright_project/project.kiln"]` | clears check 1 |
   | `user_type` | `personal` | clears check 4 |
   | `personal_use_contact` | a plain `@example.com` address | clears check 4 |

   Written whole, not merged. The path is absolute and therefore cannot be committed
   verbatim, which is why settings are generated here rather than shipped as a file.

3. Write the stamp file. Its presence is the entire signal; its contents are
   informational only — the date and the repo's HEAD revision at seed time, so a
   human wondering how old a sandbox is can find out. Nothing ever compares it.

## Isolation

Everything Kiln reads or writes resolves through `Path.home()`, and `start` runs the
backend under `env HOME="$RUN_DIR"`. Settings, projects, and the RAG indexes under
`.kiln_ai/rag_indexes` all land inside the run directory. The sandbox owns its home
completely and is expected to be clobbered.

Two facts follow from that, worth stating so nobody has to rediscover them:

- The **frontend** is not under the isolated home; `npm run dev` keeps the real one so
  it can use the real npm cache. It writes no Kiln data.
- Git-sync's `~/.ssh` lookup resolves inside the sandbox, so it cannot see real SSH
  keys. A limitation of the sandbox, and a reason git-sync stays out of the fixture.

The one guard: `start`, `reset`, and `snapshot` refuse to run when the run directory
resolves to the same path as the invoking shell's `HOME`. Seeding and wiping a real
home would destroy a real user's settings and projects. The script's current comment
inviting `KILN_DEV_HOME` to be pointed "at real projects" is retracted — the override
chooses *where the sandbox lives*, not *whose data it operates on*.

## Fixture content

The goal is that a screen an agent opens has something on it. Not exhaustive coverage
— enough that layout, empty-vs-populated states, and filtering are all exercised.

### Authoring rules

**Build it through the UI.** Do not hand-write files in the fixture, and do not create
data through the REST API, where using the UI is possible. This is the project we look
at through a browser; state created the way a user creates it is state that looks the
way a user's looks. Not a hard rule — a manual edit or an API call is fine with a good
reason — but the UI is the default, and a deviation is worth a line in the commit
message.

### Content

A realistic-looking project, so screenshots read like a real user's app:

- **Project** — support-ticket triage, or a comparable everyday domain.
- **Two tasks.** One with JSON input *and* output schemas, one with plain text for
  both. Structured and unstructured render differently in enough places that having
  only one shape would leave half the app untested.
- **15–20 task runs**, weighted toward the structured task. Ratings deliberately
  spread: several high, a couple low, and several left unrated — unrated is not an
  oversight, it is what dataset filters and split screens need in order to show
  anything interesting. At least one run with a repair.
- **Two run configs** on the structured task. Comparison and eval screens need two to
  be worth looking at.
- **One custom saved prompt.** The built-in generators need no fixture data.
- **One dataset split** on the structured task.
- **One eval** with a judge config and results across both run configs. Evals are not
  optional here — this is an evals platform, and an agent working on an eval screen is
  the likeliest reader of this fixture. This covers **specs** as well: a `Spec` is a
  child of the task that the create-eval flow produces, and `Eval.associated_spec()`
  matches it back by `eval_id`, returning `None` only for legacy evals predating specs.
  Authoring the eval through the current UI therefore yields the spec for free, and is
  the only path that produces a non-legacy one.
- **One input transform.**
- **Feedback** on at least one run.
- **One or two skills**, with `SKILL.md` bodies. Skills are pure project data — a
  name, a description, and a markdown sidecar — so they cost nothing beyond the
  clicking.
- **The docs library / RAG chain**: a couple of small documents, an extractor config, a
  chunker config, an embedding config, a vector store config, and a RAG config. See
  [RAG indexes](#rag-indexes) for what does and does not survive a snapshot.

The dividing line is external services. Anything that needs one is out, because a
fixture referencing a service nobody can reach is worse than no fixture.

### Deferred content

**Fine-tunes** (a training job at Fireworks or OpenAI), **tool servers** (a reachable
MCP server), **prompt optimization jobs**, and **git sync** (whose `~/.ssh` lookup
resolves inside the sandbox and so cannot see real keys).

### RAG indexes

A RAG index lives at `.kiln_ai/rag_indexes/lancedb/<id>`, **outside** the project
directory, so `snapshot` never captures the index. This is intended, not a defect:
the index is derived data that gets rebuilt when it is needed.

Everything else the chain produces *is* inside the project directory and *is*
captured — the extraction for each document, its chunks, and its embeddings, which
nest under `documents/<doc>/extractions/…`. So the fixture carries the documents, the
five configs, **and the outputs of running the chain**. A correction to an earlier
draft of this section, which said only "configs and never the index": committing the
configs alone would leave every rebuild depending on live extraction and embedding
calls, which is exactly what a keyless seeded sandbox cannot make. The same split
Kiln's git sync uses — extracted docs and embeddings sync, the index is a local cache.
See architecture.md's "What group 5 commits, and what it deliberately does not".

Two things follow, and both are implementation-phase obligations rather than open
questions. Rebuilding must be confirmed to actually work from a seeded sandbox — a
config whose index cannot be rebuilt is a config that only looks configured. And the
documents themselves are real files committed as attachments inside the fixture, so
they should be small and textual.

## Providers

No provider is connected in a seeded sandbox, and none needs to be. Runs are authored
once and thereafter are just files the screens read; the dataset, eval, and comparison
pages render seeded runs with nothing connected.

A provider is needed only by whoever is *authoring* the fixture, in that session
only. For this project that is a one-off OpenRouter key with a few dollars of credit.
The agent doing the authoring asks the user for it when that phase starts — it is not
recorded here, and no planning artifact should carry it — then connects it through the
UI the way a user would.

All generation uses **`deepseek/deepseek-v4-flash-0731`** — cheap, capable, and
already `ModelName.deepseek_4_flash` in the built-in list with
`structured_output_mode=json_schema`, so the schema'd task needs no special handling.

One key covers the whole fixture, including the parts that are not chat completions:
extraction routes through OpenRouter, and so do embeddings, by rewriting the model
slug `openrouter/…` to `openai/…` and calling OpenRouter as an OpenAI-compatible
endpoint because LiteLLM has no native OpenRouter embedding support. That rewrite was
the one thing here taken on faith from reading the code rather than from running it.
Phase 4 ran it: OpenRouter serves `/embeddings` for `openai/text-embedding-3-small`
and the app produced real vectors through the rewrite, so no second key was needed.
The other OpenRouter embedding models in `ml_embedding_model_list.py` remain unrun.

The key never reaches the repo, and this is a property of the design rather than of
anyone remembering. Connecting a provider through the UI writes it to
`<run_dir>/.kiln_ai/settings.yaml`, which lives inside `app/web_ui/.agent_dev_home`
— already gitignored — and `snapshot` reads only the project directory and is
specified never to touch `settings.yaml`. There is no path from a connected provider
to a commit.

Authoring against a real provider does leave a real model name recorded in each run's
run config, which is what we want: the runs look like a user's runs. It also means a
seeded run names a model the sandbox cannot call until someone connects a provider.

The consequence to document: a feature that requires *executing* a fresh run still
needs a provider connected by hand. Wiring one in automatically is a separate project.

## Errors

| Situation | Behavior |
|---|---|
| Run directory is the real home | Refuse, name the path, exit non-zero. Never partially applied. |
| `.agents/playwright_project/` missing or has no `project.kiln` | Warn and start anyway. A server with an empty app is more useful than no server. |
| Seeded project present but does not load | Warn after start, naming a stale fixture as the likely cause and `snapshot` as the fix. Server stays up. |
| Copy or settings write fails mid-seed | Do not write the stamp, so the next `start` retries. Warn and continue starting. |
| `snapshot` with zero or multiple projects | Error, change nothing. |
| `reset` while running | Stops first; a failure to stop aborts before the wipe. |

Seeding never fails the server. An agent that wanted a browser gets one, and the
warning tells it why the app looks empty.

## Documentation

`.agents/USING_PLAYWRIGHT.md` gains:

- The seeded project in the `playwright_server.sh` section: what is in it, and the
  `ui_state` command needed to get past the task picker.
- That no provider is connected, and what that means for running a task.
- `reset` for a clean sandbox.
- `snapshot` for updating the fixture: the UI-first authoring rule, and the
  instruction to code review the resulting diff for unintended files.
