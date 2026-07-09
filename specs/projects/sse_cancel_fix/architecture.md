---
status: complete
---

# Architecture: SSE Cancel Fix

Small, single-file architecture. No separate component designs.

## Files touched

- `app/desktop/git_sync/middleware.py` — add `__call__` override; no changes to `dispatch` or helpers.
- `app/desktop/git_sync/test_middleware.py` — add unit tests for the bypass path.
- `app/desktop/studio_server/test_eval_api.py` — add the integration cancellation test.
- `app/desktop/git_sync/test_sse_invariants.py` (new) — annotation-based invariant test across the full app.

No new source files, no new helpers, no new dependencies.

## Core change: `GitSyncMiddleware.__call__`

`BaseHTTPMiddleware.__call__` does two things that break SSE: it opens an `anyio` task group, and it replaces the ASGI `receive` with a proxy. The fix is an `__call__` override that short-circuits to pure ASGI for `@no_write_lock` endpoints, and delegates to `super().__call__(...)` for everything else.

```python
class GitSyncMiddleware(BaseHTTPMiddleware):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await super().__call__(scope, receive, send)

        # Build a Request wrapper only for route matching / manager lookup.
        # The real receive/send are preserved for the downstream app.
        request = Request(scope)
        endpoint = self._resolve_endpoint(request)

        if not getattr(endpoint, "_git_sync_no_write_lock", False):
            return await super().__call__(scope, receive, send)

        await self._no_write_lock_asgi(scope, receive, send, request)

    async def _no_write_lock_asgi(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        request: Request,
    ) -> None:
        manager = self._get_manager_for_request(request)
        if manager is None:
            await self.app(scope, receive, send)
            return

        try:
            await manager.ensure_fresh_for_read()
        except GitSyncError as e:
            status, message = self._map_error(e)
            error_response = Response(
                content=json.dumps({"detail": message}, ensure_ascii=False),
                status_code=status,
                media_type="application/json",
            )
            await error_response(scope, receive, send)
            return

        self._notify_background_sync(manager)
        scope.setdefault("state", {})
        scope["state"]["git_sync_manager"] = manager

        await self.app(scope, receive, send)
```

Why this works: `self.app` is `BaseHTTPMiddleware`'s downstream app (set in `__init__`). Awaiting it directly with the real `receive` and `send` gives the route handler — and therefore `StreamingResponse.__call__` — the real ASGI channels. `listen_for_disconnect` can see `http.disconnect`, cancel the body task, and the cancellation chain described in the functional spec completes.

### Why construct `Request` just for routing

`_resolve_endpoint` and `_get_manager_for_request` both accept `Request` today and read only `request.scope` + `request.url.path` internally. Constructing `Request(scope)` with no `receive`/`send` is cheap — Starlette allows scope-only construction for the URL-inspection use case, and the constructed request never awaits any body.

Alternative considered: refactor both helpers to accept `scope` directly. Functionally identical; rejected to keep the diff smaller and the existing `dispatch` call sites unchanged.

### State attachment

FastAPI's `Request.state` is backed by `scope["state"]`. The existing dispatch path uses `request.state.git_sync_manager = manager` (which writes to `scope["state"]`). The ASGI bypass path does the same assignment via direct `scope["state"]` access, so `build_save_context(request)` inside the endpoint continues to work with zero change.

### ASGI type handling

`scope["type"] == "http"` — go through the routing check above.
`scope["type"]` is anything else (`"lifespan"`, `"websocket"`) — delegate to `super().__call__`. This matches BaseHTTPMiddleware's existing behavior for non-HTTP scopes.

## Behavior matrix after change

Identical to the functional spec's table. The only new row is "URL matches, endpoint has `_git_sync_no_write_lock = True`" taking the ASGI bypass. All other rows remain in `super().__call__` → existing `dispatch`.

## Dev-time invariant

### Static test — `test_streaming_routes_require_no_write_lock`

New file `app/desktop/git_sync/test_sse_invariants.py`:

