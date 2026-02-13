# MCP Session Management — Design Report

## Executive Summary

Each MCP tool call currently spawns a new connection/subprocess, breaking stateful MCP servers. We propose using `contextvars` to propagate a session ID from the root agent through all sub-agents, combined with `AsyncExitStack`-based session caching in `MCPSessionManager` to keep transports alive for the duration of an agent run.

**Key insight missed by prior designs:** Simply caching `ClientSession` objects does not work. The underlying transport (HTTP connection or stdio subprocess) is managed by a context manager that kills the transport on exit. We must use `AsyncExitStack` to keep the entire transport stack alive.

---

## Question 1: Is `contextvars` the best pattern?

**Yes.** It is the optimal choice for this codebase.

| Factor               | Assessment                                                                        |
| -------------------- | --------------------------------------------------------------------------------- |
| Async propagation    | Copies through `asyncio.gather`, `await`, sub-coroutines automatically            |
| No signature changes | Tools and adapters keep their current APIs                                        |
| Standard library     | Built into Python 3.7+, no dependencies                                           |
| Isolation            | Each `asyncio.run()` or `Task` gets its own context copy — no cross-request leaks |
| Debugging            | Simple string session IDs, easy to log and trace                                  |

### Alternatives rejected:

| Alternative                                 | Why not                                                                                                                                                                                 |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Explicit context object**                 | Requires changing `_run()`, `process_tool_calls()`, `tool.run()`, `_call_tool()`, and every adapter's method signatures. Invasive refactor for a cross-cutting concern.                 |
| **Thread-local storage**                    | Wrong model — the adapter path is pure async. Thread-locals don't propagate across `await` boundaries or `asyncio.gather`.                                                              |
| **Global/singleton state**                  | No isolation between concurrent requests (FastAPI serves multiple requests concurrently on the same event loop).                                                                        |
| **Pass session_id through ToolCallContext** | Would work but requires modifying `ToolCallContext`, `KilnToolInterface.run()` signature, and every tool implementation. `contextvars` achieves the same without any signature changes. |

---

## Question 2: Will this work in the codebase?

**Yes.** The design aligns perfectly with Kiln's architecture.

### Async propagation verified:

```
Root Agent (BaseAdapter.invoke — sets contextvar)
  │
  ├─> _run() → _run_model_turn()
  │     └─> process_tool_calls()
  │          └─> asyncio.gather([tool1.run(), tool2.run(), tool3.run()])
  │               ├─> MCPServerTool._call_tool()        ✅ reads contextvar
  │               ├─> KilnTaskTool.run()
  │               │    └─> adapter.invoke()              ✅ sees existing contextvar (not root)
  │               │         └─> _run() → tools...
  │               │              └─> MCPServerTool._call_tool()  ✅ reads same contextvar
  │               └─> MCPServerTool._call_tool()         ✅ reads contextvar
  │
  └─> finally: cleanup all cached sessions
```

Key `asyncio.gather` behavior: child coroutines get a **copy** of the parent's context. They can read the session ID. If a child writes to the contextvar, it doesn't affect the parent or siblings. This is exactly the isolation model we want — only the root agent sets the session ID.

### No threading conflicts:

The entire adapter → tool → MCP chain is async. The threading usage in the codebase (config lock, desktop server, PDF conversion) is completely outside the adapter path.

### FastAPI concurrent requests:

FastAPI runs multiple request handlers as coroutines on the same event loop. `contextvars` provides per-coroutine isolation — two concurrent `/run` requests will each have their own session ID with no cross-talk.

---

## Question 3: Does session manager allow reusing connections?

**No. And this is the hardest part of the design.**

### The transport lifecycle problem:

Current code uses nested context managers:

```python
# Remote
async with streamablehttp_client(url) as (read, write, _):      # ← transport
    async with ClientSession(read, write) as session:             # ← session
        await session.initialize()
        yield session
# ← BOTH transport AND session are now dead

# Local
with tempfile.TemporaryFile() as err_log:                        # ← stderr capture
    async with stdio_client(params, errlog=err_log) as (r, w):   # ← subprocess
        async with ClientSession(r, w) as session:                # ← session
            await session.initialize()
            yield session
# ← subprocess killed, temp file closed, session dead
```

