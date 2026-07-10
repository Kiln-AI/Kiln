---
status: complete
---

# Architecture: Agent Memory (project: agent_memory)

This project is a datamodel record + a store-agnostic core API + a thin stdio MCP adapter (separate repo) + a cuttable harness adapter. The core is small; most of the care is in (a) making the store binding genuinely parent-agnostic so the decision-10 follow-on is a one-line subclass, and (b) the write-time-only validation / load-leniency invariant.

Grounding: base classes and conventions are read from `libs/core/kiln_ai/datamodel/basemodel.py`. The `Memory` record reuses the id-only child-folder behavior of `KilnParentedModel.build_child_dirname` (a child with no `name` attribute gets a bare `{id}` folder — the `runs/{id}/` pattern named in decision 1).

## 1. Module Layout

### `Kiln-AI/kiln`, `libs/core`

| Path | Responsibility | Status |
|---|---|---|
| `libs/core/kiln_ai/datamodel/memory.py` | `Memory(KilnParentedModel)` — fields + write-time validators. | new |
| `libs/core/kiln_ai/utils/validation.py` | add a **shared** `validate_tags(tags)` helper (see §2.5); `Memory` reuses it instead of adding a 5th copy of the rule. | edit |
| `libs/core/kiln_ai/datamodel/project.py` | register `Memory` under `Project.parent_of` (folder `assistant_memory`, accessor `memories`); typed accessor. | edit |
| `libs/core/kiln_ai/datamodel/__init__.py` | export `Memory`. | edit |
| `libs/core/kiln_ai/memory/__init__.py` | export `MemoryStore` + result types. | new |
| `libs/core/kiln_ai/memory/memory_store.py` | `MemoryStore` — the six operations over a store binding; result/summary Pydantic types. | new |
| `libs/core/kiln_ai/adapters/.../kiln_memory_tools.py` *(cuttable, Phase 3)* | `KilnToolInterface` adapters wrapping `MemoryStore`. | new, cuttable |

Test files alongside source per project convention:

- `libs/core/kiln_ai/datamodel/test_memory.py`
- `libs/core/kiln_ai/memory/test_memory_store.py`
- `libs/core/kiln_ai/memory/test_memory_store_concurrency.py` (multi-process)
- `libs/core/kiln_ai/datamodel/test_parent_of_relationship.py` — extend with the `memories` accessor + `assistant_memory` registration coverage (this is where parent/child relationship behavior is tested; there is no `test_project.py`).

**Why a new `memory/` package (not `tools/`, not `datamodel/`):** the store logic is not a datamodel class and not a `KilnToolInterface` tool — it's the reusable core the tools adapt. Kiln's top-level `kiln_ai` packages are `adapters`, `cli`, `datamodel`, `tools`, `utils`; a peer `memory/` package is the honest home for "store-agnostic memory logic." Adapters (MCP, harness) live in their respective layers/repos and depend on `memory/`.

### `kiln-ai/experiments` (separate repo, Phase 2)

| Path (illustrative; follow experiments-repo conventions) | Responsibility |
|---|---|
| `<experiments>/memory_mcp/server.py` | stdio MCP server: parse `--project`, construct `MemoryStore`, register the six tools, run over stdio. |
| `<experiments>/memory_mcp/tool_descriptions.py` (or inline) | the six tool description texts — spec'd deliverables (see §5.2). |
| `<experiments>/memory_mcp/README.md` | usage + a Claude Code `.mcp.json` example. |
| tests | round-trip each tool; two-server-process concurrency test. |

Pin `kiln-ai` core by git rev of the kiln feature branch during development (the kiln_server precedent). Two PRs; **kiln first** so the experiments repo can pin a real rev.

## 2. Data Model

### 2.1 `libs/core/kiln_ai/datamodel/memory.py`

