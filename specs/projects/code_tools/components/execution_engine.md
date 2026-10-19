---
status: complete
---

# Component: Execution Engine (sandbox worker + nested tool-call bridge)

The one novel component. Parent side: `libs/core/kiln_ai/tools/code_tool.py` (`PythonCodeTool`). Child side: `libs/core/kiln_ai/sandbox/` (stdlib-only). Contracts referenced: [functional_spec.md](../functional_spec.md) §2–4, [architecture.md](../architecture.md) §4.

## 1. Process model

One invocation = one spawned child process (confirmed: no worker pool — clean interpreter per run, code-evals precedent):

- `multiprocessing.get_context("spawn")`, `daemon=True` child (dies with the app).
- Spawn goes through the **shared** helper:

```python
# sandbox/spawn.py (stdlib-only)
_spawn_lock = threading.Lock()   # THE lock — shared by code-evals' run_scorer and code tools

def start_process_with_light_main(p: multiprocessing.process.BaseProcess) -> None:
    """p.start() under _spawn_lock with sys.modules['__main__'] swapped for a stub.

    Verbatim extraction of the block in adapters/eval/sandbox_worker.py (same
    comments, stub naming, and no-__main__ fallback). Keeps spawn children from
    re-importing the heavy parent __main__, serializes the PyInstaller-fragile
    window (bug #7410), and stays inside multiprocessing's bootstrap so
    freeze_support() keeps working.
    """
```

```python
# sandbox/entrypoint.py (stdlib-only) — shared with code-evals (subsumes the async-`score` fix)
def call_entrypoint(fn: Callable, kwargs: dict) -> Any:
    result = fn(**kwargs)
    if inspect.iscoroutine(result):        # `async def` entry points, incl. decorated/partial cases
        result = asyncio.run(result)       # child main thread; no running loop; user code must not nest asyncio.run
    return result
```

- **Two queues** from the spawn context: `requests` (child→parent) and `responses` (parent→child). Static inputs (code, kwargs) travel as `Process(args=...)`; the timeout is parent-side only.
- **Concurrency**: bounded semaphore in `tools/code_tool.py`, default `CODE_TOOL_MAX_CONCURRENCY = 8`, lazily created in the running loop, **acquired only at nesting depth 0** (nested executions bypass — counting them deadlocks the pool). `_spawn_lock` additionally serializes only `p.start()` (sub-ms).

## 2. IPC protocol

All payloads are plain dicts of JSON-level types (picklable by construction). `call_id` is a child-generated monotonically increasing int (allocated under a lock).

Child → parent (`requests` queue):

| Message | Shape |
|---|---|
| Nested tool call | `{"type": "tool_call", "call_id": int, "tool_name": str, "arguments": dict}` |
| List tools | `{"type": "list_tools", "call_id": int}` |
| Final success | `{"type": "result", "ok": str, "stdout": str, "stderr": str}` — `ok` is the already-serialized output string (§3.4) |
| Final failure | `{"type": "result", "error": str, "traceback": str \| None, "stdout": str, "stderr": str}` |

Parent → child (`responses` queue):

| Message | Shape |
|---|---|
| Tool success | `{"type": "tool_result", "call_id": int, "ok": str}` — the tool's raw output string, **verbatim** |
| Tool failure | `{"type": "tool_result", "call_id": int, "error": {"kind": "not_allowed" \| "timeout" \| "call_error", "message": str, "raw": str \| None, "available": list[str] \| None}}` |
| List-tools reply | `{"type": "tool_result", "call_id": int, "ok_list": list[{"name","description","parameters_schema"}]}` |

Exactly one `result` message ends the exchange. The child reads `responses` only through its dispatcher thread (§3.3).

## 3. Child side — `sandbox/worker.py` + `sandbox/tools_api.py`

### 3.1 Entry point

```python
def child_main(code: str, kwargs: dict, requests: Queue, responses: Queue) -> None:
```

1. Redirect stdout/stderr to `StringIO` (also the PyInstaller `--windowed` None-stdout guard), restore in `finally`; truncate each to 64 KB with an `…[truncated]` marker on send.
2. Install the synthetic modules (§3.2) and start the dispatcher thread (§3.3).
3. `exec(compile(code, "<code_tool>", "exec"), namespace)`; look up `namespace["run"]`; missing/not-callable → `result` error (defense in depth — save-time AST should have caught it).
4. `result = call_entrypoint(run_fn, kwargs)` (sync or `async def run`, §1); serialize (§3.4); put the `result` message. Any exception → `result` error with trimmed traceback (§3.5).

