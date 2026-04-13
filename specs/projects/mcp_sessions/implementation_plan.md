# Implementation Plan: MCP Session Reuse via ContextVars

## Overview

Implement session reuse for MCP servers across tool calls within an agent run (and its sub-agent calls). Uses `contextvars` for implicit session ID propagation and `AsyncExitStack` for transport lifecycle management.

**Files changed:** 4 (1 new, 3 modified)  
**Test files changed:** 3-4 (new tests + updates to existing)  
**Estimated total lines:** ~370 new/modified (including tests)

**Important** see refinement plans in this folder for full design. This doc does not represent final state. Apply those to this doc.

---

## Step 1: Create `mcp_session_context.py`

**File:** `libs/core/kiln_ai/tools/mcp_session_context.py` (NEW)

**Purpose:** Define the `ContextVar` and helper functions for MCP session ID propagation.

```python
"""MCP session context management using contextvars.

The session ID propagates automatically through async call chains,
including asyncio.gather and sub-agent calls via KilnTaskTool.
"""

import uuid
from contextvars import ContextVar

_mcp_session_id: ContextVar[str | None] = ContextVar(
    "mcp_session_id", default=None
)


def get_mcp_session_id() -> str | None:
    return _mcp_session_id.get()


def set_mcp_session_id(session_id: str) -> None:
    _mcp_session_id.set(session_id)


def clear_mcp_session_id() -> None:
    _mcp_session_id.set(None)


def generate_session_id() -> str:
    return f"mcp_{uuid.uuid4().hex[:16]}"
```

**Why first:** No dependencies on other changes. All subsequent steps import from here.

**Tests:** Simple unit tests verifying get/set/clear/generate behavior, and that `asyncio.gather` propagates the value.

---

## Step 2: Add session caching to `MCPSessionManager`

**File:** `libs/core/kiln_ai/tools/mcp_session_manager.py` (MODIFIED)

**Changes:**

### 2a. Add instance state for caching

```python
import asyncio
from contextlib import AsyncExitStack

class MCPSessionManager:
    def __init__(self):
        self._shell_path = None
        # Session cache: key = "{server_id}:{session_id}" → (ClientSession, AsyncExitStack)
        self._session_cache: dict[str, tuple[ClientSession, AsyncExitStack]] = {}
        self._cache_lock = asyncio.Lock()
```

### 2b. Add `get_or_create_session()` method

This is the core new method. It:

1. Checks if a cached session exists for this (server, session_id) combination
2. If yes, returns it
3. If no, creates a new session using `AsyncExitStack` to keep the transport alive
4. Caches it and returns it

```python
async def get_or_create_session(
    self,
    tool_server: ExternalToolServer,
    session_id: str,
) -> ClientSession:
    cache_key = f"{tool_server.id}:{session_id}"

    async with self._cache_lock:
        if cache_key in self._session_cache:
            return self._session_cache[cache_key][0]

    # Create outside the lock to avoid holding it during slow I/O.
    # Race: two coroutines may both reach here for the same key.
    # The lock below ensures only one wins; the loser closes its stack.
    session, stack = await self._create_cached_session(tool_server)

    async with self._cache_lock:
        if cache_key in self._session_cache:
            # Another coroutine created it first — close ours and return theirs
            await stack.aclose()
            return self._session_cache[cache_key][0]
        self._session_cache[cache_key] = (session, stack)
        return session
```

### 2c. Add `_create_cached_session()` helper

Creates a session with `AsyncExitStack` to manage the transport lifecycle. Preserves the existing error handling.

```python
async def _create_cached_session(
    self,
    tool_server: ExternalToolServer,
) -> tuple[ClientSession, AsyncExitStack]:
    stack = AsyncExitStack()
    await stack.__aenter__()

    try:
        match tool_server.type:
            case ToolServerType.remote_mcp:
                return await self._create_cached_remote_session(tool_server, stack), stack
            case ToolServerType.local_mcp:
                return await self._create_cached_local_session(tool_server, stack), stack
            case ToolServerType.kiln_task:
                raise ValueError("Kiln task tools are not MCP servers")
            case _:
                raise_exhaustive_enum_error(tool_server.type)
    except Exception:
        await stack.aclose()
        raise
```

