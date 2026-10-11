# Audit: `Kiln/libs/server` + `Kiln/app/desktop`

Scope: `libs/server/kiln_server/**` and `app/desktop/**`. Tests, the generated `studio_server/api_client/kiln_ai_server_client/**` client and build output are excluded. About 24k hand-written lines; the rest of the ~54k is the generated client.

## Summary

- **There are 8+ entry points and each boots the app differently.** These are `desktop.py`, `dev_server.py`→`dev_app.py`, `kiln_server.server:main`, `kiln_mcp`, `generate_openapi.py`, the inline `make_app().openapi()` in `openapi_schema.sh`, the dead `desktop_server.run_studio()`, and the stale `run_desktop_dev.sh`. They disagree on strict mode, litellm logging, log config, lifespan and remote model refresh. Process setup is spread across import time (`desktop.py` env writes and `setup_certs()`, `dev_server.py`, `dev_app.py`), the app factory (`make_app` starts a network refresh and installs litellm callbacks) and lifespan (strict mode, background git syncs).
- **Importing a module does real work.** `kiln_server/server.py:214` builds a full libs-only FastAPI app at import, and the desktop pays for it on every start just to import `make_app`. `webhost.py` mutates the stdlib `mimetypes` at import. `git_sync_manager.py` sets process-wide libgit2 timeouts at import. `kiln_server_client.py` builds an HTTP client at import that nothing uses. `jobs/registry.py:539` builds a singleton at import, and that singleton reads `KILN_JOBS_MAX_CONCURRENT` at import.
- **Module-level mutable state is everywhere, and several stores are parallel in-memory "job" systems:**
  - `job_registry`, a full job framework whose only registered worker is a Noop.
  - `data_gen_api._batch_jobs` plus `_batch_background_tasks`, an ad-hoc second job registry.
  - `GitSyncRegistry` class-level dicts.
  - a `global` cache in `provider_api`, and `global` committer caches in `git_sync_manager`.
  - a global `asyncio.Lock` in `run_api` that serializes every run update across all projects.
  - a dead `background_tasks` set in `document_api`.

  Production code carries test-only `reset()` hooks, and tests monkeypatch these globals.
- **The route modules are god files with logic in the handlers.** `connect_document_api` is one 1,642-line function holding 42 closures. `connect_evals_api` is 1,610 lines, and `eval_api.py` is 3,362 lines. Single handlers run 205–313 lines: `create_spec_with_copilot` and `get_run_config_eval_scores`, which duplicates `compute_score_summary`'s completion and score aggregation. 11 files are over 800 lines.
- **Layering is inverted.** Route modules are used as libraries: `utils/copilot_utils.py` imports from `eval_api.py`, and `copilot_api` and `batch_plan_api` import the private `_resolve_task_runtime_prompt` from `data_gen_api`. "Utils" raise `HTTPException`. `libs/server` carries desktop-only OpenAPI tags and a dead desktop `error_codes.py`.
- **Config is read ad hoc.** `Config.shared()` is called 103 times, 74 of them in `provider_api.py`, and tests patch `...provider_api.Config` 74 times. Handlers read-modify-write `Config` lists and dicts without a lock. `KILN_SERVER_BASE_URL` and its default are read in 3 places. `KILN_DEV_MODE` is read from env on every request in the middleware. The OAuth callback URL hard-codes port 8757 even though the port can be changed.
- **Logic is copy-pasted.**
  - ~15 near-identical `connect_<provider>()` key validators.
  - The project_id→GitSyncManager resolution exists 3 times, and one copy carries a "keep in sync" note.
  - The copilot API key getter exists twice.
  - The SSE "data: complete" terminator and status-generator wrappers are repeated across 4 modules.
- **Async handlers block the event loop.** 14 sync `requests.get/post` calls sit inside `async def` provider handlers, several with no timeout. Tk dialogs run from a worker thread while the Tk mainloop owns the main thread.
- **Zigzag comments are common in the eval and copilot code.** Examples: "rather than the 400 that used to stand here", "The web client is no longer an EventSource" (pasted twice), "these callers now make network calls they never used to", "the Optional is vestigial", "Phase 2 maps these to 409". Comments also run long: 10–15-line essays defending a single `if`.

## Findings by category

### 1. Redundant comments