### 3.2 The synthetic modules — `sandbox/tools_api.py`

Constructed at child startup, before user code runs:

```python
kiln_mod = types.ModuleType("kiln")
tools_mod = types.ModuleType("kiln.tools")          # sync proxy + exceptions + list_tools
async_tools_mod = types.ModuleType("kiln.async_tools")  # awaitable mirror
kiln_mod.tools, kiln_mod.async_tools = tools_mod, async_tools_mod
sys.modules["kiln"] = kiln_mod
sys.modules["kiln.tools"] = tools_mod
sys.modules["kiln.async_tools"] = async_tools_mod
```

`from kiln import tools`, `import kiln.tools`, `from kiln import tools, async_tools`, and `from kiln.tools import ToolCallError` all work. The modules exist only inside the child (no packaging change; importing `kiln` outside code-tool execution is an ImportError).

**`tools`** members:

- `__getattr__(name)` → callable proxy `lambda **kw: _bridge.call(name, kw)` (dunder names raise `AttributeError` so inspection/pickling behave). Attribute access always succeeds; resolution is parent-side at call time.
- `list_tools()` → `_bridge.list_tools()` (reserved name; the method wins over a same-named tool — documented).
- Exceptions `ToolNotAllowed`, `ToolTimeout`, `ToolCallError` with `.tool`, `.message`, `.raw` attributes.

**`async_tools`** members: `__getattr__(name)` → `async lambda`-equivalent that runs the same sync bridge in a thread: `await asyncio.to_thread(_bridge.call, name, kw)` — truly concurrent under `asyncio.gather`; `list_tools()` likewise wrapped; the exception classes re-exported (same objects, so `except` clauses match across either import path).

`_bridge.call(name, kw)`:

1. `json.dumps(kw)` roundtrip — `TypeError` → raise `ToolCallError(tool=name, message="tool arguments must be JSON-serializable: …")` in the caller's frame.
2. Allocate `call_id`, register a `threading.Event` + result slot in `_pending[call_id]`, put the `tool_call` message, `event.wait()` (no child-side timeout — the parent enforces the wall clock and kills the child; a dead parent kills the daemon child anyway).
3. On reply: `ok` → **return the string verbatim** (no parsing — the string-returns contract: byte-for-byte what the model would see); `error` → raise the exception mapped from `kind` (`not_allowed` → `ToolNotAllowed` with the available-names list in the message, `timeout` → `ToolTimeout`, else `ToolCallError`).

Thread safety: `call_id` allocation and `_pending` mutation under one lock; any user thread — or `async_tools` via `to_thread` — may call concurrently.

### 3.3 Dispatcher thread

One daemon thread: `while True: msg = responses.get(); _pending.pop(msg["call_id"]).resolve(msg)`. Unknown `call_id` (late reply after an abandoned wait) is dropped. The thread dies with the child process.

### 3.4 Return-value serialization (child-side)

`str` → as-is. `dict/list/int/float/bool/None` → `json.dumps(...)`; a non-serializable nested value → `result` error naming the offending type/path (`repr` capped). Any other top-level type → `result` error: `run() must return str or JSON-serializable data, got <type>`.

### 3.5 Traceback trimming

`traceback.format_exception(...)`, keep frames from the first frame whose filename is `"<code_tool>"` onward (drops worker plumbing above); prepend `"Traceback (most recent call last):"`. Exceptions raised inside bridge internals below a user frame keep the user frame on top — the author always sees their own line number.

## 4. Parent side — `PythonCodeTool` internals

Core internal method (single execution path; `run()` and the test endpoint are thin presenters — architecture §6.1):

```python
@dataclass
class ChildOutcome:
    ok: str | None; error: str | None; traceback: str | None
    stdout: str; stderr: str; duration_ms: int; timed_out: bool; crashed: bool

async def _invoke(self, context: ToolCallContext | None, kwargs: dict) -> ChildOutcome:
```

Pseudocode:

```python
depth = _code_tool_depth.get()
if depth >= 10:  → error outcome ("max code tool depth exceeded — check for a cycle")
token = _code_tool_depth.set(depth + 1)
async with (_semaphore() if depth == 0 else _null_cm()):
    ctx = multiprocessing.get_context("spawn")
    requests, responses = ctx.Queue(), ctx.Queue()
    p = ctx.Process(target=child_main, args=(code, kwargs, requests, responses), daemon=True)
    await loop.run_in_executor(None, start_process_with_light_main, p)
    deadline = monotonic() + timeout_seconds
    pending_tasks: set[asyncio.Task] = set()
    try:
        while True:
            msg = await loop.run_in_executor(None, _poll_get, requests)   # Queue.get(timeout=0.1); None on Empty
            if monotonic() > deadline:            → kill child; return timed_out outcome
            if msg is None:
                if not p.is_alive() and requests.empty():   → return crashed outcome (exitcode)
                continue
            match msg["type"]:
                case "tool_call" | "list_tools":  → t = asyncio.create_task(self._serve(msg, context, responses))
                                                     pending_tasks.add(t); t.add_done_callback(pending_tasks.discard)
                case "result":                    → p.join(5); return outcome from msg
    finally:
        for t in pending_tasks: t.cancel()
        if p.is_alive(): p.kill(); p.join(5)
        requests.close(); responses.close(); requests.join_thread(); responses.join_thread()
        _code_tool_depth.reset(token)
```

Notes:

- `_poll_get` uses `Queue.get(timeout=0.1)` so the executor thread always returns promptly — deadline and child-liveness are re-checked every tick; no uncancellable blocking get. (≤0.1 s added latency per tool call; irrelevant next to spawn cost.)
- `_serve` implements the nested-call handling of architecture §4 (lazy name map, allowlist resolution, kwarg schema validation, `tool_from_id_and_project`, `await tool.run(...)`, error-kind mapping, `tool_call_recorder`) and always puts exactly one reply — including on its own exception (try/except → `call_error`). `_serve` runs in the current async context: agent-run contextvars and the incremented `_code_tool_depth` propagate to nested MCP sessions and nested code tools.
- Metadata fetches by the bridge (latency footnote, not a constraint — tool *execution* is arbitrary network anyway): kwarg validation needs the target tool's `toolcall_definition()`, which for MCP tools fetches the schema from the server on first use of that tool in a run (session-cached after); `list_tools` replies need it for every allowlisted tool. Name→ID dispatch itself is always local.
- Calls the user code fired but abandoned (from a thread, never awaited before `run()` returned) are cancelled in `finally` — documented as "in-flight calls may be cancelled when run() returns". Timeout with pending `_serve` tasks: tasks cancelled; already-dispatched side effects may have landed (covered by the test panel's side-effects warning).

`run()` maps `ChildOutcome` → `ToolCallResult`:

- `ok` → `ToolCallResult(output=ok)`.
- `error` → `is_error=True`, `output = f"Code tool '{name}' failed: {error}\n{traceback or ''}"`, `error_message=error`.
- `timed_out` → `is_error=True`, `output = f"Code tool '{name}' timed out after {timeout_seconds}s"`.
- `crashed` → `is_error=True`, `output = f"Code tool '{name}' crashed (exit code {exitcode})"`.

## 5. Test plan (component-level)

Child/protocol (real spawns, `test_sandbox_worker.py` style):
sync and **async** `run` (incl. internal `asyncio.gather`; `asyncio.run` inside async `run` → clear error); return-serialization matrix (§3.4, incl. non-serializable nested value); stdout/stderr capture + truncation; traceback trimming shows `<code_tool>` line numbers; missing `run` defense; all import forms of `kiln`/`kiln.tools`/`kiln.async_tools`; **string pass-through** (JSON-object output comes back as `str`, author parses); exception mapping incl. `.tool/.message/.raw` and available-names in `ToolNotAllowed`; exception classes identical across both modules; JSON-unsafe kwargs raise in-frame; 8 user threads calling concurrently (call_id routing); `async_tools` + `gather` truly concurrent (wall-clock assertion against a slow fake tool).

Parent (`pytest-asyncio`, fake `KilnToolInterface` doubles):
happy path; nested success/is_error/resolution-failure/ambiguous/invalid-kwargs; not-allowed lists names; `list_tools` content; timeout kills child mid-sleep and mid-nested-call (pending `_serve` cancelled); crash via `os._exit(3)`; depth cap at 10 (code-tool→code-tool chain) and self-call blocked at the datamodel; **semaphore top-level only** (depth-0 bound at 8; nested calls proceed while parents hold slots — the deadlock regression test); `tool_call_recorder` entries; contextvar propagation (agent_run_id visible in `_serve`); trust-refusal short-circuits before spawn; `run_scorer` and `PythonCodeTool` share one `_spawn_lock` (identity assertion); perf: spawn+roundtrip budget via the existing `_heavy_main_bench.py` harness pattern.
