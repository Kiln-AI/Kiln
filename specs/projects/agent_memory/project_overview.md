---
status: complete
---

# Agent Memory (Assistant Memory Tool) — Project Overview

Build Kiln's **general agent memory system**: a `Memory` `.kiln` record stored under a project's `assistant_memory/` folder, a six-tool memory API implemented as reusable core logic in `libs/core`, and a **stdio MCP server** (internal, in the experiments repo) so the O3 compile agent can use it from Claude Code during Phase 0. This is **Part 2 of agent memory**; Part 1 (artifact provenance) is spec'd at [../artifact_provenance/project_overview.md](../artifact_provenance/project_overview.md) and merged into planning. This document is the self-contained kickoff for the coding agent — all decisions are captured here; no discussion needs re-opening.

**Target repos:**
- `Kiln-AI/kiln` — `libs/core/kiln_ai`: datamodel + core memory logic + tests (+ optional final phase: `KilnToolInterface` adapter). Off `main`.
- **`kiln-ai/experiments`** (internal) — the stdio MCP server wrapping the core; pin `kiln-ai` core by git rev of the kiln feature branch during development (the kiln_server precedent). **One coding task spans both repos**: two PRs, kiln first.

Reference research (O3 planning repo): [agent memory APIs](../../../research/agent_memory_apis/summary.md) (prior art this design is validated against), [planning/agent_memory.md](../../../planning/agent_memory.md) (original requirements), [datamodel](../../../research/kiln_tech/datamodel.md) (base classes, registration guard, tag validator, perf conventions). O3-side adoption plan (skills/playbook updates, tag vocabulary): [planning/memory_spec_updates.md](../../../planning/memory_spec_updates.md). Decision log: O3 [discussion queue](../../../planning/discussion_queue.md) Q16.

## Why (one paragraph)

The compile/auto-research agent accumulates knowledge that dies at context compaction: probe results, rejected approaches and why, API quirks, customer constraints, session state. Artifact provenance (Part 1) preserves the slice of this that is *about one artifact and known at its creation*; everything else — dead ends that produced no artifact, world facts, preferences, working state — needs a durable, concurrent-append store. The cost of losing it is measured: across 24,008 RE-Bench agent runs, failed runs account for 90.2% of dollar cost, and agents without prior failure records independently rediscover every dead end (arXiv 2604.24658). Division of labor (locked in Q15): memories may reference artifacts; artifacts never point at memories; provenance is never written twice. Day-1 consumer: our compile agent running in Claude Code against a partner's Kiln project, via the MCP server.

## Decisions (locked, scosman 2026-07-10)

