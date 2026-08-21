---
status: complete
---

# Architecture: Desktop Lint Config Scope

There is no runtime architecture here — nothing ships, no module is added, no interface changes.
What follows is the technical shape of the change: the exact config diff, the fix technique for
each rule, and how each phase proves it did not break anything.

## The config diff

Two files, three lines of net change, landing together in the final phase.

**`pyproject.toml` (root)** — extend the existing exclude:

```toml
[tool.ruff]
exclude = [
    ".worktrees",
    # Automatically generated code, so we don't lint it
    "app/desktop/studio_server/api_client/kiln_ai_server_client",
]
```

**`app/desktop/pyproject.toml`** — delete the whole `[tool.ruff]` section:

```toml
# removed entirely
[tool.ruff]
exclude = [
    # Automatically generated code, so we don't lint it
    "studio_server/api_client/kiln_ai_server_client",
]
```

Everything else in `app/desktop/pyproject.toml` stays — `[build-system]`, `[project]`,
`[tool.uv]`, `[tool.uv.sources]`, `[tool.hatch.build.targets.wheel]`. Only the ruff section goes.
Carry the explanatory comment up with the exclude; it is the reason the line exists.

### Why this works

Ruff resolves config by walking up from each file and stopping at the first `pyproject.toml`
with a `[tool.ruff]` section. With no such section under `app/desktop`, the walk reaches the
root, and desktop files get `extend-select = ["I","F401","RUF","FAST","TID"]` like everything else.

Exclude paths containing a slash are matched relative to the config file's directory, which is
why the path gains its `app/desktop/` prefix on the way up. Verified: running the root config
against `app/desktop` with this path excluded yields 147 findings; without it, 696.

## Fix technique per rule

### `RUF059` — unused unpacked variable (74)

Underscore-prefix the unused binding:

```python
success, msg, mode = check_remote_access(...)   # before
success, _msg, mode = check_remote_access(...)  # after
```

Ruff's own fix for this is classified unsafe (renaming a binding can collide with an existing
name), so it is **not** applied in bulk. Each site is edited and read.

Every site is in a test. Before renaming, check whether the unread value is a missing assertion —
`msg` from a `(success, msg, mode)` return is exactly the kind of thing a test meant to check.
Where it plainly was, add the assertion instead of the underscore, and call it out in the phase
notes. Where it was not, underscore it. Do not invent assertions to look thorough.

Distribution: 17 files, 71 of 74 under `app/desktop/git_sync/`, the largest single file being
`git_sync/test_clone.py` at 17.

### `I001` — unsorted imports (51)

```bash
uv run ruff check --config pyproject.toml \
  --exclude app/desktop/studio_server/api_client/kiln_ai_server_client \
  --select I --fix app/desktop
```

Safe fix, applied in bulk, no hand edits. Follow with `uv run ruff format .` since reordering
imports can change wrapping.

### `FAST002` — FastAPI dependency without `Annotated` (9)

All nine are in `app/desktop/git_sync/git_sync_api.py`. Convert the default-value form to the
`Annotated` form:

```python
# before
project_id: str = FastAPIPath(description="The unique identifier of the project."),
# after
project_id: Annotated[str, FastAPIPath(description="The unique identifier of the project.")],

# before
state: str = Query(default="", description="OAuth state parameter ..."),
# after
state: Annotated[str, Query(description="OAuth state parameter ...")] = "",
```

Two hazards:

1. **Argument ordering.** The `Annotated` form without a default is a non-default parameter.
   A parameter that previously "had a default" (`= FastAPIPath(...)`) and sat after another
   non-default parameter is still legal after conversion, but converting some params and not
   others in the same signature can produce `non-default argument follows default argument`.
   Convert whole signatures, and let the interpreter catch the rest — an import error is loud.
2. **OpenAPI schema.** This conversion should be schema-identical, and that is checkable:
   `app/web_ui/src/lib/check_schema.sh` verifies the generated client matches the live schema.
   Run it. A diff means the conversion changed the API contract and is wrong.

### `RUF012` — mutable class default (2)

Both in `app/desktop/git_sync/registry.py`. Annotate with `ClassVar`; do not restructure:

```python
_managers: ClassVar[dict[Path, GitSyncManager]] = {}
_background_syncs: ClassVar[dict[Path, BackgroundSync]] = {}
```

