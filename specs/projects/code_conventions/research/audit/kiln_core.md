# Audit: `Kiln/libs/core/kiln_ai` (python SDK)

Scope: about 53k non-test lines. I skipped the static model data in `ml_model_list.py` except for how it is loaded and changed. All paths below are relative to the workspace root. The prefix `K/` stands for `Kiln/libs/core/kiln_ai/`.

## Summary

- **The `Config.shared()` singleton is the SDK's hidden dependency-injection system.** There are 61 non-test call sites in 17 files, including the datamodel base class (`created_by` default factory), adapters, fine-tune clients, tools and the MCP manager. Credentials, base URLs, the project registry, MCP secrets and the autosave flag are all read from `~/.kiln_ai/settings.yaml` deep inside library code, and nothing lets a caller pass them in. The root `Kiln/conftest.py` has autouse fixtures that reset the singleton and patch `settings_path`, and about 95 test files touch Config.
- **`Config` has real correctness bugs.**
  - Bool env vars are parsed with `bool(str)`. I checked this: `KILN_AUTOSAVE_RUNS=false` gives `True`, and so does `ENABLE_DEMO_TOOLS=0`.
  - The settings file wins over env vars, which is the opposite of the usual library rule.
  - Reads come from a cache loaded once in `__init__` and can go stale. Writes are non-atomic read-modify-write cycles with no inter-process lock, and the secrets file is created with default (world-readable) permissions.
- **Process-wide mutable module state is spread across layers:**
  - `built_in_models` is changed in place by a background thread.
  - `finetune_cache` is unbounded and never invalidated.
  - The vector-store `_adapter_cache` is never evicted.
  - `_trusted_projects` holds code-execution trust, which is security policy, in an eval adapter module.
  - The eval migration recursion set.
  - A sandbox `asyncio.Semaphore` is bound to the first event loop.
  - The `MCPSessionManager` singleton holds an `asyncio.Lock`.
  - `ModelCache`, `TemporaryFilesystemCache` and `strict_mode`.
  These are wrong for a multi-tenant host and make tests depend on reset hooks.
- **Importing or installing the library changes the host process:**
  - Importing `utils/dataset_import.py` raises the process-wide `csv.field_size_limit` to 100 MiB (checked).
  - `pdf_utils` registers an `atexit` hook at import.
  - The `pytest11` entry point means any pytest run in any environment with `kiln-ai` installed overwrites `sys.modules["kiln"]`.
  - `setup_litellm_logging` replaces `litellm.callbacks` outright.
  - `temporary_env` changes `os.environ` for the whole process.
  - The sandbox swaps `sys.modules["__main__"]`.
- **Application concerns live in the SDK:** the desktop project registry (`project_utils`, `datamodel/registry.py`), a tool that calls the desktop's own HTTP server on `127.0.0.1:8757`, RAG index storage under `~/.kiln_ai`, code-trust session state, file logging setup, and git-sync protocols in `utils/`. Also, `utils/litellm.py` imports `adapters/`, so `utils` sits above `adapters` instead of below it.
- **Provider knowledge is smeared across at least 5 places:** `Config` properties, `provider_warnings`, `provider_name_from_id`, `lite_llm_core_config_for_provider` (`provider_tools.py`), `get_litellm_provider_info` (`utils/litellm.py`), and the provider-specific `if` branches in `LiteLlmAdapter.build_extra_body`. Adding a provider touches all of them. `provider_tools.py` (844 lines) is a grab-bag.
- **The remote model list conflicts with static enums.** A remote config can add models that are not in the compiled `ModelName` enum. `default_structured_output_mode_for_model_provider` and `default_thinking_level_for_model_provider` call `ModelName(name)` and silently fall back to defaults for those models.
- **Comments point at docs and history that are not in the repo.** There are 26 references to "functional spec §X", "architecture §7" and "Phase 4/5" across eval code, but `libs/core/specs/projects/` holds only a `.gitkeep`. There are also a few classic diff comments (`# Fixed function name`, "prior bound of 8", "consistency with the old behavior").
- **God files:**
  - `datamodel/eval.py` (1655 lines): its validators do disk I/O and import a private jinja env.
  - `basemodel.py` (1041 lines): `.parent` attribute access silently loads from disk.
  - `litellm_adapter.py` (1023), `base_adapter.py` (983), `eval_runner.py` (963), `rag_runners.py` (893) and `cli/commands/package_project.py` (1121).
