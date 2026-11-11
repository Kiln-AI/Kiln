# Code-quality audit: `Kiln/app/web_ui/src`

Scope: SvelteKit (Svelte 4 + TS), about 110k non-test, non-generated lines. I sampled it rather than reading all of it. I read every module in `lib/stores*`, `lib/api_client.ts`, `lib/utils/error_handlers.ts`, both SSE helpers, `lib/git_sync/api.ts` and the root and `(app)` layouts. Large pages were read in part. `lib/api_schema.d.ts` was skipped. All paths are relative to the workspace root.

## Summary

- **God pages.** `Kiln/app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/builder/+page.svelte` has 5,504 lines. Its `<script>` alone is 4,560 lines, with 68 functions, about 120 component `let`s and 16 inline API calls. Single handlers like `on_drive_multi_turn` (~510 lines) and `on_drive_single_turn` (~420 lines) run the whole pipeline: preflight, copilot calls, caching, analytics and error unwrapping. Nine more route files are over 900 lines. Across the code base, 213 `client.GET/POST/...` calls sit inline in route `.svelte` files, against about 66 in `.ts` modules.
- **No shared async-resource or API-error layer.** Every page builds its own `loading` / `error: KilnError | null` / stale-request guard (197 `KilnError | null = null` declarations, 71 `.svelte` files with `let *loading* =`). `createKilnError` always adds the prefix "Unexpected error:" and doesn't unwrap the typed `{message:{code,message}}` shape. Callers work around this with hand-written unwrapping in at least 4 places.
- **A second, untyped API client.** `lib/git_sync/api.ts`, `lib/ui/delete_dialog.svelte`, `lib/ui/edit_dialog.svelte`, `connect_providers.svelte` and builder streaming call `fetch(base_url + path)` directly. They write their own response types even though `api_schema.d.ts` already types these endpoints (git_sync appears 12 times there). Each one repeats the same `detail?.message || detail?.detail` block.
- **Copy-pasted store families.**
  - `prompts_store.ts`, `run_configs_store.ts` and `rating_options_store.ts` are the same roughly 90-line promise-dedup store, three times. A paste leftover shows it: the prompts store logs "Previous run config load failed".
  - `stores.ts` has the same load-once state machine three times: models, embeddings, rerankers.
  - There are two `calculateStatus`/`formatProgressPercentage`/EventSource progress stores.
  - `localStorageStore` and `sessionStorageStore` are line-for-line twins.
- **Modules that start themselves on import.**
  - `lib/stores.ts` subscribes to `ui_state` and `projects` at module load and fires task fetches from those subscriptions. The layout then fetches the same task again.
  - `jobs_store`, `tools_store`, `skills_store` and `chat_ui_state` open IndexedDB, read storage or subscribe at import.
  - `initCopilotConnectionStore()` is "initialized" from 3 different components and installs window/document listeners that are never removed.
  - Tests need `vi.resetModules()` plus dynamic re-import to get clean state.
- **Load caches that go stale.**
  - `load_available_models` & co. cache `"error_loading"` forever. After one failure there's no retry until a full reload.
  - `clear_available_models_cache()` resets only the LLM list. The embedding and reranker lists stay stale after a user connects a provider.
  - `price.ts` caches a failed pricing fetch forever.
  - `available_model_details()`, a pure lookup, quietly triggers a network load.
- **Heavy, diff-dependent comments in the newest code.** The builder directory runs 26–39% comment lines, versus about 1–5% in older pages. Many comments narrate history: "used to do", "Replaces the old … button", "Pre-X drafts have no such key", "no longer has a header". Older code has the opposite problem: comments that restate the code ("Set loading state to true", "Use the store's set method").
- **Layering inversions.**
  - `lib/ui` and `lib/components` import from `routes/` (4 sites).
  - `routes/(app)` imports components out of `routes/(fullscreen)/setup` (8 sites).
  - `app_page.svelte` is reached by `../../../../../../../../` relative paths (84 importers).
  - A test copies `sanitize_route_id` because the real function is trapped inside `+layout.svelte`.
- **Grab-bag modules.**
  - `lib/stores.ts` is mostly display-name helpers (`model_name`, `provider_name_from_id`, `vector_store_name`, `prompt_name_from_id`), not stores.
  - `lib/utils/formatters.ts` mixes generic formatting with eval, chunker and spec naming, in both camelCase and snake_case.
  - `lib/stores/evals_store.ts` holds no store: it's one API call plus analytics.
- **Persisted-draft schema without versioning.** Builder and synth drafts change shape through optional fields plus `?? null` defaults, explained by "drafts written before…" comments (13+). The IndexedDB key carries a manual `_v2` suffix that is repeated as a raw string in two pages.

## Findings by category

### 1. Redundant comments