1. **Storage: `Memory` is a `.kiln` child of `Project`**, filesystem folder **`assistant_memory/`** (name signals it's *our assistant's* memory, not the user's tasks'). Subfolders are **id-only** (the `runs/{id}/` pattern — no name prefix), so nothing about a memory's text affects paths. File-per-memory with random IDs = many parallel sessions/processes append concurrently with no locking; this is the concurrency design, not an accident.
2. **Scope is data, not structure.** One class, one folder; `scope: str` is an **opaque string** field. Conventions, owned by skills/tool-descriptions and *not* by schema: `"project"` (project-wide: constraints, env facts) and `"task::<task_id>"` (the default working scope). Future scopes (`task_run::<id>`, anything) are new conventions, zero datamodel change. **No scope validation beyond format, ever** — write-time format checks only (trimmed, non-empty, no newlines, ≤255 chars); no prefix registry, no existence checks. A deleted task leaves dangling `task::<id>` scopes = harmless unqueried strings; a model must never become invalid on load. Typo'd scopes (accepted risk) are discoverable via list-all.
3. **Record shape** (see sketch): `overview` (required, ≤140 chars, no newlines) + `content` (optional, ≤2,000 chars) + `tags` + `scope`, plus inherited `id`/`created_at`/`created_by`. **`id` is the fetch key** (unique, few tokens, exactly reproducible in a tool call); **`overview` is the load-decision signal** ("should I fetch this?"), not a title. **`content` is nullable**: short memories ("API X is limited to 5rps") are complete in the overview; `content=None` ⇒ listing shows `content_length: 0` ⇒ no fetch needed.
4. **No `session_id` field** (dropped: session identity isn't reliably defined across surfaces, and a field we can't dependably populate is landfill; `created_by` + `created_at` are inherited and cover attribution). Additive later if parallel-session engagements prove the need.
5. **No structured links field.** References to run_configs/evals/traces go in `content` as prose, type + scope-local ID ("run_config 184623901234") — same convention as Part 1's evidence-in-`provenance.notes`. Structured typed refs are a shared v2 with `evidence_refs`.
6. **Tags reuse the existing Kiln tag validator** (the `TaskRun.tags` no-spaces/snake_case rules). Free-form; vocabulary is skill-owned (seed set in [memory_spec_updates.md](../../../planning/memory_spec_updates.md)); never a closed enum.
7. **Retrieval is list-then-read; no vector store, no embeddings.** Relevance signals: recency sort, tag filter, and `content_match` regex. Proven shape (Anthropic's memory tool ships list-then-read only, at frontier scale). Search upgrades are deferred-with-triggers, not v1.
8. **`update_memory` is open to any caller** (no own-session restriction), partial field replace, standard Kiln save = last-writer-wins (accepted: the dangerous race was parallel *appends*, which file-per-memory eliminates). Corrections pattern lives in skill guidance: prefer adding a `stale` tag + writing a correction memory over silently rewriting; newer wins on conflict. `delete_memory` is a hard delete (junk removal).
9. **Layering (the "reusable outside Kiln" requirement):** core memory logic is plain Python in `libs/core`, constructed with a **store binding** (parent model + folder) and **must assume nothing about what the parent is**. Adapters on top: (a) the stdio MCP server (Phase 0 consumer, wraps the core directly), (b) a `KilnToolInterface` adapter for the Kiln agent harness (final phase, cuttable). Adapters are purely mechanical store bindings — **no scope defaults anywhere on any surface**: `scope` is an explicit API input on every write, and scope conventions live in guidance (skills / tool descriptions), so every surface behaves identically.
10. **User-task exposure is a named follow-on and a design constraint now, not a build item.** Later, users' runtime agents get these same tools bound to a *separate* memory folder under their **Task** (registration guard ⇒ a sibling model class, one-line subclass). Isolation is structural: separate store, separate tool instance — **user tasks must never be able to read the assistant's memory**, and no scope string can cross stores. Nothing in v1 may block this (hence store-binding, hence generic class naming — the folder name `assistant_memory`, not the class, carries the "whose memory" semantics).
11. **Agent access policy** (harness adapter phase): all six tools `ALLOW_AGENT`, no approval gates — it's the assistant's own memory; delete included (an agent that can't prune its own landfill defeats the purpose).
12. **No UI in v1.** `.kiln` files are human-readable; a read-only memory browser is P2. No REST API surface required by this project (the tools are the interface). Desktop-side like all Kiln tools (Q8 uniform dispatch); memories ride the project directory's existing git-sync/backup story.
13. **Caps are write discipline**, enforced structurally: 140/2,000 keep memories atomic records (one finding per memory), which is what keeps `overview` honest, tag filters precise, and supersession clean. No ranged reads — full records are always affordable at this cap (Letta's 2,000-char block cap is the precedent).

## Datamodel sketch (authoritative for field names/descriptions)

```python
class Memory(KilnParentedModel):
    """One memory record of the assistant working on this project.
    Stored at assistant_memory/{id}/memory.kiln. Concurrent-append safe
    (file per memory); updates are last-writer-wins."""

    overview: str = Field(
        max_length=140,
        description="One-line summary written so a future reader can decide "
        "whether to fetch the full content. For very short memories this IS "
        "the whole memory (leave content null). No newlines.",
    )
    content: str | None = Field(
        default=None,
        max_length=2000,
        description="The memory body: the finding/fact/decision with its "
        "conditions and evidence level, citing related Kiln records as prose "
        "IDs (e.g. 'run_config 184623901234', 'eval 5678'). Null when the "
        "overview says everything. Record observations with conditions "
        "('batch API 429'd at 50rps on 07-04'), never universal rules.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Snake_case tags for filtering (existing Kiln tag rules). "
        "Free-form; skills define the working vocabulary (e.g. experiment, "
        "dead_end, constraint, api_quirk, session_state; faceted tags like "
        "lever_prompt, verdict_accept, evidence_weak).",
    )
    scope: str = Field(
        description="Opaque scope string, exact-match filterable. Conventions: "
        "'project' for project-wide knowledge (constraints, environment "
        "facts); 'task::<task_id>' for task-scoped work. Not validated "
        "against existing records — a convention, not a reference.",
    )
```

**Validators (all write-time format checks only):** `overview` — strip, non-empty, no newlines, ≤140. `content` — strip, empty→`None`, ≤2,000. `tags` — reuse the existing tag validator. `scope` — strip, non-empty, no newlines, ≤255. Nothing here may fail on load for data that once saved (`loading_from_file` leniency where applicable).

**Registration:** add to `Project.parent_of` with filesystem folder `assistant_memory`; typed accessor per the standard pattern; export from `datamodel/__init__.py`. Purely additive — old clients ignore unknown folders; no migration, no `v` bump.

## Tool API (six tools; the descriptions are part of the deliverable — tool results and descriptions are prompts)

| Tool | Params | Returns / behavior |
|---|---|---|
| `save_memory` | `overview` (req), `scope` (req — explicit on every write; conventions `"project"` / `"task::<id>"` in the description), `content?`, `tags?` | New memory `id` + echo of the record. Description must carry the write discipline: a memory-worthy list (probe results w/ evidence level, rejected approaches + why, API quirks, constraints/preferences, future ideas, session state); "list related memories first — update instead of duplicating"; conditions-not-rules phrasing. |
| `list_memories` | `scope?` (exact match; omit = all), `tags?` (list, AND semantics — memory must have all; use multiple calls for OR), `content_match?` (case-insensitive regex over overview + content), `limit?` (default 50), `offset?` | Per memory: `id`, `overview`, `tags`, `scope`, `content_length` (0 when content is null), `created_at`, `created_by`. Sorted newest-first. **When truncated, the result text says so with tag counts as a nudge**: "62 more — filter by tag: probe(18), api_quirk(9), …". |
| `get_memories` | `ids` (one or many) | Full records. Description: "content_length 0 in listings means the overview is the entire memory — no need to fetch"; "fetch in batches, not all at once". |
| `update_memory` | `id`, any of `overview?`, `content?`, `tags?`, `scope?` | Partial replace of provided fields; open to all callers; last-writer-wins. Description: prefer adding a `stale` tag + a new correction memory over rewriting others' content; rolling session-state memories are the main rewrite case. |
| `delete_memory` | `id` | Hard delete (folder removal). For confirmed junk; prefer `stale` tagging for "wrong but instructive". |
| `memory_summary` | `scope?` (omit = all scopes) | Cheap orientation, no record content — output spec below. Description: "call at session start before targeted lists". Same folder scan as list; trivially cheap. |

Later (deferred): folding `memory_summary` into the assistant's `agent_info` — the *tool* is v1 because Phase 0 (Claude Code) has no `agent_info` surface.

### `memory_summary` output (agreed 2026-07-10)

Unscoped call returns all scopes; scoped call returns just that scope's block (same shape, no wrapper). No caps or truncation.

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

- **Grouping is per scope, always** — flat tag counts would conflate project constraints with task probes, and "which scopes exist, how active" is half the orientation value.
- `count` = memories in the scope. `tags` = filter cardinalities sorted by count desc — each number is exactly what `list_memories(scope=…, tags=[t])` returns; multi-tagged memories mean tag counts sum to more than `count`, intentionally. `untagged` present only when nonzero (invisible to tag filters — the agent should know it exists).
- `newest` = most recent `created_at` in the scope; scopes sorted newest-first (recency = where the action is; doubles as a staleness signal for old task scopes).
- Nothing else: no overviews, no content, no created_by breakdown. Orientation only; the follow-up is a targeted `list_memories`.

## MCP server (experiments repo, Phase 0 consumer)

- **stdio transport, official MCP Python SDK**, wrapping the core logic directly (no `KilnToolInterface` involved). Internal tool: follow experiments-repo conventions; small README with a Claude Code `.mcp.json` example.
- **Launch args:** `--project /path/to/project.kiln` (required — binds the store to that project's `assistant_memory/`). That's the only arg: **no `--default-scope`, no scope defaults** — the MCP client passes `scope` explicitly per the API (guidance supplies conventions), so the MCP surface has nothing the harness surface won't have. `list_memories`/`memory_summary` with `scope` omitted = all scopes.
- **Tool names/params identical to the table above** — the MCP server is a thin adapter, nothing memory-shaped lives in it.
- **Concurrency is a feature, test it:** stdio means one server process per coding-agent session; parallel sessions = concurrent writers from separate processes on the same folder. Include a test: two processes appending + updating concurrently; all appends survive, updates are last-writer-wins, no corruption.

## Phases

> **Update (scosman, 2026-07-13) — REST API pivot.** Phase 2 (the bespoke stdio MCP server) was a mistake and is **superseded by Phase 4**. Agents already reach Kiln's REST API via `kiln_api_mcp` (filtered by the `agent_approvals` `x-agent-policy` annotations), so the correct agent-access surface is REST endpoints tagged `ALLOW_AGENT` — not a bespoke server. This **reverses decision 12** ("no REST surface"). Phase 1 (core) is unchanged and underpins all surfaces.

1. **kiln `libs/core`:** `Memory` datamodel + registration + validators; core memory API (save/list/get/update/delete over a store binding; tag/scope/regex filtering; newest-first sort; truncation summary with tag counts); unit tests including the multi-process concurrency test.
2. **~~experiments repo: stdio MCP server~~ (SUPERSEDED by Phase 4):** built then abandoned; tool description texts are retained (reused as OpenAPI endpoint descriptions in Phase 4).
3. **(cuttable) kiln harness integration:** `KilnToolInterface` adapter bound to the current run's project (scope stays an explicit tool param — no injection); registry wiring; `ALLOW_AGENT` policies on all six. Phase 0 does not depend on this phase. *(Post-pivot: possibly redundant — the harness can reach the Phase-4 REST API via the built-in `CALL_KILN_API` tool. Keep-or-cut is a reviewer decision.)*
4. **kiln `libs/server`: memory REST API (the agent-access surface).** `libs/server/kiln_server/memory_api.py` — six endpoints under `/api/projects/{project_id}/memories` wrapping the core `MemoryStore`, one per tool, each tagged `ALLOW_AGENT` (incl. PATCH/DELETE, overriding the `agent_approvals` verb-defaults per decision 11). Registered in `server.py`; agent-policy annotation JSONs + web OpenAPI client regenerated for CI. Becomes agent-accessible for free via `kiln_api_mcp`. Detailed plan: `phase_plans/phase_4.md`.

## Deferred, with triggers

| Item | Trigger to build |
|---|---|
| `properties: dict` + property filters in list | Phase-0 usage shows faceted tags failing (needed comparisons like "spend > $5", "n ≥ 20") |
| Substring/semantic search beyond regex | regex + tags insufficient at real memory counts |
| Consolidation/dreaming | v2 background job (industry-unanimous: never on the write path) |
| Structured typed refs (shared with Part 1 `evidence_refs`) | a qualified-ID scheme earns its keep |
| `memory_summary` folded into assistant `agent_info` | the assistant harness integration matures (the tool itself is v1) |
| `session_id` field | parallel-session attribution need + a reliable cross-surface session identity |
| User-task memory binding + run-config tool exposure (`ToolId`) | the named follow-on of decision 10 — also the "add a memory tool" optimization lever from O3 planning (a real memory tool, first-party, for customers' runtime agents) |
| Read-only memory browser UI | P2 |
| Bare-directory (non-project) store mode | a consumer without a Kiln project |
| New scope conventions (`task_run::…`) | consumers appear; zero datamodel change |
| Import of Phase-0 file memories | never — out of scope; skills cut over, files retire |

## Prior art (why these exact shapes)

| System | Lesson taken |
|---|---|
| Anthropic memory tool | list-then-read with no search works at frontier scale; listings carry read-cost signals (our `content_length`); protocol = check memory first / record progress / assume interruption |
| mem0 | API naming (`save/list/get/update/delete` family); **walked back** LLM merge-on-write → we stay append-biased, no write-time merging; their `metadata` dict = our deferred `properties` |
| Letta | 2,000-char record cap as structural write discipline; rolling-summary block = our `session_state` update case |
| Windsurf | tags + write-discipline in tool descriptions ("check for existing related memory; update instead of duplicating") |
| doobidoo MCP / reference MCP server | tags + time as retrieval axes; substring over flat files is viable; single-JSONL corrupts under parallel writers → file-per-memory |
| ChatGPT bio | inject-everything dies at scale → summary-first listing, no auto-injection |
| ARA (arXiv 2604.24658) | dead ends as first-class records; epistemic provenance tags (→ `human_stated`/`agent_inferred`/`evidence_*` tag layer); preserved failure records can *over-constrain* → conditions-not-rules phrasing in every description |

## Out of scope

- The skills/conventions themselves (tag vocabulary, protocols) — O3 repo work, planned in [memory_spec_updates.md](../../../planning/memory_spec_updates.md).
- UI beyond nothing (browser is P2); REST CRUD endpoints.
- Vector stores, embeddings, semantic search, consolidation.
- The user-task binding build (design-constraint only, per decision 10).
- `agent_info` integration of `memory_summary` (the `memory_summary` tool itself IS in scope).
- Any modification to artifact provenance (Part 1) — the two systems meet only via prose ID references.

## Kickoff logistics (confirmed, scosman 2026-07-10)

1. Experiments repo: **`kiln-ai/experiments`**; pin kiln core by git rev of the kiln feature branch during development.
2. **One coding task across both repos** — two PRs, kiln first.
