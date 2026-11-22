---
status: draft
---

# Component: MCP server and `call_kiln_api`

Covers the `app/mcp` project, the server and its mount in the desktop app, the `KilnApiCallTool` refactor, the MCP `call_kiln_api` tool, the connection-policy seam, the `x-mcp-policy` tag with the route index and block list, and the `PUT` → `POST` change (functional spec 4, 5, 13, 14, and the tool's own error texts for 11). `kiln_skill` and the skill tree are in [skill_and_content](skill_and_content.md); this doc only names their modules and hook. The rename of the old `kiln_mcp` texts is in [connect_page_and_install](connect_page_and_install.md) (section 8 below). Cross-cutting decisions and shared files are in [architecture.md](../architecture.md). Marks: **[V]** verified by running code against the repo (`mcp` 1.30.0, Python 3.13); **[S]** read in source.

## 1. The `app/mcp` project

```
app/mcp/                        NO __init__.py here, ever
  pyproject.toml
  kiln_mcp_server/
    __init__.py                 exports build_kiln_mcp_server, KilnMcpServer, MCP_PATH, default_tmp_root
    server.py                   build_kiln_mcp_server, KilnMcpServer, McpEndpoint, the logging guard
    addresses.py                is_loopback_host, transport_security_for, app_origin
    texts.py                    WHAT_KILN_IS, SERVER_INSTRUCTIONS, CALL_KILN_API_DESCRIPTION,
                                SKILL_TOOL_DESCRIPTION, PATH_DESCRIPTION (2.4)
    api_tool/                   __init__.py, and:
      tool.py                   register_call_kiln_api, ApiToolDeps, the argument schema
      pipeline.py               run_api_call (4.2), coerce_query_params, the result builders
      messages.py               every error text of 4.3, as constants and small format functions
      route_index.py, policy.py, tmp_files.py, progress.py      sections 6.2, 5, 4.5, 4.4
    skill_files.py, skill_tool.py     other doc; hook: register_skill_tool(mcp, bound_host=..., bound_port=...)
    skill_checks/               other doc; dev tooling that the server never imports
    skill/                      other doc; the skill tree, package data
    test_*.py, conftest.py      tests beside each module
```

This is the layout of [architecture.md](../architecture.md) section 2. There is no `skill_tool/` package and no `knowledge/` package.

**SDK import boundary.** `mcp.*` imports are allowed only in `server.py`, `addresses.py`, `api_tool/tool.py`, `api_tool/pipeline.py` (result types) and `skill_tool.py`. This is the one list; the other docs refer to it. The package never imports `app.desktop`, and logs with `logging.getLogger(__name__)` only (`debug_detector.yml` fails on `print(`).

**`app/mcp/pyproject.toml`.** Copy the shape of `libs/server/pyproject.toml` (hatchling, `[tool.uv] exclude-newer = "7 days"`, `[tool.hatch.metadata] requires-python = ">=3.10"`), with:

```
name = "kiln-mcp-server"    version = "1.2.1"    requires-python = ">=3.10"
dependencies = ["kiln-ai", "kiln-server", "fastapi>=0.115.4", "starlette>=1.3.1",
                "httpx>=0.27.2", "pydantic>=2.9.2", "mcp>=1.30.0,<2"]
[tool.uv.sources]  kiln-ai = { workspace = true }   kiln-server = { workspace = true }
```

No console script. No `license` field and no licence file (owner decision): the package is covered by the repository's licence files and is not published. Hatchling finds the package because the folder name equals the normalised project name.

**Wiring.**

- Root `pyproject.toml`: add `"app/mcp"` to `[tool.uv.workspace] members`, `kiln-mcp-server = { workspace = true }` to `[tool.uv.sources]`, `"kiln-mcp-server"` to `dependencies`. `app/desktop/pyproject.toml`: the same dependency and source. Run `uv lock`; `mcp` stays at 1.30.0.
- Ruff, ty and pytest use the root config only; nothing to add. Tests import as `kiln_mcp_server.test_x`.
- `app/mcp/__init__.py` must not exist. PyInstaller runs from `app/` with `--paths=.`, which is first on its module path, so a regular package `app/mcp` would shadow the `mcp` SDK in the frozen app [S]. A test guards it (section 10).
- PyInstaller data. This component owns it. New file `app/desktop/pyinstaller_hooks/hook-kiln_mcp_server.py` with `from PyInstaller.utils.hooks import collect_data_files` and `datas = collect_data_files("kiln_mcp_server")` (no `includes=` filter: every non-Python file of the package is data, and the skill tree is all of it). The hooks folder is already on the build command line (`--additional-hooks-dir`); `build_desktop_app.sh` does not change. Python modules are found by import analysis. One test guards it (section 10): the collected data files match the skill file index.
- CI: `checks.sh` needs no change for this component. `build_and_test.yml`: add a `uv build` step in `./app/mcp`. `playwright.yml`: add `app/mcp/**` to both path filters. `build_desktop.yml`: add `app/mcp/**`, `app/desktop/build_desktop_app.sh` and `app/desktop/pyinstaller_hooks/**` to the pull-request paths.

## 2. Server construction and mounting

### 2.1 `kiln_mcp_server/server.py`

```
MCP_PATH = "/mcp"
SERVER_NAME = "kiln"

def build_kiln_mcp_server(*, api_app: FastAPI, app_version: str, host: str, port: int,
                          tmp_root: Path,                                           # the temp-file folder (4.5)
                          api_transport: httpx.AsyncBaseTransport | None = None     # tests only
                          ) -> KilnMcpServer

class KilnMcpServer:
    asgi_app: McpEndpoint                                   # the endpoint of the /mcp route
    def run(self) -> AbstractAsyncContextManager[None]      # enter once, in the app lifespan

class McpEndpoint:                                          # an ASGI app; class attribute _git_sync_no_write_lock = True
    def __init__(self, inner: ASGIApp) -> None
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None
```

`build_kiln_mcp_server` does, in order:

1. `security = transport_security_for(host)` (2.3).
2. Inside the logging guard (2.3): `mcp = FastMCP(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS, stateless_http=True, json_response=False, log_level="WARNING", transport_security=security)`. The request body limit stays at the SDK default of 4 MiB.
3. `mcp._mcp_server.version = app_version` [V]. FastMCP 1.30 has no public argument for it. This is the only private SDK attribute used.
4. Build `RouteIndex.from_app(api_app)`, `ConnectionPolicy()`, `TmpFileStore(tmp_root)` and `local_api_base_url(host, port)` (section 3).
5. `register_skill_tool(mcp, bound_host=host, bound_port=port)`, then `register_call_kiln_api(mcp, ApiToolDeps(...))`. Exactly two tools. No prompt and no resource is registered.
6. Start check: `skill_files.get_index()`. A package with no `SKILL.md` raises `RuntimeError` here (the text is in the skill doc, 2.1), so a broken bundle fails when the app starts, not at an agent's first call.
7. `mcp.streamable_http_app()`, result discarded: it creates `mcp.session_manager` [S].
8. `asgi_app = McpEndpoint(StreamableHTTPASGIApp(mcp.session_manager))` (class from `mcp.server.fastmcp.server`).

A new server is built on every call and nothing is built at import time: `session_manager.run()` works once per instance, and `make_app()` runs many times per process in tests.

**Build steps.** In build step 1 (architecture section 6) the server registers only `kiln_skill`, and `skill/` holds a placeholder tree: one minimal hand-written `SKILL.md`, which satisfies the start check and is replaced in the content phase. Step 2 adds `register_call_kiln_api` and its dependencies (step 4 of this list and the second call of step 5).

`McpEndpoint.__call__`: for an `http` scope whose method is not `POST`, answer `Response(status_code=405, headers={"Allow": "POST"})`; otherwise call `inner` [V: GET, DELETE, PUT → 405]. Stateless mode has no server stream, and without this `GET /mcp` holds an empty SSE stream open for ever [V]. CORS preflights do not reach it; `CORSMiddleware` answers them.

`KilnMcpServer.run()`: `await asyncio.to_thread(tmp_files.purge_all)`; start a task that calls `to_thread(tmp_files.purge_expired)` every 3600 s; `async with mcp.session_manager.run(): yield`; cancel the task in `finally`.

### 2.2 Desktop wiring

New file `app/desktop/studio_server/kiln_mcp_mount.py`:

```
from kiln_mcp_server import MCP_PATH, build_kiln_mcp_server, default_tmp_root

def connect_kiln_mcp_server(app: FastAPI, *, host: str, port: int) -> None:
    server = build_kiln_mcp_server(api_app=app, app_version=__version__,      # studio_server/_version.py
                                   host=host, port=port, tmp_root=default_tmp_root())
    app.state.kiln_mcp_server = server
    app.add_route(MCP_PATH, server.asgi_app, include_in_schema=False)
```

`host` and `port` are arguments: the function does not read `Config.shared()`. There is one source for them, the values that `server_config(port, host)` already holds. `default_tmp_root` is looked up as a name of this module, so that the desktop tests can patch it (section 10).

Changes in `app/desktop/desktop_server.py`. Another component edits the same functions; the combined result is in [architecture.md](../architecture.md) section 9.1.

- `make_app(tk_root=None, *, host: str | None = None, port: int | None = None)`: two new keyword arguments. `server_config(port, host, tk_root)` passes its own: `make_app(tk_root=tk_root, host=host, port=port)`. When one is `None` (the dev app and most tests call `make_app()` bare), `make_app` takes `Config.shared().kiln_local_api_host` and `kiln_local_api_port`, which are the values the dev server binds to.
- `make_app()`: call `connect_kiln_mcp_server(app, host=..., port=...)` after `connect_jobs_api(app)` and immediately before `connect_webhost(app)`. It must be the last `connect_*` before the web host, because the route index is built from `app.routes` at that moment and must see every route.
- `lifespan()`: replace the bare `yield` with `async with app.state.kiln_mcp_server.run(): yield`, still inside the `try`, after `await _start_background_syncs()`. This component adds nothing to the `finally` block.
- `server_config()`: add `timeout_graceful_shutdown=2` to `uvicorn.Config(...)`. uvicorn waits for open connections before it runs lifespan shutdown; with no bound, one in-flight tool call blocks quit [V, on `ThreadedServer`]. After 2 s uvicorn cancels the request tasks, and the cancelled tool handler cancels its REST call (4.4). The bound applies to every request of the shipped app, not only to the MCP. This is a decision; quitting with a call in flight is verified on a real build (Open items).

`dev_server.py` and `dev_app.py` do not change: the dev server uses the same `make_app()` and lifespan, and already sets `timeout_graceful_shutdown=1`. The library server (`kiln_server.server`) does not get the MCP.

Verified for this shape on the real desktop app [V]: the routes end `…, Route /mcp, Mount ""`; `POST /mcp` → 200 `text/event-stream`; `/mcp` is not in `app.openapi()`; `POST /mcp/` → 405 and `GET /mcp/` → 404 from the web host; no response is a 401, so no client starts OAuth. If ty rejects the ASGI object against the annotation of `add_route`, append `starlette.routing.Route(MCP_PATH, endpoint=server.asgi_app, include_in_schema=False)` to `app.router.routes`; that is what `add_route` does.

### 2.3 Transport security, git sync, logging

`addresses.py`: `is_loopback_host(host: str) -> bool` (`localhost`, or an IP literal whose `.is_loopback` is true; brackets stripped), `transport_security_for(host: str) -> TransportSecuritySettings`, and `app_origin(host: str, port: int) -> str`.

- **Loopback bind**: `enable_dns_rebinding_protection=True`. Names are `127.0.0.1`, `localhost`, `[::1]`, plus the bound host when it is another loopback address. `allowed_hosts` = each name and `name:*`; `allowed_origins` = `http://name` and `http://name:*`. A request with no `Origin` passes (every CLI agent). The bare names cover port 80; `:*` keeps a forwarded port working (`ssh -L 9000:localhost:8757`), and the port adds nothing against rebinding [V: `evil.com` → 421, `localhost` and `localhost:9000` → 200, `Origin: http://evil.com` → 403]. Any port is a decision (architecture section 3, item 12).
- **`app_origin`**: the address of the app as users see it, for the links in the skill (architecture section 3, item 11). It uses only the bound host and port; no request data, and never the Host header. Brackets are stripped from `host` first. An empty host, a wildcard (`0.0.0.0`, `::`) or a loopback host (`is_loopback_host`) gives `http://localhost:{port}`. Any other host gives `http://{host}:{port}`, with an IPv6 literal in brackets. The port is always written. `register_skill_tool` calls it once. It is not `local_api_base_url` (section 3), which is the target of the tool's own HTTP calls.
- **Any other bind** (`0.0.0.0`, `::`, a LAN address, a host name): `TransportSecuritySettings(enable_dns_rebinding_protection=False)`. The REST API on the same port has no Host or Origin check, and the MCP follows it. FastMCP's default must not be relied on: it answers 421 to every remote client [V].
- **Git sync**: `GitSyncMiddleware` reads `_git_sync_no_write_lock` from the endpoint of the matched route, which is the `McpEndpoint` instance. `/mcp` then takes the raw ASGI branch: no `BaseHTTPMiddleware` task, no dev-mode dirty sweep, no write lock [S]. Writes still sync, because the tool's REST calls pass through the middleware as normal `/api/projects/...` requests.
- **Logging guard**: `FastMCP.__init__` calls `logging.basicConfig` with a Rich handler [V]. The shipped app is not affected (uvicorn's `dictConfig` runs later), but the dev server and every test are. `server.py` builds FastMCP inside a context manager `_preserve_root_logging()` that records the root logger's handlers and level, and on exit removes every handler that was added and restores the level [V].

### 2.4 Identity, instructions and `texts.py`

`serverInfo` is `kiln` plus the app version.

`texts.py` is the one module for the texts that an agent sees before it has read the skill. It has no import and holds five constants: `WHAT_KILN_IS`, `SERVER_INSTRUCTIONS`, `CALL_KILN_API_DESCRIPTION` (4.1), and `SKILL_TOOL_DESCRIPTION` and `PATH_DESCRIPTION` (their texts are in the skill doc, 2.2). `server.py`, `api_tool/tool.py` and `skill_tool.py` import from it. Error texts are not here: they stay in `api_tool/messages.py` and `skill_files.py`.

```
WHAT_KILN_IS = "Kiln is an app for building, evaluating and optimizing AI agents"
```

`WHAT_KILN_IS` is the shared opening. `SERVER_INSTRUCTIONS` starts with it, and `SKILL_TOOL_DESCRIPTION` contains it followed by a full stop; both are built from the constant, and `test_texts.py` ties them (section 10). It is also the first sentence of the stub skill's description (functional spec 9.2).

The draft of `SERVER_INSTRUCTIONS` is below. Batch 14 of the content phase (skill doc, section 9) tunes the wording of all five texts. The first paragraph is 396 characters and stands alone; the whole text is about 1,100.

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

### 2.5 Concurrency and shutdown

- Each POST gets its own server task on the uvicorn loop. There is no session and no per-client state. The shared objects are `RouteIndex` (immutable after build), `ConnectionPolicy` (no state) and `TmpFileStore` (unique names, `O_EXCL`). No lock, and no cap on parallel calls.
- Each call builds its own `KilnApiCallTool` and `httpx.AsyncClient`, as the Assistant does. The self-call is one more request on the same server; it works from inside a tool handler, also when Kiln is bound to `0.0.0.0` and called at `127.0.0.1` [V: `GET /ping`, `GET /api/projects`].
- A dropped client connection cancels the tool handler at once [V]. In stateless mode a `notifications/cancelled` message cannot reach the handler [S]. Shutdown is bounded by 2.2; leaving `session_manager.run()` cancels what is left.

## 3. `KilnApiCallTool` refactor (`libs/core`, option A)

File `libs/core/kiln_ai/tools/built_in_tools/kiln_api_call_tool.py`; new names are exported from `built_in_tools/__init__.py`.

```
@dataclass(frozen=True)
class PreparedApiRequest:      method: str; url_path: str; body_str: str | None
def prepare_api_request(method: str, url_path: str, body: str | dict | list | None = None) -> PreparedApiRequest

@dataclass(frozen=True)
class KilnApiResponse:
    status_code: int; content_type: str; is_sse: bool      # content_type is lower case, "" when absent
    body_text: str             # the text after jq; else the raw text; for SSE the summary JSON
    body: Any                  # json.loads(body_text) when that works, else body_text
    body_is_json: bool
class KilnApiResponseError(ValueError):     status_code: int     # raised after the response arrived

class KilnApiCallTool(KilnTool):
    def __init__(self, api_base_url: str, transport: httpx.AsyncBaseTransport | None = None)
    async def call(self, *, method: str, url_path: str, body: str | dict | list | None = None,
                   query_params: Mapping[str, str | list[str]] | None = None,
                   jq_filter: str | None = None) -> KilnApiResponse
    async def run(...) -> ToolCallResult                          # signature unchanged
```

- `prepare_api_request` is today's validation step as a pure function. It raises `ValueError` with today's texts. Check order: method (upper-cased) → starts with `/` → **strip the trailing slash** (`url_path.rstrip("/")`, used when not empty) → allowed path → `?`/`#` → body on GET/DELETE. The "near miss on an exact path" branch of `_disallowed_path_message` becomes dead code and is removed.
- `call()` = `prepare_api_request` + today's request, SSE drain and jq-on-2xx steps. It builds `httpx.AsyncClient(transport=self._transport, trust_env=False)`: this is a loopback self-call and must not go to a proxy from the environment. The two post-response failures (`Response is not valid JSON: …`, `jq filter error: …`) raise `KilnApiResponseError` with the same text.
- `run()` = `r = await self.call(...)`, then `ToolCallResult(output=json.dumps({"status_code": r.status_code, "body": r.body}, ensure_ascii=False))`.
- **Base URL.** New function `local_api_base_url(host: str, port: int) -> str` in `libs/core/kiln_ai/utils/config.py`: `""` and `0.0.0.0` → `127.0.0.1`; `::` → `::1`; brackets stripped, then an address that contains `:` is written in brackets; returns `http://{host}:{port}`. `Config.kiln_local_api_base_url()` calls it, so the Assistant gets the fix (today: `http://0.0.0.0:8757`, and an invalid URL for `::1` [S]). The MCP package calls it with the host and port it was given. `::` gives `[::1]`, not `127.0.0.1`, because an IPv6-only socket does not accept IPv4 (architecture section 3, item 13).
- **Byte-identical for the Assistant**: the tool name, description and parameters schema (no `body_limit`, no `save_to_tmpfile`); the `run()` output string for every response; every error text, except that a path with a trailing slash is now named without it. **Changed on purpose**, three things and no more (spec 5.1, 5.3; architecture section 3, item 14): a trailing slash is removed, so `/ping/` and `/api/projects/` work; proxy settings from the environment are ignored (`trust_env=False`); the base URL is right for wildcard and IPv6 hosts.
- **Not in the core tool.** The route match (unknown endpoint, wrong method) and the `query_params` coercion of 4.2 stay in the MCP pipeline (architecture section 3, item 15).

Test changes (`test_kiln_api_call_tool.py`, `utils/test_config.py`):

- `test_near_miss_on_an_exact_path_is_corrected_to_that_path` (`/ping/`, `/ping//`) becomes a success test. Every existing assertion on `json.loads(result.output)` stays as it is.
- New: the fields of `call()` for a JSON body, a text body, an SSE stream, a jq filter with several outputs (`body_is_json` false) and a non-2xx with a jq filter (not applied); `/api/projects/` reaches `/api/projects`; `/api/` and `/` are still refused; `KilnApiResponseError.status_code`; the injected `transport` is used; the client is built with `trust_env=False`; the cases of `prepare_api_request`; a snapshot of the description and schema.
- `local_api_base_url` for `127.0.0.1`, `localhost`, `0.0.0.0`, `""`, `::`, `::1`, `[::1]`, `192.168.1.5`.

## 4. The MCP `call_kiln_api` tool

### 4.1 Registration and arguments (`api_tool/tool.py`)

`ApiToolDeps` is a frozen dataclass: `api_base_url: str`, `route_index: RouteIndex`, `policy: ConnectionPolicy`, `tmp_files: TmpFileStore`, `transport: httpx.AsyncBaseTransport | None = None`, `progress_interval: float = 2.0`.

`register_call_kiln_api(mcp: FastMCP, deps: ApiToolDeps) -> None` registers one function with `@mcp.tool(name="call_kiln_api", description=CALL_KILN_API_DESCRIPTION, structured_output=False)`, annotated `-> CallToolResult`, so there is no `outputSchema` and no duplicate `structuredContent` [V]. The function only passes its arguments, `ctx.request_context.request` and `ctx.report_progress` to `run_api_call`. Each argument is `Annotated[<type>, Field(description=...)]`, with `QueryValue = str | int | float | bool`:

| Argument | Type and default | Description text |
|---|---|---|
| `method` | `str`, with `json_schema_extra={"enum": ["GET","POST","PATCH","DELETE"]}` | HTTP method: GET, POST, PATCH or DELETE. |
| `url_path` | `str` | API path, for example `/api/projects`. No query string: pass query arguments in `query_params`. Correct paths are in the endpoint docs. |
| `body` | `dict[str, Any] \| list[Any] \| str \| None = None` | JSON request body for POST and PATCH: an object, an array, or a string that holds JSON. Not allowed with GET or DELETE. The schema is in the endpoint doc. |
| `query_params` | `dict[str, QueryValue \| None \| list[QueryValue]] \| None = None` | Query parameters as an object. Values are strings, numbers or booleans. A list repeats the key (`?ids=a&ids=b`). |
| `jq_filter` | `str \| None = None` | Optional jq expression applied to a successful (2xx) JSON response before it is returned or saved. |
| `body_limit` | `int = 30000` | Longest body, in characters, that a GET may return. Pass a higher number only when you need the whole body in your context. |
| `save_to_tmpfile` | `bool = False` | When true, the body of a successful response is written to a temporary file on the machine that runs Kiln. The result then holds `status_code`, `body_path` and `size_bytes`, and no `body`. Use the file with shell tools such as jq or grep. An error response is still returned inline. |

With these types the schema shows the enum, a lower-case `get` is accepted, numbers and booleans are accepted in `query_params`, `"50000"` is accepted for `body_limit`, and unknown arguments are ignored [V].

`CALL_KILN_API_DESCRIPTION` (in `texts.py`; draft, tuned in batch 14 of the content phase; MCP only, the Assistant keeps its own text):

```
Call the Kiln REST API. Makes one HTTP request to the running Kiln app and returns JSON with `status_code` and `body`.

Call `kiln_skill` first. Endpoint paths, request bodies, response fields and useful jq filters are in the skill's API reference, one doc per endpoint, not here. Read the endpoint's doc before you call it. Do not guess paths.

A non-2xx answer from the API is returned as data (`status_code` and the API's error body), not as a tool failure. Read it and act on it.

Large responses: a GET whose body is longer than `body_limit` characters returns an error and no body. Narrow the request with `jq_filter`, paging or filter parameters, or set `save_to_tmpfile` to get a file path in place of the body.

Streaming endpoints (text/event-stream): the tool reads the stream to its end and returns body = {"event_count": N, "message": "..."}. The end of the stream does not mean the job succeeded: check its status afterwards. A call can run for minutes.
```

### 4.2 Pipeline (`api_tool/pipeline.py`)

```
ProgressSender = Callable[[float, float | None, str | None], Awaitable[None]]

async def run_api_call(deps: ApiToolDeps, request: Request | None, send_progress: ProgressSender | None, *,
                       method: str, url_path: str, body: dict | list | str | None, query_params: Mapping | None,
                       jq_filter: str | None, body_limit: int, save_to_tmpfile: bool) -> CallToolResult
```

"E(n)" means: return the error result with text n of 4.3.

1. **`body_limit`** `< 1` → E(6).
2. **Normalise.** `prepared = prepare_api_request(method, url_path, body)`. `ValueError` → E(1).
3. **Route match.** `match = deps.route_index.match(prepared.method, prepared.url_path)`. `unknown` → E(2); `wrong_method` → E(3).
4. **Query parameters.** `params = coerce_query_params(query_params)`: a `None` value drops the key; `bool` → `"true"`/`"false"` (tested before `int`); `int` → `str(v)`; `float` → `str(int(v))` when `v.is_integer()`, else `repr(v)`; `str` kept; a list → each item by the same rules. An empty result → `None`.
5. **Policy.** `scope = deps.policy.scope_for_request(request)`, then `deps.policy.check(ApiCall(prepared.method, prepared.url_path, match.entry, match.path_params, params, prepared.body_str), scope)`. Not allowed → error result with `decision.message` (text 4 in this project).
6. **HTTP call with progress.** `resp = await run_with_progress(KilnApiCallTool(deps.api_base_url, deps.transport).call(method=prepared.method, url_path=prepared.url_path, body=prepared.body_str, query_params=params, jq_filter=jq_filter), send_progress, label=f"{prepared.method} {prepared.url_path}", interval=deps.progress_interval)`. jq runs inside `call()`, on 2xx only. `TimeoutError` or `ConnectionError` → E(7). `KilnApiResponseError` → E(8). Any other `Exception` → `logger.exception`, E(10). `CancelledError` is not caught.
7. **Shape**, in `asyncio.to_thread` (it serialises and may write a file). `body_json = json.dumps(resp.body, ensure_ascii=False, separators=(",", ":"))`. Then the first rule that applies:
   - not 2xx → inline result. Never saved and never limited: the agent needs the API's error. So `body_limit` applies to a 2xx `GET` only (a decision: functional spec 5.6 names no status).
   - `save_to_tmpfile` → `deps.tmp_files.save(resp.body_text, resp.body_is_json)` → saved result. `TmpFileError` or `OSError` → E(9). `body_limit` is not applied.
   - method `GET` and `len(body_json) > body_limit` → E(5).
   - otherwise → inline result.

### 4.3 Results and error texts

A result is one `TextContent`. JSON is compact, with `ensure_ascii=False`.

| Case | `isError` | Text |
|---|---|---|
| Inline | false | `{"status_code":200,"body":<body_json>}` |
| Saved | false | `{"status_code":200,"body_path":"/tmp/kiln_mcp/kiln_api_20261120_101500_3fa9c2d1.json","size_bytes":48213}` |
| Refusal or failure | true | the plain text below, with no JSON wrapper |

Every error is returned as `CallToolResult(content=[TextContent(type="text", text=...)], isError=True)`, never raised: a raised exception gets the SDK prefix `Error executing tool call_kiln_api: ` [V]. In the table, `{M}` is the method, `{P}` the normalised path, `{T}` the route template, and `{CAT}` is `references/knowledge/api_docs/api_index.md`. That name is final. `messages.py` takes it from the constant `API_CATALOGUE_INDEX_PATH`, which `skill_files.py` defines (skill doc, 2.3); a test there checks that the path exists in the shipped tree.

| # | When | Exact text |
|---|---|---|
| 1 | `prepare_api_request` refuses | The core text, unchanged: `Invalid method '{M}'. Must be one of: DELETE, GET, PATCH, POST` / `url_path must start with '/', got: {P}` / the two texts of `_disallowed_path_message` / `url_path must not contain a query string or fragment ('?' or '#'). Pass query args via query_params.` / `body parameter not allowed with {M} method` |
| 2 | No route matches the path | `No Kiln API endpoint matches {M} {P}. Do not guess paths. Read the API catalogues in the Kiln skill ({CAT}) to find the endpoint, then read its doc before you call it.` |
| 3 | The path exists, the method does not | `{M} is not supported on {P}. This path supports: {methods, sorted, comma separated}. Read the endpoint's doc in the Kiln skill's API catalogues ({CAT}).` |
| 4 | MCP block tag | `The endpoint {M} {T} is not available to agents over MCP. Do not retry it and do not look for another way to call it. If the user needs this, ask them to do it in the Kiln app.` |
| 5 | Body over the limit (spec 5.6) | ``Body too long. Length {len(body_json)} on limit {body_limit}. Either narrow your request (a `jq_filter`, paging or filter parameters), save it to a file with `save_to_tmpfile`, or call again passing a `body_limit` higher than {len(body_json)}.`` |
| 6 | Bad `body_limit` | `body_limit must be a positive integer. Got: {body_limit}.` |
| 7 | Timeout, or no connection | The core text (`Request to {P} timed out after 900.0s`, or `30.0s` for connect; `Could not connect to server for {P}`). For a method other than GET, append ` The {M} may have taken effect. Check the state before you repeat it.` |
| 8 | Response not JSON, or jq failed | The core text. For a method other than GET, append ` The {M} request itself completed with status {status_code}. Do not repeat it.` |
| 9 | The temp file could not be written | `Could not save the response to a temporary file: {reason}. The request completed with status {status_code}.` then ` Call again without save_to_tmpfile.` for GET, or ` Do not repeat the {M}.` for another method |
| 10 | Unexpected exception | `Unexpected error in call_kiln_api: {ExceptionType}: {message}` |
| — | An argument has the wrong type or is missing | The SDK's text: `Error executing tool call_kiln_api: N validation error(s) for call_kiln_apiArguments …`. Not under our control. Accepted: exact texts would need untyped arguments and our own validation. |
| — | The MCP request is over 4 MiB | HTTP 413 from the transport, before the tool runs. |

### 4.4 Progress (`api_tool/progress.py`)

```
async def run_with_progress(work: Coroutine[Any, Any, T], send: ProgressSender | None, *,
                            label: str, interval: float = 2.0) -> T:
    task = asyncio.ensure_future(work); ticks = 0
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=interval)
            if done: return task.result()
            ticks += 1
            if send is not None:
                try: await send(float(ticks), None, f"{label}: still running, {int(ticks * interval)} s")
                except Exception: send = None        # log at debug; keep waiting for the call
    finally:
        if not task.done(): task.cancel()            # the handler was cancelled: client gone, or shutdown
```

- The interval is 2 s and the first update comes 2 s after the call starts. 2 s is the design value: it is below the shortest known default tool timeout of the supported agents. The real agents cannot be run in this environment, so the value is confirmed in the manual sanity phase (build step 10), not before (functional spec 5.8). It is one field, `ApiToolDeps.progress_interval`. `asyncio.wait` is used because `asyncio.timeout` and `TaskGroup` do not exist on Python 3.10.
- `Context.report_progress` does nothing when the client sent no `progressToken` [V]. With a token, the updates reach the client in stateless SSE mode through the real middleware stack [V]. The SSE response also carries a `: ping` comment every 15 s (`sse_starlette`); it keeps the connection open but does not reset an MCP tool timeout.

### 4.5 Temp files (`api_tool/tmp_files.py`)

```
def default_tmp_root() -> Path                    # Path(tempfile.gettempdir()) / "kiln_mcp"
class SavedFile:     path: Path; size_bytes: int  # frozen dataclass
class TmpFileError(Exception): ...
class TmpFileStore:
    def __init__(self, root: Path, max_age_seconds: float = 24 * 3600)
    def save(self, text: str, is_json: bool) -> SavedFile
    def purge_all(self) -> None;  def purge_expired(self) -> None
```

- `root` is a required constructor argument. The store never calls `default_tmp_root()` itself and reads no global. The desktop passes the real folder (`connect_kiln_mcp_server`, 2.2); every test passes a folder under `tmp_path` (section 10). So no test can purge the real temp folder, and no fixture has to patch this package.
- **Folder**: `os.mkdir(root, 0o700)`. If it exists it must be a real folder, not a symlink, owned by the current user (`os.lstat(root).st_uid == os.getuid()`, where `os.getuid` exists); then `os.chmod(root, 0o700)`. Otherwise raise `TmpFileError("{root} exists but is not a folder owned by the current user")`. There is no fallback folder.
- **Name**: `kiln_api_<YYYYMMDD>_<HHMMSS>_<secrets.token_hex(4)>` in UTC, plus `.json` when `is_json`, else `.txt`.
- **Write**: `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)`, then the bytes of `text.encode("utf-8")`. The text is written as received, with no re-serialising. `size_bytes` is the byte count.
- **Cleanup**: `purge_all` (at start) unlinks every regular file directly in the folder. `purge_expired` (hourly) does the same for files whose `st_mtime` is older than the limit. Both use `os.scandir` with `follow_symlinks=False`, never recurse, skip a file that cannot be removed, and return quietly (one warning in the log) when the folder is missing or fails the ownership check.
- **Windows**: `tempfile.gettempdir()` is the per-user `%TEMP%`. Mode bits are ignored there; the ACL of the user profile gives the protection, and there is no owner check. A file that another program holds open cannot be removed; the next sweep tries again.
- Decision: files are removed at start (`purge_all`) and by an hourly sweep (`purge_expired`). Two Kiln processes on one machine (the app and a dev server) share the folder, so the start of one removes the files of the other. Accepted: it is rare.

## 5. Connection-policy seam (`api_tool/policy.py`)

```
# three frozen dataclasses
class ConnectionScope:      kind: Literal["open"] = "open"       # spec two adds scoped kinds and their data
class ApiCall:
    method: str; url_path: str                                   # normalised method and concrete path
    route: RouteEntry; path_params: Mapping[str, str]
    query_params: Mapping[str, str | list[str]] | None; body: str | None
class PolicyDecision:       allowed: bool; message: str | None = None     # the error text when not allowed
OPEN_SCOPE = ConnectionScope();  ALLOWED = PolicyDecision(True)

class ConnectionPolicy:
    def scope_for_request(self, request: Request | None) -> ConnectionScope     # here: always OPEN_SCOPE
    def check(self, call: ApiCall, scope: ConnectionScope) -> PolicyDecision
```

In this project `check` returns `PolicyDecision(False, <text 4>)` when `call.route.mcp_blocked`, else `ALLOWED`. It is the only place that decides "is this call allowed on this connection", and `run_api_call` asks it before every REST call (step 5). Spec two reads a token from `request.path_params` in `scope_for_request` and adds rules in `check`; `ApiCall` already carries what a scope rule needs (path parameters, query, body), so neither signature nor the pipeline changes. A call that matches no route never reaches the policy: step 3 refuses it.

## 6. `x-mcp-policy`, the route index and the block list

### 6.1 Tag

In `libs/server/kiln_server/utils/agent_checks/policy.py`, exported from the package `__init__`:

```
MCP_POLICY_KEY = "x-mcp-policy"
DENY_MCP: dict = {MCP_POLICY_KEY: {"permission": "deny"}}
def with_mcp_deny(agent_policy: dict) -> dict          # {**agent_policy, **DENY_MCP}; the input is not changed
def is_mcp_denied(openapi_extra: dict | None) -> bool
```

A missing key means allowed; there is no `ALLOW_MCP`. A blocked route is annotated `openapi_extra=with_mcp_deny(DENY_AGENT)`, or `with_mcp_deny(ALLOW_AGENT)` (row 18), or `with_mcp_deny(agent_policy_require_approval("…"))` (row 21). The agent policy of each route does not change. `dump_annotations` reads only `x-agent-policy`, so the `annotations/` folder does not change for the tag, and `api_schema.d.ts` does not change (openapi-typescript drops `x-` keys). The key does appear in `/openapi.json`, where the API reference pipeline reads it (spec 5.5). Add a section on the tag to `agent_checks/README.md`, and one sentence to the "every API route needs an agent policy" item of `.agents/skills/kiln-conventions/references/server_desktop.md`.

### 6.2 Route index (`api_tool/route_index.py`)

```
# two frozen dataclasses
class RouteEntry:     path: str; methods: frozenset[str]; regex: re.Pattern[str]; mcp_blocked: bool
class RouteMatch:
    kind: Literal["found", "wrong_method", "unknown"]
    entry: RouteEntry | None = None                  # "found"
    path_params: Mapping[str, str] = {}              # "found": the regex groupdict (use a field default factory)
    path_methods: tuple[str, ...] = ()               # "wrong_method": sorted
class RouteIndex:
    @classmethod
    def from_app(cls, app: FastAPI) -> "RouteIndex"
    def match(self, method: str, url_path: str) -> RouteMatch
```

- **Build.** Walk `app.routes` in order. Keep each `fastapi.routing.APIRoute` whose `path` is `/ping` or starts with `/api/`. Store the template `route.path`, `frozenset(route.methods)`, the route's own `route.path_regex`, and `is_mcp_denied(route.openapi_extra)`. The entries keep the route order. The index reads route objects, never `app.openapi()` (1.1 s on its first call [V]).
- **Match.**
  1. `decoded = urllib.parse.unquote(url_path)`. The server decodes the path once before it routes, and httpx sends percent-escapes as written. Without this step `/api/jobs/event%73` matches the allowed `/api/jobs/{id}` here but reaches the blocked `/api/jobs/events` on the server [V, on uvicorn; the same for `/api/jobs%2Fevents`].
  2. For each entry in order: when `entry.regex.match(decoded)`: if `method in entry.methods`, return `found` with this entry and the groupdict; else add the entry's methods to a set and continue.
  3. After the loop: the set is not empty → `wrong_method`; else `unknown`.
- **Static-versus-parameter overlap rule.** The first route that matches both the path and the method wins, exactly as in the Starlette router. Six concrete paths match two templates (`/api/jobs/events` and `/api/jobs/{id}`; `POST /api/jobs/wait` and `POST /api/jobs/{type}`; two under `/documents/`; two under `/api/settings/`). The static route is registered first and wins. So the block on `GET /api/jobs/events` does not block `GET /api/jobs/{id}`, and a call is never judged by a route other than the one the server will run. No Kiln route uses a `:path` convertor [S]. The worst case is 270 regex tests, about 0.04 ms [V].

### 6.3 Final block list

29 operations. Everything else is allowed, including `add_code_trust` (GET and POST), `connect_local_mcp`, `edit_local_mcp`, `GET /api/settings`, `GET /api/settings/{item_id}`, the Assistant chat-history routes, `GET /api/download_dataset_jsonl` and `…/download_extraction/{extraction_id}`. The list started from the 66 endpoints that the Kiln Assistant is denied today (functional spec 5.5). The ruling and the reason for each of them, and for the two blocked endpoints that the Assistant may call, are in [research/mcp_block_list_review.md](../research/mcp_block_list_review.md).

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
| 12–14 | GET, PATCH, DELETE | `/api/git_sync/config/{project_id}` | git-sync setup | same |
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
| 28–29 | POST, DELETE | `/api/provider/openai_compatible` | provider key | same |

Decisions in this table:

- All 14 routes under `/api/git_sync/` are blocked, row 12 included. Row 12 is a read-only GET that returns booleans for the tokens; it is blocked so that the rule is one simple rule. `DELETE /api/delete_project/{project_id}`, in the same file, is not blocked.
- Rows 28 and 29 are blocked with the other provider-key endpoints: the POST takes an `api_key` and the DELETE removes a stored one.
- `download_extraction` stays allowed, as text.
- Rows 21–24 are the four `open_folder` call sites in the source [S]. `POST /api/provider/ollama/connect` and `…/docker_model_runner/connect` take a URL, not a key, and stay allowed.

The skill must agree with this table (functional spec 7.3). For each capability here that a user might ask for, the skill says "ask the user to do this in the app" and gives the app page; the table of capabilities and pages is in the skill doc, section 4.4, and is built from these rows.

## 7. `PUT` → `POST` for the data guide

`PUT /api/projects/{project_id}/tasks/{task_id}/data_gen_guide` is the only `PUT` route [S]. One pull request changes all of:

- `app/desktop/studio_server/data_gen_api.py:1092`: `@app.put` → `@app.post`. `ALLOW_AGENT` stays.
- `app/desktop/studio_server/test_data_gen_api.py`: the nine `client.put(` calls (lines 711–844) → `client.post(`.
- Web UI, `client.PUT(` → `client.POST(`, under `app/web_ui/src/routes/(app)/generate/[project_id]/[task_id]/`: `data_guide/+page.svelte:125`, `data_guide/refine/+page.svelte:236`, `data_guide_setup/+page.svelte:263`, `data_guide_setup_copilot/+page.svelte:751`. No web test mocks this call [S].
- `app/web_ui/src/lib/api_schema.d.ts`: regenerate with `app/web_ui/src/lib/generate_schema.sh`.
- `libs/server/kiln_server/utils/agent_checks/annotations/`: `make annotations` adds `post_api_projects_project_id_tasks_task_id_data_gen_guide.json`. Keep the `put_…` file; the folder keeps the annotations of older clients on purpose.

The tool's method list stays `GET, POST, PATCH, DELETE`.

**The hosted Kiln Assistant.** The new `post_…` annotation file is how the hosted Assistant service learns the policy of the `POST` route. `make annotations` is part of this change. The hosted service picks the file up when it next updates its Kiln version; until then it knows only the `put_…` route, which no longer exists in the app. Nothing is done in the hosted service in this project (architecture section 8).

## 8. Rename of the existing `kiln_mcp` server

This component does not own the rename. [connect_page_and_install](connect_page_and_install.md) section 6 owns it: every place, the exact new strings and the line references. It is done in build step 7. Two facts matter here: the name in text becomes "Kiln project tools MCP server" (sentence case); and the protocol name of that server (`server_name` in `runtime.py`, its `serverInfo.name`) and its MCP `instructions` do not change, because functional spec 12 renames docs and `--help` text only.

## 9. Error handling

Architecture section 4 applies. For this component:

- Refusals and failures of the tool are returned with the texts of 4.3, not raised. The pipeline catches exceptions in two places only (steps 6 and 7). A non-2xx API answer is data: it is passed through unchanged and in full.
- The tool never repeats a request. For a method other than GET, texts 7 to 9 say that the change may have happened.
- Logging: refusals at debug; text 10 with `logger.exception`; a failed temp-folder check at warning. The method, the path and temp-file paths may be logged. Bodies and query values are not.
- Mount errors (a second `run()` on one instance, no `app.state.kiln_mcp_server`) are programming errors and are left to raise at start.

## 10. Test plan

No test reaches the network. The package's tests never import `app.desktop`.

**Build steps** (architecture section 6). Step 1: `test_addresses.py`, `test_texts.py`, `test_server.py` without the cases marked "step 2", `test_pyinstaller_hooks.py`, and the mount cases of `test_kiln_mcp_mount.py`. Step 2: everything else in the table, with the "exactly two tools" case and the end-to-end test.

**Fixtures.** This component adds no fixture to the root `conftest.py`: a root fixture would import `kiln_mcp_server` for every test in the repo, the `libs/core` and `libs/server` runs included. Temp-file protection is by construction: `TmpFileStore` and `build_kiln_mcp_server` take the folder as an argument, and every test of this package passes `tmp_path / "kiln_mcp"`. One fixture is still needed for the desktop tests that build the real app and enter its lifespan (the lifespan purges the folder at start). It goes in a new `app/desktop/conftest.py`: an autouse fixture `kiln_mcp_tmp_root` that does `monkeypatch.setattr("app.desktop.studio_server.kiln_mcp_mount.default_tmp_root", lambda: tmp_path / "kiln_mcp")`. `app/mcp/kiln_mcp_server/conftest.py` builds a small FastAPI app: `/ping`; `GET` and `PATCH /api/items/{item_id}`; the pair `GET /api/things/special` then `GET /api/things/{thing_id}`; one route with `DENY_MCP`; a text route; a finite SSE route; a slow route; a 422 route. Pipeline tests call `run_api_call` with `transport=httpx.ASGITransport(app=small_app)` (it buffers the response, which is fine for a finite stream).

| Test file | Cases |
|---|---|
| `api_tool/test_route_index.py` | found, with `path_params`; unknown; wrong method lists the path's methods; the static route wins over the parameter route; a block on one of the pair does not block the other, both ways; `%73` and `%2F` escapes match as the server routes them; non-`/api` routes and mounts are left out; for 20 sample paths the result equals a walk of `app.routes` with `route.matches(scope)` |
| `api_tool/test_policy.py` | a blocked entry → not allowed, with text 4; an allowed entry → `ALLOWED`; `scope_for_request` with `None` and with a request → `OPEN_SCOPE` |
| `api_tool/test_pipeline.py` | One test per step and per text of 4.3: bad `body_limit`; each core refusal passes through unchanged; the trailing slash is removed before the lookup; unknown; wrong method; blocked, and no HTTP request is made (the transport counts calls); the query coercion table (bool, int, float, integral float, list, `None`, empty); a 404 and a 422 from the API are inline with `isError` false; jq applied; a jq error on GET and on POST (appended sentence); a body over the limit on GET; the same body on POST is returned; the limit is measured after jq; a higher `body_limit` passes; a non-2xx over the limit is returned; the saved result shape, `.json` and `.txt`, and the file content equals `body_text`; non-2xx with `save_to_tmpfile` is inline; the save-failure text for GET and for POST; the SSE summary; the timeout and connect texts; an unexpected exception → text 10; the result JSON is compact |
| `api_tool/test_progress.py` | no update when the call ends before the interval; N updates for a slow call (`interval=0.01`); `send=None`; a failing `send` does not fail the call; cancelling the caller cancels the work task; the work's exception propagates |
| `api_tool/test_tmp_files.py` | Every case builds `TmpFileStore(tmp_path / "kiln_mcp")`. Folder mode `0o700` and file mode `0o600` (POSIX only); the name pattern and extension; `size_bytes`; `purge_all` removes files and leaves sub-folders; `purge_expired` removes only old files (`os.utime`); a symlinked root, and a root owned by another uid (patched `os.lstat`) → `TmpFileError`; a missing folder is not an error for the purges |
| `test_addresses.py` | loopback hosts → protection on, with the lists of 2.3; `0.0.0.0`, `::`, `192.168.1.5`, `kiln.lan` → protection off; `127.0.0.2` adds itself. `app_origin`: `127.0.0.1`, `localhost`, `::1`, `[::1]`, `0.0.0.0`, `::` and `""` with port 8757 → `http://localhost:8757`; `127.0.0.1` with 9000 → `http://localhost:9000`; `192.168.1.5` → `http://192.168.1.5:8757`; `kiln.lan` → `http://kiln.lan:8757`; `fd00::5` → `http://[fd00::5]:8757` |
| `test_texts.py` | `SERVER_INSTRUCTIONS` starts with `WHAT_KILN_IS`; `SKILL_TOOL_DESCRIPTION` contains `WHAT_KILN_IS + "."`; `WHAT_KILN_IS` equals the sentence of architecture section 3, item 16; `SERVER_INSTRUCTIONS` is under 4,000 characters and its first 500 name `kiln_skill` and `/kiln`; `SKILL_TOOL_DESCRIPTION` names `/kiln`; `texts.py` imports nothing |
| `test_server.py` | `serverInfo` is `kiln` plus the given version; `instructions` equals `SERVER_INSTRUCTIONS`; `tools/list` has `kiln_skill` (step 1), and exactly `call_kiln_api` and `kiln_skill` (step 2); the `call_kiln_api` schema equals a snapshot and has no `outputSchema` (step 2); `prompts/list` and `resources/list` are empty; a build with `skill_files.get_index` patched to raise fails with that `RuntimeError` (the start check); building a server adds no root log handler and keeps the root level; two servers in one process both run; `POST` works, and `GET`, `DELETE`, `PUT` → 405 with `Allow: POST`; `Host: evil.com` → 421 and `Origin: http://evil.com` → 403 on a loopback build, both 200 on a `0.0.0.0` build; `McpEndpoint._git_sync_no_write_lock` is true |
| `libs/server/…/agent_checks/test_policy.py` | the shape of `DENY_MCP`; `with_mcp_deny` keeps the agent policy and does not change its input; `is_mcp_denied` for `None`, no key, and deny; the output of `dump_annotations` is the same with and without the key |
| `app/desktop/studio_server/test_kiln_mcp_mount.py` | On `make_app()`: the routes end with `/mcp` then the web host mount; `/mcp` is not in `openapi()`; `initialize` and `tools/list` through `TestClient`; `GET /mcp` → 405; the default `TestClient` host → 421; `GitSyncMiddleware._resolve_endpoint` returns an object with the marker for `/mcp`; `server_config()` sets `timeout_graceful_shutdown`. Host and port: `make_app(host="0.0.0.0", port=9000)` builds a server without the Host check, and bare `make_app()` builds one for the `Config` host and port; `server_config(9000, "127.0.0.1")` passes both through; `connect_kiln_mcp_server` works with `Config.shared` patched to raise (it reads no config); the store of the built server uses the folder of the `kiln_mcp_tmp_root` fixture. **End to end**, one test (step 2): pick a free port, start `ThreadedServer(server_config(port, "127.0.0.1"))` (no environment variable is needed: host and port are passed through), connect with the SDK's `streamablehttp_client`, call `kiln_skill`, call `call_kiln_api` for `GET /ping` and `GET /api/projects`, call a blocked endpoint, and check that the server stops within 5 s |
| `app/desktop/studio_server/test_mcp_block_list.py` | `EXPECTED_MCP_BLOCKED` (the 29 rows of 6.3 as `(method, path)`) equals the set read from `make_app().routes` with `is_mcp_denied`. This fails when a block is added or lost, and when a blocked route is renamed or removed. For each row, `RouteIndex.match` on the template with each `{param}` replaced by `x` returns that entry (no earlier route shadows it). Each row carries `x-mcp-policy` in `app.openapi()`. `add_code_trust`, `connect_local_mcp`, `edit_local_mcp` and `GET /api/settings` are not blocked |
| `app/desktop/test_pyinstaller_hooks.py` (existing file; step 1) | `app/mcp/__init__.py` does not exist; the hook file exists. One data test, the only one for bundling in this project: the files that `collect_data_files("kiln_mcp_server")` returns under `kiln_mcp_server/skill/` are exactly the keys of `skill_files.get_index().files` (same relative paths, none missing, none extra). It holds for the placeholder tree of step 1 and for the full tree later |

**`TestClient` notes.** Use `TestClient(app, base_url="http://localhost:8757")` inside a `with` block. The default host `testserver` gets 421, and without the lifespan the request raises `RuntimeError: Task group is not initialized` [V]. Send `Content-Type: application/json` and `Accept: application/json, text/event-stream`. The answer is an SSE body: read the JSON-RPC message from its `data:` line. In stateless mode `tools/call` works without a prior `initialize` [V].

**One lifespan per app.** `session_manager.run()` can be entered once per server object, and `make_app()` builds one server per app. So the lifespan of one app from `make_app()` can be entered once; a second `with TestClient(app)` on the same app raises `RuntimeError` at start [V].

- Effect on the existing tests, checked in the repo: none has to change. Three modules build the desktop app. `app/desktop/studio_server/test_server.py` builds a new app in a function-scoped fixture and enters one `with TestClient(app)` per test. `app/desktop/git_sync/test_sse_invariants.py` builds the app and reads its routes, with no client. `app/desktop/test_desktop.py::test_desktop_app_server` runs one `ThreadedServer` on `server_config(...)`. No test keeps a desktop app in a module-scoped or session-scoped fixture. The git-sync integration tests and the router tests build their own `FastAPI()` (or `kiln_server.make_app`) with single `connect_*` calls; those apps have no MCP server and are not affected.
- Rule for tests: a test that enters the lifespan builds its own app with `make_app()`, in the test or in a function-scoped fixture, and enters it once. To use the app in a second `with TestClient(...)` block, build a second app. A `TestClient` used without `with` does not enter the lifespan: every route except `/mcp` works that way, as before.

## 11. Open items

To verify during implementation:

1. **Quit with a call in flight.** `timeout_graceful_shutdown=2` is decided (2.2). The hang was shown on `ThreadedServer`, not on the Tk app. Verify quit on a real build with a tool call in flight.
2. **Agent CLIs** (manual sanity phase, build step 10). Not run against this server: whether Claude Code and Codex send a `progressToken`, how each reacts to a 405 on `GET /mcp`, and their tool timeouts. The 2 s progress interval is the design value and is confirmed there (4.4).
3. **Packaged build.** No full PyInstaller build was run: the first proof that the package and its data are bundled, and that `app/mcp/` does not shadow the SDK, is the `build_desktop.yml` artifact.
4. **Windows.** `0.0.0.0` as a client target (the reason for `local_api_base_url`) and the proxy case behind `trust_env=False` were not tried.
5. **`download_extraction`.** It stays allowed as text (6.3). The content type of extraction output files was not checked; check it when the block list test is written.

Owner decisions are in [architecture.md](../architecture.md) section 11. Item 4 there concerns this component: `app/mcp/pyproject.toml` sets no licence field, carries the same version as the other workspace members (1.2.1 today), and is bumped with them at release.
