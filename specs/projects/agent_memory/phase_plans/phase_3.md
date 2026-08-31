---
status: complete
---

# Phase 3 (cuttable): kiln harness integration

**Repo:** `Kiln-AI/kiln`. **Cuttable** — Phase 0 (the MCP server) does not depend on this. Build it only if/when the Kiln agent harness should have the memory tools first-party. Ship or cut without touching Phases 1–2.

## Overview

Expose the same six memory operations to the Kiln agent harness through `KilnToolInterface`, bound to the current run's project. The adapter is mechanical — it wraps the Phase-1 `MemoryStore`. `scope` stays an explicit tool param (no injection): the harness surface behaves identically to the MCP surface (decision 9).

## Steps

1. **`KilnToolInterface` adapters** (base_tool.py:46) — the six tools, each constructed with a `MemoryStore` bound to the current run's project. Implement `run(**kwargs) -> ToolCallResult`, `toolcall_definition()`, `id()`, `name()`, `description()`. Reuse the Phase-2 tool description texts. Convert store errors to `ToolCallResult(is_error=True, ...)`.
2. **Tool IDs + registry wiring**: add a memory tool-id scheme in the `kiln_tool::…` family (e.g. `kiln_tool::memory::save`) in `datamodel/tool_id.py`, and resolve them in `tools/tool_registry.py::tool_from_id` (which already has the project in hand via `task.parent_project()`). Exact id scheme is discretionary.
3. **Agent policy** (decision 11): all six agent-allowed, **no approval gate** — including `delete` (an agent that can't prune its own landfill defeats the purpose). **Resolved during implementation:** core has no per-tool approval layer (the codebase `ALLOW_AGENT` is a REST/openapi_extra annotation and this project has no REST surface — decision 12). A tool listed in a run config's `tools_config.tools` is simply callable by the agent, so "agent-allowed, no approval" holds by construction — no extra wiring needed.
4. **Tests** alongside the adapter.

## Tests

- Each of the six tools exposes the correct `toolcall_definition()` (name + params matching functional_spec §6) and, on `run(...)`, calls the bound `MemoryStore` and returns a `ToolCallResult` with the serialized result.
- `scope` is an explicit param on every write tool (no default injected by the adapter).
- The adapter binds to the current run's project (isolation: a tool bound to project A cannot read project B).
- Store errors (unknown id, invalid regex, over-length field) surface as `ToolCallResult(is_error=True)`, not exceptions.
- Registry: the memory tool ids resolve via `tool_from_id`; all six are agent-allowed with no approval gate.