1. **med** `Kiln/app/web_ui/src/routes/(app)/generate/[project_id]/[task_id]/synth_data_guidance_datamodel.ts:36`, `:55`, `:109`
   - What: "Make these reactive using stores", "Subscribe to selected_template changes and call apply_selected_template", "Use the store's set method".
   - Why: each one narrates the line right below it.
2. **med** `Kiln/app/web_ui/src/lib/stores/prompts_store.ts:46,48,70,100,106` and `Kiln/app/web_ui/src/lib/stores/run_configs_store.ts:57,59,81,111,117`
   - What: "Create and store the promise", "Set loading state to true/false", "Clean up the promise from the map".
   - Why: the comments were copy-pasted along with the code.
3. **med** `Kiln/app/web_ui/src/routes/(fullscreen)/setup/(setup)/connect_providers/connect_providers.svelte:479-482` (repeated at :579, :657, :732, :903, :943)
   - What: "Clear the available models list" / "Clear the available models cache so it refreshes next time" sits above a call named `clear_available_models_cache()`, six times.
   - Why: the comment restates the call, and the repeated block hints at a missing helper.
4. **low** `Kiln/app/web_ui/src/lib/stores/rag_progress_store.ts:32-56`
   - What: per-field comments such as `// error` above `error: null` and `// last started rag config id` above `last_started_rag_config_id`.
   - Why: the type at `:10-26` already documents these fields.
5. **low** `Kiln/app/web_ui/src/lib/stores/index_db_store.ts:13,128,159,202` ("Check if IndexedDB is available", "Get value from IndexedDB", "Set value in IndexedDB") and `Kiln/app/web_ui/src/lib/stores/local_storage_store.ts:7`.
6. **low** `Kiln/app/web_ui/src/lib/stores.ts:115-116,141-142` (repeated in 9 files)
   - What: the boilerplate `data, // only present if 2XX response` / `error, // only present if 4XX or 5XX response`.
   - Why: it documents openapi-fetch rather than this code.
7. **low** `Kiln/app/web_ui/src/lib/stores/recent_model_store.ts:31,39,45` ("Remove any existing entry…", "Add the new model to the front", "Keep only the first 5 items") and `Kiln/app/web_ui/src/routes/(app)/settings/providers/add_models/+page.svelte:254` ("Reset form").
- About 36 more matches of the same stock phrasing ("Initialize …", "Clear error …", "Close the dialog"), for example `Kiln/app/web_ui/src/lib/utils/json_schema_editor/json_schema_form_element.svelte:89`.
- The opposite failure also shows up:
  - **med**: in `builder/+page.svelte`, 1,435 of 5,504 lines are comments.
  - Many are multi-sentence essays that defend each line. Example: `:2185-2193` spends 9 lines on one `await author_judge_prompt_for_spec(...)`.
  - The defensive comments at `:2147-2149` and `:2164-2166` justify guards that should read as obvious.
  - Same style in `builder/builder_draft.ts` (39%) and `builder/plan_flow.ts` (35%).

### 2. Zigzag / diff-dependent comments

1. **med** `Kiln/app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/builder/+page.svelte:320-323`
   - What: "This is what the save's redirect used to do by unmounting the page."
   - Why: describes past behaviour; only meaningful next to the diff.
2. **med** `Kiln/app/web_ui/src/routes/(app)/generate/[project_id]/[task_id]/data_guide_setup/guide_refine_view.svelte:102` ("Replaces the old standalone 'Refine Data Guide' button") and `:142` ("the same validated preview dispatch the old Refine button used").
3. **med** `Kiln/app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/builder/claim_evidence_review.svelte:97-98`
   - What: "since the step no longer has a header of its own to carry it".
4. **med** `Kiln/app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/builder/+page.svelte:513-575` (`restore_draft`)
   - What: a dozen comments of the form "Pre-pairing drafts have no such key", "Pre-prefill-tracking drafts…", "Drafts from before guides were read here…", "Model lanes: pre-Drive-Settings drafts…", "a draft written when the refine form still had example fields".
   - Why: data-compat history is mixed into restore logic, and every new field adds another one.
   - Same pattern in `builder/builder_draft.ts:90-96`. 13+ such comments in total.
5. **low** `Kiln/app/web_ui/src/routes/(app)/generate/[project_id]/[task_id]/kiln_pro_inputs.svelte:344`
   - What: "Still reported in analytics, but no longer sent to the API."
6. **low** `Kiln/app/web_ui/src/lib/types.ts:156`
   - What: "Status moved from specs to evals; the old name is kept for existing call sites." (`SpecStatus = EvalStatus`)
   - Why: a migration alias with no end date. Rename the call sites instead.
7. **low** `Kiln/app/web_ui/src/routes/(app)/dataset/[project_id]/[task_id]/[run_id]/run/+page.svelte:151` ("Prompt ID previously was stored in the prompt_builder_name field").
   - Legitimate legacy read, but it reads as history rather than as a contract.