- **Blocking HTTP calls in async paths:**
  - `ollama_online` is `async` but calls sync `httpx.get`.
  - `resolve_ollama_model_variant` does a sync `requests.get` (5s timeout) every time an Ollama model id is resolved.
  - `requests` is not a declared dependency.
- **Packaging:** runtime dependencies include `coverage`, `pytest-cov`, `pytest-benchmark` and `pdoc`. Test helpers (`pytest_mock_files.py`, `pytest_test_output.py`, `adapters/pytest_*`, `_heavy_main_bench.py`) and every `test_*.py` ship inside the package, because there is no hatch exclude.

## Findings by category

### 1. Redundant comments

Redundant comments are fairly rare in this area. About 29 narrating one-liners match a grep, and they cluster in a few files.

- **low** `K/datamodel/external_tool_server.py:457-462`: `# Save any unsaved secrets first` and `# Call the parent save_to_file method` sit directly above `super().save_to_file()`. Also `:414` `# Check if secrets are already saved`, `:440`, `:310`, `:323`. The file is mostly comments that restate the code.
- **low** `K/tools/kiln_task_tool.py:119,124`: `# Load the project first` / `# Load the task from the project` restate the next line.
- **low** `K/adapters/model_adapters/mcp_adapter.py:61,179`: `# Get the actual tool from tool registry`, `# Build single turn trace` (before `_build_single_turn_trace`).
- **low** `K/adapters/model_adapters/litellm_adapter.py:146,177`: `# Build completion kwargs for tool calls` before `build_completion_kwargs`.
- **low** `K/utils/logging.py:137,155,159,165`: narrates each step of `setup_litellm_logging` ("Create a new logger for model calls", "Tell litellm to use our custom logger"). Also `:79` `# No op` before `pass`.
- **low** `K/datamodel/strict_mode.py:12-24`: the docstrings "Get the current strict mode setting." and "Set the strict mode setting." just repeat the function names.
- **low** `K/tools/base_tool.py:72-87`: "Return the tool name (function name) of this tool." and similar docstrings repeat the method names.
- **low** `K/adapters/ml_model_list.py:13-17`: a module "docstring" placed after the imports, so it is a no-op string. It is also inaccurate: the module does not handle "instantiation of language models".
- **low** `K/adapters/ollama_tools.py:17-22`: the docstring says "using environment variable if set". It actually reads Config, where env is only a fallback. This comment is misleading, not just redundant.

### 2. Zigzag / diff-dependent comments

- **high (pattern)** 26 references to planning docs that are missing from the repo (`Kiln/libs/core/specs/projects/` contains only `.gitkeep`):
  - `K/cli/commands/migrate_eval_runs.py:5-11, 283, 330, 356, 414, 434, 483, 507-509, 542, 570, 607, 647`: "functional spec §2", "architecture §7", "Phase 4's fallback", "since Phase 4, an eval-generated run can't be deleted".
  - `K/adapters/eval/eval_runner.py:79, 187, 281, 694, 721-722, 746`: "Phase 5 migrates old calibration skips".
  - `K/adapters/eval/trace_index.py:5,13,121,147`.
  - `K/datamodel/code_file_storage.py`, `K/datamodel/eval.py`.

  Readers cannot resolve these, and "Phase N" only means something during the project that produced the code.
- **med** `K/tools/sandbox_bridge.py:38-41`: the `CODE_SANDBOX_MAX_CONCURRENCY` docstring says "Raises code tools' prior bound of 8 as a side effect of unifying the pool (arch §3.4)". It describes the diff, not the constant.
- **med** `K/tools/tool_registry.py:85-87`: `mcp_server_and_tool_name_from_id(tool_id)  # Fixed function name`. This is a pure leftover from a diff.
- **med** `K/datamodel/external_tool_server.py:446`: `# Always call update_settings to maintain consistency with the old behavior`. Also the `save_to_file` docstring at `:450-455`: "preventing the issue where secrets could be lost…".
- **med** `K/datamodel/task_run.py:261`: `# Avoid circular import at module load.` before `from kiln_ai.datamodel.datamodel_enums import TurnMode`. `datamodel_enums.py` imports only `enum`/`typing`, so there is no cycle. The comment and the local import are both stale.
- **low** `K/adapters/remote_config.py:33`: "V2 explained: Kiln v0.18 was the first release with remote config, but had bugs. We no longer publish v1 URL…". This is history that belongs in the changelog.
- **low** `K/adapters/eval/_heavy_main_bench.py:14-16`: "the exact bug this benchmark catches. The scorer now spawns through `run_bridged_child`… to keep the fix."
- **low** `K/adapters/remote_config.py:222-223`: the docstring says "This is not thread safe, only asyncio is safe. If you call this from threads, make sure to wrap in an actual lock". The function already takes `refresh_lock`, and its only caller runs it in a thread. The docstring predates the lock.
- Legitimate (not flagged): the many "Legacy …" comments in `datamodel/*` and `provider_tools.py` that explain on-disk back-compat migrations. Those are durable facts about stored data.