```python
import typing
from typing import Union, get_args, get_origin, get_type_hints

from fastapi.routing import APIRoute
from starlette.responses import StreamingResponse

from app.desktop.server import make_app   # or wherever the full app is assembled


def _return_type_is_streaming(fn) -> bool:
    try:
        hints = get_type_hints(fn)
    except Exception:
        return False
    ret = hints.get("return")
    if ret is None:
        return False
    return _contains_streaming_response(ret)


def _contains_streaming_response(tp) -> bool:
    if isinstance(tp, type) and issubclass(tp, StreamingResponse):
        return True
    origin = get_origin(tp)
    if origin is Union or origin is typing.Union or origin is type(int | str):
        return any(_contains_streaming_response(a) for a in get_args(tp))
    return False


def test_streaming_routes_require_no_write_lock():
    app = make_app()
    offenders = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not _return_type_is_streaming(route.endpoint):
            continue
        if not getattr(route.endpoint, "_git_sync_no_write_lock", False):
            offenders.append(f"{route.methods} {route.path}")
    assert not offenders, (
        "Routes return StreamingResponse but are not @no_write_lock:\n  "
        + "\n  ".join(offenders)
        + "\n\nAdd @no_write_lock to the route handler; otherwise "
        "GitSyncMiddleware will buffer the stream and client disconnects "
        "will not cancel in-flight workers."
    )
```

Notes:
- Uses `get_type_hints` (not raw `__annotations__`) to resolve forward references and string annotations.
- Recognises `Union`, PEP 604 `X | Y`, and plain subclasses. Ignores `Any`, `None`, or missing annotations — those fall to the runtime check.
- Uses the real app assembly so it exercises the full route table, not a reduced test app.

### Runtime test — `test_dev_mode_logs_missing_no_write_lock_for_sse`

Covers the existing `_dev_mode_dirty_check` SSE branch. Place in `app/desktop/git_sync/test_middleware.py`:

```python
async def test_dev_mode_logs_missing_no_write_lock_for_sse(monkeypatch, caplog):
    monkeypatch.setenv("KILN_DEV_MODE", "true")
    app = FastAPI()
    app.add_middleware(GitSyncMiddleware)

    @app.get("/api/projects/{project_id}/leak")
    async def leak(project_id: str):
        async def gen():
            yield b"data: hi\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    # Prime a manager for this project so the middleware matches.
    _install_fake_manager_for_project(project_id="p1")

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        await client.get("/api/projects/p1/leak")

    assert any(
        "DEV MODE: SSE endpoint missing @no_write_lock" in r.message
        for r in caplog.records
    )
```

If the existing test file already has a fixture for installing a fake manager, reuse it.

## Tests: middleware unit

All in `app/desktop/git_sync/test_middleware.py`. Use existing fixtures for manager registration.

| Test                                                     | Setup                                                     | Assertion                                                                 |
| -------------------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------- |
| `test_no_write_lock_takes_asgi_bypass`                   | Tagged endpoint, matched URL, manager installed           | `super().__call__` (→ `dispatch`) not called; `self.app` called with original `receive`/`send` |
| `test_write_endpoint_uses_dispatch`                      | Untagged POST endpoint                                    | `dispatch` is called (sanity)                                             |
| `test_no_write_lock_attaches_manager_to_state`           | Tagged endpoint returns `scope["state"]["git_sync_manager"]` via an introspection endpoint | Returned manager matches the installed one                                 |
| `test_no_write_lock_ensure_fresh_error_returns_json`     | `manager.ensure_fresh_for_read` raises `SyncConflictError` | Response is 409 JSON matching existing error shape                        |
| `test_no_write_lock_no_manager_passes_through`           | `_get_manager_for_request` returns None                   | `self.app` called; `ensure_fresh_for_read` not called                     |
| `test_unmatched_url_goes_through_super`                  | URL outside `/api/projects/{id}/...`                      | `dispatch` / `_unmatched_dispatch` still runs                             |
| `test_non_http_scope_delegates_to_super`                 | Send a `lifespan` scope                                   | Behaves like base class; no crash                                          |

Assertion strategy for "super called / not called": monkeypatch `BaseHTTPMiddleware.dispatch` on the subclass to a recording spy, or wrap `self.app` with a recording wrapper.

## Tests: integration cancellation

New test in `app/desktop/studio_server/test_eval_api.py`.

### Approach

Rather than standing up a real eval pipeline, inject a fake `AsyncJobRunner` that records cancellation:

```python
class RecordingRunner:
    def __init__(self):
        self.finally_ran = asyncio.Event()
        self.workers_cancelled = 0

    async def run(self):
        # Emit a first progress chunk so the client sees data and has something
        # to read, confirming the stream is live. Then await forever.
        try:
            yield Progress(complete=0, total=1, errors=0)
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                self.workers_cancelled += 1
                raise
        finally:
            self.finally_ran.set()
```

`run_eval_runner_with_status` accepts any `AsyncGenerator[Progress, None]`-producing runner, so swapping in the recording runner via FastAPI `Depends` override is sufficient.

### Test body

```python
async def test_sse_cancels_on_client_disconnect(app_with_middleware, monkeypatch):
    recorder = RecordingRunner()
    monkeypatch.setattr(eval_api, "EvalRunner", lambda *a, **kw: recorder)

    async with httpx.AsyncClient(app=app_with_middleware, base_url="http://t") as c:
        async with c.stream("GET", SSE_URL) as resp:
            it = resp.aiter_bytes()
            first = await asyncio.wait_for(it.__anext__(), timeout=1.0)
            assert b"data:" in first
            # Let the client close the stream (httpx aborts the request on exit)

    await asyncio.wait_for(recorder.finally_ran.wait(), timeout=2.0)
    assert recorder.workers_cancelled == 1
```

This proves end-to-end: ASGI bypass → Starlette's disconnect detection → `event_generator` cancelled → `runner.run()` aclose'd → `finally:` runs.

If `httpx.AsyncClient`'s in-process transport does not reliably surface `http.disconnect` (some versions do not), switch to `uvicorn` on a real socket:

```python
server = uvicorn.Server(Config(app_with_middleware, port=0, log_level="warning"))
# start in background task, hit with real httpx, close connection, await recorder
```

Start with the in-process approach; fall back only if it doesn't produce the disconnect event.

### Cover one endpoint

Run the integration test against `run_comparison` only. The other four SSE endpoints share the same middleware path and the same helper family; the unit tests cover the middleware, and the invariant tests ensure all five remain tagged.

## Error handling

No new error types, no new error paths.

Existing paths preserved:

- `GitSyncError` from `ensure_fresh_for_read` in bypass → JSON error response (matches dispatch path).
- `GitSyncError` elsewhere → unchanged (dispatch path).
- `_StreamingUnderWriteLock` → unchanged (dispatch path only; bypass skips write-lock entirely).

## Non-goals for architecture

- `AsyncJobRunner` is not touched. Its existing `finally:` (lines 127-134) is the cancellation lever.
- Endpoint `event_generator` functions and `run_*_runner_with_status` helpers are not touched.
- `BaseHTTPMiddleware.dispatch` body — unchanged.
- Route decorators — unchanged. No `response_class` additions.

## Risks and mitigations

| Risk                                                          | Mitigation                                                                                     |
| ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Future streaming endpoint added without `@no_write_lock`      | Static invariant test fails at CI; dev-mode runtime log fires on first local run.              |
| `_resolve_endpoint` routing mismatch between `__call__` and `dispatch` | Both call the same helper with the same scope; no divergence possible.                         |
| State attachment races with concurrent requests               | `scope` is per-request; no shared state introduced.                                            |
| `httpx.AsyncClient` in-process transport misses `http.disconnect` | Fall back to real `uvicorn` for the integration test. Unit tests still prove the code path.   |
| Change to `BaseHTTPMiddleware` internals (upstream Starlette) breaks the bypass | Bypass does not depend on BaseHTTPMiddleware internals — only that `super().__call__` honours the standard ASGI contract when we delegate to it. |

## Testing strategy summary

| Layer              | Scope                                                             | Framework      |
| ------------------ | ----------------------------------------------------------------- | -------------- |
| Middleware unit    | Routing matrix, state attachment, error path                      | pytest + httpx |
| Invariant (static) | All FastAPI routes returning `StreamingResponse`                  | pytest         |
| Invariant (runtime)| Dev-mode log on untagged streaming response                       | pytest + caplog |
| Integration        | End-to-end cancellation propagation for one SSE endpoint          | pytest + httpx (or uvicorn) |

Manual acceptance (UI hard-refresh of a live eval) is the smoke-test at the end of the change; not a permanent automated test.
