---
status: draft
---

# Component: MCP server and `call_kiln_api`

Covers the `app/mcp` project, the server and its mount in the desktop app, the `KilnApiCallTool` refactor, the MCP `call_kiln_api` tool, the connection-policy seam, the `x-mcp-policy` tag with the route index and block list, the `PUT` → `POST` change, and the rename of the old `kiln_mcp` texts. Functional spec sections 4, 5, 11, 13 and 14. `kiln_skill` and the skill tree are in [skill_and_content](skill_and_content.md); this doc only names their module and hook.

Marks: **[V]** verified by running code against the repo (`mcp` 1.30.0, Python 3.13), **[S]** read in source.

## 1. The `app/mcp` project

### 1.1 Files

```
app/mcp/                          NO __init__.py here, ever (1.3)
  pyproject.toml
  kiln_mcp_server/
    __init__.py                   exports build_kiln_mcp_server, KilnMcpServer, MCP_PATH
    server.py                     build_kiln_mcp_server, KilnMcpServer, McpEndpoint, the logging guard
    addresses.py                  is_loopback_host, transport_security_for
    instructions.py               SERVER_INSTRUCTIONS
    api_tool/
      __init__.py                 exports register_call_kiln_api, ApiToolDeps
      tool.py                     register_call_kiln_api: argument schema, description, FastMCP glue
      pipeline.py                 run_api_call (the steps of 4.3), coerce_query_params, result builders
      messages.py                 every error text of 4.5 as a constant or a small format function
      route_index.py              RouteIndex, RouteEntry, RouteMatch
      policy.py                   ConnectionPolicy, ConnectionScope, ApiCall, PolicyDecision
      tmp_files.py                TmpFileStore, default_tmp_root
      progress.py                 run_with_progress
    skill_tool/                   other doc. Hook: register_kiln_skill(mcp, ...)
    skill/                        other doc. Package data
    test_*.py                     beside each module
```

SDK imports (`mcp.*`) are allowed only in `server.py`, `addresses.py`, `api_tool/tool.py`, `api_tool/pipeline.py` (result types) and `skill_tool/`. `kiln_mcp_server` never imports `app.desktop`.

### 1.2 `app/mcp/pyproject.toml`

Template: `libs/server/pyproject.toml`.

```
[project]
name = "kiln-mcp-server"
version = "1.2.1"                       # same as the other members
requires-python = ">=3.10"
description = "The MCP server built into the Kiln app"
dependencies = ["kiln-ai", "kiln-server", "fastapi>=0.115.4", "starlette>=1.3.1",
                "httpx>=0.27.2", "pydantic>=2.9.2", "mcp>=1.30.0,<2"]
[tool.uv]
exclude-newer = "7 days"
[tool.uv.sources]
kiln-ai = { workspace = true }
kiln-server = { workspace = true }
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
[tool.hatch.metadata]
requires-python = ">=3.10"
```

No console script. No `license` field and no licence file: a person adds those. Hatchling finds the package because the folder name equals the normalised project name.

### 1.3 Wiring

- Root `pyproject.toml`: add `"app/mcp"` to `[tool.uv.workspace] members`, `kiln-mcp-server = { workspace = true }` to `[tool.uv.sources]`, `"kiln-mcp-server"` to `dependencies`.
- `app/desktop/pyproject.toml`: add `"kiln-mcp-server"` to `dependencies` and `kiln-mcp-server = { workspace = true }` to `[tool.uv.sources]`.
- `uv lock`. `mcp` stays at 1.30.0.
- Ruff, ty, pytest: root config only, nothing to add. Tests import as `kiln_mcp_server.test_x`.
- `app/mcp/__init__.py` must not exist. PyInstaller runs from `app/` with `--paths=.`, which goes first on the module path, so a regular package `app/mcp` would shadow the `mcp` SDK in the frozen app [S]. A test guards it (7).
- PyInstaller data: new file `app/desktop/pyinstaller_hooks/hook-kiln_mcp_server.py` (the hooks folder is already on the build command line):
  ```
  from PyInstaller.utils.hooks import collect_data_files
  datas = collect_data_files("kiln_mcp_server")
  ```
  Python modules are found by import analysis. No change to `build_desktop_app.sh`.
- CI: `checks.sh` needs no change for this component (its checks run on the whole repo). `build_and_test.yml`: add a `uv build` step in `./app/mcp`. `playwright.yml`: add `app/mcp/**` to both path filters. `build_desktop.yml`: add `app/mcp/**`, `app/desktop/build_desktop_app.sh` and `app/desktop/pyinstaller_hooks/**` to the pull-request paths.
- `debug_detector.yml` fails on `print(`: the package logs with `logging.getLogger(__name__)` only.

## 2. Server construction and mounting

### 2.1 Public API (`kiln_mcp_server/server.py`)

```
MCP_PATH = "/mcp"
SERVER_NAME = "kiln"

def build_kiln_mcp_server(
    *,
    api_app: FastAPI,                 # the app whose routes the tool may call
    app_version: str,                 # reported as serverInfo.version
    host: str,                        # the host Kiln is bound to
    port: int,
    api_transport: httpx.AsyncBaseTransport | None = None,   # tests only
    tmp_root: Path | None = None,                            # tests only
) -> KilnMcpServer

class KilnMcpServer:
    asgi_app: McpEndpoint                                    # the endpoint for the /mcp route
    def run(self) -> AbstractAsyncContextManager[None]       # enter once, in the app lifespan

class McpEndpoint:                                           # ASGI app
    _git_sync_no_write_lock = True
    def __init__(self, inner: ASGIApp) -> None
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None
```

`build_kiln_mcp_server`, in order:

1. `security = transport_security_for(host)` (2.4).
2. Inside the logging guard (2.5): `mcp = FastMCP(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS, stateless_http=True, json_response=False, log_level="WARNING", transport_security=security)`. The request body limit stays at the SDK default, 4 MiB (a larger `body` gets HTTP 413 from the transport).
3. `mcp._mcp_server.version = app_version` [V]. FastMCP 1.30 has no public argument for it. This is the one private SDK attribute used.
4. Build the dependencies: `RouteIndex.from_app(api_app)`, `ConnectionPolicy()`, `TmpFileStore(tmp_root)`, `local_api_base_url(host, port)` (3.3).
5. `register_kiln_skill(mcp, ...)` then `register_call_kiln_api(mcp, ApiToolDeps(...))`. Exactly two tools; no prompts, no resources.
6. `mcp.streamable_http_app()`, result discarded: it creates `mcp.session_manager` [S].
7. `asgi_app = McpEndpoint(StreamableHTTPASGIApp(mcp.session_manager))` (`mcp.server.fastmcp.server.StreamableHTTPASGIApp`).