The functional spec records why this is the right call rather than a silencer: the class is a
documented, lock-guarded singleton, and `ClassVar` states the intent the comment already spells
out. `_lock: threading.Lock = threading.Lock()` on the same class is not flagged (not a mutable
container literal) and is left alone.

Note the file uses `from __future__ import annotations` with a `TYPE_CHECKING` block, so
`ClassVar` must be imported from `typing` at runtime — it is evaluated by the annotation
machinery even under postponed evaluation. Import it unconditionally, not inside `TYPE_CHECKING`.

### `TID252` — relative import (3)

One line in `app/desktop/studio_server/jobs/workers/noop.py`, counted three times (one per name):

```python
from ..models import JobContext, JobDerivedState, JobWorker          # before
from app.desktop.studio_server.jobs.models import (                  # after
    JobContext, JobDerivedState, JobWorker,
)
```

Matches how the rest of the tree imports — `git_sync/registry.py` already uses the
`app.desktop....` absolute form.

### `RUF010`, `RUF022` — auto-fixable (6)

Safe fixes. Apply with `--select RUF010,RUF022 --fix` and read the diff.
`RUF010` is `f"{str(x)}"` → `f"{x!s}"` in `prompt_optimization_job_api.py` (5 sites);
`RUF022` sorts `__all__` in `studio_server/chat/__init__.py`.

### `RUF005`, `RUF015` — one each, by hand

- `studio_server/chat/stream_session.py:348` — `prior + [a] + tools` becomes
  `[*prior_messages, assistant_msg, *tool_messages]`. Read the surrounding code to confirm all
  three operands are lists and none is `None`.
- `studio_server/test_prompt_optimization_job_api.py:2313` — `[x for x in y if ...][0]` becomes
  `next(x for x in y if ...)`. Behaviour differs on empty input: `IndexError` becomes
  `StopIteration`. In a test asserting a match exists, either is a failure, so the change is safe —
  but confirm the test is not relying on the exception type.

## Verification

### Per-phase

Every phase runs, at minimum:

```bash
# the finding count for this phase's rules must be zero
uv run ruff check --config pyproject.toml \
  --exclude app/desktop/studio_server/api_client/kiln_ai_server_client \
  --select <RULES> app/desktop

# nothing else regressed
uv run ruff format --check .
uv run python3 -m pytest --benchmark-quiet -q -n auto app/desktop
```

The desktop test suite runs on every phase, not just the last. Phases 1 and 2 touch test files
and import blocks respectively; both are exactly the kind of change that looks inert and is not.

The phase touching `git_sync_api.py` additionally runs `app/web_ui/src/lib/check_schema.sh`.

### Final phase

The config flip is verified by the absence of the audit command:

```bash
uv run ruff check          # must pass — this is what CI runs
uv run ruff format --check .
git status --porcelain app/desktop/studio_server/api_client/kiln_ai_server_client
```

The last one must print nothing. If the generated client shows modifications, the exclude did
not resolve and the root path is wrong.

Then the full suite: `uv run ./checks.sh --agent-mode`.

### Proving the exclude survived

A stronger check than "did ruff pass": count findings with the exclude deliberately removed.

```bash
uv run ruff check --no-cache --statistics app/desktop | tail -1
```

If the generated client is properly excluded this reports a clean run. A result in the hundreds,
dominated by `TID252`/`TID251`, means the exclude is not being applied and the config change is
wrong regardless of what CI says.

## Testing strategy

No new tests. This project adds no behaviour to test, and a test asserting "ruff config is
shaped a certain way" would be testing ruff, not Kiln.

The existing suite is the safety net, and it is a real one: the fixes touch test files (74
`RUF059` sites), a FastAPI router (`git_sync_api.py`), a singleton registry, and 50 import
blocks. If any fix is not behaviour-preserving, the desktop suite is where it shows up.

Regression protection after the project is the config itself — CI now lints this tree, so the
class of problem cannot silently return.

## Risks

| Risk | Mitigation |
|---|---|
| A "mechanical" fix is not behaviour-preserving | No bulk `--unsafe-fixes`; desktop suite per phase |
| `Annotated` conversion changes the API contract | `check_schema.sh` in that phase |
| Exclude path does not resolve from root | Explicit finding-count and `git status` checks in final phase |
| New violations land in `app/desktop` mid-project | Final phase re-runs the full check rather than trusting earlier phases |
| Large `I001` diff hides a real change in review | `I001` isolated in its own phase, produced only by `--fix` |
