---
status: complete
---

# Implementation Plan: Agent Memory (project: agent_memory)

Each phase is independently testable. Run `uv run ./checks.sh --agent-mode` in the kiln repo before each kiln PR.

**Update (scosman, 2026-07-13) — the REST API pivot.** Phase 2 (the bespoke stdio MCP server in the experiments repo) was a mistake and is **superseded by Phase 4**. Kiln already exposes its REST API to agents via `kiln_api_mcp` (filtered by the `agent_approvals` `x-agent-policy` annotations), so the correct agent-access surface is normal REST endpoints tagged `ALLOW_AGENT` — not a bespoke server. This reverses decision 12 ("no REST surface"): a REST surface is now the primary agent path. Phase 1 (core) is unchanged and underpins everything.

## Phases

- [x] **Phase 1: kiln `libs/core` — datamodel + core memory API** *(repo: `Kiln-AI/kiln`)*
  - `Memory(KilnParentedModel)` in `datamodel/memory.py`: `overview`/`content`/`tags`/`scope` + write-time-only, load-safe validators (architecture §2).
  - Register under `Project.parent_of` via `ParentOfRelationship(model=Memory, filesystem_name="assistant_memory")`; typed `memories()` accessor; export from `datamodel/__init__.py`.
  - `MemoryStore` + result/summary Pydantic types + errors in `memory/memory_store.py`: `save` / `list` (+ truncation counts) / `get` / `update` (partial replace, `_UNSET` sentinel) / `delete` / `summary`; tag/scope/regex filtering; newest-first stable sort.
  - Tests: `datamodel/test_memory.py`, `memory/test_memory_store.py`, and the **multi-process** `memory/test_memory_store_concurrency.py`; extend the project test file with the `memories` accessor/registration.
  - → **kiln PR (first)**.

- [~] **Phase 2 (SUPERSEDED by Phase 4): experiments repo — stdio MCP server** *(repo: `kiln-ai/experiments`)*
  - Built and pushed (branch `claude/agent-memory-mcp`, `memory_mcp/`), but **abandoned**: the right agent-access surface is REST + `ALLOW_AGENT` consumed by the existing `kiln_api_mcp`, not a bespoke server. No experiments PR was opened; delete/close the branch.
  - Retained value: the six tool description texts (reused as OpenAPI endpoint descriptions in Phase 4).

- [x] **Phase 3 (cuttable): kiln harness integration** *(repo: `Kiln-AI/kiln`)*
  - `KilnToolInterface` adapters (`tools/memory_tools.py`) wrapping `MemoryStore` bound to the current run's project (`scope` stays an explicit param — no injection).
  - Tool-id scheme `kiln_tool::memory::<op>` (`tool_id.py`) + `tool_registry.py` wiring resolving via `task.parent_project()`.
  - **Agent policy resolved as a non-issue:** there is no per-tool approval layer in core (the REST `ALLOW_AGENT` doesn't apply — decision 12, no REST surface). A tool listed in a run config's `tools_config.tools` is simply agent-callable, so all six are agent-available with no approval gate by construction (decision 11).
  - The six tool description texts are authored here and are ready for Phase 2 (the experiments MCP server) to reuse.
  - Tests: `tools/test_memory_tools.py` (definitions, round-trip, error mapping, registry resolution).
  - Independent of Phase 0; ships without affecting the MCP server.
  - *Possibly redundant post-pivot: the harness can reach the Phase-4 REST API via the built-in `CALL_KILN_API` tool. Kept for now (typed first-party tools); keep-or-cut is a reviewer decision.*

- [ ] **Phase 4: kiln `libs/server` — memory REST API (the agent-access surface)** *(repo: `Kiln-AI/kiln`)*
  - `libs/server/kiln_server/memory_api.py`: six endpoints under `/api/projects/{project_id}/memories` wrapping the core `MemoryStore`, one per tool (POST save / GET list / GET summary / GET by_ids / PATCH update / DELETE), modeled on `feedback_api.py`.
  - All six tagged `openapi_extra=ALLOW_AGENT` — **including PATCH and DELETE**, a deliberate override of the `agent_approvals` verb-defaults (decision 11: the assistant's own memory, no approval gate).
  - Register `connect_memory_api(app)` in `server.py::make_app()`; regenerate the agent-policy annotation JSONs (`utils/agent_checks/annotations/`) and the web OpenAPI client (`generate_schema.sh`) so CI (`check_api_bindings`, `check_schema`) passes.
  - Tests: `libs/server/kiln_server/test_memory_api.py` (all six + policy-annotation assertion). Run `uv run ./checks.sh --agent-mode`.
  - Detailed plan: `phase_plans/phase_4.md`. Becomes the agent-access path (via `kiln_api_mcp`); no bespoke server.