**You cannot cache `ClientSession` alone.** When the outer context manager exits, the transport closes, and the cached session becomes a dead object pointing at a closed socket or killed process.

### Solution: `AsyncExitStack`

`contextlib.AsyncExitStack` lets us enter context managers and keep them open until we explicitly close the stack:

```python
from contextlib import AsyncExitStack

stack = AsyncExitStack()
await stack.__aenter__()

# Enter transport — stays open until stack.aclose()
read, write, _ = await stack.enter_async_context(
    streamablehttp_client(url, headers=headers)
)

# Enter session — stays open until stack.aclose()
session = await stack.enter_async_context(
    ClientSession(read, write)
)
await session.initialize()

# Later, to close everything:
await stack.aclose()  # closes session, then transport, in reverse order
```

For local (stdio) servers, we also need `stack.enter_context()` (sync) for the `TemporaryFile`.

This is the standard Python pattern for managing dynamic sets of context managers with non-lexical lifetimes.

---

## Question 4: What changes are needed?

### Change Summary

| File                     | Change                                                                              | Complexity            |
| ------------------------ | ----------------------------------------------------------------------------------- | --------------------- |
| `mcp_session_context.py` | **NEW** — ContextVar + helpers                                                      | Simple (~25 lines)    |
| `mcp_session_manager.py` | Add session cache with `AsyncExitStack`, `get_or_create_session`, `cleanup_session` | Moderate (~120 lines) |
| `base_adapter.py`        | Set contextvar in `invoke_returning_run_output`, cleanup in `finally`               | Simple (~15 lines)    |
| `mcp_server_tool.py`     | Read contextvar, pass session_id to manager                                         | Simple (~10 lines)    |
| Tests for above          | Unit tests for each component                                                       | Moderate (~200 lines) |

**Total: ~370 lines new/modified** (including tests)

### Detailed changes:

#### 1. New file: `mcp_session_context.py`

- `ContextVar[str | None]` for session ID
- `get_mcp_session_id()`, `set_mcp_session_id()`, `clear_mcp_session_id()`
- `generate_session_id()` using `uuid4`

#### 2. Modified: `mcp_session_manager.py`

- Add `_session_cache: dict[str, tuple[ClientSession, AsyncExitStack]]`
- Add `asyncio.Lock` for cache access (needed because `asyncio.gather` can cause concurrent access)
- Add `get_or_create_session(tool_server, session_id) -> ClientSession` — checks cache, creates with `AsyncExitStack` if missing
- Add `cleanup_session(session_id)` — closes all exit stacks for a session
- Preserve existing error handling for both remote and local servers
- Keep `mcp_client()` as a backward-compatible thin wrapper

#### 3. Modified: `base_adapter.py`

- In `invoke_returning_run_output()`: check if contextvar is already set (sub-agent case)
- If not set (root agent): generate session ID, set contextvar
- Wrap body in `try/finally`, cleanup in `finally` only if root agent

#### 4. Modified: `mcp_server_tool.py`

- In `_call_tool()` and `_get_tool()`: read session ID from contextvar
- Pass to `MCPSessionManager.mcp_client()` or new `get_or_create_session()`

---

## Question 5: Design decisions

### Decision 1: Session IDs (strings) vs Session objects

**Choice: Session IDs (strings)**

Rationale:

- BaseAdapter shouldn't know about MCP `ClientSession` — it's a cross-cutting concern, not an adapter concern
- String IDs are serializable, loggable, and debuggable
- The session manager maps IDs to actual sessions internally
- Natural composite key: `f"{server_id}:{session_id}"` for per-server-per-agent caching

### Decision 2: Implicit context (`contextvars`) vs Explicit context object

**Choice: Implicit with `contextvars`**

Rationale:

