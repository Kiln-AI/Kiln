# Binding a scope to an MCP connection

Research date: 2026-11-20. SDK versions read and run: `mcp` 1.30.0 (Kiln's lock) and `mcp` 2.3.0 (latest on PyPI). Spec revisions read: 2025-11-25 and 2026-07-28 (the current one).

## Answer

Put the scope in the URL path, and resolve it again on every HTTP request. Serve the open endpoint at `/mcp` and each scope at `/mcp/s/<token>`. The token is opaque, server-minted and 256 bits. Both paths are routes to one MCP server instance, mounted on Kiln's FastAPI app. A tool handler reads the token from `ctx.request_context.request.path_params["token"]`, and looks it up in a scope store. Run the transport with `stateless_http=True` and SSE responses (`json_response=False`).

A URL path works in all three agent CLIs, and in every other client, with no header support. It does not start OAuth discovery. It fails closed: a lost or expired token gives a 404, never the open endpoint. It is also the only candidate that does not depend on MCP sessions, and the 2026-07-28 spec removes those sessions.

**Primary:** a path token, `/mcp/s/<token>`, on one instance, with `stateless_http=True`.

**Fallback:** `Authorization: Bearer <token>` on a separate path, for example `/mcp/scoped`. This path uses a second server instance with the SDK's `TokenVerifier`, and the handler reads `get_access_token()`. Use it if tokens in URLs become a problem, for example in logs or config files that get shared. Do not put the bearer check on `/mcp` itself: the SDK auth is all-or-nothing for each instance, so an unscoped client would get a 401.

The largest risk is not how the scope binds. It is the passthrough tool: `call_kiln_api` must refuse the scope-management endpoints (`/api/mcp/scopes...`) and anything else that can widen a scope. If it does not, an agent can mint a wider scope through its own lane.

## Comparison

| Candidate | Spec status | Server SDK access (1.30 / 2.3) | All 3 CLIs, no extra flags | Fails closed if token lost | Survives Kiln restart | Verdict |
|---|---|---|---|---|---|---|
| 1. URL path `/mcp/s/<token>` | Compliant. Each URL is one MCP endpoint. Stable in 2026-07-28. | `request.path_params`, in every mode. Verified. | Yes, URL only | Yes (404) | Yes, if the scope store is persisted | **Recommended** |
| 2. Query `/mcp?scope=<token>` | Not forbidden for a custom scope. The auth spec says OAuth access tokens MUST NOT go in a query string. | `request.query_params`, in every mode. Verified. | Yes (passed through as is; not tested in the real CLIs) | No: a dropped query gives the open endpoint | Same as 1 | Weaker copy of 1 |
| 3a. Custom header `X-Kiln-Scope` | Compliant. Headers are opaque to MCP. | `request.headers` or `ctx.headers` (2.x), in every mode. Verified. | Yes (`headers`, `http_headers`) | No on `/mcp`. Yes only on a separate path | Same as 1 | Use only on a separate path |
| 3b. `Authorization: Bearer` + SDK `TokenVerifier` | Uses the MCP auth model (resource-server side only). OAuth is OPTIONAL. | `get_access_token()`. Verified in every mode. Built-in session-owner check. | Yes; Codex needs `bearer_token_env_var` or `http_headers` | Yes (401) on its own path | Same as 1 | **Fallback**, on its own path |
| 4. MCP session / `initialize` | Removed in 2026-07-28. The 2025-11-25 best practices say servers MUST NOT use sessions for authentication. | Session id via headers; stateful mode only | The CLIs cannot set `clientInfo` or `initialize` params | n/a | No (sessions are in memory) | Reject |
| 5. Port per scope | Compliant | Separate app per port | Yes | Yes | Port must be re-bound | Works, but costs too much |
| 6a. Per-request `_meta` | Compliant | `ctx.request_context.meta` | No CLI lets config set `_meta` | n/a | n/a | Reject |
| 6b. Token as a tool argument | Compliant (2026-07-28 suggests server-minted handles for *state*) | Argument | Yes | No: the model chooses the arguments | n/a | Reject for authority |

## Evidence by candidate

### Facts that apply to all candidates

Spec, 2026-07-28 (current). The changelog, item 1: "Remove protocol-level sessions and the `Mcp-Session-Id` header from the Streamable HTTP transport." Item 2: "remove the `initialize`/`notifications/initialized` handshake. Every request now carries its protocol version and client capabilities in `_meta`." The transport page says "The server **MUST** provide a single HTTP endpoint path ... that supports POST". Under security, servers MUST validate `Origin` and SHOULD bind to localhost. A server that receives an old `Mcp-Session-Id` "ignore it, and do not mint or echo session IDs" (it SHOULD do this when it supports only this revision). Item 9 removes SSE resumability. A new rule requires `Mcp-Method` and `Mcp-Name` headers. A tool parameter can become a header through `x-mcp-header`, but only as `Mcp-Param-{name}`, so the model cannot write an `X-Kiln-Scope` or `Authorization` header that way.

Spec, 2025-11-25 (the handshake era, which current CLIs mostly still speak). Session ids are optional. A server answers 404 for a session it has ended, and the client then MUST re-initialize. Security best practices: "MCP Servers **MUST NOT** use sessions for authentication."

How the HTTP request reaches a tool (1.30, read in source):
- `mcp/server/streamable_http.py`. `StreamableHTTPServerTransport` wraps each incoming POST as `ServerMessageMetadata(request_context=request)`, where `request` is the Starlette `Request` of *that* POST.
- `mcp/server/lowlevel/server.py`, `Server._handle_request`. It copies that into `RequestContext(..., request=request_data)` and sets the `request_ctx` contextvar for the duration of the handler.
- So `ctx.request_context.request` in a FastMCP tool is always the current POST: its path, `path_params`, query and headers. This holds in stateful, stateless and JSON modes.
- 2.3: the same field is `ServerRequestContext.request` (`mcp/server/context.py`). `mcp/server/mcpserver/context.py` adds `Context.headers` and `Context.protocol_version`. The modern (2026-07-28) path, `mcp/server/_streamable_http_modern.py`, builds `ServerMessageMetadata(request_context=request)` too.

The contextvar trap (verified by running the code). In stateful mode, `StreamableHTTPSessionManager._serve_opening_request` starts the session's server task with `self._task_group.start(run_server)` during the `initialize` POST. The task copies the contextvars of *that* request. Every later POST in the session is only fed into the task's streams (`transport.handle_request`). So a contextvar that ASGI middleware sets on a later request is **not** visible in the tool handler; the handler sees the value from `initialize`. In stateless mode (`_handle_stateless_request`) a fresh server task starts inside each request, and in 2.x modern mode the handler runs in the ASGI task. In both of those, middleware contextvars are visible. The SDK's own `get_access_token()` is a contextvar too (`mcp/server/auth/middleware/auth_context.py`). It stays correct in stateful mode only because the session manager rejects any request whose credential differs from the one that created the session (`_session_owners`, which answers 404).

Mounting gotchas (read in source and verified):
- `FastMCP.streamable_http_app()` creates the session manager lazily. `mcp.session_manager` raises `RuntimeError` before that call.
- The returned Starlette app has `lifespan=lambda app: self.session_manager.run()`. A parent FastAPI app does not run a mounted sub-app's lifespan, so Kiln's own `lifespan` (`app/desktop/desktop_server.py`) must enter `session_manager.run()`, once for each instance.
- `run()` can be called only once per manager (`RuntimeError: ... can only be called once per instance`). Build the MCP server inside `make_app()`, not at import time, or tests and reloads that build two apps will fail.
- The inner route is an exact `Route(streamable_http_path)` with the default `/mcp`. `app.mount("/mcp", sub)` therefore serves `/mcp/mcp`. Mounting with `streamable_http_path="/"` gives `/mcp/` plus a slash redirect. The clean way is to add routes to the parent router that point at `StreamableHTTPASGIApp(session_manager)`. This class is in `mcp.server.fastmcp.server` in 1.x and in `mcp.server.streamable_http_manager` in 2.x. `/mcp/` (with a trailing slash) then gives 404, which the POC shows.
- One instance can serve several paths: two `Route`s to the same ASGI app share one manager (verified). In stateful mode they also share sessions: a session opened at `/mcp/s/tokA` was accepted at `/mcp/s/tokB` and at `/mcp` (verified, HTTP 200). `stateless_http=True` removes this, because there are no sessions.
- DNS-rebinding protection. In 1.x, `FastMCP.__init__` turns it on when `host` is `127.0.0.1`, `localhost` or `::1`, and `host` defaults to `127.0.0.1`. In 2.x the same rule is in `streamable_http_app(host=...)`. Allowed hosts are `127.0.0.1:*`, `localhost:*` and `[::1]:*`, with the matching `http://` origins. A wrong `Host` gave `421 Invalid Host header` (verified). Kiln's UI origin `http://localhost:8757` passes. This check is separate from Kiln's `CORSMiddleware`.
- Kiln-specific. `connect_webhost(app)` is a catch-all and must stay last, so add the MCP routes before it. `GitSyncMiddleware` is a `BaseHTTPMiddleware` that wraps every request. Check that it never takes the write lock or buffers on `/mcp...`; the MCP POSTs can stream for minutes (not tested).

### 1. URL path per scope (recommended)

Protocol: each URL is "the MCP endpoint" of a logical server, so this is compliant in both revisions. It does not depend on sessions, so 2026-07-28 does not affect it.

Server code (1.30; the 2.x changes are noted below):

```
# kiln mcp app factory, called from make_app()
mcp = FastMCP("kiln", stateless_http=True, json_response=False)

@mcp.tool()
async def call_kiln_api(method: str, path: str, body: dict | None = None, ctx: Context = None):
    scope = scope_for_request(ctx.request_context.request)   # one function, used by both tools
    enforce(scope, method, path, body)                       # raises a tool error
    ...

def scope_for_request(req) -> Scope:
    token = req.path_params.get("token")
    if token is None:
        return Scope.UNRESTRICTED          # plain /mcp
    scope = scope_store.get(token)         # store is keyed by sha256(token)
    if scope is None or scope.expired:
        raise ScopeGone()                  # defence in depth; the route already answered 404
    return scope

mcp.streamable_http_app()                  # creates mcp.session_manager
asgi = StreamableHTTPASGIApp(mcp.session_manager)

async def scoped(scope, receive, send):    # pure ASGI: 404 before any MCP processing
    if scope_store.get(scope["path_params"]["token"]) is None:
        await PlainTextResponse("Unknown MCP scope", status_code=404)(scope, receive, send)
        return
    await asgi(scope, receive, send)

app.router.routes.insert(0, Route("/mcp", endpoint=asgi))
app.router.routes.insert(0, Route("/mcp/s/{token}", endpoint=scoped))
# in Kiln's lifespan:  async with mcp.session_manager.run(): yield
```

Why 404 and not 401: Claude Code marks a server as needing OAuth when it gets a 401 or 403 and has no configured `Authorization` header. It then probes `/.well-known/oauth-protected-resource`, and on Kiln that probe would land on the web-host catch-all. OpenCode also starts its OAuth flow on a 401 unless `oauth: false` is set.

Stateless vs stateful:
- Stateless: the scope is re-read on every POST. No sessions cross between paths. Kiln restarts are invisible to the client, provided the scope store is persisted. Progress notifications still reach the client over the POST's SSE stream (verified). What you lose: server-to-client requests (sampling, elicitation), the GET stream (`list_changed`) and resumability. Kiln needs none of these, because the tool list is fixed.
- Stateful (if ever needed): read the scope from `path_params` per request, never from a middleware contextvar. Also record `session_id -> token` on first sight and reject a mismatch, because of the cross-path reuse shown above. The 30-minute `session_idle_timeout` (new in 1.2x) reaps idle sessions, and a Kiln restart loses all sessions, so clients get a 404 and must re-initialize.
- `json_response=True`: the scope still works (verified), but progress notifications are dropped (verified: `progress_received=[]`) and there are no SSE keep-alive pings. Do not use it for long calls.

Security:
- Token: `secrets.token_urlsafe(32)`. Store only its sha256. Give it a TTL (for example the run length plus a margin), and add `DELETE` for the tuner to call at the end of a run.
- Guessing 256 bits is not practical.
- An agent that reads its own config gets only its own token, which is harmless.
- The agent cannot make its CLI send to another URL: the URL is fixed in the launch config, and the shell has no network.
- Falling back to the open `/mcp` would need a new MCP connection, which only the CLI process can open (see "Can the model add servers" below).
- Paths are logged: uvicorn's access log prints `POST /mcp/s/<token>`. Add a log filter that redacts `/mcp/s/*`, or accept the risk: the token is local and short-lived.
- Scope store: persist it to disk (hashes, scope, expiry), or a Kiln restart breaks every live agent: the agent's URL is fixed, and its CLI cannot be given a new token mid-session.

Operational: tens of concurrent sessions are trivial. One instance and one manager serve every scope. Stateless mode creates one server task per POST, and its cost is small next to a Kiln API call. Do not build one instance per scope: each needs its own `session_manager.run()` entered in the lifespan, and you cannot add those after start-up.

### 2. Query parameter

This works in the SDK (`request.query_params`, verified in every mode). It is weaker than a path for three reasons:
- If a client or proxy drops or rewrites the query, the request lands on the open `/mcp` without an error. It fails open.
- The MCP authorization spec says "Access tokens **MUST NOT** be included in the URI query string". That rule binds only OAuth tokens under MCP auth, but reviewers will flag it.
- The token is logged in the same way as a path token.

OpenCode keeps the query (`new URL(url)` in its remote connect code). Claude Code and Codex probably keep it too (not verified in the real CLIs). No advantage over a path.

### 3. HTTP header

3a, custom header (`X-Kiln-Scope`). Read with `ctx.request_context.request.headers` (1.x and 2.x) or `ctx.headers` (2.x), verified in every mode. All three CLIs can send static headers. On the shared `/mcp` path, a missing header means unrestricted access, so a client bug or a config typo fails open. Use it only on a path that rejects requests without the header.

3b, SDK bearer auth (verified, 1.30 and 2.3). A static token works without any OAuth flow:

```
class StaticVerifier:                    # mcp.server.auth.provider.TokenVerifier protocol
    async def verify_token(self, token):
        s = scope_store.get(token)
        return AccessToken(token=token, client_id=s.id, scopes=["kiln"]) if s else None

mcp_scoped = FastMCP("kiln", token_verifier=StaticVerifier(),
                     auth=AuthSettings(issuer_url="http://127.0.0.1:8757", resource_server_url=None),
                     streamable_http_path="/mcp/scoped", stateless_http=True)
# tool: at = get_access_token(); scope = scope_store.by_id(at.client_id)
```

- `AuthSettings.issuer_url` is a required field, so give it a dummy value.
- With `resource_server_url=None`, no protected-resource metadata route is added, and the `WWW-Authenticate` header has no `resource_metadata` (verified: `401 Bearer error="invalid_token", error_description="Authentication required"`).
- `BearerAuthBackend` plus `RequireAuthMiddleware` wrap the only route of that instance. Every request without a valid token gets a 401, so this instance cannot also be the open endpoint. Run a second instance for `/mcp` (two `session_manager.run()` in the lifespan; the POC does this) and register the same tool functions on both.
- Identity reaches the tool through the `auth_context_var` contextvar, via `get_access_token()`. That is safe in every mode, because the manager's session-owner check covers stateful mode.
- Advantages: the token is not in URLs or access logs, and the SDK binds stateful sessions to the token.
- Costs: two instances; a 401 can start OAuth discovery in a client that has no `Authorization` header configured (not the case for the tuner's configs); and Codex refuses an inline `bearer_token` for HTTP servers (`throw_if_set("streamable_http", "bearer_token", ...)` in `codex-rs/config/src/mcp_types.rs`), so use `bearer_token_env_var` or `http_headers`.

### 4. MCP session / `initialize`

Reject this.
- `clientInfo` and the `initialize` params are set by the CLI, not by its config. Claude Code, Codex and OpenCode give no per-launch option for them, so the tuner cannot put a scope there.
- `Mcp-Session-Id` is minted by the server *after* the client connects, so the tuner cannot know it in advance.
- The 2025-11-25 best practices forbid using sessions for authentication.
- 2026-07-28 removes `initialize` and sessions completely, and 2.3 already serves that revision. The POC's `mcp.Client` in its default `auto` mode negotiated `2026-07-28` with no session at all.
- In 2026-07-28, `clientInfo` moves into every request's `_meta`, and the client chooses it.

### 5. Separate port per scope

It works: a second `uvicorn.Server` in the same process, serving its own app. But each scope needs a free port, a listener started and stopped at run time, its own DNS-rebinding allowed-hosts entry, and a mapping from port to scope. It still needs a token or the port number as the secret, and any local process can scan ports. A path prefix gives the same isolation for free. One fixed second port for "scoped only" adds nothing over a `/mcp/s/` prefix.

### 6. Other mechanisms

- Per-request `_meta`: none of the three CLIs lets the config inject `_meta` (not found in any of their docs or config schemas). In 2026-07-28, `_meta` comes from the client implementation on each request.
- Tool-argument token: the model writes the arguments. It can leave the token out, or use another token it finds in a log or file. A tool argument can carry a capability handle, but it cannot set authority. The 2026-07-28 spec's "server-minted handles passed as ordinary tool arguments" are for state, not for access control.

### Can the agent widen its scope?

- Another token: guessing is not practical. Tokens can leak through Kiln logs if the path is not redacted. Agents read traces, so keep the tokens out of anything the tuner hands to agents.
- Its own token: harmless.
- Leaving the token out: needs a new connection to `/mcp`. The shell has no network. The CLI process does have network, so these CLI features matter:
  - Claude Code: the docs list only user commands for adding servers (`claude mcp add`, `add-json`). The shell could run one, but it writes config for *future* sessions, and the tuner launches with `--strict-mcp-config`. Its `WebFetch` tool runs in the CLI process. The tuner already disallows it (`_BUILT_IN_TOOLS` in `dispatch/claude_cli.py`).
  - Codex: the tuner passes `--ignore-user-config` and disables `skill_mcp_dependency_install` and other features (`DISABLED_FEATURES` in `dispatch/codex_cli.py`). There is no model-facing tool for adding MCP servers (not verified beyond the config source).
  - OpenCode: the tuner writes the config outside the workspace, denies reads of it, and denies every tool with `"*": "deny"`. Whether OpenCode reloads a workspace `opencode.json` while running is **not verified**. Keep the agent unable to write config files that OpenCode reads.
- The passthrough itself: `call_kiln_api` must deny the scope endpoints and any settings endpoint that changes the MCP config (for example a setting that disables the fence). This is the most direct way to widen a scope, and binding alone does not prevent it.
- Context: Kiln's REST API on 127.0.0.1:8757 has no authentication. The fence holds only because the agent's sole lane is the MCP connection. Any CLI tool that can do HTTP from the CLI process (a web fetch, a browser, a plugin) breaks that assumption, whatever the binding.

## Client configuration

Scoped launch (harness tuner). The URL is the scope. The timeout is long because a call can wait on a Kiln job.

Claude Code (`claude -p ... --mcp-config <file> --strict-mcp-config`):

```
{"mcpServers": {"kiln": {
  "type": "http",
  "url": "http://127.0.0.1:8757/mcp/s/<token>",
  "timeout": 1800000
}}}
```

- `type` also accepts `streamable-http`. An entry with `url` but no `type` is read as stdio, which is an error.
- `headers` is supported (`"headers": {"Authorization": "Bearer ${KILN_SCOPE_TOKEN}"}`), with `${VAR}` expansion. Credential-looking names such as `ANTHROPIC_API_KEY` expand as empty.
- There is also `headersHelper`.
- The per-server `timeout` (ms) overrides `MCP_TOOL_TIMEOUT`, and the default is "about 28 hours". `MCP_TIMEOUT` is the start-up timeout.

Codex (`codex exec ... -c key=value`, TOML values):

```
-c 'mcp_servers.kiln.url="http://127.0.0.1:8757/mcp/s/<token>"'
-c 'mcp_servers.kiln.tool_timeout_sec=1800'
-c 'mcp_servers.kiln.startup_timeout_sec=120'
-c 'mcp_servers.kiln.default_tools_approval_mode="approve"'
# header variants:
-c 'mcp_servers.kiln.http_headers={"X-Kiln-Scope"="<token>"}'
-c 'mcp_servers.kiln.bearer_token_env_var="KILN_SCOPE_TOKEN"'
```

- `url`, `bearer_token_env_var`, `http_headers`, `env_http_headers` and `http_headers_helper` are fields of the streamable HTTP config in `codex-rs/config/src/mcp_types.rs`. An inline `bearer_token` is rejected.
- Defaults on `main`: `DEFAULT_STARTUP_TIMEOUT` = 30 s and `DEFAULT_TOOL_TIMEOUT` = 300 s (`codex-rs/codex-mcp/src/rmcp_client.rs`).
- No experimental flag is needed on current `main`: there is no rmcp or streamable feature in `codex-rs/features/src/lib.rs`. Releases from 2025 needed `experimental_use_rmcp_client = true` (from memory, not re-checked).
- OAuth: the default `auth = "oauth"` uses only *stored* credentials ("Starting an OAuth login is a separate operation"), so `codex exec` does not start a login on a 401.

OpenCode (`OPENCODE_CONFIG=<file> opencode run ...`):

```
{"mcp": {"kiln": {
  "type": "remote",
  "url": "http://127.0.0.1:8757/mcp/s/<token>",
  "enabled": true,
  "oauth": false,
  "timeout": 1800000
}}}
```

- From the 1.19.6 binary's config schema (`McpRemoteConfig`): `url`, `enabled`, `headers`, `oauth` (an object, or `false` "to disable OAuth auto-detection") and `timeout` ("Defaults to 5000 (5 seconds)"). There is also `experimental.mcp_timeout`.
- The remote connect code tries StreamableHTTP first and then falls back to SSE. Both get the configured headers.
- A 401 sets `needs_auth` unless `oauth: false`.
- Tool calls use `resetTimeoutOnProgress: true`, so progress notifications extend the timeout.

The open endpoint, for a user's own clients (the URL is the only setting needed):
- Claude Code: `claude mcp add --transport http kiln http://127.0.0.1:8757/mcp`.
- Cursor (`~/.cursor/mcp.json`): `{"mcpServers": {"kiln": {"url": "http://127.0.0.1:8757/mcp"}}}`.
- VS Code (`.vscode/mcp.json`): `{"servers": {"kiln": {"type": "http", "url": "http://127.0.0.1:8757/mcp"}}}`.
- Claude Desktop: its local config file runs stdio servers, and its remote "connectors" are reached from Anthropic's cloud, so a localhost URL needs a stdio bridge such as `npx mcp-remote http://127.0.0.1:8757/mcp` (from memory, not verified for current releases).
- Cursor, VS Code and Claude Code also accept `headers`. None of these needs a header for the open endpoint, and none starts OAuth unless it gets a 401.

## Long tool calls

- Server (SDK): there is no server-side tool timeout in 1.30 or 2.3, and uvicorn has no response timeout. `session_idle_timeout` (1.30 default 30 min) counts only time with *no* request in flight, so a long call does not trip it. SSE responses send `: ping` comments every 15 s (`sse_starlette` `DEFAULT_PING_INTERVAL = 15` in 1.x; `_SSE_PING_INTERVAL = 15.0` in 2.x modern mode). Those pings keep idle-read timeouts in proxies and HTTP clients from firing. With `json_response=True` there are no pings and no progress.
- Spec: senders SHOULD set timeouts. They MAY reset the timeout on progress, but SHOULD keep a maximum (2025-11-25 lifecycle, "Timeouts").
- Claude Code: per-server `timeout`, or `MCP_TOOL_TIMEOUT`, default about 28 h. Whether progress resets it is not verified; the default is long enough anyway.
- Codex: `tool_timeout_sec`, default 300 s. Set it as the tuner does now (1800). Whether progress resets it is not verified.
- OpenCode: per-server `timeout`, default 5 s. This applies to tool calls and resets on progress. Set it as the tuner does now (30 min).
- Progress notifications are not *required* when each client's timeout is set long. They are still worth sending: send `ctx.report_progress(...)` every 15 to 30 s while `call_kiln_api` waits on a job or relays a Kiln SSE stream. This is a safety net for OpenCode and for any client with a short default. It only reaches clients that sent a `progressToken`: the SDK client and OpenCode do; Claude Code and Codex are not verified.
- Stateless mode keeps progress working (verified).
- In 2026-07-28 a broken response stream loses the call, and the client must re-issue it. Design long Kiln operations so that a retry is safe, or return a job handle.

## mcp 1.x vs 2.x

The recommendation stays the same after a bump to 2.x. In fact 2.x makes it more clearly right, because 2.x clients speak sessionless 2026-07-28 by default. The verified 2.3 run printed `proto: 2026-07-28` with `path_token: tokA`. API differences that touch this design:

- `mcp.server.fastmcp.FastMCP` becomes `mcp.server.mcpserver.MCPServer`. Importing the old module raises `ModuleNotFoundError` with a migration link (`mcp/server/fastmcp.py`). Kiln imports it today in `libs/server/kiln_server/mcp/runtime.py`.
- Transport options move from the constructor to `streamable_http_app(...)`: `stateless_http`, `json_response`, `streamable_http_path`, `transport_security`, `host`, `event_store`, `retry_interval`, `session_idle_timeout` and `max_sessions`.
- `StreamableHTTPASGIApp` moves to `mcp.server.streamable_http_manager`. `session_manager` is still lazy, and `run()` still runs only once.
- The context type is now `ServerRequestContext` (`mcp/server/context.py`). `request` is still the Starlette `Request`. New: `Context.headers` and `Context.protocol_version`.
- New `MCPServer(middleware=[...])`. A `ServerMiddleware` gets `(ctx, call_next)` for every request, before validation. It is a good single place to resolve the scope and enforce the fence for `tools/call`.
- 2026-07-28 requests take `handle_modern_request` (no session; handled in the ASGI task or a child task of it), chosen by the `MCP-Protocol-Version` header. The `stateless_http` flag then matters only for clients that still speak the handshake era.
- Auth: the same `TokenVerifier`, `AuthSettings` and `get_access_token()`. The `auth` package also gains `identity_assertion_enabled`.
- Client side: `streamablehttp_client` is removed. Kiln uses it in `libs/core/kiln_ai/tools/mcp_session_manager.py`. `streamable_http_client` takes an `httpx2.AsyncClient` (a new dependency, `httpx2`), and there is a new high-level `mcp.Client(..., mode="auto"|"legacy")`.
- `McpError` becomes `MCPError` (`mcp/shared/exceptions.py`). Kiln imports `McpError` today.

## What was run

POC scripts are in `/tmp/claude-0/-home-user/e2ccd85e-57b6-5fe6-a2f4-cbe5464fa93d/scratchpad/mcp_scope_poc/`:
- `poc_v1.py`: Kiln's venv, mcp 1.30.0.
- `poc_v2.py`: a scratch venv with mcp 2.3.0.
- `poc_progress_v1.py`.

Each runs uvicorn with a FastAPI app. The app has one MCP instance on `/mcp` and `/mcp/s/{token}`, a pure-ASGI middleware that sets a contextvar from the path, and a second instance with `TokenVerifier` on `/mcpauth`. The SDK's own client calls a `whoami` tool that returns everything the handler can see. Results, summarised:

- 1.30, all four modes (stateful or stateless × SSE or JSON): `/mcp/s/tokA` gives `path_token: 'tokA'` and `mw_contextvar: 'tokA'`. `/mcp?scope=tokC` with `X-Kiln-Scope: tokB` gives `header: 'tokB'` and `query: 'tokC'`. Bearer `tokA` on `/mcpauth` gives `access_token: 'tokA'`. No token or a bad token gives `401`. A bad `Host` gives `421`. `/mcp/` gives `404`.
- 1.30 stateful, raw session reuse: a session opened at `/mcp/s/tokA` and reused at `/mcp/s/tokB` gives `200`, `path_token: 'tokB'` and **`mw_contextvar: 'tokA'`**. Reused at `/mcp`, it gives `200`, `path_token: None` and **`mw_contextvar: 'tokA'`**. This proves the contextvar trap and the cross-path session sharing. In stateless mode the same requests show the current path in both fields.
- 2.3, all four modes, with `mcp.Client` in `auto` (it negotiated `2026-07-28`) and in `legacy` (`2025-11-25`): the same path, header, query and bearer results. The middleware contextvar is correct in both.
- 1.30 stateless progress: SSE mode delivered 3 of 3 progress notifications; `json_response=True` delivered none.

## Unverified / open

- The behaviour of the real CLIs against this server. Not run: they were not installed (Codex, OpenCode) or not tested against a local HTTP server (Claude Code 2.1.329 is installed). This covers query-string handling, stateless-server compatibility, sending of `progressToken`, and progress-reset of timeouts in Claude Code and Codex.
- Whether OpenCode or Codex reload MCP config written into the workspace during a run.
- Claude Desktop's current remote-server support for localhost URLs, and the Codex `experimental_use_rmcp_client` history. Both are from memory.
- `GitSyncMiddleware` (a `BaseHTTPMiddleware`) with long MCP SSE responses: not tested.
- The network blocked modelcontextprotocol.io, developers.openai.com and opencode.ai. Spec text came from the `modelcontextprotocol/modelcontextprotocol` repo on GitHub. Codex facts came from `openai/codex` `main` on GitHub. OpenCode facts came from the strings in the `opencode-linux-x64@1.19.6` npm binary. Claude Code facts came from code.claude.com/docs/en/mcp.
- Open design choices: the scope-store persistence format and its TTL; whether to add a user setting that turns off the open `/mcp`; and how to redact tokens from access logs.

## Sources

- Spec 2026-07-28 changelog: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/changelog.mdx
- Spec 2026-07-28 Streamable HTTP: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/transports/streamable-http.mdx
- Spec 2026-07-28 authorization: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/authorization/index.mdx
- Spec 2025-11-25 transports and lifecycle: https://github.com/modelcontextprotocol/modelcontextprotocol/tree/main/docs/specification/2025-11-25/basic
- Security best practices 2025-11-25: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/docs/2025-11-25/tutorials/security/security_best_practices.mdx
- Python SDK: https://github.com/modelcontextprotocol/python-sdk. Read in the installed source: `mcp/server/fastmcp/server.py`, `mcp/server/streamable_http_manager.py`, `mcp/server/streamable_http.py`, `mcp/server/lowlevel/server.py`, `mcp/server/auth/middleware/{bearer_auth,auth_context}.py`, `mcp/server/transport_security.py`. For 2.3 also `mcp/server/mcpserver/{server,context}.py`, `mcp/server/_streamable_http_modern.py` and `mcp_types/version.py`.
- 2.x migration guide: https://py.sdk.modelcontextprotocol.io/v2/migration/
- Claude Code MCP docs: https://code.claude.com/docs/en/mcp
- Codex: https://github.com/openai/codex (`codex-rs/config/src/mcp_types.rs`, `codex-rs/codex-mcp/src/rmcp_client.rs`, `codex-rs/codex-mcp/src/connection_manager.rs`)
- OpenCode: https://opencode.ai/docs/mcp-servers/ (blocked here; the npm package `opencode-linux-x64@1.19.6` was read instead)
- Harness tuner dispatchers: `src/kiln_harness_tuner/dispatch/{claude_cli,codex_cli,opencode_cli}.py`