1. **low** `Kiln/app/desktop/studio_server/provider_api.py:1251-1260` (and `:1285-1293`). The comments "# Any non-200 status code is an error", "# If the request is successful, the function will continue" and "# It worked! Save the key and return success" narrate `raise_for_status()` and the assignment below them. They are copy-pasted across the provider connectors.
2. **low** `Kiln/libs/server/kiln_server/run_api.py:1041`, `:1052`. "# Lock to prevent overwriting concurrent updates" repeats the module comment at `:38`, and "# Update and save" sits above three self-describing lines.
3. **low** `Kiln/app/desktop/studio_server/provider_api.py:695`, `:720`. "# Validate provider exists" and "# Add to registry" only narrate the step.
4. **low** Other one-line step narration:
   - `Kiln/app/desktop/studio_server/run_config_api.py:358` "# Save task first"
   - `Kiln/app/desktop/studio_server/repair_api.py:201` "# Save the updated run"
   - `Kiln/app/desktop/studio_server/tool_api.py:392`, `:462` "# Add task tools" / "# Add code tools"
   - `Kiln/app/desktop/studio_server/eval_api.py:3142` "# Verify the run config exists"
5. **low** `Kiln/app/desktop/studio_server/api_client/kiln_server_client.py:14-21`. The docstrings "Get the version of the kiln-studio-desktop package." and "Get the base URL for the Kiln server." restate one-line private functions. `_get_desktop_app_version()` just returns `__version__`.
6. **low** `Kiln/libs/server/kiln_server/server.py:24`. The docstring "Get the version of the kiln-server package." on `_get_version`.
7. **med (verbosity)** `Kiln/libs/server/kiln_server/run_api.py:1023-1034`. A 12-line essay defends one `if "eval_source" in run_data` check. The same style appears at `Kiln/app/desktop/studio_server/eval_api.py:1315-1318` ("A second caller has to keep it too…"), `Kiln/app/desktop/studio_server/copilot_api.py:1132-1300` (roughly every third line is a comment), and `Kiln/app/desktop/studio_server/data_gen_api.py:386-395`. The useful invariant is buried in prose and drifts from the code. Prefer a short "why", and push long rationale into the spec or PR.

### 2. Zigzag / diff-dependent comments

1. **med** `Kiln/app/desktop/studio_server/eval_api.py:2804-2807`: "reports its real counts rather than the 400 that used to stand here. That 400 was never a policy about golden sets — it fired because…". This explains deleted code and only makes sense next to the diff.
2. **med** `Kiln/app/desktop/studio_server/eval_api.py:2553-2555` and `:2682-2684`: "The web client is no longer an EventSource — run_eval.svelte reads this with fetch… switching to POST would break…". It is history plus a defense, and the identical block is pasted twice.
3. **med** `Kiln/app/desktop/studio_server/utils/copilot_utils.py:158-160`: "so these callers now make network calls they never used to." It describes a change, not the code.
4. **med** `Kiln/app/desktop/studio_server/eval_builder_api.py:471-474`: "the Optional is vestigial, as every arm now judges a transcript". The comment admits the type is stale. Remove the Optional instead.
5. **low** `Kiln/app/desktop/studio_server/api_models/copilot_models.py:330-332`: "Preview inputs are no longer bundled here — once the draft is ready…".
6. **low** `Kiln/app/desktop/studio_server/jobs/registry.py:44`: "Phase 2 maps these to 409 Conflict." This refers to a project plan phase, not to code.
7. **low** `Kiln/app/desktop/studio_server/tool_api.py:277`: "Basic field validation is now handled by Pydantic validators in CreationRequest."
8. **low** `Kiln/app/desktop/studio_server/eval_api.py:1097`, `:1244` ("which now holds every eval trace") and `:3166` ("for every record written since the trace/score split"). These are migration-relative wording.
9. **low** `Kiln/app/desktop/studio_server/agent_api.py:350-351`: "a fallback for legacy files that predate the move." Which move is not stated.
10. **low** `Kiln/app/desktop/studio_server/utils/eval_builder_utils.py:107` ("both arms now judge the transcript") and `Kiln/app/desktop/studio_server/eval_builder_api.py:775`, `:1095`.

### 3. Poor modularization

