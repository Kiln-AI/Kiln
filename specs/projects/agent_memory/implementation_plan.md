---
status: complete
---

# Implementation Plan: Agent Memory (project: agent_memory)

Cross-repo project, three phases. **One coding task, two PRs, kiln first** (the experiments MCP server pins kiln core by git rev). Phase 3 is cuttable and Phase 0 (the MCP server) does not depend on it.

Each phase is independently testable. Run `uv run ./checks.sh --agent-mode` in the kiln repo before each kiln PR.

## Phases

- [ ] **Phase 1: kiln `libs/core` — datamodel + core memory API** *(repo: `Kiln-AI/kiln`)*
  - `Memory(KilnParentedModel)` in `datamodel/memory.py`: `overview`/`content`/`tags`/`scope` + write-time-only, load-safe validators (architecture §2).
  - Register under `Project.parent_of` via `ParentOfRelationship(model=Memory, filesystem_name="assistant_memory")`; typed `memories()` accessor; export from `datamodel/__init__.py`.
  - `MemoryStore` + result/summary Pydantic types + errors in `memory/memory_store.py`: `save` / `list` (+ truncation counts) / `get` / `update` (partial replace, `_UNSET` sentinel) / `delete` / `summary`; tag/scope/regex filtering; newest-first stable sort.
  - Tests: `datamodel/test_memory.py`, `memory/test_memory_store.py`, and the **multi-process** `memory/test_memory_store_concurrency.py`; extend the project test file with the `memories` accessor/registration.
  - → **kiln PR (first)**.

- [ ] **Phase 2: experiments repo — stdio MCP server** *(repo: `kiln-ai/experiments`)*
  - stdio MCP server (official MCP Python SDK) wrapping `MemoryStore`; `--project` launch arg (required); no scope defaults.
  - Six tools with names/params identical to functional_spec §6; render the `list_memories` truncation nudge; convert store errors to tool errors.
  - The six **tool description texts** (spec'd deliverables, functional_spec §6 / architecture §5.2).
  - README with a Claude Code `.mcp.json` example; two-server-process concurrency test; manual smoke test against a scratch Kiln project.
  - Pin kiln core by git rev of the Phase-1 branch.
  - → **experiments PR (second)**.

- [ ] **Phase 3 (cuttable): kiln harness integration** *(repo: `Kiln-AI/kiln`)*
  - `KilnToolInterface` adapters wrapping `MemoryStore` bound to the current run's project (`scope` stays an explicit param — no injection).
  - Tool-id scheme + `tool_registry` wiring; all six agent-allowed with no approval gate (decision 11; reconcile with the harness approval mechanism — this project has no REST surface).
  - Tests alongside the adapter.
  - Independent of Phase 0; ship or cut without affecting the MCP server.
