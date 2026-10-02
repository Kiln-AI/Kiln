# Area reference: `libs/server` and `app/desktop`

`libs/server` (`kiln_server`) is a FastAPI library that wraps `kiln_ai`. `app/desktop` is the desktop application: a pyinstaller app whose `studio_server` extends the `kiln_server` app with desktop-only APIs, hosts the built web UI, and runs a tray app.

## Gotchas

- **Importing `kiln_server.server` builds an app.** The module ends with `app = make_app()` so uvicorn can import it by string. `desktop_server` imports the module only to call `kiln_server.server.make_app`, so every desktop start and test import builds and discards a full `kiln_server` app. Don't add another module-level app; a new runtime that needs an import-string app gets a tiny module of its own (as `app/desktop/dev_app.py` does).
- **Startup work goes in `lifespan`, not in `make_app()` or at import.** `desktop_server.make_app` currently calls `setup_litellm_logging()` and `refresh_model_list_background()`, so building the app (for example to dump the OpenAPI schema) starts a network refresh. That is grandfathered; new long-lived resources are created in `desktop_server.lifespan` and stored on `app.state` (rules.md B6).
- **Process-wide state set by lifespan.** `lifespan` turns on `kiln_ai.datamodel.strict_mode` and restores it on shutdown, and shuts down `job_registry.events`. A second app built in the same process shares those globals.
- **Background work uses the job registry.** `studio_server/jobs/` is the job framework: subclass `JobWorker` (`jobs/models.py`) and register it on the `JobRegistry` where `connect_jobs_api` registers `NoopJobWorker`. Don't add another dict-of-jobs plus a `set[asyncio.Task]`, as `data_gen_api._batch_jobs` / `_batch_background_tasks` do.
- **Routers are not libraries.** Don't import from another `*_api.py` module, and never import its `_private` names (for example `data_gen_api._resolve_task_runtime_prompt`). Move the shared logic to a service module first (see "Where things go").
- **`project_from_id` and `task_from_id` raise `HTTPException`.** They live in `kiln_server.project_api` and `kiln_server.task_api` and are fine to call from a route handler. Don't call them from service code; take a loaded `Project`/`Task` or raise a domain error.
- **`Config` read-modify-write isn't atomic.** `kiln_server.project_api.add_project_to_config`, `git_sync.config` (`git_sync_projects`) and the custom-model handlers in `provider_api` read a list or dict from `Config.shared()`, change it, and save it. Sync handlers run in a threadpool, so two requests can lose an update. Don't add another unguarded read-modify-write of a `Config` collection.
- **No `requests` inside `async def`.** `provider_api` has many synchronous `requests.get/post` calls inside async handlers, and each one blocks the whole server (including SSE streams) for the length of the call. New outbound calls use `httpx.AsyncClient` with a timeout (rules.md G23).
- **Config is read inside handlers today.** `Config.shared()` is called directly in handlers and helpers, and tests patch `<module>.Config`. For new code, read config in the handler (or a FastAPI dependency) and pass the values down; don't read it in helpers (rules.md D11).
- **`libs/server` must not know about desktop features.** No git-sync, copilot, jobs or other desktop-only knowledge in `kiln_server`. The desktop extends it through `make_app(lifespan=..., extra_middleware=...)` and its own `connect_*_api(app)` calls. `kiln_server.server.tags_metadata` already lists desktop-only tags; don't add more.
- **The env vars a process reads live in the entry points.** `KILN_DEV_MODE`, `DEBUG_EVENT_LOOP` and `KILN_SKIP_REMOTE_MODEL_LIST` are set by `app/desktop/dev_env.set_dev_env_vars` for the dev server. Read new settings in the entry point or through `Config`, not in middleware or helpers (gate: `env-access`).

## Where things go

| You are adding | It goes in |
|---|---|
| An endpoint that works on any `kiln_ai` project with no desktop feature | `libs/server/kiln_server/<domain>_api.py`, wired in `kiln_server.server.make_app` |
| A desktop-only endpoint | `app/desktop/studio_server/<domain>_api.py`, as a `connect_<domain>_api(app)` called from `desktop_server.make_app` (before `connect_webhost`, which must stay last) |
| Request and response models for desktop endpoints | `app/desktop/studio_server/api_models/` |
| Logic shared by several handlers, or a handler over ~50 lines | a service module that takes plain arguments and raises domain errors, e.g. `studio_server/services/<domain>.py` (create the folder if needed), or `kiln_ai` if it isn't app-specific. `studio_server/utils/` holds older helpers that raise `HTTPException`; don't extend that pattern. |
| Background or long-running work | a `JobWorker` in `studio_server/jobs/` |
| Git-sync behaviour | `app/desktop/git_sync/` |
| App-scoped objects (registries, clients, caches, locks) | created in `lifespan` or inside `connect_*_api(app)` (`git_sync_api.connect_git_sync_api` creates its `OAuthFlowManager` this way), never at module level |

**Dependency direction.** `app/desktop` → `libs/server` → `libs/core`. Never the reverse. Within `studio_server`: routers → services → `kiln_ai`; services and utils never import routers.

## Startup

| Entry point | What it sets up |
|---|---|
| `app/desktop/desktop.py` (`__main__`, the shipped app) | At import: `setup_certs()` and the `LLAMA_INDEX_CACHE_DIR` / `NLTK_DATA` env vars. In `__main__`: multiprocessing start method, Sentry (when `SENTRY_DSN` is set), `setup_resource_limits()`, then the tray app and a `DesktopServer` thread running `desktop_server.make_app` via `server_config`. |
| `app/desktop/dev_server.py` (`__main__`) → `app/desktop/dev_app.py` | `set_dev_env_vars()` at import of both modules, `setup_resource_limits()`, then uvicorn with reload on `app.desktop.dev_app:dev_app` (`make_app()` at import of `dev_app`). |
| `desktop_server.make_app` (used by both above) | `setup_litellm_logging()`, the remote model-list refresh, all routers, `GitSyncMiddleware`. Its `lifespan` sets strict mode, starts and stops background git syncs, and closes the job event bus. |
| `kiln_server` script (`kiln_server.server:main`) | Writes host/port CLI args to `os.environ`, then runs uvicorn on `kiln_server.server:app`. No lifespan, strict mode or litellm logging. |
| `kiln_mcp` script (`kiln_server.mcp.mcp:main`) | `logging.basicConfig` at the CLI's log level, then serves a project's tools over MCP. No strict mode or litellm logging. |
| `app/web_ui/src/lib/openapi_schema.sh` | Imports `desktop_server.make_app` and dumps `make_app().openapi()` with `KILN_SKIP_REMOTE_MODEL_LIST=true` to avoid the network refresh. |

Process-wide setup belongs in one bootstrap function that each entry point calls (rules.md B4); per-app setup belongs in `lifespan`. The entry points above don't agree yet, so when you add startup work, add it to `lifespan` (per-app) or next to the existing setup in each entry point that needs it, and say which in your summary.
