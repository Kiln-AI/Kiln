---
status: complete
---

# Functional Spec: Agent Memory (project: agent_memory)

## 1. Summary

Adds a durable, concurrent-append memory store for the assistant working on a Kiln project. Three deliverables across two repos:

1. **`Memory` datamodel** — a `.kiln` child of `Project`, stored one-file-per-record under `assistant_memory/{id}/memory.kiln`. Fields: `overview` (required, ≤140), `content` (nullable, ≤2,000), `tags`, `scope`, plus inherited `id` / `created_at` / `created_by`. (`Kiln-AI/kiln`, `libs/core`.)
2. **Core memory API** — reusable plain-Python logic in `libs/core` exposing six operations (`save` / `list` / `get` / `update` / `delete` / `summary`) over a **store binding** (a parent model + its memory folder). It assumes nothing about the parent beyond "it's a Kiln parent model with a path." (`Kiln-AI/kiln`, `libs/core`.)
3. **stdio MCP server** — an internal adapter in `kiln-ai/experiments` that wraps the core API and exposes the six tools to Claude Code over stdio. This is the Phase 0 consumer (the O3 compile agent). (`kiln-ai/experiments`.)

A fourth, **cuttable** deliverable — a `KilnToolInterface` adapter that exposes the same six tools to the Kiln agent harness — is spec'd but not required by Phase 0.

The design goal underpinning every decision: the memory logic is a store-agnostic core with mechanical adapters on top, so the exact same six operations serve the MCP server today and (later, additively) a per-Task memory store bound to a *separate* folder for users' runtime agents. See project_overview.md decisions 9 and 10.

**This is not a UI project and not a REST project.** The tools are the interface (decision 12). `.kiln` files are human-readable and ride the project directory's existing git-sync/backup story.

## 2. Goals

