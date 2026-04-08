# Refinement: BaseHTTPMiddleware with Response Buffering

**Resolves:** Crit #1 (ASGI middleware can't change response after sent)

## Decision

Use Starlette's `BaseHTTPMiddleware` instead of raw ASGI middleware. Buffer response body before committing, so commit/push failures can still return error responses.

## What changes from architecture.md

**Replace** the raw ASGI `GitSyncMiddleware` with a `BaseHTTPMiddleware` subclass.

## Design

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class WriteContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        manager = self._get_manager_for_request(request)

        if manager is None:
            # No auto-sync — pass through without buffering.
            # Preserves streaming for non-sync routes.
            return await call_next(request)

        ctx = ...  # enter write_context
        request.state.write_context = ctx
        try:
            response = await call_next(request)

            # Buffer full body — route handler has completed at this point
            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            # Commit after body is fully read, before sending to client
            await ctx.commit_and_push()

            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        except Exception:
            await ctx.rollback()
            # Map error type to HTTP status per error table
            return Response(
                content='{"detail": "..."}',
                status_code=...,
                media_type="application/json",
            )
```

## Key details

### No buffering overhead when sync is disabled

If `_get_manager_for_request` returns `None` (project not auto-sync, or non-project route), the middleware calls `call_next` directly and returns the response as-is. No body buffering, streaming preserved. The buffering cost only applies to auto-sync routes.

### Contextvar propagation — integration test required

`BaseHTTPMiddleware` runs `call_next` in a separate anyio task internally. The `write_context` contextvar must be visible deep in the call stack when `write_file()` is called from route handlers. Python 3.10+ copies context to child tasks, so it should work, but **write an early integration test** to verify:

1. Middleware enters write_context (sets contextvar)
2. Route handler calls `save_to_file()` (sync, possibly via `asyncio.to_thread`)
3. `write_file()` reads contextvar successfully

If propagation fails, fallback is passing context via `request.state` with a retrieval helper, but this is messier since `write_file()` doesn't have access to the request object.

### Error mapping

The `except` block maps error types to HTTP status codes per the existing error table in architecture.md (e.g. `SyncConflictError` -> 409, `RemoteUnreachableError` -> 503).

## Why

- Raw ASGI middleware sends `http.response.start` (status+headers) before body — can't change status after that
- `BaseHTTPMiddleware` gives us access to the full response before it's sent to the client
- Buffering is acceptable — API responses are small JSON payloads
- Non-sync routes skip buffering entirely, preserving streaming
