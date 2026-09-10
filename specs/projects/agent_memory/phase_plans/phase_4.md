---
status: complete
---

# Phase 4: memory REST API (the agent-access surface)

**Repo:** `Kiln-AI/kiln`, `libs/server`. **This supersedes Phase 2** (the bespoke stdio MCP server in the experiments repo — see "Why this replaces Phase 2" below).

## Why (the pivot)

The experiments MCP server (Phase 2) was the wrong shape. Kiln already ships `kiln_api_mcp` (in the experiments repo), which exposes Kiln's REST API to any agent, filtered by the per-endpoint **agent-policy annotations** built in the `agent_approvals` project (`x-agent-policy`, `ALLOW_AGENT`/`DENY_AGENT`/approval). So the right way to give our agent memory access over MCP is **not** a bespoke server — it's to add normal REST endpoints and tag them `ALLOW_AGENT`. They then become available to the compile agent through the existing `kiln_api_mcp`, for free, with no new server to build, pin, or maintain.

This also reverses **decision 12** ("No REST API surface required"): a REST surface is now the *primary* agent-access path. The tool *semantics* (the six operations, `scope` explicit, list-then-read, truncation nudge) are unchanged — only the transport changes from a custom MCP server to annotated REST + the shared api MCP.

## Endpoints (one per tool, project-scoped, wrapping the core `MemoryStore`)

All under `/api/projects/{project_id}/memories`. Each wraps `MemoryStore(project_from_id(project_id))` and calls the matching core method (Phase 1). Modeled on `libs/server/kiln_server/feedback_api.py`.

| Tool | Method + path | Params | Returns |
|---|---|---|---|
| `save_memory` | **POST** `/memories` | body: `overview`, `scope` (req), `content?`, `tags?` | the created `Memory` |
| `list_memories` | **GET** `/memories` | query: `scope?`, `tags?` (repeatable → AND), `content_match?`, `limit?`, `offset?` | `MemoryListResult` (listings + `matched`/`remaining`/`remaining_tag_counts`) |
| `memory_summary` | **GET** `/memories/summary` | query: `scope?` | `MemorySummary` |
| `get_memories` | **GET** `/memories/by_ids` | query: `ids` (repeatable) | `list[Memory]` (unknown ids omitted) |
| `update_memory` | **PATCH** `/memories/{memory_id}` | body: `overview?`, `content?`, `tags?`, `scope?` (partial replace) | the updated `Memory` |
| `delete_memory` | **DELETE** `/memories/{memory_id}` | — | 204 / `None` |

- **Route ordering:** declare the static sub-paths (`/memories/summary`, `/memories/by_ids`) before any `/memories/{memory_id}` route so `summary`/`by_ids` aren't captured as a `memory_id`. (In this design the `{memory_id}` routes are PATCH/DELETE only, so there's no GET collision, but keep the ordering rule.)
- **Response models are the core Pydantic types** returned as-is: `Memory`, `MemoryListResult`, `MemorySummary`. `content_length` (0 for null content) is already on `MemoryListing`. The structured `remaining` / `remaining_tag_counts` are returned directly; a rendered "N more — filter by tag…" string can be added as an optional field if a consumer wants it, but the structured counts are the source of truth.
- **`get_memories` is a batch GET** (`?ids=a&ids=b`) to map 1:1 to the tool. A single-record `GET /memories/{memory_id}` can be added later if useful; not required.

## Agent policy (decision 11 — note the deliberate override)

All six endpoints are tagged **`openapi_extra=ALLOW_AGENT`** — including PATCH and DELETE. This **overrides the `agent_approvals` verb-defaults** (which default DELETE → deny and PATCH → approve-with-message). The override is justified and intentional: this is the assistant's *own* memory, and per decision 11 all six tools are agent-allowed with no approval gate (delete included — an agent that can't prune its own landfill defeats the purpose). Call this out in the PR so the deviation from the backfill defaults is a conscious choice, not an oversight.

## Files

| Path | Change |
|---|---|
| `libs/server/kiln_server/memory_api.py` | new — `connect_memory_api(app)` with the six routes; request body models (`SaveMemoryRequest`, `UpdateMemoryRequest`); wraps `MemoryStore`. |
| `libs/server/kiln_server/server.py` | edit — `from .memory_api import connect_memory_api` + `connect_memory_api(app)` in `make_app()`. |
| `libs/server/kiln_server/test_memory_api.py` | new — endpoint tests (below). |
| `libs/server/kiln_server/utils/agent_checks/annotations/*.json` | regenerate — run the annotation-dump CLI so the six new endpoints get their policy JSONs (CI `check_api_bindings.yml` fails otherwise). |
| `app/web_ui/src/lib/api_schema.d.ts` | regenerate — `app/web_ui/src/lib/generate_schema.sh` (CI `check_schema.sh` enforces the OpenAPI client is current). No UI is built (decision 12), but the generated client must stay in sync. |

## Error mapping

Keep the `Memory` validators as the single source of truth; catch core errors and map:

- `MemoryNotFoundError` → **404**.
- `InvalidContentMatchError` → **422** (bad `content_match` regex).
- pydantic `ValidationError` from constructing/updating a `Memory` (over-length, newline, empty, bad tag) → **422** with the field message.

Mirror `feedback_api.py`'s `HTTPException(404, …)` style.

## Tests (`test_memory_api.py`)

Use the FastAPI `TestClient` + a tmp project, mirroring `test_feedback_api.py`:

- POST creates a memory; response echoes it; it's on disk under `assistant_memory/{id}/`.
- GET list: newest-first; `scope` exact filter; `tags` AND (repeatable query); `content_match` regex; `limit`/`offset`; `content_length` 0 for null content; truncation fields when truncated.
- GET `/summary`: per-scope shape; `untagged` only when nonzero.
- GET `/by_ids`: batch; unknown ids omitted.
- PATCH: partial replace (untouched fields preserved); `content=""` clears; unknown id → 404; over-length field → 422.
- DELETE: removes the record; unknown id → 404.
- **Agent-policy annotations present**: assert each of the six routes carries `x-agent-policy = allow` in `app.openapi()` (guards the decision-11 override and satisfies the binding check).
- Invalid `content_match` regex → 422.

Run `uv run ./checks.sh --agent-mode` (covers ruff/ty/pytest, the api-binding check, and the schema check).

## Why this replaces Phase 2

- Phase 2 (bespoke stdio MCP server, experiments repo) is **abandoned**. Its work — server + tool descriptions + concurrency test — is not needed once memory is REST + `ALLOW_AGENT`, because `kiln_api_mcp` already provides the MCP transport for every annotated endpoint. Delete/close the experiments branch (`claude/agent-memory-mcp`); no experiments PR was opened.
- The six tool *description* texts authored for Phase 2/3 are still useful: they become the endpoints' `summary`/`description` and the request-field descriptions (OpenAPI descriptions are what the api MCP surfaces to the agent — same "descriptions are prompts" principle).

## Note on Phase 3 (harness `KilnToolInterface` tools)

Phase 3 may now be partly redundant: the Kiln agent harness can reach the memory REST API through the built-in `CALL_KILN_API` tool, the same way it reaches other Kiln APIs. Phase 3's typed first-party tools are still a nicer surface than raw API calls, so this phase does **not** remove them — but flag for the reviewer whether Phase 3 should be kept, or dropped in favor of API access only. (Phase 3 is already in PR #1572/#1573; cutting it is a separate decision.)