- About 100 more comments match "no longer / old / previously". Most are fine ("tools the server no longer offers"), but the builder/generate flows are dense with the diff-dependent kind.

### 3. Poor modularization

1. **high** `Kiln/app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/builder/+page.svelte:1-4561`
   - What: 4,560-line script with 68 functions and about 120 `let`s.
   - `on_drive_multi_turn` (`:2146`–~`:2655`), `on_drive_single_turn` (`:2745`–~`:3160`), `on_save` (`:4084`–`:4337`) and `run_calibration_round` (`:3868`) each mix orchestration, API calls, cache decisions, posthog capture and UI state.
   - A local `class CalibrationRefineError` is declared inside the component (`:3691`).
   - Why: this is business logic in the view layer. It can't be unit-tested without mounting the page, and some of it already lives in sibling `.ts` files (`plan_flow.ts`, `builder_draft.ts`, `claim_evidence.ts`) while the page still holds the rest.
2. **high** Other route god files:
   - `Kiln/app/web_ui/src/routes/(app)/generate/[project_id]/[task_id]/synth/+page.svelte` (1,602 lines)
   - `.../specs/[project_id]/[task_id]/compare/+page.svelte` (1,355)
   - `Kiln/app/web_ui/src/routes/(fullscreen)/setup/(setup)/connect_providers/connect_providers.svelte` (1,281)
   - `.../prompt_optimization/.../create_prompt_optimization_job/+page.svelte` (1,235)
   - `.../specs/[project_id]/[task_id]/+page.svelte` (1,159)
   - `Kiln/app/web_ui/src/routes/(app)/models/+page.svelte` (1,158)
   - `Kiln/app/web_ui/src/routes/(app)/assistant/chat.svelte` (1,143)
   - `.../dataset/.../[run_id]/run/+page.svelte` (1,125)
   - `.../fine_tune/.../create_finetune/+page.svelte` (1,033)
   - `.../[eval_id]/+page.svelte` (1,026)
3. **high** Copy-pasted promise-dedup store, three times:
   - `Kiln/app/web_ui/src/lib/stores/prompts_store.ts:22-113`, `Kiln/app/web_ui/src/lib/stores/run_configs_store.ts:26-125`, `Kiln/app/web_ui/src/lib/stores/rating_options_store.ts:22-103`.
   - Each has three `writable<Record<TaskCompositeId,…>>` (data / errors / loading) and identical try/catch/finally logic.
   - Paste leftover: `prompts_store.ts:35-37` logs "Previous run config load failed".
   - The copies have already drifted: run_configs short-circuits on cached data (`run_configs_store.ts:33-38`), prompts and rating_options don't, so they refetch on every call.
4. **high** `Kiln/app/web_ui/src/lib/stores.ts:250-342`
   - What: the same `"not_loaded"|"loading"|"loaded"|"error_loading"` state machine and loader written three times, for models, embeddings and rerankers.
5. **med** `Kiln/app/web_ui/src/routes/(fullscreen)/setup/(setup)/connect_providers/connect_providers.svelte:755-790`
   - What: decides "provider connected" by checking raw settings keys (`data["open_ai_api_key"]`, `data["bedrock_access_key"] && data["bedrock_secret_key"]`, …) against an untyped `fetch(base_url + "/api/settings")`.
   - Why: backend knowledge is duplicated in the UI. The server should report connection status.
6. **med** `Kiln/app/web_ui/src/routes/(app)/generate/[project_id]/[task_id]/synth_data_guidance_datamodel.ts:502-1248+`
   - What: about 750 lines of eval prompt-template builders (`requirements_eval_template`, `issue_eval_template`, …) and `static_templates` inside a UI data-model class that also does HTTP loads.
   - Why: prompt content and view-model are mixed in one class.
7. **med** `Kiln/app/web_ui/src/lib/stores/extractor_progress_store.ts:23-162` vs `Kiln/app/web_ui/src/lib/stores/rag_progress_store.ts:69-400`
   - What: parallel EventSource progress stores with duplicated `calculateStatus` (`extractor:164`, `rag:416`) and identically named `formatProgressPercentage` exports (`extractor:180`, `rag:461`).
8. **med** `Kiln/app/web_ui/src/lib/stores/local_storage_store.ts:6-38` vs `:40-69`
   - What: `localStorageStore` and `sessionStorageStore` are twins. They differ only in the `Storage` object; it should be a parameter.
9. **med** Several components fetch the same global data themselves:
   - `load_available_models()` is called in 20 files, `load_model_info()` in 19, `load_task_prompts()` in 19, `load_task_run_configs()` in 13 and `load_available_tools()` in 12.
   - The fetching is done from `$:` reactive statements in shared components (`Kiln/app/web_ui/src/lib/ui/run_config_component/tools_selector.svelte:50`, `skills_selector.svelte:45`, `prompt_type_selector.svelte:92`).
   - `stores.ts:199-201` has to guard against the empty-string `project_id` these reactive calls produce.