For remote:

```python
async def _create_cached_remote_session(
    self,
    tool_server: ExternalToolServer,
    stack: AsyncExitStack,
) -> ClientSession:
    server_url = tool_server.properties.get("server_url")
    if not server_url:
        raise ValueError("server_url is required")

    headers = tool_server.properties.get("headers", {}).copy()
    secret_headers, _ = tool_server.retrieve_secrets()
    headers.update(secret_headers)

    try:
        read_stream, write_stream, _ = await stack.enter_async_context(
            streamablehttp_client(server_url, headers=headers)
        )
        session = await stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()
        return session
    except Exception as e:
        # Reuse existing error handling from _create_remote_mcp_session
        # (HTTP status errors, connection errors, etc.)
        http_error = self._extract_first_exception(e, httpx.HTTPStatusError)
        if http_error and isinstance(http_error, httpx.HTTPStatusError):
            raise ValueError(
                f"The MCP server rejected the request. "
                f"Status {http_error.response.status_code}. "
                f"Response from server:\n{http_error.response.reason_phrase}"
            )
        # ... same error handling as existing _create_remote_mcp_session ...
        raise
```

For local:

```python
async def _create_cached_local_session(
    self,
    tool_server: ExternalToolServer,
    stack: AsyncExitStack,
) -> ClientSession:
    # Same parameter extraction as existing _create_local_mcp_session
    command = tool_server.properties.get("command")
    if not command:
        raise ValueError("...")
    # ... args, env_vars setup ...

    server_params = StdioServerParameters(command=command, args=args, env=env_vars, cwd=cwd)

    err_log = stack.enter_context(
        tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace")
    )

    try:
        read, write = await stack.enter_async_context(
            stdio_client(server_params, errlog=err_log)
        )
        session = await stack.enter_async_context(
            ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30))
        )
        await session.initialize()
        return session
    except Exception as e:
        err_log.seek(0)
        stderr_content = err_log.read()
        if stderr_content:
            logger.error(f"MCP server '{tool_server.name}' stderr: {stderr_content}")
        # ... same error handling as existing _create_local_mcp_session ...
        raise
```

### 2d. Add `cleanup_session()` method

```python
async def cleanup_session(self, session_id: str) -> None:
    """Close all MCP sessions associated with a session ID.

    Called by the root agent's finally block when the agent run completes.
    """
    to_cleanup: list[tuple[str, AsyncExitStack]] = []

    async with self._cache_lock:
        keys_to_remove = [
            key for key in self._session_cache
            if key.endswith(f":{session_id}")
        ]
        for key in keys_to_remove:
            _, exit_stack = self._session_cache.pop(key)
            to_cleanup.append((key, exit_stack))

    # Close outside the lock to avoid holding it during I/O
    for key, exit_stack in to_cleanup:
        try:
            await exit_stack.aclose()
        except Exception:
            logger.warning(f"Error closing MCP session {key}", exc_info=True)
```

### 2e. Keep existing `mcp_client()` working

The existing `mcp_client()` context manager continues to work for ephemeral sessions (no session_id). No changes needed to its implementation — it remains the fallback for code that doesn't have a session context.

**DRY consideration:** The error handling logic in the existing `_create_remote_mcp_session` / `_create_local_mcp_session` should be extracted into shared helper methods so the new cached versions don't duplicate it. For example:

```python
def _handle_remote_mcp_error(self, e: Exception) -> None:
    """Shared error handling for remote MCP connection failures."""
    http_error = self._extract_first_exception(e, httpx.HTTPStatusError)
    if http_error and isinstance(http_error, httpx.HTTPStatusError):
        raise ValueError(...) from e
    connection_error = self._extract_first_exception(e, connection_error_types)
    if connection_error:
        raise RuntimeError(...) from e
    raise RuntimeError(...) from e
```