```python
from pydantic import Field, field_validator

from kiln_ai.datamodel.basemodel import KilnParentedModel
from kiln_ai.utils.validation import validate_tags


class Memory(KilnParentedModel):
    """One memory record of the assistant working on this project.
    Stored at assistant_memory/{id}/memory.kiln. Concurrent-append safe
    (file per memory); updates are last-writer-wins."""

    overview: str = Field(
        max_length=140,
        description=(
            "One-line summary written so a future reader can decide whether to "
            "fetch the full content. For very short memories this IS the whole "
            "memory (leave content null). No newlines."
        ),
    )
    content: str | None = Field(
        default=None,
        max_length=2000,
        description=(
            "The memory body: the finding/fact/decision with its conditions and "
            "evidence level, citing related Kiln records as prose IDs (e.g. "
            "'run_config 184623901234', 'eval 5678'). Null when the overview says "
            "everything. Record observations with conditions ('batch API 429'd at "
            "50rps on 07-04'), never universal rules."
        ),
    )
    tags: list[str] = Field(
        default_factory=list,
        description=(
            "Snake_case tags for filtering (existing Kiln tag rules). Free-form; "
            "skills define the working vocabulary (e.g. experiment, dead_end, "
            "constraint, api_quirk, session_state; faceted tags like lever_prompt, "
            "verdict_accept, evidence_weak)."
        ),
    )
    scope: str = Field(
        description=(
            "Opaque scope string, exact-match filterable. Conventions: 'project' "
            "for project-wide knowledge (constraints, environment facts); "
            "'task::<task_id>' for task-scoped work. Not validated against existing "
            "records — a convention, not a reference."
        ),
    )

    # --- write-time-only, load-safe validators (see §2.4) ---

    @field_validator("overview", mode="before")
    @classmethod
    def _normalize_overview(cls, v): ...   # strip; reject empty; reject newline

    @field_validator("content", mode="before")
    @classmethod
    def _normalize_content(cls, v): ...    # None passthrough; strip; empty -> None

    @field_validator("scope", mode="before")
    @classmethod
    def _normalize_scope(cls, v): ...      # strip; reject empty; reject newline; reject > 255

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, v: list[str]) -> list[str]:
        return validate_tags(v)            # shared helper (§2.5), NOT a 5th copy
```

**No `name` field — deliberate.** `KilnParentedModel.build_child_dirname` (basemodel.py:601) does `getattr(self, "name", None)`; with no `name`, the child folder is exactly `{id}`. That is the id-only-subfolder requirement (decision 1) with zero extra code. `base_filename()` = `type_name() + ".kiln"` = `memory.kiln`, so the on-disk path is `assistant_memory/{id}/memory.kiln`, matching the docstring.

### 2.2 Registration on `Project`

`Memory`'s Python accessor (`memories`) and its on-disk folder (`assistant_memory`) differ, so register with the **decoupled form** — `ParentOfRelationship` (basemodel.py:742), which exists for exactly this "attribute name ≠ folder name" case:

```python
# project.py
from kiln_ai.datamodel.basemodel import (
    FilenameString, KilnParentModel, ParentOfRelationship,
)
from kiln_ai.datamodel.memory import Memory

class Project(
    KilnParentModel,
    parent_of={
        # ... existing relationships ...
        "memories": ParentOfRelationship(model=Memory, filesystem_name="assistant_memory"),
    },
):
    ...
    def memories(self, readonly: bool = False) -> list[Memory]:
        return super().memories(readonly=readonly)  # type: ignore
```

- `relationship_name()` for `Memory` resolves to `assistant_memory` (the folder), while the accessor stays `memories` (the class name carries no "whose memory" semantics — the **folder** does, per decision 10).
- The registration guard (`__init_subclass__`, basemodel.py:808) enforces that `Memory` is registered under exactly one parent — which is *why* the decision-10 per-Task store is a sibling subclass (`class TaskMemory(Memory): ...`) rather than re-registering `Memory`. v1 must not foreclose that; it doesn't.
- Export `Memory` from `datamodel/__init__.py` (`from kiln_ai.datamodel.memory import Memory` + add to `__all__`).

