# Area reference: `app/web_ui`

A SvelteKit app (Svelte 4, TypeScript), prerendered with `ssr = false` and served by the desktop app. All data comes from the FastAPI servers. This reference covers code structure; for visual design and house controls, use the `kiln-ui` skill.

## Gotchas

- **Use the typed API client.** Call endpoints through `client` from `$lib/api_client` (openapi-fetch, typed by `lib/api_schema.d.ts`). Don't write `fetch(base_url + path)` for an endpoint that's in the schema, and don't hand-write response types for it; use the aliases in `$lib/types`, which are built from `components["schemas"]`. `lib/git_sync/api.ts`, `lib/ui/delete_dialog.svelte` and `lib/ui/edit_dialog.svelte` still use raw `fetch`; don't copy them. Streaming endpoints are the exception and go through the shared SSE helpers in `lib/utils/`.
- **Use the shared error helper.** Turn errors into `KilnError` with `createKilnError` (`lib/utils/error_handlers.ts`). Don't hand-unwrap `detail?.message || detail?.detail` or write a page-local `error_detail()`; if the helper doesn't handle a shape, extend it.
- **Store modules don't set themselves up on import.** No `store.subscribe(...)`, fetch, storage read or `init*()` call at module scope (gate: `module-level-subscribe`, WARN). `lib/stores.ts` subscribes to `ui_state` and `projects` at import, and `jobs_store`, `chat_ui_state` and others do similar work; that's why 7 test files need `vi.resetModules()`. New setup goes in an exported `init_*()` that returns a teardown and is called once from `routes/(app)/+layout.svelte`, never from leaf components (`initCopilotConnectionStore` is called from three components today; don't add a fourth).
- **`indexedDBStore` and `localStorageStore` are never created inside functions or components.** Each call starts a load and installs a subscription that is never removed (`lib/stores/index_db_store.ts`, `lib/stores/local_storage_store.ts`). Define each persisted store once, at module scope of the module that owns its key and shape (as `tools_store.ts` does). For a read-only peek, read the storage directly instead of creating a live, auto-saving store.
- **Lookup functions don't trigger loads.** Name and detail helpers (`*_name`, `*_details`, `*_info`) are pure. `available_model_details` in `lib/stores.ts` calls `load_available_models()` as a hidden side effect; don't add more like it. Callers load explicitly in `onMount` or the page loader.
- **Load-once caches must be able to retry and reset.** A new "load once" global list must leave its error state on the next call and expose a reset. After a provider is connected or removed, invalidate model caches through the helper in `lib/stores.ts` (extend it if it misses a cache you add), never by nulling individual stores from a page.
- **`lib/` doesn't import `routes/`** (gate: `lib-imports-routes`). A component used by more than one route tree moves into `lib/ui` (generic) or `lib/components` (domain). Four existing `lib` → `routes` imports (`run_sidebar.svelte`, `copilot_auth_page.svelte`, `multiturn_composer.svelte`, `extractor_picker.svelte`) are grandfathered. Don't import across the `(app)` and `(fullscreen)` route groups either.
- **Errors show in the page.** Use the page's error state with `Warning` or a `Dialog`'s error. Never `alert()`, and never `alert()` from a store.

## Where things go

| You are adding | It goes in |
|---|---|
| A page or layout | `src/routes/(app)/…` (inside the app shell) or `src/routes/(fullscreen)/…` (setup and full-screen flows) |
| Page logic beyond wiring: multi-step handlers, orchestration, API sequences, draft migration | a `.ts` flow module next to the page with a `.test.ts` beside it (`routes/(app)/specs/[project_id]/[task_id]/builder/plan_flow.ts` is the model). A handler over ~50 lines or calling several endpoints moves out of the `.svelte` file. Never copy a function into a test because it lives in a component; extract it. |
| A typed API wrapper used by several pages | `lib/api/` (e.g. `lib/api/v2_eval_api.ts`) |
| A client-side service with no UI | `lib/services/` |
| A store | `lib/stores/<domain>_store.ts`. Not `lib/stores.ts`, which already mixes stores with display helpers. |
| A display-name or formatting helper | a domain module in `lib/utils/` (rules.md E18). `lib/utils/formatters.ts` is for domain-free formatting only. |
| A shared, generic component | `lib/ui/` (a shared control: see `kiln-ui` before changing one) |
| A shared, domain-specific component | `lib/components/` |
| Generated API types | `lib/api_schema.d.ts`, regenerated with `lib/generate_schema.sh`. Never edit it by hand. |

**Dependency direction.** `routes/` → `lib/`. `lib/ui` and `lib/components` → `lib/utils`, `lib/stores`, `lib/api`, `lib/api_client`. Nothing in `lib/` imports from `routes/`.

## Startup

| Where | What starts there |
|---|---|
| `src/hooks.client.ts` | Sentry |
| `src/routes/+layout.ts` (root `load`) | PostHog and `setup_ph_user()` (outside dev builds) |
| `src/routes/+layout.svelte` | Loads projects and the current task |
| `src/routes/(app)/+layout.svelte` | App-shell services such as the update check |
| Import of `lib/stores.ts` and some `lib/stores/*` modules | Subscriptions and storage reads (grandfathered; see Gotchas) |

App-wide services start in one of the first two rows; app-shell state is wired in `routes/(app)/+layout.svelte`. Don't start a service from a leaf component or from a module's top level.