1. **high** `Kiln/libs/server/kiln_server/document_api.py:976`. `connect_document_api` is one 1,642-line function containing 42 nested route closures (2,618-line file). Handlers can't be imported or tested on their own, and the file mixes request models, SSE wrappers, RAG runner construction (`build_rag_workflow_runner`, 118 lines at `:820`) and routes.
2. **high** `Kiln/app/desktop/studio_server/eval_api.py:1752` (`connect_evals_api`, 1,610 lines, 32 closures) in a 3,362-line file. The file holds ~40 Pydantic models, score math, split resolution, trace usage aggregation and the routes.
3. **high** `Kiln/app/desktop/studio_server/eval_api.py:3128-3333`. `get_run_config_eval_scores` is a 205-line handler doing all of the run-config score aggregation inline: 11 hand-rolled accumulators and a ≥50% threshold rule. It duplicates the "remaining_expected_items / partial_incomplete" completion logic in module-level `compute_score_summary` (`:1635-1730`). Two copies of the eval-completion semantics will drift.
4. **high** `Kiln/app/desktop/studio_server/copilot_api.py:1098-1411`. `create_spec_with_copilot` is a 313-line handler. It validates, deals splits with a seeded RNG, builds the Eval, EvalConfig and Spec, calls the remote copilot, builds datasets and persists. This is domain orchestration that belongs in a service. It also calls `generate_spec_eval_tags(request.name)` twice (`:1135`, `:1148`).
5. **high** `Kiln/app/desktop/studio_server/provider_api.py:1103-1743`. There are ~15 copy-pasted `connect_openai/groq/gemini/together/anthropic/...` functions, each doing GET models → special-case 401 → `raise_for_status` → write `Config` → `JSONResponse`. They differ only in URL, header and error string, so a table-driven validator would do. `connect_provider_api` (`:258`) is a further 803 lines.
6. **med** `Kiln/app/desktop/studio_server/tool_api.py:297` (`get_available_tools`, 192 lines inside a 768-line `connect_tool_servers_api`). The handler assembles tool sets and dials MCP servers inline.
7. **med** Duplicated project_id → GitSyncManager resolution. `Kiln/app/desktop/git_sync/middleware.py:358-389` and `Kiln/app/desktop/git_sync/save_context.py:12-45` are line-for-line copies; each docstring says to keep it in sync with the other. A partial third copy sits at `Kiln/app/desktop/desktop_server.py:57-93`.
8. **med** Two copies of the copilot API key getter: `Kiln/app/desktop/studio_server/utils/copilot_utils.py:120-128` (`get_copilot_api_key`) and `Kiln/app/desktop/studio_server/prompt_optimization_job_api.py:190-198` (`_get_api_key`, same docstring and same message).
9. **med** The SSE status-stream boilerplate is re-implemented four times: `Kiln/libs/server/kiln_server/document_api.py:161-182`, `:184-255`, `Kiln/app/desktop/studio_server/eval_api.py:321-334` and `Kiln/app/desktop/studio_server/multiturn_sdg_api.py:531-577`. The `"data: complete\n\n"` literal is repeated, and a constant exists only in `eval_builder_api.py:190`.
10. **med** `Kiln/app/desktop/desktop_server.py`. One file mixes the app factory, lifespan, git-sync bootstrap, a uvicorn thread wrapper and dead `run_studio*` helpers.
11. **med** The libs/server vs desktop split is arbitrary. `Kiln/app/desktop/studio_server/prompt_api.py` is a pure-core endpoint with the same `connect_prompt_api` name as `Kiln/libs/server/kiln_server/prompt_api.py`. `Kiln/libs/server/kiln_server/server.py:31-132` declares OpenAPI tags for desktop-only routers (Evals, Fine-tuning, Copilot, Git Sync, Jobs, Agent…), so the library knows its consumer.
12. **low** `Kiln/app/desktop/git_sync/git_sync_api.py:60-140`. Inline HTML/CSS templates for OAuth pages live in the API module.
13. **low** The `connect_` prefix means two things. It names route wiring (`connect_*_api(app)`) and also provider credential checks (`connect_openai(key)`, `connect_ollama`) in the same file, which is confusing when grepping.
14. **low** Eleven files exceed 800 lines: `eval_api` 3362, `document_api` 2618, `provider_api` 2340, `eval_builder_api` 1631, `data_gen_api` 1524, `copilot_api` 1411, `run_api` 1093, `tool_api` 1059, `copilot_utils` 1023, `finetune_api` 947, `git_sync_api` 928, `prompt_optimization_job_api` 928.

