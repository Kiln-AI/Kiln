---
status: draft
---

# Playwright Seed Project

## What we want

More setup for the VM, where the CLI instance already has setup complete, and has
a project with data in it so all screens work out of the box. That lets an agent
jump right into the feature it actually needs to work on, instead of spending its
first ten minutes clicking through onboarding and creating a task.

## The catch

It would be a moving target. We add features often, so we'd need to add data on
occasion to keep it covering the app.

## Shape of it

- A `.agents/playwright_project` folder holding the project.
- VM setup sets up a custom home for the playwright-cli dev server, and writes the
  needed settings — get past onboarding, plus importing the project in
  `.agents/playwright_project`.
- Points at a **copy**, not the checkout's `.agents/playwright_project` itself, so the
  running app can make edits without touching git state. Plus instructions for "if
  you're setting up new initial state you want in future sessions, copy files from X
  to `.agents/playwright_project`".
- Get the initial project set up — "one of everything" kind of thing.

## Decisions made while discussing this

**In repo, not a separate demo_project repo.** The data is coupled to the datamodel,
so it has to version with the code in lockstep.

**Committed data, not a generator script.** The artifact is real `.kiln` files, not
code that builds them.

**Name it `.agents/playwright_project`, not `demo_project`.** This isn't going to be
a good "demo" in any way — name it for what it really is.

**Seed from `playwright_server.sh`, not from VM setup and not from the SessionStart
hook.** The VM is cached for a week and used across branches, and the demo project's
feature set will change per branch, so the copy has to happen at server start. This
is true of `settings.yaml` as well as the project files.

**Add a `playwright_server.sh snapshot` command** to capture the current dev home's
project back into `.agents/playwright_project`. In the docs around it, note that you
should code review the snapshot and make sure it didn't pick up unintentional files.

**Create the data through the UI, by default.** Don't create data in the folder
manually, or via the API, where possible — ideally use the UI. We want a realistic
user setup, and going through the UI gets the most realistic project. It's our
Playwright project; the best things seen in the UI were also created through the UI.
Not a hard rule — manual file edits or API calls are fine with a good reason — but
the default is through the UI.

**No pytest that loads the committed project** — not for now.

**No rewriting the recorded username to `demo`** — unnecessary.

**Mock inference provider: design it, but last, and we may still punt.** Wiring the
e2e mock provider into the agent dev server so Run actually works explodes the scope
of this project.
