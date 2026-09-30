# Extending the fixture

Two commands change what future sessions start from.
## `playwright_server.sh reset` — start over

```bash
.agents/scripts/playwright_server.sh reset
```

Stops the server, deletes the sandbox, seeds it again, starts. This is the only
command that re-seeds: an ordinary `start` never reverts changes you made, however
many times you stop and start. Use `reset` when you want the committed fixture
back, or after pulling a branch whose fixture differs.

It deletes the whole sandbox home, `settings.yaml` included — so any provider you
connected by hand goes with it, and you will need to paste the key again. The
seed's own OpenRouter key comes back on its own, since reseeding re-reads
`OPENROUTER_QA_KEY` from the environment.

## `playwright_server.sh snapshot` — improve the fixture

Not to be confused with `playwright-cli snapshot`, which prints the page.

When you have built state through the UI that future sessions should start from:

```bash
.agents/scripts/playwright_server.sh snapshot
```

It mirrors the sandbox's project over `.agents/playwright_project` and prints
`git status` for it. **Read that diff before committing.** A snapshot captures
whatever was in the sandbox, including files you did not mean to create, and a
deletion in the sandbox is a deletion in the repo.

Three rules if you are extending the fixture:

- **Create the data through the UI**, not by hand-editing files under
  `.agents/playwright_project` and not through the REST API. This is the project we
  look at through a browser, and state created the way a user creates it looks the
  way a user's looks. A manual edit is fine with a good reason — say so in the
  commit message.
- **Create the task you want agents to land on first.** The `ui_state` hint points
  at the earliest-created task in the project.
- **Run the expensive steps once, here, and commit what they produce.** Anything a
  future sandbox would otherwise have to regenerate with an API key belongs in the
  fixture if it lands inside the project directory — which is what makes the RAG
  chain's extractions and embeddings committed data rather than something each
  sandbox recreates. Locally derived caches outside the project, like the LanceDB
  index, stay out and are rebuilt on demand.

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

