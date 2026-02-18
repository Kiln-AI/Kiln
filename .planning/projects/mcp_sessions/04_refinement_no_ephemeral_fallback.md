# Refinement: Remove Ephemeral Fallback from Tool Calls

## Decision

Remove the silent ephemeral fallback from `MCPServerTool._call_tool()`. A missing session ID during a tool call is always a bug — fail loudly instead of silently degrading to broken stateful behavior.

## Problem with the Current Implementation

`_call_tool()` has an if/else branch:

```python
session_id = get_mcp_session_id()
if session_id:
    session = await manager.get_or_create_session(...)
else:
    async with manager.mcp_client(...) as session:  # ephemeral fallback
        ...
```

The ephemeral fallback silently creates a one-off session. This masks exactly the class of bug the entire session feature exists to fix. If someone adds a new code path that calls tools without setting up session context, it would "work" but with broken statefulness — the hardest kind of bug to catch.

## Consumer Analysis

| Consumer | Called during agent run? | Session ID available? | Needs persistence? |
|----------|------------------------|----------------------|-------------------|
| `_call_tool()` | Always | Always (set by BaseAdapter) | Yes |
| `_get_tool()` from agent run | Yes | Yes | Nice to have |
| `_get_tool()` from UI listing | No | No | No (stateless) |

## Changes

### `MCPServerTool._call_tool()` — Remove fallback, require session

```python
async def _call_tool(self, **kwargs) -> CallToolResult:
    session_id = get_mcp_session_id()
    if not session_id:
        raise RuntimeError(
            "MCP tool call attempted without an agent run context. "
            "This is a bug — tool calls should only happen during an agent run."
        )
    session = await MCPSessionManager.shared().get_or_create_session(
        self._tool_server_model, session_id
    )
    return await session.call_tool(name=await self.name(), arguments=kwargs)
```

No branching. Missing context is a loud error.

### `MCPServerTool._get_tool()` — Keep fallback (legitimate use case)

```python
async def _get_tool(self, tool_name: str) -> MCPTool:
    session_id = get_mcp_session_id()
    if session_id:
        session = await MCPSessionManager.shared().get_or_create_session(
            self._tool_server_model, session_id
        )
        tools = await session.list_tools()
    else:
        async with MCPSessionManager.shared().mcp_client(
            self._tool_server_model
        ) as session:
            tools = await session.list_tools()
    ...
```

The fallback here is legitimate: the UI calls `_get_tool()` to list tools during configuration, outside any agent run. This is a stateless operation where ephemeral is correct behavior.

### `mcp_client()` — Unchanged

The existing context manager remains the ephemeral API for code that genuinely operates outside agent runs (UI tool listing, health checks, etc.). No wrapper needed.

### `get_or_create_session()` — Unchanged

Already requires `session_id` as a mandatory parameter. No changes needed.

## Rationale

- **Fail-fast over fail-silent:** A missing session ID during a tool call is always a bug. Making it an error ensures it's caught immediately during development, not discovered as subtle state loss in production.
- **Simpler hot path:** `_call_tool()` has no branching — just read the ID and use it.
- **Ephemeral stays where it belongs:** `mcp_client()` context manager is the right API for genuinely ephemeral use. It doesn't pretend to be something it's not.