### 3. Poor modularization

- **high** Provider knowledge is spread across at least 6 sites, and adding a provider means editing all of them:
  - `K/utils/config.py:50-184`: one key or env-var pair per provider.
  - `K/adapters/provider_tools.py:575-649` (`provider_warnings`).
  - `K/adapters/provider_tools.py:519-571` (`provider_name_from_id`).
  - `K/adapters/provider_tools.py:652-844` (`lite_llm_core_config_for_provider`).
  - `K/utils/litellm.py:21+` (`get_litellm_provider_info`).
  - `K/adapters/model_adapters/litellm_adapter.py:536-648` (`build_extra_body`, which has hard-coded OpenRouter provider order lists and R1/DeepInfra special cases). The code itself admits this at `:537-539`: "Don't love having this logic here… Should figure out how I want to isolate this".

  A per-provider descriptor or registry would collapse these.
- **high** `K/adapters/provider_tools.py` (844 lines) mixes provider enablement checks (which do network calls to Ollama/Docker), user model registry parsing, legacy custom models, fine-tune lookup through the global project registry (`:282-308`), parser selection, LiteLLM credential assembly, and display names.
- **high** `K/datamodel/eval.py` (1655 lines) mixes about 30 classes: property schemas, scorer filename constants, score validation, migrations, template compilation and recursion-guard globals. `Eval.upgrade_old_reference_answer_eval_config` (`:1521-1563`) loads child files from disk inside a pydantic `model_validator`. `EvalConfig.validate_v2_templates_and_expressions` (`:1222-1250`) imports `jinja2.meta` and the private `_template_env` from `utils/jinja_engine.py` inside a validator.
- **med** `K/datamodel/basemodel.py` (1041 lines): the file-backed persistence engine, caching, the parent/child metaprogramming (`__init_subclass__` method injection, `:866+`), attachment file handling and name validation all live in one module.
- **med** `K/adapters/model_adapters/base_adapter.py:222-367`: `_run_returning_run_output` is about 145 lines covering validation, input transform, formatting, the model call, parsing, schema validation, the reasoning-required check, building the run, deciding whether to autosave (via a global) and error wrapping.
- **med** Other god files: `K/adapters/model_adapters/litellm_adapter.py` (1023), `K/adapters/eval/eval_runner.py` (963), `K/adapters/rag/rag_runners.py` (893), `K/cli/commands/package_project.py` (1121), `K/cli/commands/migrate_eval_runs.py` (870, a one-shot migration living permanently in the SDK CLI), `K/synthetic_user/runner.py` (704).
- **med** `K/adapters/remote_config.py:99-195`: three near-identical copy-pasted validate-providers-then-model loops for models, embedding models and rerankers. One generic helper would replace them.
- **med** `K/adapters/fine_tune/fireworks_finetune.py:82-88, 169-172, 259-262`: the "read Config key and account id, raise if missing" block is pasted three times, even though `api_key_and_account_id()` exists at `:367-372` for exactly this.
- **low** `K/utils/name_generator.py` (2880 lines) is static word lists in a `.py` file. It would be better as a data file.

### 4. Globals