### 4. Globals

1. **high** `Kiln/app/desktop/studio_server/jobs/registry.py:539` (`job_registry = JobRegistry()`).
   - It is a process singleton created at import.
   - `connect_jobs_api` mutates it during app wiring (`Kiln/app/desktop/studio_server/jobs/api.py:97-99`).
   - Lifespan shuts down its event bus permanently (`Kiln/app/desktop/desktop_server.py:125` → `Kiln/app/desktop/studio_server/jobs/events.py:143`, `_closed = True`). A second app built in the same process gets a closed bus.
   - Tests must `monkeypatch.setattr(jobs_api, "job_registry", ...)` (`Kiln/app/desktop/studio_server/jobs/test_api.py:110`, `:605`).

   It should be app-scoped, created in lifespan and stored on `app.state`.
2. **high** `Kiln/app/desktop/studio_server/data_gen_api.py:337-375`. `_batch_jobs` and `_batch_background_tasks` form a second, ad-hoc in-memory job registry with hand-rolled eviction. It sits next to the real `JobRegistry`, which has only a `NoopJobWorker` registered (`Kiln/app/desktop/studio_server/jobs/api.py:99`). The tests poke `_batch_jobs.clear()` directly (`test_data_gen_api.py:1538-1562`).
3. **high** `Kiln/libs/server/kiln_server/run_api.py:39` (`update_run_lock = Lock()`, used at `:1042`). This module-global asyncio lock serializes every TaskRun update across all projects and tasks. It also only guards this one code path; other writers of the same TaskRun files skip it. That gives false safety plus a global bottleneck.
4. **med** `Kiln/app/desktop/git_sync/registry.py:20-24`. A ClassVar-dict singleton. It reaches into private manager fields (`existing._remote_name` at `:60`, `manager._git_executor` at `:108`, `:114`) and carries a test-only `reset()` at `:111`.
5. **med** `Kiln/app/desktop/git_sync/git_sync_manager.py:54-104`. Module caches for the committer name and email use the `global` keyword and a `reset_committer_cache()` "Used for testing", which is referenced 12 times in tests. The cached value bakes in `Config.shared().user_id` from the first call.
6. **med** `Kiln/app/desktop/studio_server/provider_api.py:2217-2234`. The `_openai_compatible_providers_cache` global (with the `global` keyword) has staleness logic that re-reads `Config` inside `is_stale()` (`:2210`).
7. **med** `Kiln/app/desktop/git_sync/git_sync_manager.py:27-31`. `pygit2.Settings()` timeouts are set process-wide as an import side effect of a manager module.
8. **med** `Kiln/app/desktop/desktop_server.py:113-129`. Lifespan flips the process-global `kiln_ai.datamodel.strict_mode`, so strict mode depends on which entry point ran. `kiln_server.server:main` never sets it.
9. **low** `Kiln/libs/server/kiln_server/document_api.py:104`. `background_tasks: set[asyncio.Task] = set()` is a dead global, never referenced.
10. **low** `Kiln/app/desktop/studio_server/api_client/kiln_server_client.py:65`. `server_client = get_kiln_server_client()` is a module-level client built at import. Only a test uses it, and it freezes `KILN_SERVER_BASE_URL` at import.
11. **low** `Kiln/app/desktop/util/resource_limits.py:6-18`. A `global has_setup_resource_limits` guard.
12. **low** `Kiln/app/desktop/studio_server/webhost.py:12-17`. `mimetypes.add_type(...)` mutates a stdlib global at import. It should happen inside `connect_webhost`.
13. **contrast (good)** `Kiln/app/desktop/git_sync/git_sync_api.py:753`. `OAuthFlowManager()` is created inside `connect_git_sync_api`, so it is app-scoped. Use this as the template.

### 5. Self-initializing modules / multiple entry points