- One `Memory` record class, one folder (`assistant_memory/`), id-only subfolders — so nothing about a memory's text affects its path, and many parallel processes append concurrently with no locking.
- Six memory operations available identically on every surface (MCP now, harness later), with **`scope` an explicit input on every write** and **no scope defaults anywhere**.
- Retrieval is **list-then-read**: recency sort + exact-match `scope` filter + AND-semantics `tags` filter + case-insensitive `content_match` regex. No vector store, no embeddings, no search index.
- Write discipline is enforced structurally by the caps (140 / 2,000) and carried in prose by the tool descriptions (which are spec'd deliverables, not incidental strings).
- Concurrent appends from separate processes never corrupt the store; concurrent updates to the *same* record are last-writer-wins.
- Backward compatible and forward compatible: purely additive registration (old clients ignore the unknown folder), and a model that once saved must never fail to load.

## 3. Non-Goals (v1)

- No vector store, embeddings, semantic search, or consolidation/"dreaming" (see project_overview.md "Deferred, with triggers").
- No `session_id` field, no structured links / `evidence_refs` field, no `properties` dict. References to other Kiln records live in `content` as prose IDs.
- No scope validation beyond format (no prefix registry, no existence checks, no cross-record validation).
- No UI (browser is P2). No REST CRUD endpoints.
- No per-Task / user-agent memory binding **build** — it is a design constraint that v1 must not block, not a v1 deliverable (decision 10).
- No changes to artifact provenance (Part 1). The two systems meet only via prose ID references.
- No `agent_info` integration of `memory_summary` (the `memory_summary` **tool** is in scope; folding it into `agent_info` is deferred).

## 4. Data Model

### 4.1 `Memory`

A `KilnParentedModel` (child of `Project` in v1). Field names and descriptions are authoritative per project_overview.md "Datamodel sketch".

| Field | Type | Required | Constraint | Role |
|---|---|---|---|---|
| `overview` | `str` | yes | ≤140 chars, no newlines, non-empty after strip | The load-decision signal: "should I fetch this?" For very short memories it IS the whole memory. |
| `content` | `str \| None` | no (default `None`) | ≤2,000 chars; empty→`None` after strip | The memory body. `None` ⇒ listing shows `content_length: 0` ⇒ no fetch needed. |
| `tags` | `list[str]` | no (default `[]`) | existing Kiln tag rules (non-empty, no spaces) | Filtering. Free-form; vocabulary is skill-owned. |
| `scope` | `str` | yes | ≤255 chars, no newlines, non-empty after strip | Opaque exact-match filter key. Conventions (`"project"`, `"task::<id>"`) live in guidance, not schema. |
| `id` | inherited | — | 12-digit string, auto | The fetch key: unique, few tokens, exactly reproducible in a tool call. |
| `created_at` | inherited | — | tz-aware datetime, auto | Recency sort key; staleness signal. |
| `created_by` | inherited | — | str, auto | Attribution (replaces the dropped `session_id`). |

**Note on `id` as fetch key.** Kiln's `generate_model_id()` produces a 12-digit numeric string. It is unique within a parent/child relationship, cheap to type, and exactly reproducible by the model in a follow-up tool call — which is why it, not `overview`, is the `get_memories` key.

### 4.2 Validators (all write-time format checks only)

Per project_overview.md, nothing here may fail on load for data that once saved. Validators run on new/mutated records; on load-from-file they either don't run or are lenient (`loading_from_file` leniency), so a record that once saved always loads.

- **`overview`**: strip; reject empty; reject if it contains a newline; enforce ≤140 (max_length).
- **`content`**: strip; empty string → `None`; enforce ≤2,000 (max_length). `None` is allowed and is the "overview says everything" case.
- **`tags`**: reuse the existing Kiln tag rule — reject empty-string tags and tags containing spaces. This rule is today copy-pasted across four models (`TaskRun`, `ExtractorConfig`, `Spec`, `RagConfig`); v1 extracts it into a single shared `validate_tags` helper in `utils/validation.py` and `Memory` reuses it rather than adding a fifth copy (see architecture §2.5). Free-form otherwise; never a closed enum.
- **`scope`**: strip; reject empty; reject if it contains a newline; enforce ≤255. **No validation beyond format** — no prefix registry, no existence check against tasks. A dangling `task::<deleted_task_id>` scope is a harmless unqueried string.

### 4.3 Registration

- Add `Memory` to `Project.parent_of` with **on-disk folder `assistant_memory`** and **Python accessor `memories`** (the accessor name and folder name differ, so the registration uses the decoupled form — see architecture §2.2).
- Storage path: `<project_folder>/assistant_memory/{id}/memory.kiln`. Subfolders are **id-only** (no name prefix) because `Memory` has no `name` field.
- Export `Memory` from `datamodel/__init__.py`.
- Purely additive: old clients ignore the unknown `assistant_memory/` folder; no migration; no schema-version (`v`) bump.

## 5. Store Binding (the reusable-core contract)

The core API is constructed with a **store binding**: a parent Kiln model (with a `path`) plus the `Memory` model class registered under it. The core assumes nothing else about the parent (decision 9). Concretely:

- v1 binds to a `Project` and the `Memory` class.
- The follow-on (decision 10, out of scope to build) will bind a sibling `TaskMemory(Memory)` subclass to a `Task` and a *separate* folder. Because Kiln's registration guard forbids registering one child class under two parents, the follow-on adds a one-line subclass; the core API takes the model class as part of the binding so it needs no change.
- **Isolation is structural**: a store bound to Project A's `assistant_memory/` can never read Project B's, and a future user-Task store can never read the assistant's — different parent, different folder, different store instance. No `scope` string can cross stores; `scope` filters *within* a store only.

There are **no scope defaults on any surface**. Every write takes `scope` explicitly; scope conventions are guidance, not code.

## 6. Tool API (six operations)

The operations below are the behavioral contract. They are realized as (a) core Python methods, (b) MCP tools, and (c) — cuttable — harness `KilnToolInterface` tools. Params and semantics are identical across surfaces.

### 6.1 `save_memory`

- **Params:** `overview` (req), `scope` (req), `content?`, `tags?`.
- **Behavior:** creates a new `Memory` under the bound store, writing a fresh `{id}/memory.kiln`. Returns the new `id` plus an echo of the saved record.
- **Concurrency:** each save is a new file with a random id — concurrent saves from separate processes never collide.
- **Description requirements (spec'd deliverable):** must carry the write discipline — a memory-worthy list (probe results w/ evidence level; rejected approaches + why; API quirks; constraints/preferences; future ideas; session state); the instruction "list related memories first — update instead of duplicating"; and conditions-not-rules phrasing ("record observations with conditions, never universal rules"). Must state that `scope` is explicit, with the `"project"` / `"task::<id>"` conventions.

### 6.2 `list_memories`

- **Params:** `scope?` (exact match; omit = all scopes), `tags?` (list; AND semantics — a memory must have **all** listed tags; OR is done with multiple calls), `content_match?` (case-insensitive regex matched over `overview` + `content`), `limit?` (default 50), `offset?` (default 0).
- **Returns:** per memory — `id`, `overview`, `tags`, `scope`, `content_length` (0 when `content` is `None`, else `len(content)`), `created_at`, `created_by`. **Sorted newest-first** by `created_at`.
- **Truncation nudge (spec'd deliverable):** when the full matched set exceeds the returned page, the result text says so and lists tag counts of the **not-returned remainder** as a filtering nudge — e.g. `"62 more — filter by tag: probe(18), api_quirk(9), …"`. (See §7 for exact semantics.)
- **Description requirements:** explains `tags` AND-semantics and the multiple-calls-for-OR pattern; explains `content_match` is a regex over overview + content; explains `content_length: 0` means the overview is the whole memory.

### 6.3 `get_memories`

- **Params:** `ids` (one or many).
- **Returns:** full records for the requested ids (all persisted fields). Unknown ids are omitted from the result (not an error) — the result is the set of found records.
- **Description requirements:** "`content_length` 0 in listings means the overview is the entire memory — no need to fetch"; "fetch in batches, not all at once".

### 6.4 `update_memory`

- **Params:** `id`, and any of `overview?`, `content?`, `tags?`, `scope?`.
- **Behavior:** partial replace — only provided fields change; omitted fields are untouched. Provided fields are re-validated by the same write-time validators (e.g. an over-length `overview` is rejected). Open to **any** caller (no own-session restriction). Standard Kiln save = **last-writer-wins**. Returns the updated record.
- **Explicit `content` clearing:** passing `content=""` (or whitespace) sets `content` to `None` via the content validator; omitting `content` leaves it unchanged. (An explicit `null`/`None` for `content` also clears it.)
- **Description requirements:** prefer adding a `stale` tag + writing a new correction memory over rewriting someone else's `content`; the main legitimate rewrite case is a rolling session-state memory.

### 6.5 `delete_memory`

- **Params:** `id`.
- **Behavior:** hard delete — removes the `{id}/` folder. For confirmed junk only. Idempotent-ish: deleting an unknown id is a no-op-with-signal (see §9). Returns success.
- **Description requirements:** "for confirmed junk; prefer `stale` tagging for 'wrong but instructive'."

### 6.6 `memory_summary`

- **Params:** `scope?` (omit = all scopes).
- **Behavior:** cheap orientation, **no record content**. Same folder scan as `list_memories`. Output per §8. No caps, no truncation.
- **Description requirements:** "call at session start before targeted lists".

## 7. `list_memories` — filtering, sorting, and truncation

Given a store scan of all `Memory` records under the binding:

1. **Filter** (AND across all provided filters):
   - `scope`: keep records whose `scope == scope` (exact string match). Omitted ⇒ no scope filter.
   - `tags`: keep records whose `tags` is a superset of the requested list (every requested tag present). Omitted / empty ⇒ no tag filter.
   - `content_match`: keep records where the case-insensitive regex matches anywhere in `overview` OR (`content` if non-null). Omitted ⇒ no content filter. An **invalid regex** is a caller error (see §9).
2. **Sort** the filtered set newest-first by `created_at` (ties broken deterministically — e.g. by `id` — so paging is stable).
3. **Page**: skip `offset`, take `limit`.
4. **Truncation summary**: let `matched` = size of the filtered set. If `offset + len(page) < matched`, the store reports:
   - `remaining` = `matched - (offset + len(page))` (the count beyond this page).
   - `remaining_tag_counts` = tag cardinalities computed over the **remaining (not-returned) records**, sorted by count descending. This is the data behind the nudge string `"{remaining} more — filter by tag: {tag}({n}), …"`. Records with no tags contribute to no tag count (an untagged remainder is not surfaced here — `memory_summary` is where untagged visibility lives).
   - The exact rendering of the nudge string (how many tags to list, ellipsis) is an adapter concern; the **core returns the structured counts** and the adapters render the prompt-facing text.

**Rationale for remainder-based tag counts:** the nudge exists to help the agent narrow an over-broad listing. Counting the *remainder* (not the whole matched set) tells the agent what it hasn't seen yet and how to slice it.

## 8. `memory_summary` — output

Unscoped call returns all scopes; scoped call returns just that scope's block (same shape, no wrapper). Grouping is **per scope, always**.

```json
{
  "total": 87,
  "scopes": [
    {
      "scope": "task::184623901234",
      "count": 75,
      "newest": "2026-07-10T18:04:11Z",
      "tags": {"experiment": 20, "probe": 14, "dead_end": 9, "hypothesis": 7, "session_state": 3},
      "untagged": 2
    },
    {
      "scope": "project",
      "count": 12,
      "newest": "2026-07-08T09:12:44Z",
      "tags": {"api_quirk": 5, "lesson": 4, "constraint": 3, "env_fact": 2}
    }
  ]
}
```

- `total` = total memories in the store (or in the one scope, for a scoped call).
- `count` = memories in the scope.
- `tags` = filter cardinalities **sorted by count desc**. Each number is exactly what `list_memories(scope=…, tags=[t])` would return for that scope. A multi-tagged memory contributes to each of its tags, so the tag counts can sum to more than `count` — intentional.
- `untagged` = number of memories in the scope with zero tags. **Present only when nonzero** (an untagged memory is invisible to any tag filter, so the agent needs to know it exists).
- `newest` = most recent `created_at` in the scope. **Scopes are sorted newest-first** by their `newest` (recency = where the action is; also a staleness signal for old task scopes).
- Nothing else: no overviews, no content, no `created_by` breakdown. Orientation only; the follow-up is a targeted `list_memories`.

## 9. Error Handling

| Condition | Surfaced as |
|---|---|
| `save_memory` / `update_memory` with an invalid field (over-length `overview`/`content`/`scope`, newline in `overview`/`scope`, empty `overview`/`scope`, tag with a space, etc.) | Validation error — the write is rejected with a message the caller (and the model) can act on. Adapters surface it as a tool error result, not a crash. |
| `list_memories` with an invalid `content_match` regex | Caller error with a clear message ("invalid regex: …"); no records returned. |
| `get_memories` with unknown id(s) | Not an error — unknown ids are omitted; found records are returned. |
| `update_memory` / `delete_memory` with an unknown id | A clear "no memory with id … in this store" signal (not a silent success — the model should know its id was wrong). |
| Store not bound / parent has no `path` | Programming error at construction time (the adapter guarantees a bound store). |

The general philosophy mirrors the rest of Kiln: format/validation failures are attributable caller errors; a memory that once saved never fails to load.

## 10. Concurrency

The concurrency model is the reason for file-per-record with random ids (decision 1).

- **Appends (saves) are the dangerous case in single-file stores, and are eliminated here.** Each `save_memory` writes a distinct `{id}/memory.kiln`. N processes saving concurrently produce N files; none overwrites another; the store never corrupts. (Contrast the rejected single-JSONL design, which corrupts under parallel writers.)
- **Updates to the *same* record are last-writer-wins.** This is accepted: the dangerous race was parallel appends, not parallel edits of one record. Guidance (skills) steers agents toward "add a `stale` tag + write a correction" over rewriting others' records.
- **Reads (list/get/summary) are lock-free** directory scans; they tolerate concurrent writers (a record appearing/disappearing mid-scan is fine — the scan sees a consistent-enough snapshot for orientation).

**Test obligation (v1):** a multi-process test in which ≥2 processes concurrently `save` (and `update`) against the same folder, asserting: every append survives (no lost writes), same-record updates resolve last-writer-wins, and no file is left corrupt/half-written. In the MCP layer (experiments repo) this is repeated with two **server processes** (stdio = one process per session), the real Phase-0 topology.

## 11. Backward & Forward Compatibility

- **Additive registration.** Adding `assistant_memory` to `Project.parent_of` doesn't touch existing folders. Projects created before this change simply have no `assistant_memory/` folder; the accessor returns an empty list. No migration, no `v` bump.
- **Load leniency.** Write-time validators do not run destructively on load; a `Memory` that once passed validation always loads, even if conventions later change (e.g. a scope string that a future convention would discourage still loads fine).
- **Scope is forward-compatible by construction.** New scope conventions (`task_run::…`, anything) are new strings, zero datamodel change.
- **Store binding is forward-compatible.** The per-Task follow-on is a sibling subclass + a new binding; the core API is unchanged.

## 12. Tests (authoritative checklist)

The architecture doc (§7) restates these with file placement. The coding agent does not add or omit tests beyond this list without surfacing the decision in the phase plan.

### 12.1 Datamodel (`Memory`)

- `overview`: accepts ≤140; rejects >140; rejects newline; rejects empty/whitespace-only; strips surrounding whitespace.
- `content`: accepts `None`; accepts ≤2,000; rejects >2,000; empty/whitespace-only → `None`; strips.
- `tags`: accepts snake_case list; rejects a tag with a space; rejects an empty-string tag; defaults to `[]`.
- `scope`: required; accepts ≤255; rejects >255; rejects newline; rejects empty/whitespace; strips. Accepts arbitrary opaque strings (`"project"`, `"task::123"`, `"anything"`), including a dangling `task::<nonexistent>`.
- Registration: a `Memory` saved under a `Project` lands at `assistant_memory/{id}/memory.kiln` (id-only folder, no name prefix); `project.memories()` returns it; round-trips through save/load equal.
- Backcompat: a `Project` with no `assistant_memory/` folder returns `[]` from `memories()`. A saved `Memory` loads cleanly (load leniency) even if re-validated.

### 12.2 Core memory API

- `save_memory` returns a new id + echoes the record; the file exists on disk.
- `list_memories`: newest-first order; `scope` exact-match filter; `tags` AND-semantics (superset); `content_match` case-insensitive regex over overview + content; `limit` / `offset` paging; `content_length` is 0 for null content and `len(content)` otherwise.
- `list_memories` truncation: `remaining` count correct; `remaining_tag_counts` computed over the not-returned remainder, sorted desc; no truncation info when the page covers the matched set.
- `list_memories` invalid regex → caller error.
- `get_memories`: single and multiple ids; unknown ids omitted; full fields returned.
- `update_memory`: partial replace (only provided fields change); re-validates provided fields (over-length rejected); `content=""` clears to `None`; unknown id → clear error; last-writer-wins across two loads of the same record.
- `delete_memory`: removes the folder; unknown id → clear signal; a subsequent `list` no longer shows it.
- `memory_summary`: per-scope grouping; `count`, `newest`, `tags` (desc), `untagged` present only when nonzero; scopes sorted newest-first; scoped call returns just that scope's block; `total` correct.

### 12.3 Concurrency

- Multi-process: ≥2 processes concurrently `save` (and `update`) the same folder — all appends survive, same-record updates are last-writer-wins, no corruption. (Repeated at the MCP layer with two server processes in the experiments repo.)

### 12.4 MCP server (experiments repo)

- Each of the six tools round-trips through the stdio transport with params identical to §6.
- `--project` binds the store; omitting it is a startup error; no `--default-scope` exists.
- Two-server-process concurrency test (the Phase-0 topology).
- Tool description texts are present and carry the required write-discipline / semantics content (§6).

### 12.5 Harness adapter (cuttable Phase 3)

- The `KilnToolInterface` adapter exposes the six tools bound to the current run's project; `scope` stays an explicit param (no injection); all six are agent-allowed with no approval gate.

## 13. Opens (resolved in architecture)

- Exact module path for the core memory API in `libs/core` and its class name.
- The concrete shape of the structured return values (list result / summary result) — dataclass vs Pydantic, field names.
- How the registration decouples the `memories` accessor from the `assistant_memory` folder (the `ParentOfRelationship` form).
- Exact rendering of the truncation nudge string in each adapter (the core returns structured counts).
- Where the multi-process concurrency test lives and how it spawns processes.
