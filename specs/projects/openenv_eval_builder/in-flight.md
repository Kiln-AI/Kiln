# In flight

Work started for this project that is not merged yet, across every repo it touches. Update this file
when an item lands or changes. The design itself is in `project_overview.md`; the plan page with
diagrams and the proposed prompts is https://claude.ai/artifact/99YYFkgHghSTN2tcqmSRsh.

The first customer's world is named only as "the customer world" here. Its repo is local, not part
of Kiln.

## Summary

| Where | Branch | What | State |
|---|---|---|---|
| Kiln | `worktree-openenv-eval-builder` | This spec, phases 1 and 2, and the grounding-input change | Committed (`97bbca26a`, `46eef6c2b`, `6c448ca8b`), not pushed. Branched from `worktree-openenv-run-page-spec` at `cb650560e`. Prototype results in `prototype_results.md` |
| Seahaven (local) | `sfierro/local-51-52` in `~/Repos/Seahaven-local-51-52` | #51 and #52 merged for testing | Local commits only. Never push |
| Worlds (local) | `sfierro/local-seahaven-51-52` worktrees of the customer world, a payments world and a commerce world | Each points at the local Seahaven and OpenEnv 0.13 | One uncommitted `pyproject.toml` change each. Never commit |
| Kiln | `worktree-openenv-run-page-spec` | The OpenEnv run page work the builder depends on (reset-schema forms and more) | 37 commits ahead of `main`, no PR yet |
| Kiln | `worktree-openenv-run-page-spec` | Preset dialog cuts long reset-argument descriptions | Committed on the branch |
| Seahaven | `claude/openenv-0.13-schema` | OpenEnv 0.13; reset schema on the standard `/schema` (Kiln now reads only that) | PR open: Kiln-AI/Seahaven#51 |
| Seahaven | `sfierro/fixture-descriptions-in-reset-schema` | Fixture descriptions published in the reset schema, and `World(setup_sql_notes=...)` appended to the `setup_sql` description | PR open: Kiln-AI/Seahaven#52 |
| Customer world | `sfierro/setup-sql-notes` | Its setup notes, passed as `setup_sql_notes` | Committed locally (`ef6d1655`), not pushed. Needs a Seahaven release with #52 before the pin moves |
| Customer world | `main` | `acting_user` startup keyword gets a description | Merged: `d2d2f322` |

## Kiln

### The spec

`project_overview.md` in this folder, on `worktree-openenv-eval-builder` (worktree
`.claude/worktrees/openenv-eval-builder`), which branches from `worktree-openenv-run-page-spec`. Not
committed. It follows the decisions on the plan page:
no `OpenEnvServer.brief` field in v1, the planner reads the server's own reset-schema descriptions,
setup arguments are used only when their description says how.

### The branch the builder work depends on

`worktree-openenv-run-page-spec` is 37 commits ahead of `main` and has no PR yet. It holds the
OpenEnv run page work, including reading the reset schema (environments phase 8). `main` has no
reset-schema code, and the planner's reset-arguments section needs it, so the builder work starts
from this branch or after it merges.

The `/seahaven/schemas` fallback is gone (`3e4b5f59e`): Seahaven now publishes its reset schema on
OpenEnv's standard `/schema`, and Kiln reads only that.

### Long descriptions in the environment preset dialog

The preset dialog builds its reset form from the reset schema and shows each argument's
`description` under the field. Server descriptions can now be long, so the dialog cuts them to three
lines with a "See all" link that opens the full text.

- `form_element.svelte` takes an optional `on_see_all_description` and uses `ClampedText` when set.
- `environment_preset_dialog.svelte` passes it and shows a `SeeAllDialog`.
- `run_input_form.svelte` and the run input element components pass the callback through.
- Tests in `environment_preset_dialog.test.ts`.

Sam's change, committed on the branch (`8ba727df7`, `a0ec8ae1b`).

## Seahaven

Worktree `~/Repos/Seahaven-fixture-descriptions`, branch `sfierro/fixture-descriptions-in-reset-schema`,
off `origin/main` at `cb16457`.

**What.** The reset schema's `fixture` description now lists every fixture with its own description
from `fixture.yaml`:

```
The fixture to start from, by id. Null starts a blank instance from the world's schema.

The fixtures:
- `agency`: A twelve-person agency: three teams, ...
- `small_startup`: A three-person startup's tracker: ...
```

