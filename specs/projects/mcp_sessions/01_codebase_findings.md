# Codebase Research Findings

## 1. Current MCP Session Lifecycle

**Confirmed: Each tool call creates a brand new MCP session.** There is zero session reuse.

The flow is:

```
MCPServerTool._call_tool()
  └─> MCPSessionManager.mcp_client(tool_server)  [async context manager]
       ├─> remote: streamablehttp_client() → ClientSession() → session.initialize()
       └─> local:  stdio_client() → ClientSession() → session.initialize()

  On context manager exit: transport closes, session dies, subprocess killed (local)
```

Key code in `mcp_server_tool.py`:

```python
async def _call_tool(self, **kwargs) -> CallToolResult:
    async with MCPSessionManager.shared().mcp_client(
        self._tool_server_model
    ) as session:
        result = await session.call_tool(name=..., arguments=kwargs)
        return result
```

This means:

- **Remote MCP:** New HTTP connection per tool call
- **Local MCP:** New subprocess spawned per tool call, killed after
- **Stateful servers broken:** Memory set → process killed → memory get → empty

## 2. Agent & Sub-Agent Architecture

### Adapter Lifecycle

- Adapters are **created per request** via `adapter_for_task()`
- Short-lived: created, `invoke()` called once, discarded
- Entry point: `BaseAdapter.invoke()` → `invoke_returning_run_output()` → `_run()`

### Sub-Agent Chain

```
Root Agent (LiteLlmAdapter)
  invoke() → _run() → _run_model_turn()
    └─> process_tool_calls()
         ├─> MCPServerTool.run()       ← MCP tool call
         ├─> KilnTaskTool.run()        ← Sub-agent!
         │    └─> adapter_for_task()   ← Creates NEW adapter
         │         └─> adapter.invoke() ← Recursive!
         │              └─> _run() → _run_model_turn()
         │                   └─> process_tool_calls()
         │                        └─> MCPServerTool.run()  ← MCP from sub-agent
         └─> MCPServerTool.run()       ← Another MCP call
```

### Parallel Tool Execution

Tools within a single turn are run **concurrently** via `asyncio.gather`:

```python
tool_run_coroutines.append(run_tool_and_format())
# ...
tool_call_response_messages = await asyncio.gather(*tool_run_coroutines)
```

This means multiple MCP tool calls can happen simultaneously within a turn.

## 3. Async Patterns

- **Pure async in adapter path:** No threads, no `run_in_executor`, no `ThreadPoolExecutor`
- **Threading exists but only for:** Config lock, desktop server startup, remote config background fetch, PDF conversion
- **`contextvars` compatibility:** `asyncio.gather` copies the parent context to each child coroutine. Reads work. Child writes don't affect parent or siblings. This is exactly what we need.

## 4. Transport Lifecycle (Critical Finding)

The MCP library uses **nested context managers** for connection lifecycle:

### Remote (streamable HTTP):

```python
async with streamablehttp_client(url, headers=headers) as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()
        yield session
# ← Exiting kills HTTP connection
```

### Local (stdio subprocess):

```python
with tempfile.TemporaryFile(...) as err_log:
    async with stdio_client(server_params, errlog=err_log) as (read, write):
        async with ClientSession(read, write, ...) as session:
            await session.initialize()
            yield session
# ← Exiting kills subprocess AND closes temp file
```

**Critical implication:** You cannot simply cache a `ClientSession` object. The transport underneath it is managed by the outer context manager. When that context manager exits, the transport closes and the cached session becomes a dead object.

**This means the prior design proposals that cache `ClientSession` alone are broken.** We need to keep the entire context manager stack alive.

## 5. Existing Context Patterns

- `ToolCallContext` dataclass is passed explicitly to `tool.run()` — contains `allow_saving`
- No `contextvars` usage in production code
- `MCPSessionManager` is a singleton (`_shared_instance`)
- No session/connection pooling anywhere

## 6. Server Configuration

`ExternalToolServer` has:

- `id` field (from `KilnParentedModel`)
- `type`: `remote_mcp`, `local_mcp`, `kiln_task`
- `properties`: connection details (url/headers or command/args/env_vars)
- Secret management for headers/env vars

Tools are resolved by ID in `tool_registry.py` — constructed on demand from `ExternalToolServer` data models.