- **Zero signature changes** — `_run()`, `process_tool_calls()`, `tool.run()`, `_call_tool()` all keep their current signatures
- Impossible to forget to pass context (it's always available)
- Standard Python pattern for cross-cutting concerns in async code (same approach used by `decimal` context, OpenTelemetry tracing, etc.)
- If we later need more context (not just MCP sessions), we can add more `ContextVar`s or put a richer object in the existing one

### Decision 3: Where to set/clear context

**Choice: `BaseAdapter.invoke_returning_run_output()` with root-agent detection**

```python
is_root = get_mcp_session_id() is None
if is_root:
    set_mcp_session_id(generate_session_id())
try:
    # ... existing logic ...
finally:
    if is_root:
        await cleanup_session(get_mcp_session_id())
        clear_mcp_session_id()
```

Why here and not `invoke()`:

- `invoke()` delegates to `invoke_returning_run_output()`, so wrapping the latter covers both entry points
- The `_run()` call (which triggers tool calls) happens inside `invoke_returning_run_output()`

Why root-agent detection:

- Sub-agents (via `KilnTaskTool`) also call `invoke()` → `invoke_returning_run_output()`
- They should inherit the parent's session ID, not create a new one
- Checking `get_mcp_session_id() is None` distinguishes root from sub-agent

### Decision 4: Session caching scope

**Choice: Cache both remote AND local MCP sessions**

Prior proposals suggested not caching local (stdio) sessions. This is wrong — local stdio servers are the most likely to be stateful (memory servers, filesystem tools, etc.). The `AsyncExitStack` approach handles both transport types uniformly.

### Decision 5: `mcp_client()` API evolution

**Choice: Keep `mcp_client()` as backward-compatible context manager, add `get_or_create_session()` for cached path**

The `mcp_client()` context manager remains for:

- Backward compatibility
- Ephemeral sessions (no session_id)
- Cases outside agent runs (e.g., tool listing in UI)

The new `get_or_create_session()` is used when a session_id is available (during agent runs).

### Decision 6: Concurrency safety

**Choice: `asyncio.Lock` on the session cache**

`asyncio.gather` can cause two tool calls to concurrently try to create a session for the same server. The lock ensures only one creates the session while the other waits and gets the cached one.

---

## Edge Cases

### 1. MCP server connection drops mid-session

If a cached session fails, the error propagates to the tool call. The agent's error handling (or retry logic) handles this. We do NOT automatically retry with a new session — that could mask bugs.

### 2. Multiple MCP servers in one agent run

The cache key is `f"{server_id}:{session_id}"`, so each server gets its own independent cached session within the same agent run.

### 3. Tool property loading (`_load_tool_properties`)

This is called before the agent run starts (in `available_tools()`/`litellm_tools()`), potentially before the session ID is set. This is fine — tool listing is stateless and can use ephemeral sessions.

### 4. No tools configured

If an agent has no MCP tools, the contextvar is still set but no sessions are created. Cleanup is a no-op. Zero overhead.

### 5. Agent crashes mid-run

The `finally` block in `invoke_returning_run_output()` guarantees cleanup. `AsyncExitStack.aclose()` properly shuts down transports even on error.

### 6. Stale session timeout

For a first implementation, we rely on the `finally` cleanup. If needed later, we can add a TTL-based cleanup sweep for sessions that somehow leak (e.g., if the process is killed without running `finally`).

---

## Comparison with Prior Design Proposals

| Aspect              | Prior Reports (project34645, project_4545_gemini)                                | This Design                                                      |
| ------------------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Session caching     | Caches `ClientSession` objects directly                                          | Caches `(ClientSession, AsyncExitStack)` tuples                  |
| Transport lifecycle | **Broken** — transport closes when context manager exits, cached session is dead | Correct — `AsyncExitStack` keeps transport alive                 |
| Local MCP servers   | "Don't cache"                                                                    | Cache them (they're the most stateful!)                          |
| Cleanup             | `session_cache.pop()` — leaks transport                                          | `stack.aclose()` — properly shuts down transport chain           |
| Error handling      | Not addressed                                                                    | Preserved — errors during session creation use existing handlers |
| Lock type           | `asyncio.Lock` (correct)                                                         | `asyncio.Lock` (correct)                                         |

The core insight: **session caching requires lifecycle management of the entire transport stack, not just the session object.**
