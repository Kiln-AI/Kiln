---
status: complete
---

# Phase 2: `call_kiln_api`

## Overview

Add the second MCP tool, `call_kiln_api`, which lets an agent call Kiln's REST API through the running app. It wraps the Kiln Assistant's `KilnApiCallTool`, which is refactored in `libs/core` so both tools share one implementation: a pure request-preparation step, a structured response, an injectable transport, a client that ignores proxy settings, and trailing-slash removal. The MCP side adds the pipeline (argument checks, route match against the app's own route table, query coercion, the connection-policy seam, the HTTP call with progress updates, and the result shaping with `body_limit` and `save_to_tmpfile`), the temp-file store with its purges, and the `x-mcp-policy` tag helpers in `libs/server`. The server is built with the API app and a temp folder; the desktop mount passes both. An end-to-end test runs the real desktop app on a port and calls both tools with the SDK client.

Specs: [mcp_server_and_api_tool](../components/mcp_server_and_api_tool.md) sections 3–6.2, 9 and 10; architecture sections 3 and 9.

Left for phase 3: annotating the 29 blocked routes, the block-list test, and the `PUT` → `POST` change. So in this phase no real route carries `x-mcp-policy`; the end-to-end test checks a refusal of an unknown endpoint, and the blocked path is covered by the package tests with a synthetic `DENY_MCP` route. Phase 3 adds the blocked call to the end-to-end test.

## Steps

1. **`libs/core/kiln_ai/utils/config.py`**: add
   ```python
   def local_api_base_url(host: str, port: int) -> str
   ```
   `""`/`0.0.0.0` → `127.0.0.1`; `::` → `::1`; brackets stripped, then a host containing `:` is bracketed; returns `http://{host}:{port}`. `Config.kiln_local_api_base_url()` returns `local_api_base_url(self.kiln_local_api_host, self.kiln_local_api_port)`.

2. **`libs/core/kiln_ai/tools/built_in_tools/kiln_api_call_tool.py`**:
   ```python
   @dataclass(frozen=True)
   class PreparedApiRequest: method: str; url_path: str; body_str: str | None
   def prepare_api_request(method: str, url_path: str, body: str | dict | list | None = None) -> PreparedApiRequest
   @dataclass(frozen=True)
   class KilnApiResponse: status_code: int; content_type: str; is_sse: bool; body_text: str; body: Any; body_is_json: bool
   class KilnApiResponseError(ValueError):  # .status_code
   class KilnApiCallTool(KilnTool):
       def __init__(self, api_base_url: str, transport: httpx.AsyncBaseTransport | None = None)
       async def call(self, *, method, url_path, body=None, query_params=None, jq_filter=None) -> KilnApiResponse
       async def run(...)  # unchanged signature; output from call()
   ```
   Check order in `prepare_api_request`: method → leading `/` → `rstrip("/")` when the result is not empty → allowed path → `?`/`#` → body on GET/DELETE. Remove the near-miss branch of `_disallowed_path_message`. `call()` uses `httpx.AsyncClient(transport=self._transport, trust_env=False)`; the JSON and jq failures raise `KilnApiResponseError`. Export the new names from `built_in_tools/__init__.py`. Name, description and schema unchanged.

3. **`libs/server/kiln_server/utils/agent_checks/policy.py`**: `MCP_POLICY_KEY`, `DENY_MCP`, `with_mcp_deny(agent_policy)`, `is_mcp_denied(openapi_extra)`, exported from the package `__init__`. A section on the tag in `agent_checks/README.md`; one sentence in `.agents/skills/kiln-conventions/references/server_desktop.md`.

4. **`app/mcp/kiln_mcp_server/api_tool/`** (new package):
   - `messages.py`: texts 2–10 of server doc 4.3 as constants and format functions; `{CAT}` from `skill_files.API_CATALOGUE_INDEX_PATH`.
   - `route_index.py`: `RouteEntry`, `RouteMatch`, `RouteIndex.from_app(app)`, `RouteIndex.match(method, url_path)` (unquote, then first full match in route order; wrong method lists the path's methods sorted).
   - `policy.py`: `ConnectionScope`, `ApiCall`, `PolicyDecision`, `OPEN_SCOPE`, `ALLOWED`, `ConnectionPolicy.scope_for_request`, `ConnectionPolicy.check` (blocked entry → text 4).
   - `tmp_files.py`: `default_tmp_root()`, `SavedFile`, `TmpFileError`, `TmpFileStore(root, max_age_seconds=24*3600)` with `save`, `purge_all`, `purge_expired` per server doc 4.5.
   - `progress.py`: `ProgressSender`, `run_with_progress(work, send, *, label, interval=2.0)` per server doc 4.4.
   - `pipeline.py`: `coerce_query_params`, `run_api_call(deps, request, send_progress, *, method, url_path, body, query_params, jq_filter, body_limit, save_to_tmpfile) -> CallToolResult` with steps 1–7 of server doc 4.2.
   - `tool.py`: `ApiToolDeps` (frozen dataclass), `CALL_KILN_API_TOOL_NAME`, `register_call_kiln_api(mcp, deps)` with the argument table of server doc 4.1 and `structured_output=False`.

5. **`texts.py`**: add `CALL_KILN_API_DESCRIPTION` (the draft of server doc 4.1).

6. **`server.py`**:
   ```python
   def build_kiln_mcp_server(*, api_app: FastAPI, app_version: str, host: str, port: int,
                             tmp_root: Path, api_transport: httpx.AsyncBaseTransport | None = None) -> KilnMcpServer
   ```
   Builds `RouteIndex.from_app(api_app)`, `ConnectionPolicy()`, `TmpFileStore(tmp_root)`, `local_api_base_url(host, port)`; registers `kiln_skill` then `call_kiln_api`. `KilnMcpServer.run()` purges all temp files in a thread, starts the hourly `purge_expired` sweep task, enters the session manager, and cancels the sweep on exit. `__init__.py` also exports `default_tmp_root`.

7. **Desktop**: `kiln_mcp_mount.connect_kiln_mcp_server` passes `api_app=app` and `tmp_root=default_tmp_root()` (imported by name into the module so tests can patch it). New `app/desktop/conftest.py` with the autouse fixture `kiln_mcp_tmp_root`.

## Tests

- `libs/core/.../test_kiln_api_call_tool.py`: the near-miss test becomes a success test for `/ping/` and `/ping//`; `/api/projects/` reaches `/api/projects`; `/api/` and `/` still refused; `prepare_api_request` cases (method upper-cased, body serialised, order of checks, trailing slash removed, error names the stripped path); `call()` fields for a JSON body, a text body, an SSE stream, a jq filter with several outputs (`body_is_json` false), a non-2xx with a jq filter (not applied); `KilnApiResponseError.status_code` for the not-JSON and jq errors; the injected transport is used; the client is built with `trust_env=False`; a snapshot of description and parameters schema.
- `libs/core/.../utils/test_config.py`: `local_api_base_url` for `127.0.0.1`, `localhost`, `0.0.0.0`, `""`, `::`, `::1`, `[::1]`, `192.168.1.5`; `kiln_local_api_base_url` uses it.
- `libs/server/.../agent_checks/test_policy.py`: `DENY_MCP` shape; `with_mcp_deny` keeps the agent policy and does not change its input; `is_mcp_denied` for `None`, no key, deny; `dump_annotations` output is the same with and without the key.
- `api_tool/test_route_index.py`: found with `path_params`; unknown; wrong method lists methods; static route wins over parameter route; a block on one of the pair does not block the other, both ways; `%73` and `%2F` escapes match as the server routes them; non-`/api` routes and mounts left out; for 20 sample paths the result equals a walk of `app.routes` with `route.matches(scope)`.
- `api_tool/test_policy.py`: blocked entry → not allowed with text 4; allowed entry → `ALLOWED`; `scope_for_request(None)` and with a request → `OPEN_SCOPE`.
- `api_tool/test_pipeline.py`: bad `body_limit`; core refusals pass through unchanged; trailing slash removed before lookup; unknown; wrong method; blocked with no HTTP request (counting transport); query coercion table; 404 and 422 inline with `isError` false; jq applied; jq error on GET and on POST; over limit on GET; same body on POST returned; limit measured after jq; higher `body_limit` passes; non-2xx over the limit returned; saved result shape for `.json` and `.txt` with file content equal to `body_text`; non-2xx with `save_to_tmpfile` inline; save-failure text for GET and POST; SSE summary; timeout and connect texts with the non-GET sentence; unexpected exception → text 10; compact result JSON; progress updates sent for a slow call.
- `api_tool/test_progress.py`: no update when the call ends first; N updates for a slow call; `send=None`; a failing `send` does not fail the call; cancelling the caller cancels the work; the work's exception propagates.
- `api_tool/test_tmp_files.py`: folder `0o700`, file `0o600` (POSIX); name pattern and extension; `size_bytes`; `purge_all` removes files and leaves sub-folders; `purge_expired` removes only old files; symlinked root and a root owned by another uid → `TmpFileError`; missing folder is not an error for the purges.
- `api_tool/test_tool.py` (in-memory client session): lower-case method accepted, numbers and booleans in `query_params`, `"50000"` for `body_limit`, unknown arguments ignored, progress notifications reach a client that sends a `progressToken`.
- `test_server.py`: `tools/list` has exactly `call_kiln_api` and `kiln_skill`; the `call_kiln_api` schema equals a snapshot and has no `outputSchema`; `run()` purges the temp folder at start; the hourly sweep calls `purge_expired`; a `tools/call` of `call_kiln_api` reaches the API app through the injected transport. Existing cases updated for the new signature.
- `test_texts.py`: `CALL_KILN_API_DESCRIPTION` names `kiln_skill`, `body_limit` and `save_to_tmpfile`.
- `app/desktop/studio_server/test_kiln_mcp_mount.py`: `tools/list` has both tools; the built server's store uses the `kiln_mcp_tmp_root` folder; the route index sees the desktop routes. End to end: `ThreadedServer(server_config(port, "127.0.0.1"))`, SDK `streamablehttp_client`, `kiln_skill`, `call_kiln_api` `GET /ping` and `GET /api/projects`, an unknown endpoint refused, and the server stops within 5 s.