1. **high** The entry points do not agree with each other:

   | Entry point | Strict mode | Litellm logging | Log config | Lifespan / bg sync | Remote model refresh |
   |---|---|---|---|---|---|
   | `Kiln/app/desktop/desktop.py:220` (prod) | yes | yes | `log_config()` | yes | yes |
   | `Kiln/app/desktop/dev_server.py:24` → `dev_app.py:17` | yes | yes | uvicorn default | yes | skipped via env |
   | `Kiln/libs/server/kiln_server/server.py:217` (`kiln_server` script) | **no** | **no** | default | **none** | no |
   | `Kiln/libs/server/kiln_server/mcp/mcp.py:143` (`kiln_mcp`) | no | no | `basicConfig` | n/a | no |
   | `Kiln/libs/server/kiln_server/generate_openapi.py:5-7` | libs-only schema; unreferenced, stale | | | | |
   | `Kiln/app/web_ui/src/lib/openapi_schema.sh:22-26` | inline `make_app().openapi()`; must set `KILN_SKIP_REMOTE_MODEL_LIST` to stop a network call | | | | |
   | `Kiln/app/desktop/desktop_server.py:208-222` | `run_studio`/`run_studio_thread` serve the libs-only app; dead code | | | | |
   | `Kiln/app/desktop/run_desktop_dev.sh:7` | `python -m desktop.desktop` from `app/`; module path doesn't match `app.desktop.*` imports; unreferenced | | | | |

   Nothing composes "bootstrap the process" in one place.
2. **high** `Kiln/libs/server/kiln_server/server.py:214`. `app = make_app()` runs at import. `desktop_server.py:12` does `import kiln_server.server as kiln_server` just to call `kiln_server.make_app`, so every desktop start and every test import first builds and discards a complete libs-only app, wiring ~100 routes.
3. **high** `Kiln/app/desktop/desktop_server.py:132-137`. The app factory installs global litellm callbacks (`setup_litellm_logging()`) and starts a background network refresh (`refresh_model_list_background()`), so building the app for an OpenAPI dump has side effects. `test_server.py:24` has to patch `refresh_model_list_background`. Both belong in lifespan.
4. **high** `Kiln/app/desktop/desktop.py:2-5`, `:36-40`. `setup_certs()` runs before the other imports (`# ruff: noqa: E402`), and `os.environ["LLAMA_INDEX_CACHE_DIR"]` and `os.environ["NLTK_DATA"]` are written at import. Importing `DesktopApp` in `test_desktop.py:12` therefore mutates the pytest process env.
5. **med** `Kiln/app/desktop/dev_server.py:21` and `Kiln/app/desktop/dev_app.py:12-14`. Both call `set_dev_env_vars()` at import, and `dev_app` defers its import (`# noqa: E402`) because unnamed modules "read these at import time". `test_dev_server.py:18-30` has to probe in a subprocess and `patch.dict(os.environ)` for that reason.
6. **med** `Kiln/app/desktop/studio_server/jobs/api.py:97-99`. Worker registration happens as a side effect of route wiring on a module singleton ("register_type overwrites by type_name, so repeated calls… are safe").
7. **med** `Kiln/app/desktop/studio_server/webhost.py:87`. `connect_webhost` does `os.makedirs(studio_path())` inside the app factory, so building the app creates `app/web_ui/build` in the repo.
8. **low** `Kiln/libs/server/kiln_server/server.py:225-228` and `Kiln/app/desktop/dev_server.py:35-37`. CLI args are passed to the app by writing `os.environ` so reload workers pick them up. It works, but config travels through process env.

### 6. Improper modules

1. **high** Route modules are imported as libraries, including private names.
   - `Kiln/app/desktop/studio_server/copilot_api.py:119-121` and `Kiln/app/desktop/studio_server/batch_plan_api.py:24` import `_resolve_task_runtime_prompt` from `data_gen_api`.
   - `Kiln/app/desktop/studio_server/utils/copilot_utils.py:66` (a *utils* module) imports from `eval_api`.
   - `Kiln/app/desktop/studio_server/eval_builder_api.py:103` imports guards and models from `multiturn_sdg_api`.
   - `Kiln/app/desktop/studio_server/eval_api.py:113` imports from `code_tool_api`.
   - `Kiln/app/desktop/studio_server/agent_api.py:22` and `Kiln/app/desktop/studio_server/prompt_optimization_job_api.py:56` import from `eval_api`.

   Shared domain helpers belong in a service or domain module, not in a router.