10. **med** `Kiln/app/web_ui/src/lib/utils/route_sanitizer.test.ts:3-24` copies `sanitize_route_id` from `Kiln/app/web_ui/src/routes/+layout.svelte:29-47`, because the function lives in a component.
    - Why: the test exercises a copy, not the shipped code. This is direct evidence of logic stuck in `.svelte` files.
11. **med** Layering inversions:
    - `Kiln/app/web_ui/src/lib/ui/run_sidebar.svelte:2` imports `routes/(app)/run/rating.svelte`.
    - `Kiln/app/web_ui/src/lib/ui/kiln_copilot/copilot_auth_page.svelte:5` imports `routes/(app)/app_page.svelte`.
    - `Kiln/app/web_ui/src/lib/ui/conversation/multiturn_composer.svelte:5` imports `routes/(app)/run/run_input_form.svelte`.
    - `Kiln/app/web_ui/src/lib/components/extractor_picker.svelte:15` imports `routes/.../create_extractor_dialog.svelte`.
    - Why: shared code depends on pages.
12. **med** Cross-route-tree imports:
    - 8 `routes/(app)` files import from `routes/(fullscreen)/setup`, e.g. `Kiln/app/web_ui/src/routes/(app)/settings/edit_task/[project_id]/[task_id]/load_task_editor.svelte:2` and `.../tools/[project_id]/add_tools/code_tool/+page.svelte:8`.
    - `Kiln/app/web_ui/src/routes/(fullscreen)/setup/(setup)/select_task/+page.svelte:2` imports from `(app)`.
    - 84 files reach `app_page.svelte` by relative `../../…` chains, up to 8 levels deep (`.../run_result/+page.svelte:2`).
13. **low** `Kiln/app/web_ui/src/lib/ui/run_sidebar.svelte:123,236,519,552,584`
   - What: a house component makes 5 API calls itself (PATCH run, feedback CRUD).
   - Why: it's intentionally central, but data access should be injected or live in a lib module.
14. **low** `Kiln/app/web_ui/src/routes/(app)/generate/[project_id]/[task_id]/+page.svelte:187` and `.../synth/+page.svelte:223`
   - What: the same `synth_data_${project_id}_${task_id}_v2` key and the same default shape are written out in two pages.

### 4. Globals

1. **high** `Kiln/app/web_ui/src/lib/stores.ts:71,187,252,284,315`
   - What: module-level mutable `let`s: `previous_ui_state`, `loading_project_tools` (array, mutated with push/filter), and three `*_loaded` flags.
   - Why: the state is hidden, can't be reset except via `clear_available_models_cache` (which covers one of the three), and survives across tests.
2. **high** `Kiln/app/web_ui/src/lib/stores.ts:157-181`
   - What: `load_current_task` mutates the global `ui_state` (clears `current_task_id`) and calls `alert()` in dev builds as a side effect of a failed fetch.
   - Why: a data loader that drives UI and persisted state.
3. **med** Module-level promise maps:
   - `Kiln/app/web_ui/src/lib/stores/prompts_store.ts:20`
   - `Kiln/app/web_ui/src/lib/stores/run_configs_store.ts:24`
   - `Kiln/app/web_ui/src/lib/stores/rating_options_store.ts:20`
   - `Kiln/app/web_ui/src/lib/stores/data_guide_job_store.ts:187` (`pollers = new Map` of intervals)
4. **med** `Kiln/app/web_ui/src/routes/(app)/models/price.ts:23-24`
   - What: module `pricingData` / `pricingLoadPromise` singletons. A failed fetch resolves to `null` and is cached permanently.
5. **med** `Kiln/app/web_ui/src/lib/stores/extractor_progress_store.ts:88-113,162`
   - What: the factory's closures reference the exported singleton `extractorProgressStore` by name instead of their own `update`.
   - Why: the "factory" can only ever produce one working instance.
6. **med** `Kiln/app/web_ui/src/lib/stores/rag_progress_store.ts:245-262`
   - What: the RAG store writes the global `progress_ui_state` (sidebar banner) directly.
   - Why: hidden store-to-store coupling.
7. **low** `Kiln/app/web_ui/src/lib/stores/copilot_connection_store.ts:9`
   - What: `let initialized` guard flag.
8. **low** `Kiln/app/web_ui/src/lib/stores/fine_tune_store.ts:6-8`
   - What: globals named `available_models_error` / `available_models_loading` that relate to fine-tune providers, not to `stores.ts:available_models`.
   - Why: misleading global names.
- Fine as designed: `jobs_dialog` (`lib/stores/jobs_dialog.ts:22`), `viewport` (lazy `readable` with teardown), `agentInfo` (`lib/agent.ts:9`).

### 5. Self-initializing modules / multiple entry points