**Tests:**

- Test `get_or_create_session` returns same session for same key
- Test `get_or_create_session` returns different sessions for different servers
- Test `cleanup_session` properly closes exit stacks
- Test concurrent access (two tasks calling `get_or_create_session` simultaneously)
- Test that cleanup after error still works

---

## Step 3: Update `BaseAdapter.invoke_returning_run_output()`

**File:** `libs/core/kiln_ai/adapters/model_adapters/base_adapter.py` (MODIFIED)

**Changes:**

```python
from kiln_ai.tools.mcp_session_context import (
    clear_mcp_session_id,
    generate_session_id,
    get_mcp_session_id,
    set_mcp_session_id,
)

class BaseAdapter(metaclass=ABCMeta):
    async def invoke_returning_run_output(
        self,
        input: InputType,
        input_source: DataSource | None = None,
    ) -> Tuple[TaskRun, RunOutput]:
        # Determine if this is the root agent (no existing session context)
        is_root_agent = get_mcp_session_id() is None

        if is_root_agent:
            session_id = generate_session_id()
            set_mcp_session_id(session_id)

        try:
            # === EXISTING CODE (unchanged) ===
            # validate input
            if self.input_schema is not None:
                validate_schema_with_value_error(...)

            formatted_input = input
            # ... formatting ...

            run_output, usage = await self._run(formatted_input)

            # ... parsing, validation, run generation, saving ...

            return run, run_output

        finally:
            if is_root_agent:
                session_id = get_mcp_session_id()
                if session_id:
                    from kiln_ai.tools.mcp_session_manager import MCPSessionManager
                    await MCPSessionManager.shared().cleanup_session(session_id)
                clear_mcp_session_id()
```

**Why root-agent detection works:**

- Root agent: `get_mcp_session_id()` returns `None` → creates new ID
- Sub-agent (via `KilnTaskTool.run()` → `adapter.invoke()`): `get_mcp_session_id()` returns parent's ID → skips creation, reuses ID
- `asyncio.gather`: each child coroutine gets a **copy** of the context. They can read the session ID but writes don't propagate back. Since sub-agents only read, this works perfectly.

**Tests:**

- Test that root agent sets and clears the contextvar
- Test that sub-agent inherits parent's session ID
- Test that cleanup runs even when `_run()` raises
- Test that `is_root_agent` is False when contextvar is already set

---

## Step 4: Update `MCPServerTool` to use session context

**File:** `libs/core/kiln_ai/tools/mcp_server_tool.py` (MODIFIED)

**Changes:**

```python
from kiln_ai.tools.mcp_session_context import get_mcp_session_id

class MCPServerTool(KilnToolInterface):
    async def _call_tool(self, **kwargs) -> CallToolResult:
        session_id = get_mcp_session_id()

        if session_id:
            # Use cached session from the agent's session context
            session = await MCPSessionManager.shared().get_or_create_session(
                self._tool_server_model, session_id
            )
            result = await session.call_tool(
                name=await self.name(),
                arguments=kwargs,
            )
            return result
        else:
            # Fallback: ephemeral session (outside agent context)
            async with MCPSessionManager.shared().mcp_client(
                self._tool_server_model
            ) as session:
                result = await session.call_tool(
                    name=await self.name(),
                    arguments=kwargs,
                )
                return result

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

        tool = next((t for t in tools.tools if t.name == tool_name), None)
        if tool is None:
            raise ValueError(f"Tool {tool_name} not found")
        return tool
```

**Note on `_get_tool`/`_load_tool_properties`:** These are called during `available_tools()` / `litellm_tools()` which happens inside `_run()`, so the session ID is already set by the root agent. This means tool property loading will also reuse the cached session — a nice bonus that avoids extra connections.

**DRY refactor suggestion:** Extract the "get session or use ephemeral" pattern into a helper:

```python
async def _with_session(self, callback):
    session_id = get_mcp_session_id()
    if session_id:
        session = await MCPSessionManager.shared().get_or_create_session(
            self._tool_server_model, session_id
        )
        return await callback(session)
    else:
        async with MCPSessionManager.shared().mcp_client(
            self._tool_server_model
        ) as session:
            return await callback(session)
```