2. **med** HTTP lookups live in route modules but act as the shared helpers. `project_from_id` and `task_from_id` (`Kiln/libs/server/kiln_server/project_api.py:27`, `Kiln/libs/server/kiln_server/task_api.py:42`) raise `HTTPException` and are imported by 20+ desktop modules. "Utils" raise `HTTPException` too: 13 occurrences in `copilot_utils.py`, 4 in `eval_builder_utils.py`, 7 in `response_utils.py`. Domain helpers can't be reused outside HTTP.
3. **med** `Kiln/app/desktop/git_sync/git_sync_manager.py:363`, `:451`. Function-local `from app.desktop.git_sync.clone import ...` works around a cycle (`clone.py:15` imports `git_sync_manager`). `:83` also imports `Config` locally.
4. **med** `Kiln/app/desktop/studio_server/chat/helpers.py:1-5`. A test-helper module (`unittest.mock` imports, `PATCH_*` target strings) ships inside the production `chat` package and is bundled by pyinstaller. Only `test_*.py` use it.
5. **low** `Kiln/app/desktop/studio_server/chat/routes.py:26`. It imports the private `_get_base_url` from `kiln_server_client`.
6. **low** `Kiln/libs/server/kiln_server/error_codes.py:1`. A one-constant module (`CHAT_CLIENT_VERSION_TOO_OLD`) that nothing references.
7. **low** `Kiln/app/desktop/git_sync/save_context.py:48`. `save_context_for_project` is unused in production; it was built ahead of job workers that don't exist yet.
8. **low** `Kiln/app/desktop/studio_server/eval_api.py:113-119`. It mixes absolute `app.desktop.studio_server...` imports with relative `.correlation_calculator` imports.

### 7. Lazy-loading config gotchas

1. **high** `Config.shared()` is called 103 times from handlers and helpers, 74 in `Kiln/app/desktop/studio_server/provider_api.py` alone. Tests patch module-level `Config` 132 times, including 74× `patch("app.desktop.studio_server.provider_api.Config...")`, 13× `tool_api`, and 11× `git_sync.config`. Nothing is injected, so every test has to monkeypatch a global.
2. **high** Handlers read-modify-write `Config` collections with no lock:
   - `Kiln/app/desktop/studio_server/provider_api.py:721-733`, `:778-818` (`user_model_registry`, `custom_models`)
   - `Kiln/app/desktop/git_sync/config.py:49-62` (`git_sync_projects`)
   - `Kiln/libs/server/kiln_server/project_api.py:37-43` (`projects`)

   Sync handlers run in a threadpool, so concurrent requests can lose updates. `Config`'s internal lock only covers one `update_settings` call, not the read before it.
3. **med** `KILN_SERVER_BASE_URL` and its default `"https://api.kiln.tech"` are read from env in three places: `Kiln/app/desktop/studio_server/api_client/kiln_server_client.py:21`, `Kiln/app/desktop/studio_server/provider_api.py:1044` and `:1709`. The two `provider_api` sites also bypass the generated client and build raw httpx calls.
4. **med** `Kiln/app/desktop/git_sync/oauth.py:26`. `CALLBACK_URL = "http://localhost:8757/..."` is hard-coded, but the server port is configurable (`KILN_LOCAL_API_PORT`/`KILN_PORT`, `Config.kiln_local_api_port`), so GitHub OAuth breaks on any other port.
5. **med** `Kiln/app/desktop/git_sync/middleware.py:36-37`. `_is_dev_mode()` reads `os.environ["KILN_DEV_MODE"]` on every request. The feature flag is hidden deep in middleware instead of being passed when the middleware is built.
6. **med** `Kiln/app/desktop/studio_server/jobs/registry.py:56` via `:539`. `KILN_JOBS_MAX_CONCURRENT` is read when the singleton is built at import, so setting it later or in a test fixture has no effect without replacing the singleton.
7. **med** `Kiln/app/desktop/git_sync/middleware.py:358-372`. Every project-scoped request calls `project_path_from_id`, which `Project.load_from_file`s every configured project, and then `get_git_sync_config`. That is hidden per-request disk I/O before the handler repeats the same lookup through `task_from_id`.
8. **low** `Kiln/libs/server/kiln_server/server.py:165`. `KILN_FRONTEND_PORT` is read from env inside the library app factory; it should be a `make_app(...)` parameter.
9. **low** `Kiln/app/desktop/log_config.py:14-43`. Four `KILN_LOG_*` env vars are read directly. That is acceptable at an entry point, but `dev_server` and `kiln_server` never use this config.

### 8. Other significant red flags