1. **high** `Kiln/app/web_ui/src/lib/stores.ts:57,74-91`
   - What: at import it reads localStorage (`ui_state`) and subscribes to `ui_state` and `projects`. The subscriptions trigger `load_current_task` (network).
   - The root layout then calls `load_projects()`, and the `projects.subscribe` handler fetches the task. `Kiln/app/web_ui/src/routes/+layout.svelte:94` then calls `load_current_task` again, so the task is fetched twice.
   - Why: data flow is invisible from the entry point.
2. **high** `Kiln/app/web_ui/src/lib/stores/copilot_connection_store.ts:57-79`
   - What: `initCopilotConnectionStore()` is called from 3 places: `Kiln/app/web_ui/src/routes/(app)/chat_bar.svelte:161`, `Kiln/app/web_ui/src/routes/(app)/assistant/+page.svelte:56` and `builder/+page.svelte:629`.
   - It adds `window` "storage" and `document` "visibilitychange" listeners that are never removed, and it fires a network check.
   - Why: several components bootstrap a global; it should be wired once in `(app)/+layout.svelte`.
3. **med** `Kiln/app/web_ui/src/lib/stores/tools_store.ts:52-56` and `Kiln/app/web_ui/src/lib/stores/skills_store.ts:8-11`
   - What: `indexedDBStore(...)` runs at import, which opens an IndexedDB connection and starts a read for any module that imports a helper from `tools_store`.
4. **med** `Kiln/app/web_ui/src/lib/stores/index_db_store.ts:202-232`
   - What: every `indexedDBStore()` call starts a load and a persistent `store.subscribe` that is never unsubscribed.
   - The 4 page call sites create it inside functions: `Kiln/app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/+page.svelte:232` (a "read-only peek"), `builder/+page.svelte:501`, `generate/[project_id]/[task_id]/+page.svelte:188` and `synth/+page.svelte:224`. Each leaks an auto-saving store and its connection per call.
   - `local_storage_store.ts:3-5` documents the same "must be module-level singletons" constraint, but `indexedDBStore` doesn't, and its callers break it.
5. **med** `Kiln/app/web_ui/src/lib/stores/jobs_store.ts:176-186,219`
   - What: the singleton subscribes to `ui_state` at import.
   - Evidence: `Kiln/app/web_ui/src/lib/stores/jobs_store.test.ts:88-94` needs `vi.resetModules()` plus dynamic import "so … the module-level ui_state subscription start clean".
6. **med** `Kiln/app/web_ui/src/lib/stores/chat_ui_state.ts:8`
   - What: reads storage at import.
   - Evidence: `Kiln/app/web_ui/src/lib/stores/chat_ui_state.test.ts:4-27` has to `resetModules` and `doMock("$app/environment")` before re-importing.
   - 7 test files use `vi.resetModules`.
7. **low** Two bootstrap locations:
   - Sentry initializes in `Kiln/app/web_ui/src/hooks.client.ts:6`.
   - PostHog initializes inside the root `load()` in `Kiln/app/web_ui/src/routes/+layout.ts:9-19`, which also fires `setup_ph_user()` (a GET of `/api/settings`).
   - `update_update_store()` (a GitHub fetch) runs in `Kiln/app/web_ui/src/routes/(app)/+layout.svelte:70`.
   - Why: three different places start app-wide services. `/api/settings` is fetched independently in about 8 modules.
8. **low** `Kiln/app/web_ui/src/lib/stores.ts:368-375`
   - What: `available_model_details()`, a pure lookup used in reactive templates, calls `load_available_models()` as a hidden side effect.

### 6. Improper modules

1. **med** `Kiln/app/web_ui/src/lib/git_sync/api.ts:16-34,210-265`
   - What: a hand-rolled fetch client with hand-written response types (`:53-120`) for endpoints that `api_schema.d.ts` already types (12 git_sync paths).
   - The error-unwrap block `detail?.message || detail?.detail || …` is repeated 4 times in the same file (`:29,219,246,262`), and `getConfig`/`deleteConfig`/`oauthStatus` skip the file's own `request()` helper.
2. **med** Raw `fetch(base_url + …)` that bypasses the typed client:
   - `Kiln/app/web_ui/src/lib/ui/delete_dialog.svelte:17`
   - `Kiln/app/web_ui/src/lib/ui/edit_dialog.svelte:48`
   - `connect_providers.svelte:707,756`
   - Why: URL strings are passed as props (`delete_url`), so there's no type checking of paths or bodies.