**Why.** Every fixture already has a required `description`, written for whoever is choosing
between fixtures, but only `seahaven fixture list` printed it. No OpenEnv client could see it. Kiln's
planner and grounding agent read the reset schema's descriptions, so this is how they learn what each
starting state holds. It uses the standard `description` field, not `oneOf` with a `const` per
value, because Kiln's reset form refuses `oneOf`.

**Changes.**
- `src/seahaven/openenv/env.py`: `fill_fixture_ids` became `fill_fixtures` in
  `SeahavenResetRequest.for_world`. It still fills the enum and now appends the listing. A
  description keeps its line breaks, with later lines indented under its list item, so a table in
  a description survives. A blank description is left out. A world with no
  described fixtures keeps the plain sentence. It is read on every `model_json_schema()`, so a
  fixture frozen while the server runs appears without a restart.
- `src/seahaven/docs/db_schema_and_fixtures.md`: "Writing a description" says the description is
  published in the reset schema.
- `tests/test_reset_schema.py`: the reference world lists each fixture, a blank description is left
  out, a world with only blank descriptions keeps the plain sentence, and a fixture frozen while
  serving appears in the served schema.

**Left.**
- Checks: `ruff` passes. The full suite has 26 failures on this branch and the same 26 on clean
  `main` (2,630 passed here, 2,627 on main: the three new tests). `ty` flags two errors in
  `tools/bench/harness.py`, which this change does not touch. PR: https://github.com/Kiln-AI/Seahaven/pull/52
- Also in #52: `World(setup_sql_notes=...)`, appended to the `setup_sql` description after
  Seahaven's own sentence. The prototype showed the customer world needs them
  (`prototype_results.md`, finding 2). Served locally from the customer world's branch.
- After merge, the customer world needs a Seahaven version that has this change before its
  fixture descriptions show up.

### Running both Seahaven PRs before they ship

The prototype and any UI testing need #51 and #52 together. They conflict in `fill_fixture_ids` in
`src/seahaven/openenv/env.py` and in `tests/test_reset_schema.py`, so a local branch merges them.
The customer world pins Seahaven to a commit and OpenEnv to `<0.6`; serving it on that branch
needs a local override to the checkout and OpenEnv 0.13, not committed.

Set up 2026-11-17. The merge keeps #51's handling of an unreadable fixtures folder and #52's
descriptions; the 33 reset-schema tests pass. Each world runs from a worktree whose `pyproject.toml`
points at `~/Repos/Seahaven-local-51-52`. Rebase #52 onto #51 once #51 lands, and this branch goes
away.

## Customer world

Merged to `main` as `d2d2f322` (fast-forward, from branch `sfierro/reset-descriptions`).

**What.** The `acting_user` startup keyword now has a description in the reset schema:

> Who the agent acts as: the objectId of one of the fixture's users. Each fixture's description
> lists its users as `objectId Name (Role)`. The role sets what the agent can see and change. ...
> Null acts as the company's first Administrator. An id that is not a user of the fixture fails the
> reset.

It is set with `Annotated[str | None, pydantic.Field(description=...)]` on the hook's parameter,
which Seahaven already publishes. Confirmed in the v2 world's published reset schema.

**Why.** The grounding agent picks who the session acts as by reading reset-argument descriptions.
Without one, `acting_user` was a bare string.

**Tests.** Lint passes. Base and v2 tests that touch `acting_user` or the reset schema pass. Two v1
tests in `build/tests/replay/test_harness.py` fail with or without this change, so they were already
failing.

**Already there.** Each fixture's `fixture.yaml` has a detailed description, including every user's
objectId and role. It reaches the reset schema once the Seahaven change above is released.

## Not started

- Kiln docs: say that reset-schema descriptions guide eval generation and should be written for
  models.
- Follow-up ticket: notes a Kiln user writes for a server they can't change. Environment preset
  descriptions are a possible place to start.
- The customer world: push `sfierro/setup-sql-notes` and move its Seahaven pin once #52 is released.
- kiln_server production: the batch planner returned 500 for every request on 2026-11-17 (trace ids
  `85a56d1c-64a3-4c65-b641-dcdc989093d0`, `104072f4-33b9-45b8-b149-c48c8cb1ba0c`,
  `0fcea80e-9baa-4c4a-b35c-390ba28f0d2e`). The prototype used a local kiln_server.
- A project-wide multi-turn synthetic user guide replaces the per-build Data Guide field
  (decided 2026-11-18). Sam is scoping its UI.