1. **high** Sync `requests.get/post` calls run inside `async def` handlers, 14 sites in `Kiln/app/desktop/studio_server/provider_api.py`. Examples: `:1242` (`connect_openai`, no timeout), `:1275`, `:1305`, `:1428`, `:1538`, `:77`, `:98`. Each blocks the event loop for the whole server, including SSE streams, for the full duration of a remote call.
2. **med** `Kiln/app/desktop/studio_server/import_api.py:31-71`. Tk calls (`deiconify`, `filedialog.askopenfilename`) run via `asyncio.to_thread` while `tk.mainloop()` owns the main thread (`desktop.py:75`). Tk is not thread-safe.
3. **med** `Kiln/app/desktop/studio_server/settings_api.py:89-101`. `open_project_folder` wraps `project_from_id` in a bare `except Exception` that re-raises as 500, so a 404 becomes a 500. The same swallow pattern is at `:72-76`.
4. **low** `Kiln/app/desktop/git_sync/oauth.py:23`. The GitHub client secret is in source. The comment justifies it as a public-client secret, but it should at least come from the build-time config like `_sentry_config.py`.
5. **low** `Kiln/app/desktop/desktop_server.py:191-192`. A busy-wait `time.sleep(1e-3)` loop waits for uvicorn start, and `desktop.py:71` still adds a 200 ms "avoid race with server starting" delay after that wait.
6. **low** `Kiln/libs/server/kiln_server/mcp/runtime.py:50`, `:54`. It reaches into FastMCP's private `server._mcp_server`.

## Candidate rules

- **There is one bootstrap path.** Process setup belongs in one `bootstrap()` called by every entry point: certs, env-derived cache dirs, logging, litellm callbacks, resource limits, Sentry. Per-app startup belongs in the FastAPI `lifespan`: strict mode, remote model refresh, background syncs, job registry. Never do either at module import, and never in `make_app()`.
- **Never build objects at module import in `libs/server` or `studio_server`.** No `app = make_app()`, no client instances, no `Registry()` singletons, no `pygit2.Settings`, no `mimetypes.add_type`. Expose factories, create in lifespan and store on `app.state`. A CLI that needs a module-level `app` for uvicorn's import string should get it from a separate tiny `asgi.py`, not from the library module.
- **Long-lived in-memory state is app-scoped.** Registries, caches, locks and background task sets belong on `app.state`, or are created inside `connect_*_api(app)` as `OAuthFlowManager` is in `git_sync_api.py:753`. Don't add `global`, module dicts or ClassVar dicts. If a test needs `reset()`, the state is in the wrong place.
- **Use the existing job framework for long-running work.** New background or batch work registers a `JobWorker` with the job registry instead of adding another `_jobs: dict` plus a `set[asyncio.Task]`, as `data_gen_api._batch_jobs` does.
- **Route handlers are thin.** A handler parses and validates the request, calls one domain function, and maps errors to HTTP. Anything over ~40 lines, or anything with loops that accumulate stats, goes in a service module that takes plain arguments and raises domain errors. That module must not raise `HTTPException` and must not import from another `*_api.py`.
- **Never import from another router module** (`*_api.py`), and never import a `_private` name across modules. Promote shared helpers to `studio_server/services/` (or `kiln_ai`) first.
- **Don't call `Config.shared()` below the handler.** Read config once in the handler or dependency and pass the values down. For new handlers, use a FastAPI dependency (`Depends(get_config)`) so tests override one dependency instead of patching `module.Config`. Any read-modify-write of a `Config` list or dict needs a lock or an atomic `Config` helper.
- **Server endpoints and ports come from `Config` or the generated client.** Never call `os.environ.get("KILN_SERVER_BASE_URL", ...)` inline; use `kiln_server_client`'s public accessor. Never hard-code `8757`; use `Config.shared().kiln_local_api_base_url`.
- **No blocking I/O in `async def`.** Use `httpx.AsyncClient` with an explicit timeout, or wrap sync calls in `asyncio.to_thread`. Every outbound HTTP call has a timeout.
- **SSE endpoints use one shared helper** for framing and the `data: complete` terminator, and carry `@no_write_lock`.
- **Comments describe the code as it is now.** Don't write "no longer", "used to", "now does", "vestigial", "Phase N", or "since the X split". Put history in the PR description. Keep rationale to 1–3 lines; a longer explanation belongs in the spec.
- **Test helpers live under `test_*`/`conftest.py`**, never in a production package (see `chat/helpers.py`).
- **`libs/server` must not know about desktop features.** That covers OpenAPI tags, error codes and git-sync specifics. Desktop extends through `make_app(extra_middleware=..., extra_tags=...)` parameters.

