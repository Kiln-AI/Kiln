# Area reference: `libs/core` (the `kiln_ai` SDK)

`kiln_ai` is a library that third parties install. Code here runs inside someone else's process (the desktop app, kiln_server, a user's script or notebook), so the library rules (rules.md §F) apply with full force.

## Gotchas

### `Config` (`kiln_ai.utils.config.Config`)

- **Precedence: the stored value wins over the env var.** Each property is either in-memory (`ConfigProperty(in_memory=True)`) or file-backed. `Config.__getattr__` returns the stored value first (the in-memory value, or the value in `~/.kiln_ai/settings.yaml`), then the property's `env_var`, then its default. So a value saved in settings.yaml can't be overridden from the environment. This is the documented behaviour; don't change it in passing.
- **The file is read once.** `Config.__init__` loads settings.yaml into `_settings`, and reads never reload it. Edits by another process stay invisible to this one until it writes.
- **Assignment is disk I/O.** `Config.shared().foo = x` rewrites settings.yaml for a file-backed key (via `update_settings`) and only touches memory for an in-memory key. Prefer the explicit `save_setting(name, value)`.
- **Read-modify-write of lists and dicts isn't atomic.** `update_settings` locks one write, not the read before it. `projects = config.projects; projects.append(p); config.save_setting("projects", projects)` can lose a concurrent update.
- **`Config.shared()` is a lazy process singleton** (`Config._shared_instance`). The root `conftest.py` resets it before and after every test (`reset_config`) and points `Config.settings_path` at `tmp_path` (`use_temp_settings_dir`), so tests never touch the real file. Don't add new `patch("...Config.shared")` calls; pass the value in instead.
- **No new `Config.shared()` in `kiln_ai/`** (gate: `core-config-shared`). Credentials, base URLs, the autosave policy and the user id come in as parameters. `AdapterConfig.allow_saving` already exists for the autosave decision.

### The model list (`kiln_ai.adapters.ml_model_list`)

- **`built_in_models` is replaced at runtime.** `remote_config.refresh_model_list` swaps its contents in place (`built_in_models[:] = …`, under `refresh_lock`) from a background thread started by `refresh_model_list_background`. Treat the list as read-only, iterate it fresh each time, and never keep a reference to a slice or a filtered copy across calls. The embedding and reranker lists behave the same way.
- **`ModelName` is not the set of valid model names.** The remote list can add models whose names aren't members of the shipped `ModelName` enum, and `KilnModel.name` is a `str`. Compare against `KilnModel.name` strings; never validate or type user-provided model ids with `ModelName`. `ModelName` is fine for constants chosen at build time and inside the model list itself.
- `KILN_SKIP_REMOTE_MODEL_LIST=true` (`should_skip_remote_model_list`) turns the refresh off; the root `conftest.py` sets it for every test.

### Adapters are the hot path

- `BaseAdapter` and `LiteLlmAdapter` are the core run loop; a process may run hundreds of them concurrently. No blocking I/O, no per-call file reads, no per-call client construction. Read files once and pass the result in.
- `ollama_tools.ollama_online` and `resolve_ollama_model_variant` make synchronous HTTP calls today. Don't copy that pattern into async code (rules.md §G).

### Datamodel

- Validators and `default_factory` are pure (rules.md D14). Existing exceptions to know about: `KilnBaseModel.created_by` defaults through `Config.shared().user_id`, `Eval.upgrade_old_reference_answer_eval_config` loads child files inside a validator, and `KilnParentedModel.parent` loads from disk on attribute access. Don't add more; put migrations in an explicit load step or a `cli/commands` migration.
- On-disk back-compat ("legacy" fields upgraded on load) is normal and stays. Describe the stored shape in the comment, not the history (rules.md A1).

### The SDK must not mutate its host

- Host-level setup is exposed as a function the app calls, never run at import. `kiln_ai.utils.logging.setup_litellm_logging` is the example: the desktop app calls it from its startup. Don't call it from library code.
- Existing violations to avoid copying: `pdf_utils` registers an `atexit` hook at import, `utils/env.temporary_env` writes `os.environ` for the whole process, and the `pytest11` entry point (`kiln_ai.tool_testing.plugin`) loads in every pytest run of any environment that installs `kiln-ai`.

## Where things go

| You are adding | It goes in |
|---|---|
| A persisted model (task, run, eval, config) | `datamodel/`, one domain per module. `datamodel/__init__.py` re-exports the public names. |
| A model-calling adapter or a change to the run loop | `adapters/model_adapters/` |
| An eval, fine-tune, RAG, chunker, extractor, embedding or reranker implementation | the matching folder under `adapters/` |
| A tool an agent can call | `tools/` (built-ins in `tools/built_in_tools/`) |
| A model or provider entry | `adapters/ml_model_list.py`, `ml_embedding_model_list.py`, `reranker_list.py` |
| A CLI command | `cli/commands/`, registered in `cli/cli.py` |
| A small, dependency-free helper | `utils/`, only if no domain module owns it (rules.md E19) |
| Test support | `test_*.py` or `conftest.py`. The `pytest_*.py` modules in the package predate this rule; don't add more. |

**Dependency direction.** `utils/` is the bottom layer: it must not import `adapters/`, `tools/` or `datamodel/`. `utils/litellm.py` and `utils/project_utils.py` break this today; don't add more, and put helpers that need those packages in the layer that owns them. `utils/test_import_layering.py` guards the datamodel import cycle. `tools/` and `adapters/` import each other through function-local imports; don't add new cycles.

**Adding a provider** touches all of these today (grep for `ModelProviderName.<name>` to find any others):

1. `ModelProviderName` in `datamodel/datamodel_enums.py`
2. the key and env-var properties in `Config.__init__` (`utils/config.py`)
3. `provider_warnings` and `provider_name_from_id` in `adapters/provider_tools.py`
4. `lite_llm_core_config_for_provider` in `adapters/provider_tools.py`. Every case there reads `Config.shared().<key>`, so a new case FAILs `core-config-shared` (and `env-access` if it reads a base-URL env var). That is an H24 case: don't allowlist it; report it in your summary and the PR with the rule id, `path:line`, and "waits on provider config injection".
5. `get_litellm_provider_info` in `utils/litellm.py`
6. any provider branches in `LiteLlmAdapter.build_extra_body`
7. the model entries in `ml_model_list.py`

## Startup

`kiln_ai` has no process of its own. Its only entry point is the `kiln_ai` CLI (`kiln_ai.cli:app`, a Typer app built in `cli/cli.py`). Hosts (the desktop app, kiln_server, scripts) are responsible for process setup: they call `setup_litellm_logging` and `refresh_model_list_background` if they want them. Nothing in the library may do that setup at import.
