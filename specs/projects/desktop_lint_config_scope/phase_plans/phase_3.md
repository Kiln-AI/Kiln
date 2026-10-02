---
status: complete
---

# Phase 3: The judgment tail

## Overview

Clear the remaining 22 lint findings under `app/desktop/` — everything that is not `RUF059`
(Phase 1) or `I001` (Phase 2). Seven rules across nine files, none of them a single repetitive
shape, most needing the surrounding code read before the fix is chosen.

After this phase the audit command reports zero findings, and Phase 4 can flip the config
knowing there is nothing left for it to surface.

## Site survey

| Count | Rule | File | Technique |
|---|---|---|---|
| 9 | `FAST002` | `git_sync/git_sync_api.py` | hand-convert to `Annotated[...]` |
| 5 | `RUF010` | `studio_server/prompt_optimization_job_api.py` | safe auto-fix |
| 3 | `TID252` | `studio_server/jobs/workers/noop.py` | hand edit (one import line) |
| 2 | `RUF012` | `git_sync/registry.py` | hand-annotate `ClassVar` |
| 1 | `RUF005` | `studio_server/chat/stream_session.py` | hand edit |
| 1 | `RUF015` | `studio_server/test_prompt_optimization_job_api.py` | hand edit |
| 1 | `RUF022` | `studio_server/chat/__init__.py` | safe auto-fix |

No file under `studio_server/api_client/kiln_ai_server_client` may appear in the diff.

## Steps

### 1. `FAST002` — `git_sync_api.py` (9 sites, 5 signatures)

Add `Annotated` to the existing `from typing import Literal` import. Convert every parameter in
each affected signature, not a subset, so no signature ends up mixing forms.

Path parameters (no default) — `api_get_config` (664), `api_update_config` (696),
`api_oauth_status` (853), `delete_project` (886), `api_delete_config` (902):

```python
project_id: Annotated[str, FastAPIPath(description="The unique identifier of the project.")],
```

This matches the form already used across `studio_server/eval_api.py`, `tool_api.py`,
`jobs/api.py` and `kiln_server/spec_api.py`.

`api_update_config` takes `request: UpdateConfigRequest` first and `project_id` second. Both
become non-default parameters after conversion, so the order stays legal.

Query parameters with defaults — `api_oauth_callback` (787, 791, 795, 799): the default moves
out of `Query(...)` and onto the parameter:

```python
state: Annotated[
    str,
    Query(description="OAuth state parameter linking the callback to a pending flow."),
] = "",
```

All four params in that signature convert together, so all four keep their `= ""` default and
the signature remains valid.

### 2. `RUF012` — `git_sync/registry.py`

Import `ClassVar` from `typing` **unconditionally**. Not because a `TYPE_CHECKING`-only import
would break: `GitSyncRegistry` is a plain class — not pydantic, not a dataclass — and the file has
`from __future__ import annotations`, so the annotation is stored as a string and never evaluated
at runtime. The unconditional import is the right call for two other reasons: it matches
`libs/core/kiln_ai/datamodel/dataset_filters.py:3`, and it is what would be required if this class
ever became a pydantic model, where annotations *are* evaluated.

```python
from typing import TYPE_CHECKING, ClassVar
...
    _managers: ClassVar[dict[Path, GitSyncManager]] = {}
    _background_syncs: ClassVar[dict[Path, BackgroundSync]] = {}
```

`_lock: threading.Lock = threading.Lock()` is not flagged and is left alone. The existing comment
explaining the intentional singleton stays.

`BackgroundSync` is only imported under `TYPE_CHECKING`, and stays that way — it appears solely
inside the annotation string, which postponed evaluation never resolves at runtime.

### 3. `TID252` — `studio_server/jobs/workers/noop.py`

```python
from app.desktop.studio_server.jobs.models import (
    JobContext,
    JobDerivedState,
    JobWorker,
)
```

This is not the only relative import in `app/desktop` outside the generated client — there are ten
others (`studio_server/jobs/api.py:16-20`, `jobs/registry.py:14-16`, `jobs/events.py:8`,
`eval_api.py:44`). They survive because ruff's default `ban-relative-imports = "parents"` flags
`..` but not `.`, and the root config does not override it.

Absolute was nonetheless the only option here: `noop.py` sits in `workers/` and reaches up into
its parent package, so no compliant relative form exists. The consequence to state plainly is that
`noop.py` becomes the one file in `studio_server/jobs/` importing its own package absolutely. The
tree is mixed-style by rule design, not by oversight, so the sibling files are deliberately left
alone rather than churned to match.

### 4. `RUF010` and `RUF022` — safe auto-fixes

```bash
uv run ruff check --config pyproject.toml \
  --exclude app/desktop/studio_server/api_client/kiln_ai_server_client \
  --select RUF010,RUF022 --fix app/desktop
```

Read the diff: five `f"{str(e)}"` → `f"{e!s}"` inside `HTTPException` details in
`prompt_optimization_job_api.py`, and the `__all__` reorder in `chat/__init__.py`. Nothing else
may appear.

### 5. `RUF005` — `studio_server/chat/stream_session.py:349`

```python
new_messages = [*prior_messages, assistant_msg, *tool_messages]
```

Confirmed safe: `prior_messages` is `list(original_body.get("messages", []))` (line 322),
`tool_messages` is `list[dict[str, Any]] = []` (line 310), and `assistant_msg` is a dict literal
built just above. All three are lists/dicts, never `None`.

### 6. `RUF015` — `studio_server/test_prompt_optimization_job_api.py:2314`

```python
new_run_config = next(rc for rc in run_configs if rc.id != target_run_config.id)
```

The preceding `assert len(run_configs) == 2` guarantees exactly one match, and the test does not
catch `IndexError`, so the `IndexError` → `StopIteration` change is unobservable.

## Tests

No new tests. This phase changes no behaviour — the existing desktop suite is the safety net,
and it covers every touched file.

Verification:

- `uv run ruff check --config pyproject.toml --exclude app/desktop/studio_server/api_client/kiln_ai_server_client app/desktop` — zero findings (all rules, not just this phase's).
- `uv run ruff format --check .`
- `uv run ty check`
- `app/web_ui/src/lib/check_schema.sh` — must report no diff. This is the real test of the
  `FAST002` conversion: the `Annotated` form is meant to be OpenAPI-schema-identical, so any
  regenerated-client diff means the conversion changed the API contract and is wrong.
- `uv run python3 -m pytest --benchmark-quiet -q -n auto app/desktop` — full desktop suite, with
  particular weight on `git_sync/test_git_sync_api.py` (the converted routes),
  `git_sync` registry tests, `studio_server/test_prompt_optimization_job_api.py`, and the chat
  stream-session tests.
- `git status --porcelain app/desktop/studio_server/api_client/kiln_ai_server_client` — empty.