## Refactor candidates

1. **Unify bootstrapping.** Size M, risk med.
   - Scope: `app/desktop/desktop.py`, `desktop_server.py`, `dev_server.py`, `dev_app.py`, `dev_env.py`, `libs/server/kiln_server/server.py`, `generate_openapi.py`, `run_desktop_dev.sh`, `web_ui/src/lib/openapi_schema.sh`.
   - Add one `bootstrap_process()` and move `setup_litellm_logging` and `refresh_model_list_background` from `make_app` into lifespan.
   - Move `kiln_server.server.app` into a separate `asgi.py` so importing `make_app` builds nothing.
   - Delete `run_studio*`, `generate_openapi.py` and `run_desktop_dev.sh`, or fix them.
   - The risk is pyinstaller import ordering for certs and env, which needs a smoke test of the packaged app.
2. **Make module singletons app-scoped.** Size M, risk med.
   - Scope: `jobs/registry.py:539` + `jobs/api.py`, `data_gen_api.py:337-375` (migrate onto `JobRegistry` workers), `git_sync/registry.py`, `provider_api.py:2217`, `git_sync_manager.py:29-104`, `run_api.py:39`, `document_api.py:104`, `kiln_server_client.py:65`.
   - Create them in lifespan and put them on `app.state`. Replace the global run lock with a per-run-path lock.
   - Tests get simpler: no more monkeypatching module globals.
3. **Split `eval_api.py` (3.3k lines) into routers, models and service modules.** Size L, risk med.
   - Extract a single eval-completion and score-aggregation service shared by `compute_score_summary` and `get_run_config_eval_scores`, which removes the duplicated logic.
   - Move the Pydantic models to `api_models/eval_models.py`.
   - Start with the score summary pieces because they are pure functions with good test coverage.
4. **Break up `connect_document_api` (1.6k-line closure).** Size L, risk low-med. Use an `APIRouter` per resource (documents, extractors, chunkers, embeddings, vector stores, RAG configs) with module-level handlers. Move `build_rag_workflow_runner` and the SSE wrappers into a service module. The change is mostly mechanical.
5. **Extract a copilot spec-creation service** out of the `create_spec_with_copilot` handler (`copilot_api.py:1098-1411`) into `copilot_utils` or a new `spec_creation.py`, with domain exceptions mapped to HTTP in the handler. Size M, risk med, because the path is persistence-heavy and needs good coverage first.
6. **Table-drive the provider connect functions.** Size M, risk low-med. Collapse the ~15 `connect_<provider>` functions in `provider_api.py:1103-1743` into one async validator (`httpx.AsyncClient` with a timeout) plus a per-provider spec: URL, auth header, invalid-key detector and config key. This also fixes event-loop blocking.
7. **Inject config instead of patching it.** Size M, risk low. Add a `get_config` FastAPI dependency and route `provider_api`, `tool_api` and `settings_api` through it, so the 132 test patches become a single `app.dependency_overrides`. Add `Config` helpers that do atomic read-modify-write for list and dict settings: `user_model_registry`, `git_sync_projects`, `projects`.
8. **Untangle the cross-router imports.** Size M, risk low. Move `task_run_config_from_id`, `eval_from_id`, `eval_config_from_id`, `get_all_run_configs`, `_resolve_task_runtime_prompt` and the multiturn guards into `studio_server/services/*`, raising domain errors. Map those errors to 404/422 in one exception handler in `custom_errors.py`.
9. **Dedupe git-sync manager resolution.** Size S, risk low. Make `middleware._get_manager_for_request` and `desktop_server._start_background_syncs` call `save_context.get_manager_for_project`. Break the `clone.py` ↔ `git_sync_manager.py` cycle by moving `make_credentials` and `make_push_callbacks` into `git_sync/auth.py`. Derive the OAuth callback URL from `Config.kiln_local_api_base_url`.
10. **Small cleanups.** Size S, risk low.
    - Move `chat/helpers.py` to test support.
    - Delete `error_codes.py` and the dead globals.
    - Strip the zigzag comments listed in §2.
    - Fix the `settings_api.open_project_folder` 404→500 bug.
    - Move `mimetypes.add_type` into `connect_webhost`.