3. **med** `Kiln/app/web_ui/src/lib/stores.ts:349-655` is a grab-bag.
   - What: about half the "stores" module is pure display/lookup helpers (`model_name`, `embedding_model_name`, `reranker_name`, `vector_store_name`, `provider_name_from_id` with a hard-coded `provider_name_map`, `prompt_name_from_id`, `rating_options_for_sample`, `get_model_friendly_name`).
   - Some read global stores through `get()` (`:421`, `:580`, `:650`), others take data as arguments.
   - `$lib/stores` (file) and `$lib/stores/` (folder) also coexist, and the folder's modules import back from the file (`Kiln/app/web_ui/src/lib/stores/run_configs_store.ts:5-9`).
4. **med** `Kiln/app/web_ui/src/lib/utils/formatters.ts:22-381`
   - What: generic helpers (`formatDate`, `formatSize`, `capitalize`) mixed with domain naming (`eval_config_to_ui_name`, `chunker_type_format`, `formatSpecType`, `toolServerTypeToString`, `structuredOutputModeToString`), with both naming styles in one file.
   - `Kiln/app/web_ui/src/lib/utils/` also mixes `.svelte` components (`form_container.svelte`, `form_element.svelte`, `task_run_picker.svelte`, `task_sample_selector.svelte`) in with pure utilities.
5. **low** `Kiln/app/web_ui/src/lib/stores/evals_store.ts:1-34`
   - What: not a store. It's one POST plus a posthog capture.
6. **low** Two SSE parsers:
   - `Kiln/app/web_ui/src/lib/utils/sse.ts:1-9` says it is "One line-splitting implementation for every consumer".
   - `Kiln/app/web_ui/src/lib/utils/sse_stream.ts:48-63` is a second implementation with different rules (splits events on `\n\n` and joins multi-line `data:`, but has no CRLF handling).
   - Native `EventSource` is also used in `rag_progress_store.ts:222`, `extractor_progress_store.ts:82` and `jobs_store.ts:138`.
7. **low** `Kiln/app/web_ui/src/config.ts:1-3`
   - What: `WebsiteName` etc. have no importers. Dead code.

### 7. Lazy-loading / caching gotchas

1. **high** `Kiln/app/web_ui/src/lib/stores.ts:258-280,290-311,321-342`
   - What: `"error_loading"` is terminal. One transient failure (e.g. server still starting) leaves the models, embeddings or rerankers list empty for the rest of the session.
   - `clear_available_models_cache()` (`:344-347`) resets only `available_models`. After connecting a provider in `connect_providers.svelte`, the embedding and reranker lists stay stale until reload.
2. **med** `Kiln/app/web_ui/src/lib/stores/fine_tune_store.ts:10-15` (`get_available_models` caches forever via `if (get(available_tuning_models)) return`) and `Kiln/app/web_ui/src/lib/stores.ts:352-356` (`load_model_info` same).
   - Why: invalidation happens ad hoc by callers. `connect_providers.svelte:480` sets `available_tuning_models.set(null)` by hand.
3. **med** `Kiln/app/web_ui/src/routes/(app)/models/price.ts:26-61`
   - What: the in-flight promise is cached even when it resolves to `null`, so pricing never retries.
4. **med** `Kiln/app/web_ui/src/routes/(app)/models/+page.svelte:192-213`
   - What: the page fetches `https://remote-config.getkiln.ai/kiln_config_v2.json` directly from the browser.
   - Why: this is a second source of truth for the model list, separate from `/api/providers/models` (which the backend fills from the same remote config). The URL is also hard-coded.
5. **med** Persisted-draft evolution without a schema version:
   - `builder/+page.svelte:513-575` and `Kiln/app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/builder/builder_draft.ts:87-100` handle every added field with `?? null` plus a history comment.
   - The synth draft key uses a hand-bumped `_v2` (`generate/.../+page.svelte:187`).
   - Why: there's no single migrate step, and restore logic grows with every field.
