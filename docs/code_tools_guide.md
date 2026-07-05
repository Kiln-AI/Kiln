# Code Tools: Authoring Guide

Code tools let you write Python functions that run as tools inside Kiln's agent harness. A code tool can call other tools it has been granted access to, making it ideal for orchestration, filtering, and multi-step workflows.

This guide covers the authoring contract: how to write the Python, how to call other tools, and how results and errors work.

## Entry point

Every code tool must define a module-level function named `run`. Both sync and async forms are supported:

```python
def run(query: str, max_results: int = 10) -> str:
    """Search and return filtered results."""
    # your code here
    return "result"
```

```python
async def run(urls: list[str], concurrency: int = 50) -> list:
    """Fetch URLs concurrently."""
    import asyncio
    # your async code here
    results = await asyncio.gather(*(fetch(u) for u in urls))
    return results
```

**Parameters** are passed as keyword arguments matching the tool's `parameters_schema` (JSON Schema). Optional parameters not provided by the caller are simply not passed -- use Python defaults.

**Return values** become the tool output string sent to the model:
- `str` passes through as-is.
- `dict`, `list`, `int`, `float`, `bool`, `None` are JSON-serialized (`json.dumps`).
- Anything else that isn't JSON-serializable is an error.

**Async notes:** When using `async def run`, the runtime owns the event loop. Your code should `await` and use `asyncio.gather` freely. Do not call `asyncio.run()` inside an async `run` -- there is already a running loop. A sync `def run` may call `asyncio.run()` if it needs async internally.

## Environment

- **Interpreter**: The Kiln app's bundled Python. You can import anything from the standard library and anything shipped in the Kiln bundle.
- **No sandbox**: There are no import restrictions or resource limits beyond the wall-clock timeout. Code runs on your machine with full access.
- **Security**: Code tools only execute in trusted projects. The trust gate prevents execution in untrusted projects.

## Calling other tools

Code tools can call other tools they've been granted access to via the allowlist. Two modules are available inside the code tool environment:

```python
from kiln import tools          # sync -- blocks until the tool returns
from kiln import async_tools    # async -- awaitable, concurrent under gather
```

### Sync usage

```python
from kiln import tools

def run(user_id: str) -> str:
    result = tools.get_user(id=user_id)
    return result
```

### Async usage

```python
from kiln import async_tools
import asyncio

async def run(user_ids: list[str]) -> str:
    results = await asyncio.gather(
        *(async_tools.get_user(id=uid) for uid in user_ids)
    )
    return results
```

Use `async_tools` in async code for true concurrency. Using `tools` (sync) inside an `async def run` blocks the event loop -- it works but defeats the purpose of async.

### Tool call results are always `str`

Every tool call returns a string -- byte-for-byte what the model would see from that tool. When a tool returns JSON, parse it yourself:

```python
import json
from kiln import tools

def run(query: str) -> str:
    raw = tools.search(query=query)
    results = json.loads(raw)  # parse the JSON string
    filtered = [r for r in results if r.get("score", 0) > 0.5]
    return json.dumps(filtered)
```

This is deliberate: results are always strings for type stability and fidelity to what the model sees. `json.loads` is one line.

### Listing available tools

```python
from kiln import tools

def run() -> str:
    available = tools.list_tools()
    # Returns: [{"name": "...", "description": "...", "parameters_schema": {...}}, ...]
    return available
```

`list_tools()` is a reserved name that returns the tools in your allowlist. It takes priority over any allowlisted tool with the same name.

## Exceptions

Tool calls can raise typed exceptions. Import them from either module:

```python
from kiln.tools import ToolNotAllowed, ToolTimeout, ToolCallError
# or equivalently:
from kiln.async_tools import ToolNotAllowed, ToolTimeout, ToolCallError
```

| Exception | When |
|---|---|
| `ToolNotAllowed` | The tool name is not in the allowlist. The `.message` includes available names. |
| `ToolTimeout` | A nested tool call timed out. |
| `ToolCallError` | Everything else: the tool returned an error, arguments failed schema validation, the tool couldn't be resolved. Has `.tool`, `.message`, and `.raw` (the raw output string when available). |

Use these for retry logic:

```python
from kiln import tools
from kiln.tools import ToolCallError

def run(item_id: str) -> str:
    for attempt in range(3):
        try:
            return tools.fetch_item(id=item_id)
        except ToolCallError:
            if attempt == 2:
                raise
```

## Timeout and allowlist

- **Timeout**: Wall-clock timeout for one invocation, including time spent in nested tool calls. Default is 60 seconds, minimum 1, no maximum. Set when creating the tool.
- **Allowlist**: Explicit list of tools this code tool may call. Only tools in the allowlist are callable. Tools are resolved by function name at call time.
- **Nesting**: Code tools can call other code tools (they're just tools). A maximum nesting depth of 10 prevents runaways.

## Concurrency

You can use threads and asyncio freely. Tool calls are safe from multiple threads or gathered coroutines simultaneously. The harness executes them concurrently.

There is no built-in batch/parallelism helper -- use standard library constructs (`ThreadPoolExecutor`, `asyncio.gather`, etc.) as shown in the examples below.

## Examples

### Parallel with retries (threads + `tools`)

Fetch multiple URLs in parallel with exponential backoff retries, using the sync `tools` API from worker threads:

```python
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from kiln import tools

def run(urls: list[str], max_retries: int = 3) -> str:
    """Fetch multiple URLs in parallel with retries."""
    results = {}

    def fetch_with_retry(url):
        for attempt in range(max_retries):
            try:
                result = tools.fetch_url(url=url)
                return url, json.loads(result)
            except Exception as e:
                if attempt == max_retries - 1:
                    return url, {"error": str(e)}
                time.sleep(0.5 * (attempt + 1))

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(fetch_with_retry, u) for u in urls]
        for future in as_completed(futures):
            url, data = future.result()
            results[url] = data

    return json.dumps(results)
```

### Async fan-out (`async_tools` + `gather`)

Fetch user details concurrently using the async API for true parallelism:

```python
import json
import asyncio
from kiln import async_tools

async def run(user_ids: list[str]) -> str:
    """Fetch user details concurrently using async_tools."""
    async def fetch_user(uid):
        result = await async_tools.get_user(id=uid)
        return json.loads(result)

    users = await asyncio.gather(*(fetch_user(uid) for uid in user_ids))
    return json.dumps(users)
```

### Filter and transform (`json.loads` result filtering)

Search and filter results, demonstrating how to parse and reshape tool output:

```python
import json
from kiln import tools

def run(query: str, max_results: int = 10) -> str:
    """Search and filter results, returning only relevant fields."""
    raw = tools.search(query=query)
    results = json.loads(raw)

    filtered = [
        {"title": r["title"], "url": r["url"]}
        for r in results[:max_results]
        if "title" in r and "url" in r
    ]

    return json.dumps(filtered)
```