A new server is built on every call. Nothing is built at import time: `session_manager.run()` works once per instance, and `make_app()` runs many times per process in tests.

`McpEndpoint.__call__`: when `scope["type"] == "http"` and `scope["method"] != "POST"`, answer `Response(status_code=405, headers={"Allow": "POST"})`; otherwise call `inner`. Stateless mode has no server stream; without this, `GET /mcp` holds an empty SSE stream open for ever [V]. CORS preflights never reach it (`CORSMiddleware` answers them).

`KilnMcpServer.run()`:

```
await asyncio.to_thread(tmp_files.purge_all)
sweeper = asyncio.create_task(sweep_loop())      # every 3600 s: to_thread(tmp_files.purge_expired)
try:
    async with mcp.session_manager.run():
        yield
finally:
    sweeper.cancel()
```

### 2.2 Desktop wiring

New file `app/desktop/studio_server/kiln_mcp_mount.py`:

```
def connect_kiln_mcp_server(app: FastAPI) -> None:
    config = Config.shared()
    server = build_kiln_mcp_server(api_app=app, app_version=__version__,     # studio_server/_version.py
                                   host=config.kiln_local_api_host, port=config.kiln_local_api_port)
    app.state.kiln_mcp_server = server
    app.add_route(MCP_PATH, server.asgi_app, include_in_schema=False)
```

`app/desktop/desktop_server.py`:

- `make_app()`: call `connect_kiln_mcp_server(app)` after `connect_jobs_api(app)` and immediately before `connect_webhost(app)`. It must be the last `connect_*` before the web host: the route index is built from `app.routes` at that moment.
- `lifespan()`: wrap the `yield`. Nothing else changes.
  ```
  try:
      await _start_background_syncs()
      async with app.state.kiln_mcp_server.run():
          yield
  finally:
      ...                                  # unchanged
  ```
- `server_config()`: add `timeout_graceful_shutdown=2` to `uvicorn.Config(...)`. uvicorn waits for open connections before it runs lifespan shutdown; with no bound, one in-flight tool call blocks quit [V, on `ThreadedServer`]. After 2 s uvicorn cancels the request tasks; the tool handler is cancelled and cancels its REST call (4.6).

`app/desktop/dev_server.py`, `dev_app.py`: no change. The dev server calls the same `make_app()` and lifespan, and already sets `timeout_graceful_shutdown=1`. The library server (`kiln_server.server`) does not get the MCP.

Results of this shape [V, on the real desktop app]: route order ends `…, Route /mcp, Mount ""`; `POST /mcp` → 200 `text/event-stream`; `/mcp` is not in `app.openapi()`; `POST /mcp/` → 405 and `GET /mcp/` → 404 from the web host; no 401 anywhere, so no client starts OAuth. If ty rejects the ASGI object against `add_route`'s annotation, append `starlette.routing.Route(MCP_PATH, endpoint=server.asgi_app, include_in_schema=False)` to `app.router.routes`; it is what `add_route` does.

### 2.3 Git sync

`GitSyncMiddleware` reads `_git_sync_no_write_lock` from the matched route's endpoint, which is the `McpEndpoint` instance. With the marker, `/mcp` takes the raw ASGI branch: no `BaseHTTPMiddleware` task, no dev-mode dirty sweep, no write lock [S]. Writes still sync: the tool's REST calls pass through the middleware as normal `/api/projects/...` requests.

### 2.4 Transport security (`addresses.py`)

```
def is_loopback_host(host: str) -> bool        # "localhost", or an IP literal with .is_loopback (brackets stripped)
def transport_security_for(host: str) -> TransportSecuritySettings
```

- Loopback bind: `enable_dns_rebinding_protection=True`. Names = `127.0.0.1`, `localhost`, `[::1]`, plus the bound host if it is another loopback address. `allowed_hosts` = each name and `name:*`. `allowed_origins` = `http://name` and `http://name:*`. A request with no `Origin` passes (every CLI agent). The bare names cover port 80. The `:*` form keeps a forwarded port working (`ssh -L 9000:localhost:8757`); the port adds nothing against rebinding.
- Any other bind (`0.0.0.0`, `::`, a LAN address, a host name): `TransportSecuritySettings(enable_dns_rebinding_protection=False)`. The REST API on the same port has no Host or Origin check, and the MCP follows it.
- Never rely on FastMCP's default: it would answer 421 to every remote client of a non-loopback bind [V].

### 2.5 Logging trap

