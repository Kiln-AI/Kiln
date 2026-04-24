# Refinement: General-Purpose Agent Run ID

## Decision

Replace the MCP-specific `mcp_session_id` contextvar with a general-purpose `agent_run_id`. The adapter layer defines a run-scoping ID with no knowledge of MCP. The MCP session manager consumes that ID as a cache key.

## Rationale

The contextvar is set in `BaseAdapter.invoke_returning_run_output()` — the universal entry point for all agent work. Naming it `mcp_session_id` couples a generic orchestration concept to a single consumer. The "scope of an agent run, including sub-agents" is inherently general and useful beyond MCP.

### Future uses for a general agent run ID

- Log/trace correlation across an agent invocation tree
- Rate limiting scoped to a single user-initiated run
- Caching or deduplication within a run
- Metrics (latency, token usage) grouped by run

None of these require MCP awareness. All of them benefit from a shared run-scoping ID.

### No cost to generality

The MCP session manager uses the ID as a cache key. It doesn't care what the ID is called — only that the same ID appears across tool calls within the same run. The coupling is one-directional: MCP reads the ID; the ID doesn't know about MCP.

## Changes from Original Plan

| Original                            | Refined                                                          |
| ----------------------------------- | ---------------------------------------------------------------- |
| New file: `mcp_session_context.py`  | New file: `adapter_run_context.py` (in `adapters/` not `tools/`) |
| `ContextVar` name: `mcp_session_id` | `agent_run_id`                                                   |
| `get_mcp_session_id()`              | `get_agent_run_id()`                                             |
| `set_mcp_session_id(id)`            | `set_agent_run_id(id)`                                           |
| `clear_mcp_session_id()`            | `clear_agent_run_id()`                                           |
| `generate_session_id()`             | `generate_agent_run_id()`                                        |
| ID format: `mcp_abc123...`          | `run_abc123...`                                                  |

Everything else in the original plan stays the same. `MCPSessionManager` still caches sessions keyed by `f"{server_id}:{agent_run_id}"`. `MCPServerTool` still reads the contextvar and passes the ID to the session manager.

## File Placement

The context module moves from `tools/` to `adapters/` since it's an adapter-level concept:

```
libs/core/kiln_ai/adapters/adapter_run_context.py   ← NEW (was tools/mcp_session_context.py)
libs/core/kiln_ai/adapters/model_adapters/base_adapter.py  ← sets/clears the ID
libs/core/kiln_ai/tools/mcp_session_manager.py              ← reads the ID (via import)
libs/core/kiln_ai/tools/mcp_server_tool.py                  ← reads the ID (via import)
```

The dependency direction is correct: `tools/` imports from `adapters/` to read the run ID. `adapters/` has no knowledge of MCP session caching.