**Tests:**

- Test that `_call_tool` uses `get_or_create_session` when session ID is set
- Test that `_call_tool` falls back to ephemeral when no session ID
- Test that `_get_tool` uses cached session

---

## Step 5: Write comprehensive tests

### 5a. Test file: `test_mcp_session_context.py` (NEW)

Test the context module in isolation:

- `test_default_is_none` — verify default value
- `test_set_and_get` — basic set/get cycle
- `test_clear` — clear resets to None
- `test_generate_session_id_unique` — IDs are unique
- `test_asyncio_gather_propagation` — verify contextvar is readable in `asyncio.gather` children
- `test_asyncio_gather_isolation` — verify child writes don't affect parent

### 5b. Updates to: `test_mcp_session_manager.py`

Add tests for the new caching behavior:

- `test_get_or_create_session_creates_new` — first call creates session
- `test_get_or_create_session_returns_cached` — second call returns same session
- `test_get_or_create_session_different_servers` — different servers get different sessions
- `test_cleanup_session_closes_stacks` — verify `aclose()` is called
- `test_cleanup_session_removes_from_cache` — verify cache is empty after cleanup
- `test_cleanup_ignores_other_sessions` — verify only matching session_id is cleaned
- `test_concurrent_get_or_create` — two gather'd calls get same session

### 5c. Updates to: `test_base_adapter.py`

- `test_invoke_sets_session_context` — verify contextvar is set during `_run`
- `test_invoke_clears_session_context_after` — verify cleared after invoke
- `test_invoke_clears_session_context_on_error` — verify cleared even on exception
- `test_sub_agent_inherits_session` — verify sub-agent sees parent's session ID
- `test_sub_agent_does_not_create_new_session` — verify `is_root_agent` is False

### 5d. Updates to: `test_mcp_server_tool.py`

- `test_call_tool_with_session_context` — verify `get_or_create_session` is called
- `test_call_tool_without_session_context` — verify ephemeral fallback
- `test_get_tool_with_session_context` — verify cached session used for tool listing

---

## Step 6: Verification & quality checks

1. Run all existing tests to ensure no regressions
2. Run linting and type checking
3. Run formatting
4. Manually verify the async propagation chain works end-to-end (if a test MCP server is available)

---

## Implementation Order Summary

```
Step 1: mcp_session_context.py (NEW)
   ↓ no dependencies
Step 2: mcp_session_manager.py (session cache + AsyncExitStack)
   ↓ imports from Step 1
Step 3: base_adapter.py (contextvar lifecycle)
   ↓ imports from Step 1
Step 4: mcp_server_tool.py (use cached sessions)
   ↓ imports from Steps 1 & 2
Step 5: Tests for all of the above
Step 6: Quality checks (lint, typecheck, format, full test suite)
```

Steps 2 and 3 can be developed in parallel since they only share a dependency on Step 1.

---

## Risk Assessment

| Risk                                             | Likelihood | Mitigation                                                                  |
| ------------------------------------------------ | ---------- | --------------------------------------------------------------------------- |
| MCP server drops connection mid-session          | Medium     | Error propagates normally; agent retry logic handles it                     |
| Leaked sessions (process killed without finally) | Low        | Add optional TTL sweep in future if needed                                  |
| Race condition in concurrent cache access        | Low        | `asyncio.Lock` prevents this                                                |
| Breaking existing tests                          | Low        | `mcp_client()` is unchanged; new code only activates when session_id is set |
| Memory leak from cached sessions                 | Low        | Guaranteed cleanup in `finally` block                                       |

---

## Future Enhancements (Not in this PR)

1. **Session TTL/timeout** — Auto-close sessions that have been open too long
2. **Session health checks** — Ping cached sessions before returning them
3. **Metrics/logging** — Log session cache hits/misses for debugging
4. **Configuration** — Allow disabling session caching per-tool or per-server