- **high** `K/utils/config.py:35, 234-238`: the `Config._shared_instance` lazy singleton. It is not thread-safe on creation, and tests reset it by poking `_shared_instance` (`Kiln/conftest.py:67-72`, `K/tools/test_mcp_session_manager.py:134`). Used from 17 modules (see #7).
- **high** `K/adapters/eval/v2_eval_code_eval.py:27-51`: `_trusted_projects: set[str]` is process-wide "code trust" (permission to execute user code), keyed by project path. Only the desktop app uses it (`Kiln/app/desktop/studio_server/eval_api.py:3347`). This is a security decision kept as module state in an SDK adapter, and it would leak across tenants in a server. It has a test-only `_reset_add_code_trust`.
- **high** `K/adapters/remote_config.py:229-232`: `built_in_models[:] = …` (and the embedding and reranker lists) changes module-level lists that about 15 modules import by name and iterate without the lock, for example `K/adapters/provider_tools.py:116,152,501` and `K/adapters/ml_model_list.py:10589-10604`. The writer runs on a daemon thread (`refresh_model_list_background`, `:235-255`). Readers can see a half-swapped world, and nothing can be scoped per caller.
- **med** `K/adapters/provider_tools.py:282-308`: `finetune_cache: dict[str, Finetune]` is an unbounded process-wide cache. It is never invalidated, so a deleted or edited fine-tune stays cached, and it is keyed by IDs with no tenant or project root.
- **med** `K/adapters/vector_store/vector_store_registry.py:16-19`: `_adapter_cache` is never evicted. It holds LanceDB handles for every RAG config ever touched, keyed only by `rag_config.id`.
- **med** `K/tools/sandbox_bridge.py:46-47, 93-102`: a process-global `asyncio.Semaphore`, lazily created and bound to the first event loop that uses it. A second loop, such as the `asyncio.run` in the remote-config thread, other `asyncio.run` callers, or tests, gets "bound to a different event loop". The `_bridge_executor` (`:63-90`) is a deliberate singleton and is documented as one.
- **med** `K/tools/mcp_session_manager.py:40-58`: the `MCPSessionManager` singleton holds an `asyncio.Lock()` and live `ClientSession`s. These have the same loop-affinity problem. Tests reset it through `_shared_instance = None`.
- **med** `K/datamodel/eval.py:54-57`: the `_migration_lock` / `_currently_migrating_eval_ids` module set exists only to stop validator recursion caused by doing disk I/O in a validator.
- **med** `K/datamodel/model_cache.py:29-46`: the `ModelCache` singleton is unbounded, so memory grows with every file read. `_check_timestamp_granularity` (`:107-129`) probes the filesystem of the package's own `__file__`, not the project directory, so caching can be enabled on a project volume with coarse mtimes.
- **low** `K/utils/filesystem_cache.py:57-72`: the `TemporaryFilesystemCache` singleton creates a temp dir on first use and never cleans it up.
- **low** `K/datamodel/strict_mode.py:9-24`: a global `_strict_mode` flag toggled by the app. This is documented, but it is process-wide validation behaviour.
- **low** `K/utils/pdf_utils.py:16-24`: the `global _pdf_conversion_executor` lazy `ProcessPoolExecutor` has no lock. The comment "singleton so dev-server reloading doesn't recreate the executor" is doubtful, because a module reload resets it.
- **low** `K/tool_testing/plugin.py:24-28`: a process-global `FakeToolBridge()` created at plugin import.

### 5. Self-initializing modules / import-time side effects / multiple entry points

- **high** `Kiln/libs/core/pyproject.toml:54-55` and `K/tool_testing/plugin.py:31-38` → `K/sandbox/tools_surface.py:154-156`: the `pytest11` entry point loads automatically in every pytest session of any environment where `kiln-ai` is installed, including third-party projects and `kiln_server`. `pytest_configure` then writes synthetic modules into `sys.modules["kiln"]`, `["kiln.tools"]` and `["kiln.async_tools"]`, which shadows any real package called `kiln`.
- **high** `K/utils/dataset_import.py:32`: `csv.field_size_limit(100 MiB)` runs at import and changes the stdlib `csv` module for the whole host process. I checked this: the limit goes from 131072 to 104857600 just by importing.
- **high** `K/utils/logging.py:136-166` (`setup_litellm_logging`): this library function assigns `litellm.callbacks = [CustomLiteLLMLogger(...)]`, dropping any callbacks the host registered (Langfuse, PostHog, …). It also forces the `"LiteLLM"` logger to ERROR, attaches a rotating file handler to a non-namespaced `"ModelCalls"` logger with `propagate=False`, and creates `~/.kiln_ai/logs`. Its only callers are the desktop entry point (`Kiln/app/desktop/desktop_server.py:133`) and `Kiln/conftest.py:43-46`, so it belongs in app code. The module also imports `litellm` at the top level.
- **med** `K/utils/pdf_utils.py:93`: `atexit.register(_shutdown_pdf_conversion_executor)` runs at import time, whether or not PDFs are ever used.
- **med** `K/utils/env.py:5-15` used at `K/adapters/vector_store/lancedb_adapter.py:89`: `temporary_env("OPENAI_API_KEY", "fake-api-key")` changes `os.environ` for the whole process. Any concurrent thread (FastAPI threadpool, the remote-config thread) that reads `OPENAI_API_KEY` during that window sees the fake key. It works around a llama_index default instead of passing an explicit mock embed model.
- **med** `K/sandbox/spawn.py:48-62`: swaps `sys.modules["__main__"]` for the whole process around `p.start()`. It is serialized by a module lock, but host code on other threads can still observe it. It is well documented, but it is a host-visible mutation coming from library code.
- **low** `K/adapters/remote_config.py:235-255`: `refresh_model_list_background` starts a daemon thread that runs its own `asyncio.run` and changes the globals above. It is wired from the app entry point (`Kiln/app/desktop/desktop_server.py:135-136`), which is good, but the opt-out is an env var read in the library (`:39-41`, `KILN_SKIP_REMOTE_MODEL_LIST`) that the root conftest has to set for every test (`Kiln/conftest.py:52-59`).
- Good: `K/adapters/__init__.py` is lazy (PEP 562), and no `logging.basicConfig` calls exist in the library.

### 6. Improper modules

- **med** Layering inversion: `K/utils/litellm.py:3-7` imports from `kiln_ai.adapters.*` (`ml_model_list`, `ollama_tools`, `reranker_list`), and `K/utils/project_utils.py` imports `datamodel.project`. `utils` is not a leaf layer. `K/utils/test_import_layering.py` exists precisely because of a past cycle.
- **med** About 12 cycle-avoidance function-local imports between tools, adapters and the registry:
  - `K/tools/tool_registry.py:61-67, 137-161`
  - `K/tools/built_in_tools/llm_tools.py:80-88, 282-283` ("avoid the tools -> adapter -> tool_registry cycle")
  - `K/datamodel/dataset_split.py:172-173`
  - `K/datamodel/eval.py:721, 1230-1240`

  `tools` and `adapters` depend on each other in both directions.
- **med** `K/datamodel/eval.py:1240`: imports the private `_template_env` from `K/utils/jinja_engine.py:94`. Validation needs a public "referenced variables" helper.
- **med** App-only modules in the SDK utils grab-bag:
  - `K/utils/git_sync_protocols.py` (desktop git-sync save contexts threaded through `eval_runner`, `rag_runners`, `extractor_runner`, `synthetic_user/runner`)
  - `K/utils/project_utils.py` and `K/datamodel/registry.py` (the desktop's project list)
  - `K/utils/logging.py` (desktop file logging)
- **low** Test-support code ships as importable package modules: `K/pytest_mock_files.py`, `K/pytest_test_output.py`, `K/adapters/pytest_embedding_fanout.py`, `K/adapters/pytest_prerelease_whitelist.py`, `K/adapters/eval/_heavy_main_bench.py`. All `test_*.py` files sit beside the source with no hatch `exclude` in `Kiln/libs/core/pyproject.toml`.
- **low** `K/datamodel/__init__.py` is a large flat re-export that eagerly imports every datamodel submodule. That is fine as an API surface, but it means `import kiln_ai.datamodel` pulls in jinja, jsonschema and the rest.

### 7. Config gotchas (lazy-loading singleton, env reads, config from library code)

- **high** `K/utils/config.py:268-270, 278`: values are coerced with `property_config.type(value)`. For `bool` properties that means `bool("false") is True`. I checked this: `KILN_AUTOSAVE_RUNS=false` gives `autosave_runs == True`, and `ENABLE_DEMO_TOOLS=0` gives `True`. The env var for these flags cannot turn them off.
- **high** `K/utils/config.py:258-270`: the order is settings.yaml, then env var, then default. A stray `~/.kiln_ai/settings.yaml` therefore overrides `OPENAI_API_KEY` and similar env vars, which is the reverse of 12-factor and of what SDK users expect. On a server this means credentials come from the home directory of whichever user runs the process.
- **high** Credentials and endpoints are read from the global inside adapters and fine-tune clients at call time, with no injection point:
  - `K/adapters/provider_tools.py:665-805`: about 20 `Config.shared().<provider>_api_key` reads, plus the direct `os.getenv("OPENROUTER_BASE_URL")` / `os.getenv("SILICONFLOW_BASE_URL")` at `:665,677`.
  - `K/adapters/model_adapters/jev_adapter.py:221`.
  - `K/adapters/fine_tune/fireworks_finetune.py:83-84,169-170,187-189,259-260,368-369`, `together_finetune.py:43,140-141`, `vertex_finetune.py:217-218`.
  - `K/adapters/ollama_tools.py:23`, `K/adapters/docker_model_runner_tools.py:19`.

  `adapter_for_task` (`K/adapters/adapter_registry.py:156`) accepts no credentials or config object.
- **high** `K/datamodel/basemodel.py:339-342`: `created_by: str = Field(default_factory=lambda: Config.shared().user_id)`. Constructing any datamodel object instantiates the Config singleton and reads `~/.kiln_ai/settings.yaml`, then falls back to `getpass.getuser()`. In a multi-tenant server every record is stamped with the OS user unless it is overridden.
- **high** Autosave is decided from a global inside the adapter: `K/adapters/model_adapters/base_adapter.py:340, 521` and `K/adapters/model_adapters/mcp_adapter.py:188` check `Config.shared().autosave_runs`. `AdapterConfig.allow_saving` already exists for this, so the policy has two sources.
- **med** `K/utils/config.py:232, 263-265`: `_settings` is loaded once in `__init__`. Reads never reload, so edits by another process (the desktop app or a CLI) are invisible until this process writes. Writes do a fresh read-modify-write (`:367-377`) with no file lock (the `threading.Lock` is per instance) and a non-atomic `open("w")`, so a crash mid-dump truncates the file. The comment "Fresh load to avoid clobbering changes from other instances" (`:368`) only half-solves this.
- **med** `K/utils/config.py:280-290`: `__setattr__` turns assignment into disk I/O. `Config.shared().foo = x` silently rewrites `settings.yaml` for non-`in_memory` keys, and for `in_memory` keys it only updates process memory. The same syntax has two very different behaviours.
- **med** The global project registry is used for lookups inside the SDK:
  - `K/utils/project_utils.py:7-19` (`project_from_id` scans `Config.projects`), used by `K/adapters/provider_tools.py:293` (resolving fine-tunes) and `K/tools/kiln_task_tool.py:118-120` (the sub-task tool).
  - `K/datamodel/registry.py:5-16`.

  A library user who loads projects by path, or `kiln_server`, cannot use fine-tuned models or task tools unless the project is in the home-dir yaml.
- **med** `K/tools/tool_registry.py:53-58`: the `CALL_KILN_API` tool reads `Config.shared().kiln_local_api_base_url()`, an in-memory value "the server must set before starting". The `if not api_base_url` guard is dead code, because the f-string is never empty and so always defaults to `http://127.0.0.1:8757`.
- **med** `~/.kiln_ai` is a hidden storage root:
  - `K/adapters/vector_store/lancedb_adapter.py:321-325`: RAG indexes live outside the project, keyed by `rag_config.id`.
  - `K/tools/mcp_session_manager.py:285`: MCP cwd.
  - `K/utils/logging.py:24`.

  `settings_dir(create=True)` makes the directory on read paths. Tests have to patch `Config.settings_dir` (see the comment at `Kiln/conftest.py:35-40`).
- **med** `K/datamodel/external_tool_server.py:376-447`: `save_to_file()` on a datamodel also writes MCP secrets into the global `settings.yaml` (`_save_secrets`). One persistence call writes to two stores, one of which is per-user.
- **low** `K/tools/mcp_session_manager.py:465`: `custom_mcp_path` is read from Config. `get_shell_path` runs a login shell (`$SHELL -l -c 'echo $PATH'`) and caches the result on the singleton.
- **low** `K/adapters/remote_config.py:39-41`: `should_skip_remote_model_list()` reads an env var instead of taking a parameter.
- **Test evidence:** `Kiln/conftest.py:67-81` has autouse `reset_config` (pokes `Config._shared_instance`), `use_temp_settings_dir` (patches `Config.settings_path`) and `skip_remote_model_list` (sets the env var). Core tests also contain about 26 instances of `patch("kiln_ai.utils.config.Config.shared")`, 14 of `patch("kiln_ai.utils.project_utils.Config.shared")`, 17 of `patch("kiln_ai.adapters.provider_tools.Config…")` and 14 of `patch.object(Config, …)`, across 95 test files that reference Config.

### 8. Other significant maintainability flags

- **med** Blocking HTTP calls in async code:
  - `K/adapters/ollama_tools.py:29-40`: `async def ollama_online()` calls sync `httpx.get` with no timeout.
  - `:157`: `get_ollama_connection` (async) calls `requests.get`.
  - `:190`: `resolve_ollama_model_variant` calls `requests.get(timeout=5)`. It is called from `K/utils/litellm.py:100-104` each time an Ollama provider is resolved for a call.

  `requests` is not declared in `Kiln/libs/core/pyproject.toml`.
- **med** `K/adapters/ml_model_list.py:10607-10649` (with `K/adapters/remote_config.py`): `default_structured_output_mode_for_model_provider` and `default_thinking_level_for_model_provider` call `ModelName(model_name)`. Models added only through the remote config, whose names are not in the compiled enum, quietly get default modes instead of their configured ones. `get_model_by_name` is typed `ModelName`, but `KilnModel.name` is `str`.
- **med** `K/datamodel/basemodel.py:561-564, 569-593`: `KilnParentedModel.__getattribute__` makes `obj.parent` do a disk load. The I/O is hidden in attribute access, and it is the root cause of the validator recursion that `eval.py` guards with a global.
- **med** `K/utils/config.py:375-376`: `settings.yaml`, which holds API keys, PAT/OAuth tokens and MCP secrets, is written with the default umask (usually 0644) and no `chmod 600`.
- **med** `Kiln/libs/core/pyproject.toml:20-49`: runtime dependencies include dev tools (`coverage`, `pytest-cov`, `pytest-benchmark`, `pdoc`) and heavy optional stacks (`google-cloud-aiplatform`, `vertexai`, `lancedb`, `llama-index`, `together` from a personal git fork). Every SDK user pays for them.
- **low** `K/utils/logging.py:36-76`: the custom LiteLLM logger writes full request curl commands, headers and every message (user data) to `~/.kiln_ai/logs/model_calls.log` at INFO. It relies on litellm's curl helper to mask auth headers.

## Candidate rules

1. **Never call `Config.shared()` in new `libs/core` code outside the app-facing edge** (`cli/`, or a single `config_from_settings()` adapter). Take credentials, base URLs, the autosave policy and the user id as constructor or function parameters, or as a `ProviderCredentials`/`KilnRuntimeConfig` object passed in. Existing call sites are tech debt, so do not add more.
2. **The SDK must not mutate host-process globals.** No changes to `litellm.callbacks`/`litellm.*`, `logging.getLogger(...).setLevel/addHandler`, `csv.field_size_limit`, `os.environ`, `sys.modules`, or `atexit` from importable library code. If a host-level setting is needed, expose `setup_*()` functions that the app entry point (`app/desktop/desktop_server.py`) calls, and keep them additive: append to `litellm.callbacks`, never replace it.
3. **No work at import time.** Module top level may only define things. No I/O, threads, executors, env reads, registrations or global-library tweaks. Lazily created resources go behind an explicit, injectable owner, not a module `global`.
4. **No new module-level mutable caches or registries** (`dict`/`set`/list mutated at runtime). If a cache is truly needed, it must have an owner object, a bound or eviction policy, and an invalidation path, and it must not be keyed only by IDs in code that can run multi-tenant. Never put permission or trust state (like `_trusted_projects`) in module globals.
5. **Never create `asyncio.Lock`/`Semaphore`/`Event` in a module global or a process singleton.** They bind to the first event loop. Create them per loop or per owner.
6. **Parse config values with real parsers.** Bools from env must go through an explicit `"1"/"true"/"yes"` parser. Never call `bool(str)`. When adding a `ConfigProperty`, add a test that sets the env var to a false value.
7. **No blocking I/O in `async def`** in adapters or tools. Use `httpx.AsyncClient` with a timeout. Never use `requests` in core: it is not a declared dependency.
8. **Datamodel validators must be pure.** No disk reads, no `self.configs()`/`.parent` traversal, and no imports of private helpers from other modules inside validators. Put migrations in explicit load hooks or the migration CLI.
9. **Adding a provider:** update the single provider descriptor (once it exists). Until then, the checklist is `Config` property, `provider_warnings`, `provider_name_from_id`, `lite_llm_core_config_for_provider`, `utils/litellm.get_litellm_provider_info`, and any `build_extra_body` branches. Grep for `ModelProviderName.<x>` to find them all.
10. **Never index model lookups through the `ModelName` enum.** The remote config can deliver names that are not in it, so compare against `KilnModel.name` strings. Treat `built_in_models` as read-only outside `remote_config.refresh_model_list`.
11. **Comments must make sense without the diff or the planning docs.** No "Phase N", "functional spec §x", "architecture §y", "now", "no longer", "fixed", "old behavior", or "prior bound". State the invariant or reason directly, and put history in the PR or changelog.
12. **`utils/` must not import `adapters/`, `tools/` or `datamodel/`.** Put helpers that need those in the layer that owns them.
13. **Tests:** do not add new `patch("...Config.shared")` calls. Prefer passing values in. Remember that the root `Kiln/conftest.py` already resets the singleton and redirects `settings_path`.

## Refactor candidates

1. **Inject runtime config into adapters.** Introduce a `ProviderCredentials` (or `KilnRuntimeConfig`) value object built once by the app from `Config`. Thread it through `adapter_for_task` → `litellm_core_provider_config` → `lite_llm_core_config_for_provider`, plus the fine-tune adapters and the `JevAdapter` client. Keep a default that falls back to `Config.shared()` for back-compat.
   - Scope: `adapters/provider_tools.py`, `adapters/adapter_registry.py`, `adapters/fine_tune/*`, `adapters/model_adapters/jev_adapter.py`, `ollama_tools.py`, `docker_model_runner_tools.py`. Size: **L**. Risk: med, since the public API changes and many tests patch `Config`.
2. **Fix and harden `Config`.**
   - Use a real bool parser.
   - Decide and document the precedence; env should probably beat the file.
   - Reload on mtime change.
   - Write atomically (tmp + `os.replace`), use `0600` permissions, and take a cross-process file lock.
   - Replace `__setattr__` disk writes with explicit `save_setting`.
   - Make `shared()` thread-safe.

   Scope: `utils/config.py` (+ tests). Size: **M**. Risk: med, because changing the precedence changes user-visible behaviour, so ship it with release notes.
3. **Move app-only concerns out of the SDK:** `setup_litellm_logging`/`get_log_file_path`, the `project_utils`/`datamodel/registry.py` project registry, the code-trust set, and the `git_sync_protocols` contexts move to `app/desktop`, or become injectable hooks. Change `project_from_id` callers (`finetune_from_id`, `KilnTaskTool`) to take a project resolver. Size: **M**. Risk: low-med.
4. **Remove import- and install-time side effects:**
   - Apply the `csv.field_size_limit` change inside the import function (and restore it afterwards), or use a reader that respects a local limit.
   - Drop the import-time `atexit` in `pdf_utils` in favour of an owner object.
   - Make the `pytest11` plugin opt-in (`-p kiln_ai.tool_testing.plugin`) or install the `kiln` shim only when a test requests the fixture.
   - Replace `temporary_env` in LanceDB with an explicit `MockEmbedding`.

   Size: **S-M**. Risk: low. Note that the plugin change affects tool authors.
5. **Single provider registry.** Build one `ProviderSpec` table: config keys, display name, warning message, LiteLLM provider name and base URL, and extra-body hooks. Generate `provider_warnings`, `provider_name_from_id`, `lite_llm_core_config_for_provider` and `get_litellm_provider_info` from it, and move the OpenRouter/Anthropic/R1 branches out of `LiteLlmAdapter.build_extra_body` into per-provider hooks. Scope: `provider_tools.py`, `utils/litellm.py`, `litellm_adapter.py`, `config.py`. Size: **L**. Risk: med, but the existing tests cover it well.
6. **Model-list store object.** Replace the module-global `built_in_models[:]` mutation with a `ModelCatalog` that has an atomic snapshot swap. Readers get an immutable tuple, and lookups go by string name rather than the `ModelName` enum. Deduplicate the three copy-pasted deserialize loops in `remote_config.py`. Size: **M**. Risk: low-med.
7. **Scope the process caches.** Give `finetune_cache`, the vector-store `_adapter_cache`, `ModelCache`, `MCPSessionManager` and the sandbox semaphore an owner with bounds and invalidation, and make the asyncio primitives loop-aware. Size: **M**. Risk: med, because these caches exist for LanceDB and performance reasons.
8. **Split `datamodel/eval.py`** into property schemas, run records, config, eval and splits, and move the on-load migrations and the jinja validation out of validators. Also split `provider_tools.py` (user models, fine-tune resolution, LiteLLM config, provider display). Size: **M-L**. Risk: low-med, since it is mostly mechanical, but the datamodel import order is fragile; see `utils/test_import_layering.py`.
9. **Make Ollama probes async.** Use `httpx.AsyncClient` with timeouts in `ollama_tools.py`, and cache variant resolution per connection instead of making an HTTP call for each model-id resolution. Size: **S**. Risk: low.
10. **Packaging cleanup.** Move `coverage`, `pytest-*` and `pdoc` to dev dependencies. Exclude `test_*.py`, `pytest_*.py` and `_heavy_main_bench.py` from the wheel. Consider extras for vertex, lancedb and llama-index. Size: **S-M**. Risk: low-med, because some downstream users may rely on the transitive dependencies.
11. **Comment sweep.** Rewrite the 26 spec/phase references and the zigzag comments listed in #2 as self-contained explanations, and delete the stale "circular import" comment and local import in `task_run.py:261`. Size: **S**. Risk: none.