**Additive, no migration.** Projects without an `assistant_memory/` folder return `[]` from `memories()` (the relationship folder simply doesn't exist — `iterate_children_paths_of_parent_path` returns `[]`). No `v` bump.

### 2.3 Import cycle

`project.py` already imports many child models; adding `from kiln_ai.datamodel.memory import Memory` follows the existing pattern (see `skill.py`, `chunk.py` imports at the top of `project.py`). `memory.py` imports only `basemodel`. No cycle.

### 2.4 Write-time-only validation & load leniency (the key invariant)

Decision (project_overview.md §"Validators"): *nothing here may fail on load for data that once saved.* Two mechanisms, both already in the codebase:

1. **Normalize in `mode="before"` validators**, so length is measured on the normalized value. `strip()` is idempotent; `Field(max_length=140/2000)` then applies to the stripped string. This avoids the pitfall where `"  <140 chars>  "` fails the length check before stripping. `content` empty→`None` also happens here.
2. **Monotonic reject rules are inherently load-safe.** A record that saved with a non-empty, newline-free, ≤140 `overview` will always satisfy those checks on reload. So the reject validators do not need a `loading_from_file` guard in v1.
3. **Escape hatch, documented, unused in v1:** if a cap is ever *lowered* (decision 13 says it won't be — caps are fixed write discipline), the reject checks can be gated behind `self.loading_from_file(info)` (the `TaskRun.validate_input_format` pattern, task_run.py:118) so old data still loads. We call this out so the future maintainer knows the lever exists; v1 uses `Field(max_length=…)` + `mode="before"` normalization and needs no guard.

`content` allows newlines (it's a body); only `overview` and `scope` reject newlines (they must stay single-line). `tags` reuses the shared `validate_tags` helper (§2.5).

### 2.5 Shared `validate_tags` helper (dedupe, don't replicate)

The tag rule (reject empty-string tags; reject tags containing spaces) is currently **copy-pasted four times**: `task_run.py:233`, `extraction.py:286`, `spec.py:90` are byte-identical, and `rag.py:71` bundles the same loop with extra tool-name/description checks. Adding a fifth copy for `Memory` is the wrong move. Extract one helper into `utils/validation.py` (which already hosts `tool_name_validator`, `skill_name_validator`, `string_not_empty` — the right home) and reuse it:

```python
# libs/core/kiln_ai/utils/validation.py
def validate_tags(tags: list[str]) -> list[str]:
    """Shared Kiln tag rule: no empty-string tags, no spaces (use underscores)."""
    for tag in tags:
        if not tag:
            raise ValueError("Tags cannot be empty strings")
        if " " in tag:
            raise ValueError("Tags cannot contain spaces. Try underscores.")
    return tags
```

- `Memory` calls it from a `@field_validator("tags")` (the new consumer — this is the whole point of the helper).
- **Consolidate the existing duplicates in the same PR** (recommended, low-risk, identical behavior): `task_run`, `extraction`, and `spec` swap their loop for `validate_tags(self.tags)`; `rag` delegates its tag loop to the helper and keeps its extra empty-list / tool-name checks. One nuance to reconcile: `spec.py` currently lowercases its message ("tags cannot…"); the helper standardizes on the capitalized form used by the other three — update `spec`'s test assertion on that message text if it pins the exact string. If the reviewer prefers to keep the memory PR narrow, the consolidation of the four existing sites can be split into a follow-up cleanup commit, but the helper itself ships with `Memory`.
- `utils/validation.py` imports only `re`/`typing`/`pydantic`; datamodel files already import from `utils`, so there is no import cycle.

## 3. Core Memory API — `libs/core/kiln_ai/memory/memory_store.py`

### 3.1 The store binding

```python
_UNSET = object()  # sentinel: distinguish "field omitted" from "field set to None"

class MemoryStore:
    """Store-agnostic memory operations over a (parent model + Memory class) binding.

    Assumes nothing about the parent beyond: it is a saved KilnParentModel (has a
    `path`) under which `memory_model` is registered. v1 binds Project + Memory;
    the decision-10 follow-on binds Task + a TaskMemory subclass with no change here.
    """

    def __init__(self, parent: KilnParentModel, memory_model: type[Memory] = Memory):
        if parent.path is None:
            raise ValueError("MemoryStore requires a saved parent (path is set).")
        self.parent = parent
        self.memory_model = memory_model
```

The store reads/writes exclusively through the base-model child APIs, which already give lock-free directory scans and cache-backed id lookups:

- list/summary scan → `memory_model.all_children_of_parent_path(self.parent.path, readonly=True)` (basemodel.py:680).
- id fetch → `memory_model.from_ids_and_parent_path(set(ids), self.parent.path)` (basemodel.py:713) — bulk, cache-backed.
- single mutable fetch (for update/delete) → `memory_model.from_id_and_parent_path(id, self.parent.path)` (basemodel.py:690).

Nothing in the store references `Project` or `assistant_memory` by name — the binding carries both. That is what makes it reusable (decision 9).

### 3.2 Operations

```python
def save_memory(self, *, overview, scope, content=None, tags=None) -> Memory:
    mem = self.memory_model(
        parent=self.parent, overview=overview, scope=scope,
        content=content, tags=list(tags or []),
    )
    mem.save_to_file()          # writes assistant_memory/{id}/memory.kiln
    return mem

def get_memories(self, ids: list[str]) -> list[Memory]:
    found = self.memory_model.from_ids_and_parent_path(set(ids), self.parent.path)
    return list(found.values())  # unknown ids simply absent

def update_memory(self, id, *, overview=_UNSET, content=_UNSET,
                  tags=_UNSET, scope=_UNSET) -> Memory:
    mem = self.memory_model.from_id_and_parent_path(id, self.parent.path)
    if mem is None:
        raise MemoryNotFoundError(id)     # clear signal, not silent success
    if overview is not _UNSET: mem.overview = overview   # validate_assignment fires
    if content  is not _UNSET: mem.content  = content    # "" -> None via validator
    if tags     is not _UNSET: mem.tags     = list(tags or [])
    if scope    is not _UNSET: mem.scope    = scope
    mem.save_to_file()          # last-writer-wins
    return mem

def delete_memory(self, id) -> None:
    mem = self.memory_model.from_id_and_parent_path(id, self.parent.path)
    if mem is None:
        raise MemoryNotFoundError(id)
    mem.delete()                # shutil.rmtree of the {id}/ folder (basemodel.py:511)
```

`validate_assignment=True` is set on `KilnBaseModel` (basemodel.py:320), so assigning `mem.overview = …` re-runs the field validators — over-length / newline / empty are rejected on update exactly as on create. The `_UNSET` sentinel is what makes partial replace correct: `content=None` explicitly clears, `content` omitted leaves it untouched.

### 3.3 `list_memories` + truncation

```python
def list_memories(self, *, scope=None, tags=None, content_match=None,
                  limit=50, offset=0) -> "MemoryListResult":
    mems = self.memory_model.all_children_of_parent_path(self.parent.path, readonly=True)

    # filter (AND across provided filters)
    if scope is not None:
        mems = [m for m in mems if m.scope == scope]
    if tags:
        want = set(tags)
        mems = [m for m in mems if want.issubset(set(m.tags))]
    if content_match is not None:
        try:
            rx = re.compile(content_match, re.IGNORECASE)
        except re.error as e:
            raise InvalidContentMatchError(str(e))
        mems = [m for m in mems if rx.search(m.overview) or (m.content and rx.search(m.content))]

    # newest-first, stable tiebreak on id for deterministic paging
    mems.sort(key=lambda m: (m.created_at, m.id), reverse=True)

    matched = len(mems)
    page = mems[offset:offset + limit]
    remainder = mems[offset + len(page):]
    remaining_tag_counts = _tag_counts(remainder)   # Counter, sorted desc by caller

    return MemoryListResult(
        listings=[_to_listing(m) for m in page],   # id, overview, tags, scope, content_length, created_at, created_by
        matched=matched,
        remaining=len(remainder),
        remaining_tag_counts=remaining_tag_counts,
    )
```

- `content_length` = `0` if `content is None` else `len(content)`.
- `remaining_tag_counts` counts tags over the **not-returned remainder** (functional_spec §7). The core returns structured counts; each **adapter** renders the nudge string `"{remaining} more — filter by tag: {t}({n}), …"` (adapters own prompt text, decision 9 / "tool results are prompts").
- readonly=True → cache-backed, no mutable-copy overhead on the scan.

### 3.4 `memory_summary`

```python
def memory_summary(self, scope=None) -> "MemorySummary":
    mems = self.memory_model.all_children_of_parent_path(self.parent.path, readonly=True)
    if scope is not None:
        mems = [m for m in mems if m.scope == scope]
    # group by scope; per group: count, newest created_at, tag counts (desc), untagged (if > 0)
    # scopes sorted by newest desc; total = len(mems)
    ...
```

Per functional_spec §8: grouping is always per-scope; `tags` sorted desc; `untagged` present only when nonzero; scopes newest-first; no content, no overviews.

### 3.5 Result types (Pydantic, in the same module)

```python
class MemoryListing(BaseModel):
    id: str
    overview: str
    tags: list[str]
    scope: str
    content_length: int
    created_at: datetime
    created_by: str

class MemoryListResult(BaseModel):
    listings: list[MemoryListing]
    matched: int
    remaining: int
    remaining_tag_counts: dict[str, int]   # sorted desc by insertion

class ScopeSummary(BaseModel):
    scope: str
    count: int
    newest: datetime
    tags: dict[str, int]
    untagged: int | None = None            # omitted from output when None/0

class MemorySummary(BaseModel):
    total: int
    scopes: list[ScopeSummary]
```

Pydantic (not dataclasses) so the MCP adapter serializes results to JSON with `model_dump()` and `exclude_none=True` (drops `untagged` when absent), matching the functional_spec §8 JSON exactly.

### 3.6 Errors

Small, explicit exception types in the `memory` package: `MemoryNotFoundError(id)` and `InvalidContentMatchError(msg)`. Validation errors from create/update propagate as Pydantic `ValidationError`. Adapters convert all of these into tool-error results (MCP `isError`, harness `ToolCallResult(is_error=True, ...)`); they never crash the server/harness.

## 4. Concurrency (design + test)

The store never serializes writes and needs no lock:

- **save** → a new `{id}/memory.kiln`; `save_to_file` (basemodel.py:479) does `mkdir(parents=True, exist_ok=True)` then a single `open(w)` write. Distinct ids ⇒ distinct files ⇒ no interleave. This is the whole reason for file-per-record with random ids.
- **update** → overwrites one record's file; two updaters race to last-writer-wins on that one file (accepted).
- **read** → `os.scandir` walk (basemodel.py:671); tolerates files appearing/vanishing mid-scan.

**Test (`test_memory_store_concurrency.py`):** spawn ≥2 OS processes (e.g. `multiprocessing.Process` or `concurrent.futures.ProcessPoolExecutor`) each constructing its own `MemoryStore` on the *same* project folder and doing a burst of `save_memory` (plus some `update_memory` on a shared id). Assert: (a) the number of records equals the total saved (no lost appends), (b) same-id updates leave a single valid record whose fields match one of the writers (last-writer-wins, not a corrupt merge), (c) every `memory.kiln` on disk parses (`Memory.load_from_file`). The MCP layer repeats this with two **server processes** (the real Phase-0 topology) in the experiments repo.

> Note on the model cache: `ModelCache` (basemodel.py) is per-process. Cross-process writes are seen because the store scans the directory and `load_from_file` validates mtime for cache invalidation. The concurrency test must read with a fresh store/process (or accept that a long-lived reader sees its own process's cache) — the Phase-0 topology is one process per session, so this matches reality. Call this out in the test.

## 5. Adapters

### 5.1 stdio MCP server (experiments repo, Phase 2)

- Official MCP Python SDK, **stdio** transport. On startup: require `--project /path/to/project.kiln`, load the `Project`, construct `MemoryStore(project)`. **No `--default-scope`, no scope defaults** — the client passes `scope` explicitly per tool.
- Register six tools whose names/params are identical to functional_spec §6. Each tool body: call the matching `MemoryStore` method, serialize the result (`model_dump`, `exclude_none=True`), render the truncation nudge string for `list_memories`. Convert store exceptions to MCP tool errors.
- Nothing memory-shaped lives in the server — it's a mechanical adapter.

### 5.2 Tool description texts (spec'd deliverables — authored in Phase 2)

The six description strings are prompts and are part of the deliverable. Requirements per functional_spec §6 (write-discipline list; "list before you save — update, don't duplicate"; conditions-not-rules; `content_length: 0` meaning; `tags` AND-semantics + multi-call-for-OR; "call `memory_summary` at session start"; prefer `stale`-tag-plus-correction over rewrites; "delete only confirmed junk"). They live with the MCP server (and are re-used by the harness adapter). The tag vocabulary they reference is O3-repo skill work (out of scope here) — the descriptions name representative tags, not a closed enum.

### 5.3 Harness `KilnToolInterface` adapter (cuttable, Phase 3)

- Implement the six tools against `KilnToolInterface` (base_tool.py:46): `run(**kwargs) -> ToolCallResult`, `toolcall_definition()`, `id()`, `name()`, `description()`. Construct each bound to a `MemoryStore` on the **current run's project** (`scope` stays an explicit tool param — no injection).
- Tool IDs: add a built-in prefix for memory tools (e.g. `kiln_tool::memory::save`, following the `kiln_tool::…` family in `tool_id.py`) and wire them into `tool_from_id` (`tool_registry.py`). Exact id scheme is Phase-3 discretion.
- **Agent policy:** all six agent-allowed, no approval gate (decision 11). Note: `ALLOW_AGENT` in the codebase (`libs/server/.../agent_checks/policy.py`) is a **REST/openapi_extra** annotation, and this project has **no REST surface** (decision 12). "Agent-allowed, no approval" is therefore realized in the harness tool layer (the tool is simply available to the agent with no approval prompt), not via the REST policy constant. Reconcile with whatever approval mechanism the harness uses at build time.
- **Phase 0 does not depend on this.** If cut, the MCP server (Phase 2) is the only consumer and the project still ships its Day-1 value.

## 6. What this project does NOT touch

- No REST endpoints, no `kiln_server` changes (decision 12).
- No UI / web_ui changes (decision 12).
- No artifact-provenance code (Part 1) — reference only via prose IDs in `content`.
- No schema-version bump; no migration.
- No `Task`-bound memory store, no `TaskMemory` subclass, no `ToolId` exposure for user agents (decision 10 is a constraint, not a build item) — but the `MemoryStore(parent, memory_model=…)` signature and generic `Memory` class name exist precisely so that follow-on is additive.

## 7. Tests (placement of the functional_spec §12 checklist)

| Functional_spec §12 group | File |
|---|---|
| 12.1 Datamodel (`Memory`) | `datamodel/test_memory.py`; `memories` accessor + registration coverage in `datamodel/test_parent_of_relationship.py` |
| 12.2 Core memory API | `memory/test_memory_store.py` |
| 12.3 Concurrency | `memory/test_memory_store_concurrency.py` (multi-process) |
| 12.4 MCP server | experiments repo test suite (Phase 2) |
| 12.5 Harness adapter | alongside the adapter (Phase 3, cuttable) |

Run `uv run ./checks.sh --agent-mode` in the kiln repo before each phase PR.

## 8. Implementation order (informational; implementation_plan.md drives phasing)

1. `Memory` datamodel + validators + registration + export; `test_memory.py`; project-accessor test. (kiln)
2. `MemoryStore` + result types + errors; `test_memory_store.py`; multi-process concurrency test. (kiln) → **kiln PR**.
3. stdio MCP server + tool descriptions + README + two-process concurrency test; pin kiln core by rev. (experiments) → **experiments PR**.
4. *(cuttable)* harness `KilnToolInterface` adapter + registry wiring + agent policy. (kiln)