`FastMCP.__init__` calls `logging.basicConfig` with a Rich handler [V]. It is harmless in the shipped app (uvicorn's `dictConfig` runs later) but it changes the root logger in the dev server and in every test. `server.py` wraps the constructor:

```
@contextmanager
def _preserve_root_logging():
    root = logging.getLogger(); handlers = list(root.handlers); level = root.level
    try: yield
    finally:
        for h in list(root.handlers):
            if h not in handlers: root.removeHandler(h)
        root.setLevel(level)
```

### 2.6 Identity and instructions

`serverInfo` = `kiln` + the app version. `instructions.py` holds the draft below (wording is tuned in the content phase; the same trigger text is in the `kiln_skill` description). The first paragraph is under 500 characters and stands alone. A test checks both limits.

```
Kiln is an app for building, evaluating and optimizing AI agents: prompts, models, tools, evals, synthetic data, fine-tuning and RAG. This server connects you to the user's running Kiln app. Call the `kiln_skill` tool first, before any other Kiln tool: it returns the instructions for working with Kiln. When the user asks for `/kiln`, or asks to use Kiln, that is a request to call `kiln_skill`.

Tools:
- `kiln_skill` reads the Kiln skill. Call it with no arguments for the instructions. Pass a `path` that the instructions name to read one reference file. Only paths the instructions list are valid. Do not guess.
- `call_kiln_api` calls Kiln's REST API. The skill's API reference lists every endpoint. Read an endpoint's doc before you call it.

Rules:
- The skill arrives through a tool call and can drop out of your context. If you no longer have it, call `kiln_skill` again.
- A result of `call_kiln_api` with a non-2xx `status_code` is the API's own error. Read the body and act on it.
- Confirm with the user before a destructive or irreversible operation.
```

### 2.7 Concurrency and shutdown

- Stateless: each POST gets its own server task on the uvicorn loop. There is no session and no per-client state.
- Shared objects: `RouteIndex` (immutable after build), `ConnectionPolicy` (no state), `TmpFileStore` (unique names, `O_EXCL`). No lock and no cap on parallel calls.
- Each call builds its own `KilnApiCallTool` and `httpx.AsyncClient`, as the Assistant does. The self-call is one more request on the same server; async handlers and thread-pool handlers both work from inside a tool [V].
- A dropped client connection cancels the tool handler at once [V]. In stateless mode a `notifications/cancelled` message cannot reach the handler [S].
- Shutdown: 2.2 (`timeout_graceful_shutdown`). Leaving `session_manager.run()` cancels what is left.

## 3. `KilnApiCallTool` refactor (`libs/core`, option A)

File: `libs/core/kiln_ai/tools/built_in_tools/kiln_api_call_tool.py`. New names are exported from `built_in_tools/__init__.py`.

### 3.1 New types and signatures

```
@dataclass(frozen=True)
class PreparedApiRequest:
    method: str                 # upper case, one of GET POST PATCH DELETE
    url_path: str               # validated, trailing slash removed
    body_str: str | None

def prepare_api_request(method: str, url_path: str,
                        body: str | dict | list | None = None) -> PreparedApiRequest
    # Today's step 1, as a pure function. Raises ValueError with today's texts.

@dataclass(frozen=True)
class KilnApiResponse:
    status_code: int
    content_type: str           # lower case, "" when absent
    is_sse: bool
    body_text: str              # the text after jq; else the raw text; for SSE the summary JSON
    body: Any                   # json.loads(body_text) when that works, else body_text
    body_is_json: bool

class KilnApiResponseError(ValueError):      # raised after the response arrived
    status_code: int

class KilnApiCallTool(KilnTool):
    def __init__(self, api_base_url: str, transport: httpx.AsyncBaseTransport | None = None)
    async def call(self, *, method: str, url_path: str, body: str | dict | list | None = None,
                   query_params: Mapping[str, str | list[str]] | None = None,
                   jq_filter: str | None = None) -> KilnApiResponse
    async def run(self, context=None, *, method, url_path, body=None, query_params=None,
                  jq_filter=None) -> ToolCallResult        # signature unchanged
```

- `call()` = `prepare_api_request` + today's steps 2–4 (request, SSE drain, jq on 2xx). It builds `httpx.AsyncClient(transport=self._transport, trust_env=False)`: the call is a loopback self-call and must not go to a proxy from the environment. The two post-response failures ("Response is not valid JSON: …", "jq filter error: …") raise `KilnApiResponseError` with the same text.
- `run()` = `r = await self.call(...)`, then `ToolCallResult(output=json.dumps({"status_code": r.status_code, "body": r.body}, ensure_ascii=False))`.
- `prepare_api_request` check order: method → starts with `/` → **strip** (`stripped = url_path.rstrip("/")`; use it when not empty) → allowed path → `?`/`#` → body on GET/DELETE. The "near miss on an exact path" branch of `_disallowed_path_message` is now dead code and is removed.

### 3.2 Base URL (`libs/core/kiln_ai/utils/config.py`)

```
def local_api_base_url(host: str, port: int) -> str
```

`""`, `0.0.0.0` → `127.0.0.1`. `::` → `::1`. Strip brackets; an address that contains `:` is written in brackets. Returns `http://{host}:{port}`. `Config.kiln_local_api_base_url()` returns `local_api_base_url(self.kiln_local_api_host, self.kiln_local_api_port)`, so the Assistant gets the fix. Today it returns `http://0.0.0.0:8757` and an invalid URL for `::1` [S].

### 3.3 What stays the same for the Assistant

Byte-identical: the tool name, description and parameters schema (no `body_limit`, no `save_to_tmpfile`); the `run()` output string for every response; every error text, except that a path with a trailing slash is now named without it. Changed on purpose (spec 5.1, 5.3): a trailing slash is removed, so `/ping/` and `/api/projects/` work; proxy settings from the environment are ignored; the base URL is correct for wildcard and IPv6 hosts.

### 3.4 Test changes (`test_kiln_api_call_tool.py`, `test_config.py`)

- `test_near_miss_on_an_exact_path_is_corrected_to_that_path` (`/ping/`, `/ping//`) becomes a success test.
- New: `call()` fields for a JSON body, a text body, an SSE stream, a jq filter with several outputs (`body_is_json` false), a non-2xx with a jq filter (filter not applied); `/api/projects/` reaches `/api/projects`; `/api/` and `/` are still refused; `KilnApiResponseError.status_code`; the injected `transport` is used; the client is built with `trust_env=False`; `prepare_api_request` cases; a snapshot of description and schema.
- All existing assertions on `json.loads(result.output)` stay unchanged.
- `local_api_base_url`: `127.0.0.1`, `localhost`, `0.0.0.0`, `""`, `::`, `::1`, `[::1]`, `192.168.1.5`.

## 4. The MCP `call_kiln_api` tool

### 4.1 Registration (`api_tool/tool.py`)

```
@dataclass(frozen=True)
class ApiToolDeps:
    api_base_url: str
    route_index: RouteIndex
    policy: ConnectionPolicy
    tmp_files: TmpFileStore
    transport: httpx.AsyncBaseTransport | None = None
    progress_interval: float = 2.0

def register_call_kiln_api(mcp: FastMCP, deps: ApiToolDeps) -> None
```

It registers one function with `@mcp.tool(name="call_kiln_api", description=CALL_KILN_API_DESCRIPTION, structured_output=False)`, annotated `-> CallToolResult` (then there is no `outputSchema` and no duplicate `structuredContent` [V]). The function only passes its arguments, `ctx.request_context.request` and `ctx.report_progress` to `run_api_call` (4.3).

### 4.2 Arguments and description

`QueryValue = str | int | float | bool`. Each argument is `Annotated[<type>, Field(description=...)]`.

| Argument | Python type, default | Description text |
|---|---|---|
| `method` | `str` with `json_schema_extra={"enum": ["GET","POST","PATCH","DELETE"]}` | HTTP method: GET, POST, PATCH or DELETE. |
| `url_path` | `str` | API path, for example `/api/projects`. No query string: pass query arguments in `query_params`. Correct paths are in the endpoint docs. |
| `body` | `dict[str, Any] \| list[Any] \| str \| None = None` | JSON request body for POST and PATCH: an object, an array, or a string that holds JSON. Not allowed with GET or DELETE. The schema is in the endpoint doc. |
| `query_params` | `dict[str, QueryValue \| None \| list[QueryValue]] \| None = None` | Query parameters as an object. Values are strings, numbers or booleans. A list repeats the key (`?ids=a&ids=b`). |
| `jq_filter` | `str \| None = None` | Optional jq expression applied to a successful (2xx) JSON response before it is returned or saved. |
| `body_limit` | `int = 30000` | Longest body, in characters, that a GET may return. Pass a higher number only when you need the whole body in your context. |
| `save_to_tmpfile` | `bool = False` | When true, the body of a successful response is written to a temporary file on the machine that runs Kiln. The result then holds `status_code`, `body_path` and `size_bytes`, and no `body`. Use the file with shell tools such as jq or grep. An error response is still returned inline. |

`method` is a plain string with an enum in the schema, so a lower-case `get` is accepted [V]. `"50000"` is accepted for `body_limit`, a JSON string is accepted for `body`, and unknown arguments are ignored [V].

`CALL_KILN_API_DESCRIPTION` (draft; MCP only, the Assistant keeps its own):

```
Call the Kiln REST API. Makes one HTTP request to the running Kiln app and returns JSON with `status_code` and `body`.

Call `kiln_skill` first. Endpoint paths, request bodies, response fields and useful jq filters are in the skill's API reference, one doc per endpoint, not here. Read the endpoint's doc before you call it. Do not guess paths.

A non-2xx answer from the API is returned as data (`status_code` and the API's error body), not as a tool failure. Read it and act on it.

Large responses: a GET whose body is longer than `body_limit` characters returns an error and no body. Narrow the request with `jq_filter`, paging or filter parameters, or set `save_to_tmpfile` to get a file path in place of the body.

Streaming endpoints (text/event-stream): the tool reads the stream to its end and returns body = {"event_count": N, "message": "..."}. The end of the stream does not mean the job succeeded: check its status afterwards. A call can run for minutes.
```

### 4.3 Pipeline (`api_tool/pipeline.py`)

```
ProgressSender = Callable[[float, float | None, str | None], Awaitable[None]]

async def run_api_call(deps: ApiToolDeps, request: Request | None, send_progress: ProgressSender | None, *,
                       method: str, url_path: str, body, query_params, jq_filter: str | None,
                       body_limit: int, save_to_tmpfile: bool) -> CallToolResult
```

`E(n)` below means "return the error result with text n of 4.5".

1. **Check `body_limit`.** `< 1` → E(6).
2. **Normalise.** `prepared = prepare_api_request(method, url_path, body)`. `ValueError` → E(1).
3. **Route match.** `match = deps.route_index.match(prepared.method, prepared.url_path)`. `unknown` → E(2). `wrong_method` → E(3).
4. **Policy.** `scope = deps.policy.scope_for_request(request)`; `decision = deps.policy.check(ApiCall(...), scope)`. Not allowed → E with `decision.message` (text 4 in this project).
5. **Query parameters.** `coerce_query_params(query_params)`: `None` value → key dropped; `bool` → `"true"`/`"false"` (tested before `int`); `int` → `str(v)`; `float` → `str(int(v))` when `v.is_integer()`, else `repr(v)`; `str` kept; a list → each item by the same rules. An empty result → `None`.
6. **HTTP call with progress.** `tool = KilnApiCallTool(deps.api_base_url, deps.transport)`; `resp = await run_with_progress(tool.call(method=prepared.method, url_path=prepared.url_path, body=prepared.body_str, query_params=..., jq_filter=jq_filter), send_progress, label=f"{method} {url_path}", interval=deps.progress_interval)`. jq runs inside `call()`, on 2xx only. `TimeoutError`, `ConnectionError` → E(7). `KilnApiResponseError` → E(8). Any other `Exception` → `logger.exception`, E(10). `CancelledError` is not caught.
7. **Shape** (in `asyncio.to_thread`: it serialises and may write a file):
   - `body_json = json.dumps(resp.body, ensure_ascii=False, separators=(",", ":"))`.
   - Not 2xx → inline result. Never saved, never limited: the agent needs the API's error.
   - 2xx and `save_to_tmpfile` → `saved = deps.tmp_files.save(resp.body_text, resp.body_is_json)` → saved result. `TmpFileError`/`OSError` → E(9). `body_limit` is not applied.
   - 2xx, method `GET`, `len(body_json) > body_limit` → E(5).
   - Otherwise → inline result.

### 4.4 Result shapes

One `TextContent`. Compact JSON, `ensure_ascii=False`.

| Case | `isError` | Text |
|---|---|---|
| Inline | false | `{"status_code":200,"body":<body_json>}` |
| Saved | false | `{"status_code":200,"body_path":"/tmp/kiln_mcp/kiln_api_20261120_101500_3fa9c2d1.json","size_bytes":48213}` |
| Refusal or failure | true | the plain text of 4.5, no JSON wrapper |

Every error is returned as `CallToolResult(content=[TextContent(type="text", text=...)], isError=True)`. An exception raised in a FastMCP tool gets the prefix `Error executing tool call_kiln_api: ` [V]; returning the result keeps the text exact. The length in text 5 is `len(body_json)`: the body as the result would hold it, after `jq_filter`.

### 4.5 Error texts

`{M}` method, `{P}` normalised path, `{T}` route template, `{CAT}` = `references/knowledge/api_docs/api_index.md` (constant `API_CATALOGUE_PATH`; the name is owned by the skill doc).

| # | When | Exact text |
|---|---|---|
| 1 | Path or method refused by `prepare_api_request` | The core text, unchanged: `Invalid method '{M}'. Must be one of: DELETE, GET, PATCH, POST` / `url_path must start with '/', got: {P}` / the two texts of `_disallowed_path_message` (dot segments; "must start with '/api/', or be exactly '/ping'… Did you mean '/api{P}'?") / `url_path must not contain a query string or fragment ('?' or '#'). Pass query args via query_params.` / `body parameter not allowed with {M} method` |
| 2 | No route matches the path | `No Kiln API endpoint matches {M} {P}. Do not guess paths. Read the API catalogues in the Kiln skill ({CAT}) to find the endpoint, then read its doc before you call it.` |
| 3 | The path exists, the method does not | `{M} is not supported on {P}. This path supports: {methods, sorted, comma separated}. Read the endpoint's doc in the Kiln skill's API catalogues ({CAT}).` |
| 4 | MCP block tag | `The endpoint {M} {T} is not available to agents over MCP. Do not retry it and do not look for another way to call it. If the user needs this, ask them to do it in the Kiln app.` |
| 5 | Body over the limit (spec 5.6) | ``Body too long. Length {len} on limit {body_limit}. Either narrow your request (a `jq_filter`, paging or filter parameters), save it to a file with `save_to_tmpfile`, or call again passing a `body_limit` higher than {len}.`` |
| 6 | Bad `body_limit` | `body_limit must be a positive integer. Got: {body_limit}.` |
| 7 | Timeout or no connection | The core text: `Request to {P} timed out after 900.0s` (30.0s for connect) / `Could not connect to server for {P}`. For a method other than GET, append: ` The {M} may have taken effect. Check the state before you repeat it.` |
| 8 | Response not JSON, or jq failed | The core text (`Response is not valid JSON: …` / `jq filter error: …`). For a method other than GET, append: ` The {M} request itself completed with status {status_code}. Do not repeat it; fix the jq_filter only if you call a read endpoint.` |
| 9 | The temp file could not be written | `Could not save the response to a temporary file: {reason}. The request completed with status {status_code}.` then, for GET: ` Call again without save_to_tmpfile.`; for another method: ` Do not repeat the {M}.` |
| 10 | Unexpected exception | `Unexpected error in call_kiln_api: {ExceptionType}: {message}` |
| — | Argument of the wrong type, or a required one missing | The SDK's text: `Error executing tool call_kiln_api: N validation error(s) for call_kiln_apiArguments …`. Not under our control. |
| — | MCP request body over 4 MiB | HTTP 413 from the transport, before the tool runs. |

### 4.6 Progress (`api_tool/progress.py`)

```
async def run_with_progress(work: Coroutine[Any, Any, T], send: ProgressSender | None, *,
                            label: str, interval: float = 2.0) -> T
```

```
task = asyncio.ensure_future(work); ticks = 0
try:
    while True:
        done, _ = await asyncio.wait({task}, timeout=interval)
        if done: return task.result()
        ticks += 1
        if send is not None:
            try: await send(float(ticks), None, f"{label}: still running, {int(ticks * interval)} s")
            except Exception: send = None            # log at debug; keep waiting for the call
finally:
    if not task.done(): task.cancel()
```

- Interval 2 s, the first update 2 s after the call starts. `asyncio.wait` is used because `asyncio.timeout` and `TaskGroup` are missing on Python 3.10.
- `Context.report_progress` does nothing when the client sent no `progressToken` [V]. With a token, updates reach the client in stateless SSE mode through the real middleware stack [V].
- The `finally` cancels the REST call when the handler is cancelled (client gone, or shutdown).
- The SSE response also carries a `: ping` comment every 15 s from `sse_starlette`; it keeps the connection open but does not reset MCP tool timeouts.

### 4.7 Temp files (`api_tool/tmp_files.py`)

```
TMP_MAX_AGE_SECONDS = 24 * 3600

def default_tmp_root() -> Path                 # Path(tempfile.gettempdir()) / "kiln_mcp"

@dataclass(frozen=True)
class SavedFile:
    path: Path
    size_bytes: int

class TmpFileError(Exception): ...

class TmpFileStore:
    def __init__(self, root: Path | None = None, max_age_seconds: float = TMP_MAX_AGE_SECONDS)
    def save(self, text: str, is_json: bool) -> SavedFile
    def purge_all(self) -> None
    def purge_expired(self) -> None
```

- `root=None` resolves `default_tmp_root()` at each use, by a module-level lookup, so tests can patch it (7).
- Folder: created with `os.mkdir(root, 0o700)`. If it exists it must be a real folder (not a symlink) owned by the current user (`os.lstat(root).st_uid == os.getuid()`, where `os.getuid` exists); then `os.chmod(root, 0o700)`. Otherwise `TmpFileError("{root} exists but is not a folder owned by the current user")`. There is no fallback folder.
- Name: `kiln_api_<YYYYMMDD>_<HHMMSS>_<secrets.token_hex(4)>` in UTC, plus `.json` when `is_json`, else `.txt`.
- Write: `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)`, then `text.encode("utf-8")`. `size_bytes` is the byte count. The text is written as received: no re-serialising.
- `purge_all` (at start, from `run()`): unlink every regular file directly in the folder. `purge_expired` (hourly): the same for files whose `st_mtime` is older than the limit. Both use `os.scandir` with `follow_symlinks=False`, never recurse, skip a file that cannot be removed, and return quietly when the folder is missing or fails the ownership check (one warning in the log).
- Windows: `tempfile.gettempdir()` is the per-user `%TEMP%`; mode bits are ignored and the profile's ACL gives the protection; there is no owner check; a file open in another program cannot be removed and is tried again at the next sweep.
- Two Kiln processes on one machine (the app and a dev server) share the folder, so one's start removes the other's files. Accepted.

## 5. Connection-policy seam (`api_tool/policy.py`)

```
@dataclass(frozen=True)
class ConnectionScope:
    kind: Literal["open"] = "open"            # spec two adds scoped kinds and their data
OPEN_SCOPE = ConnectionScope()

@dataclass(frozen=True)
class ApiCall:
    method: str
    url_path: str                             # normalised concrete path
    route: RouteEntry
    path_params: Mapping[str, str]
    query_params: Mapping[str, str | list[str]] | None
    body: str | None

@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    message: str | None = None                # the error text when not allowed
ALLOWED = PolicyDecision(True)

class ConnectionPolicy:
    def scope_for_request(self, request: Request | None) -> ConnectionScope     # here: always OPEN_SCOPE
    def check(self, call: ApiCall, scope: ConnectionScope) -> PolicyDecision
```

`check` in this project: `call.route.mcp_blocked` → `PolicyDecision(False, text 4)`; else `ALLOWED`. It is the only place that decides "is this call allowed on this connection", and `run_api_call` calls it before every REST call. Spec two reads a token from `request.path_params` in `scope_for_request` and adds rules in `check`; the two signatures and the pipeline stay as they are. Calls that match no route never reach the policy: they are refused in step 3.

## 6. `x-mcp-policy`, the route index and the block list

### 6.1 Tag (`libs/server/kiln_server/utils/agent_checks/policy.py`, exported from the package `__init__`)

```
MCP_POLICY_KEY = "x-mcp-policy"
DENY_MCP: dict = {MCP_POLICY_KEY: {"permission": "deny"}}

def with_mcp_deny(agent_policy: dict) -> dict        # {**agent_policy, **DENY_MCP}; inputs are not changed
def is_mcp_denied(openapi_extra: dict | None) -> bool
```

A missing key means allowed; there is no `ALLOW_MCP`. A blocked route is annotated `openapi_extra=with_mcp_deny(DENY_AGENT)` (or `with_mcp_deny(ALLOW_AGENT)`, or `with_mcp_deny(agent_policy_require_approval("…"))`): the agent policy of each route is unchanged. `dump_annotations` reads only `x-agent-policy`, so the `annotations/` folder does not change for the tag. `api_schema.d.ts` does not change (openapi-typescript drops `x-` keys). The key appears in `/openapi.json`, where the API reference pipeline reads it (spec 5.5). Add a section on the tag to `agent_checks/README.md` and one line to the "every API route needs an agent policy" item in `.agents/skills/kiln-conventions/references/server_desktop.md`.

### 6.2 Route index (`api_tool/route_index.py`)

```
@dataclass(frozen=True)
class RouteEntry:
    path: str                         # template, e.g. /api/projects/{project_id}
    methods: frozenset[str]
    regex: re.Pattern[str]            # the route's own path_regex
    mcp_blocked: bool

@dataclass(frozen=True)
class RouteMatch:
    kind: Literal["found", "wrong_method", "unknown"]
    entry: RouteEntry | None = None                  # for "found"
    path_params: Mapping[str, str] = ...             # for "found": regex groupdict
    path_methods: tuple[str, ...] = ()               # for "wrong_method": sorted

class RouteIndex:
    @classmethod
    def from_app(cls, app: FastAPI) -> "RouteIndex"
    def match(self, method: str, url_path: str) -> RouteMatch
    def blocked(self) -> list[RouteEntry]
```

- `from_app`: walk `app.routes` in order; keep each `fastapi.routing.APIRoute` whose `path` is `/ping` or starts with `/api/`; store `route.path`, `frozenset(route.methods)`, `route.path_regex`, `is_mcp_denied(route.openapi_extra)`. The entries keep the route order. It reads the route objects, never `app.openapi()` (1.1 s on first call [V]).
- `match`:
  1. `decoded = urllib.parse.unquote(url_path)`. The server decodes the path once before it routes, and httpx sends percent-escapes as written [V]. Without this step `/api/jobs/event%73` would match the allowed `/api/jobs/{id}` here and the blocked `/api/jobs/events` on the server.
  2. For each entry in order: if `entry.regex.match(decoded)`: when `method in entry.methods` → return `found` with this entry; else add its methods to a set and continue.
  3. After the loop: the set is not empty → `wrong_method`; else `unknown`.
- **Static-versus-parameter overlap rule.** The first route that matches both path and method wins, exactly as in the Starlette router. Six concrete paths match two templates (for example `/api/jobs/events` and `/api/jobs/{id}`; `POST /api/jobs/wait` and `POST /api/jobs/{type}`); the static route is registered first and wins. So a block on `GET /api/jobs/events` does not block `GET /api/jobs/{id}`, and a route can never be reached through the index by a path that the server would route elsewhere. No Kiln route uses a `:path` convertor [S].
- Cost: 270 regex tests in the worst case, about 0.04 ms [V].

### 6.3 Final block list

29 operations. Everything else is allowed, including `add_code_trust` (GET and POST), `connect_local_mcp`, `edit_local_mcp`, `GET /api/settings`, `GET /api/settings/{item_id}`, the Assistant chat history routes, `GET /api/download_dataset_jsonl` and `…/download_extraction/{extraction_id}`.

| # | Method | Path | Group | Route file |
|---|---|---|---|---|
| 1 | GET | `/api/git_sync/oauth/status/{state}` | git-sync OAuth (returns a token) | `app/desktop/git_sync/git_sync_api.py` |
| 2 | POST | `/api/git_sync/oauth/start` | git-sync OAuth | same |
| 3 | GET | `/api/git_sync/oauth/callback` | git-sync OAuth | same |
| 4 | GET | `/api/git_sync/oauth/authorize` | git-sync OAuth | same |
| 5 | POST | `/api/git_sync/test_access` | git-sync setup | same |
| 6 | POST | `/api/git_sync/list_branches` | git-sync setup | same |
| 7 | POST | `/api/git_sync/clone` | git-sync setup | same |
| 8 | POST | `/api/git_sync/test_write_access` | git-sync setup | same |
| 9 | POST | `/api/git_sync/scan_projects` | git-sync setup | same |
| 10 | POST | `/api/git_sync/rename_clone` | git-sync setup | same |
| 11 | POST | `/api/git_sync/save_config` | git-sync setup | same |
| 12 | GET | `/api/git_sync/config/{project_id}` | git-sync setup (see Open items) | same |
| 13 | PATCH | `/api/git_sync/config/{project_id}` | git-sync setup | same |
| 14 | DELETE | `/api/git_sync/config/{project_id}` | git-sync setup | same |
| 15 | GET | `/api/select_kiln_file` | native file dialog | `app/desktop/studio_server/import_api.py` |
| 16 | POST | `/api/chat` | Assistant protocol | `app/desktop/studio_server/chat/routes.py` |
| 17 | POST | `/api/chat/execute-tools` | Assistant protocol | same |
| 18 | GET | `/api/jobs/events` | endless stream (`ALLOW_AGENT` today) | `app/desktop/studio_server/jobs/api.py` |
| 19 | POST | `/api/provider/create_kiln_copilot_api_key` | browser sign-in step | `app/desktop/studio_server/provider_api.py` |
| 20 | POST | `/api/settings` | raw config write | `app/desktop/studio_server/settings_api.py` |
| 21 | POST | `/api/open_logs` | open in the OS (approval policy today) | same |
| 22 | POST | `/api/open_project_folder/{project_id}` | open in the OS | same |
| 23 | POST | `/api/projects/{project_id}/documents/{document_id}/open_enclosing_folder` | open in the OS | `libs/server/kiln_server/document_api.py` |
| 24 | POST | `/api/projects/{project_id}/skills/{skill_id}/open_enclosing_folder` | open in the OS | `app/desktop/studio_server/skill_api.py` |
| 25 | GET | `/api/projects/{project_id}/documents/{document_id}/download` | binary document download | `libs/server/kiln_server/document_api.py` |
| 26 | POST | `/api/provider/connect_api_key` | provider key | `app/desktop/studio_server/provider_api.py` |
| 27 | POST | `/api/provider/disconnect_api_key` | provider key | same |
| 28 | POST | `/api/provider/openai_compatible` | provider key (see Open items) | same |
| 29 | DELETE | `/api/provider/openai_compatible` | provider key (see Open items) | same |

All 14 routes under `/api/git_sync/` are blocked; `DELETE /api/delete_project/{project_id}` in the same file is not. The four `open_folder` call sites in the source are rows 21–24 [S]. `POST /api/provider/ollama/connect` and `…/docker_model_runner/connect` take a URL, not a key, and stay allowed.

## 7. `PUT` → `POST` for the data guide

`PUT /api/projects/{project_id}/tasks/{task_id}/data_gen_guide` is the only `PUT` route [S]. Files:

- `app/desktop/studio_server/data_gen_api.py:1092`: `@app.put` → `@app.post`. `ALLOW_AGENT` stays.
- `app/desktop/studio_server/test_data_gen_api.py`: nine `client.put(` calls (lines 711–844) → `client.post(`.
- Web UI, `client.PUT(` → `client.POST(` in `app/web_ui/src/routes/(app)/generate/[project_id]/[task_id]/`: `data_guide/+page.svelte:125`, `data_guide/refine/+page.svelte:236`, `data_guide_setup/+page.svelte:263`, `data_guide_setup_copilot/+page.svelte:751`. No web test mocks this call [S].
- `app/web_ui/src/lib/api_schema.d.ts`: regenerate with `app/web_ui/src/lib/generate_schema.sh`.
- `libs/server/kiln_server/utils/agent_checks/annotations/`: `make annotations` adds `post_api_projects_project_id_tasks_task_id_data_gen_guide.json`. Keep the `put_…` file: the folder keeps annotations of older clients on purpose.

The same pull request holds all of it. The tool's method list stays `GET, POST, PATCH, DELETE`.

## 8. Rename of the existing `kiln_mcp` server

New name in text: **Kiln project tools MCP server**. The command `kiln_mcp` and the module path stay. Each README and the `--help` description say what it is ("serves one Kiln project's tools to other apps over MCP") and what it is not ("it is not the way to connect a coding agent to Kiln; for that, use the MCP server built into the Kiln app at `http://localhost:8757/mcp`").

- `libs/server/kiln_server/mcp/mcp.py`: module docstring (line 1); argparse `description` (30–32).
- `libs/server/kiln_server/mcp/runtime.py`: docstring (1); `server_name = "Kiln MCP Server"` (30) → `"Kiln Project Tools"`; `instructions` (34) → `"Kiln project tools MCP server: serves the tools of one Kiln project."`.
- Docstrings of `mcp/__init__.py`, `tool_selection.py`, `mcp_server_tool_utils.py`.
- `libs/server/kiln_server/mcp/README.md`: title, lines 5 and 17, and the pasted `--help` block (46–65), regenerated from the real output (it is stale today).
- `libs/server/README.md:64-68`: heading and sentence.
- `.agents/skills/kiln-conventions/references/server_desktop.md`: the `kiln_mcp` row of the start-up table; add a row for the new server to "Where things go".

## 9. Error handling

Architecture section 4 applies. For this component:

- Refusals and failures of the tool are returned, not raised, with the texts of 4.5. The pipeline has one `except Exception` at step 6 and one at step 7; nothing else is caught.
- A non-2xx API answer is data and is passed through unchanged, in full.
- The tool never repeats a request. For a method other than GET, texts 7–9 say that the change may have happened.
- Logging: `logging.getLogger(__name__)`. Refusals at debug, text 10 with `logger.exception`, a failed temp-folder check at warning. Method, path and temp-file paths may be logged; bodies and query values are not.
- Mount errors (a second `run()` on one instance, a missing `app.state.kiln_mcp_server`) are programming errors and are left to raise at start.

## 10. Test plan

No test reaches the network. The package's tests never import `app.desktop`.

**Shared fixtures.** Root `conftest.py` gets one autouse fixture that patches `kiln_mcp_server.api_tool.tmp_files.default_tmp_root` to `tmp_path / "kiln_mcp"`, so no test touches the real temp folder (the desktop tests enter the lifespan, which purges it). `app/mcp/kiln_mcp_server/conftest.py` builds a small FastAPI app: `/ping`; `GET`+`PATCH /api/items/{item_id}`; the pair `GET /api/things/special` then `GET /api/things/{thing_id}`; one route with `DENY_MCP`; a route that returns text; a finite SSE route; a slow route; a 422 route. Pipeline tests call `run_api_call` with `transport=httpx.ASGITransport(app=small_app)` (it buffers the response, which is fine for finite streams).

| Area (test file) | Cases |
|---|---|
| `test_route_index.py` | found with `path_params`; unknown; wrong method lists the path's methods; static wins over parameter; a block on the static route does not block the parameter route, and the reverse; `%73`-style escapes match as the server routes them; `%2F` splits a segment; non-`/api` routes and `Mount`s are left out; for 20 sample paths the result equals a walk of `app.routes` with `route.matches(scope)` |
| `test_policy.py` | blocked entry → not allowed with text 4; allowed entry → `ALLOWED`; `scope_for_request(None)` and with a request → `OPEN_SCOPE` |
| `test_pipeline.py` | one test per step and per text of 4.5: bad `body_limit`; each core refusal passes through unchanged; trailing slash is removed before the lookup; unknown; wrong method; blocked (and no HTTP request is made: the transport counts calls); query coercion table (bool, int, float, integral float, list, `None`, empty); 404/422 from the API returned inline with `isError` false; jq applied; jq error on GET and on POST (appended sentence); body over the limit on GET; the same body on POST is returned; limit measured after jq; a higher `body_limit` passes; non-2xx over the limit is returned; `save_to_tmpfile` result shape, `.json` and `.txt`, file content equals `body_text`; non-2xx with `save_to_tmpfile` is inline; save failure text for GET and POST; SSE summary; timeout and connect error texts; unexpected exception → text 10; result JSON is compact |
| `test_progress.py` | no update when the call ends before the interval; N updates for a slow call (`interval=0.01`); `send=None`; a failing `send` does not fail the call; cancelling the caller cancels the work task; the work's exception propagates |
| `test_tmp_files.py` | folder mode `0o700` and file mode `0o600` (POSIX only); name pattern and extension; `size_bytes`; `purge_all` removes files and leaves sub-folders; `purge_expired` removes only old files (`os.utime`); a symlinked root and a root owned by another uid (patched `os.lstat`) → `TmpFileError`; a missing folder is not an error for the purges |
| `test_addresses.py` | loopback hosts → protection on with the lists of 2.4; `0.0.0.0`, `::`, `192.168.1.5`, `kiln.lan` → protection off; `127.0.0.2` adds itself |
| `test_server.py` (package) | `serverInfo` is `kiln` + the given version; `instructions` under 4,000 characters, first 500 name `kiln_skill` and `/kiln`; `tools/list` has exactly `call_kiln_api` and `kiln_skill`; the `call_kiln_api` schema equals a snapshot and has no `outputSchema`; no prompts, no resources; building a server adds no root log handler and keeps the root level; two servers in one process both run; `POST` works, `GET`/`DELETE`/`PUT` → 405 with `Allow: POST`; `Host: evil.com` → 421 and `Origin: http://evil.com` → 403 on a loopback build, both 200 on a `0.0.0.0` build; `McpEndpoint._git_sync_no_write_lock` is true |
| `libs/server/.../agent_checks/test_policy.py` | `DENY_MCP` shape; `with_mcp_deny` keeps the agent policy and does not change its input; `is_mcp_denied` for `None`, no key, deny; `dump_annotations` output is the same with and without the key |
| `app/desktop/studio_server/test_kiln_mcp_mount.py` | on `make_app()`: route order ends `/mcp` then the web host mount; `/mcp` not in `openapi()`; `initialize` and `tools/list` through `TestClient`; `GET /mcp` → 405; `POST /mcp/` → 405 from the web host; default `TestClient` host → 421; `GitSyncMiddleware` resolves the `/mcp` endpoint to an object with the marker; `server_config()` sets `timeout_graceful_shutdown`. **End to end** (one test): start `ThreadedServer(server_config(port=<free port>, host="127.0.0.1"))` with `KILN_LOCAL_API_PORT` set to that port, connect with the SDK's `streamablehttp_client`, call `kiln_skill`, call `call_kiln_api` for `GET /ping` and `GET /api/projects`, call a blocked endpoint, and check that the server stops within 5 s |
| `app/desktop/studio_server/test_mcp_block_list.py` | `EXPECTED_MCP_BLOCKED` (the 29 rows of 6.3, as `(method, path)`) equals the set read from `make_app().routes` with `is_mcp_denied`: this fails when a block is added, lost, or its route is renamed or removed; for each row, `RouteIndex.match` on the template with each `{param}` replaced by `x` returns that entry (no earlier route shadows it); each row carries `x-mcp-policy` in `app.openapi()`; `add_code_trust`, `connect_local_mcp`, `edit_local_mcp` and `GET /api/settings` are not blocked |
| `app/desktop/test_pyinstaller_hooks.py` | `app/mcp/__init__.py` does not exist; the hook file exists; `collect_data_files("kiln_mcp_server")` is not empty once the skill tree is in the package |

**`TestClient` notes.** Use `TestClient(app, base_url="http://localhost:8757")` inside a `with` block. The default host `testserver` gets 421 [V]; without the lifespan the request raises `RuntimeError: Task group is not initialized` [V]. Send `Content-Type: application/json` and `Accept: application/json, text/event-stream`; the answer is an SSE body, so read the JSON-RPC message from its `data:` line. In stateless mode `tools/call` works without a prior `initialize` [V].

## 11. Open items

1. **Block list rows to confirm.** (a) Row 12, `GET /api/git_sync/config/{project_id}`: read only, returns booleans for the tokens; blocked here because the decision says "all other git-sync setup endpoints". (b) Rows 28–29, `openai_compatible` POST/DELETE: blocked here as provider key endpoints (the POST takes an `api_key`, the DELETE removes a stored one); the decision names only "connect and disconnect". (c) `download_extraction` is left allowed as text; the content type of extraction output files was not checked.
2. **Allowed hosts.** The decision says "loopback names with the port". This doc allows any port (`name:*`) plus the bare names, so a forwarded port works. Confirm, or restrict to the bound port.
3. **`body_limit` and non-2xx.** This doc applies the limit to 2xx `GET` answers only, so an API error is never replaced by "Body too long". Spec 5.6 names no status. Confirm.
4. **`timeout_graceful_shutdown=2` in the shipped app** changes quit for every request, not only MCP. The hang was shown on `ThreadedServer`, not on the Tk app. Verify quit on a real build with a tool call in flight.
5. **Agent CLIs.** Not run against this server: whether Claude Code and Codex send a `progressToken`, how each reacts to 405 on `GET /mcp`, and their tool timeouts. The 2 s interval is the binding value; the manual sanity phase confirms it.
6. **PyInstaller.** No full build was run. The first proof that the package and its data are bundled, and that `app/mcp/` does not shadow the SDK, is the `build_desktop.yml` artifact.
7. **`API_CATALOGUE_PATH`.** `references/knowledge/api_docs/api_index.md` is the working name; the skill doc owns the final one.
8. **Licence metadata** for `app/mcp/pyproject.toml`, and adding that file to the release version-bump steps (the other four members carry 1.2.1): a person decides and does both.
9. **Rename.** `serverInfo.name` of the `kiln_mcp` command changes from "Kiln MCP Server" to "Kiln Project Tools". Clients key servers by their own config name, so no break is expected; confirm it is wanted.
10. **Windows.** `local_api_base_url` avoids `0.0.0.0` as a client target; the proxy case behind `trust_env=False` was not reproduced; `%TEMP%` permissions rely on the user profile's ACL.
11. **Argument-type errors** carry the SDK's prefix and a pydantic URL (4.5). Making them exact would need untyped arguments and our own validation; not done.