6. **low** `Kiln/app/web_ui/src/lib/api_client.ts:4-9`
   - What: `VITE_API_PORT` is read and the client built at import, hard-coded to `http://localhost`.
   - Acceptable for the desktop app, but `base_url` string concatenation is now spread across about 10 modules (see #6.2).
- Test evidence: `$lib/api_client` is `vi.mock`ed in 29 test files, `$lib/stores` in 22 and `posthog-js` in 12. Seven files need `vi.resetModules` because of import-time state.

### 8. Other

1. **med** `Kiln/app/web_ui/src/lib/utils/error_handlers.ts:64-84`
   - What: `createKilnError` always adds the prefix "Unexpected error:" and only reads `message`, `message.message` or `details`, never FastAPI's `detail`.
   - Callers hand-unwrap around it: `builder/+page.svelte:2126-2135` (the comment says createKilnError "would prefix 'Unexpected…'"), `:2293-2305` and `:3664-3676` (`error_detail`), plus `lib/git_sync/api.ts` ×4.
   - Why: there's no single "readable API error" function.
2. **med** About 197 hand-written `let x_error: KilnError | null = null` and 71 files with `let loading = true`.
   - Pages repeat a stale-response guard (`if (req_project_id !== project_id || …) return` ×3 per function), e.g. `Kiln/app/web_ui/src/routes/(app)/skills/[project_id]/[skill_id]/+page.svelte:36-62` and `Kiln/app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/+page.svelte:228-250`.
   - Why: missing shared async-resource helper.
3. **low** `alert()` used for error reporting in about 10 places, e.g. `Kiln/app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/[spec_id]/[eval_id]/+page.svelte:617,626,640`, `Kiln/app/web_ui/src/routes/(app)/settings/manage_projects/+page.svelte:74,95` and `Kiln/app/web_ui/src/lib/utils/logs.ts:18`.
   - Why: inconsistent with the `Warning`/`Dialog` error surfaces used elsewhere.
4. Noted, not a problem: `Kiln/app/web_ui/src/lib/utils/name_generator.ts` (2,866 lines) is just word lists, which is fine.

## Candidate rules

1. **No API calls in `+page.svelte` beyond a single loader.**
   - Put fetching and orchestration in a `.ts` module next to the page (`<page>_api.ts` / `<flow>.ts`) or in `lib/api/*`. Pages wire state to UI.
   - Any handler over about 60 lines, or one that calls more than one endpoint, belongs in a `.ts` module with unit tests.
   - Never copy a function into a test because it lives in a component. Extract it.
2. **Always use the typed `client` from `$lib/api_client`.**
   - Don't use `fetch(base_url + …)` for any route that exists in `api_schema.d.ts`, and don't hand-write response types for schema endpoints; use `components["schemas"][…]` via `$lib/types`.
   - Streaming endpoints are the only exception, and they go through one SSE helper.
3. **Turn errors into user text with one helper.**
   - Don't write `(error as {message?…})` unwrapping, `detail?.message || detail?.detail`, or a page-local `error_detail()`. Extend `createKilnError` (or add `api_error_message`) instead.
4. **Don't add another per-task cache store by copy-paste.** Use a shared keyed-resource factory that returns `{data, errors, loading, load(project_id, task_id, force)}`. The same applies to new "load once" global lists: use the shared loader, which must allow retry after error and must have a `reset()`.
5. **Store modules must not do I/O or subscribe at import.**
   - That means no `store.subscribe(...)` at module scope, no `indexedDBStore(...)` at module scope, no storage reads at module scope, and no fetches.
   - Expose `init_*()` and call it once from `routes/(app)/+layout.svelte` (or `hooks.client.ts` for app-wide services), with teardown.
   - Don't call `init*` from leaf components.
6. **Don't call `indexedDBStore()` / `localStorageStore()` inside a function or component.** They install never-removed subscriptions. For a read-only peek, use a read helper, not a live auto-saving store.
7. **No module-level mutable `let`s or maps outside a `createX()` factory.** A factory must use its own closure (`update`), never the exported singleton name. Any module-level state needs a test-reset hook.
8. **Pure lookup functions (`*_name`, `*_details`, `*_info`) must not trigger loads.** Callers load explicitly in `onMount` or the page loader.
9. **Persisted draft shapes get a `version` field and one `migrate_draft()` function.** Don't scatter `?? null` and "drafts written before…" comments through restore code, and don't hand-bump `_v2` keys. Define each storage key once, in the module that owns the shape.
10. **`lib/` must never import from `routes/`.**
    - A component used by more than one route tree moves to `lib/ui` (generic) or `lib/components` (domain).
    - Don't import across `(app)` and `(fullscreen)`; use `$lib/…` aliases instead of `../../../../` chains.
11. **Comments say why, never what or what used to be.**
    - Delete comments that restate the next line.
    - Don't mention removed buttons, old redirects or previous behaviour; that goes in the PR description.
    - Keep comments to 1–3 lines. A paragraph defending a guard means the code needs a better name or a helper.
12. **Don't put display-name helpers in `$lib/stores.ts` or generic formatters.** Put them in a domain module (e.g. `lib/utils/model_display.ts`, `lib/utils/rag_display.ts`). `formatters.ts` is for domain-free formatting only, with one naming style per module.
13. **After connecting or removing a provider, call one `invalidate_model_caches()`.** It must reset LLM, embedding, reranker, fine-tune and model-info caches. Don't null individual stores.
14. **Report errors in-page (`Warning`, dialog `error`).** Never `alert()`, and never `alert()` from a store.

## Refactor candidates

1. **Break up `builder/+page.svelte`.**
   - Scope: `Kiln/app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/builder/+page.svelte` plus siblings.
   - Move the drive pipelines (`on_drive_multi_turn`, `on_drive_single_turn`, `preflight_lanes`, `mint_inputs_from_plan`), calibration (`run_calibration_round`, `rejudge_all_traces`, `refine_judge_for_calibration`), save (`on_save`) and draft restore into `drive_flow.ts`, `calibration_flow.ts`, `save_flow.ts` and `builder_draft.ts`. Each should take explicit inputs and return results or state transitions.
   - Prune the narrative comments while doing it.
   - Size **L**. Risk **high**: complex state, few UI-level tests. Do it step by step behind existing `.test.ts` coverage for the flow modules.
2. **Keyed task-resource factory.**
   - Scope: `Kiln/app/web_ui/src/lib/stores/prompts_store.ts`, `run_configs_store.ts`, `rating_options_store.ts`, and possibly `load_available_tools` in `Kiln/app/web_ui/src/lib/stores.ts:183-248`.
   - Replace with `createTaskKeyedResource(fetcher)`. This also fixes the cache-check drift.
   - Size **S–M**. Risk **low**: exported names can stay.
3. **Load-once global list loader with retry and reset.**
   - Scope: `Kiln/app/web_ui/src/lib/stores.ts:250-366`, `Kiln/app/web_ui/src/lib/stores/fine_tune_store.ts`, `Kiln/app/web_ui/src/routes/(app)/models/price.ts`.
   - Add one `invalidate_model_caches()` and replace the 6 inline blocks in `connect_providers.svelte`.
   - Size **S**. Risk **low**. Fixes the stale-after-error and stale-embeddings bugs.
4. **API error helper plus typed git_sync and dialogs.**
   - Scope: `Kiln/app/web_ui/src/lib/utils/error_handlers.ts`, `Kiln/app/web_ui/src/lib/git_sync/api.ts`, `Kiln/app/web_ui/src/lib/ui/delete_dialog.svelte`, `edit_dialog.svelte`, `connect_providers.svelte:707,756`, and builder `error_detail`.
   - Teach `createKilnError` the `detail` and nested shapes, with an option to skip the "Unexpected error:" prefix. Move git_sync onto `client`. Change the dialogs to accept an async action instead of a URL.
   - Size **M**. Risk **med**: error text changes are visible to users and tests.
5. **Move store bootstrapping to the app entry point.**
   - Scope: `Kiln/app/web_ui/src/lib/stores.ts:74-91`, `Kiln/app/web_ui/src/lib/stores/jobs_store.ts:176-186`, `tools_store.ts:52`, `skills_store.ts:8`, `copilot_connection_store.ts:57`, `chat_ui_state.ts:8`, `Kiln/app/web_ui/src/routes/+layout.svelte`, `Kiln/app/web_ui/src/routes/(app)/+layout.svelte`, `Kiln/app/web_ui/src/routes/+layout.ts`.
   - Replace import-time subscriptions with `init_app_stores()` / teardown called once from the `(app)` layout, and remove the duplicate task fetch. Lets tests drop `vi.resetModules`.
   - Size **M**. Risk **med**: ordering of initial project/task load.
6. **Fix `indexedDBStore` lifecycle.**
   - Scope: `Kiln/app/web_ui/src/lib/stores/index_db_store.ts` plus the 4 page call sites.
   - Return a `destroy()` that unsubscribes and closes the connection, add a `read_indexed_db(key)` for peeks, and put each draft key and default shape in one module.
   - Size **S–M**. Risk **low–med**.
7. **Split `$lib/stores.ts` and `formatters.ts`.**
   - Scope: `Kiln/app/web_ui/src/lib/stores.ts:349-655` → `lib/utils/model_display.ts` (etc.); domain functions in `Kiln/app/web_ui/src/lib/utils/formatters.ts` → domain modules; `lib/stores/evals_store.ts` → `lib/api/evals.ts`.
   - Size **M** (many importers, mechanical). Risk **low**.
8. **Fix the import graph.**
   - Scope: the 4 `lib → routes` imports, the 8 `(app) → (fullscreen)` imports, `app_page.svelte` (84 importers).
   - Move `app_page.svelte`, `rating.svelte`, `run_input_form.svelte`, `edit_task.svelte`/`schema_section.svelte` and `create_extractor_dialog.svelte` into `lib/`, and add an ESLint `no-restricted-imports` rule for `routes/` from `lib/`.
   - Size **M** (mechanical). Risk **low**.
9. **Extract prompt templates out of the synth data model.**
   - Scope: `Kiln/app/web_ui/src/routes/(app)/generate/[project_id]/[task_id]/synth_data_guidance_datamodel.ts:502-1556` → `synth_templates.ts` (pure functions); consider moving them server-side.
   - Size **S–M**. Risk **low**.
10. **Merge SSE and progress-store code.**
    - Scope: `Kiln/app/web_ui/src/lib/utils/sse.ts`, `sse_stream.ts`, `Kiln/app/web_ui/src/lib/stores/extractor_progress_store.ts`, `rag_progress_store.ts`.
    - Use one SSE reader, a shared `progress_status()` / `format_progress_percentage()`, and give the extractor store its own closure instead of referencing the singleton.
    - Size **M**. Risk **med** (streaming behaviour).
